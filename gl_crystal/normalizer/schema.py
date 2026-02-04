"""
GL Crystal - Schéma Canonique
Définit la structure normalisée des données GL.

Le schéma canonique est le point d'entrée unique pour toutes les analyses.
Chaque GL, quel que soit son format d'origine, doit être normalisé vers ce schéma.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional, List
from enum import Enum


class ClassePCG(Enum):
    """Classes du Plan Comptable Général."""
    CAPITAUX = 1          # Comptes de capitaux
    IMMOBILISATIONS = 2   # Comptes d'immobilisations
    STOCKS = 3            # Comptes de stocks et en-cours
    TIERS = 4             # Comptes de tiers
    FINANCIERS = 5        # Comptes financiers
    CHARGES = 6           # Comptes de charges
    PRODUITS = 7          # Comptes de produits
    SPECIAUX = 8          # Comptes spéciaux


class NatureCompte(Enum):
    """Nature économique du compte."""
    BILAN = "bilan"           # Classes 1-5
    CHARGE = "charge"         # Classe 6
    PRODUIT = "produit"       # Classe 7
    SPECIAL = "special"       # Classe 8


class TypeContrepartie(Enum):
    """Type de contrepartie selon le certificat d'origine."""
    FOURNISSEUR = "401"       # Achat réel
    CLIENT = "411"            # Vente réelle
    BANQUE = "512"            # Paiement direct
    CAISSE = "530"            # Paiement espèces
    PROVISION = "488"         # Charge à payer / Produit à recevoir
    ETALEMENT = "486"         # Charge constatée d'avance
    ATTENTE = "471"           # Compte d'attente
    PERSONNEL = "421"         # Rémunérations dues
    ORGANISMES = "43"         # Organismes sociaux
    ETAT = "44"               # État et collectivités
    TRANSFERT = "79"          # Transfert de charges
    AUTRE = "autre"


@dataclass
class GLEntry:
    """
    Écriture GL normalisée - Schéma canonique.

    C'est la structure de base après normalisation, avant enrichissement.
    """
    # Identifiants
    date_ecriture: date
    piece: str

    # Journal
    journal_code: str
    journal_libelle: str

    # Compte
    compte_general: str
    compte_libelle: str
    compte_auxiliaire: Optional[str] = None

    # Analytique
    analytique: Optional[str] = None

    # Libellé et montants
    libelle_ecriture: str = ""
    debit: float = 0.0
    credit: float = 0.0

    # Métadonnées (générées)
    ligne_id: Optional[int] = None

    @property
    def montant_signe(self) -> float:
        """Montant signé: positif si débit, négatif si crédit."""
        return self.debit - self.credit

    @property
    def sens(self) -> str:
        """Sens de l'écriture: 'D' ou 'C'."""
        return 'D' if self.debit > self.credit else 'C'


@dataclass
class EnrichedEntry(GLEntry):
    """
    Écriture enrichie avec métadonnées calculées.

    L'enrichissement ajoute:
    - Classification PCG (classe, famille)
    - Contrepartie identifiée
    - Période comptable
    - Hash pour dédoublonnage
    """
    # Classification PCG
    classe_pcg: Optional[ClassePCG] = None
    famille: Optional[str] = None  # Racine à 3 chiffres (ex: "606")
    nature: Optional[NatureCompte] = None

    # Contrepartie (écritures liées par la même pièce)
    contrepartie_comptes: List[str] = field(default_factory=list)
    contrepartie_type: Optional[TypeContrepartie] = None

    # Période
    mois_comptable: Optional[str] = None  # Format "YYYY-MM"
    exercice: Optional[int] = None

    # Hash pour dédoublonnage
    hash_ecriture: Optional[str] = None

    @classmethod
    def from_gl_entry(cls, entry: GLEntry) -> 'EnrichedEntry':
        """Crée une EnrichedEntry à partir d'une GLEntry."""
        return cls(
            date_ecriture=entry.date_ecriture,
            piece=entry.piece,
            journal_code=entry.journal_code,
            journal_libelle=entry.journal_libelle,
            compte_general=entry.compte_general,
            compte_libelle=entry.compte_libelle,
            compte_auxiliaire=entry.compte_auxiliaire,
            analytique=entry.analytique,
            libelle_ecriture=entry.libelle_ecriture,
            debit=entry.debit,
            credit=entry.credit,
            ligne_id=entry.ligne_id,
        )


@dataclass
class GLSchema:
    """
    Schéma complet du GL normalisé et enrichi.

    Contient les métadonnées globales et la liste des écritures.
    """
    # Métadonnées
    source_file: str
    source_format: str  # "sage", "cegid", "quadratus", "ebp", "generic"
    date_extraction: date

    # Période couverte
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None
    exercice: Optional[int] = None

    # Statistiques
    nb_ecritures: int = 0
    nb_comptes: int = 0
    nb_journaux: int = 0
    nb_analytiques: int = 0

    # Validation
    is_equilibre: bool = True
    ecart_equilibre: float = 0.0
    colonnes_manquantes: List[str] = field(default_factory=list)

    # Données
    entries: List[EnrichedEntry] = field(default_factory=list)

    def validate_equilibre(self) -> bool:
        """Vérifie l'équilibre débit/crédit global."""
        total_debit = sum(e.debit for e in self.entries)
        total_credit = sum(e.credit for e in self.entries)
        self.ecart_equilibre = abs(total_debit - total_credit)
        self.is_equilibre = self.ecart_equilibre < 0.01
        return self.is_equilibre

    def validate_equilibre_par_piece(self) -> dict:
        """Vérifie l'équilibre par pièce comptable."""
        pieces = {}
        for entry in self.entries:
            if entry.piece not in pieces:
                pieces[entry.piece] = {'debit': 0.0, 'credit': 0.0}
            pieces[entry.piece]['debit'] += entry.debit
            pieces[entry.piece]['credit'] += entry.credit

        desequilibres = {}
        for piece, totaux in pieces.items():
            ecart = abs(totaux['debit'] - totaux['credit'])
            if ecart >= 0.01:
                desequilibres[piece] = ecart

        return desequilibres

    def get_comptes_uniques(self) -> set:
        """Retourne l'ensemble des comptes uniques."""
        return {e.compte_general for e in self.entries}

    def get_analytiques_uniques(self) -> set:
        """Retourne l'ensemble des codes analytiques uniques."""
        return {e.analytique for e in self.entries if e.analytique}

    def get_couples_compte_analytique(self) -> set:
        """Retourne l'ensemble des couples (compte, analytique)."""
        return {(e.compte_general, e.analytique) for e in self.entries}

    def compute_stats(self):
        """Calcule les statistiques globales."""
        self.nb_ecritures = len(self.entries)
        self.nb_comptes = len(self.get_comptes_uniques())
        self.nb_analytiques = len(self.get_analytiques_uniques())
        self.nb_journaux = len({e.journal_code for e in self.entries})

        if self.entries:
            dates = [e.date_ecriture for e in self.entries]
            self.date_debut = min(dates)
            self.date_fin = max(dates)
