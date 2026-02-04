"""
gl_normalizer/layer3/materiality.py
Filtre de Matérialité

Premier filtre de Layer 3: élimine les signaux dont le montant
est inférieur au seuil de matérialité.

Principes:
- Seuil par défaut: 5000€ (configurable)
- Seuil par univers (optionnel): CRISTALLIN peut avoir un seuil plus bas
- Le montant utilisé est delta × base (impact réel, pas juste l'écart %)

Un signal statistiquement significatif (p < 0.05) mais portant sur
50€ n'est pas actionnable pour l'audit.
"""

from typing import Dict, Any, Optional, Tuple, TYPE_CHECKING
import math

if TYPE_CHECKING:
    from ..layer2.base import RawSignal, Univers


# =============================================================================
# CONSTANTES
# =============================================================================

DEFAULT_MATERIALITY_THRESHOLD = 5000.0  # 5000€ par défaut

# Seuils par univers (peut être overridé par referentiel)
UNIVERS_MATERIALITY: Dict[str, float] = {
    "CRISTALLIN": 2000.0,         # Charges fixes: seuil plus bas car récurrent
    "NOMINATIF_TIERS": 10000.0,   # Auxiliaires: seuil plus haut (volume)
    "NOMINATIF_OPERATIONNEL": 5000.0,
    "PROCESSUS": 5000.0,
    "VENTILATION": 3000.0,        # ABT: souvent petits montants mais critiques
    "CUT_OFF": 5000.0,
    "TRESORERIE": 20000.0,        # Trésorerie: seuil élevé
    "PONCTUEL": 10000.0,          # Exceptionnel: seuil élevé
    "INVENTAIRE": 15000.0,        # Stocks/Immos: seuil élevé
    "COMPOSITE": 5000.0,
}

# Multiplicateurs selon le type de signal
SIGNAL_TYPE_MULTIPLIERS: Dict[str, float] = {
    "L2-VAR": 1.0,       # Variation standard
    "L2-DISCORD": 0.8,   # Discord Matrix Profile: plus strict
    "L2-MISSING": 0.5,   # Mois manquant: pas directement un montant
    "L2-CONC": 1.2,      # Concentration: moins strict
}


# =============================================================================
# FUNCTIONS
# =============================================================================

def get_materiality_threshold(
    signal: "RawSignal",
    referentiel: Dict[str, Any],
    default_threshold: float = DEFAULT_MATERIALITY_THRESHOLD,
) -> float:
    """
    Détermine le seuil de matérialité pour un signal.

    Ordre de priorité:
    1. Seuil spécifique dans le référentiel pour cette famille
    2. Seuil par univers
    3. Seuil par défaut

    Args:
        signal: RawSignal à évaluer
        referentiel: Dictionnaire famille → metadata
        default_threshold: Seuil par défaut si non trouvé

    Returns:
        Seuil de matérialité en euros
    """
    famille = signal.famille

    # 1. Chercher dans le référentiel
    ref_entry = referentiel.get(famille, {})
    if "seuil_materialite" in ref_entry:
        threshold = float(ref_entry["seuil_materialite"])
        if threshold > 0:
            return threshold

    # 2. Seuil par univers
    univers_str = signal.univers.value if hasattr(signal.univers, 'value') else str(signal.univers)
    if univers_str in UNIVERS_MATERIALITY:
        return UNIVERS_MATERIALITY[univers_str]

    # 3. Défaut
    return default_threshold


def compute_materiality_amount(
    signal: "RawSignal",
    referentiel: Dict[str, Any],
) -> float:
    """
    Calcule le montant de matérialité pour un signal.

    Le "montant" pertinent dépend du type de test:
    - Variation: delta × médiane historique (impact réel)
    - Discord: montant du mois discord
    - Missing: estimation du montant manquant (médiane × nb mois)
    - Concentration: montant du mois concentré

    Args:
        signal: RawSignal
        referentiel: Référentiel sémantique

    Returns:
        Montant de matérialité en euros (absolu)
    """
    test_id = signal.test_id

    # Cas 1: Le signal a un metric_value qui est déjà un montant
    if signal.metric_value > 100:  # Probablement un montant
        return abs(signal.metric_value)

    # Cas 2: Variation en pourcentage
    if test_id == "L2-VAR":
        # delta = écart au seuil, threshold = médiane
        # Impact = variation × base
        if signal.threshold > 0:
            return abs(signal.delta * signal.threshold)
        return abs(signal.metric_value)

    # Cas 3: Discord Matrix Profile
    if test_id == "L2-DISCORD":
        return abs(signal.metric_value)

    # Cas 4: Mois manquant
    if test_id == "L2-MISSING":
        # Estimation: médiane × nombre de mois manquants
        missing_count = signal.metadata.get("missing_count", 1)
        median_month = signal.threshold  # threshold = expected months, mais on veut montant
        # Fallback sur metric_value si disponible
        if signal.metric_value > 0:
            return abs(signal.metric_value * missing_count)
        return 0.0

    # Cas 5: Concentration
    if test_id == "L2-CONC":
        # Le montant est dans metadata ou metric_value
        return abs(signal.metric_value) if signal.metric_value > 1 else 0.0

    # Default: metric_value ou delta
    return max(abs(signal.metric_value), abs(signal.delta * signal.threshold))


def check_materiality(
    signal: "RawSignal",
    referentiel: Dict[str, Any],
    override_threshold: Optional[float] = None,
) -> Tuple[bool, float, float, str]:
    """
    Vérifie si un signal passe le filtre de matérialité.

    Args:
        signal: RawSignal à évaluer
        referentiel: Référentiel sémantique
        override_threshold: Seuil forcé (ignore univers/famille)

    Returns:
        Tuple (passes, amount, threshold, reason):
        - passes: True si le signal passe
        - amount: Montant calculé
        - threshold: Seuil appliqué
        - reason: Explication textuelle
    """
    # Calculer le seuil
    if override_threshold is not None:
        threshold = override_threshold
    else:
        threshold = get_materiality_threshold(signal, referentiel)

    # Appliquer multiplicateur selon type de signal
    multiplier = SIGNAL_TYPE_MULTIPLIERS.get(signal.test_id, 1.0)
    adjusted_threshold = threshold * multiplier

    # Calculer le montant
    amount = compute_materiality_amount(signal, referentiel)

    # Vérifier
    passes = amount >= adjusted_threshold

    if passes:
        reason = f"Matérialité OK: {amount:,.0f}€ >= {adjusted_threshold:,.0f}€"
    else:
        reason = f"Sous matérialité: {amount:,.0f}€ < {adjusted_threshold:,.0f}€"

    return (passes, amount, adjusted_threshold, reason)


def compute_materiality_score(
    amount: float,
    threshold: float,
    max_score_at: float = 10.0,
) -> float:
    """
    Calcule un score de matérialité (0-100).

    Le score augmente avec le ratio amount/threshold:
    - ratio = 1: score = 50 (juste au seuil)
    - ratio = 2: score = 70
    - ratio = 5: score = 90
    - ratio >= 10: score = 100

    Args:
        amount: Montant en euros
        threshold: Seuil de matérialité
        max_score_at: Ratio pour score max (défaut: 10×)

    Returns:
        Score 0-100
    """
    if threshold <= 0:
        return 50.0  # Default

    ratio = amount / threshold

    if ratio < 1:
        # Sous le seuil: score proportionnel
        return 50.0 * ratio
    else:
        # Au-dessus: score logarithmique
        log_ratio = math.log10(1 + ratio)
        log_max = math.log10(1 + max_score_at)
        score = 50.0 + 50.0 * (log_ratio / log_max)
        return min(100.0, score)
