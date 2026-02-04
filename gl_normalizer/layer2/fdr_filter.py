"""
gl_normalizer/layer2/fdr_filter.py
Layer 2.5: Benjamini-Hochberg FDR Control

Avec 230 familles × 18 tests = 4140 hypothèses testées,
sans correction on a une quasi-certitude de faux positifs.

BH contrôle le False Discovery Rate:
"Parmi les signaux remontés, au plus α% sont des faux positifs."

C'est le point de bascule: de ~200 signaux bruts à ~40 signaux
statistiquement significatifs.
"""

from typing import List, Tuple, TypeVar, Generic
from dataclasses import dataclass
import numpy as np

# Import scipy si disponible, sinon implémentation maison
try:
    from scipy.stats import false_discovery_control
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


T = TypeVar('T')


@dataclass
class FDRResult(Generic[T]):
    """Résultat du filtrage FDR."""
    significant: List[T]           # Signaux significatifs après correction
    rejected: List[T]              # Signaux rejetés
    adjusted_pvalues: List[float]  # P-values ajustées
    n_input: int                   # Nombre de signaux en entrée
    n_output: int                  # Nombre de signaux significatifs
    fdr_level: float               # Niveau FDR utilisé


def benjamini_hochberg(
    pvalues: List[float],
    alpha: float = 0.05
) -> List[float]:
    """
    Correction de Benjamini-Hochberg pour tests multiples.

    Ajuste les p-values pour contrôler le False Discovery Rate.

    Args:
        pvalues: Liste des p-values brutes
        alpha: Niveau FDR cible (défaut: 0.05 = 5% de faux positifs)

    Returns:
        Liste des p-values ajustées

    Examples:
        >>> pvalues = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205]
        >>> adjusted = benjamini_hochberg(pvalues, alpha=0.05)
        >>> significant = [p < 0.05 for p in adjusted]
    """
    if SCIPY_AVAILABLE:
        return list(false_discovery_control(pvalues, method='bh'))

    # Implémentation maison si scipy non disponible
    n = len(pvalues)
    if n == 0:
        return []

    # Trier les p-values avec leurs indices
    indexed = sorted(enumerate(pvalues), key=lambda x: x[1])

    # Calcul des p-values ajustées (méthode BH)
    adjusted = [0.0] * n
    prev_adj = 1.0

    for i in range(n - 1, -1, -1):
        orig_idx, pval = indexed[i]
        rank = i + 1  # Rang (1-indexed)

        # Ajustement: p_adj = min(p * n / rank, previous_adjusted)
        adj = min(pval * n / rank, prev_adj)
        adj = min(adj, 1.0)  # Plafonner à 1.0

        adjusted[orig_idx] = adj
        prev_adj = adj

    return adjusted


def fdr_filter(
    signals: List[T],
    pvalue_extractor,
    alpha: float = 0.05
) -> FDRResult[T]:
    """
    Filtre les signaux par contrôle FDR Benjamini-Hochberg.

    Args:
        signals: Liste de signaux (avec p-value accessible)
        pvalue_extractor: Fonction pour extraire la p-value d'un signal
                         ex: lambda s: s.pvalue
        alpha: Niveau FDR cible

    Returns:
        FDRResult avec signaux significatifs et rejetés

    Examples:
        >>> signals = [RawSignal(..., pvalue=0.01), RawSignal(..., pvalue=0.10)]
        >>> result = fdr_filter(signals, lambda s: s.pvalue, alpha=0.05)
        >>> print(f"{result.n_output} signaux significatifs sur {result.n_input}")
    """
    if not signals:
        return FDRResult(
            significant=[],
            rejected=[],
            adjusted_pvalues=[],
            n_input=0,
            n_output=0,
            fdr_level=alpha
        )

    # Extraire les p-values
    pvalues = [pvalue_extractor(s) for s in signals]

    # Correction BH
    adjusted = benjamini_hochberg(pvalues, alpha)

    # Séparer significatifs et rejetés
    significant = []
    rejected = []

    for signal, adj_pval in zip(signals, adjusted):
        if adj_pval < alpha:
            significant.append(signal)
        else:
            rejected.append(signal)

    return FDRResult(
        significant=significant,
        rejected=rejected,
        adjusted_pvalues=adjusted,
        n_input=len(signals),
        n_output=len(significant),
        fdr_level=alpha
    )


def fdr_filter_simple(
    pvalues: List[float],
    alpha: float = 0.05
) -> Tuple[List[int], List[float]]:
    """
    Version simplifiée: retourne les indices des p-values significatives.

    Args:
        pvalues: Liste des p-values brutes
        alpha: Niveau FDR

    Returns:
        (significant_indices, adjusted_pvalues)

    Examples:
        >>> pvalues = [0.001, 0.04, 0.06, 0.10, 0.50]
        >>> sig_idx, adj = fdr_filter_simple(pvalues, alpha=0.05)
        >>> sig_idx
        [0, 1]  # Les 2 premiers sont significatifs
    """
    adjusted = benjamini_hochberg(pvalues, alpha)
    significant_indices = [i for i, p in enumerate(adjusted) if p < alpha]
    return (significant_indices, adjusted)


def estimate_fdr_cutoff(
    pvalues: List[float],
    target_n: int
) -> float:
    """
    Estime le niveau FDR nécessaire pour obtenir ~target_n signaux.

    Utile pour explorer: "si je veux 20 signaux, quel FDR?"

    Args:
        pvalues: Liste des p-values
        target_n: Nombre cible de signaux

    Returns:
        Niveau alpha estimé
    """
    if not pvalues or target_n <= 0:
        return 0.05

    # Tester des niveaux alpha croissants
    for alpha in [0.001, 0.005, 0.01, 0.02, 0.03, 0.05, 0.10, 0.15, 0.20]:
        adjusted = benjamini_hochberg(pvalues, alpha)
        n_sig = sum(1 for p in adjusted if p < alpha)
        if n_sig >= target_n:
            return alpha

    return 0.20  # Maximum
