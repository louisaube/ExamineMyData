"""
gl_normalizer/layer1/intents.py
Classification d'intention et type d'opération

Détecte:
- Intent: REGULARISATION, EXTOURNE, PROVISION, CLOTURE, etc.
- OperationType: ACHAT, VENTE, SALAIRE, etc.
- Récurrence: Détection de patterns récurrents

Basé sur des patterns de mots-clés pondérés.
"""

import re
from typing import Tuple, List, Dict, Optional
from .base import Intent, OperationType


# =============================================================================
# PATTERNS D'INTENTION
# =============================================================================

INTENT_PATTERNS: Dict[Intent, List[Tuple[str, float]]] = {
    Intent.REGULARISATION: [
        (r'\bREGUL', 1.0),
        (r'\bREGULARISATION', 1.0),
        (r'\bCORRECTION', 0.9),
        (r'\bCORRECTIF', 0.9),
        (r'\bAJUSTEMENT', 0.8),
        (r'\bRECTIFICATIF', 0.9),
        (r'\bMISE\s*A\s*JOUR', 0.7),
        (r'\bOD\s*REGUL', 1.0),
    ],
    Intent.EXTOURNE: [
        (r'\bEXTOURNE', 1.0),
        (r'\bANNULATION', 0.95),
        (r'\bANNULE', 0.9),
        (r'\bCONTREPASSATION', 1.0),
        (r'\bSTORNO', 1.0),
        (r'\bANNUL\b', 0.85),
    ],
    Intent.PROVISION: [
        (r'\bPROVISION', 1.0),
        (r'\bDOTATION', 0.9),
        (r'\bREPRISE\s*(?:DE\s*)?PROVISION', 1.0),
        (r'\bDAP\b', 0.85),
        (r'\bPROV\b', 0.8),
    ],
    Intent.CLOTURE: [
        (r'\bCLOTURE', 1.0),
        (r'\bCLOT\b', 0.8),
        (r'\bFIN\s*D[E\']?\s*EXERCICE', 1.0),
        (r'\bAFFECTATION\s*RESULTAT', 0.95),
        (r'\bA\s*NOUVEAU', 0.9),
        (r'\bOUVERTURE', 0.85),
    ],
    Intent.INTERCO: [
        (r'\bINTERCO', 1.0),
        (r'\bINTER[- ]?COMPAGNIE', 1.0),
        (r'\bINTRA[- ]?GROUPE', 1.0),
        (r'\bGROUPE\b.*\bFACTURE', 0.8),
        (r'\bREFACTURATION', 0.85),
        (r'\bMANAGEMENT\s*FEES?', 0.9),
    ],
    Intent.MANUEL: [
        (r'\bMANUEL', 0.9),
        (r'\bOD\b(?!\s*REGUL)', 0.85),  # OD mais pas OD REGUL
        (r'\bECRITURE\s*MANUELLE', 1.0),
        (r'\bSAISIE\s*MANUELLE', 1.0),
    ],
    Intent.AUTOMATIQUE: [
        (r'\bAUTOMATIQUE', 0.9),
        (r'\bAUTO\b', 0.7),
        (r'\bINTERFACE', 0.8),
        (r'\bIMPORT', 0.75),
        (r'\bBATCH', 0.8),
    ],
}

# =============================================================================
# PATTERNS TYPE D'OPÉRATION
# =============================================================================

OPERATION_PATTERNS: Dict[OperationType, List[Tuple[str, float]]] = {
    OperationType.ACHAT: [
        (r'\bACHAT', 1.0),
        (r'\bFOURNISSEUR', 0.9),
        (r'\bFACTURE\s*(?:FOURNISSEUR|FOURN|FRN)', 1.0),
        (r'\bFA\s*FRN', 0.95),
        (r'\bAPPRO', 0.8),
        (r'\bCOMMANDE', 0.7),
    ],
    OperationType.VENTE: [
        (r'\bVENTE', 1.0),
        (r'\bCLIENT', 0.9),
        (r'\bFACTURE\s*(?:CLIENT|CLI)', 1.0),
        (r'\bFA\s*CLI', 0.95),
        (r'\bCA\b', 0.7),
        (r'\bCHIFFRE\s*D[\'E]?\s*AFFAIRE', 0.95),
    ],
    OperationType.PROVISION: [
        (r'\bPROVISION', 1.0),
        (r'\bDOTATION', 0.95),
        (r'\bREPRISE', 0.85),
        (r'\bDAP\b', 0.9),
        (r'\bDEPRECIATION', 0.9),
    ],
    OperationType.DOTATION: [
        (r'\bDOTATION', 1.0),
        (r'\bAMORTISSEMENT', 0.95),
        (r'\bDAP\b', 0.9),
        (r'\bDAMO', 0.9),
    ],
    OperationType.REPRISE: [
        (r'\bREPRISE', 1.0),
        (r'\bRAP\b', 0.85),
    ],
    OperationType.SALAIRE: [
        (r'\bSALAIRE', 1.0),
        (r'\bPAIE\b', 0.95),
        (r'\bPAYE\b', 0.95),
        (r'\bREMUNERATION', 0.9),
        (r'\bCHARGES?\s*SOCIALES?', 0.85),
        (r'\bURSSAF', 0.9),
        (r'\bCOTISATION', 0.8),
    ],
    OperationType.CHARGE_FIXE: [
        (r'\bLOYER', 1.0),
        (r'\bABONNEMENT', 0.95),
        (r'\bASSURANCE', 0.85),
        (r'\bLEASING', 0.9),
        (r'\bLOCATION', 0.85),
        (r'\bMAINTENANCE', 0.8),
        (r'\bENTRETIEN', 0.75),
    ],
    OperationType.INVESTISSEMENT: [
        (r'\bINVESTISSEMENT', 1.0),
        (r'\bIMMOBILISATION', 0.95),
        (r'\bIMMO\b', 0.8),
        (r'\bACQUISITION', 0.85),
        (r'\bCAPEX', 0.9),
    ],
    OperationType.CESSION: [
        (r'\bCESSION', 1.0),
        (r'\bSORTIE\s*D[\'E]?\s*IMMO', 0.95),
        (r'\bVENTE\s*D[\'E]?\s*IMMO', 0.95),
        (r'\bPLUS[- ]?VALUE', 0.85),
        (r'\bMOINS[- ]?VALUE', 0.85),
    ],
    OperationType.REGULARISATION: [
        (r'\bREGULARISATION', 1.0),
        (r'\bREGUL\b', 0.9),
        (r'\bAJUSTEMENT', 0.85),
    ],
    OperationType.EXTOURNE: [
        (r'\bEXTOURNE', 1.0),
        (r'\bCONTREPASSATION', 1.0),
        (r'\bANNULATION', 0.9),
    ],
    OperationType.VIREMENT: [
        (r'\bVIREMENT', 1.0),
        (r'\bTRANSFERT', 0.85),
        (r'\bVIR\b', 0.8),
    ],
}

# =============================================================================
# PATTERNS DE RÉCURRENCE
# =============================================================================

RECURRING_PATTERNS = [
    # Mensuel
    (r'\bMENSUEL', 1.0),
    (r'\bLOYER', 0.9),
    (r'\bABONNEMENT', 0.9),
    (r'\bPRELEVEMENT\s*AUTO', 0.85),
    # Périodes
    (r'\bJANVIER|FEVRIER|MARS|AVRIL|MAI|JUIN|JUILLET|AOUT|SEPTEMBRE|OCTOBRE|NOVEMBRE|DECEMBRE', 0.7),
    (r'\bMOIS\s*DE', 0.75),
    # Contrats
    (r'\bCONTRAT', 0.7),
    (r'\bREDEVANCE', 0.85),
]


# =============================================================================
# CLASSIFICATION FUNCTIONS
# =============================================================================

def classify_intent(text: str) -> Tuple[Intent, float]:
    """
    Classifie l'intention d'un libellé.

    Args:
        text: Libellé à analyser

    Returns:
        Tuple (Intent, confidence)
    """
    if not text:
        return (Intent.STANDARD, 0.0)

    text_upper = text.upper()
    best_intent = Intent.STANDARD
    best_score = 0.0

    for intent, patterns in INTENT_PATTERNS.items():
        score = _calculate_pattern_score(text_upper, patterns)
        if score > best_score:
            best_score = score
            best_intent = intent

    # Si aucun pattern ne matche, c'est STANDARD
    if best_score < 0.5:
        return (Intent.STANDARD, 1.0 - best_score)

    return (best_intent, best_score)


def classify_operation(text: str) -> Tuple[OperationType, float]:
    """
    Classifie le type d'opération d'un libellé.

    Args:
        text: Libellé à analyser

    Returns:
        Tuple (OperationType, confidence)
    """
    if not text:
        return (OperationType.INCONNU, 0.0)

    text_upper = text.upper()
    best_type = OperationType.INCONNU
    best_score = 0.0

    for op_type, patterns in OPERATION_PATTERNS.items():
        score = _calculate_pattern_score(text_upper, patterns)
        if score > best_score:
            best_score = score
            best_type = op_type

    # Si aucun pattern ne matche suffisamment
    if best_score < 0.5:
        return (OperationType.INCONNU, 0.0)

    return (best_type, best_score)


def detect_recurring(text: str) -> Tuple[bool, float]:
    """
    Détecte si un libellé indique une opération récurrente.

    Args:
        text: Libellé à analyser

    Returns:
        Tuple (is_recurring, confidence)
    """
    if not text:
        return (False, 0.0)

    text_upper = text.upper()
    total_score = 0.0
    matches = 0

    for pattern, weight in RECURRING_PATTERNS:
        if re.search(pattern, text_upper, re.IGNORECASE):
            total_score += weight
            matches += 1

    if matches == 0:
        return (False, 0.0)

    avg_score = total_score / matches
    is_recurring = avg_score >= 0.7 or matches >= 2

    return (is_recurring, avg_score)


def detect_round_amount(text: str) -> bool:
    """
    Détecte si le libellé mentionne un montant rond.

    Args:
        text: Libellé à analyser

    Returns:
        True si montant rond détecté
    """
    # Chercher des montants ronds dans le texte
    round_patterns = [
        r'\b(\d+)\s*000\b',  # 1000, 5000, etc.
        r'\b(\d+)\s*K\b',     # 5K, 10K
    ]

    for pattern in round_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return True

    # Chercher un montant et vérifier s'il est rond
    amount_match = re.search(r'(\d{3,}(?:[,\.]\d{2})?)', text)
    if amount_match:
        try:
            amount_str = amount_match.group(1).replace(",", ".").replace(" ", "")
            amount = float(amount_str)
            # Rond si divisible par 100 ou 500
            if amount >= 100 and (amount % 100 == 0 or amount % 500 == 0):
                return True
        except ValueError:
            pass

    return False


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _calculate_pattern_score(text: str, patterns: List[Tuple[str, float]]) -> float:
    """
    Calcule un score basé sur les patterns matchés.

    Args:
        text: Texte à analyser (uppercase)
        patterns: Liste de (pattern_regex, weight)

    Returns:
        Score entre 0 et 1
    """
    matched_weights = []

    for pattern, weight in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            matched_weights.append(weight)

    if not matched_weights:
        return 0.0

    # Prendre le max des poids matchés (pas la somme, pour éviter sur-scoring)
    return max(matched_weights)


def get_all_intents(text: str) -> List[Tuple[Intent, float]]:
    """
    Retourne tous les intents potentiels avec leurs scores.

    Utile pour debug ou quand plusieurs intents sont possibles.

    Args:
        text: Libellé à analyser

    Returns:
        Liste de (Intent, score) triée par score décroissant
    """
    if not text:
        return [(Intent.STANDARD, 1.0)]

    text_upper = text.upper()
    results = []

    for intent, patterns in INTENT_PATTERNS.items():
        score = _calculate_pattern_score(text_upper, patterns)
        if score > 0:
            results.append((intent, score))

    # Ajouter STANDARD si rien ne matche fortement
    if not results or max(r[1] for r in results) < 0.5:
        results.append((Intent.STANDARD, 0.5))

    # Trier par score décroissant
    results.sort(key=lambda x: x[1], reverse=True)

    return results


def get_all_operations(text: str) -> List[Tuple[OperationType, float]]:
    """
    Retourne tous les types d'opération potentiels avec leurs scores.

    Args:
        text: Libellé à analyser

    Returns:
        Liste de (OperationType, score) triée par score décroissant
    """
    if not text:
        return [(OperationType.INCONNU, 1.0)]

    text_upper = text.upper()
    results = []

    for op_type, patterns in OPERATION_PATTERNS.items():
        score = _calculate_pattern_score(text_upper, patterns)
        if score > 0:
            results.append((op_type, score))

    if not results:
        results.append((OperationType.INCONNU, 1.0))

    results.sort(key=lambda x: x[1], reverse=True)

    return results
