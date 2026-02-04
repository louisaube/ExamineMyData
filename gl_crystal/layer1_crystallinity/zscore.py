"""
GL Crystal - Z-Score par Famille

Le référentiel est relatif aux pairs du même compte G.
C'est la déviation par rapport à la famille qui compte, pas le score absolu.

Un 641 (salaires) devrait être quasi-cristallin (monoculture).
Un 606 (fournitures) peut être naturellement plus divers.

Le z-score mesure si un couple est anormalement amorphe par rapport
aux autres couples de la même famille.
"""

from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import numpy as np
from scipy import stats

from .icc_calculator import ICCScore, CoupleAnalysis


def compute_zscore_par_famille(
    analyses: List[CoupleAnalysis],
    min_pairs: int = 3
) -> Dict[Tuple[str, Optional[str]], float]:
    """
    Calcule le z-score de chaque couple par rapport à sa famille.

    Args:
        analyses: Liste des analyses de couples
        min_pairs: Nombre minimum de pairs pour calculer le z-score

    Returns:
        Dict {(compte, analytique): zscore}
    """
    # Groupe par famille
    by_famille: Dict[str, List[CoupleAnalysis]] = defaultdict(list)
    for analysis in analyses:
        by_famille[analysis.famille].append(analysis)

    # Calcule les z-scores
    zscores = {}

    for famille, famille_analyses in by_famille.items():
        if len(famille_analyses) < min_pairs:
            # Pas assez de pairs
            for a in famille_analyses:
                zscores[(a.compte, a.analytique)] = None
            continue

        # Distribution des ICC dans la famille
        icc_values = [a.icc_score.icc for a in famille_analyses
                      if a.icc_score is not None]

        if len(icc_values) < min_pairs:
            for a in famille_analyses:
                zscores[(a.compte, a.analytique)] = None
            continue

        mean_icc = np.mean(icc_values)
        std_icc = np.std(icc_values)

        if std_icc < 0.01:  # Pas de variation
            for a in famille_analyses:
                zscores[(a.compte, a.analytique)] = 0.0
        else:
            for a in famille_analyses:
                if a.icc_score:
                    z = (a.icc_score.icc - mean_icc) / std_icc
                    zscores[(a.compte, a.analytique)] = float(z)
                else:
                    zscores[(a.compte, a.analytique)] = None

    return zscores


def compute_zscore_multidimensionnel(
    analyses: List[CoupleAnalysis],
    min_pairs: int = 3
) -> Dict[Tuple[str, Optional[str]], float]:
    """
    Calcule le z-score multidimensionnel (Mahalanobis) par famille.

    Prend en compte les 5 axes de l'ICC simultanément plutôt que
    juste le score composite.

    Args:
        analyses: Liste des analyses de couples
        min_pairs: Nombre minimum de pairs

    Returns:
        Dict {(compte, analytique): mahalanobis_distance}
    """
    from scipy.spatial.distance import mahalanobis

    # Groupe par famille
    by_famille: Dict[str, List[CoupleAnalysis]] = defaultdict(list)
    for analysis in analyses:
        by_famille[analysis.famille].append(analysis)

    distances = {}

    for famille, famille_analyses in by_famille.items():
        if len(famille_analyses) < min_pairs:
            for a in famille_analyses:
                distances[(a.compte, a.analytique)] = None
            continue

        # Extrait les vecteurs 5D (scores par axe)
        vectors = []
        for a in famille_analyses:
            if a.icc_score:
                v = [
                    a.icc_score.score_montants,
                    a.icc_score.score_libelles,
                    a.icc_score.score_temporalite,
                    a.icc_score.score_journaux,
                    a.icc_score.score_contreparties,
                ]
                vectors.append(v)

        if len(vectors) < min_pairs:
            for a in famille_analyses:
                distances[(a.compte, a.analytique)] = None
            continue

        # Matrice et covariance
        X = np.array(vectors)
        mean_v = np.mean(X, axis=0)

        try:
            cov = np.cov(X.T)
            if cov.ndim == 0:
                cov = np.array([[cov]])
            cov_inv = np.linalg.inv(cov + np.eye(cov.shape[0]) * 1e-6)
        except np.linalg.LinAlgError:
            # Matrice singulière
            for a in famille_analyses:
                distances[(a.compte, a.analytique)] = None
            continue

        # Calcule la distance de Mahalanobis pour chaque couple
        for i, a in enumerate(famille_analyses):
            if a.icc_score and i < len(vectors):
                try:
                    dist = mahalanobis(vectors[i], mean_v, cov_inv)
                    distances[(a.compte, a.analytique)] = float(dist)
                except:
                    distances[(a.compte, a.analytique)] = None
            else:
                distances[(a.compte, a.analytique)] = None

    return distances


def get_alertes_par_zscore(
    zscores: Dict[Tuple[str, Optional[str]], float],
    threshold: float = -1.5
) -> List[Tuple[str, Optional[str], float]]:
    """
    Retourne les couples avec z-score significativement négatif.

    Un z-score négatif signifie que le couple est plus amorphe que
    la moyenne de sa famille.

    Args:
        zscores: Dict des z-scores par couple
        threshold: Seuil d'alerte (défaut -1.5 = ~6.7% les plus amorphes)

    Returns:
        Liste de (compte, analytique, zscore) triée par zscore
    """
    alertes = []
    for (compte, analytique), z in zscores.items():
        if z is not None and z < threshold:
            alertes.append((compte, analytique, z))

    return sorted(alertes, key=lambda x: x[2])


def compute_famille_stats(
    analyses: List[CoupleAnalysis]
) -> Dict[str, Dict]:
    """
    Calcule les statistiques ICC par famille de comptes.

    Utile pour comprendre le comportement "normal" de chaque famille.

    Returns:
        Dict {famille: {mean, std, median, min, max, n}}
    """
    by_famille: Dict[str, List[float]] = defaultdict(list)
    for a in analyses:
        if a.icc_score:
            by_famille[a.famille].append(a.icc_score.icc)

    stats_by_famille = {}
    for famille, icc_values in by_famille.items():
        if icc_values:
            stats_by_famille[famille] = {
                'mean': float(np.mean(icc_values)),
                'std': float(np.std(icc_values)),
                'median': float(np.median(icc_values)),
                'min': float(np.min(icc_values)),
                'max': float(np.max(icc_values)),
                'n': len(icc_values),
            }
    return stats_by_famille
