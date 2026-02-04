"""
gl_normalizer/layer2/statistical.py
Méthodes statistiques avancées pour détection d'anomalies

Fournit:
- Matrix Profile (STUMPY): Détection de discord (sous-séquence la plus atypique)
- ECOD: Empirical CDF Outlier Detection (scoring multivarié)

Ces méthodes sont distribution-free et adaptées aux petits échantillons (12 mois).
"""

from typing import List, Tuple, Optional, Dict, Any
import numpy as np

# Import optionnel de STUMPY (peut ne pas être installé)
try:
    import stumpy
    STUMPY_AVAILABLE = True
except ImportError:
    STUMPY_AVAILABLE = False


# =============================================================================
# MATRIX PROFILE (STUMPY) - Discord Detection
# =============================================================================

def matrix_profile_discord(
    series: List[float],
    window_size: int = 3,
    normalize: bool = True
) -> Tuple[Optional[int], Optional[float], Optional[float]]:
    """
    Trouve le discord (sous-séquence la plus atypique) dans une série temporelle.

    Utilise Matrix Profile (Yeh et al. 2016) via STUMPY.
    Le discord est le point ayant la plus grande distance à son plus proche voisin.

    Idéal pour CRISTALLIN et PROCESSUS: identifie LE mois qui ne ressemble
    à aucun autre, sans définir a priori ce qu'est "anormal".

    Args:
        series: Série temporelle (ex: 12 montants mensuels)
        window_size: Taille de la fenêtre de comparaison (défaut: 3 mois)
        normalize: Normaliser la série avant analyse

    Returns:
        (discord_idx, discord_distance, pvalue_estimate):
        - discord_idx: Index du mois le plus atypique (None si échec)
        - discord_distance: Distance au plus proche voisin
        - pvalue_estimate: Estimation de p-value basée sur le rang

    Examples:
        >>> series = [1000, 1005, 998, 1002, 2500, 1001, 999, 1003, 997, 1004, 1000, 1002]
        >>> idx, dist, pval = matrix_profile_discord(series)
        >>> idx
        4  # Le mois avec 2500 est le discord
    """
    if not STUMPY_AVAILABLE:
        return _matrix_profile_fallback(series, window_size)

    series_arr = np.array(series, dtype=float)
    n = len(series_arr)

    # Besoin d'au moins window_size + 1 points
    if n < window_size + 1:
        return (None, None, None)

    # Normalisation optionnelle
    if normalize and np.std(series_arr) > 0:
        series_arr = (series_arr - np.mean(series_arr)) / np.std(series_arr)

    try:
        # Calcul du Matrix Profile
        mp = stumpy.stump(series_arr, m=window_size)

        # Le discord est le point avec la plus grande distance (colonne 0)
        distances = mp[:, 0].astype(float)
        discord_idx = int(np.argmax(distances))
        discord_distance = float(distances[discord_idx])

        # Estimation p-value: rang du discord / nombre de points
        rank = np.sum(distances <= discord_distance)
        pvalue_estimate = 1.0 - (rank / len(distances))

        return (discord_idx, discord_distance, pvalue_estimate)

    except Exception:
        return _matrix_profile_fallback(series, window_size)


def _matrix_profile_fallback(
    series: List[float],
    window_size: int = 3
) -> Tuple[Optional[int], Optional[float], Optional[float]]:
    """
    Fallback simple si STUMPY n'est pas disponible.

    Utilise une approche basique: distance de chaque point à la médiane
    des fenêtres glissantes.
    """
    series_arr = np.array(series, dtype=float)
    n = len(series_arr)

    if n < window_size + 1:
        return (None, None, None)

    # Calcul des moyennes mobiles
    distances = []
    for i in range(n - window_size + 1):
        window = series_arr[i:i + window_size]
        # Distance = écart de la fenêtre à la médiane globale
        median_global = np.median(series_arr)
        dist = abs(np.mean(window) - median_global)
        distances.append(dist)

    if not distances:
        return (None, None, None)

    distances = np.array(distances)
    discord_idx = int(np.argmax(distances))
    discord_distance = float(distances[discord_idx])

    # P-value estimée
    rank = np.sum(distances <= discord_distance)
    pvalue_estimate = 1.0 - (rank / len(distances))

    return (discord_idx, discord_distance, pvalue_estimate)


def detect_discord_months(
    monthly_amounts: Dict[str, float],
    window_size: int = 3,
    pvalue_threshold: float = 0.1
) -> List[Tuple[str, float, float]]:
    """
    Détecte les mois discord dans une série de montants mensuels.

    Args:
        monthly_amounts: Dict période -> montant (ex: {"2024-01": 1000, ...})
        window_size: Taille de fenêtre pour Matrix Profile
        pvalue_threshold: Seuil de p-value pour considérer comme discord

    Returns:
        Liste de (période, distance, pvalue) pour les mois discord
    """
    if len(monthly_amounts) < window_size + 1:
        return []

    # Trier par période
    sorted_periods = sorted(monthly_amounts.keys())
    series = [monthly_amounts[p] for p in sorted_periods]

    discord_idx, discord_dist, pvalue = matrix_profile_discord(series, window_size)

    if discord_idx is None or pvalue is None:
        return []

    if pvalue < pvalue_threshold:
        return [(sorted_periods[discord_idx], discord_dist, pvalue)]

    return []


# =============================================================================
# ECOD (Empirical CDF Outlier Detection)
# =============================================================================

def ecod_score_univariate(
    x: float,
    reference_set: List[float]
) -> float:
    """
    Score ECOD univarié: position dans la CDF empirique.

    Le score est la probabilité d'observer une valeur plus extrême.
    Équivalent à une p-value empirique bilatérale.

    Args:
        x: Valeur à scorer
        reference_set: Échantillon de référence

    Returns:
        Score ∈ (0, 1] - Plus c'est petit, plus c'est extrême
    """
    if len(reference_set) < 2:
        return 1.0

    ref_arr = np.array(reference_set)
    n = len(ref_arr)

    # Position dans la CDF
    rank_left = np.sum(ref_arr <= x) / n   # P(X <= x)
    rank_right = np.sum(ref_arr >= x) / n  # P(X >= x)

    # Score bilatéral: min des deux queues, multiplié par 2
    score = 2 * min(rank_left, rank_right)

    # Éviter score = 0 exact
    return max(score, 1.0 / (n + 1))


def ecod_score_multivariate(
    x_vector: List[float],
    reference_matrix: List[List[float]]
) -> Tuple[float, List[float]]:
    """
    Score ECOD multivarié (Li et al. 2022 simplifié).

    Chaque dimension contribue indépendamment au score via sa CDF empirique.
    Le score final est le produit des scores (ou min pour être conservateur).

    Args:
        x_vector: Vecteur de features à scorer [f1, f2, ...]
        reference_matrix: Matrice de référence, chaque ligne = une observation

    Returns:
        (combined_score, per_feature_scores):
        - combined_score: Score agrégé
        - per_feature_scores: Score par feature

    Examples:
        >>> # Observation avec montant normal mais concentration anormale
        >>> x = [1000, 0.8]  # [montant, concentration_mois]
        >>> ref = [[1000, 0.2], [1050, 0.15], [980, 0.25], ...]
        >>> score, details = ecod_score_multivariate(x, ref)
    """
    if not reference_matrix or len(reference_matrix[0]) != len(x_vector):
        return (1.0, [1.0] * len(x_vector))

    ref_arr = np.array(reference_matrix)
    n_features = len(x_vector)

    per_feature_scores = []
    for i in range(n_features):
        feature_values = ref_arr[:, i].tolist()
        score = ecod_score_univariate(x_vector[i], feature_values)
        per_feature_scores.append(score)

    # Agrégation: on prend le min (feature la plus anormale)
    # Alternative: produit (plus strict) ou moyenne géométrique
    combined_score = min(per_feature_scores)

    return (combined_score, per_feature_scores)


def ecod_detect_outliers(
    data: List[Dict[str, float]],
    features: List[str],
    threshold: float = 0.05
) -> List[Tuple[int, float, Dict[str, float]]]:
    """
    Détecte les outliers multivariés via ECOD.

    Args:
        data: Liste de dictionnaires avec features
        features: Liste des noms de features à utiliser
        threshold: Seuil de score pour outlier

    Returns:
        Liste de (index, score, feature_scores) pour les outliers
    """
    if len(data) < 3:
        return []

    # Construire la matrice
    matrix = []
    for row in data:
        vector = [row.get(f, 0.0) for f in features]
        matrix.append(vector)

    outliers = []
    for i, row in enumerate(data):
        # Leave-one-out: référence = tous sauf i
        ref_matrix = matrix[:i] + matrix[i+1:]
        x_vector = matrix[i]

        score, feature_scores = ecod_score_multivariate(x_vector, ref_matrix)

        if score < threshold:
            feature_dict = {f: s for f, s in zip(features, feature_scores)}
            outliers.append((i, score, feature_dict))

    return outliers


# =============================================================================
# HELPERS
# =============================================================================

def is_stumpy_available() -> bool:
    """Vérifie si STUMPY est disponible."""
    return STUMPY_AVAILABLE
