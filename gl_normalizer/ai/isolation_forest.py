"""
Isolation Forest Anomaly Detection
==================================

Détection d'anomalies non supervisée basée sur Isolation Forest.

Principe:
- Les anomalies sont plus faciles à "isoler" que les points normaux
- Moins de splits nécessaires pour isoler un point = plus anormal
- Score d'anomalie entre -1 (très anormal) et 1 (normal)

Usage:
    detector = IsolationForestDetector(df)
    detector.fit()
    anomalies = detector.get_anomalies()
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


@dataclass
class AnomalyResult:
    """Résultat pour une écriture"""
    index: int
    anomaly_score: float  # Plus négatif = plus anormal
    is_anomaly: bool
    features_contribution: Dict[str, float]


@dataclass
class IsolationForestAnalysis:
    """Analyse complète Isolation Forest"""
    total_entries: int
    nb_anomalies: int
    anomaly_rate: float
    contamination: float
    feature_importances: Dict[str, float]
    score_distribution: Dict[str, float]


class IsolationForestDetector:
    """
    Détecteur d'anomalies basé sur Isolation Forest.

    Idéal pour:
    - Détection non supervisée (pas besoin d'exemples de fraude)
    - Grands volumes de données
    - Anomalies multidimensionnelles
    """

    # Features par défaut pour l'analyse
    DEFAULT_FEATURES = [
        "montant",
        "mois",
        "jour_semaine",
        "est_fin_mois",
        "est_weekend",
        "est_montant_rond",
        "nb_ecritures_jour",
        "ecart_moyenne_compte",
    ]

    def __init__(
        self,
        df: pd.DataFrame,
        contamination: float = 0.05,
        n_estimators: int = 100,
        random_state: int = 42,
    ):
        """
        Initialise le détecteur.

        Args:
            df: DataFrame avec les écritures comptables
            contamination: Proportion attendue d'anomalies (0.01 à 0.1)
            n_estimators: Nombre d'arbres dans la forêt
            random_state: Seed pour reproductibilité
        """
        self.df = df.copy()
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.random_state = random_state

        self.model = None
        self.scaler = StandardScaler()
        self.features = []
        self.X = None

    def _engineer_features(self) -> pd.DataFrame:
        """Crée les features pour la détection"""
        df = self.df.copy()

        # S'assurer que la date est au bon format
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df["jour_semaine"] = df["date"].dt.dayofweek
            df["jour_mois"] = df["date"].dt.day
            df["est_fin_mois"] = (df["jour_mois"] >= 25).astype(int)
            df["est_weekend"] = (df["jour_semaine"] >= 5).astype(int)
            df["est_fin_annee"] = (df["date"].dt.month == 12).astype(int)

        # Features sur les montants
        if "montant" in df.columns:
            df["montant_abs"] = df["montant"].abs()
            df["log_montant"] = np.log1p(df["montant_abs"])

            # Montants ronds
            df["est_montant_rond_100"] = (df["montant_abs"] % 100 == 0).astype(int)
            df["est_montant_rond_1000"] = (df["montant_abs"] % 1000 == 0).astype(int)
            df["est_montant_rond"] = df["est_montant_rond_100"] | df["est_montant_rond_1000"]

            # Écart par rapport à la moyenne du compte
            if "compte" in df.columns:
                compte_stats = df.groupby("compte")["montant_abs"].agg(["mean", "std"])
                df = df.merge(
                    compte_stats,
                    left_on="compte",
                    right_index=True,
                    how="left",
                    suffixes=("", "_compte"),
                )
                df["mean"] = df["mean"].fillna(df["montant_abs"].mean())
                df["std"] = df["std"].fillna(df["montant_abs"].std())
                df["ecart_moyenne_compte"] = (
                    (df["montant_abs"] - df["mean"]) / df["std"].replace(0, 1)
                ).fillna(0)

        # Features sur les journaux
        if "journal" in df.columns:
            # Encoder les journaux OD
            od_journals = ["OD", "AN", "RAN", "EXT", "EXTOURNE", "SIT", "SITUATION"]
            df["est_journal_od"] = df["journal"].str.upper().isin(od_journals).astype(int)

        # Nombre d'écritures par jour (concentration)
        if "date" in df.columns:
            jour_counts = df.groupby("date").size().rename("nb_ecritures_jour")
            df = df.merge(jour_counts, left_on="date", right_index=True, how="left")

        # Nombre d'écritures par utilisateur (si disponible)
        if "utilisateur" in df.columns:
            user_counts = df.groupby("utilisateur").size().rename("nb_ecritures_user")
            df = df.merge(user_counts, left_on="utilisateur", right_index=True, how="left")

        return df

    def _select_features(self, df: pd.DataFrame) -> List[str]:
        """Sélectionne les features disponibles"""
        available_features = []

        # Features numériques potentielles
        potential_features = [
            "montant_abs",
            "log_montant",
            "mois",
            "jour_semaine",
            "jour_mois",
            "est_fin_mois",
            "est_weekend",
            "est_fin_annee",
            "est_montant_rond",
            "est_montant_rond_100",
            "est_montant_rond_1000",
            "ecart_moyenne_compte",
            "est_journal_od",
            "nb_ecritures_jour",
            "nb_ecritures_user",
        ]

        for feat in potential_features:
            if feat in df.columns:
                # Vérifier que c'est numérique et sans trop de NaN
                if pd.api.types.is_numeric_dtype(df[feat]):
                    if df[feat].notna().sum() / len(df) > 0.5:
                        available_features.append(feat)

        return available_features

    def fit(self) -> "IsolationForestDetector":
        """
        Entraîne le modèle Isolation Forest.

        Returns:
            Self pour chaînage
        """
        # Feature engineering
        df_features = self._engineer_features()

        # Sélectionner les features
        self.features = self._select_features(df_features)

        if len(self.features) < 2:
            raise ValueError(
                f"Pas assez de features disponibles: {self.features}"
            )

        # Préparer X
        self.X = df_features[self.features].fillna(0).values

        # Normaliser
        self.X_scaled = self.scaler.fit_transform(self.X)

        # Entraîner Isolation Forest
        self.model = IsolationForest(
            contamination=self.contamination,
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            n_jobs=-1,
        )
        self.model.fit(self.X_scaled)

        # Calculer les scores
        self.scores = self.model.decision_function(self.X_scaled)
        self.predictions = self.model.predict(self.X_scaled)

        return self

    def get_anomaly_scores(self) -> pd.Series:
        """
        Retourne les scores d'anomalie pour chaque écriture.

        Returns:
            Series avec scores (plus négatif = plus anormal)
        """
        if self.model is None:
            raise ValueError("Modèle non entraîné. Appelez fit() d'abord.")

        return pd.Series(self.scores, index=self.df.index, name="anomaly_score")

    def get_anomalies(
        self,
        threshold: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        Retourne les écritures détectées comme anomalies.

        Args:
            threshold: Seuil personnalisé (None = utiliser contamination)

        Returns:
            DataFrame des anomalies avec scores
        """
        if self.model is None:
            raise ValueError("Modèle non entraîné. Appelez fit() d'abord.")

        if threshold is None:
            # Utiliser la prédiction du modèle
            mask = self.predictions == -1
        else:
            # Utiliser le seuil personnalisé
            mask = self.scores < threshold

        result = self.df[mask].copy()
        result["anomaly_score"] = self.scores[mask]
        result["anomaly_rank"] = result["anomaly_score"].rank()

        return result.sort_values("anomaly_score")

    def get_top_anomalies(self, n: int = 100) -> pd.DataFrame:
        """
        Retourne les N écritures les plus anormales.

        Args:
            n: Nombre d'anomalies à retourner

        Returns:
            DataFrame des top anomalies
        """
        if self.model is None:
            raise ValueError("Modèle non entraîné. Appelez fit() d'abord.")

        result = self.df.copy()
        result["anomaly_score"] = self.scores

        return result.nsmallest(n, "anomaly_score")

    def get_feature_importances(self) -> Dict[str, float]:
        """
        Estime l'importance de chaque feature.

        Note: Isolation Forest n'a pas d'importances natives,
        on utilise une approximation basée sur la corrélation
        avec les scores d'anomalie.

        Returns:
            Dict feature -> importance
        """
        if self.model is None:
            raise ValueError("Modèle non entraîné. Appelez fit() d'abord.")

        importances = {}
        for i, feat in enumerate(self.features):
            # Corrélation entre la feature et le score d'anomalie
            corr = np.abs(np.corrcoef(self.X[:, i], self.scores)[0, 1])
            importances[feat] = corr if not np.isnan(corr) else 0

        # Normaliser
        total = sum(importances.values())
        if total > 0:
            importances = {k: v / total for k, v in importances.items()}

        return dict(sorted(importances.items(), key=lambda x: -x[1]))

    def analyze(self) -> IsolationForestAnalysis:
        """
        Effectue une analyse complète.

        Returns:
            IsolationForestAnalysis
        """
        if self.model is None:
            self.fit()

        nb_anomalies = (self.predictions == -1).sum()

        return IsolationForestAnalysis(
            total_entries=len(self.df),
            nb_anomalies=nb_anomalies,
            anomaly_rate=nb_anomalies / len(self.df),
            contamination=self.contamination,
            feature_importances=self.get_feature_importances(),
            score_distribution={
                "min": float(self.scores.min()),
                "max": float(self.scores.max()),
                "mean": float(self.scores.mean()),
                "std": float(self.scores.std()),
                "q25": float(np.percentile(self.scores, 25)),
                "q75": float(np.percentile(self.scores, 75)),
            },
        )

    def summary(self) -> Dict:
        """Retourne un résumé de l'analyse"""
        analysis = self.analyze()
        return {
            "total_entries": analysis.total_entries,
            "nb_anomalies": analysis.nb_anomalies,
            "anomaly_rate_pct": round(analysis.anomaly_rate * 100, 2),
            "features_used": self.features,
            "top_features": list(analysis.feature_importances.keys())[:5],
            "score_range": f"{analysis.score_distribution['min']:.3f} to {analysis.score_distribution['max']:.3f}",
        }


def detect_anomalies_iforest(
    df: pd.DataFrame,
    contamination: float = 0.05,
) -> pd.DataFrame:
    """
    Fonction utilitaire pour détecter rapidement les anomalies.

    Args:
        df: DataFrame avec les écritures
        contamination: Proportion d'anomalies attendue

    Returns:
        DataFrame des anomalies
    """
    detector = IsolationForestDetector(df, contamination=contamination)
    detector.fit()
    return detector.get_anomalies()
