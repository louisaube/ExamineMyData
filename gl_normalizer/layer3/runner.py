"""
gl_normalizer/layer3/runner.py
Orchestration de Layer 3: Filtres Métier

Pipeline:
1. Recevoir signaux de Layer 2.5 (post-FDR)
2. Appliquer filtre matérialité
3. Appliquer règles d'exclusion (non_signal_si)
4. Calculer pertinence avec règles d'inclusion (signal_si)
5. Filtrer par seuil de pertinence
6. Ranger et retourner anomalies qualifiées

Usage:
    from layer2 import run_layer2
    from layer3 import Layer3Runner

    l2_result = run_layer2(gl, referentiel)
    runner = Layer3Runner(referentiel)
    l3_result = runner.run(l2_result.significant_signals)
    print(l3_result.summary())
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

from ..layer2.base import RawSignal

from .base import (
    QualifiedAnomaly,
    FilteredSignal,
    Layer3Result,
    FilterReason,
    PertinenceLevel,
)
from .materiality import (
    check_materiality,
    compute_materiality_amount,
    get_materiality_threshold,
    DEFAULT_MATERIALITY_THRESHOLD,
)
from .business_rules import (
    check_exclusions,
    check_inclusions,
    compute_signal_context,
    SignalContext,
    STANDARD_EXCLUSION_RULES,
    STANDARD_INCLUSION_RULES,
)
from .pertinence import (
    compute_pertinence,
    passes_pertinence_threshold,
    DEFAULT_PERTINENCE_THRESHOLD,
)


# =============================================================================
# LAYER 3 RUNNER
# =============================================================================

class Layer3Runner:
    """
    Orchestrateur de Layer 3: applique les filtres métier.

    Args:
        referentiel: Dictionnaire famille → metadata
        materiality_threshold: Seuil de matérialité par défaut (€)
        pertinence_threshold: Seuil de pertinence minimum (0-100)
        apply_exclusions: Appliquer les règles non_signal_si
        apply_inclusions: Appliquer les règles signal_si (boost)
    """

    def __init__(
        self,
        referentiel: Dict[str, Any],
        materiality_threshold: float = DEFAULT_MATERIALITY_THRESHOLD,
        pertinence_threshold: float = DEFAULT_PERTINENCE_THRESHOLD,
        apply_exclusions: bool = True,
        apply_inclusions: bool = True,
    ):
        self.referentiel = referentiel
        self.materiality_threshold = materiality_threshold
        self.pertinence_threshold = pertinence_threshold
        self.apply_exclusions = apply_exclusions
        self.apply_inclusions = apply_inclusions

    def run(
        self,
        signals: List[RawSignal],
        gl_data: Optional["pd.DataFrame"] = None,
    ) -> Layer3Result:
        """
        Exécute Layer 3 sur les signaux de Layer 2.5.

        Args:
            signals: Liste des RawSignal (post-FDR)
            gl_data: DataFrame GL optionnel pour enrichir le contexte

        Returns:
            Layer3Result avec anomalies qualifiées et signaux filtrés
        """
        qualified: List[QualifiedAnomaly] = []
        filtered_materiality: List[FilteredSignal] = []
        filtered_exclusion: List[FilteredSignal] = []
        filtered_pertinence: List[FilteredSignal] = []

        exclusion_rules_count = 0

        for signal in signals:
            # --- Étape 1: Filtre matérialité ---
            passes_mat, mat_amount, mat_threshold, mat_reason = check_materiality(
                signal,
                self.referentiel,
                override_threshold=self.materiality_threshold if self.materiality_threshold != DEFAULT_MATERIALITY_THRESHOLD else None,
            )

            if not passes_mat:
                filtered_materiality.append(FilteredSignal(
                    signal=signal,
                    filter_reason=FilterReason.BELOW_MATERIALITY,
                    filter_details=mat_reason,
                    materiality_amount=mat_amount,
                    materiality_threshold=mat_threshold,
                ))
                continue

            # --- Étape 2: Calculer contexte ---
            context = self._compute_context(signal, gl_data)

            # --- Étape 3: Règles d'exclusion ---
            if self.apply_exclusions:
                is_excluded, rules_checked, rules_matched = check_exclusions(
                    signal,
                    context,
                    self.referentiel,
                )
                exclusion_rules_count += len(rules_checked)

                if is_excluded:
                    filtered_exclusion.append(FilteredSignal(
                        signal=signal,
                        filter_reason=FilterReason.EXCLUDED_BY_RULE,
                        filter_details=f"Règles: {', '.join(rules_matched)}",
                        materiality_amount=mat_amount,
                        materiality_threshold=mat_threshold,
                        matched_exclusion_rule=rules_matched[0] if rules_matched else None,
                    ))
                    continue
            else:
                rules_checked = []
                rules_matched = []

            # --- Étape 4: Règles d'inclusion (boost) ---
            if self.apply_inclusions:
                inclusion_boost, signal_si_matched = check_inclusions(
                    signal,
                    context,
                    self.referentiel,
                )
            else:
                inclusion_boost = 0.0
                signal_si_matched = []

            # --- Étape 5: Calcul pertinence ---
            pertinence = compute_pertinence(
                signal,
                materiality_amount=mat_amount,
                materiality_threshold=mat_threshold,
                inclusion_boost=inclusion_boost,
                context=context.to_dict() if context else {},
            )

            # --- Étape 6: Filtre pertinence ---
            if not passes_pertinence_threshold(pertinence, self.pertinence_threshold):
                filtered_pertinence.append(FilteredSignal(
                    signal=signal,
                    filter_reason=FilterReason.LOW_PERTINENCE,
                    filter_details=f"Score {pertinence.final_score:.1f} < {self.pertinence_threshold}",
                    materiality_amount=mat_amount,
                    materiality_threshold=mat_threshold,
                    pertinence_score=pertinence.final_score,
                ))
                continue

            # --- Signal qualifié ---
            qualified.append(QualifiedAnomaly(
                signal=signal,
                materiality_amount=mat_amount,
                materiality_threshold=mat_threshold,
                exclusion_rules_checked=rules_checked,
                exclusion_rules_matched=[],  # Pas de match car on a passé
                is_excluded=False,
                pertinence_score=pertinence.final_score,
                pertinence_level=pertinence.level,
                signal_si_matched=signal_si_matched,
                pertinence_factors={
                    "statistical": pertinence.statistical_score,
                    "materiality": pertinence.materiality_score,
                    "business": pertinence.business_score,
                    "context": pertinence.context_score,
                },
                final_score=pertinence.final_score,
            ))

        # Trier par score décroissant et assigner les rangs
        qualified.sort(key=lambda x: x.final_score, reverse=True)
        for i, qa in enumerate(qualified):
            qa.rank = i + 1

        return Layer3Result(
            qualified=qualified,
            filtered_materiality=filtered_materiality,
            filtered_exclusion=filtered_exclusion,
            filtered_pertinence=filtered_pertinence,
            n_input=len(signals),
            n_output=len(qualified),
            n_filtered_materiality=len(filtered_materiality),
            n_filtered_exclusion=len(filtered_exclusion),
            n_filtered_pertinence=len(filtered_pertinence),
            materiality_threshold=self.materiality_threshold,
            pertinence_threshold=self.pertinence_threshold,
            exclusion_rules_applied=exclusion_rules_count,
        )

    def _compute_context(
        self,
        signal: RawSignal,
        gl_data: Optional["pd.DataFrame"],
    ) -> SignalContext:
        """
        Calcule le contexte d'un signal.

        Si gl_data est fourni, enrichit avec les données historiques.
        Sinon, utilise les métadonnées du signal.
        """
        # Contexte de base
        context = SignalContext()

        # Enrichir depuis les métadonnées du signal
        metadata = signal.metadata or {}

        # Vérifier les caractéristiques de montant
        if signal.metric_value > 0:
            context.is_round = self._is_round(signal.metric_value)

        # Vérifier la récurrence (depuis metadata)
        if "calibration_size" in metadata:
            calib_size = metadata["calibration_size"]
            context.is_monthly_recurrent = calib_size >= 6

        # Si GL disponible, enrichir davantage
        if gl_data is not None:
            context = self._enrich_context_from_gl(context, signal, gl_data)

        return context

    def _enrich_context_from_gl(
        self,
        context: SignalContext,
        signal: RawSignal,
        gl_data: "pd.DataFrame",
    ) -> SignalContext:
        """Enrichit le contexte avec les données du GL."""
        try:
            # Identifier la colonne famille
            famille_col = None
            for col in ["famille", "compte", "account"]:
                if col in gl_data.columns:
                    famille_col = col
                    break

            if famille_col is None:
                return context

            # Filtrer sur cette famille
            famille_data = gl_data[gl_data[famille_col] == signal.famille]

            if famille_data.empty:
                return context

            # Vérifier même montant sur plusieurs mois
            if "montant" in famille_data.columns and "periode" in famille_data.columns:
                monthly = famille_data.groupby("periode")["montant"].sum()
                amounts = list(monthly.values)

                if len(amounts) >= 3:
                    context.same_amount_3m = self._check_same_amount(amounts[-3:])
                if len(amounts) >= 12:
                    context.same_amount_12m = self._check_same_amount(amounts[-12:])

            # Vérifier libellés répétitifs
            if "libelle" in famille_data.columns:
                labels = famille_data["libelle"].dropna().tolist()
                context.repetitive_label = self._check_repetitive_labels(labels)

            # Vérifier solde à zéro
            if "montant" in famille_data.columns:
                solde = famille_data["montant"].sum()
                context.solde_zero = abs(solde) < 0.01

        except Exception:
            # En cas d'erreur, retourner le contexte non enrichi
            pass

        return context

    @staticmethod
    def _is_round(amount: float) -> bool:
        """Vérifie si un montant est rond."""
        if amount <= 0:
            return False
        for base in [100, 500, 1000, 5000]:
            if abs(amount % base) < 0.01 * base:
                return True
        return False

    @staticmethod
    def _check_same_amount(amounts: List[float], tolerance: float = 0.001) -> bool:
        """Vérifie si tous les montants sont identiques."""
        if not amounts:
            return False
        first = amounts[0]
        if first == 0:
            return all(a == 0 for a in amounts)
        return all(abs(a - first) / abs(first) < tolerance for a in amounts)

    @staticmethod
    def _check_repetitive_labels(labels: List[str]) -> bool:
        """Vérifie si un libellé se répète."""
        if len(labels) < 3:
            return False
        from collections import Counter
        normalized = [l.strip().lower() for l in labels if l]
        counts = Counter(normalized)
        if not counts:
            return False
        most_common = counts.most_common(1)[0][1]
        return most_common >= 3 and most_common / len(normalized) > 0.5


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def run_layer3(
    signals: List[RawSignal],
    referentiel: Dict[str, Any],
    materiality_threshold: float = DEFAULT_MATERIALITY_THRESHOLD,
    pertinence_threshold: float = DEFAULT_PERTINENCE_THRESHOLD,
    gl_data: Optional["pd.DataFrame"] = None,
) -> Layer3Result:
    """
    Fonction raccourcie pour exécuter Layer 3.

    Args:
        signals: Signaux de Layer 2.5
        referentiel: Référentiel sémantique
        materiality_threshold: Seuil de matérialité
        pertinence_threshold: Seuil de pertinence
        gl_data: DataFrame GL optionnel

    Returns:
        Layer3Result
    """
    runner = Layer3Runner(
        referentiel,
        materiality_threshold=materiality_threshold,
        pertinence_threshold=pertinence_threshold,
    )
    return runner.run(signals, gl_data)


def run_full_pipeline(
    gl: "pd.DataFrame",
    referentiel: Dict[str, Any],
    fdr_alpha: float = 0.05,
    materiality_threshold: float = DEFAULT_MATERIALITY_THRESHOLD,
    pertinence_threshold: float = DEFAULT_PERTINENCE_THRESHOLD,
) -> Layer3Result:
    """
    Exécute le pipeline complet Layer 2 + Layer 2.5 + Layer 3.

    Args:
        gl: DataFrame du Grand Livre
        referentiel: Référentiel sémantique
        fdr_alpha: Niveau FDR pour Layer 2.5
        materiality_threshold: Seuil de matérialité
        pertinence_threshold: Seuil de pertinence

    Returns:
        Layer3Result avec anomalies qualifiées
    """
    from ..layer2 import run_layer2

    # Layer 2 + 2.5
    l2_result = run_layer2(gl, referentiel, fdr_alpha=fdr_alpha)

    # Layer 3
    l3_result = run_layer3(
        l2_result.significant_signals,
        referentiel,
        materiality_threshold=materiality_threshold,
        pertinence_threshold=pertinence_threshold,
        gl_data=gl,
    )

    return l3_result
