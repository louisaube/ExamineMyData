"""
Tests for Layer 4: ICC Score

Tests:
- Impact calculation
- Global score computation
- Univers scores (radar)
- Report generation
"""

import pytest
from typing import List

from gl_normalizer.layer2.base import RawSignal, Univers
from gl_normalizer.layer3.base import QualifiedAnomaly, PertinenceLevel
from gl_normalizer.layer4 import (
    # Base
    ICCResult,
    ICCScore,
    UniversScore,
    ICCConfig,
    ICCLevel,
    AnomalyImpact,
    # Scorer
    ICCScorer,
    compute_anomaly_impact,
    compute_univers_scores,
    run_icc,
    # Report
    ReportGenerator,
    generate_summary,
    generate_recommendations,
    format_top_anomalies,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_config():
    """Configuration de test."""
    return ICCConfig()


@pytest.fixture
def sample_signal():
    """Signal de test."""
    return RawSignal(
        id="L2-VAR_613_202401",
        famille="613",
        univers=Univers.CRISTALLIN,
        test_id="L2-VAR",
        test_name="Variation mensuelle",
        metric_value=5000.0,
        threshold=3000.0,
        delta=2000.0,
        periode="2024-01",
        pvalue=0.02,
        pvalue_adjusted=0.03,
    )


@pytest.fixture
def sample_anomaly(sample_signal):
    """Anomalie qualifiée de test."""
    return QualifiedAnomaly(
        signal=sample_signal,
        materiality_amount=8000.0,
        materiality_threshold=5000.0,
        materiality_ratio=1.6,
        pertinence_score=75.0,
        pertinence_level=PertinenceLevel.HIGH,
        final_score=75.0,
        rank=1,
    )


@pytest.fixture
def sample_anomalies():
    """Liste d'anomalies de test."""
    anomalies = []

    # Anomalie 1: CRISTALLIN, haute pertinence
    sig1 = RawSignal(
        id="L2-VAR_613_202401",
        famille="613",
        univers=Univers.CRISTALLIN,
        test_id="L2-VAR",
        test_name="Variation loyer",
        metric_value=10000.0,
        threshold=5000.0,
        delta=5000.0,
        pvalue=0.01,
    )
    anomalies.append(QualifiedAnomaly(
        signal=sig1,
        materiality_amount=10000.0,
        materiality_threshold=5000.0,
        pertinence_score=85.0,
        pertinence_level=PertinenceLevel.CRITICAL,
        final_score=85.0,
        rank=1,
    ))

    # Anomalie 2: PONCTUEL, très haute pertinence
    sig2 = RawSignal(
        id="L2-VAR_672_202401",
        famille="672",
        univers=Univers.PONCTUEL,
        test_id="L2-VAR",
        test_name="Charge exceptionnelle",
        metric_value=25000.0,
        threshold=10000.0,
        delta=15000.0,
        pvalue=0.005,
    )
    anomalies.append(QualifiedAnomaly(
        signal=sig2,
        materiality_amount=25000.0,
        materiality_threshold=10000.0,
        pertinence_score=90.0,
        pertinence_level=PertinenceLevel.CRITICAL,
        final_score=90.0,
        rank=2,
    ))

    # Anomalie 3: CUT_OFF, pertinence moyenne
    sig3 = RawSignal(
        id="L2-VAR_486_202401",
        famille="486",
        univers=Univers.CUT_OFF,
        test_id="L2-MISSING",
        test_name="Extourne manquante",
        metric_value=3000.0,
        threshold=2000.0,
        delta=1000.0,
        pvalue=0.03,
    )
    anomalies.append(QualifiedAnomaly(
        signal=sig3,
        materiality_amount=3000.0,
        materiality_threshold=5000.0,
        pertinence_score=60.0,
        pertinence_level=PertinenceLevel.MEDIUM,
        final_score=60.0,
        rank=3,
    ))

    return anomalies


# =============================================================================
# TEST IMPACT CALCULATION
# =============================================================================

class TestImpactCalculation:
    """Tests calcul d'impact."""

    def test_compute_impact_basic(self, sample_anomaly, sample_config):
        """Calcul d'impact basique."""
        impact = compute_anomaly_impact(
            sample_anomaly,
            sample_config,
            total_materiality=100000.0,
        )

        assert isinstance(impact, AnomalyImpact)
        assert impact.anomaly_id == sample_anomaly.signal.id
        assert impact.final_impact > 0
        assert impact.final_impact <= sample_config.max_impact_per_anomaly

    def test_impact_increases_with_pertinence(self, sample_config):
        """Plus la pertinence est haute, plus l'impact est fort."""
        signal = RawSignal(
            id="test", famille="613", univers=Univers.CRISTALLIN,
            test_id="L2-VAR", test_name="Test",
            metric_value=5000, threshold=3000, delta=2000,
        )

        # Anomalie basse pertinence
        low = QualifiedAnomaly(
            signal=signal, materiality_amount=5000, materiality_threshold=5000,
            pertinence_score=30.0, pertinence_level=PertinenceLevel.LOW, final_score=30.0, rank=1,
        )
        # Anomalie haute pertinence
        high = QualifiedAnomaly(
            signal=signal, materiality_amount=5000, materiality_threshold=5000,
            pertinence_score=90.0, pertinence_level=PertinenceLevel.CRITICAL, final_score=90.0, rank=1,
        )

        impact_low = compute_anomaly_impact(low, sample_config, 100000)
        impact_high = compute_anomaly_impact(high, sample_config, 100000)

        assert impact_high.final_impact > impact_low.final_impact

    def test_impact_to_dict(self, sample_anomaly, sample_config):
        """Conversion impact en dict."""
        impact = compute_anomaly_impact(sample_anomaly, sample_config, 100000)
        d = impact.to_dict()

        assert "anomaly_id" in d
        assert "impacts" in d
        assert "final" in d["impacts"]


# =============================================================================
# TEST SCORER
# =============================================================================

class TestICCScorer:
    """Tests du scorer ICC."""

    def test_scorer_basic(self, sample_anomalies):
        """Scoring basique."""
        scorer = ICCScorer()
        result = scorer.score(sample_anomalies)

        assert isinstance(result, ICCResult)
        assert 0 <= result.global_score <= 100
        assert result.score.anomaly_count == len(sample_anomalies)

    def test_scorer_empty_list(self):
        """Liste vide = score 100."""
        scorer = ICCScorer()
        result = scorer.score([])

        assert result.global_score == 100.0
        assert result.score.level == ICCLevel.EXCELLENT

    def test_scorer_univers_scores(self, sample_anomalies):
        """Scores par univers calculés."""
        scorer = ICCScorer()
        result = scorer.score(sample_anomalies)

        assert len(result.univers_scores) > 0
        # Univers avec anomalies ont un score < 100
        for univers in ["CRISTALLIN", "PONCTUEL", "CUT_OFF"]:
            if univers in result.univers_scores:
                us = result.univers_scores[univers]
                assert us.anomaly_count > 0 or us.score == 100

    def test_scorer_top_anomalies(self, sample_anomalies):
        """Top anomalies extraites."""
        scorer = ICCScorer()
        result = scorer.score(sample_anomalies)

        assert len(result.top_anomalies) > 0
        assert len(result.top_anomalies) <= len(sample_anomalies)

        # Triées par impact décroissant
        if len(result.top_anomalies) >= 2:
            assert result.top_anomalies[0]["final_impact"] >= result.top_anomalies[1]["final_impact"]

    def test_scorer_with_period_entity(self, sample_anomalies):
        """Period et entity passés."""
        scorer = ICCScorer()
        result = scorer.score(sample_anomalies, period="2024-01", entity="ACME Corp")

        assert result.period == "2024-01"
        assert result.entity == "ACME Corp"


class TestRunICC:
    """Tests de la fonction raccourcie."""

    def test_run_icc_convenience(self, sample_anomalies):
        """Fonction run_icc."""
        result = run_icc(sample_anomalies)
        assert isinstance(result, ICCResult)


# =============================================================================
# TEST ICC RESULT
# =============================================================================

class TestICCResult:
    """Tests de ICCResult."""

    def test_result_summary(self, sample_anomalies):
        """Summary lisible."""
        result = run_icc(sample_anomalies)
        summary = result.summary()

        assert "ICC SCORE" in summary
        assert str(int(result.global_score)) in summary

    def test_result_radar_data(self, sample_anomalies):
        """Données radar."""
        result = run_icc(sample_anomalies)
        radar = result.radar_data()

        assert isinstance(radar, dict)
        assert all(0 <= v <= 100 for v in radar.values())

    def test_result_to_dict(self, sample_anomalies):
        """Conversion en dict."""
        result = run_icc(sample_anomalies)
        d = result.to_dict()

        assert "score" in d
        assert "univers_scores" in d
        assert "impacts" in d
        assert "top_anomalies" in d

    def test_result_to_json(self, sample_anomalies):
        """Export JSON."""
        result = run_icc(sample_anomalies)
        json_str = result.to_json()

        assert isinstance(json_str, str)
        import json
        parsed = json.loads(json_str)
        assert "score" in parsed


# =============================================================================
# TEST REPORT GENERATION
# =============================================================================

class TestReportGeneration:
    """Tests de génération de rapports."""

    def test_generate_summary(self, sample_anomalies):
        """Génération du résumé."""
        result = run_icc(sample_anomalies)
        summary = generate_summary(result)

        assert isinstance(summary, str)
        assert "Rapport ICC" in summary
        assert "Score Global" in summary

    def test_generate_recommendations(self, sample_anomalies):
        """Génération des recommandations."""
        result = run_icc(sample_anomalies)
        recs = generate_recommendations(result)

        assert isinstance(recs, list)
        assert len(recs) > 0
        assert all(isinstance(r, str) for r in recs)

    def test_format_top_anomalies(self, sample_anomalies):
        """Formatage des top anomalies."""
        result = run_icc(sample_anomalies)
        formatted = format_top_anomalies(result)

        assert "Top Anomalies" in formatted

    def test_report_generator_basic(self, sample_anomalies):
        """ReportGenerator basique."""
        result = run_icc(sample_anomalies)
        generator = ReportGenerator()
        report = generator.generate(result)

        assert "metadata" in report
        assert "executive_summary" in report
        assert "recommendations" in report

    def test_report_to_markdown(self, sample_anomalies):
        """Export Markdown."""
        result = run_icc(sample_anomalies)
        generator = ReportGenerator()
        md = generator.to_markdown(result)

        assert isinstance(md, str)
        assert "# " in md  # Headers

    def test_report_to_html(self, sample_anomalies):
        """Export HTML."""
        result = run_icc(sample_anomalies)
        generator = ReportGenerator()
        html = generator.to_html(result)

        assert "<html>" in html
        assert "</html>" in html


# =============================================================================
# TEST SCORE LEVELS
# =============================================================================

class TestScoreLevels:
    """Tests des niveaux de score."""

    def test_level_excellent(self):
        """Score >= 90 = EXCELLENT."""
        scorer = ICCScorer()
        result = scorer.score([])  # Pas d'anomalies = 100
        assert result.score.level == ICCLevel.EXCELLENT

    def test_level_detection(self, sample_config):
        """Vérification des seuils de niveau."""
        # Ces seuils sont définis dans ICCConfig.thresholds
        assert sample_config.thresholds["EXCELLENT"] == 90.0
        assert sample_config.thresholds["BON"] == 75.0
        assert sample_config.thresholds["ACCEPTABLE"] == 60.0
        assert sample_config.thresholds["ATTENTION"] == 40.0


# =============================================================================
# TEST UNIVERS SCORES
# =============================================================================

class TestUniversScores:
    """Tests des scores par univers."""

    def test_univers_score_structure(self, sample_anomalies):
        """Structure UniversScore."""
        result = run_icc(sample_anomalies)

        for univers, us in result.univers_scores.items():
            assert isinstance(us, UniversScore)
            assert us.univers == univers
            assert 0 <= us.score <= 100
            assert us.anomaly_count >= 0

    def test_univers_with_anomalies_lower_score(self, sample_anomalies):
        """Univers avec anomalies ont un score plus bas."""
        result = run_icc(sample_anomalies)

        # PONCTUEL a une anomalie avec haute pertinence
        ponctuel = result.univers_scores.get("PONCTUEL")
        tresorerie = result.univers_scores.get("TRESORERIE")

        if ponctuel and tresorerie:
            # TRESORERIE n'a pas d'anomalie dans nos fixtures
            if tresorerie.anomaly_count == 0:
                assert tresorerie.score > ponctuel.score


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
