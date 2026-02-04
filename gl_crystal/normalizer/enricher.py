"""
GL Crystal - Enricher
Enrichissement automatique des écritures GL.

L'enrichissement ajoute:
- Classification PCG (classe, famille, nature)
- Identification des contreparties (certificat d'origine)
- Période comptable (mois, exercice)
- Hash pour dédoublonnage

Le principe clé: la contrepartie est un certificat d'origine.
"""

import hashlib
from collections import defaultdict
from typing import Dict, List, Optional, Set

from .schema import (
    GLSchema, GLEntry, EnrichedEntry,
    ClassePCG, NatureCompte, TypeContrepartie
)


class GLEnricher:
    """
    Enrichit les écritures GL avec les métadonnées calculées.

    La méthode principale est enrich() qui transforme un GLSchema
    contenant des GLEntry en un GLSchema contenant des EnrichedEntry.
    """

    def __init__(self):
        self.stats = {
            'entries_enriched': 0,
            'contreparties_found': 0,
            'pieces_processed': 0,
        }

    def enrich(self, schema: GLSchema) -> GLSchema:
        """
        Enrichit toutes les écritures d'un GLSchema.

        Args:
            schema: GLSchema avec des GLEntry ou EnrichedEntry

        Returns:
            GLSchema avec des EnrichedEntry enrichies
        """
        # Convertit en EnrichedEntry si nécessaire
        enriched_entries = []
        for entry in schema.entries:
            if isinstance(entry, EnrichedEntry):
                enriched = entry
            else:
                enriched = EnrichedEntry.from_gl_entry(entry)
            enriched_entries.append(enriched)

        # Étape 1: Classification PCG
        for entry in enriched_entries:
            self._classify_pcg(entry)
            self._compute_period(entry)
            self._compute_hash(entry)

        # Étape 2: Identification des contreparties (nécessite toutes les écritures)
        self._identify_contreparties(enriched_entries)

        # Met à jour le schéma
        schema.entries = enriched_entries
        self.stats['entries_enriched'] = len(enriched_entries)

        return schema

    def _classify_pcg(self, entry: EnrichedEntry):
        """
        Classifie le compte selon le PCG.

        Le premier chiffre donne la classe.
        Les 3 premiers chiffres donnent la famille.
        """
        compte = entry.compte_general.strip()
        if not compte or not compte[0].isdigit():
            return

        # Classe (premier chiffre)
        try:
            classe_num = int(compte[0])
            entry.classe_pcg = ClassePCG(classe_num)
        except (ValueError, KeyError):
            pass

        # Famille (3 premiers chiffres)
        if len(compte) >= 3:
            entry.famille = compte[:3]

        # Nature économique
        if entry.classe_pcg:
            if entry.classe_pcg.value in [1, 2, 3, 4, 5]:
                entry.nature = NatureCompte.BILAN
            elif entry.classe_pcg.value == 6:
                entry.nature = NatureCompte.CHARGE
            elif entry.classe_pcg.value == 7:
                entry.nature = NatureCompte.PRODUIT
            elif entry.classe_pcg.value == 8:
                entry.nature = NatureCompte.SPECIAL

    def _compute_period(self, entry: EnrichedEntry):
        """Calcule la période comptable (mois et exercice)."""
        if entry.date_ecriture:
            entry.mois_comptable = entry.date_ecriture.strftime('%Y-%m')
            entry.exercice = entry.date_ecriture.year

    def _compute_hash(self, entry: EnrichedEntry):
        """
        Calcule un hash unique pour l'écriture.

        Utilisé pour le dédoublonnage.
        """
        components = [
            str(entry.date_ecriture),
            entry.journal_code,
            entry.compte_general,
            entry.libelle_ecriture,
            f"{entry.debit:.2f}",
            f"{entry.credit:.2f}",
            entry.piece,
        ]
        content = '|'.join(components)
        entry.hash_ecriture = hashlib.md5(content.encode()).hexdigest()[:12]

    def _identify_contreparties(self, entries: List[EnrichedEntry]):
        """
        Identifie les contreparties de chaque écriture.

        La contrepartie est le compte "de l'autre côté" dans la même pièce.
        C'est le certificat d'origine qui qualifie la nature économique.

        Pour une écriture de charge (classe 6):
        - 401 = achat réel (fournisseur)
        - 512 = paiement direct (banque)
        - 488 = charge à payer (provision)
        - 486 = charge constatée d'avance (étalement)
        - 471 = compte d'attente (à investiguer)
        """
        # Groupe les écritures par pièce
        pieces: Dict[str, List[EnrichedEntry]] = defaultdict(list)
        for entry in entries:
            if entry.piece:
                pieces[entry.piece].append(entry)

        self.stats['pieces_processed'] = len(pieces)

        # Pour chaque pièce, identifie les contreparties
        for piece, piece_entries in pieces.items():
            if len(piece_entries) < 2:
                continue

            # Sépare débit et crédit
            debits = [e for e in piece_entries if e.debit > 0]
            credits = [e for e in piece_entries if e.credit > 0]

            # Pour chaque écriture au débit, sa contrepartie est au crédit
            for entry in debits:
                entry.contrepartie_comptes = [e.compte_general for e in credits]
                entry.contrepartie_type = self._determine_type_contrepartie(
                    credits, entry
                )
                if entry.contrepartie_comptes:
                    self.stats['contreparties_found'] += 1

            # Pour chaque écriture au crédit, sa contrepartie est au débit
            for entry in credits:
                entry.contrepartie_comptes = [e.compte_general for e in debits]
                entry.contrepartie_type = self._determine_type_contrepartie(
                    debits, entry
                )
                if entry.contrepartie_comptes:
                    self.stats['contreparties_found'] += 1

    def _determine_type_contrepartie(
        self,
        contreparties: List[EnrichedEntry],
        entry: EnrichedEntry
    ) -> Optional[TypeContrepartie]:
        """
        Détermine le type de contrepartie dominant.

        Le type de contrepartie est le "certificat d'origine" de l'écriture.
        """
        if not contreparties:
            return None

        # Compte les types par montant
        type_amounts: Dict[TypeContrepartie, float] = defaultdict(float)

        for cp in contreparties:
            compte = cp.compte_general
            montant = cp.debit + cp.credit

            cp_type = self._get_type_from_compte(compte)
            type_amounts[cp_type] += montant

        # Retourne le type dominant (montant le plus élevé)
        if type_amounts:
            return max(type_amounts, key=type_amounts.get)
        return None

    def _get_type_from_compte(self, compte: str) -> TypeContrepartie:
        """Détermine le type de contrepartie depuis un numéro de compte."""
        if not compte:
            return TypeContrepartie.AUTRE

        # Préfixes pour les types principaux
        prefixes = [
            ('401', TypeContrepartie.FOURNISSEUR),
            ('411', TypeContrepartie.CLIENT),
            ('421', TypeContrepartie.PERSONNEL),
            ('431', TypeContrepartie.ORGANISMES),
            ('437', TypeContrepartie.ORGANISMES),
            ('43', TypeContrepartie.ORGANISMES),
            ('44', TypeContrepartie.ETAT),
            ('471', TypeContrepartie.ATTENTE),
            ('486', TypeContrepartie.ETALEMENT),
            ('487', TypeContrepartie.ETALEMENT),
            ('488', TypeContrepartie.PROVISION),
            ('512', TypeContrepartie.BANQUE),
            ('530', TypeContrepartie.CAISSE),
            ('531', TypeContrepartie.CAISSE),
            ('79', TypeContrepartie.TRANSFERT),
        ]

        for prefix, type_cp in prefixes:
            if compte.startswith(prefix):
                return type_cp

        return TypeContrepartie.AUTRE

    def get_stats(self) -> Dict:
        """Retourne les statistiques d'enrichissement."""
        return self.stats.copy()


# Templates de contrepartie par famille de comptes
# Ce sont les patterns attendus selon la nature de la charge/produit

CONTREPARTIE_TEMPLATES = {
    # Charges de personnel
    '641': {TypeContrepartie.PERSONNEL, TypeContrepartie.ORGANISMES,
            TypeContrepartie.BANQUE},
    '645': {TypeContrepartie.ORGANISMES, TypeContrepartie.BANQUE},
    '647': {TypeContrepartie.PERSONNEL, TypeContrepartie.BANQUE},

    # Charges externes
    '606': {TypeContrepartie.FOURNISSEUR, TypeContrepartie.BANQUE},
    '607': {TypeContrepartie.FOURNISSEUR, TypeContrepartie.BANQUE},
    '611': {TypeContrepartie.FOURNISSEUR, TypeContrepartie.PROVISION},
    '613': {TypeContrepartie.FOURNISSEUR, TypeContrepartie.PROVISION,
            TypeContrepartie.ETALEMENT},
    '615': {TypeContrepartie.FOURNISSEUR},
    '616': {TypeContrepartie.FOURNISSEUR, TypeContrepartie.ETALEMENT},
    '617': {TypeContrepartie.FOURNISSEUR},
    '618': {TypeContrepartie.FOURNISSEUR},
    '622': {TypeContrepartie.FOURNISSEUR, TypeContrepartie.PERSONNEL},
    '623': {TypeContrepartie.FOURNISSEUR},
    '625': {TypeContrepartie.FOURNISSEUR, TypeContrepartie.PERSONNEL},
    '626': {TypeContrepartie.FOURNISSEUR, TypeContrepartie.BANQUE},
    '627': {TypeContrepartie.FOURNISSEUR, TypeContrepartie.BANQUE},

    # Impôts et taxes
    '631': {TypeContrepartie.ETAT},
    '633': {TypeContrepartie.ETAT, TypeContrepartie.PROVISION},
    '635': {TypeContrepartie.ETAT, TypeContrepartie.PROVISION},
    '637': {TypeContrepartie.ETAT},

    # Charges financières
    '661': {TypeContrepartie.BANQUE},
    '666': {TypeContrepartie.BANQUE},

    # Dotations
    '681': {TypeContrepartie.PROVISION},
    '686': {TypeContrepartie.PROVISION},
    '687': {TypeContrepartie.PROVISION},

    # Produits d'exploitation
    '706': {TypeContrepartie.CLIENT},
    '707': {TypeContrepartie.CLIENT},
    '708': {TypeContrepartie.CLIENT},
    '709': {TypeContrepartie.CLIENT},

    # Reprises
    '781': {TypeContrepartie.PROVISION},
    '786': {TypeContrepartie.PROVISION},
    '787': {TypeContrepartie.PROVISION},
}


def check_contrepartie_conformity(
    entry: EnrichedEntry,
    templates: Dict = CONTREPARTIE_TEMPLATES
) -> bool:
    """
    Vérifie si la contrepartie d'une écriture est conforme au template.

    Args:
        entry: Écriture enrichie avec contrepartie identifiée
        templates: Dictionnaire des templates par famille

    Returns:
        True si conforme, False si atypique
    """
    if not entry.famille or not entry.contrepartie_type:
        return True  # Pas de vérification possible

    expected = templates.get(entry.famille)
    if not expected:
        return True  # Pas de template défini

    return entry.contrepartie_type in expected
