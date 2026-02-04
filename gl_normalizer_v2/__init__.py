"""
GL Normalizer v2
================

Un comptable senior automatisé, pas un data scientist.

Architecture 4 couches:
- Couche 1: Lecture comptable (journaux, PCG, ABT, provisions)
- Couche 2: Tableau de passage (brut → normalisé)
- Couche 3: Alertes contextuelles
- Couche 4: IA optionnelle
"""

__version__ = "2.0.0"

from .gl_loader import GLLoader
from .layer1_reading import (
    JournalClassifier,
    JournalType,
    PCGClassifier,
    PCGInfo,
    ABTDetector,
    ABTAccount,
    ProvisionMatcher,
    ProvisionCouple,
)
from .layer2_passage import PassageTableBuilder, MonthlyPassage, AnnualSummary, RunRate
from .layer3_alerts import AlertGenerator, Alert, AlertType
from .output import ExcelReporter

__all__ = [
    "GLLoader",
    "JournalClassifier",
    "JournalType",
    "PCGClassifier",
    "PCGInfo",
    "ABTDetector",
    "ABTAccount",
    "ProvisionMatcher",
    "ProvisionCouple",
    "PassageTableBuilder",
    "MonthlyPassage",
    "AnnualSummary",
    "RunRate",
    "AlertGenerator",
    "Alert",
    "AlertType",
    "ExcelReporter",
]
