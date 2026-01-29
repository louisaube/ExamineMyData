"""
gl_normalizer/config.py
Configuration et constantes pour l'analyse GL/P&L
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class NormalizerConfig:
    """Configuration des seuils et paramètres d'analyse"""

    # Seuils de détection d'anomalies
    z_score_threshold: float = 1.5       # Écart-types pour anomalie
    min_ecart_absolu: float = 2000       # Euros minimum pour signaler
    min_ecart_pct: float = 30            # Pourcentage minimum pour signaler
    seuil_regul: float = 2000            # Régularisation significative (€)

    # Mois de référence pour normalisation (décembre par défaut)
    mois_reference: int = 12

    # Nombre de mois dans l'année
    nb_mois: int = 12


# Mapping des colonnes par format d'export comptable
COLUMN_MAPPINGS: Dict[str, Dict[str, str]] = {
    "sage": {
        "date": "Date",
        "compte": "N° Compte",
        "libelle_compte": "Intitulé compte",
        "journal": "Code journal",
        "piece": "N° Pièce",
        "libelle": "Libellé écriture",
        "debit": "Débit",
        "credit": "Crédit",
    },
    "cegid": {
        "date": "DATE",
        "compte": "COMPTE",
        "libelle_compte": "LIB_COMPTE",
        "journal": "JOURNAL",
        "piece": "PIECE",
        "libelle": "LIBELLE",
        "debit": "DEBIT",
        "credit": "CREDIT",
    },
    "generic": {
        "date": "date",
        "compte": "compte",
        "libelle_compte": "libelle_compte",
        "journal": "journal",
        "piece": "piece",
        "libelle": "libelle",
        "debit": "debit",
        "credit": "credit",
    }
}

# Colonnes standardisées en sortie
STANDARD_COLUMNS = [
    "date", "compte", "libelle_compte", "journal",
    "piece", "libelle", "debit", "credit"
]

# Colonnes calculées ajoutées après harmonisation
COMPUTED_COLUMNS = [
    "periode",      # YYYY-MM
    "annee",        # Année extraite
    "mois",         # Mois extrait
    "classe",       # Classe comptable (1er chiffre)
    "racine_2",     # 2 premiers chiffres
    "racine_3",     # 3 premiers chiffres
    "montant",      # Débit - Crédit
]

# Comptes de provisions/régularisations (contreparties bilan)
COMPTES_PROVISION: Dict[str, str] = {
    "486": "Charges constatées d'avance (CCA)",
    "487": "Produits constatés d'avance (PCA)",
    "408": "Fournisseurs - Factures non parvenues (FNP)",
    "418": "Clients - Factures à établir (FAE)",
    "428": "Personnel - Charges à payer",
    "438": "Organismes sociaux - Charges à payer",
    "448": "État - Charges à payer",
    "488": "Comptes de régularisation",
    "491": "Dépréciation comptes clients",
    "158": "Autres provisions pour charges",
    "151": "Provisions pour risques",
    "695": "Impôt sur les bénéfices",
    "681": "Dotations aux amortissements",
    "686": "Dotations aux provisions financières",
    "687": "Dotations aux provisions exceptionnelles",
}

# Racines de comptes d'achats/charges à surveiller
COMPTES_CHARGES: List[str] = ["60", "61", "62", "63", "64", "65", "66", "67", "68", "69"]

# Journaux typiques de régularisation
JOURNAUX_OD: List[str] = ["OD", "AN", "RAN", "CLO", "EXT", "BILAN"]

# Types d'écritures pour classification
class EntryType:
    RUN_RATE = "RUN_RATE"           # Charge récurrente normale
    SEASONAL = "SEASONAL"            # Charge saisonnière
    ESTIMATIF = "ESTIMATIF"          # Provision/estimation
    ONE_SHOT = "ONE_SHOT"            # Charge exceptionnelle non récurrente
    REGUL = "REGUL"                  # Régularisation
    UNKNOWN = "UNKNOWN"              # Non classifié
