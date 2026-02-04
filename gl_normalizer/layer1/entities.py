"""
gl_normalizer/layer1/entities.py
Extraction d'entités nommées (NER)

Extraction hiérarchique:
1. Regex compilés (rapide, patterns connus)
2. spaCy NER (si disponible, entités génériques)
3. Fuzzy matching (pour noms de tiers)

Entités extraites:
- MONTANT: Valeurs numériques avec devise
- DATE: Dates et périodes
- REFERENCE: N° facture, bon commande, etc.
- TIERS: Noms fournisseurs/clients
- LIEU: Sites, agences, pays
"""

import re
from typing import List, Optional, Tuple, Dict, Any
from .base import ExtractedEntity, EntityType


# =============================================================================
# PATTERNS REGEX COMPILÉS
# =============================================================================

# Montants: 1234.56€, 1 234,56 EUR, etc.
AMOUNT_PATTERNS = [
    # Format français: 1 234,56 €
    re.compile(r'(\d{1,3}(?:\s?\d{3})*(?:[,\.]\d{2})?)\s*(?:€|EUR|EUROS?)', re.IGNORECASE),
    # Format international: 1,234.56 EUR
    re.compile(r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:€|EUR|EUROS?)', re.IGNORECASE),
    # Montant seul avec devise implicite
    re.compile(r'(?:MONTANT|MT|TOTAL)[\s:]*(\d+(?:[,\.]\d{2})?)', re.IGNORECASE),
]

# Dates: 01/01/2024, janvier 2024, Q1 2024
DATE_PATTERNS = [
    # Date complète: 01/01/2024 ou 01-01-2024
    re.compile(r'\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b'),
    # Mois année: janvier 2024, jan 2024
    re.compile(r'\b((?:JANVIER|FEVRIER|MARS|AVRIL|MAI|JUIN|JUILLET|AOUT|SEPTEMBRE|OCTOBRE|NOVEMBRE|DECEMBRE|'
               r'JAN|FEV|MAR|AVR|JUI|JUL|AOU|SEP|OCT|NOV|DEC)\.?\s*\d{2,4})\b', re.IGNORECASE),
    # Période: Q1 2024, T1 2024
    re.compile(r'\b([QT][1-4]\s*\d{2,4})\b', re.IGNORECASE),
    # Année seule en contexte
    re.compile(r'\b(?:EXERCICE|EX|ANNEE)\s*(\d{4})\b', re.IGNORECASE),
    # Mois abrégé: 01/2024
    re.compile(r'\b(\d{1,2}/\d{4})\b'),
]

# Références: FA-2024-0123, BC-123456, etc.
REFERENCE_PATTERNS = [
    # Facture: FA-2024-001, FAC/2024/001
    re.compile(r'\b(FA[C]?[-/]?\d{4}[-/]?\d{3,6})\b', re.IGNORECASE),
    # Bon de commande: BC-123456
    re.compile(r'\b(BC[-/]?\d{4,8})\b', re.IGNORECASE),
    # Avoir: AV-2024-001
    re.compile(r'\b(AV[-/]?\d{4}[-/]?\d{3,6})\b', re.IGNORECASE),
    # Numéro de pièce générique
    re.compile(r'\b(?:PIECE|PCE|N°|NO|NUM)[\s:]*(\d{4,10})\b', re.IGNORECASE),
    # Code alphanumérique structuré
    re.compile(r'\b([A-Z]{2,4}[-/]\d{4}[-/]\d{3,6})\b'),
    # Référence client/fournisseur
    re.compile(r'\b(?:REF|REFERENCE)[\s:]*([A-Z0-9\-]{4,15})\b', re.IGNORECASE),
]

# Tiers: Patterns pour détecter noms d'entreprises
TIERS_PATTERNS = [
    # Suffixes entreprise
    re.compile(r'\b([A-Z][A-Z0-9\s]{2,30}(?:SARL|SAS|SA|EURL|SCI|SASU|SCOP|GIE|SNC))\b', re.IGNORECASE),
    # Après "de" ou "pour"
    re.compile(r'(?:DE|POUR|CHEZ|CLIENT|FOURNISSEUR)[\s:]+([A-Z][A-Z0-9\s&\'-]{2,30})', re.IGNORECASE),
    # Nom propre capitalisé (2+ mots)
    re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'),
]

# Lieux
LIEU_PATTERNS = [
    # Agence/Site
    re.compile(r'(?:AGENCE|SITE|MAGASIN|DEPOT)[\s:]+([A-Z][A-Z0-9\s]{2,20})', re.IGNORECASE),
    # Ville connue (liste réduite)
    re.compile(r'\b(PARIS|LYON|MARSEILLE|TOULOUSE|BORDEAUX|LILLE|NANTES|STRASBOURG)\b', re.IGNORECASE),
]


# =============================================================================
# EXTRACTION FUNCTIONS
# =============================================================================

def extract_amount(text: str) -> List[ExtractedEntity]:
    """
    Extrait les montants d'un libellé.

    Args:
        text: Libellé à analyser

    Returns:
        Liste d'ExtractedEntity de type MONTANT
    """
    entities = []

    for pattern in AMOUNT_PATTERNS:
        for match in pattern.finditer(text):
            value_str = match.group(1)
            # Normaliser le montant
            normalized = _normalize_amount(value_str)

            entities.append(ExtractedEntity(
                entity_type=EntityType.MONTANT,
                value=match.group(0),
                normalized=str(normalized) if normalized else value_str,
                start=match.start(),
                end=match.end(),
                confidence=0.9 if normalized else 0.6,
                source="regex",
            ))

    return _dedupe_entities(entities)


def extract_date(text: str) -> List[ExtractedEntity]:
    """
    Extrait les dates et périodes d'un libellé.

    Args:
        text: Libellé à analyser

    Returns:
        Liste d'ExtractedEntity de type DATE
    """
    entities = []

    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1)
            normalized = _normalize_date(value)

            entities.append(ExtractedEntity(
                entity_type=EntityType.DATE,
                value=match.group(0),
                normalized=normalized,
                start=match.start(),
                end=match.end(),
                confidence=0.85,
                source="regex",
            ))

    return _dedupe_entities(entities)


def extract_reference(text: str) -> List[ExtractedEntity]:
    """
    Extrait les références (factures, BC, etc.) d'un libellé.

    Args:
        text: Libellé à analyser

    Returns:
        Liste d'ExtractedEntity de type REFERENCE
    """
    entities = []

    for pattern in REFERENCE_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1) if match.lastindex else match.group(0)

            # Déterminer le type de référence
            ref_type = _classify_reference(value)

            entities.append(ExtractedEntity(
                entity_type=EntityType.REFERENCE,
                value=value,
                normalized=value.upper().replace(" ", ""),
                start=match.start(),
                end=match.end(),
                confidence=0.85,
                source="regex",
            ))

    return _dedupe_entities(entities)


def extract_tiers(text: str, known_tiers: Optional[List[str]] = None) -> List[ExtractedEntity]:
    """
    Extrait les noms de tiers (fournisseurs/clients).

    Args:
        text: Libellé à analyser
        known_tiers: Liste optionnelle de tiers connus pour matching

    Returns:
        Liste d'ExtractedEntity de type TIERS
    """
    entities = []

    # 1. Patterns regex
    for pattern in TIERS_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1) if match.lastindex else match.group(0)

            # Filtrer les faux positifs
            if _is_valid_tiers(value):
                entities.append(ExtractedEntity(
                    entity_type=EntityType.TIERS,
                    value=value,
                    normalized=value.strip().upper(),
                    start=match.start(),
                    end=match.end(),
                    confidence=0.7,
                    source="regex",
                ))

    # 2. Fuzzy matching contre tiers connus
    if known_tiers:
        fuzzy_matches = _fuzzy_match_tiers(text, known_tiers)
        entities.extend(fuzzy_matches)

    return _dedupe_entities(entities)


def extract_lieu(text: str) -> List[ExtractedEntity]:
    """
    Extrait les lieux (sites, agences, villes).

    Args:
        text: Libellé à analyser

    Returns:
        Liste d'ExtractedEntity de type LIEU
    """
    entities = []

    for pattern in LIEU_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1) if match.lastindex else match.group(0)

            entities.append(ExtractedEntity(
                entity_type=EntityType.LIEU,
                value=value,
                normalized=value.strip().upper(),
                start=match.start(),
                end=match.end(),
                confidence=0.75,
                source="regex",
            ))

    return _dedupe_entities(entities)


def extract_entities(text: str, known_tiers: Optional[List[str]] = None) -> List[ExtractedEntity]:
    """
    Extrait toutes les entités d'un libellé.

    Combine tous les extracteurs dans l'ordre optimal.

    Args:
        text: Libellé à analyser
        known_tiers: Liste optionnelle de tiers connus

    Returns:
        Liste de toutes les ExtractedEntity
    """
    if not text or not text.strip():
        return []

    all_entities = []

    # Ordre: référence → montant → date → tiers → lieu
    # (du plus spécifique au plus générique)
    all_entities.extend(extract_reference(text))
    all_entities.extend(extract_amount(text))
    all_entities.extend(extract_date(text))
    all_entities.extend(extract_tiers(text, known_tiers))
    all_entities.extend(extract_lieu(text))

    # Trier par position
    all_entities.sort(key=lambda e: e.start)

    return all_entities


# =============================================================================
# SPACY NER (OPTIONNEL)
# =============================================================================

_spacy_nlp = None
_spacy_available = None


def is_spacy_available() -> bool:
    """Vérifie si spaCy est disponible."""
    global _spacy_available
    if _spacy_available is None:
        try:
            import spacy
            _spacy_available = True
        except ImportError:
            _spacy_available = False
    return _spacy_available


def _get_spacy_nlp():
    """Charge le modèle spaCy français (lazy loading)."""
    global _spacy_nlp
    if _spacy_nlp is None and is_spacy_available():
        try:
            import spacy
            # Essayer le modèle moyen, sinon le petit
            try:
                _spacy_nlp = spacy.load("fr_core_news_md")
            except OSError:
                try:
                    _spacy_nlp = spacy.load("fr_core_news_sm")
                except OSError:
                    _spacy_nlp = False  # Marquer comme indisponible
        except Exception:
            _spacy_nlp = False
    return _spacy_nlp if _spacy_nlp and _spacy_nlp is not False else None


def extract_with_spacy(text: str) -> List[ExtractedEntity]:
    """
    Extrait les entités avec spaCy NER.

    Args:
        text: Libellé à analyser

    Returns:
        Liste d'ExtractedEntity (vide si spaCy indisponible)
    """
    nlp = _get_spacy_nlp()
    if nlp is None:
        return []

    entities = []
    doc = nlp(text)

    # Mapping labels spaCy → EntityType
    label_mapping = {
        "PER": EntityType.TIERS,
        "ORG": EntityType.TIERS,
        "LOC": EntityType.LIEU,
        "GPE": EntityType.LIEU,
        "MONEY": EntityType.MONTANT,
        "DATE": EntityType.DATE,
    }

    for ent in doc.ents:
        if ent.label_ in label_mapping:
            entities.append(ExtractedEntity(
                entity_type=label_mapping[ent.label_],
                value=ent.text,
                normalized=ent.text.upper(),
                start=ent.start_char,
                end=ent.end_char,
                confidence=0.75,  # spaCy confidence générique
                source="spacy",
            ))

    return entities


# =============================================================================
# HELPERS
# =============================================================================

def _normalize_amount(value_str: str) -> Optional[float]:
    """Normalise un montant en float."""
    try:
        # Retirer les espaces
        cleaned = value_str.replace(" ", "").replace("\u00a0", "")
        # Gérer le format français (virgule décimale)
        if "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        elif "," in cleaned and "." in cleaned:
            # Format 1,234.56 → retirer les virgules
            cleaned = cleaned.replace(",", "")
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def _normalize_date(value: str) -> str:
    """Normalise une date/période."""
    # Mapping mois
    mois_map = {
        "JANVIER": "01", "JAN": "01",
        "FEVRIER": "02", "FEV": "02",
        "MARS": "03", "MAR": "03",
        "AVRIL": "04", "AVR": "04",
        "MAI": "05",
        "JUIN": "06", "JUI": "06",
        "JUILLET": "07", "JUL": "07",
        "AOUT": "08", "AOU": "08",
        "SEPTEMBRE": "09", "SEP": "09",
        "OCTOBRE": "10", "OCT": "10",
        "NOVEMBRE": "11", "NOV": "11",
        "DECEMBRE": "12", "DEC": "12",
    }

    upper = value.upper().strip()

    # Essayer de normaliser mois + année
    for mois, num in mois_map.items():
        if mois in upper:
            # Extraire l'année
            year_match = re.search(r'(\d{4})', upper)
            if year_match:
                return f"{year_match.group(1)}-{num}"

    return upper


def _classify_reference(value: str) -> str:
    """Classifie le type de référence."""
    upper = value.upper()
    if upper.startswith(("FA", "FAC")):
        return "FACTURE"
    elif upper.startswith(("BC", "BON")):
        return "BON_COMMANDE"
    elif upper.startswith("AV"):
        return "AVOIR"
    else:
        return "AUTRE"


def _is_valid_tiers(value: str) -> bool:
    """Vérifie si une extraction est un tiers valide."""
    if not value or len(value) < 3:
        return False

    # Filtrer les mots communs
    stopwords = {
        "JANVIER", "FEVRIER", "MARS", "AVRIL", "MAI", "JUIN",
        "JUILLET", "AOUT", "SEPTEMBRE", "OCTOBRE", "NOVEMBRE", "DECEMBRE",
        "TOTAL", "MONTANT", "SOLDE", "FACTURE", "AVOIR", "REGLEMENT",
        "VIREMENT", "CHEQUE", "PAIEMENT", "ENCAISSEMENT",
    }

    if value.upper().strip() in stopwords:
        return False

    return True


def _fuzzy_match_tiers(text: str, known_tiers: List[str], threshold: int = 80) -> List[ExtractedEntity]:
    """
    Matching fuzzy contre une liste de tiers connus.

    Args:
        text: Libellé
        known_tiers: Liste des noms de tiers connus
        threshold: Score minimum (0-100)

    Returns:
        Liste d'ExtractedEntity matchées
    """
    entities = []

    try:
        from rapidfuzz import fuzz, process
    except ImportError:
        # Fallback: matching exact simple
        text_upper = text.upper()
        for tiers in known_tiers:
            if tiers.upper() in text_upper:
                start = text_upper.find(tiers.upper())
                entities.append(ExtractedEntity(
                    entity_type=EntityType.TIERS,
                    value=tiers,
                    normalized=tiers.upper(),
                    start=start,
                    end=start + len(tiers),
                    confidence=1.0,
                    source="exact",
                ))
        return entities

    # Découper le texte en segments
    words = text.split()
    for i in range(len(words)):
        for j in range(i + 1, min(i + 5, len(words) + 1)):  # Max 4 mots
            segment = " ".join(words[i:j])
            if len(segment) < 3:
                continue

            # Chercher le meilleur match
            result = process.extractOne(segment, known_tiers, scorer=fuzz.token_sort_ratio)
            if result and result[1] >= threshold:
                matched_tiers, score, _ = result
                entities.append(ExtractedEntity(
                    entity_type=EntityType.TIERS,
                    value=segment,
                    normalized=matched_tiers.upper(),
                    start=text.find(segment),
                    end=text.find(segment) + len(segment),
                    confidence=score / 100.0,
                    source="fuzzy",
                ))

    return entities


def _dedupe_entities(entities: List[ExtractedEntity]) -> List[ExtractedEntity]:
    """
    Déduplique les entités qui se chevauchent.

    Garde l'entité avec la meilleure confiance.
    """
    if not entities:
        return []

    # Trier par position puis confiance décroissante
    sorted_entities = sorted(entities, key=lambda e: (e.start, -e.confidence))

    result = []
    for entity in sorted_entities:
        # Vérifier le chevauchement avec les entités déjà gardées
        overlaps = False
        for kept in result:
            if (entity.start < kept.end and entity.end > kept.start and
                entity.entity_type == kept.entity_type):
                overlaps = True
                break

        if not overlaps:
            result.append(entity)

    return result
