"""
GL Crystal - Couche 1 : Cohérence Interne (ICC)

L'Indice de Cristallinité Comptable mesure l'homogénéité du contenu
d'un couple (compte général, analytique).

Grain d'analyse: couple (compte G, analytique) - pas la ligne individuelle.

5 axes de mesure:
1. Montants: Coefficient de variation décomposé
2. Libellés: Entropie de Shannon sur TF-IDF
3. Temporalité: Autocorrélation + régularité
4. Journaux: Nombre de journaux distincts
5. Contreparties: Concentration (Herfindahl)

Le score ICC est un composite 0-1 où:
- 1 = cristallin (contenu homogène, prévisible)
- 0 = amorphe (contenu hétérogène, chaotique)

Le référentiel est relatif aux pairs du même compte G.
C'est la déviation par rapport à la famille qui compte, pas le score absolu.
"""

from .metrics import (
    compute_cv_decompose,
    compute_entropy_libelles,
    compute_regularite_temporelle,
    compute_diversite_journaux,
    compute_concentration_contreparties,
)
from .icc_calculator import ICCCalculator, ICCScore, CoupleAnalysis
from .zscore import compute_zscore_par_famille

__all__ = [
    'ICCCalculator',
    'ICCScore',
    'CoupleAnalysis',
    'compute_cv_decompose',
    'compute_entropy_libelles',
    'compute_regularite_temporelle',
    'compute_diversite_journaux',
    'compute_concentration_contreparties',
    'compute_zscore_par_famille',
]
