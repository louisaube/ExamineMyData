"""
gl_normalizer/layer2 - Tests de Normalité par Univers

Layer 2 de GL Crystal : génère ~200 signaux bruts à partir du GL + référentiel.
Chaque test est calibré selon l'univers sémantique de la famille.

Architecture:
- base.py: RawSignal dataclass, BaseUniverseTest ABC
- calibration.py: dead_band(), seuil_relatif()
- registry.py: TestRegistry mapping univers → tests
- runner.py: Layer2Runner orchestration
- tests/: Implémentations par univers

Usage:
    from gl_normalizer.layer2 import Layer2Runner, RawSignal

    runner = Layer2Runner(referentiel)
    signals: List[RawSignal] = runner.run(gl_dataframe)
"""

from .base import RawSignal, BaseUniverseTest, Univers
from .calibration import dead_band, seuil_relatif, seuil_materialite

__all__ = [
    "RawSignal",
    "BaseUniverseTest",
    "Univers",
    "dead_band",
    "seuil_relatif",
    "seuil_materialite",
]
