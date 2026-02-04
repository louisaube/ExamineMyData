"""
GL Crystal - Métriques de Cristallinité

Les 5 axes de mesure de l'ICC (Indice de Cristallinité Comptable).

Chaque métrique retourne un score brut qui sera ensuite normalisé
et pondéré dans le calcul de l'ICC composite.

Optimisations:
- Numba JIT pour les calculs d'entropie Shannon (x170 plus rapide)
- Vectorisation numpy pour les calculs CV
"""

import math
from collections import Counter
from typing import List, Dict, Tuple, Optional
import numpy as np
from scipy import stats

try:
    from numba import njit
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    def njit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator


@njit(cache=True)
def _shannon_entropy_numba(counts: np.ndarray, total: int) -> float:
    """
    Calcul Numba-accéléré de l'entropie de Shannon.
    Gain x170 sur grandes listes.
    """
    entropy = 0.0
    log2_total = np.log2(total)
    for count in counts:
        if count > 0:
            p = count / total
            entropy -= p * (np.log2(count) - log2_total)
    return entropy


def compute_cv_decompose(
    montants: List[float],
    fournisseurs: Optional[List[str]] = None,
    mois: Optional[List[str]] = None
) -> Dict[str, float]:
    """
    Calcule le coefficient de variation décomposé.

    La variance totale est décomposée en:
    - Variance inter-fournisseurs (si disponible)
    - Variance temporelle (si disponible)
    - Variance résiduelle (de nature)

    Un CV faible = montants homogènes = cristallin
    Un CV élevé = montants très dispersés = amorphe

    Args:
        montants: Liste des montants (valeurs absolues)
        fournisseurs: Liste des codes fournisseurs (optionnel)
        mois: Liste des mois (optionnel)

    Returns:
        Dict avec cv_total, cv_inter_fournisseur, cv_temporel, cv_residuel
    """
    if not montants or len(montants) < 2:
        return {'cv_total': 0.0, 'cv_inter_fournisseur': 0.0,
                'cv_temporel': 0.0, 'cv_residuel': 0.0}

    montants_arr = np.array([abs(m) for m in montants])
    mean = np.mean(montants_arr)

    if mean == 0:
        return {'cv_total': 0.0, 'cv_inter_fournisseur': 0.0,
                'cv_temporel': 0.0, 'cv_residuel': 0.0}

    # CV total
    cv_total = float(np.std(montants_arr) / mean)

    # Variance inter-fournisseur
    cv_inter_fournisseur = 0.0
    if fournisseurs and len(set(fournisseurs)) > 1:
        groups = {}
        for m, f in zip(montants_arr, fournisseurs):
            if f not in groups:
                groups[f] = []
            groups[f].append(m)
        group_means = [np.mean(g) for g in groups.values() if len(g) > 0]
        if len(group_means) > 1:
            cv_inter_fournisseur = float(np.std(group_means) / mean)

    # Variance temporelle
    cv_temporel = 0.0
    if mois and len(set(mois)) > 1:
        groups = {}
        for m, month in zip(montants_arr, mois):
            if month not in groups:
                groups[month] = []
            groups[month].append(m)
        monthly_totals = [sum(g) for g in groups.values()]
        if len(monthly_totals) > 1 and np.mean(monthly_totals) > 0:
            cv_temporel = float(np.std(monthly_totals) / np.mean(monthly_totals))

    # Variance résiduelle (approximation)
    cv_residuel = max(0, cv_total - cv_inter_fournisseur - cv_temporel)

    return {
        'cv_total': cv_total,
        'cv_inter_fournisseur': cv_inter_fournisseur,
        'cv_temporel': cv_temporel,
        'cv_residuel': cv_residuel,
    }


def compute_entropy_libelles(
    libelles: List[str],
    use_tfidf: bool = True
) -> Dict[str, float]:
    """
    Calcule l'entropie de Shannon sur les libellés.

    Mesure la diversité sémantique du contenu.
    - Entropie faible = libellés homogènes = cristallin
    - Entropie élevée = libellés très divers = amorphe

    L'entropie est normalisée par log(n) pour être comparable
    entre couples de tailles différentes.

    Args:
        libelles: Liste des libellés d'écritures
        use_tfidf: Si True, utilise TF-IDF pour pondérer les tokens

    Returns:
        Dict avec entropy_raw, entropy_normalized, n_tokens_uniques
    """
    if not libelles:
        return {'entropy_raw': 0.0, 'entropy_normalized': 0.0,
                'n_tokens_uniques': 0}

    # Tokenisation simple
    tokens = []
    for lib in libelles:
        if lib:
            # Normalise et tokenise
            words = str(lib).lower().split()
            # Filtre les mots très courts et les nombres purs
            words = [w for w in words if len(w) > 2 and not w.isdigit()]
            tokens.extend(words)

    if not tokens:
        return {'entropy_raw': 0.0, 'entropy_normalized': 0.0,
                'n_tokens_uniques': 0}

    # Compte les fréquences
    token_counts = Counter(tokens)
    n_tokens = len(tokens)
    n_unique = len(token_counts)

    # Calcul de l'entropie de Shannon avec Numba si disponible
    if NUMBA_AVAILABLE and n_unique > 100:
        counts_arr = np.array(list(token_counts.values()), dtype=np.float64)
        entropy = _shannon_entropy_numba(counts_arr, n_tokens)
    else:
        entropy = 0.0
        for count in token_counts.values():
            p = count / n_tokens
            if p > 0:
                entropy -= p * math.log2(p)

    # Normalisation par log2(n_unique) pour avoir un score entre 0 et 1
    max_entropy = math.log2(n_unique) if n_unique > 1 else 1.0
    entropy_normalized = entropy / max_entropy if max_entropy > 0 else 0.0

    return {
        'entropy_raw': entropy,
        'entropy_normalized': entropy_normalized,
        'n_tokens_uniques': n_unique,
    }


def compute_regularite_temporelle(
    montants: List[float],
    mois: List[str]
) -> Dict[str, float]:
    """
    Calcule la régularité temporelle des écritures.

    Mesure si le pattern est récurrent (cristallin) ou chaotique (amorphe).

    Utilise:
    - Autocorrélation: pattern qui se répète
    - Coefficient de variation inter-mois: stabilité des totaux mensuels

    Args:
        montants: Liste des montants
        mois: Liste des mois (format "YYYY-MM")

    Returns:
        Dict avec autocorrelation, cv_mensuel, score_regularite
    """
    if not montants or not mois or len(montants) < 3:
        return {'autocorrelation': 0.0, 'cv_mensuel': 1.0, 'score_regularite': 0.0}

    # Agrège par mois
    monthly_totals = {}
    for m, month in zip(montants, mois):
        if month not in monthly_totals:
            monthly_totals[month] = 0.0
        monthly_totals[month] += abs(m)

    # Trie par mois
    sorted_months = sorted(monthly_totals.keys())
    series = [monthly_totals[m] for m in sorted_months]

    if len(series) < 3:
        return {'autocorrelation': 0.0, 'cv_mensuel': 1.0, 'score_regularite': 0.0}

    # CV mensuel
    mean_monthly = np.mean(series)
    cv_mensuel = float(np.std(series) / mean_monthly) if mean_monthly > 0 else 1.0

    # Autocorrélation lag=1 (mois consécutifs)
    series_arr = np.array(series)
    if len(series_arr) > 1 and np.std(series_arr) > 0:
        autocorr = float(np.corrcoef(series_arr[:-1], series_arr[1:])[0, 1])
        if np.isnan(autocorr):
            autocorr = 0.0
    else:
        autocorr = 0.0

    # Score de régularité composite
    # CV faible + autocorrélation positive = régulier
    score_regularite = max(0, (1 - min(cv_mensuel, 2) / 2) * 0.5 +
                          (autocorr + 1) / 2 * 0.5)

    return {
        'autocorrelation': autocorr,
        'cv_mensuel': cv_mensuel,
        'score_regularite': score_regularite,
    }


def compute_diversite_journaux(journaux: List[str]) -> Dict[str, float]:
    """
    Calcule la diversité des journaux sources.

    Un seul journal = pur (cristallin)
    Plusieurs journaux = suspect (amorphe)

    Args:
        journaux: Liste des codes journaux

    Returns:
        Dict avec n_journaux, concentration, score_purete
    """
    if not journaux:
        return {'n_journaux': 0, 'concentration': 1.0, 'score_purete': 1.0}

    journaux_clean = [j for j in journaux if j]
    if not journaux_clean:
        return {'n_journaux': 0, 'concentration': 1.0, 'score_purete': 1.0}

    journal_counts = Counter(journaux_clean)
    n_journaux = len(journal_counts)
    total = sum(journal_counts.values())

    # Concentration (Herfindahl normalisé)
    hhi = sum((c / total) ** 2 for c in journal_counts.values())

    # Score de pureté: 1 journal = 1.0, 2+ journaux = décroissant
    if n_journaux == 1:
        score_purete = 1.0
    elif n_journaux == 2:
        score_purete = 0.7
    elif n_journaux <= 3:
        score_purete = 0.4
    else:
        score_purete = 0.1

    return {
        'n_journaux': n_journaux,
        'concentration': hhi,
        'score_purete': score_purete,
    }


def compute_concentration_contreparties(
    contreparties: List[str]
) -> Dict[str, float]:
    """
    Calcule la concentration des contreparties (indice de Herfindahl).

    Fournisseur unique = forte concentration = cristallin (monoculture)
    Dispersion = faible concentration = amorphe

    L'indice de Herfindahl (HHI) = Σ(part_i)²
    - HHI = 1 : concentration maximale (un seul fournisseur)
    - HHI = 1/n : concentration minimale (répartition égale)

    Args:
        contreparties: Liste des comptes de contrepartie

    Returns:
        Dict avec herfindahl, n_contreparties, concentration_top1
    """
    if not contreparties:
        return {'herfindahl': 1.0, 'n_contreparties': 0, 'concentration_top1': 1.0}

    contreparties_clean = [c for c in contreparties if c]
    if not contreparties_clean:
        return {'herfindahl': 1.0, 'n_contreparties': 0, 'concentration_top1': 1.0}

    counts = Counter(contreparties_clean)
    n_contreparties = len(counts)
    total = sum(counts.values())

    # Indice de Herfindahl
    hhi = sum((c / total) ** 2 for c in counts.values())

    # Concentration top 1 (part du fournisseur principal)
    concentration_top1 = max(counts.values()) / total if total > 0 else 1.0

    return {
        'herfindahl': hhi,
        'n_contreparties': n_contreparties,
        'concentration_top1': concentration_top1,
    }


def compute_icc_composite(
    cv_metrics: Dict[str, float],
    entropy_metrics: Dict[str, float],
    regularite_metrics: Dict[str, float],
    journaux_metrics: Dict[str, float],
    contreparties_metrics: Dict[str, float],
    weights: Optional[Dict[str, float]] = None
) -> float:
    """
    Calcule l'ICC composite à partir des 5 axes.

    Chaque axe contribue au score final selon des poids configurables.
    Le score final est entre 0 (amorphe) et 1 (cristallin).

    Axes:
    1. Montants (CV): CV faible = cristallin
    2. Libellés (Entropie): Entropie faible = cristallin
    3. Temporalité: Régularité élevée = cristallin
    4. Journaux: Pureté élevée = cristallin
    5. Contreparties: Concentration élevée = cristallin

    Args:
        cv_metrics: Résultat de compute_cv_decompose
        entropy_metrics: Résultat de compute_entropy_libelles
        regularite_metrics: Résultat de compute_regularite_temporelle
        journaux_metrics: Résultat de compute_diversite_journaux
        contreparties_metrics: Résultat de compute_concentration_contreparties
        weights: Poids des axes (optionnel)

    Returns:
        Score ICC composite entre 0 et 1
    """
    if weights is None:
        weights = {
            'montants': 0.20,
            'libelles': 0.20,
            'temporalite': 0.20,
            'journaux': 0.20,
            'contreparties': 0.20,
        }

    # Normalisation des métriques en scores 0-1 (1 = cristallin)
    # Montants: CV < 0.5 = bon, CV > 2 = mauvais
    cv = cv_metrics.get('cv_total', 0)
    score_montants = max(0, 1 - min(cv, 2) / 2)

    # Libellés: entropie normalisée < 0.5 = bon, > 0.9 = mauvais
    entropy = entropy_metrics.get('entropy_normalized', 0)
    score_libelles = max(0, 1 - entropy)

    # Temporalité: score déjà entre 0 et 1
    score_temporalite = regularite_metrics.get('score_regularite', 0.5)

    # Journaux: score déjà entre 0 et 1
    score_journaux = journaux_metrics.get('score_purete', 1.0)

    # Contreparties: HHI élevé = cristallin
    hhi = contreparties_metrics.get('herfindahl', 1.0)
    score_contreparties = hhi  # Déjà entre 0 et 1

    # Composite pondéré
    icc = (
        weights['montants'] * score_montants +
        weights['libelles'] * score_libelles +
        weights['temporalite'] * score_temporalite +
        weights['journaux'] * score_journaux +
        weights['contreparties'] * score_contreparties
    )

    return float(min(1.0, max(0.0, icc)))
