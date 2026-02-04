"""
GL Crystal - Clustering et Détection d'Outliers

Dans l'espace latent des embeddings:
- Les établissements au fonctionnement similaire DEVRAIENT se regrouper
- Un établissement qui s'éloigne de son cluster signale un comportement atypique
- Un mois qui "saute" dans l'espace latent signale un changement structurel

Utilise HDBSCAN qui détecte automatiquement:
- Le nombre de clusters
- Les points aberrants (outliers)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
import numpy as np

try:
    from sklearn.cluster import HDBSCAN
    HAS_HDBSCAN = True
except ImportError:
    HAS_HDBSCAN = False

from sklearn.cluster import DBSCAN
from sklearn.manifold import TSNE
from sklearn.preprocessing import StandardScaler

from .vectorizer import EmbeddingResult


@dataclass
class ClusterResult:
    """Résultat du clustering pour un embedding."""
    analytique: Optional[str]
    mois: Optional[str]

    # Cluster assigné (-1 = outlier)
    cluster_id: int

    # Distances
    distance_to_centroid: float
    distance_to_nearest_neighbor: float

    # Flags
    is_outlier: bool

    # Coordonnées t-SNE (pour visualisation)
    tsne_x: Optional[float] = None
    tsne_y: Optional[float] = None


@dataclass
class ClusterInfo:
    """Information sur un cluster."""
    cluster_id: int
    n_members: int
    centroid: np.ndarray
    radius: float  # Distance max au centroïde
    members: List[Tuple[str, str]]  # (analytique, mois)

    # Caractéristiques dominantes
    dominant_analytiques: List[str] = field(default_factory=list)
    dominant_mois: List[str] = field(default_factory=list)


class TopologicalClusterer:
    """
    Clustering topologique des embeddings.

    Identifie les groupes d'établissements/mois similaires
    et détecte les outliers.
    """

    def __init__(
        self,
        min_cluster_size: int = 3,
        min_samples: int = 2,
        outlier_threshold: float = 2.0
    ):
        """
        Args:
            min_cluster_size: Taille minimum d'un cluster
            min_samples: Samples minimum pour former un core point
            outlier_threshold: Seuil en écarts-types pour être outlier
        """
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.outlier_threshold = outlier_threshold

        # État
        self.labels_: np.ndarray = None
        self.centroids_: Dict[int, np.ndarray] = {}
        self.tsne_coords_: np.ndarray = None

    def fit_predict(
        self,
        embeddings: List[EmbeddingResult]
    ) -> Tuple[List[ClusterResult], List[ClusterInfo]]:
        """
        Clusterise les embeddings et retourne les résultats.

        Args:
            embeddings: Liste d'EmbeddingResult

        Returns:
            (résultats par embedding, infos par cluster)
        """
        if not embeddings:
            return [], []

        # Extrait les vecteurs
        vectors = np.array([e.vector for e in embeddings])

        # Normalise
        scaler = StandardScaler()
        vectors_scaled = scaler.fit_transform(vectors)

        # Clustering
        if HAS_HDBSCAN:
            clusterer = HDBSCAN(
                min_cluster_size=self.min_cluster_size,
                min_samples=self.min_samples,
            )
        else:
            # Fallback sur DBSCAN
            clusterer = DBSCAN(
                eps=0.5,
                min_samples=self.min_samples,
            )

        self.labels_ = clusterer.fit_predict(vectors_scaled)

        # Calcule les centroïdes par cluster
        unique_labels = set(self.labels_)
        for label in unique_labels:
            if label == -1:
                continue
            mask = self.labels_ == label
            self.centroids_[label] = np.mean(vectors_scaled[mask], axis=0)

        # t-SNE pour visualisation
        if len(vectors) >= 2:
            perplexity = min(30, len(vectors) - 1)
            tsne = TSNE(n_components=2, perplexity=perplexity, random_state=42)
            self.tsne_coords_ = tsne.fit_transform(vectors_scaled)
        else:
            self.tsne_coords_ = np.zeros((len(vectors), 2))

        # Construit les résultats
        results = []
        for i, emb in enumerate(embeddings):
            label = self.labels_[i]
            vector = vectors_scaled[i]

            # Distance au centroïde
            if label != -1 and label in self.centroids_:
                dist_centroid = float(np.linalg.norm(vector - self.centroids_[label]))
            else:
                # Outlier : distance au centroïde global
                dist_centroid = float(np.linalg.norm(vector - np.mean(vectors_scaled, axis=0)))

            # Distance au plus proche voisin
            dists = np.linalg.norm(vectors_scaled - vector, axis=1)
            dists[i] = np.inf  # Exclut soi-même
            dist_nn = float(np.min(dists))

            # Est-ce un outlier ?
            is_outlier = (label == -1)

            # Si dans un cluster, vérifie si trop loin du centroïde
            if not is_outlier and label in self.centroids_:
                cluster_mask = self.labels_ == label
                cluster_dists = np.linalg.norm(
                    vectors_scaled[cluster_mask] - self.centroids_[label],
                    axis=1
                )
                mean_dist = np.mean(cluster_dists)
                std_dist = np.std(cluster_dists)
                if std_dist > 0 and (dist_centroid - mean_dist) / std_dist > self.outlier_threshold:
                    is_outlier = True

            results.append(ClusterResult(
                analytique=emb.analytique,
                mois=emb.mois,
                cluster_id=int(label),
                distance_to_centroid=dist_centroid,
                distance_to_nearest_neighbor=dist_nn,
                is_outlier=is_outlier,
                tsne_x=float(self.tsne_coords_[i, 0]),
                tsne_y=float(self.tsne_coords_[i, 1]),
            ))

        # Construit les infos de cluster
        cluster_infos = self._build_cluster_infos(embeddings, vectors_scaled, results)

        return results, cluster_infos

    def _build_cluster_infos(
        self,
        embeddings: List[EmbeddingResult],
        vectors: np.ndarray,
        results: List[ClusterResult]
    ) -> List[ClusterInfo]:
        """Construit les informations par cluster."""
        infos = []

        for label in sorted(set(self.labels_)):
            if label == -1:
                continue

            mask = self.labels_ == label
            cluster_vectors = vectors[mask]
            cluster_results = [r for r in results if r.cluster_id == label]

            # Membres
            members = [(r.analytique, r.mois) for r in cluster_results]

            # Centroïde et rayon
            centroid = self.centroids_[label]
            dists = np.linalg.norm(cluster_vectors - centroid, axis=1)
            radius = float(np.max(dists))

            # Analytiques et mois dominants
            analytiques = [r.analytique for r in cluster_results if r.analytique]
            mois_list = [r.mois for r in cluster_results if r.mois]

            from collections import Counter
            ana_counts = Counter(analytiques)
            mois_counts = Counter(mois_list)

            dominant_ana = [a for a, _ in ana_counts.most_common(3)]
            dominant_mois = [m for m, _ in mois_counts.most_common(3)]

            infos.append(ClusterInfo(
                cluster_id=label,
                n_members=len(members),
                centroid=centroid,
                radius=radius,
                members=members,
                dominant_analytiques=dominant_ana,
                dominant_mois=dominant_mois,
            ))

        return infos

    def get_outliers(self, results: List[ClusterResult]) -> List[ClusterResult]:
        """Retourne les outliers."""
        return [r for r in results if r.is_outlier]

    def get_cluster_evolution(
        self,
        results: List[ClusterResult],
        analytique: str
    ) -> List[Tuple[str, int]]:
        """
        Retourne l'évolution du cluster pour un analytique au fil des mois.

        Utile pour détecter les "sauts" topologiques.
        """
        evolution = []
        for r in results:
            if r.analytique == analytique and r.mois:
                evolution.append((r.mois, r.cluster_id))
        return sorted(evolution)

    def detect_cluster_jumps(
        self,
        results: List[ClusterResult],
        analytique: str
    ) -> List[Dict]:
        """
        Détecte les changements de cluster (sauts topologiques).

        Un établissement qui passe d'un cluster à un autre signale
        un changement structurel dans ses flux comptables.
        """
        evolution = self.get_cluster_evolution(results, analytique)
        if len(evolution) < 2:
            return []

        jumps = []
        for i in range(1, len(evolution)):
            prev_mois, prev_cluster = evolution[i-1]
            curr_mois, curr_cluster = evolution[i]

            if prev_cluster != curr_cluster:
                jumps.append({
                    'analytique': analytique,
                    'from_mois': prev_mois,
                    'to_mois': curr_mois,
                    'from_cluster': prev_cluster,
                    'to_cluster': curr_cluster,
                    'type': 'outlier' if curr_cluster == -1 else 'cluster_change',
                })

        return jumps


def cluster_embeddings(
    embeddings: List[EmbeddingResult],
    **kwargs
) -> Tuple[List[ClusterResult], List[ClusterInfo]]:
    """
    Fonction utilitaire pour clusteriser des embeddings.
    """
    clusterer = TopologicalClusterer(**kwargs)
    return clusterer.fit_predict(embeddings)


def find_all_cluster_jumps(
    results: List[ClusterResult]
) -> List[Dict]:
    """
    Trouve tous les sauts de cluster pour tous les analytiques.
    """
    # Groupe par analytique
    by_analytique = {}
    for r in results:
        if r.analytique:
            if r.analytique not in by_analytique:
                by_analytique[r.analytique] = []
            by_analytique[r.analytique].append(r)

    # Détecte les sauts
    all_jumps = []
    clusterer = TopologicalClusterer()

    for analytique, ana_results in by_analytique.items():
        jumps = clusterer.detect_cluster_jumps(results, analytique)
        all_jumps.extend(jumps)

    return sorted(all_jumps, key=lambda x: x.get('to_mois', ''))
