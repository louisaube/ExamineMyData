"""
gl_normalizer/advanced_stats.py
Méthodes statistiques avancées pour détection d'anomalies

Fournit:
- MAD (Median Absolute Deviation) - Robuste aux outliers
- IQR adaptatif par compte
- Décomposition saisonnière (STL simplifié)
- Clustering comportemental des comptes
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Any
from enum import Enum


# =============================================================================
# MAD - MEDIAN ABSOLUTE DEVIATION
# =============================================================================

@dataclass
class MADResult:
    """Résultat d'analyse MAD pour un compte"""
    compte: str
    median: float
    mad: float                    # Median Absolute Deviation
    mad_score: float              # Score normalisé (comme z-score mais robuste)
    threshold: float              # Seuil utilisé
    is_anomaly: bool
    anomaly_months: List[str] = field(default_factory=list)
    anomaly_values: List[float] = field(default_factory=list)


class MADDetector:
    """
    Détecteur d'anomalies basé sur MAD (Median Absolute Deviation).

    Avantages vs Z-score:
    - Robuste aux outliers (utilise médiane au lieu de moyenne)
    - Meilleur pour distributions non-gaussiennes
    - Moins sensible aux valeurs extrêmes

    Formule:
    MAD = median(|Xi - median(X)|)
    MAD_score = 0.6745 * (Xi - median) / MAD

    Le facteur 0.6745 normalise pour être comparable au z-score
    sur une distribution normale.
    """

    # Facteur de normalisation pour comparabilité avec z-score
    NORMALIZATION_FACTOR = 0.6745

    def __init__(
        self,
        df: pd.DataFrame,
        year: Optional[int] = None,
        threshold: float = 3.0,  # MAD score threshold
    ):
        """
        Args:
            df: DataFrame GL avec colonnes compte, periode, montant
            year: Année à analyser
            threshold: Seuil MAD score (défaut: 3.0, équivalent ~z=3)
        """
        self.df = df.copy()
        self.year = year
        self.threshold = threshold

        if year is not None and "annee" in self.df.columns:
            self.df = self.df[self.df["annee"] == year]

    def compute_mad(self, values: np.ndarray) -> Tuple[float, float]:
        """
        Calcule la médiane et le MAD d'un array.

        Args:
            values: Array de valeurs

        Returns:
            (median, mad)
        """
        median = np.median(values)
        mad = np.median(np.abs(values - median))

        # Éviter division par zéro
        if mad == 0:
            mad = np.std(values) / self.NORMALIZATION_FACTOR

        return median, mad

    def compute_mad_score(self, value: float, median: float, mad: float) -> float:
        """
        Calcule le MAD score (équivalent robuste du z-score).

        Args:
            value: Valeur à scorer
            median: Médiane de référence
            mad: MAD de référence

        Returns:
            MAD score normalisé
        """
        if mad == 0:
            return 0.0
        return self.NORMALIZATION_FACTOR * (value - median) / mad

    def detect_anomalies(self) -> List[MADResult]:
        """
        Détecte les anomalies pour tous les comptes.

        Returns:
            Liste de MADResult par compte avec anomalies
        """
        results = []

        if "compte" not in self.df.columns or "periode" not in self.df.columns:
            return results

        # Grouper par compte
        for compte in self.df["compte"].unique():
            df_compte = self.df[self.df["compte"] == compte]

            # Agréger par période
            monthly = df_compte.groupby("periode")["montant"].sum()

            if len(monthly) < 3:
                continue

            values = monthly.values
            median, mad = self.compute_mad(values)

            # Calculer scores et détecter anomalies
            anomaly_months = []
            anomaly_values = []
            max_score = 0

            for periode, value in monthly.items():
                score = abs(self.compute_mad_score(value, median, mad))
                if score > max_score:
                    max_score = score
                if score > self.threshold:
                    anomaly_months.append(str(periode))
                    anomaly_values.append(float(value))

            results.append(MADResult(
                compte=str(compte),
                median=float(median),
                mad=float(mad),
                mad_score=float(max_score),
                threshold=self.threshold,
                is_anomaly=len(anomaly_months) > 0,
                anomaly_months=anomaly_months,
                anomaly_values=anomaly_values,
            ))

        # Trier par score décroissant
        results.sort(key=lambda x: x.mad_score, reverse=True)
        return results

    def get_anomalies_only(self) -> List[MADResult]:
        """Retourne uniquement les comptes avec anomalies"""
        return [r for r in self.detect_anomalies() if r.is_anomaly]


# =============================================================================
# IQR ADAPTATIF
# =============================================================================

@dataclass
class IQRResult:
    """Résultat d'analyse IQR pour un compte"""
    compte: str
    q1: float                     # 1er quartile (25%)
    q3: float                     # 3ème quartile (75%)
    iqr: float                    # Interquartile Range
    lower_bound: float            # Limite basse (Q1 - k*IQR)
    upper_bound: float            # Limite haute (Q3 + k*IQR)
    outliers_low: List[Tuple[str, float]] = field(default_factory=list)
    outliers_high: List[Tuple[str, float]] = field(default_factory=list)


class IQRDetector:
    """
    Détecteur d'anomalies basé sur IQR (Interquartile Range).

    Méthode de Tukey:
    - Outlier modéré: Q1 - 1.5*IQR < x < Q3 + 1.5*IQR
    - Outlier extrême: Q1 - 3*IQR < x < Q3 + 3*IQR

    Avantages:
    - Non-paramétrique (pas d'hypothèse de distribution)
    - Robuste aux outliers
    - Adaptatif à chaque compte
    """

    def __init__(
        self,
        df: pd.DataFrame,
        year: Optional[int] = None,
        k_factor: float = 1.5,    # Facteur de Tukey (1.5 = modéré, 3 = extrême)
    ):
        """
        Args:
            df: DataFrame GL
            year: Année à analyser
            k_factor: Multiplicateur IQR (défaut: 1.5)
        """
        self.df = df.copy()
        self.year = year
        self.k_factor = k_factor

        if year is not None and "annee" in self.df.columns:
            self.df = self.df[self.df["annee"] == year]

    def compute_iqr_bounds(self, values: np.ndarray) -> Tuple[float, float, float, float, float]:
        """
        Calcule les quartiles et limites IQR.

        Returns:
            (q1, q3, iqr, lower_bound, upper_bound)
        """
        q1 = np.percentile(values, 25)
        q3 = np.percentile(values, 75)
        iqr = q3 - q1

        lower = q1 - self.k_factor * iqr
        upper = q3 + self.k_factor * iqr

        return q1, q3, iqr, lower, upper

    def detect_anomalies(self) -> List[IQRResult]:
        """
        Détecte les outliers IQR pour tous les comptes.

        Returns:
            Liste de IQRResult par compte
        """
        results = []

        if "compte" not in self.df.columns or "periode" not in self.df.columns:
            return results

        for compte in self.df["compte"].unique():
            df_compte = self.df[self.df["compte"] == compte]
            monthly = df_compte.groupby("periode")["montant"].sum()

            if len(monthly) < 4:  # Besoin de min 4 points pour IQR
                continue

            values = monthly.values
            q1, q3, iqr, lower, upper = self.compute_iqr_bounds(values)

            outliers_low = []
            outliers_high = []

            for periode, value in monthly.items():
                if value < lower:
                    outliers_low.append((str(periode), float(value)))
                elif value > upper:
                    outliers_high.append((str(periode), float(value)))

            results.append(IQRResult(
                compte=str(compte),
                q1=float(q1),
                q3=float(q3),
                iqr=float(iqr),
                lower_bound=float(lower),
                upper_bound=float(upper),
                outliers_low=outliers_low,
                outliers_high=outliers_high,
            ))

        return results


# =============================================================================
# DÉCOMPOSITION SAISONNIÈRE (STL SIMPLIFIÉ)
# =============================================================================

class SeasonalPattern(Enum):
    """Patterns saisonniers détectés"""
    NONE = "none"                 # Pas de saisonnalité
    MONTHLY = "monthly"           # Pattern mensuel
    QUARTERLY = "quarterly"       # Pattern trimestriel
    ANNUAL = "annual"             # Concentration annuelle (fin d'année)
    IRREGULAR = "irregular"       # Pattern irrégulier


@dataclass
class SeasonalityResult:
    """Résultat d'analyse de saisonnalité pour un compte"""
    compte: str
    pattern: SeasonalPattern
    trend: float                  # Tendance moyenne
    seasonal_strength: float      # Force de la saisonnalité (0-1)
    peak_months: List[int]        # Mois de pic
    trough_months: List[int]      # Mois creux
    seasonality_index: Dict[int, float] = field(default_factory=dict)  # Index par mois
    residuals_std: float = 0.0    # Écart-type des résidus


class SeasonalDecomposer:
    """
    Décomposition saisonnière simplifiée (STL-like).

    Décompose une série en:
    - Tendance (moyenne mobile)
    - Composante saisonnière (pattern mensuel)
    - Résidus (anomalies)

    Version simplifiée sans dépendance statsmodels.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        year: Optional[int] = None,
        min_months: int = 6,      # Minimum de mois pour analyse
    ):
        """
        Args:
            df: DataFrame GL
            year: Année à analyser
            min_months: Minimum de mois requis
        """
        self.df = df.copy()
        self.year = year
        self.min_months = min_months

        if year is not None and "annee" in self.df.columns:
            self.df = self.df[self.df["annee"] == year]

    def compute_seasonal_index(self, monthly_values: pd.Series) -> Dict[int, float]:
        """
        Calcule l'index saisonnier par mois.

        Index > 1 = mois au-dessus de la moyenne
        Index < 1 = mois en-dessous de la moyenne

        Args:
            monthly_values: Série avec index = période (YYYY-MM)

        Returns:
            Dict {mois: index_saisonnier}
        """
        # Extraire le mois de chaque période
        monthly_values = monthly_values.copy()

        # Calculer moyenne globale
        global_mean = monthly_values.mean()
        if global_mean == 0:
            return {m: 1.0 for m in range(1, 13)}

        # Moyenne par mois
        month_means = {}
        for periode, value in monthly_values.items():
            month = int(str(periode).split("-")[1])
            if month not in month_means:
                month_means[month] = []
            month_means[month].append(value)

        # Index saisonnier
        seasonal_index = {}
        for month, values in month_means.items():
            month_mean = np.mean(values)
            seasonal_index[month] = month_mean / global_mean if global_mean != 0 else 1.0

        return seasonal_index

    def detect_pattern(self, seasonal_index: Dict[int, float]) -> SeasonalPattern:
        """
        Détecte le type de pattern saisonnier.

        Args:
            seasonal_index: Index saisonnier par mois

        Returns:
            SeasonalPattern détecté
        """
        if not seasonal_index:
            return SeasonalPattern.NONE

        values = list(seasonal_index.values())
        std = np.std(values)

        # Pas de variation significative
        if std < 0.15:
            return SeasonalPattern.NONE

        # Concentration en décembre
        dec_index = seasonal_index.get(12, 1.0)
        if dec_index > 2.0:
            return SeasonalPattern.ANNUAL

        # Pattern trimestriel (pics à 3, 6, 9, 12)
        quarterly_months = [3, 6, 9, 12]
        quarterly_avg = np.mean([seasonal_index.get(m, 1.0) for m in quarterly_months])
        other_avg = np.mean([seasonal_index.get(m, 1.0) for m in range(1, 13) if m not in quarterly_months])

        if quarterly_avg > 1.3 * other_avg:
            return SeasonalPattern.QUARTERLY

        # Pattern irrégulier si forte variation
        if std > 0.4:
            return SeasonalPattern.IRREGULAR

        return SeasonalPattern.MONTHLY

    def compute_seasonal_strength(self, monthly_values: pd.Series, seasonal_index: Dict[int, float]) -> float:
        """
        Calcule la force de la saisonnalité (0-1).

        Basé sur: 1 - (Var(residus) / Var(deseasonalized))

        Args:
            monthly_values: Valeurs mensuelles
            seasonal_index: Index saisonnier

        Returns:
            Score de force saisonnière (0-1)
        """
        if len(monthly_values) < 3:
            return 0.0

        total_var = np.var(monthly_values.values)
        if total_var == 0:
            return 0.0

        # Calculer les résidus après désaisonnalisation
        residuals = []
        mean_val = monthly_values.mean()

        for periode, value in monthly_values.items():
            month = int(str(periode).split("-")[1])
            expected = mean_val * seasonal_index.get(month, 1.0)
            residuals.append(value - expected)

        residual_var = np.var(residuals)

        strength = max(0, 1 - residual_var / total_var)
        return min(strength, 1.0)

    def analyze(self) -> List[SeasonalityResult]:
        """
        Analyse la saisonnalité de tous les comptes.

        Returns:
            Liste de SeasonalityResult par compte
        """
        results = []

        if "compte" not in self.df.columns or "periode" not in self.df.columns:
            return results

        for compte in self.df["compte"].unique():
            df_compte = self.df[self.df["compte"] == compte]
            monthly = df_compte.groupby("periode")["montant"].sum()

            if len(monthly) < self.min_months:
                continue

            # Calculer index saisonnier
            seasonal_index = self.compute_seasonal_index(monthly)

            # Détecter pattern
            pattern = self.detect_pattern(seasonal_index)

            # Force saisonnière
            strength = self.compute_seasonal_strength(monthly, seasonal_index)

            # Identifier pics et creux
            sorted_months = sorted(seasonal_index.items(), key=lambda x: x[1], reverse=True)
            peak_months = [m for m, idx in sorted_months[:3] if idx > 1.0]
            trough_months = [m for m, idx in sorted_months[-3:] if idx < 1.0]

            # Tendance (moyenne)
            trend = float(monthly.mean())

            # Résidus
            residuals = []
            for periode, value in monthly.items():
                month = int(str(periode).split("-")[1])
                expected = trend * seasonal_index.get(month, 1.0)
                residuals.append(value - expected)

            results.append(SeasonalityResult(
                compte=str(compte),
                pattern=pattern,
                trend=trend,
                seasonal_strength=strength,
                peak_months=peak_months,
                trough_months=trough_months,
                seasonality_index=seasonal_index,
                residuals_std=float(np.std(residuals)) if residuals else 0.0,
            ))

        # Trier par force saisonnière
        results.sort(key=lambda x: x.seasonal_strength, reverse=True)
        return results


# =============================================================================
# CLUSTERING COMPORTEMENTAL
# =============================================================================

class AccountBehaviorCluster(Enum):
    """Clusters de comportement de comptes"""
    STABLE = "stable"             # Charges régulières, faible variation
    SEASONAL = "seasonal"         # Pattern saisonnier clair
    VOLATILE = "volatile"         # Forte variation, imprévisible
    CONCENTRATED = "concentrated" # Concentré sur peu de mois
    DORMANT = "dormant"           # Peu d'activité


@dataclass
class ClusterResult:
    """Résultat de clustering pour un compte"""
    compte: str
    cluster: AccountBehaviorCluster
    features: Dict[str, float]    # Features utilisées
    distance_to_centroid: float   # Distance au centre du cluster
    confidence: float             # Confiance dans l'assignation


@dataclass
class ClusteringSummary:
    """Résumé du clustering"""
    total_accounts: int
    clusters: Dict[str, int]      # Nombre de comptes par cluster
    results: List[ClusterResult]


class AccountClusterer:
    """
    Clustering comportemental des comptes.

    Regroupe les comptes selon leurs caractéristiques:
    - Coefficient de variation (volatilité)
    - Force saisonnière
    - Concentration mensuelle
    - Nombre de mois actifs

    Utilise une méthode de clustering simple basée sur des règles
    (pas besoin de sklearn pour cette version).
    """

    def __init__(
        self,
        df: pd.DataFrame,
        year: Optional[int] = None,
    ):
        """
        Args:
            df: DataFrame GL
            year: Année à analyser
        """
        self.df = df.copy()
        self.year = year

        if year is not None and "annee" in self.df.columns:
            self.df = self.df[self.df["annee"] == year]

    def compute_features(self, compte: str) -> Optional[Dict[str, float]]:
        """
        Calcule les features comportementales d'un compte.

        Returns:
            Dict de features ou None si données insuffisantes
        """
        df_compte = self.df[self.df["compte"] == compte]

        if len(df_compte) == 0:
            return None

        monthly = df_compte.groupby("periode")["montant"].sum()

        if len(monthly) < 2:
            return None

        values = monthly.abs().values
        mean_val = np.mean(values)
        std_val = np.std(values)

        # Coefficient de variation
        cv = (std_val / mean_val * 100) if mean_val > 0 else 0

        # Concentration max (% du max mois / total)
        max_month = np.max(values)
        total = np.sum(values)
        concentration = (max_month / total * 100) if total > 0 else 0

        # Nombre de mois actifs
        active_months = len(monthly[monthly.abs() > 0])

        # Skewness (asymétrie) - simplifié
        if std_val > 0:
            skewness = np.mean(((values - mean_val) / std_val) ** 3)
        else:
            skewness = 0

        return {
            "cv": cv,                       # Coefficient de variation
            "concentration": concentration, # Concentration max
            "active_months": active_months, # Mois actifs
            "skewness": abs(skewness),      # Asymétrie
            "mean": mean_val,
            "std": std_val,
        }

    def assign_cluster(self, features: Dict[str, float]) -> Tuple[AccountBehaviorCluster, float]:
        """
        Assigne un cluster basé sur les features.

        Utilise des règles simples basées sur les seuils.

        Returns:
            (cluster, confidence)
        """
        cv = features["cv"]
        concentration = features["concentration"]
        active_months = features["active_months"]

        # Règles de classification
        if active_months <= 2:
            return AccountBehaviorCluster.DORMANT, 0.9

        if concentration > 80:
            return AccountBehaviorCluster.CONCENTRATED, 0.85

        if cv < 20:
            return AccountBehaviorCluster.STABLE, 0.8

        if cv > 80:
            return AccountBehaviorCluster.VOLATILE, 0.75

        # Pattern saisonnier si concentration modérée et variation moyenne
        if 30 < concentration < 60 and 20 < cv < 50:
            return AccountBehaviorCluster.SEASONAL, 0.7

        # Défaut: volatile si forte variation
        if cv > 40:
            return AccountBehaviorCluster.VOLATILE, 0.6

        return AccountBehaviorCluster.STABLE, 0.5

    def cluster_accounts(self) -> ClusteringSummary:
        """
        Clusterise tous les comptes.

        Returns:
            ClusteringSummary avec résultats
        """
        results = []
        cluster_counts = {c.value: 0 for c in AccountBehaviorCluster}

        if "compte" not in self.df.columns:
            return ClusteringSummary(
                total_accounts=0,
                clusters=cluster_counts,
                results=[],
            )

        for compte in self.df["compte"].unique():
            features = self.compute_features(compte)

            if features is None:
                continue

            cluster, confidence = self.assign_cluster(features)
            cluster_counts[cluster.value] += 1

            results.append(ClusterResult(
                compte=str(compte),
                cluster=cluster,
                features=features,
                distance_to_centroid=0.0,  # Simplifié
                confidence=confidence,
            ))

        return ClusteringSummary(
            total_accounts=len(results),
            clusters=cluster_counts,
            results=results,
        )

    def get_cluster(self, cluster: AccountBehaviorCluster) -> List[ClusterResult]:
        """Retourne tous les comptes d'un cluster"""
        summary = self.cluster_accounts()
        return [r for r in summary.results if r.cluster == cluster]


# =============================================================================
# FONCTIONS UTILITAIRES
# =============================================================================

def detect_anomalies_robust(
    df: pd.DataFrame,
    year: Optional[int] = None,
    method: str = "mad",          # "mad", "iqr", or "both"
    threshold: float = 3.0,
) -> Dict[str, Any]:
    """
    Détection d'anomalies robuste combinant MAD et IQR.

    Args:
        df: DataFrame GL
        year: Année à analyser
        method: Méthode à utiliser
        threshold: Seuil de détection

    Returns:
        Dict avec résultats par méthode
    """
    results = {}

    if method in ["mad", "both"]:
        mad_detector = MADDetector(df, year, threshold)
        results["mad"] = mad_detector.get_anomalies_only()

    if method in ["iqr", "both"]:
        iqr_detector = IQRDetector(df, year, k_factor=1.5)
        results["iqr"] = [r for r in iqr_detector.detect_anomalies()
                         if r.outliers_low or r.outliers_high]

    return results


def analyze_seasonality(
    df: pd.DataFrame,
    year: Optional[int] = None,
) -> List[SeasonalityResult]:
    """
    Analyse la saisonnalité de tous les comptes.

    Args:
        df: DataFrame GL
        year: Année à analyser

    Returns:
        Liste de résultats de saisonnalité
    """
    decomposer = SeasonalDecomposer(df, year)
    return decomposer.analyze()


def cluster_accounts(
    df: pd.DataFrame,
    year: Optional[int] = None,
) -> ClusteringSummary:
    """
    Clusterise les comptes par comportement.

    Args:
        df: DataFrame GL
        year: Année à analyser

    Returns:
        Résumé du clustering
    """
    clusterer = AccountClusterer(df, year)
    return clusterer.cluster_accounts()


if __name__ == "__main__":
    print("Advanced Stats - Méthodes statistiques avancées")
    print("=" * 60)
    print("\nMéthodes disponibles:")
    print("  - MADDetector: Détection robuste via Median Absolute Deviation")
    print("  - IQRDetector: Détection via Interquartile Range")
    print("  - SeasonalDecomposer: Analyse de saisonnalité")
    print("  - AccountClusterer: Clustering comportemental")
    print("\nUsage:")
    print("  from gl_normalizer.advanced_stats import detect_anomalies_robust")
    print("  results = detect_anomalies_robust(df, year=2024, method='both')")
