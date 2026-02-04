"""
Couche 2 : Tableau de passage
=============================

LE COEUR du produit : transformation P&L brut → P&L normalisé.
"""

from .passage_table_builder import (
    PassageTableBuilder,
    Retraitement,
    RetraitementType,
    MonthlyPassage,
    AnnualSummary,
    RunRate,
)

__all__ = [
    "PassageTableBuilder",
    "Retraitement",
    "RetraitementType",
    "MonthlyPassage",
    "AnnualSummary",
    "RunRate",
]
