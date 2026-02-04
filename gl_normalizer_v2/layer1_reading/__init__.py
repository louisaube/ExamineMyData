"""
Couche 1 : Lecture comptable
============================

Modules de bon sens comptable codifié :
- JournalClassifier: OD, SAL, VTE, ACH, BQ
- PCGClassifier: Plan Comptable Général
- ABTDetector: Comptes d'abonnement (488)
- ProvisionMatcher: Couples dotations/reprises
"""

from .journal_classifier import JournalClassifier, JournalType
from .pcg_classifier import PCGClassifier, PCGInfo, Behavior
from .abt_detector import ABTDetector, ABTAccount
from .provision_matcher import ProvisionMatcher, ProvisionCouple

__all__ = [
    "JournalClassifier",
    "JournalType",
    "PCGClassifier",
    "PCGInfo",
    "Behavior",
    "ABTDetector",
    "ABTAccount",
    "ProvisionMatcher",
    "ProvisionCouple",
]
