"""
gl_normalizer/layer2 - Tests de Normalité par Univers (v2)

Layer 2 de GL Crystal : génère signaux bruts à partir du GL + référentiel.
Utilise des méthodes statistiques distribution-free:
- Conformal Prediction: p-values avec garantie de couverture
- Matrix Profile (STUMPY): détection de discord
- ECOD: scoring multivarié
- BH-FDR: contrôle des faux positifs

Architecture:
- base.py: RawSignal, FamilySignal, BaseUniverseTest, Univers
- calibration.py: conformal_pvalue(), dead_band() (fallback)
- statistical.py: matrix_profile_discord(), ecod_score()
- fdr_filter.py: benjamini_hochberg(), fdr_filter()
- runner.py: Layer2Runner orchestration
- tests/: Implémentations par univers

Usage:
    from gl_normalizer.layer2 import Layer2Runner, RawSignal

    runner = Layer2Runner(referentiel)
    signals: List[RawSignal] = runner.run(gl_dataframe)
"""

from .base import RawSignal, FamilySignal, BaseUniverseTest, Univers
from .calibration import (
    dead_band,
    seuil_relatif,
    seuil_materialite,
    conformal_pvalue,
    conformal_or_fallback,
    MIN_MOIS_CONFORMAL,
)
from .statistical import (
    matrix_profile_discord,
    detect_discord_months,
    ecod_score_univariate,
    ecod_score_multivariate,
    is_stumpy_available,
)
from .fdr_filter import (
    benjamini_hochberg,
    fdr_filter,
    fdr_filter_simple,
    FDRResult,
)
from .runner import Layer2Runner, Layer2Result, run_layer2

__all__ = [
    # Base
    "RawSignal",
    "FamilySignal",
    "BaseUniverseTest",
    "Univers",
    # Calibration
    "dead_band",
    "seuil_relatif",
    "seuil_materialite",
    "conformal_pvalue",
    "conformal_or_fallback",
    "MIN_MOIS_CONFORMAL",
    # Statistical
    "matrix_profile_discord",
    "detect_discord_months",
    "ecod_score_univariate",
    "ecod_score_multivariate",
    "is_stumpy_available",
    # FDR
    "benjamini_hochberg",
    "fdr_filter",
    "fdr_filter_simple",
    "FDRResult",
    # Runner
    "Layer2Runner",
    "Layer2Result",
    "run_layer2",
]
