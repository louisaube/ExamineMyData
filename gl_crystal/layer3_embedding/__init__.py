"""
GL Crystal - Couche 3 : Embedding Topologique

Vectorisation de SETS d'écritures, pas de lignes individuelles.

Grain d'analyse: ensemble d'écritures par (analytique, mois)

Ce qu'on mesure:
- 3a. Matrice de connectivité: A[i,j] = flux de compte i vers compte j
- 3b. Vectorisation SVD: projection dans un espace de dimension k
- 3c. Clustering et anomalies: HDBSCAN, détection d'outliers

Point clé sur la distance:
La distance entre comptes dans l'embedding émergent est une distance FONCTIONNELLE,
pas taxonomique. Le 641 et le 431 seront proches (couplage mécanique paie/charges sociales).

La comparaison entre l'embedding émergent et la hiérarchie PCG révèle:
- Les couplages attendus (641↔431 : mécanique, normal)
- Les couplages inattendus (606↔758 : transfert de charges suspect)
- Les découplages surprenants (deux comptes frères dans le PCG qui ont des
  comportements radicalement différents)
"""

from .connectivity import build_connectivity_matrix, ConnectivityMatrix
from .vectorizer import SVDVectorizer, EmbeddingResult
from .clustering import TopologicalClusterer, ClusterResult
from .topology_compare import TopologyComparator, TopologyDivergence

__all__ = [
    'build_connectivity_matrix',
    'ConnectivityMatrix',
    'SVDVectorizer',
    'EmbeddingResult',
    'TopologicalClusterer',
    'ClusterResult',
    'TopologyComparator',
    'TopologyDivergence',
]
