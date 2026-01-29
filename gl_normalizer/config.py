"""
gl_normalizer/config.py
Configuration et constantes pour l'analyse GL/P&L
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


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

    # Analytique : activer l'analyse par axe
    use_analytique: bool = True

    # Axes analytiques à utiliser (si vide, utilise tous ceux détectés)
    axes_analytiques: List[str] = field(default_factory=list)


# =============================================================================
# MAPPING DES COLONNES PAR FORMAT
# =============================================================================

# Colonnes obligatoires pour le fonctionnement
REQUIRED_COLUMNS = ["date", "compte", "debit", "credit"]

# Colonnes optionnelles mais recommandées
OPTIONAL_COLUMNS = ["libelle_compte", "journal", "piece", "libelle"]

# Colonnes analytiques possibles
ANALYTICAL_COLUMNS = [
    "axe_1", "axe_2", "axe_3",
    "section_analytique", "centre_cout", "projet",
    "code_analytique", "analytique",
]

# Mapping des colonnes par format d'export comptable
COLUMN_MAPPINGS: Dict[str, Dict[str, List[str]]] = {
    "sage": {
        "date": ["Date", "Date écriture", "Date pièce"],
        "compte": ["N° Compte", "Compte", "N° compte général", "Compte général"],
        "libelle_compte": ["Intitulé compte", "Libellé compte", "Intitulé"],
        "journal": ["Code journal", "Journal", "Code jal"],
        "piece": ["N° Pièce", "Pièce", "N° document"],
        "libelle": ["Libellé écriture", "Libellé", "Référence"],
        "debit": ["Débit", "Montant débit", "Debit"],
        "credit": ["Crédit", "Montant crédit", "Credit"],
        # Analytique Sage
        "axe_1": ["Section analytique", "Axe 1", "Centre analytique", "N° Section"],
        "axe_2": ["Axe 2", "Section 2"],
        "axe_3": ["Axe 3", "Section 3"],
    },
    "cegid": {
        "date": ["DATE", "DATECPT", "DATE_PIECE"],
        "compte": ["COMPTE", "NUMCPT", "COMPTE_GENERAL"],
        "libelle_compte": ["LIB_COMPTE", "LIBCPT", "LIBELLE_COMPTE"],
        "journal": ["JOURNAL", "CODEJAL", "CODE_JOURNAL"],
        "piece": ["PIECE", "NUMPIECE", "NUM_PIECE"],
        "libelle": ["LIBELLE", "LIBECRITURE", "LIB_ECRITURE"],
        "debit": ["DEBIT", "MTDEBIT", "MONTANT_DEBIT"],
        "credit": ["CREDIT", "MTCREDIT", "MONTANT_CREDIT"],
        # Analytique Cegid
        "axe_1": ["AXE1", "SECTION1", "ANALYTIQUE1", "CODE_ANA1"],
        "axe_2": ["AXE2", "SECTION2", "ANALYTIQUE2", "CODE_ANA2"],
        "axe_3": ["AXE3", "SECTION3", "ANALYTIQUE3", "CODE_ANA3"],
    },
    "quadratus": {
        "date": ["Date", "DateEcriture"],
        "compte": ["Compte", "NumeroCompte"],
        "libelle_compte": ["LibelleCompte"],
        "journal": ["Journal", "CodeJournal"],
        "piece": ["Piece", "NumeroPiece"],
        "libelle": ["Libelle", "LibelleEcriture"],
        "debit": ["Debit", "MontantDebit"],
        "credit": ["Credit", "MontantCredit"],
        "axe_1": ["Analytique", "SectionAnalytique"],
    },
    "ebp": {
        "date": ["Date"],
        "compte": ["N° de compte", "Numéro de compte"],
        "libelle_compte": ["Intitulé du compte"],
        "journal": ["Code journal"],
        "piece": ["N° de pièce"],
        "libelle": ["Libellé"],
        "debit": ["Débit"],
        "credit": ["Crédit"],
        "axe_1": ["Code analytique", "Analytique"],
    },
    "generic": {
        "date": ["date", "Date", "DATE"],
        "compte": ["compte", "Compte", "COMPTE", "account", "Account"],
        "libelle_compte": ["libelle_compte", "LibelleCompte", "account_name"],
        "journal": ["journal", "Journal", "JOURNAL"],
        "piece": ["piece", "Piece", "PIECE", "reference"],
        "libelle": ["libelle", "Libelle", "LIBELLE", "description"],
        "debit": ["debit", "Debit", "DEBIT"],
        "credit": ["credit", "Credit", "CREDIT"],
        "axe_1": ["analytique", "axe_1", "cost_center", "centre_cout"],
        "axe_2": ["axe_2", "projet", "project"],
        "axe_3": ["axe_3"],
    }
}

# Colonnes standardisées en sortie
STANDARD_COLUMNS = [
    "date", "compte", "libelle_compte", "journal",
    "piece", "libelle", "debit", "credit"
]

# Colonnes analytiques standardisées
STANDARD_ANALYTICAL_COLUMNS = ["axe_1", "axe_2", "axe_3"]

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


# =============================================================================
# COMPTES COMPTABLES
# =============================================================================

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

# Racines de comptes de produits
COMPTES_PRODUITS: List[str] = ["70", "71", "72", "73", "74", "75", "76", "77", "78", "79"]

# Journaux typiques de régularisation
JOURNAUX_OD: List[str] = ["OD", "AN", "RAN", "CLO", "EXT", "BILAN", "EXTOURNE"]


# =============================================================================
# TYPES D'ÉCRITURES
# =============================================================================

class EntryType:
    """Types d'écritures pour classification"""
    RUN_RATE = "RUN_RATE"           # Charge récurrente normale
    SEASONAL = "SEASONAL"            # Charge saisonnière
    ESTIMATIF = "ESTIMATIF"          # Provision/estimation
    ONE_SHOT = "ONE_SHOT"            # Charge exceptionnelle non récurrente
    REGUL = "REGUL"                  # Régularisation
    UNKNOWN = "UNKNOWN"              # Non classifié


# =============================================================================
# VALIDATION DES HEADERS
# =============================================================================

@dataclass
class ColumnMapping:
    """Mapping d'une colonne source vers colonne standard"""
    standard_name: str          # Nom standardisé (ex: "compte")
    source_name: str            # Nom dans le fichier source (ex: "N° Compte")
    is_required: bool = False   # Colonne obligatoire ?
    is_analytical: bool = False # Colonne analytique ?
    confidence: float = 1.0     # Score de confiance du mapping (0-1)


@dataclass
class HeaderValidation:
    """Résultat de la validation des headers"""
    is_valid: bool                              # Tous les champs requis sont mappés
    detected_format: str                        # Format détecté (sage, cegid, etc.)
    mappings: List[ColumnMapping]               # Mappings détectés
    missing_required: List[str]                 # Colonnes requises manquantes
    unmapped_columns: List[str]                 # Colonnes source non mappées
    suggestions: Dict[str, List[str]]           # Suggestions pour colonnes manquantes
    analytical_columns_found: List[str]         # Colonnes analytiques trouvées

    def get_mapping_dict(self) -> Dict[str, str]:
        """Retourne le dictionnaire de mapping source -> standard"""
        return {m.source_name: m.standard_name for m in self.mappings}

    def summary(self) -> str:
        """Résumé textuel de la validation"""
        lines = [
            f"Format détecté: {self.detected_format}",
            f"Validation: {'OK' if self.is_valid else 'ERREUR'}",
            "",
            "Colonnes mappées:",
        ]
        for m in self.mappings:
            status = "REQUIS" if m.is_required else ("ANALYTIQUE" if m.is_analytical else "optionnel")
            lines.append(f"  {m.source_name:30} → {m.standard_name:20} [{status}]")

        if self.missing_required:
            lines.append("")
            lines.append("COLONNES REQUISES MANQUANTES:")
            for col in self.missing_required:
                suggestions = self.suggestions.get(col, [])
                if suggestions:
                    lines.append(f"  {col} - Suggestions: {', '.join(suggestions[:3])}")
                else:
                    lines.append(f"  {col}")

        if self.unmapped_columns:
            lines.append("")
            lines.append(f"Colonnes non utilisées: {', '.join(self.unmapped_columns[:10])}")
            if len(self.unmapped_columns) > 10:
                lines.append(f"  ... et {len(self.unmapped_columns) - 10} autres")

        if self.analytical_columns_found:
            lines.append("")
            lines.append(f"Colonnes analytiques: {', '.join(self.analytical_columns_found)}")

        return "\n".join(lines)
