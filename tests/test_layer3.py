"""
Tests for Layer 3: Business Filters

Tests:
- Materiality filtering
- Exclusion rules (non_signal_si)
- Inclusion rules (signal_si)
- Pertinence calculation
- Full pipeline
"""

import pytest
from typing import List

from gl_normalizer.layer2.base import RawSignal, Univers
from gl_normalizer.layer3 import (
    # Base
    FilterReason,
    PertinenceLevel,
    QualifiedAnomaly,
    FilteredSignal,
    Layer3Result,
    # Materiality
    check_materiality,
    compute_materiality_amount,
    get_materiality_threshold,
    compute_materiality_score,
    DEFAULT_MATERIALITY_THRESHOLD,
    UNIVERS_MATERIALITY,
    # Business Rules
    SignalContext,
    check_exclusions,
    check_inclusions,
    STANDARD_EXCLUSION_RULES,
    # Pertinence
    compute_pertinence,
    compute_statistical_score,
    passes_pertinence_threshold,
    DEFAULT_PERTINENCE_THRESHOLD,
    # Runner
    Layer3Runner,
    run_layer3,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_referentiel():
    """Référentiel de test."""
    return {
        "613": {
            "univers": "CRISTALLIN",
            "cv_montant": 0.05,
            "seuil_materialite": 2000,
            "non_signal_si": ["montant_rond", "meme_montant_12_mois"],
            "signal_si": ["variation > 10%"],
        },
        "401": {
            "univers": "NOMINATIF_TIERS",
            "cv_montant": 0.50,
            "seuil_materialite": 10000,
            "non_signal_si": [],
            "signal_si": [],
        },
        "672": {
            "univers": "PONCTUEL",
            "cv_montant": 1.0,
            "non_signal_si": ["solde_zero"],
            "signal_si": ["first_occurrence"],
        },
    }


@pytest.fixture
def sample_signal():
    """Signal de test standard."""
    return RawSignal(
        id="L2-VAR_613_202401",
        famille="613",
        univers=Univers.CRISTALLIN,
        test_id="L2-VAR",
        test_name="Variation mensuelle",
        metric_value=3200.0,
        threshold=3000.0,
        delta=200.0,
        periode="2024-01",
        pvalue=0.02,
        pvalue_adjusted=0.03,
        detection_method="conformal",
        metadata={"calibration_size": 12}
    )


@pytest.fixture
def sample_signals():
    """Liste de signaux de test."""
    return [
        # Signal 1: Haute matérialité, p-value faible → devrait passer
        RawSignal(
            id="L2-VAR_613_202401",
            famille="613",
            univers=Univers.CRISTALLIN,
            test_id="L2-VAR",
            test_name="Variation mensuelle",
            metric_value=8000.0,
            threshold=5000.0,
            delta=3000.0,
            periode="2024-01",
            pvalue=0.005,
            pvalue_adjusted=0.01,
            detection_method="conformal",
        ),
        # Signal 2: Basse matérialité → devrait être filtré
        RawSignal(
            id="L2-VAR_613_202402",
            famille="613",
            univers=Univers.CRISTALLIN,
            test_id="L2-VAR",
            test_name="Variation mensuelle",
            metric_value=500.0,
            threshold=1000.0,
            delta=100.0,
            periode="2024-02",
            pvalue=0.01,
            pvalue_adjusted=0.02,
            detection_method="conformal",
        ),
        # Signal 3: Montant élevé mais p-value limite
        RawSignal(
            id="L2-VAR_401_202401",
            famille="401",
            univers=Univers.NOMINATIF_TIERS,
            test_id="L2-VAR",
            test_name="Variation mensuelle",
            metric_value=15000.0,
            threshold=10000.0,
            delta=5000.0,
            periode="2024-01",
            pvalue=0.04,
            pvalue_adjusted=0.045,
            detection_method="conformal",
        ),
    ]


# =============================================================================
# TEST MATERIALITY
# =============================================================================

class TestMateriality:
    """Tests du filtre de matérialité."""

    def test_get_threshold_from_referentiel(self, sample_referentiel):
        """Vérifie récupération du seuil depuis le référentiel."""
        signal = RawSignal(
            id="test", famille="613", univers=Univers.CRISTALLIN,
            test_id="L2-VAR", test_name="Test",
            metric_value=1000, threshold=500, delta=500,
        )
        threshold = get_materiality_threshold(signal, sample_referentiel)
        assert threshold == 2000  # Défini dans le référentiel

    def test_get_threshold_by_univers(self, sample_referentiel):
        """Vérifie seuil par défaut de l'univers."""
        signal = RawSignal(
            id="test", famille="999", univers=Univers.TRESORERIE,
            test_id="L2-VAR", test_name="Test",
            metric_value=1000, threshold=500, delta=500,
        )
        threshold = get_materiality_threshold(signal, sample_referentiel)
        assert threshold == UNIVERS_MATERIALITY["TRESORERIE"]  # 20000

    def test_check_materiality_passes(self, sample_referentiel):
        """Signal au-dessus du seuil passe."""
        signal = RawSignal(
            id="test", famille="613", univers=Univers.CRISTALLIN,
            test_id="L2-VAR", test_name="Test",
            metric_value=5000, threshold=3000, delta=2000,
        )
        passes, amount, threshold, reason = check_materiality(signal, sample_referentiel)
        assert passes is True
        assert amount >= threshold

    def test_check_materiality_fails(self, sample_referentiel):
        """Signal sous le seuil ne passe pas."""
        signal = RawSignal(
            id="test", famille="613", univers=Univers.CRISTALLIN,
            test_id="L2-VAR", test_name="Test",
            metric_value=500, threshold=1000, delta=100,
        )
        passes, amount, threshold, reason = check_materiality(signal, sample_referentiel)
        assert passes is False

    def test_materiality_score(self):
        """Score de matérialité selon le ratio."""
        # Au seuil (ratio = 1): score > 50 (formule log)
        score_at = compute_materiality_score(5000, 5000)
        assert 50 <= score_at <= 75  # Log formula gives ~64

        # 2× le seuil: score plus élevé
        score_2x = compute_materiality_score(10000, 5000)
        assert score_2x > score_at

        # 5× le seuil: score encore plus élevé
        score_5x = compute_materiality_score(25000, 5000)
        assert score_5x > score_2x


# =============================================================================
# TEST EXCLUSION RULES
# =============================================================================

class TestExclusionRules:
    """Tests des règles d'exclusion."""

    def test_round_amount_exclusion(self, sample_referentiel):
        """Montant rond exclut le signal."""
        signal = RawSignal(
            id="test", famille="613", univers=Univers.CRISTALLIN,
            test_id="L2-VAR", test_name="Test",
            metric_value=5000, threshold=3000, delta=2000,
        )
        context = SignalContext(is_round=True)

        is_excluded, checked, matched = check_exclusions(
            signal, context, sample_referentiel
        )
        assert is_excluded is True
        assert "EXC-ROUND" in matched

    def test_same_amount_12m_exclusion(self, sample_referentiel):
        """Même montant sur 12 mois exclut."""
        signal = RawSignal(
            id="test", famille="613", univers=Univers.CRISTALLIN,
            test_id="L2-VAR", test_name="Test",
            metric_value=2500, threshold=2500, delta=50,
        )
        context = SignalContext(same_amount_12m=True)

        is_excluded, checked, matched = check_exclusions(
            signal, context, sample_referentiel
        )
        assert is_excluded is True
        assert "EXC-SAME12M" in matched

    def test_no_exclusion_when_context_false(self, sample_referentiel):
        """Pas d'exclusion si conditions non remplies."""
        signal = RawSignal(
            id="test", famille="613", univers=Univers.CRISTALLIN,
            test_id="L2-VAR", test_name="Test",
            metric_value=5123.45, threshold=3000, delta=2000,
        )
        context = SignalContext(is_round=False, same_amount_12m=False)

        is_excluded, checked, matched = check_exclusions(
            signal, context, sample_referentiel
        )
        assert is_excluded is False
        assert len(matched) == 0


# =============================================================================
# TEST PERTINENCE
# =============================================================================

class TestPertinence:
    """Tests du calcul de pertinence."""

    def test_statistical_score_from_pvalue(self):
        """Score statistique basé sur p-value."""
        # p < 0.001 → score max
        signal_high = RawSignal(
            id="test", famille="613", univers=Univers.CRISTALLIN,
            test_id="L2-VAR", test_name="Test",
            metric_value=5000, threshold=3000, delta=2000,
            pvalue=0.0005,
        )
        score_high = compute_statistical_score(signal_high)
        assert score_high >= 95

        # p ~ 0.05 → score moyen
        signal_medium = RawSignal(
            id="test", famille="613", univers=Univers.CRISTALLIN,
            test_id="L2-VAR", test_name="Test",
            metric_value=5000, threshold=3000, delta=2000,
            pvalue=0.04,
        )
        score_medium = compute_statistical_score(signal_medium)
        assert 60 <= score_medium <= 75

    def test_pertinence_combines_factors(self, sample_signal, sample_referentiel):
        """Pertinence combine tous les facteurs."""
        result = compute_pertinence(
            sample_signal,
            materiality_amount=5000,
            materiality_threshold=2000,
            inclusion_boost=10.0,
        )

        assert result.final_score > 0
        assert result.statistical_score > 0
        assert result.materiality_score > 0
        assert result.level in PertinenceLevel

    def test_passes_threshold(self, sample_signal, sample_referentiel):
        """Vérification du seuil de pertinence."""
        # Signal avec bon score
        high_result = compute_pertinence(
            sample_signal,
            materiality_amount=10000,
            materiality_threshold=2000,
        )
        assert passes_pertinence_threshold(high_result, 40) is True

        # Signal avec score faible (simulé)
        low_signal = RawSignal(
            id="test", famille="613", univers=Univers.CRISTALLIN,
            test_id="L2-VAR", test_name="Test",
            metric_value=100, threshold=100, delta=10,
            pvalue=0.09,
        )
        low_result = compute_pertinence(
            low_signal,
            materiality_amount=100,
            materiality_threshold=5000,
        )
        # Pourrait ne pas passer avec seuil élevé
        if low_result.final_score < 40:
            assert passes_pertinence_threshold(low_result, 40) is False


# =============================================================================
# TEST LAYER3 RUNNER
# =============================================================================

class TestLayer3Runner:
    """Tests du runner Layer 3."""

    def test_runner_basic(self, sample_signals, sample_referentiel):
        """Test basique du runner."""
        runner = Layer3Runner(
            sample_referentiel,
            materiality_threshold=2000,
            pertinence_threshold=30,
        )
        result = runner.run(sample_signals)

        assert isinstance(result, Layer3Result)
        assert result.n_input == len(sample_signals)
        assert result.n_output <= result.n_input

    def test_runner_filters_low_materiality(self, sample_referentiel):
        """Runner filtre les signaux sous matérialité."""
        signals = [
            RawSignal(
                id="low", famille="613", univers=Univers.CRISTALLIN,
                test_id="L2-VAR", test_name="Test",
                metric_value=123.45, threshold=567.89, delta=50,  # Non-round amounts
                pvalue=0.001,  # Très significatif mais petit montant
            ),
        ]
        runner = Layer3Runner(
            sample_referentiel,
            materiality_threshold=50000,  # Seuil très élevé
            apply_exclusions=False,        # Désactiver exclusions pour ce test
        )
        result = runner.run(signals)

        assert result.n_output == 0
        assert result.n_filtered_materiality == 1

    def test_runner_qualified_anomalies_ranked(self, sample_signals, sample_referentiel):
        """Anomalies qualifiées sont rangées par score."""
        runner = Layer3Runner(
            sample_referentiel,
            materiality_threshold=100,  # Bas pour tout passer
            pertinence_threshold=0,      # Pas de filtre pertinence
            apply_exclusions=False,      # Pas d'exclusions
        )
        result = runner.run(sample_signals)

        if len(result.qualified) >= 2:
            # Vérifier ordre décroissant
            for i in range(len(result.qualified) - 1):
                assert result.qualified[i].final_score >= result.qualified[i + 1].final_score
            # Vérifier rangs
            assert result.qualified[0].rank == 1

    def test_run_layer3_convenience(self, sample_signals, sample_referentiel):
        """Test de la fonction raccourcie."""
        result = run_layer3(
            sample_signals,
            sample_referentiel,
            materiality_threshold=1000,
        )
        assert isinstance(result, Layer3Result)


# =============================================================================
# TEST LAYER3 RESULT
# =============================================================================

class TestLayer3Result:
    """Tests de Layer3Result."""

    def test_result_summary(self, sample_signals, sample_referentiel):
        """Le summary est lisible."""
        runner = Layer3Runner(sample_referentiel)
        result = runner.run(sample_signals)

        summary = result.summary()
        assert "Layer 3" in summary
        assert "Input signals" in summary
        assert "Qualified" in summary

    def test_result_to_dict(self, sample_signals, sample_referentiel):
        """Conversion en dict pour sérialisation."""
        runner = Layer3Runner(sample_referentiel)
        result = runner.run(sample_signals)

        d = result.to_dict()
        assert "qualified" in d
        assert "filtered" in d
        assert "stats" in d

    def test_reduction_rate(self, sample_signals, sample_referentiel):
        """Taux de réduction calculé."""
        runner = Layer3Runner(
            sample_referentiel,
            materiality_threshold=5000,  # Élevé pour filtrer
        )
        result = runner.run(sample_signals)

        rate = result.reduction_rate
        assert 0 <= rate <= 1
        if result.n_filtered_materiality > 0:
            assert rate > 0


# =============================================================================
# TEST INTEGRATION
# =============================================================================

class TestIntegration:
    """Tests d'intégration Layer 2 → Layer 3."""

    def test_qualified_anomaly_has_all_fields(self, sample_signals, sample_referentiel):
        """QualifiedAnomaly a tous les champs attendus."""
        runner = Layer3Runner(
            sample_referentiel,
            materiality_threshold=100,
            pertinence_threshold=0,
            apply_exclusions=False,
        )
        result = runner.run(sample_signals)

        if result.qualified:
            qa = result.qualified[0]
            assert qa.signal is not None
            assert qa.materiality_amount >= 0
            assert qa.materiality_threshold > 0
            assert qa.pertinence_score >= 0
            assert qa.final_score >= 0
            assert qa.rank >= 1

    def test_filtered_signal_has_reason(self, sample_referentiel):
        """FilteredSignal a une raison de filtrage."""
        signals = [
            RawSignal(
                id="test", famille="613", univers=Univers.CRISTALLIN,
                test_id="L2-VAR", test_name="Test",
                metric_value=10, threshold=100, delta=5,
                pvalue=0.001,
            ),
        ]
        runner = Layer3Runner(sample_referentiel, materiality_threshold=10000)
        result = runner.run(signals)

        assert len(result.filtered_materiality) == 1
        fs = result.filtered_materiality[0]
        assert fs.filter_reason == FilterReason.BELOW_MATERIALITY
        assert fs.filter_details != ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
