"""
Tests pour advanced_stats.py - Méthodes statistiques avancées
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from gl_normalizer.advanced_stats import (
    MADDetector,
    MADResult,
    IQRDetector,
    IQRResult,
    SeasonalDecomposer,
    SeasonalityResult,
    SeasonalPattern,
    AccountClusterer,
    AccountBehaviorCluster,
    ClusteringSummary,
    detect_anomalies_robust,
    analyze_seasonality,
    cluster_accounts,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_gl_data():
    """Crée un DataFrame GL de test avec patterns variés"""
    data = []

    # Compte stable (peu de variation)
    for month in range(1, 13):
        data.append({
            "compte": "601100",
            "libelle_compte": "Achats matières premières",
            "periode": f"2024-{month:02d}",
            "annee": 2024,
            "mois": month,
            "montant": 10000 + np.random.normal(0, 500),  # Variation ~5%
        })

    # Compte volatile (forte variation)
    for month in range(1, 13):
        data.append({
            "compte": "617100",
            "libelle_compte": "Études et recherches",
            "periode": f"2024-{month:02d}",
            "annee": 2024,
            "mois": month,
            "montant": np.random.uniform(1000, 50000),  # Grande variation
        })

    # Compte saisonnier (pic en décembre)
    for month in range(1, 13):
        base = 5000
        if month == 12:
            base = 50000  # Pic décembre
        elif month in [6, 9]:
            base = 8000  # Pics intermédiaires
        data.append({
            "compte": "681100",
            "libelle_compte": "Dotations aux amortissements",
            "periode": f"2024-{month:02d}",
            "annee": 2024,
            "mois": month,
            "montant": base + np.random.normal(0, 200),
        })

    # Compte concentré (activité sur 2 mois)
    for month in range(1, 13):
        montant = 0
        if month == 6:
            montant = 100000
        elif month == 12:
            montant = 150000
        data.append({
            "compte": "695000",
            "libelle_compte": "Impôts sur les bénéfices",
            "periode": f"2024-{month:02d}",
            "annee": 2024,
            "mois": month,
            "montant": montant,
        })

    # Compte dormant (peu d'activité)
    for month in range(1, 13):
        montant = 0
        if month == 3:
            montant = 500
        data.append({
            "compte": "671000",
            "libelle_compte": "Charges exceptionnelles",
            "periode": f"2024-{month:02d}",
            "annee": 2024,
            "mois": month,
            "montant": montant,
        })

    return pd.DataFrame(data)


@pytest.fixture
def anomaly_gl_data():
    """DataFrame avec anomalies claires pour tests MAD/IQR"""
    data = []

    # Compte avec anomalie évidente en mois 6
    # Utiliser des valeurs avec variation naturelle pour que MAD fonctionne
    base_values = [9500, 10200, 9800, 10100, 9900, 10300, 10000, 9700, 10400, 9600, 10100]
    for month in range(1, 13):
        if month == 6:
            montant = 50000  # Anomalie 5x
        else:
            montant = base_values[(month - 1) % len(base_values)]
        data.append({
            "compte": "622600",
            "libelle_compte": "Honoraires",
            "periode": f"2024-{month:02d}",
            "annee": 2024,
            "mois": month,
            "montant": montant,
        })

    return pd.DataFrame(data)


# =============================================================================
# TESTS MAD DETECTOR
# =============================================================================

class TestMADDetector:
    """Tests pour MADDetector"""

    def test_compute_mad_basic(self, anomaly_gl_data):
        """Test calcul MAD de base"""
        detector = MADDetector(anomaly_gl_data, year=2024)

        values = np.array([1, 2, 3, 4, 5, 100])  # Outlier clair
        median, mad = detector.compute_mad(values)

        assert median == 3.5  # Médiane de [1,2,3,4,5,100]
        assert mad > 0

    def test_detect_anomalies(self, anomaly_gl_data):
        """Test détection d'anomalies"""
        detector = MADDetector(anomaly_gl_data, year=2024, threshold=2.5)
        results = detector.detect_anomalies()

        assert len(results) >= 1

        # Le compte 622600 devrait avoir une anomalie
        compte_result = next((r for r in results if r.compte == "622600"), None)
        assert compte_result is not None
        assert compte_result.is_anomaly
        assert "2024-06" in compte_result.anomaly_months

    def test_get_anomalies_only(self, anomaly_gl_data):
        """Test filtrage des anomalies"""
        detector = MADDetector(anomaly_gl_data, year=2024, threshold=2.5)
        anomalies = detector.get_anomalies_only()

        # Tous les résultats doivent être des anomalies
        for result in anomalies:
            assert result.is_anomaly

    def test_mad_result_dataclass(self):
        """Test structure MADResult"""
        result = MADResult(
            compte="123456",
            median=1000.0,
            mad=100.0,
            mad_score=3.5,
            threshold=3.0,
            is_anomaly=True,
            anomaly_months=["2024-06"],
            anomaly_values=[5000.0],
        )

        assert result.compte == "123456"
        assert result.is_anomaly
        assert len(result.anomaly_months) == 1


# =============================================================================
# TESTS IQR DETECTOR
# =============================================================================

class TestIQRDetector:
    """Tests pour IQRDetector"""

    def test_compute_iqr_bounds(self, sample_gl_data):
        """Test calcul des bornes IQR"""
        detector = IQRDetector(sample_gl_data, year=2024)

        values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        q1, q3, iqr, lower, upper = detector.compute_iqr_bounds(values)

        assert q1 == pytest.approx(3.25, rel=0.1)
        assert q3 == pytest.approx(7.75, rel=0.1)
        assert iqr == pytest.approx(4.5, rel=0.1)

    def test_detect_outliers(self, anomaly_gl_data):
        """Test détection des outliers IQR"""
        detector = IQRDetector(anomaly_gl_data, year=2024, k_factor=1.5)
        results = detector.detect_anomalies()

        assert len(results) >= 1

        # Le compte 622600 devrait avoir un outlier haut
        compte_result = next((r for r in results if r.compte == "622600"), None)
        assert compte_result is not None
        assert len(compte_result.outliers_high) > 0

    def test_iqr_result_structure(self):
        """Test structure IQRResult"""
        result = IQRResult(
            compte="123456",
            q1=5000.0,
            q3=15000.0,
            iqr=10000.0,
            lower_bound=-10000.0,
            upper_bound=30000.0,
            outliers_low=[("2024-01", -5000.0)],
            outliers_high=[("2024-06", 50000.0)],
        )

        assert result.iqr == 10000.0
        assert len(result.outliers_high) == 1


# =============================================================================
# TESTS SEASONAL DECOMPOSER
# =============================================================================

class TestSeasonalDecomposer:
    """Tests pour SeasonalDecomposer"""

    def test_compute_seasonal_index(self, sample_gl_data):
        """Test calcul de l'index saisonnier"""
        decomposer = SeasonalDecomposer(sample_gl_data, year=2024)

        df_compte = sample_gl_data[sample_gl_data["compte"] == "681100"]
        monthly = df_compte.groupby("periode")["montant"].sum()

        index = decomposer.compute_seasonal_index(monthly)

        # Décembre devrait avoir un index élevé (pic)
        assert index[12] > 1.5

    def test_detect_annual_pattern(self, sample_gl_data):
        """Test détection pattern annuel"""
        decomposer = SeasonalDecomposer(sample_gl_data, year=2024)
        results = decomposer.analyze()

        # Chercher le compte 681100 (pic décembre)
        compte_681 = next((r for r in results if r.compte == "681100"), None)
        assert compte_681 is not None
        assert compte_681.pattern in [SeasonalPattern.ANNUAL, SeasonalPattern.IRREGULAR]

    def test_seasonality_result_structure(self):
        """Test structure SeasonalityResult"""
        result = SeasonalityResult(
            compte="123456",
            pattern=SeasonalPattern.QUARTERLY,
            trend=10000.0,
            seasonal_strength=0.75,
            peak_months=[3, 6, 9, 12],
            trough_months=[1, 2],
            seasonality_index={m: 1.0 for m in range(1, 13)},
            residuals_std=500.0,
        )

        assert result.pattern == SeasonalPattern.QUARTERLY
        assert result.seasonal_strength == 0.75


# =============================================================================
# TESTS ACCOUNT CLUSTERER
# =============================================================================

class TestAccountClusterer:
    """Tests pour AccountClusterer"""

    def test_compute_features(self, sample_gl_data):
        """Test calcul des features"""
        clusterer = AccountClusterer(sample_gl_data, year=2024)

        # Compte stable
        features_stable = clusterer.compute_features("601100")
        assert features_stable is not None
        assert features_stable["cv"] < 30  # Faible variation

        # Compte concentré
        features_conc = clusterer.compute_features("695000")
        assert features_conc is not None
        assert features_conc["concentration"] > 50  # Forte concentration

    def test_assign_cluster_stable(self, sample_gl_data):
        """Test assignation cluster stable"""
        clusterer = AccountClusterer(sample_gl_data, year=2024)
        features = {"cv": 10, "concentration": 15, "active_months": 12, "skewness": 0.1, "mean": 10000, "std": 1000}

        cluster, confidence = clusterer.assign_cluster(features)
        assert cluster == AccountBehaviorCluster.STABLE

    def test_assign_cluster_dormant(self, sample_gl_data):
        """Test assignation cluster dormant"""
        clusterer = AccountClusterer(sample_gl_data, year=2024)
        features = {"cv": 100, "concentration": 100, "active_months": 1, "skewness": 0, "mean": 500, "std": 0}

        cluster, confidence = clusterer.assign_cluster(features)
        assert cluster == AccountBehaviorCluster.DORMANT

    def test_cluster_accounts_summary(self, sample_gl_data):
        """Test résumé du clustering"""
        clusterer = AccountClusterer(sample_gl_data, year=2024)
        summary = clusterer.cluster_accounts()

        assert isinstance(summary, ClusteringSummary)
        assert summary.total_accounts >= 4  # Au moins nos 4 comptes de test
        assert len(summary.results) == summary.total_accounts

    def test_get_cluster_filter(self, sample_gl_data):
        """Test filtrage par cluster"""
        clusterer = AccountClusterer(sample_gl_data, year=2024)

        # Chercher les comptes dormants
        dormants = clusterer.get_cluster(AccountBehaviorCluster.DORMANT)

        # Le compte 671000 devrait être dormant
        assert any(r.compte == "671000" for r in dormants)


# =============================================================================
# TESTS FONCTIONS UTILITAIRES
# =============================================================================

class TestUtilityFunctions:
    """Tests pour les fonctions utilitaires"""

    def test_detect_anomalies_robust_mad(self, anomaly_gl_data):
        """Test detect_anomalies_robust avec MAD"""
        results = detect_anomalies_robust(anomaly_gl_data, year=2024, method="mad")

        assert "mad" in results
        assert len(results["mad"]) >= 1

    def test_detect_anomalies_robust_iqr(self, anomaly_gl_data):
        """Test detect_anomalies_robust avec IQR"""
        results = detect_anomalies_robust(anomaly_gl_data, year=2024, method="iqr")

        assert "iqr" in results

    def test_detect_anomalies_robust_both(self, anomaly_gl_data):
        """Test detect_anomalies_robust avec les deux méthodes"""
        results = detect_anomalies_robust(anomaly_gl_data, year=2024, method="both")

        assert "mad" in results
        assert "iqr" in results

    def test_analyze_seasonality(self, sample_gl_data):
        """Test analyze_seasonality"""
        results = analyze_seasonality(sample_gl_data, year=2024)

        assert isinstance(results, list)
        assert len(results) >= 1

    def test_cluster_accounts_function(self, sample_gl_data):
        """Test cluster_accounts function"""
        summary = cluster_accounts(sample_gl_data, year=2024)

        assert isinstance(summary, ClusteringSummary)
        assert summary.total_accounts > 0


# =============================================================================
# TESTS D'INTÉGRATION
# =============================================================================

class TestIntegration:
    """Tests d'intégration avancés"""

    def test_full_analysis_pipeline(self, sample_gl_data):
        """Test pipeline complet d'analyse"""
        # 1. Détection robuste
        anomalies = detect_anomalies_robust(sample_gl_data, year=2024, method="both")

        # 2. Analyse saisonnalité
        seasonality = analyze_seasonality(sample_gl_data, year=2024)

        # 3. Clustering
        clusters = cluster_accounts(sample_gl_data, year=2024)

        # Vérifications
        assert "mad" in anomalies
        assert "iqr" in anomalies
        assert len(seasonality) >= 1
        assert clusters.total_accounts >= 1

    def test_empty_dataframe(self):
        """Test avec DataFrame vide"""
        empty_df = pd.DataFrame(columns=["compte", "periode", "montant", "annee"])

        mad = MADDetector(empty_df, year=2024)
        assert mad.detect_anomalies() == []

        iqr = IQRDetector(empty_df, year=2024)
        assert iqr.detect_anomalies() == []

        decomposer = SeasonalDecomposer(empty_df, year=2024)
        assert decomposer.analyze() == []

    def test_single_month_data(self):
        """Test avec données d'un seul mois"""
        single_month = pd.DataFrame([{
            "compte": "601100",
            "periode": "2024-01",
            "annee": 2024,
            "montant": 10000,
        }])

        mad = MADDetector(single_month, year=2024)
        results = mad.detect_anomalies()
        assert len(results) == 0  # Pas assez de données

    def test_comparison_mad_vs_zscore(self, sample_gl_data):
        """Test que MAD fonctionne avec des données à variation naturelle"""
        # Créer données avec variation naturelle et un outlier
        data = []
        base_values = [9500, 10200, 9800, 10100, 9900, 10000, 9700, 10400, 9600, 10100, 10300]
        for month in range(1, 13):
            if month == 6:
                montant = 80000  # Outlier clair (~8x moyenne)
            else:
                montant = base_values[(month - 1) % len(base_values)]
            data.append({
                "compte": "test",
                "periode": f"2024-{month:02d}",
                "annee": 2024,
                "montant": montant,
            })
        df_outlier = pd.DataFrame(data)

        detector = MADDetector(df_outlier, year=2024, threshold=2.5)
        results = detector.detect_anomalies()

        # MAD devrait détecter le mois 6 comme anomalie
        assert len(results) == 1
        assert results[0].is_anomaly
        assert "2024-06" in results[0].anomaly_months


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
