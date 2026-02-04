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

# Import advanced stats
from .advanced_stats import (
    MADDetector, MADResult,
    IQRDetector, IQRResult,
    SeasonalDecomposer, SeasonalityResult, SeasonalPattern,
    AccountClusterer, ClusteringSummary, AccountBehaviorCluster,
    detect_anomalies_robust,
    analyze_seasonality,
    cluster_accounts,
)

# Import AI modules conditionally
AI_AVAILABLE = False
try:
    from .ai.benford import BenfordAnalyzer, BenfordAnalysis, analyze_benford
    from .ai.isolation_forest import IsolationForestDetector, IsolationForestAnalysis, detect_anomalies_iforest
    from .ai.nlp_analyzer import NLPAnalyzer, NLPAnalysis, analyze_labels
    from .ai.risk_scorer import RiskScorer, RiskAnalysis, calculate_risk_scores, RiskLevel
    AI_AVAILABLE = True
except ImportError:
    pass


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
class PLCategory:
    """Catégorie de P&L avec montants"""
    name: str
    code: str
    total: float
    count: int  # Nombre de comptes
    pct_total: float  # % du total charges ou produits


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

    # Détail P&L par catégorie
    charges_by_category: List[PLCategory] = field(default_factory=list)
    produits_by_category: List[PLCategory] = field(default_factory=list)


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

    # Advanced Statistics (STORY-024, 025, 026)
    mad_results: Optional[List[Any]] = None       # MAD detector results
    iqr_results: Optional[List[Any]] = None       # IQR detector results
    seasonality: Optional[Dict[str, Any]] = None  # Seasonal decomposition
    clustering: Optional[Dict[str, Any]] = None   # Account behavioral clusters

    # AI Analysis (Benford, Isolation Forest, NLP, Risk Scoring)
    ai_available: bool = False
    benford_analysis: Optional[Dict[str, Any]] = None
    isolation_forest: Optional[Dict[str, Any]] = None
    nlp_analysis: Optional[Dict[str, Any]] = None
    combined_risk_scores: Optional[Dict[str, Any]] = None

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

        # 6. Advanced Statistics (MAD, IQR, Seasonality, Clustering)
        result.mad_results, result.iqr_results = self._run_advanced_stats()
        result.seasonality = self._run_seasonality_analysis()
        result.clustering = self._run_clustering()

        # 7. AI Pipeline (Benford, Isolation Forest, NLP, Risk Scoring)
        result.ai_available = AI_AVAILABLE
        if AI_AVAILABLE:
            result.benford_analysis = self._run_benford()
            result.isolation_forest = self._run_isolation_forest()
            result.nlp_analysis = self._run_nlp_analysis()
            result.combined_risk_scores = self._run_risk_scoring(result)

        # 8. Scores globaux
        result.overall_risk_score = self._compute_overall_risk(result)
        result.data_confidence_score = self._compute_confidence(result)

        # 9. Résumé et recommandations
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

        # Classe du compte (1er caractère)
        classe = compte[0] if compte else ""

        if classif:
            # Les comptes annuels/exceptionnels ont une concentration normale
            if classif.frequency.value in ["annuelle", "exceptionnelle"]:
                is_expected = True
                category = AnomalyCategory.CONCENTRATION_EXPLIQUEE

            # Les provisions sont souvent concentrées
            if classif.is_provision_compte:
                is_expected = True
                category = AnomalyCategory.PROVISION_NORMALE

            # Les régularisations sont normales en fin d'année
            if classif.behavior.value == "regularisation":
                is_expected = True
                category = AnomalyCategory.REGULARISATION_NORMALE

        # Règles par classe de compte (même sans classification PCG détaillée)
        if classe == "2":
            # Immobilisations : mouvements ponctuels normaux
            is_expected = True
            category = AnomalyCategory.CONCENTRATION_EXPLIQUEE
        elif classe == "1":
            # Capitaux : mouvements exceptionnels normaux
            is_expected = True
            category = AnomalyCategory.CONCENTRATION_EXPLIQUEE
        elif compte[:2] in ["68", "78"]:
            # Dotations/Reprises : concentration normale
            is_expected = True
            category = AnomalyCategory.PROVISION_NORMALE
        elif compte[:3] in ["486", "487", "408", "418", "428", "438", "448"]:
            # Comptes de régularisation
            is_expected = True
            category = AnomalyCategory.REGULARISATION_NORMALE

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
            pcg_context=classif.libelle_pcg if classif else self._get_default_pcg_context(compte),
            is_expected=is_expected,
            severity=severity,
            recommendation=self._get_concentration_recommendation(is_expected, conc.percentage),
        )

    def _get_default_pcg_context(self, compte: str) -> str:
        """Retourne un contexte PCG par défaut basé sur la classe du compte"""
        if not compte:
            return ""
        classe = compte[0]
        contexts = {
            "1": "Comptes de capitaux",
            "2": "Immobilisations (mouvement ponctuel normal)",
            "3": "Stocks et en-cours",
            "4": "Comptes de tiers",
            "5": "Comptes financiers",
            "6": "Charges",
            "7": "Produits",
        }
        return contexts.get(classe, "")

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
            df_charges = self.df[self.df["classe"] == "6"]
            df_produits = self.df[self.df["classe"] == "7"]

            charges_annuelles = df_charges["montant"].sum()
            produits_annuels = df_produits["montant"].sum()

            run_rate_mensuel = abs(charges_annuelles) / 12

            # Calcul du détail par catégorie de charges
            charges_by_cat = self._compute_pl_categories(df_charges, "charges")
            produits_by_cat = self._compute_pl_categories(df_produits, "produits")

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
                charges_by_category=charges_by_cat,
                produits_by_category=produits_by_cat,
            )
        except Exception as e:
            return None

    def _compute_pl_categories(self, df: pd.DataFrame, pl_type: str) -> List[PLCategory]:
        """Calcule le détail P&L par catégorie"""
        if df.empty or "compte" not in df.columns:
            return []

        # Mapping des racines vers catégories
        if pl_type == "charges":
            cat_mapping = {
                "60": ("Achats", "60"),
                "61": ("Services extérieurs", "61"),
                "62": ("Autres services ext.", "62"),
                "63": ("Impôts et taxes", "63"),
                "64": ("Charges de personnel", "64"),
                "65": ("Autres charges gestion", "65"),
                "66": ("Charges financières", "66"),
                "67": ("Charges exceptionnelles", "67"),
                "68": ("Dotations amort./prov.", "68"),
                "69": ("Impôt sur les bénéfices", "69"),
            }
        else:
            cat_mapping = {
                "70": ("Ventes et prestations", "70"),
                "71": ("Production stockée", "71"),
                "72": ("Production immobilisée", "72"),
                "74": ("Subventions", "74"),
                "75": ("Autres produits gestion", "75"),
                "76": ("Produits financiers", "76"),
                "77": ("Produits exceptionnels", "77"),
                "78": ("Reprises amort./prov.", "78"),
                "79": ("Transferts de charges", "79"),
            }

        # Extraire la racine à 2 caractères
        df = df.copy()
        df["racine"] = df["compte"].astype(str).str[:2]

        # Agréger par racine
        agg = df.groupby("racine").agg(
            total=("montant", lambda x: abs(x.sum())),
            count=("compte", "nunique")
        ).reset_index()

        total_all = agg["total"].sum()

        categories = []
        for _, row in agg.iterrows():
            racine = row["racine"]
            if racine in cat_mapping:
                name, code = cat_mapping[racine]
                pct = (row["total"] / total_all * 100) if total_all > 0 else 0
                categories.append(PLCategory(
                    name=name,
                    code=code,
                    total=row["total"],
                    count=int(row["count"]),
                    pct_total=pct,
                ))

        # Trier par montant décroissant
        categories.sort(key=lambda x: x.total, reverse=True)
        return categories

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

    # =========================================================================
    # Advanced Statistics Methods (STORY-024, 025, 026)
    # =========================================================================

    def _run_advanced_stats(self) -> Tuple[Optional[List], Optional[List]]:
        """Exécute MAD et IQR detection"""
        mad_results = None
        iqr_results = None

        try:
            if "montant" not in self.df.columns:
                # Créer colonne montant si absente
                if "debit" in self.df.columns and "credit" in self.df.columns:
                    self.df["montant"] = self.df["debit"].fillna(0) - self.df["credit"].fillna(0)
                else:
                    return None, None

            # MAD Detection
            mad = MADDetector(threshold=3.5)
            mad_result = mad.detect(self.df["montant"].abs().values)
            if mad_result:
                mad_results = [{
                    "n_outliers": mad_result.n_outliers,
                    "pct_outliers": mad_result.outlier_percentage,
                    "median": mad_result.median,
                    "mad": mad_result.mad,
                    "threshold": mad_result.threshold,
                    "outlier_indices": mad_result.outlier_indices[:50].tolist() if mad_result.outlier_indices is not None else []
                }]

            # IQR Detection
            iqr = IQRDetector(k=1.5)
            iqr_result = iqr.detect(self.df["montant"].abs().values)
            if iqr_result:
                iqr_results = [{
                    "n_outliers": iqr_result.n_outliers,
                    "pct_outliers": iqr_result.outlier_percentage,
                    "q1": iqr_result.q1,
                    "q3": iqr_result.q3,
                    "iqr": iqr_result.iqr,
                    "lower_bound": iqr_result.lower_bound,
                    "upper_bound": iqr_result.upper_bound
                }]

        except Exception as e:
            pass

        return mad_results, iqr_results

    def _run_seasonality_analysis(self) -> Optional[Dict[str, Any]]:
        """Analyse saisonnière des comptes"""
        try:
            if "date" not in self.df.columns or "compte" not in self.df.columns:
                return None

            if "montant" not in self.df.columns:
                if "debit" in self.df.columns and "credit" in self.df.columns:
                    self.df["montant"] = self.df["debit"].fillna(0) - self.df["credit"].fillna(0)
                else:
                    return None

            decomposer = SeasonalDecomposer()
            results_by_account = {}

            # Analyser les comptes avec le plus de mouvements
            top_accounts = (
                self.df.groupby("compte")["montant"]
                .agg(["sum", "count"])
                .nlargest(20, "count")
                .index.tolist()
            )

            december_concentrated = []

            for compte in top_accounts:
                compte_df = self.df[self.df["compte"] == compte].copy()
                if len(compte_df) < 12:
                    continue

                try:
                    compte_df["date"] = pd.to_datetime(compte_df["date"], errors="coerce")
                    compte_df = compte_df.dropna(subset=["date"])

                    if len(compte_df) < 3:
                        continue

                    result = decomposer.analyze(compte_df["montant"].values, compte_df["date"].values)

                    if result:
                        results_by_account[compte] = {
                            "pattern": result.pattern.value,
                            "seasonal_strength": result.seasonal_strength,
                            "peak_months": result.peak_months,
                            "interpretation": result.interpretation
                        }

                        # Identifier les comptes concentrés en décembre
                        if 12 in result.peak_months and result.seasonal_strength > 0.5:
                            december_concentrated.append({
                                "compte": compte,
                                "strength": result.seasonal_strength,
                                "pattern": result.pattern.value,
                                "interpretation": result.interpretation
                            })
                except Exception:
                    continue

            return {
                "accounts_analyzed": len(results_by_account),
                "december_concentrated": december_concentrated,
                "by_account": results_by_account
            }

        except Exception as e:
            return None

    def _run_clustering(self) -> Optional[Dict[str, Any]]:
        """Clustering comportemental des comptes"""
        try:
            if "compte" not in self.df.columns:
                return None

            if "montant" not in self.df.columns:
                if "debit" in self.df.columns and "credit" in self.df.columns:
                    self.df["montant"] = self.df["debit"].fillna(0) - self.df["credit"].fillna(0)
                else:
                    return None

            clusterer = AccountClusterer()
            summary = clusterer.cluster(self.df)

            if summary:
                return {
                    "n_accounts": summary.n_accounts,
                    "cluster_distribution": {c.value: n for c, n in summary.cluster_distribution.items()},
                    "accounts_by_cluster": {
                        c.value: accounts[:10]  # Top 10 par cluster
                        for c, accounts in summary.accounts_by_cluster.items()
                    }
                }

        except Exception as e:
            return None

        return None

    # =========================================================================
    # AI Pipeline Methods (Benford, Isolation Forest, NLP, Risk Scoring)
    # =========================================================================

    def _run_benford(self) -> Optional[Dict[str, Any]]:
        """Analyse de Benford sur les montants"""
        if not AI_AVAILABLE:
            return None

        try:
            if "montant" not in self.df.columns:
                if "debit" in self.df.columns:
                    amounts = self.df["debit"].dropna()
                else:
                    return None
            else:
                amounts = self.df["montant"].abs()

            amounts = amounts[amounts > 0]

            if len(amounts) < 100:
                return None

            analysis = analyze_benford(amounts.values)

            if analysis:
                return {
                    "conformity_score": analysis.conformity_score,
                    "chi_square": analysis.chi_square_statistic,
                    "p_value": analysis.p_value,
                    "is_conformant": analysis.is_conformant,
                    "digit_distribution": analysis.observed_distribution.tolist() if analysis.observed_distribution is not None else [],
                    "expected_distribution": analysis.expected_distribution.tolist() if analysis.expected_distribution is not None else [],
                    "suspicious_digits": analysis.suspicious_digits,
                    "interpretation": analysis.interpretation
                }

        except Exception as e:
            return None

        return None

    def _run_isolation_forest(self) -> Optional[Dict[str, Any]]:
        """Détection d'anomalies par Isolation Forest"""
        if not AI_AVAILABLE:
            return None

        try:
            analysis = detect_anomalies_iforest(self.df, contamination=0.05)

            if analysis:
                # Récupérer les top anomalies
                top_anomalies = []
                for anom in analysis.anomalies[:20]:
                    top_anomalies.append({
                        "index": int(anom.index),
                        "score": float(anom.anomaly_score),
                        "compte": str(anom.compte) if hasattr(anom, 'compte') else None,
                        "montant": float(anom.montant) if hasattr(anom, 'montant') else None,
                        "features": anom.feature_contributions if hasattr(anom, 'feature_contributions') else {}
                    })

                return {
                    "n_anomalies": analysis.n_anomalies,
                    "contamination_rate": analysis.contamination_rate,
                    "top_anomalies": top_anomalies,
                    "feature_importance": analysis.feature_importance if hasattr(analysis, 'feature_importance') else {}
                }

        except Exception as e:
            return None

        return None

    def _run_nlp_analysis(self) -> Optional[Dict[str, Any]]:
        """Analyse NLP des libellés"""
        if not AI_AVAILABLE:
            return None

        try:
            # Trouver la colonne libellé
            libelle_col = None
            for col in ["libelle", "libellé", "label", "description"]:
                if col in self.df.columns:
                    libelle_col = col
                    break

            if libelle_col is None:
                return None

            analysis = analyze_labels(self.df[libelle_col].dropna().values)

            if analysis:
                return {
                    "total_labels": analysis.total_labels,
                    "unique_labels": analysis.unique_labels,
                    "empty_ratio": analysis.empty_ratio,
                    "suspicious_patterns": analysis.suspicious_patterns[:10] if hasattr(analysis, 'suspicious_patterns') else [],
                    "duplicate_groups": analysis.duplicate_groups[:5] if hasattr(analysis, 'duplicate_groups') else [],
                    "generic_labels_count": analysis.generic_labels_count if hasattr(analysis, 'generic_labels_count') else 0,
                    "interpretation": analysis.interpretation if hasattr(analysis, 'interpretation') else ""
                }

        except Exception as e:
            return None

        return None

    def _run_risk_scoring(self, result: FullAnalysisResult) -> Optional[Dict[str, Any]]:
        """Calcul du score de risque combiné"""
        if not AI_AVAILABLE:
            return None

        try:
            # Préparer les inputs pour le risk scorer
            inputs = {
                "benford": result.benford_analysis,
                "isolation_forest": result.isolation_forest,
                "nlp": result.nlp_analysis,
                "mad": result.mad_results[0] if result.mad_results else None,
                "seasonality": result.seasonality,
            }

            analysis = calculate_risk_scores(self.df, inputs)

            if analysis:
                return {
                    "overall_risk": analysis.overall_risk.value if hasattr(analysis.overall_risk, 'value') else str(analysis.overall_risk),
                    "risk_score": analysis.risk_score,
                    "component_scores": analysis.component_scores if hasattr(analysis, 'component_scores') else {},
                    "high_risk_accounts": analysis.high_risk_accounts[:20] if hasattr(analysis, 'high_risk_accounts') else [],
                    "risk_factors": analysis.risk_factors if hasattr(analysis, 'risk_factors') else [],
                    "interpretation": analysis.interpretation if hasattr(analysis, 'interpretation') else ""
                }

        except Exception as e:
            return None

        return None

    # =========================================================================
    # Summary and Recommendations
    # =========================================================================

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
