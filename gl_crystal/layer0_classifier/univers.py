"""
GL Crystal - Les Cinq Univers Sémantiques

Découverte empirique centrale sur le GL MicroStars 2024.
"""

from enum import Enum
from dataclasses import dataclass
from typing import List, Set


class UniversSemantique(str, Enum):
    """Les cinq univers sémantiques + non classé."""
    CRISTALLIN = "CRISTALLIN"
    NOMINATIF = "NOMINATIF"
    INVENTAIRE = "INVENTAIRE"
    VENTILATION = "VENTILATION"
    COMPOSITE = "COMPOSITE"
    NON_CLASSE = "NON_CLASSE"


@dataclass
class UniversProfile:
    """Profil d'un univers sémantique."""
    univers: UniversSemantique
    description: str
    volume_attendu_pct: float  # % des flux attendu

    # Caractéristiques
    shannon_brut_range: tuple  # (min, max) attendu
    cv_montants_range: tuple
    regularite_temporelle_min: float

    # Contrôle pertinent
    controle_pertinent: str

    # Axes ICC actifs
    axes_icc_actifs: List[str]
    icc_attendu: float
    seuil_surprise: float


# Profils des univers
UNIVERS_PROFILES = {
    UniversSemantique.CRISTALLIN: UniversProfile(
        univers=UniversSemantique.CRISTALLIN,
        description="Même opération répétée. Loyer mensuel, abonnement fixe, dotation linéaire.",
        volume_attendu_pct=14.0,
        shannon_brut_range=(0.0, 2.0),
        cv_montants_range=(0.0, 0.15),
        regularite_temporelle_min=0.8,
        controle_pertinent="Régularité temporelle uniquement. Toute déviation est significative.",
        axes_icc_actifs=["montants", "temporalite", "journaux", "contreparties"],
        icc_attendu=0.10,
        seuil_surprise=0.15,
    ),

    UniversSemantique.NOMINATIF: UniversProfile(
        univers=UniversSemantique.NOMINATIF,
        description="Entropie apparente des noms propres. Facturation familles, paie.",
        volume_attendu_pct=47.5,
        shannon_brut_range=(3.0, 8.0),  # Élevée en apparence
        cv_montants_range=(0.0, 1.0),
        regularite_temporelle_min=0.5,
        controle_pertinent="Arithmétique : N entités × montant unitaire = total attendu.",
        axes_icc_actifs=["montants", "temporalite", "journaux", "contreparties"],  # PAS libellés
        icc_attendu=0.20,
        seuil_surprise=0.20,
    ),

    UniversSemantique.INVENTAIRE: UniversProfile(
        univers=UniversSemantique.INVENTAIRE,
        description="Amortissements, provisions par actif. Calcul déterministe.",
        volume_attendu_pct=2.7,
        shannon_brut_range=(4.0, 9.0),  # Très élevée (réf immo)
        cv_montants_range=(0.0, 0.5),
        regularite_temporelle_min=0.9,  # Mensuel parfait
        controle_pertinent="Conformité au tableau d'amortissement.",
        axes_icc_actifs=["montants", "temporalite", "journaux", "contreparties"],  # PAS libellés
        icc_attendu=0.08,
        seuil_surprise=0.12,
    ),

    UniversSemantique.VENTILATION: UniversProfile(
        univers=UniversSemantique.VENTILATION,
        description="Répartitions analytiques, refacturations inter-sites.",
        volume_attendu_pct=5.0,
        shannon_brut_range=(1.0, 4.0),
        cv_montants_range=(0.0, 0.8),
        regularite_temporelle_min=0.3,
        controle_pertinent="Somme des ventilations = flux source. Cohérence des clés.",
        axes_icc_actifs=["montants", "temporalite", "journaux", "contreparties", "libelles"],
        icc_attendu=0.30,
        seuil_surprise=0.25,
    ),

    UniversSemantique.COMPOSITE: UniversProfile(
        univers=UniversSemantique.COMPOSITE,
        description="Vrai bazar. Multi-journaux, multi-natures, multi-fournisseurs.",
        volume_attendu_pct=6.1,
        shannon_brut_range=(3.0, 8.0),
        cv_montants_range=(0.5, 3.0),
        regularite_temporelle_min=0.0,
        controle_pertinent="Analyse d'entropie + NLP + reclassification.",
        axes_icc_actifs=["montants", "libelles", "temporalite", "journaux", "contreparties"],
        icc_attendu=0.65,
        seuil_surprise=0.15,
    ),

    UniversSemantique.NON_CLASSE: UniversProfile(
        univers=UniversSemantique.NON_CLASSE,
        description="Profil intermédiaire. À qualifier progressivement.",
        volume_attendu_pct=24.7,
        shannon_brut_range=(0.0, 8.0),
        cv_montants_range=(0.0, 3.0),
        regularite_temporelle_min=0.0,
        controle_pertinent="Dépend de la classification à venir.",
        axes_icc_actifs=["montants", "libelles", "temporalite", "journaux", "contreparties"],
        icc_attendu=0.40,
        seuil_surprise=0.30,
    ),
}


# Comptes typiques par univers (pour aide à la classification)
COMPTES_TYPIQUES = {
    UniversSemantique.CRISTALLIN: {'613', '616', '626'},  # Loyers, assurances, télécom
    UniversSemantique.NOMINATIF: {'641', '706', '707'},   # Salaires, ventes
    UniversSemantique.INVENTAIRE: {'681', '686', '281', '291'},  # Dotations, amortissements
    UniversSemantique.VENTILATION: {'791'},  # Transferts de charges
    UniversSemantique.COMPOSITE: {'618', '627', '471'},  # Divers, attente
}


def get_univers_attendu(famille: str) -> UniversSemantique:
    """
    Retourne l'univers attendu pour une famille de comptes.

    C'est une heuristique initiale, la vraie classification vient des features.
    """
    for univers, familles in COMPTES_TYPIQUES.items():
        if famille in familles:
            return univers
    return UniversSemantique.NON_CLASSE
