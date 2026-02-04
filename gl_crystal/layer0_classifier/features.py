"""
GL Crystal - Extraction des Features de Classification

Le calcul clé : normalisation des noms propres.
Si l'entropie chute drastiquement après retrait des noms propres,
c'est que la diversité apparente était nominative.
"""

import re
import math
from collections import Counter
from typing import Dict, List, Optional, Tuple
import numpy as np

from ..normalizer.schema import EnrichedEntry


# Vocabulaire comptable standard (ne pas normaliser ces mots)
VOCABULAIRE_COMPTABLE = {
    # Opérations
    "LOYER", "SALAIRE", "FACTURE", "AVOIR", "REGUL", "REGULARISATION",
    "PROVISION", "AMORTISSEMENT", "DOTATION", "REPRISE",
    "VIREMENT", "PRELEVEMENT", "CHEQUE", "CARTE", "CB",
    "ABONNEMENT", "ASSURANCE", "HONORAIRES", "COTISATION",
    "ACHAT", "VENTE", "PRESTATION", "SERVICE",
    # Périodes
    "JANVIER", "FEVRIER", "MARS", "AVRIL", "MAI", "JUIN",
    "JUILLET", "AOUT", "SEPTEMBRE", "OCTOBRE", "NOVEMBRE", "DECEMBRE",
    "JAN", "FEV", "MAR", "AVR", "JUI", "JUL", "AOU", "SEP", "OCT", "NOV", "DEC",
    # Codes
    "REF", "NUM", "FAC", "BL", "OD", "AN", "EX",
    # Organismes
    "URSSAF", "RSI", "CPAM", "CAF", "MSA", "TRESOR", "IMPOT", "TVA",
    # Divers comptables
    "SOLDE", "REPORT", "EXTOURNE", "CONTREPASSATION", "ABT", "CCA", "PCA",
}


def normalize_proper_nouns(libelles: List[str]) -> List[str]:
    """
    Remplace les noms propres par un token générique.

    Heuristiques :
    1. Patterns connus : "M./MME/MR/MRS [NOM]", "FAM. [NOM]"
    2. Mots en majuscules > 3 lettres non dans le vocabulaire comptable
    3. Références numériques (n° facture, n° immo)

    Args:
        libelles: Liste des libellés bruts

    Returns:
        Liste des libellés normalisés
    """
    patterns = [
        # Noms de famille dans les libellés de facturation
        (r'\b(M\.|MME|MR|MRS|FAM\.?|FAMILLE)\s+[A-Z][A-Za-zÀ-ÿ\-]+', '[NOM_PROPRE]'),
        # Noms propres simples (mot capitalisé non comptable)
        (r'\b[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)*\b', _replace_if_not_comptable),
        # Références numériques (n° facture, n° immo, dates)
        (r'\b\d{4,}\b', '[REF_NUM]'),
        (r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', '[DATE]'),
    ]

    result = []
    for lib in libelles:
        if not lib:
            result.append('')
            continue

        normalized = str(lib).upper()

        # Applique les patterns
        for pattern, replacement in patterns:
            if callable(replacement):
                normalized = re.sub(pattern, replacement, normalized)
            else:
                normalized = re.sub(pattern, replacement, normalized)

        # Remplace les entités (mots en majuscules > 4 lettres non comptables)
        words = normalized.split()
        normalized_words = []
        for word in words:
            clean_word = re.sub(r'[^\w]', '', word)
            if (len(clean_word) > 4
                and clean_word.isupper()
                and clean_word not in VOCABULAIRE_COMPTABLE):
                normalized_words.append('[ENTITE]')
            else:
                normalized_words.append(word)

        result.append(' '.join(normalized_words))

    return result


def _replace_if_not_comptable(match) -> str:
    """Remplace un mot capitalisé s'il n'est pas comptable."""
    word = match.group().upper()
    if word in VOCABULAIRE_COMPTABLE:
        return match.group()
    return '[NOM_PROPRE]'


def compute_shannon_entropy(items: List[str]) -> float:
    """Calcule l'entropie de Shannon sur une liste d'items."""
    if not items:
        return 0.0

    counts = Counter(items)
    total = len(items)

    entropy = 0.0
    for count in counts.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)

    return entropy


def detect_proper_nouns_ratio(libelles: List[str]) -> float:
    """
    Détecte le ratio de tokens qui sont des noms propres.

    Returns:
        Ratio entre 0 et 1
    """
    if not libelles:
        return 0.0

    total_tokens = 0
    proper_noun_tokens = 0

    # Pattern pour détecter les noms propres
    proper_patterns = [
        r'\b(M\.|MME|MR|MRS|FAM\.?)\s+[A-Z][A-Za-zÀ-ÿ\-]+',
        r'\b[A-Z][a-zà-ÿ]{2,}(?:\s+[A-Z][a-zà-ÿ]+)*\b',
    ]

    for lib in libelles:
        if not lib:
            continue

        lib_upper = str(lib).upper()
        words = lib_upper.split()
        total_tokens += len(words)

        # Compte les mots qui semblent être des noms propres
        for word in words:
            clean = re.sub(r'[^\w]', '', word)
            if len(clean) > 3 and clean not in VOCABULAIRE_COMPTABLE:
                # Vérifie si c'est un mot capitalisé dans l'original
                if re.search(r'[A-Z][a-z]', str(lib)):
                    proper_noun_tokens += 1

    return proper_noun_tokens / total_tokens if total_tokens > 0 else 0.0


def detect_asset_references_ratio(libelles: List[str]) -> float:
    """
    Détecte le ratio de libellés contenant des références d'immobilisation.

    Patterns : IMMO-XXXX, N°XXXX, REF:XXXX, codes d'actifs
    """
    if not libelles:
        return 0.0

    patterns = [
        r'IMMO[\.:\-\s]?\d+',
        r'N[°O]?\s*\d{3,}',
        r'REF[\.:\-\s]?\d+',
        r'ACTIF\s*\d+',
        r'DOT\.\s*\d+',  # Dotation numérotée
    ]

    count = 0
    for lib in libelles:
        if not lib:
            continue
        lib_upper = str(lib).upper()
        for pattern in patterns:
            if re.search(pattern, lib_upper):
                count += 1
                break

    return count / len(libelles)


def detect_mirror_entries_ratio(
    montants: List[float],
    analytiques: List[str]
) -> float:
    """
    Détecte le ratio d'écritures miroirs (même montant, sens opposé).

    Les ventilations inter-sites ont ce pattern.
    """
    if not montants or len(montants) < 2:
        return 0.0

    # Cherche des montants opposés sur différents analytiques
    montants_abs = [abs(m) for m in montants]
    montant_counts = Counter(montants_abs)

    # Montants qui apparaissent plusieurs fois (potentielles ventilations)
    mirror_candidates = sum(
        count for montant, count in montant_counts.items()
        if count >= 2 and montant > 0
    )

    return mirror_candidates / len(montants)


def compute_temporal_regularity(
    mois_list: List[str],
    montants: List[float]
) -> float:
    """
    Mesure la régularité temporelle des écritures.

    1.0 = parfaitement régulier (1 écriture/mois, même montant)
    0.0 = irrégulier
    """
    if not mois_list or not montants:
        return 0.0

    # Agrège par mois
    mois_montants = {}
    for mois, montant in zip(mois_list, montants):
        if mois:
            if mois not in mois_montants:
                mois_montants[mois] = []
            mois_montants[mois].append(abs(montant))

    if len(mois_montants) < 2:
        return 0.5  # Pas assez de mois pour juger

    # Calcule le CV des totaux mensuels
    monthly_totals = [sum(m) for m in mois_montants.values()]
    mean_total = np.mean(monthly_totals)

    if mean_total == 0:
        return 0.0

    cv = np.std(monthly_totals) / mean_total

    # Régularité = inverse du CV, normalisé entre 0 et 1
    # CV = 0 → régularité = 1
    # CV > 1 → régularité → 0
    regularity = max(0, 1 - min(cv, 1))

    # Bonus si présence tous les mois (12 mois)
    if len(mois_montants) >= 11:
        regularity = min(1.0, regularity + 0.1)

    return float(regularity)


def extract_classification_features(
    ecritures: List[EnrichedEntry],
    couple_id: str
) -> Dict:
    """
    Extrait les features de classification pour un couple.

    Args:
        ecritures: Liste des écritures du couple
        couple_id: Identifiant du couple (compte|analytique)

    Returns:
        Dict de features pour la classification
    """
    if not ecritures:
        return {}

    # Extractions basiques
    libelles = [e.libelle_ecriture for e in ecritures if e.libelle_ecriture]
    montants = [e.montant_signe for e in ecritures]
    montants_abs = [abs(m) for m in montants]
    mois_list = [e.mois_comptable for e in ecritures if e.mois_comptable]
    journaux = [e.journal_code for e in ecritures if e.journal_code]
    analytiques = [e.analytique for e in ecritures if e.analytique]

    # Contreparties
    contreparties = []
    for e in ecritures:
        if e.contrepartie_comptes:
            contreparties.extend(e.contrepartie_comptes)

    # Entropie brute vs normalisée
    shannon_brut = compute_shannon_entropy(libelles) if libelles else 0.0
    libelles_normalises = normalize_proper_nouns(libelles)
    shannon_normalise = compute_shannon_entropy(libelles_normalises)

    # CV des montants
    mean_montant = np.mean(montants_abs) if montants_abs else 0
    cv_montants = (np.std(montants_abs) / mean_montant
                   if mean_montant > 0 else 0)

    # Régularité temporelle
    regularite = compute_temporal_regularity(mois_list, montants)

    # Ratios de détection
    pct_noms_propres = detect_proper_nouns_ratio(libelles)
    pct_ref_immo = detect_asset_references_ratio(libelles)
    ratio_miroirs = detect_mirror_entries_ratio(montants, analytiques)

    # Classe et famille
    first_entry = ecritures[0]
    classe = first_entry.compte_general[0] if first_entry.compte_general else ''
    famille = first_entry.compte_general[:3] if len(first_entry.compte_general) >= 3 else ''

    return {
        # Identité
        'couple_id': couple_id,
        'compte_general': first_entry.compte_general,
        'analytique': first_entry.analytique,
        'classe': classe,
        'famille': famille,
        'nb_ecritures': len(ecritures),
        'volume_total': sum(montants_abs),

        # Entropie
        'shannon_brut': shannon_brut,
        'shannon_normalise': shannon_normalise,
        'delta_shannon': shannon_brut - shannon_normalise,

        # Diversité des sources
        'nb_journaux': len(set(journaux)),
        'nb_contreparties': len(set(contreparties)),
        'nb_libelles_uniques': len(set(libelles)),

        # Pattern des montants
        'cv_montants': float(cv_montants),
        'mean_montant': float(mean_montant),

        # Temporalité
        'nb_mois': len(set(mois_list)),
        'regularite_temporelle': regularite,

        # Détecteurs spécifiques
        'ratio_miroirs': ratio_miroirs,
        'pct_noms_propres': pct_noms_propres,
        'pct_ref_immo': pct_ref_immo,
    }
