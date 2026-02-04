"""
Tests pour gl_normalizer/layer2/base.py et calibration.py
"""

import pytest
from gl_normalizer.layer2.base import Univers, RawSignal, FamilySignal
from gl_normalizer.layer2.calibration import (
    dead_band,
    seuil_relatif,
    seuil_materialite,
    seuil_variation,
    z_score_calibre,
    est_montant_rond,
    meme_montant_n_mois,
    MATERIALITE_PLANCHER,
)


class TestUnivers:
    """Tests pour l'enum Univers."""

    def test_univers_values(self):
        """Vérifie que tous les univers attendus existent."""
        expected = [
            "CRISTALLIN", "NOMINATIF_TIERS", "NOMINATIF_OPERATIONNEL",
            "PROCESSUS", "VENTILATION", "CUT_OFF", "TRESORERIE",
            "PONCTUEL", "INVENTAIRE", "COMPOSITE"
        ]
        actual = [u.value for u in Univers]
        assert set(expected) == set(actual)

    def test_univers_string_conversion(self):
        """Vérifie la conversion string."""
        assert Univers.CRISTALLIN.value == "CRISTALLIN"
        assert str(Univers.CRISTALLIN) == "Univers.CRISTALLIN"


class TestRawSignal:
    """Tests pour la dataclass RawSignal."""

    def test_raw_signal_creation(self):
        """Test création basique."""
        signal = RawSignal(
            id="T-CRIS-01_613_202401",
            famille="613",
            univers=Univers.CRISTALLIN,
            test_id="T-CRIS-01",
            test_name="Variation montant",
            metric_value=0.08,
            threshold=0.05,
            delta=0.03,
        )
        assert signal.famille == "613"
        assert signal.univers == Univers.CRISTALLIN
        assert signal.delta == 0.03

    def test_raw_signal_auto_score(self):
        """Test calcul automatique du score."""
        signal = RawSignal(
            id="test",
            famille="613",
            univers=Univers.CRISTALLIN,
            test_id="T-CRIS-01",
            test_name="Test",
            metric_value=0.10,
            threshold=0.05,
            delta=0.05,
        )
        # delta/threshold * 50 = 0.05/0.05 * 50 = 50
        assert signal.raw_score == 50.0

    def test_raw_signal_severity(self):
        """Test classification sévérité."""
        # LOW
        signal_low = RawSignal(
            id="t1", famille="613", univers=Univers.CRISTALLIN,
            test_id="T1", test_name="T", metric_value=0.06, threshold=0.05, delta=0.01
        )
        assert signal_low.severity == "LOW"

        # CRITICAL
        signal_crit = RawSignal(
            id="t2", famille="613", univers=Univers.CRISTALLIN,
            test_id="T2", test_name="T", metric_value=0.15, threshold=0.05, delta=0.10,
            raw_score=85.0
        )
        assert signal_crit.severity == "CRITICAL"

    def test_raw_signal_exclusion(self):
        """Test flag exclusion."""
        signal_excluded = RawSignal(
            id="t1", famille="613", univers=Univers.CRISTALLIN,
            test_id="T1", test_name="T", metric_value=0.08, threshold=0.05, delta=0.03,
            non_signal_si_matched=["montant_rond"]
        )
        assert signal_excluded.is_excluded is True

        signal_not_excluded = RawSignal(
            id="t2", famille="613", univers=Univers.CRISTALLIN,
            test_id="T2", test_name="T", metric_value=0.08, threshold=0.05, delta=0.03,
        )
        assert signal_not_excluded.is_excluded is False

    def test_raw_signal_to_dict(self):
        """Test sérialisation."""
        signal = RawSignal(
            id="T-CRIS-01_613",
            famille="613",
            univers=Univers.CRISTALLIN,
            test_id="T-CRIS-01",
            test_name="Variation",
            metric_value=0.08,
            threshold=0.05,
            delta=0.03,
            periode="2024-01",
        )
        d = signal.to_dict()
        assert d["famille"] == "613"
        assert d["univers"] == "CRISTALLIN"
        assert d["periode"] == "2024-01"
        assert "is_excluded" in d
        assert "severity" in d


class TestFamilySignal:
    """Tests pour FamilySignal (agrégation)."""

    def test_family_signal_aggregation(self):
        """Test agrégation de signaux."""
        signals = [
            RawSignal(
                id="t1", famille="613", univers=Univers.CRISTALLIN,
                test_id="T-CRIS-01", test_name="T1",
                metric_value=0.08, threshold=0.05, delta=0.03, raw_score=30.0
            ),
            RawSignal(
                id="t2", famille="613", univers=Univers.CRISTALLIN,
                test_id="T-CRIS-02", test_name="T2",
                metric_value=0.12, threshold=0.05, delta=0.07, raw_score=70.0
            ),
        ]
        family = FamilySignal(
            famille="613",
            univers=Univers.CRISTALLIN,
            tests_triggered=["T-CRIS-01", "T-CRIS-02"],
            max_score=70.0,
            signals=signals,
            summary="2 anomalies sur famille 613"
        )
        assert family.count == 2
        assert family.max_score == 70.0

    def test_family_signal_active_signals(self):
        """Test filtrage signaux actifs (non exclus)."""
        signals = [
            RawSignal(
                id="t1", famille="613", univers=Univers.CRISTALLIN,
                test_id="T1", test_name="T1",
                metric_value=0.08, threshold=0.05, delta=0.03,
                non_signal_si_matched=["montant_rond"]  # Exclu
            ),
            RawSignal(
                id="t2", famille="613", univers=Univers.CRISTALLIN,
                test_id="T2", test_name="T2",
                metric_value=0.08, threshold=0.05, delta=0.03,
            ),
        ]
        family = FamilySignal(
            famille="613",
            univers=Univers.CRISTALLIN,
            tests_triggered=["T1", "T2"],
            max_score=30.0,
            signals=signals,
        )
        assert len(family.active_signals) == 1
        assert family.has_exclusions is True


class TestDeadBand:
    """Tests pour la fonction dead_band()."""

    def test_dead_band_cristallin(self):
        """CRISTALLIN avec cv très faible."""
        # cv = 0.05 → dead_band = 1.5 + 2.0 * 0.05 = 1.6
        assert dead_band(0.05) == pytest.approx(1.6, rel=0.01)

    def test_dead_band_loyers(self):
        """Famille 613 loyers avec cv réel ~0.72."""
        # cv = 0.72 → dead_band = 1.5 + 2.0 * 0.72 = 2.94
        assert dead_band(0.72) == pytest.approx(2.94, rel=0.01)

    def test_dead_band_nominatif(self):
        """NOMINATIF volatile."""
        # cv = 1.20 → dead_band = 1.5 + 2.0 * 1.20 = 3.9
        assert dead_band(1.20) == pytest.approx(3.9, rel=0.01)

    def test_dead_band_ponctuel(self):
        """PONCTUEL très volatile."""
        # cv = 2.00 → dead_band = 1.5 + 2.0 * 2.00 = 5.5
        assert dead_band(2.00) == pytest.approx(5.5, rel=0.01)

    def test_dead_band_zero(self):
        """CV = 0 → minimum 1.5."""
        assert dead_band(0.0) == 1.5


class TestSeuilRelatif:
    """Tests pour seuil_relatif()."""

    def test_seuil_relatif_normal(self):
        """Cas normal: seuil > plancher."""
        # 5% de 100K€ = 5K€ > 500€ plancher
        assert seuil_relatif(100_000, 0.05) == 5000.0

    def test_seuil_relatif_plancher(self):
        """Cas plancher: seuil < plancher."""
        # 5% de 5K€ = 250€ < 500€ plancher
        assert seuil_relatif(5_000, 0.05) == MATERIALITE_PLANCHER

    def test_seuil_relatif_custom_plancher(self):
        """Plancher personnalisé."""
        assert seuil_relatif(5_000, 0.05, plancher=100.0) == 250.0


class TestSeuilMaterialite:
    """Tests pour seuil_materialite()."""

    def test_seuil_materialite_cristallin(self):
        """Famille CRISTALLIN avec 2% matérialité."""
        referentiel = {
            "613": {
                "univers": "CRISTALLIN",
                "volume_annuel_median": 500_000
            }
        }
        # 2% de 500K€ = 10K€
        assert seuil_materialite("613", referentiel) == 10_000.0

    def test_seuil_materialite_composite(self):
        """Famille COMPOSITE (défaut 8%)."""
        referentiel = {
            "999": {
                "univers": "COMPOSITE",
                "volume_annuel_median": 50_000
            }
        }
        # 8% de 50K€ = 4K€
        assert seuil_materialite("999", referentiel) == 4_000.0

    def test_seuil_materialite_famille_inconnue(self):
        """Famille absente du référentiel → défauts."""
        referentiel = {}
        # Défaut: volume=100K€, univers=COMPOSITE (8%)
        # 8% de 100K€ = 8K€
        assert seuil_materialite("XXX", referentiel) == 8_000.0


class TestSeuilVariation:
    """Tests pour seuil_variation()."""

    def test_seuil_variation_cristallin(self):
        """CRISTALLIN = 5%."""
        assert seuil_variation(Univers.CRISTALLIN) == 0.05

    def test_seuil_variation_nominatif(self):
        """NOMINATIF_TIERS = 30%."""
        assert seuil_variation(Univers.NOMINATIF_TIERS) == 0.30

    def test_seuil_variation_adapte(self):
        """Adaptation au CV historique."""
        # CV historique 0.08 → 1.5 * 0.08 = 0.12 > 0.05 (seuil CRISTALLIN)
        assert seuil_variation(Univers.CRISTALLIN, cv_historique=0.08) == pytest.approx(0.12)

    def test_seuil_variation_cv_faible(self):
        """CV historique faible → garde seuil univers."""
        # CV historique 0.02 → 1.5 * 0.02 = 0.03 < 0.05 (seuil CRISTALLIN)
        assert seuil_variation(Univers.CRISTALLIN, cv_historique=0.02) == 0.05


class TestZScoreCalibre:
    """Tests pour z_score_calibre()."""

    def test_z_score_calibre_signal(self):
        """Z-score qui dépasse la dead band."""
        # 1200 vs moyenne 1000, std 100 → z = 2.0
        # cv_attendu = 0.05 → dead_band = 1.6
        # 2.0 > 1.6 → signal
        z, is_signal = z_score_calibre(1200, 1000, 100, cv_attendu=0.05)
        assert z == pytest.approx(2.0)
        assert is_signal is True

    def test_z_score_calibre_no_signal(self):
        """Z-score sous la dead band."""
        # z = 2.0, cv_attendu = 1.0 → dead_band = 3.5
        # 2.0 < 3.5 → pas de signal
        z, is_signal = z_score_calibre(1200, 1000, 100, cv_attendu=1.0)
        assert z == pytest.approx(2.0)
        assert is_signal is False

    def test_z_score_calibre_zero_std(self):
        """Écart-type nul → pas de signal."""
        z, is_signal = z_score_calibre(1000, 1000, 0, cv_attendu=0.05)
        assert z == 0.0
        assert is_signal is False


class TestEstMontantRond:
    """Tests pour est_montant_rond()."""

    def test_montant_rond_1000(self):
        """1000€ exact."""
        assert est_montant_rond(1000.0) is True

    def test_montant_rond_5000(self):
        """5000€ exact."""
        assert est_montant_rond(5000.0) is True

    def test_montant_rond_tolerance(self):
        """Avec tolérance 1%."""
        assert est_montant_rond(1005.0) is True  # 0.5% de 1000
        assert est_montant_rond(995.0) is True   # 0.5% de 1000

    def test_montant_non_rond(self):
        """Montant non rond."""
        assert est_montant_rond(1234.56) is False

    def test_montant_petit(self):
        """Montant < 100€ → jamais rond."""
        assert est_montant_rond(50.0) is False


class TestMemeMontantNMois:
    """Tests pour meme_montant_n_mois()."""

    def test_meme_montant_12_mois(self):
        """Même montant 12 fois."""
        montants = [1000.0] * 12
        assert meme_montant_n_mois(montants, n=12) is True

    def test_meme_montant_tolerance(self):
        """Avec petites variations."""
        montants = [1000.0, 1005.0, 995.0, 1002.0, 998.0, 1001.0,
                    1003.0, 997.0, 1004.0, 996.0, 1000.0, 999.0]
        assert meme_montant_n_mois(montants, n=12, tolerance=0.01) is True

    def test_montants_differents(self):
        """Montants variables."""
        montants = [1000.0, 1500.0, 800.0, 2000.0, 500.0, 1200.0,
                    900.0, 1100.0, 1300.0, 700.0, 1400.0, 600.0]
        assert meme_montant_n_mois(montants, n=12) is False

    def test_pas_assez_de_mois(self):
        """Moins de N mois."""
        montants = [1000.0] * 6
        assert meme_montant_n_mois(montants, n=12) is False
