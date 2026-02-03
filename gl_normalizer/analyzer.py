"""
gl_normalizer/analyzer.py
Analyseur principal intégrant tous les composants

Fournit:
- Analyse complète GL avec contexte PCG
- Orchestration des détecteurs
- Rapport consolidé d'anomalies
- Calcul du run rate normalisé
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Any
from enum import Enum

from .accounting_context import AccountingContext, get_pcg_context, AccountClassification
from .profiler import Profiler, DataProfileResult
from .detector import AnomalyDetector, DetectionResult
from .regularization import RegularizationDetector, RegularizationAnalysis
from .pnl_normalizer import PnLNormalizer, NormalizedPLResult, ProvisionAnalysis


class AnomalyCategory(Enum):
    """Catégories d'anomalies avec contexte PCG"""
    PROVISION_NORMALE = "provision_normale"         # Provision selon PCG
    PROVISION_SUSPECTE = "provision_suspecte"       # Provision hors contexte
    REGULARISATION_NORMALE = "regularisation_normale"
    REGULARISATION_EXCESSIVE = "regularisation_excessive"
    CONCENTRATION_EXPLIQUEE = "concentration_expliquee"  # PCG l'explique
    CONCENTRATION_ANORMALE = "concentration_anormale"
    MONTANT_ROND_JUSTIFIE = "montant_rond_justifie"
    MONTANT_ROND_SUSPECT = "montant_rond_suspect"


@dataclass
class ContextualizedAnomaly:
    """Anomalie avec contexte PCG"""
    compte: str
    libelle_compte: str
    anomaly_type: str             # Type d'anomalie original
    category: AnomalyCategory     # Catégorie après contexte PCG
    montant: float
    details: str
    pcg_context: Optional[str]    # Info PCG
    is_expected: bool             # True si comportement attendu selon PCG
    severity: str                 # low, medium, high, critical
    recommendation: str           # Recommandation


@dataclass
class RunRateResult:
    """Résultat du calcul du run rate"""
    year: int

    # P&L brut
    charges_brutes: float
    produits_bruts: float
    resultat_brut: float

    # P&L normalisé (run rate)
    charges_run_rate: float
    produits_run_rate: float  # Généralement = brut
    resultat_run_rate: float

    # Ajustements
    total_ajustement_provisions: float
    total_ajustement_regularisations: float
    nb_comptes_ajustes: int

    # Détail mensuel run rate
    run_rate_mensuel: float

    # Confiance
    confidence_score: float       # 0-1


@dataclass
class FullAnalysisResult:
    """Résultat complet de l'analyse GL"""
    year: int

    # Qualité des données
    data_quality: str
    row_count: int
    account_count: int
    filename: Optional[str] = None

    # Profil
    profile: Optional[DataProfileResult] = None

    # Détections
    detection_result: Optional[DetectionResult] = None
    regularization_result: Optional[RegularizationAnalysis] = None

    # Anomalies contextualisées
    anomalies: List[ContextualizedAnomaly] = field(default_factory=list)
    anomalies_by_category: Dict[str, int] = field(default_factory=dict)

    # Run rate
    run_rate: Optional[RunRateResult] = None

    # Scores
    overall_risk_score: float = 0.0
    data_confidence_score: float = 0.0

    # Résumé
    summary: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class GLAnalyzer:
    """
    Analyseur principal orchestrant tous les composants.

    Intègre:
    - AccountingContext pour le référentiel PCG
    - Profiler pour les stats
    - AnomalyDetector pour les détections
    - RegularizationDetector pour les régularisations
    - PnLNormalizer pour le run rate
    """

    def __init__(
        self,
        df: pd.DataFrame,
        year: int,
        accounting_context: Optional[AccountingContext] = None,
    ):
        """
        Args:
            df: DataFrame GL classifié
            year: Année à analyser
            accounting_context: Contexte PCG (optionnel)
        """
        self.df = df.copy()
        self.year = year
        self.ctx = accounting_context or get_pcg_context()

        # Filtrer sur l'année
        if "annee" in self.df.columns:
            self.df = self.df[self.df["annee"] == year]

    def analyze(self) -> FullAnalysisResult:
        """
        Exécute l'analyse complète.

        Returns:
            FullAnalysisResult avec tous les résultats
        """
        result = FullAnalysisResult(
            year=self.year,
            data_quality="unknown",
            row_count=len(self.df),
            account_count=self.df["compte"].nunique() if "compte" in self.df.columns else 0,
        )

        # 1. Profilage
        result.profile = self._run_profiler()
        result.data_quality = result.profile.data_quality.value if result.profile else "unknown"

        # 2. Détection d'anomalies
        result.detection_result = self._run_detector()

        # 3. Détection des régularisations
        result.regularization_result = self._run_regularization_detector()

        # 4. Contextualiser les anomalies avec PCG
        result.anomalies = self._contextualize_anomalies(
            result.detection_result,
            result.regularization_result,
        )

        # Comptage par catégorie
        for a in result.anomalies:
            cat = a.category.value
            result.anomalies_by_category[cat] = result.anomalies_by_category.get(cat, 0) + 1

        # 5. Calcul du run rate
        result.run_rate = self._compute_run_rate()

        # 6. Scores globaux
        result.overall_risk_score = self._compute_overall_risk(result)
        result.data_confidence_score = self._compute_confidence(result)

        # 7. Résumé et recommandations
        result.summary = self._build_summary(result)
        result.warnings = self._collect_warnings(result)
        result.recommendations = self._build_recommendations(result)

        return result

    def _run_profiler(self) -> Optional[DataProfileResult]:
        """Exécute le profilage"""
        try:
            profiler = Profiler(self.df, self.year)
            return profiler.profile()
        except Exception as e:
            return None

    def _run_detector(self) -> Optional[DetectionResult]:
        """Exécute la détection d'anomalies"""
        try:
            detector = AnomalyDetector(self.df, self.year)
            return detector.detect_all()
        except Exception as e:
            return None

    def _run_regularization_detector(self) -> Optional[RegularizationAnalysis]:
        """Exécute la détection des régularisations"""
        try:
            detector = RegularizationDetector(self.df, self.year, self.ctx)
            return detector.get_full_analysis()
        except Exception as e:
            return None

    def _contextualize_anomalies(
        self,
        detection: Optional[DetectionResult],
        regularization: Optional[RegularizationAnalysis],
    ) -> List[ContextualizedAnomaly]:
        """Contextualise les anomalies avec le PCG"""
        anomalies = []

        # Contextualiser les concentrations
        if detection:
            for conc in detection.concentrations:
                compte = self._extract_compte(conc.value)
                if compte:
                    anomalies.append(self._contextualize_concentration(compte, conc))

            # Contextualiser les montants ronds
            for rond in detection.round_amounts:
                anomalies.append(self._contextualize_round_amount(rond))

        # Contextualiser les régularisations
        if regularization:
            for regul in regularization.regularizations[:50]:  # Top 50
                anomalies.append(self._contextualize_regularization(regul))

        # Trier par sévérité
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        anomalies.sort(key=lambda x: severity_order.get(x.severity, 4))

        return anomalies

    def _extract_compte(self, value: str) -> Optional[str]:
        """Extrait un numéro de compte d'une valeur"""
        import re
        match = re.match(r"(\d{5,})", value)
        return match.group(1) if match else None

    def _contextualize_concentration(self, compte: str, conc) -> ContextualizedAnomaly:
        """Contextualise une concentration avec le PCG"""
        classif = self.ctx.classify_account(compte)
        behavior = self.ctx.get_expected_behavior(compte)

        # Déterminer si la concentration est attendue selon le PCG
        is_expected = False
        category = AnomalyCategory.CONCENTRATION_ANORMALE

        if classif:
            # Les comptes annuels ont une concentration normale
            if classif.frequency.value == "annuelle":
                is_expected = True
                category = AnomalyCategory.CONCENTRATION_EXPLIQUEE

            # Les provisions sont souvent concentrées
            if classif.is_provision_compte:
                is_expected = True
                category = AnomalyCategory.PROVISION_NORMALE

        # Sévérité ajustée selon contexte
        if is_expected:
            severity = "low"
        elif conc.percentage > 90:
            severity = "high"
        else:
            severity = "medium"

        return ContextualizedAnomaly(
            compte=compte,
            libelle_compte="",
            anomaly_type="concentration",
            category=category,
            montant=conc.amount,
            details=f"{conc.percentage:.1f}% sur {conc.dimension}",
            pcg_context=classif.libelle_pcg if classif else None,
            is_expected=is_expected,
            severity=severity,
            recommendation=self._get_concentration_recommendation(is_expected, conc.percentage),
        )

    def _contextualize_round_amount(self, rond) -> ContextualizedAnomaly:
        """Contextualise un montant rond avec le PCG"""
        classif = self.ctx.classify_account(rond.compte)

        # Les provisions et impôts ont souvent des montants ronds
        is_expected = False
        if classif and classif.categorie in ["dotations", "reprises", "is", "taxes"]:
            is_expected = True

        category = (
            AnomalyCategory.MONTANT_ROND_JUSTIFIE if is_expected
            else AnomalyCategory.MONTANT_ROND_SUSPECT
        )

        return ContextualizedAnomaly(
            compte=rond.compte,
            libelle_compte=rond.libelle_compte,
            anomaly_type="montant_rond",
            category=category,
            montant=rond.total_amount,
            details=f"{rond.amount:,.0f}€ x{rond.occurrences}",
            pcg_context=classif.libelle_pcg if classif else None,
            is_expected=is_expected,
            severity="low" if is_expected else "medium",
            recommendation="Vérifier la nature des écritures" if not is_expected else "",
        )

    def _contextualize_regularization(self, regul) -> ContextualizedAnomaly:
        """Contextualise une régularisation"""
        classif = self.ctx.classify_account(regul.compte)

        # Les régularisations sont attendues sur certains comptes
        is_expected = False
        if classif and classif.is_regul_typical:
            is_expected = True

        category = (
            AnomalyCategory.REGULARISATION_NORMALE if is_expected
            else AnomalyCategory.REGULARISATION_EXCESSIVE
        )

        return ContextualizedAnomaly(
            compte=regul.compte,
            libelle_compte=regul.libelle_compte,
            anomaly_type=regul.type.value,
            category=category,
            montant=regul.montant,
            details=f"{regul.type.value} ({regul.confidence:.0%})",
            pcg_context=regul.pcg_context,
            is_expected=is_expected,
            severity="low" if is_expected else "medium",
            recommendation="",
        )

    def _get_concentration_recommendation(self, is_expected: bool, pct: float) -> str:
        """Génère une recommandation pour une concentration"""
        if is_expected:
            return ""
        if pct > 80:
            return "Vérifier si provision ou régularisation justifiée"
        return "Analyser la nature des écritures concentrées"

    def _compute_run_rate(self) -> Optional[RunRateResult]:
        """Calcule le run rate normalisé"""
        try:
            normalizer = PnLNormalizer(self.df, self.year)
            norm_result = normalizer.compute_normalized_december()

            # Calcul du run rate annuel
            charges_annuelles = self.df[self.df["classe"] == "6"]["montant"].sum()
            produits_annuels = self.df[self.df["classe"] == "7"]["montant"].sum()

            run_rate_mensuel = abs(charges_annuelles) / 12

            return RunRateResult(
                year=self.year,
                charges_brutes=abs(charges_annuelles),
                produits_bruts=abs(produits_annuels),
                resultat_brut=abs(produits_annuels) - abs(charges_annuelles),
                charges_run_rate=run_rate_mensuel * 12,
                produits_run_rate=abs(produits_annuels),
                resultat_run_rate=abs(produits_annuels) - (run_rate_mensuel * 12),
                total_ajustement_provisions=norm_result.total_ajustement,
                total_ajustement_regularisations=0,  # TODO: calculer
                nb_comptes_ajustes=norm_result.nb_comptes_ajustes,
                run_rate_mensuel=run_rate_mensuel,
                confidence_score=0.8,  # TODO: calculer
            )
        except Exception as e:
            return None

    def _compute_overall_risk(self, result: FullAnalysisResult) -> float:
        """Calcule le score de risque global"""
        score = 0.0

        # Risque des détections
        if result.detection_result:
            score += result.detection_result.risk_score * 0.3

        # Risque des régularisations
        if result.regularization_result:
            score += result.regularization_result.risk_score * 0.3

        # Ratio d'anomalies non attendues
        unexpected = [a for a in result.anomalies if not a.is_expected]
        if result.anomalies:
            ratio = len(unexpected) / len(result.anomalies)
            score += ratio * 0.4

        return min(score, 1.0)

    def _compute_confidence(self, result: FullAnalysisResult) -> float:
        """Calcule le score de confiance dans l'analyse"""
        score = 1.0

        # Qualité des données
        quality_penalty = {
            "excellent": 0,
            "good": 0.1,
            "acceptable": 0.2,
            "poor": 0.4,
        }
        score -= quality_penalty.get(result.data_quality, 0.3)

        # Nombre d'écritures
        if result.row_count < 1000:
            score -= 0.1
        elif result.row_count < 100:
            score -= 0.3

        return max(score, 0.1)

    def _build_summary(self, result: FullAnalysisResult) -> Dict[str, Any]:
        """Construit le résumé"""
        return {
            "year": self.year,
            "total_ecritures": result.row_count,
            "total_comptes": result.account_count,
            "data_quality": result.data_quality,
            "total_anomalies": len(result.anomalies),
            "anomalies_attendues": len([a for a in result.anomalies if a.is_expected]),
            "anomalies_suspectes": len([a for a in result.anomalies if not a.is_expected]),
            "risk_score": f"{result.overall_risk_score:.0%}",
            "run_rate_mensuel": result.run_rate.run_rate_mensuel if result.run_rate else 0,
        }

    def _collect_warnings(self, result: FullAnalysisResult) -> List[str]:
        """Collecte les warnings"""
        warnings = []

        if result.profile and result.profile.warnings:
            warnings.extend(result.profile.warnings)

        # Ajouter warnings spécifiques
        unexpected_high = [
            a for a in result.anomalies
            if not a.is_expected and a.severity in ["high", "critical"]
        ]
        if unexpected_high:
            warnings.append(
                f"{len(unexpected_high)} anomalies à haute sévérité non expliquées par le PCG"
            )

        return warnings

    def _build_recommendations(self, result: FullAnalysisResult) -> List[str]:
        """Construit les recommandations"""
        recs = []

        # Recommandations générales
        if result.overall_risk_score > 0.7:
            recs.append("Risque élevé: audit approfondi recommandé")
        elif result.overall_risk_score > 0.4:
            recs.append("Risque modéré: vérifier les anomalies prioritaires")

        # Recommandations des profils
        if result.profile and result.profile.recommendations:
            recs.extend(result.profile.recommendations[:3])

        # Recommandations spécifiques aux anomalies
        for a in result.anomalies:
            if a.recommendation and a.recommendation not in recs:
                recs.append(a.recommendation)
                if len(recs) >= 10:
                    break

        return recs


def analyze_gl(
    df: pd.DataFrame,
    year: int,
) -> FullAnalysisResult:
    """
    Fonction utilitaire pour analyser un GL complet.

    Args:
        df: DataFrame GL
        year: Année à analyser

    Returns:
        FullAnalysisResult avec tous les résultats
    """
    analyzer = GLAnalyzer(df, year)
    return analyzer.analyze()


if __name__ == "__main__":
    print("GLAnalyzer - Analyse complète GL avec contexte PCG")
    print("=" * 60)
    print("Usage:")
    print("  from gl_normalizer.analyzer import analyze_gl")
    print("  result = analyze_gl(df, year=2024)")
    print("  print(f'Risk: {result.overall_risk_score:.0%}')")
    print("  print(f'Anomalies: {len(result.anomalies)}')")
