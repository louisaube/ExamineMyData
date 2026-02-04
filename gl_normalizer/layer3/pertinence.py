"""
gl_normalizer/layer3/pertinence.py
Calcul du Score de Pertinence

Combine tous les facteurs pour calculer un score de pertinence final:
- Score statistique (p-value)
- Score de matérialité (montant vs seuil)
- Boost des règles signal_si
- Pénalités éventuelles

Le score final détermine:
1. Si le signal passe le seuil de pertinence minimum
2. Le rang du signal dans la liste finale
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional, TYPE_CHECKING
import math

if TYPE_CHECKING:
    from ..layer2.base import RawSignal

from .base import PertinenceLevel


# =============================================================================
# CONSTANTES
# =============================================================================

DEFAULT_PERTINENCE_THRESHOLD = 40.0  # Score minimum pour être pertinent

# Poids des facteurs dans le score final
WEIGHTS = {
    "statistical": 0.35,   # P-value / significativité
    "materiality": 0.30,   # Montant / impact financier
    "business": 0.25,      # Règles métier (boost signal_si)
    "context": 0.10,       # Contexte additionnel
}


# =============================================================================
# SCORE COMPONENTS
# =============================================================================

def compute_statistical_score(
    signal: "RawSignal",
    max_score: float = 100.0,
) -> float:
    """
    Calcule le score statistique basé sur la p-value.

    Mapping p-value → score:
    - p < 0.001: score = 100 (très significatif)
    - p < 0.01:  score = 85
    - p < 0.05:  score = 70
    - p < 0.10:  score = 50
    - p >= 0.10: score décroissant

    Args:
        signal: RawSignal avec pvalue/pvalue_adjusted
        max_score: Score maximum

    Returns:
        Score 0-100
    """
    # Utiliser pvalue_adjusted si disponible (après BH-FDR)
    pvalue = signal.pvalue_adjusted or signal.pvalue

    if pvalue is None:
        # Fallback sur raw_score si pas de p-value
        return min(max_score, signal.raw_score)

    # Mapping p-value → score
    if pvalue < 0.001:
        return max_score
    elif pvalue < 0.005:
        return max_score * 0.90
    elif pvalue < 0.01:
        return max_score * 0.85
    elif pvalue < 0.02:
        return max_score * 0.75
    elif pvalue < 0.05:
        return max_score * 0.70
    elif pvalue < 0.10:
        return max_score * 0.50
    else:
        # Score décroissant logarithmique
        return max_score * max(0, 0.5 - math.log10(pvalue + 0.01) * 0.2)


def compute_materiality_score(
    amount: float,
    threshold: float,
    max_score: float = 100.0,
) -> float:
    """
    Calcule le score de matérialité.

    Mapping ratio → score:
    - ratio < 1: score proportionnel (sous le seuil)
    - ratio = 1: score = 50 (juste au seuil)
    - ratio = 2: score = 70
    - ratio >= 5: score = 100

    Args:
        amount: Montant en euros
        threshold: Seuil de matérialité
        max_score: Score maximum

    Returns:
        Score 0-100
    """
    if threshold <= 0:
        return max_score * 0.5  # Default

    ratio = amount / threshold

    if ratio < 1:
        # Sous le seuil: score proportionnel
        return max_score * 0.5 * ratio
    elif ratio < 2:
        # Entre 1× et 2×: 50-70
        return max_score * (0.5 + 0.2 * (ratio - 1))
    elif ratio < 5:
        # Entre 2× et 5×: 70-90
        return max_score * (0.7 + 0.2 * (ratio - 2) / 3)
    else:
        # Au-dessus de 5×: 90-100
        return max_score * min(1.0, 0.9 + 0.1 * math.log10(ratio / 5))


def compute_business_score(
    base_score: float,
    inclusion_boost: float,
    exclusion_penalty: float = 0.0,
    max_boost: float = 30.0,
) -> float:
    """
    Applique les ajustements métier au score.

    Args:
        base_score: Score de base (0-100)
        inclusion_boost: Points à ajouter (signal_si)
        exclusion_penalty: Points à retirer (exclusions partielles)
        max_boost: Boost maximum

    Returns:
        Score ajusté (0-100)
    """
    boost = min(max_boost, inclusion_boost) - exclusion_penalty
    adjusted = base_score + boost
    return max(0.0, min(100.0, adjusted))


def compute_context_score(
    signal: "RawSignal",
    context: Dict[str, Any],
) -> float:
    """
    Calcule un score contextuel basé sur les métadonnées.

    Facteurs:
    - Univers à risque: +10 points
    - Fin d'exercice: +5 points
    - Test Matrix Profile: +5 points (méthode sophistiquée)

    Args:
        signal: RawSignal
        context: Contexte additionnel

    Returns:
        Score 0-30
    """
    score = 0.0

    # Univers à risque plus élevé
    high_risk_univers = ["CUT_OFF", "PONCTUEL", "INVENTAIRE"]
    univers_str = signal.univers.value if hasattr(signal.univers, 'value') else str(signal.univers)
    if univers_str in high_risk_univers:
        score += 10.0

    # Période à risque (fin d'exercice)
    periode = signal.periode or ""
    if periode.endswith("-12"):
        score += 5.0

    # Méthode de détection sophistiquée
    if signal.detection_method in ["matrix_profile", "conformal"]:
        score += 5.0

    # Calibration set large
    calib_size = signal.metadata.get("calibration_size", 0)
    if calib_size >= 12:
        score += 5.0

    return min(30.0, score)


# =============================================================================
# PERTINENCE FINALE
# =============================================================================

@dataclass
class PertinenceResult:
    """Résultat du calcul de pertinence."""
    final_score: float
    level: PertinenceLevel

    # Composantes
    statistical_score: float
    materiality_score: float
    business_score: float
    context_score: float

    # Détails
    weights_used: Dict[str, float]
    factors: Dict[str, Any]


def compute_pertinence(
    signal: "RawSignal",
    materiality_amount: float,
    materiality_threshold: float,
    inclusion_boost: float = 0.0,
    exclusion_penalty: float = 0.0,
    context: Optional[Dict[str, Any]] = None,
    weights: Optional[Dict[str, float]] = None,
) -> PertinenceResult:
    """
    Calcule le score de pertinence final d'un signal.

    Formule:
    score_final = Σ(weight_i × score_i)

    Où:
    - score_statistical: basé sur p-value
    - score_materiality: basé sur montant/seuil
    - score_business: base + boost - penalty
    - score_context: facteurs additionnels

    Args:
        signal: RawSignal
        materiality_amount: Montant calculé
        materiality_threshold: Seuil de matérialité
        inclusion_boost: Points de boost signal_si
        exclusion_penalty: Points de pénalité
        context: Contexte additionnel
        weights: Poids personnalisés

    Returns:
        PertinenceResult avec score et niveau
    """
    weights = weights or WEIGHTS
    context = context or {}

    # Calculer chaque composante
    stat_score = compute_statistical_score(signal)
    mat_score = compute_materiality_score(materiality_amount, materiality_threshold)

    # Score business: partir de la moyenne stat+mat, puis ajuster
    base_business = (stat_score + mat_score) / 2
    bus_score = compute_business_score(base_business, inclusion_boost, exclusion_penalty)

    ctx_score = compute_context_score(signal, context)

    # Score final pondéré
    final_score = (
        weights.get("statistical", 0.35) * stat_score +
        weights.get("materiality", 0.30) * mat_score +
        weights.get("business", 0.25) * bus_score +
        weights.get("context", 0.10) * ctx_score
    )

    # Normaliser à 100
    weight_sum = sum(weights.values())
    if weight_sum > 0 and weight_sum != 1.0:
        final_score = final_score / weight_sum

    final_score = min(100.0, max(0.0, final_score))

    # Déterminer le niveau
    level = _score_to_level(final_score)

    return PertinenceResult(
        final_score=final_score,
        level=level,
        statistical_score=stat_score,
        materiality_score=mat_score,
        business_score=bus_score,
        context_score=ctx_score,
        weights_used=weights,
        factors={
            "pvalue": signal.pvalue_adjusted or signal.pvalue,
            "materiality_ratio": materiality_amount / materiality_threshold if materiality_threshold > 0 else 0,
            "inclusion_boost": inclusion_boost,
            "exclusion_penalty": exclusion_penalty,
        }
    )


def _score_to_level(score: float) -> PertinenceLevel:
    """Convertit un score en niveau de pertinence."""
    if score >= 80:
        return PertinenceLevel.CRITICAL
    elif score >= 60:
        return PertinenceLevel.HIGH
    elif score >= 40:
        return PertinenceLevel.MEDIUM
    else:
        return PertinenceLevel.LOW


def passes_pertinence_threshold(
    pertinence: PertinenceResult,
    threshold: float = DEFAULT_PERTINENCE_THRESHOLD,
) -> bool:
    """Vérifie si un signal passe le seuil de pertinence."""
    return pertinence.final_score >= threshold
