"""
gl_normalizer/layer2/runner.py
Orchestration de Layer 2: Tests de Normalité par Univers

Pipeline:
1. Charger GL + référentiel
2. Pour chaque famille: appliquer tests selon univers
3. Collecter tous les signaux avec p-values
4. Appliquer BH-FDR (Layer 2.5)
5. Retourner signaux significatifs

Usage:
    runner = Layer2Runner(referentiel)
    result = runner.run(gl_dataframe)
    print(f"{result.n_significant} signaux significatifs sur {result.n_total}")
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable
import numpy as np

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from .base import RawSignal, FamilySignal, Univers
from .calibration import conformal_pvalue, conformal_or_fallback, MIN_MOIS_CONFORMAL
from .statistical import matrix_profile_discord, detect_discord_months, is_stumpy_available
from .fdr_filter import fdr_filter, FDRResult


# =============================================================================
# RESULT DATACLASS
# =============================================================================

@dataclass
class Layer2Result:
    """Résultat de l'exécution de Layer 2."""
    # Signaux
    all_signals: List[RawSignal]           # Tous les signaux bruts
    significant_signals: List[RawSignal]   # Après FDR filter
    rejected_signals: List[RawSignal]      # Non significatifs

    # Agrégation par famille
    family_signals: List[FamilySignal]

    # Stats
    n_total: int
    n_significant: int
    n_families_tested: int
    n_families_with_signals: int

    # FDR info
    fdr_level: float
    adjusted_pvalues: List[float]

    # Méthodes utilisées
    methods_used: Dict[str, int]  # {"conformal": 150, "matrix_profile": 23, ...}

    def summary(self) -> str:
        """Résumé textuel."""
        return f"""
Layer 2 Results:
  Familles testées: {self.n_families_tested}
  Familles avec signaux: {self.n_families_with_signals}
  Signaux bruts: {self.n_total}
  Signaux significatifs (FDR={self.fdr_level}): {self.n_significant}
  Taux de réduction: {100 * (1 - self.n_significant / max(self.n_total, 1)):.0f}%

Méthodes: {self.methods_used}
"""


# =============================================================================
# LAYER 2 RUNNER
# =============================================================================

class Layer2Runner:
    """
    Orchestrateur de Layer 2: exécute les tests par univers sur le GL.

    Args:
        referentiel: Dictionnaire famille → {univers, cv_montant, signal_si, non_signal_si, ...}
        fdr_alpha: Niveau FDR pour le filtrage (défaut: 0.05)
        use_matrix_profile: Activer Matrix Profile pour CRISTALLIN/PROCESSUS
        use_ecod: Activer ECOD pour scoring multivarié
    """

    def __init__(
        self,
        referentiel: Dict[str, Any],
        fdr_alpha: float = 0.05,
        use_matrix_profile: bool = True,
        use_ecod: bool = True,
    ):
        self.referentiel = referentiel
        self.fdr_alpha = fdr_alpha
        self.use_matrix_profile = use_matrix_profile and is_stumpy_available()
        self.use_ecod = use_ecod

        # Stats de méthodes
        self.methods_used: Dict[str, int] = {}

    def run(self, gl: "pd.DataFrame") -> Layer2Result:
        """
        Exécute Layer 2 sur le GL complet.

        Args:
            gl: DataFrame du Grand Livre avec colonnes:
                - compte ou famille: code compte/famille
                - periode: période (ex: "2024-01")
                - montant: montant de l'écriture
                - journal: code journal (optionnel)
                - libelle: libellé (optionnel)
                - site: code site (optionnel)

        Returns:
            Layer2Result avec tous les signaux et stats
        """
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas requis pour Layer2Runner")

        all_signals: List[RawSignal] = []
        family_signals: List[FamilySignal] = []
        self.methods_used = {}

        # Identifier la colonne famille
        famille_col = self._get_famille_column(gl)

        # Grouper par famille
        families = gl[famille_col].unique()

        for famille in families:
            famille_str = str(famille)
            famille_data = gl[gl[famille_col] == famille]

            # Lookup univers dans référentiel
            ref_entry = self.referentiel.get(famille_str, {})
            univers_str = ref_entry.get("univers", "COMPOSITE")
            try:
                univers = Univers(univers_str)
            except ValueError:
                univers = Univers.COMPOSITE

            # Exécuter les tests pour cette famille
            signals = self._test_famille(famille_str, famille_data, univers, ref_entry)

            if signals:
                all_signals.extend(signals)

                # Créer FamilySignal agrégé
                family_signal = FamilySignal(
                    famille=famille_str,
                    univers=univers,
                    tests_triggered=[s.test_id for s in signals],
                    max_score=max(s.raw_score for s in signals),
                    signals=signals,
                    summary=f"{len(signals)} signaux détectés"
                )
                family_signals.append(family_signal)

        # Appliquer FDR filter
        if all_signals:
            fdr_result = fdr_filter(
                all_signals,
                pvalue_extractor=lambda s: s.pvalue if s.pvalue is not None else 1.0,
                alpha=self.fdr_alpha
            )

            # Mettre à jour pvalue_adjusted
            for signal, adj_p in zip(all_signals, fdr_result.adjusted_pvalues):
                signal.pvalue_adjusted = adj_p

            significant = fdr_result.significant
            rejected = fdr_result.rejected
            adjusted_pvalues = fdr_result.adjusted_pvalues
        else:
            significant = []
            rejected = []
            adjusted_pvalues = []

        return Layer2Result(
            all_signals=all_signals,
            significant_signals=significant,
            rejected_signals=rejected,
            family_signals=family_signals,
            n_total=len(all_signals),
            n_significant=len(significant),
            n_families_tested=len(families),
            n_families_with_signals=len(family_signals),
            fdr_level=self.fdr_alpha,
            adjusted_pvalues=adjusted_pvalues,
            methods_used=self.methods_used.copy(),
        )

    def _get_famille_column(self, gl: "pd.DataFrame") -> str:
        """Identifie la colonne famille/compte dans le GL."""
        for col in ["famille", "compte", "account", "compte_general"]:
            if col in gl.columns:
                return col
        raise ValueError("Colonne famille/compte non trouvée dans le GL")

    def _test_famille(
        self,
        famille: str,
        data: "pd.DataFrame",
        univers: Univers,
        ref_entry: Dict[str, Any]
    ) -> List[RawSignal]:
        """
        Exécute les tests appropriés pour une famille selon son univers.

        Applique:
        - Conformal p-value sur variation montant (tous univers)
        - Matrix Profile (CRISTALLIN, PROCESSUS)
        - Tests spécifiques univers
        """
        signals: List[RawSignal] = []

        # Agréger par période
        monthly = self._aggregate_monthly(data)
        if len(monthly) < 2:
            return signals  # Pas assez de données

        periods = sorted(monthly.keys())
        amounts = [monthly[p] for p in periods]

        cv_attendu = ref_entry.get("cv_montant", 1.0)

        # --- Test 1: Conformal/Variation sur dernier mois ---
        if len(amounts) >= 2:
            calibration = amounts[:-1]
            test_value = amounts[-1]
            test_period = periods[-1]

            score, is_signal, method = conformal_or_fallback(
                test_value, calibration, cv_attendu, alpha=0.05
            )

            self._count_method(method)

            if is_signal:
                pvalue = score if method == "conformal" else None
                signals.append(RawSignal(
                    id=f"L2-VAR_{famille}_{test_period}",
                    famille=famille,
                    univers=univers,
                    test_id="L2-VAR",
                    test_name="Variation mensuelle",
                    metric_value=test_value,
                    threshold=np.median(calibration),
                    delta=abs(test_value - np.median(calibration)),
                    periode=test_period,
                    pvalue=pvalue,
                    detection_method=method,
                    metadata={"calibration_size": len(calibration)}
                ))

        # --- Test 2: Matrix Profile (CRISTALLIN, PROCESSUS) ---
        if self.use_matrix_profile and univers in [Univers.CRISTALLIN, Univers.PROCESSUS]:
            if len(amounts) >= 6:
                discord_idx, discord_dist, mp_pvalue = matrix_profile_discord(amounts)

                if discord_idx is not None and mp_pvalue is not None and mp_pvalue < 0.1:
                    self._count_method("matrix_profile")
                    discord_period = periods[discord_idx] if discord_idx < len(periods) else None

                    signals.append(RawSignal(
                        id=f"L2-DISCORD_{famille}_{discord_period}",
                        famille=famille,
                        univers=univers,
                        test_id="L2-DISCORD",
                        test_name="Discord Matrix Profile",
                        metric_value=amounts[discord_idx] if discord_idx < len(amounts) else 0,
                        threshold=np.median(amounts),
                        delta=discord_dist or 0,
                        periode=discord_period,
                        pvalue=mp_pvalue,
                        detection_method="matrix_profile",
                        metadata={"discord_distance": discord_dist}
                    ))

        # --- Test 3: Mois manquant (CRISTALLIN) ---
        if univers == Univers.CRISTALLIN:
            expected_months = 12
            if len(monthly) < expected_months:
                missing_count = expected_months - len(monthly)
                # P-value heuristique: plus il manque de mois, plus c'est anormal
                pvalue_missing = max(0.01, 1.0 - (missing_count / expected_months))

                self._count_method("missing_month")
                signals.append(RawSignal(
                    id=f"L2-MISSING_{famille}",
                    famille=famille,
                    univers=univers,
                    test_id="L2-MISSING",
                    test_name="Mois manquant",
                    metric_value=len(monthly),
                    threshold=expected_months,
                    delta=missing_count,
                    pvalue=pvalue_missing if missing_count >= 2 else None,
                    detection_method="rule_based",
                    metadata={"missing_count": missing_count}
                ))

        # --- Test 4: Concentration mensuelle (tous sauf CUT_OFF) ---
        if univers != Univers.CUT_OFF and len(amounts) >= 3:
            total = sum(abs(a) for a in amounts)
            if total > 0:
                max_month_pct = max(abs(a) for a in amounts) / total

                # Seuil selon univers
                threshold_pct = 0.5 if univers != Univers.PONCTUEL else 0.8

                if max_month_pct > threshold_pct:
                    max_idx = amounts.index(max(amounts, key=abs))
                    max_period = periods[max_idx]

                    # P-value approximative
                    pvalue_conc = conformal_pvalue(max_month_pct, [abs(a)/total for a in amounts])

                    self._count_method("concentration")
                    signals.append(RawSignal(
                        id=f"L2-CONC_{famille}_{max_period}",
                        famille=famille,
                        univers=univers,
                        test_id="L2-CONC",
                        test_name="Concentration mensuelle",
                        metric_value=max_month_pct,
                        threshold=threshold_pct,
                        delta=max_month_pct - threshold_pct,
                        periode=max_period,
                        pvalue=pvalue_conc,
                        detection_method="conformal",
                        metadata={"max_month_pct": max_month_pct}
                    ))

        return signals

    def _aggregate_monthly(self, data: "pd.DataFrame") -> Dict[str, float]:
        """Agrège les montants par période."""
        if "periode" not in data.columns:
            # Essayer de créer depuis date
            if "date" in data.columns:
                data = data.copy()
                data["periode"] = pd.to_datetime(data["date"]).dt.strftime("%Y-%m")
            else:
                return {}

        montant_col = None
        for col in ["montant", "amount", "debit", "credit"]:
            if col in data.columns:
                montant_col = col
                break

        if montant_col is None:
            return {}

        grouped = data.groupby("periode")[montant_col].sum()
        return grouped.to_dict()

    def _count_method(self, method: str):
        """Comptabilise l'utilisation d'une méthode."""
        self.methods_used[method] = self.methods_used.get(method, 0) + 1


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def run_layer2(
    gl: "pd.DataFrame",
    referentiel: Dict[str, Any],
    fdr_alpha: float = 0.05
) -> Layer2Result:
    """
    Fonction raccourcie pour exécuter Layer 2.

    Args:
        gl: DataFrame du Grand Livre
        referentiel: Référentiel sémantique
        fdr_alpha: Niveau FDR

    Returns:
        Layer2Result
    """
    runner = Layer2Runner(referentiel, fdr_alpha=fdr_alpha)
    return runner.run(gl)
