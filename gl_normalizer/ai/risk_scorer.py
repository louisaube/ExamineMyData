"""
Combined Risk Scorer
====================

Système de scoring de risque multi-modèles combinant:
- Loi de Benford (statistique)
- Isolation Forest (ML non supervisé)
- Autoencoder (Deep Learning)
- NLP (analyse des libellés)
- XGBoost (ML supervisé/semi-supervisé)

Architecture inspirée de MindBridge AI:
- Chaque modèle produit un score individuel
- Les scores sont combinés avec pondération
- Score final de 0 (normal) à 100 (très suspect)

Usage:
    scorer = RiskScorer(df)
    scorer.fit()
    results = scorer.get_risk_scores()
    high_risk = scorer.get_high_risk_entries()
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from enum import Enum

# Import des modules internes
from .benford import BenfordAnalyzer
from .isolation_forest import IsolationForestDetector

# Modules optionnels (nécessitent des dépendances supplémentaires)
try:
    from .autoencoder import AutoencoderDetector
    AUTOENCODER_AVAILABLE = True
except ImportError:
    AUTOENCODER_AVAILABLE = False

try:
    from .nlp_analyzer import NLPAnalyzer
    NLP_AVAILABLE = True
except ImportError:
    NLP_AVAILABLE = False

try:
    from .xgboost_scorer import XGBoostScorer
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False


class RiskLevel(Enum):
    """Niveaux de risque"""
    CRITICAL = "critical"    # 80-100
    HIGH = "high"           # 60-80
    MEDIUM = "medium"       # 40-60
    LOW = "low"             # 20-40
    MINIMAL = "minimal"     # 0-20


@dataclass
class RiskScoreResult:
    """Résultat de scoring pour une écriture"""
    index: int
    final_score: float
    risk_level: RiskLevel
    benford_score: float
    isolation_score: float
    autoencoder_score: float
    nlp_score: float
    xgboost_score: float
    contributing_factors: List[str]


@dataclass
class RiskAnalysis:
    """Analyse de risque complète"""
    total_entries: int
    risk_distribution: Dict[str, int]
    mean_score: float
    median_score: float
    std_score: float
    top_risk_factors: List[Tuple[str, float]]
    models_used: List[str]
    model_correlations: Dict[str, float]


class RiskScorer:
    """
    Système de scoring de risque multi-modèles.

    Combine plusieurs approches pour une détection robuste:
    1. Benford - Détecte les données fabriquées
    2. Isolation Forest - Anomalies non supervisées
    3. Autoencoder - Patterns complexes non-linéaires
    4. NLP - Libellés suspects
    5. XGBoost - Classification supervisée/semi-supervisée

    Pondération par défaut (ajustable):
    - Benford: 15%
    - Isolation Forest: 20%
    - Autoencoder: 20%
    - NLP: 20%
    - XGBoost: 25%
    """

    DEFAULT_WEIGHTS = {
        "benford": 0.15,
        "isolation_forest": 0.20,
        "autoencoder": 0.20,
        "nlp": 0.20,
        "xgboost": 0.25,
    }

    RISK_THRESHOLDS = {
        RiskLevel.CRITICAL: 80,
        RiskLevel.HIGH: 60,
        RiskLevel.MEDIUM: 40,
        RiskLevel.LOW: 20,
        RiskLevel.MINIMAL: 0,
    }

    def __init__(
        self,
        df: pd.DataFrame,
        weights: Optional[Dict[str, float]] = None,
        use_autoencoder: bool = True,
        use_nlp: bool = True,
        use_xgboost: bool = True,
        verbose: bool = True,
    ):
        """
        Initialise le scorer multi-modèles.

        Args:
            df: DataFrame avec les écritures
            weights: Pondération personnalisée des modèles
            use_autoencoder: Utiliser l'autoencoder (nécessite PyTorch)
            use_nlp: Utiliser l'analyse NLP
            use_xgboost: Utiliser XGBoost
            verbose: Afficher la progression
        """
        self.df = df.copy()
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.verbose = verbose

        # Désactiver les modèles non disponibles
        self.use_autoencoder = use_autoencoder and AUTOENCODER_AVAILABLE
        self.use_nlp = use_nlp and NLP_AVAILABLE
        self.use_xgboost = use_xgboost and XGBOOST_AVAILABLE

        # Ajuster les poids si certains modèles sont désactivés
        self._adjust_weights()

        # Modèles
        self.benford_analyzer = None
        self.iforest_detector = None
        self.autoencoder_detector = None
        self.nlp_analyzer = None
        self.xgboost_scorer = None

        # Résultats
        self.scores = None
        self.models_used = []

    def _adjust_weights(self):
        """Ajuste les poids si certains modèles sont désactivés"""
        active_weights = {}
        total = 0

        # Benford et Isolation Forest sont toujours disponibles
        active_weights["benford"] = self.weights["benford"]
        active_weights["isolation_forest"] = self.weights["isolation_forest"]
        total += active_weights["benford"] + active_weights["isolation_forest"]

        if self.use_autoencoder:
            active_weights["autoencoder"] = self.weights["autoencoder"]
            total += active_weights["autoencoder"]

        if self.use_nlp:
            active_weights["nlp"] = self.weights["nlp"]
            total += active_weights["nlp"]

        if self.use_xgboost:
            active_weights["xgboost"] = self.weights["xgboost"]
            total += active_weights["xgboost"]

        # Normaliser pour que la somme = 1
        self.weights = {k: v / total for k, v in active_weights.items()}

    def _normalize_score(self, scores: np.ndarray, higher_is_riskier: bool = True) -> np.ndarray:
        """Normalise les scores entre 0 et 100"""
        if len(scores) == 0:
            return scores

        min_val = np.min(scores)
        max_val = np.max(scores)

        if max_val == min_val:
            return np.full_like(scores, 50.0)

        normalized = (scores - min_val) / (max_val - min_val) * 100

        if not higher_is_riskier:
            normalized = 100 - normalized

        return normalized

    def fit(
        self,
        autoencoder_epochs: int = 30,
        iforest_contamination: float = 0.05,
    ) -> "RiskScorer":
        """
        Entraîne tous les modèles et calcule les scores.

        Args:
            autoencoder_epochs: Époques pour l'autoencoder
            iforest_contamination: Taux de contamination Isolation Forest

        Returns:
            Self pour chaînage
        """
        n_models = 2 + int(self.use_autoencoder) + int(self.use_nlp) + int(self.use_xgboost)
        current = 0

        # Initialiser le DataFrame des scores
        self.scores = pd.DataFrame(index=self.df.index)

        # 1. BENFORD
        current += 1
        if self.verbose:
            print(f"[{current}/{n_models}] Analyse Benford...")

        try:
            self.benford_analyzer = BenfordAnalyzer(self.df, min_entries=50)

            # Calculer un score par écriture basé sur le premier chiffre
            amounts = self.df["montant"].abs()
            first_digits = amounts.apply(
                lambda x: int(str(int(x))[0]) if x > 0 else 0
            )

            # Distribution attendue Benford
            expected = {1: 0.301, 2: 0.176, 3: 0.125, 4: 0.097, 5: 0.079,
                       6: 0.067, 7: 0.058, 8: 0.051, 9: 0.046}

            # Score = inverse de la probabilité attendue (chiffres rares = plus suspect)
            benford_raw = first_digits.map(lambda d: 1 - expected.get(d, 0.05) if d > 0 else 0.5)
            self.scores["benford_score"] = self._normalize_score(benford_raw.values)
            self.models_used.append("benford")

            if self.verbose:
                analysis = self.benford_analyzer.analyze()
                print(f"   Conformité: {analysis.conformity_first}")

        except Exception as e:
            if self.verbose:
                print(f"   Erreur Benford: {e}")
            self.scores["benford_score"] = 50

        # 2. ISOLATION FOREST
        current += 1
        if self.verbose:
            print(f"[{current}/{n_models}] Isolation Forest...")

        try:
            self.iforest_detector = IsolationForestDetector(
                self.df,
                contamination=iforest_contamination,
            )
            self.iforest_detector.fit()

            # Scores: plus négatif = plus anormal
            iforest_raw = self.iforest_detector.get_anomaly_scores().values
            # Inverser car plus négatif = plus suspect
            self.scores["isolation_score"] = self._normalize_score(-iforest_raw)
            self.models_used.append("isolation_forest")

            if self.verbose:
                nb_anomalies = (self.iforest_detector.predictions == -1).sum()
                print(f"   Anomalies détectées: {nb_anomalies}")

        except Exception as e:
            if self.verbose:
                print(f"   Erreur Isolation Forest: {e}")
            self.scores["isolation_score"] = 50

        # 3. AUTOENCODER
        if self.use_autoencoder:
            current += 1
            if self.verbose:
                print(f"[{current}/{n_models}] Autoencoder...")

            try:
                self.autoencoder_detector = AutoencoderDetector(self.df)
                self.autoencoder_detector.fit(epochs=autoencoder_epochs, verbose=False)

                ae_raw = self.autoencoder_detector.get_reconstruction_errors().values
                self.scores["autoencoder_score"] = self._normalize_score(ae_raw)
                self.models_used.append("autoencoder")

                if self.verbose:
                    analysis = self.autoencoder_detector.analyze()
                    print(f"   Anomalies (>p95): {analysis.nb_anomalies}")

            except Exception as e:
                if self.verbose:
                    print(f"   Erreur Autoencoder: {e}")
                self.scores["autoencoder_score"] = 50
        else:
            self.scores["autoencoder_score"] = 50

        # 4. NLP
        if self.use_nlp:
            current += 1
            if self.verbose:
                print(f"[{current}/{n_models}] Analyse NLP...")

            try:
                if "libelle" in self.df.columns:
                    self.nlp_analyzer = NLPAnalyzer(self.df, use_embeddings=False)
                    self.nlp_analyzer.fit(verbose=False)

                    self.scores["nlp_score"] = self.nlp_analyzer.df["nlp_risk_score"].values
                    self.models_used.append("nlp")

                    if self.verbose:
                        analysis = self.nlp_analyzer.analyze()
                        print(f"   Libellés suspects: {analysis.nb_suspicious}")
                else:
                    self.scores["nlp_score"] = 50
                    if self.verbose:
                        print("   Colonne 'libelle' non trouvée")

            except Exception as e:
                if self.verbose:
                    print(f"   Erreur NLP: {e}")
                self.scores["nlp_score"] = 50
        else:
            self.scores["nlp_score"] = 50

        # 5. XGBOOST
        if self.use_xgboost:
            current += 1
            if self.verbose:
                print(f"[{current}/{n_models}] XGBoost...")

            try:
                self.xgboost_scorer = XGBoostScorer(self.df)
                self.xgboost_scorer.fit_auto(verbose=False)

                xgb_proba = self.xgboost_scorer.df["risk_proba"].values
                self.scores["xgboost_score"] = self._normalize_score(xgb_proba)
                self.models_used.append("xgboost")

                if self.verbose:
                    analysis = self.xgboost_scorer.analyze()
                    print(f"   Haut risque: {analysis.nb_high_risk}")

            except Exception as e:
                if self.verbose:
                    print(f"   Erreur XGBoost: {e}")
                self.scores["xgboost_score"] = 50
        else:
            self.scores["xgboost_score"] = 50

        # CALCUL DU SCORE FINAL
        if self.verbose:
            print("\nCalcul du score final combiné...")

        self.scores["final_score"] = (
            self.scores["benford_score"] * self.weights.get("benford", 0) +
            self.scores["isolation_score"] * self.weights.get("isolation_forest", 0) +
            self.scores["autoencoder_score"] * self.weights.get("autoencoder", 0) +
            self.scores["nlp_score"] * self.weights.get("nlp", 0) +
            self.scores["xgboost_score"] * self.weights.get("xgboost", 0)
        )

        # Niveau de risque
        self.scores["risk_level"] = self.scores["final_score"].apply(self._get_risk_level)

        # Facteurs contributifs
        self.scores["top_factor"] = self.scores.apply(self._get_top_factor, axis=1)

        if self.verbose:
            dist = self.scores["risk_level"].value_counts()
            print(f"\nDistribution des risques:")
            for level in RiskLevel:
                count = dist.get(level.value, 0)
                print(f"   {level.value}: {count} ({count/len(self.df)*100:.1f}%)")

        return self

    def _get_risk_level(self, score: float) -> str:
        """Détermine le niveau de risque"""
        if score >= self.RISK_THRESHOLDS[RiskLevel.CRITICAL]:
            return RiskLevel.CRITICAL.value
        elif score >= self.RISK_THRESHOLDS[RiskLevel.HIGH]:
            return RiskLevel.HIGH.value
        elif score >= self.RISK_THRESHOLDS[RiskLevel.MEDIUM]:
            return RiskLevel.MEDIUM.value
        elif score >= self.RISK_THRESHOLDS[RiskLevel.LOW]:
            return RiskLevel.LOW.value
        else:
            return RiskLevel.MINIMAL.value

    def _get_top_factor(self, row: pd.Series) -> str:
        """Identifie le facteur principal de risque"""
        factors = {
            "benford": row["benford_score"],
            "isolation": row["isolation_score"],
            "autoencoder": row["autoencoder_score"],
            "nlp": row["nlp_score"],
            "xgboost": row["xgboost_score"],
        }
        return max(factors, key=factors.get)

    def get_risk_scores(self) -> pd.DataFrame:
        """
        Retourne tous les scores de risque.

        Returns:
            DataFrame avec tous les scores
        """
        if self.scores is None:
            self.fit()

        result = self.df.copy()
        for col in self.scores.columns:
            result[col] = self.scores[col]

        return result

    def get_high_risk_entries(
        self,
        min_level: str = "high",
    ) -> pd.DataFrame:
        """
        Retourne les écritures à risque élevé.

        Args:
            min_level: Niveau minimum ("critical", "high", "medium")

        Returns:
            DataFrame des écritures à risque
        """
        if self.scores is None:
            self.fit()

        levels = [RiskLevel.CRITICAL.value]
        if min_level in ["high", "medium"]:
            levels.append(RiskLevel.HIGH.value)
        if min_level == "medium":
            levels.append(RiskLevel.MEDIUM.value)

        result = self.get_risk_scores()
        mask = result["risk_level"].isin(levels)

        return result[mask].sort_values("final_score", ascending=False)

    def get_top_anomalies(self, n: int = 100) -> pd.DataFrame:
        """Retourne les N écritures les plus suspectes"""
        if self.scores is None:
            self.fit()

        result = self.get_risk_scores()
        return result.nlargest(n, "final_score")

    def explain_entry(self, index: int) -> Dict:
        """
        Explique pourquoi une écriture est considérée à risque.

        Args:
            index: Index de l'écriture

        Returns:
            Dict avec l'explication détaillée
        """
        if self.scores is None:
            self.fit()

        if index not in self.scores.index:
            raise ValueError(f"Index {index} non trouvé")

        row = self.scores.loc[index]
        entry = self.df.loc[index]

        factors = []
        if row["benford_score"] > 60:
            factors.append(f"Benford: Premier chiffre inhabituel (score={row['benford_score']:.0f})")
        if row["isolation_score"] > 60:
            factors.append(f"Isolation Forest: Écriture isolée (score={row['isolation_score']:.0f})")
        if row["autoencoder_score"] > 60:
            factors.append(f"Autoencoder: Pattern inhabituel (score={row['autoencoder_score']:.0f})")
        if row["nlp_score"] > 60:
            factors.append(f"NLP: Libellé suspect (score={row['nlp_score']:.0f})")
        if row["xgboost_score"] > 60:
            factors.append(f"XGBoost: Caractéristiques à risque (score={row['xgboost_score']:.0f})")

        return {
            "index": index,
            "entry": entry.to_dict(),
            "final_score": row["final_score"],
            "risk_level": row["risk_level"],
            "scores": {
                "benford": row["benford_score"],
                "isolation_forest": row["isolation_score"],
                "autoencoder": row["autoencoder_score"],
                "nlp": row["nlp_score"],
                "xgboost": row["xgboost_score"],
            },
            "contributing_factors": factors,
            "top_factor": row["top_factor"],
        }

    def analyze(self) -> RiskAnalysis:
        """Analyse complète"""
        if self.scores is None:
            self.fit()

        dist = self.scores["risk_level"].value_counts().to_dict()
        factor_dist = self.scores["top_factor"].value_counts()

        # Corrélations entre modèles
        correlations = {}
        score_cols = ["benford_score", "isolation_score", "autoencoder_score",
                     "nlp_score", "xgboost_score"]
        for col in score_cols:
            if col in self.scores.columns:
                corr = self.scores["final_score"].corr(self.scores[col])
                correlations[col.replace("_score", "")] = round(corr, 3)

        return RiskAnalysis(
            total_entries=len(self.df),
            risk_distribution=dist,
            mean_score=self.scores["final_score"].mean(),
            median_score=self.scores["final_score"].median(),
            std_score=self.scores["final_score"].std(),
            top_risk_factors=list(factor_dist.items()),
            models_used=self.models_used,
            model_correlations=correlations,
        )

    def summary(self) -> Dict:
        """Résumé de l'analyse"""
        analysis = self.analyze()

        return {
            "total_entries": analysis.total_entries,
            "models_used": analysis.models_used,
            "risk_distribution": analysis.risk_distribution,
            "mean_score": round(analysis.mean_score, 1),
            "median_score": round(analysis.median_score, 1),
            "critical_count": analysis.risk_distribution.get("critical", 0),
            "high_count": analysis.risk_distribution.get("high", 0),
            "top_factor": analysis.top_risk_factors[0] if analysis.top_risk_factors else None,
            "model_correlations": analysis.model_correlations,
        }

    def export_report(self, filepath: str, top_n: int = 500):
        """
        Exporte un rapport Excel avec les résultats.

        Args:
            filepath: Chemin du fichier Excel
            top_n: Nombre d'écritures à exporter
        """
        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            # Résumé
            summary_df = pd.DataFrame([self.summary()])
            summary_df.to_excel(writer, sheet_name="Résumé", index=False)

            # Top anomalies
            top = self.get_top_anomalies(top_n)
            top.to_excel(writer, sheet_name="Top Anomalies", index=False)

            # Par niveau de risque
            for level in RiskLevel:
                mask = self.scores["risk_level"] == level.value
                if mask.sum() > 0:
                    df_level = self.get_risk_scores()[mask].head(100)
                    df_level.to_excel(writer, sheet_name=f"Risque {level.value}", index=False)

            # Distribution des scores
            score_dist = self.scores["final_score"].describe()
            score_dist.to_excel(writer, sheet_name="Distribution")


def calculate_risk_scores(
    df: pd.DataFrame,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Fonction utilitaire pour calculer rapidement les scores de risque.

    Args:
        df: DataFrame avec les écritures
        verbose: Afficher la progression

    Returns:
        DataFrame avec les scores
    """
    scorer = RiskScorer(df, verbose=verbose)
    scorer.fit()
    return scorer.get_risk_scores()
