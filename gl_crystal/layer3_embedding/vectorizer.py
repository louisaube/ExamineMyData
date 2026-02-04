"""
GL Crystal - Vectorisation SVD

SVD sur la matrice de connectivité: A ≈ UΣV^T

Les k premiers composants capturent les "modes principaux" des flux comptables.
Chaque (établissement, mois) est ainsi représenté par un vecteur de dimension k.

C'est la vectorisation de SETS - on représente un ensemble d'écritures,
pas une ligne individuelle. C'est le changement de paradigme fondamental.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy.linalg import svd

from .connectivity import ConnectivityMatrix, build_connectivity_matrix
from ..normalizer.schema import GLSchema


@dataclass
class EmbeddingResult:
    """
    Vecteur d'embedding pour un (établissement, mois).

    Le vecteur capture la "signature topologique" des flux comptables.
    """
    analytique: Optional[str]
    mois: Optional[str]

    # Vecteur d'embedding
    vector: np.ndarray

    # Composantes SVD (pour interprétation)
    singular_values: np.ndarray = None
    explained_variance_ratio: float = 0.0

    # Métriques
    matrix_rank: int = 0
    total_flux: float = 0.0

    @property
    def dimension(self) -> int:
        return len(self.vector)

    def distance_to(self, other: 'EmbeddingResult', metric: str = 'euclidean') -> float:
        """Calcule la distance à un autre embedding."""
        if metric == 'euclidean':
            return float(np.linalg.norm(self.vector - other.vector))
        elif metric == 'cosine':
            norm1 = np.linalg.norm(self.vector)
            norm2 = np.linalg.norm(other.vector)
            if norm1 == 0 or norm2 == 0:
                return 1.0
            return float(1 - np.dot(self.vector, other.vector) / (norm1 * norm2))
        else:
            return float(np.linalg.norm(self.vector - other.vector))


class SVDVectorizer:
    """
    Vectoriseur basé sur SVD.

    Projette les matrices de connectivité dans un espace de dimension k.
    """

    def __init__(self, k: int = 15, normalize: bool = True):
        """
        Args:
            k: Nombre de composantes à conserver
            normalize: Normaliser les matrices avant SVD
        """
        self.k = k
        self.normalize = normalize

        # État appris (pour projection cohérente)
        self.fitted = False
        self.reference_comptes: List[str] = []
        self.mean_matrix: np.ndarray = None

    def fit_transform(
        self,
        matrices: Dict[Tuple[Optional[str], Optional[str]], ConnectivityMatrix]
    ) -> List[EmbeddingResult]:
        """
        Apprend l'espace d'embedding et transforme les matrices.

        Args:
            matrices: Dict {(analytique, mois): ConnectivityMatrix}

        Returns:
            Liste d'EmbeddingResult
        """
        if not matrices:
            return []

        # Collecte tous les comptes
        all_comptes = set()
        for matrix in matrices.values():
            all_comptes.update(matrix.compte_to_idx.keys())

        self.reference_comptes = sorted(all_comptes)
        n = len(self.reference_comptes)
        compte_to_idx = {c: i for i, c in enumerate(self.reference_comptes)}

        # Aligne toutes les matrices sur les mêmes comptes
        aligned_matrices = []
        keys = list(matrices.keys())

        for key in keys:
            matrix = matrices[key]
            aligned = np.zeros((n, n))

            for (source, dest), vol in matrix.to_sparse_dict().items():
                i = compte_to_idx.get(source)
                j = compte_to_idx.get(dest)
                if i is not None and j is not None:
                    aligned[i, j] = vol

            # Normalise si demandé
            if self.normalize:
                total = np.sum(aligned)
                if total > 0:
                    aligned = aligned / total

            aligned_matrices.append(aligned)

        # Calcule la matrice moyenne (pour centrage)
        stacked = np.stack(aligned_matrices)
        self.mean_matrix = np.mean(stacked, axis=0)

        # Vectorise chaque matrice
        embeddings = []
        for i, key in enumerate(keys):
            ana, mois = key

            # Centre la matrice
            centered = aligned_matrices[i] - self.mean_matrix

            # SVD
            embedding = self._svd_vectorize(centered, matrices[key].total_flux)
            embedding.analytique = ana
            embedding.mois = mois

            embeddings.append(embedding)

        self.fitted = True
        return embeddings

    def transform(self, matrix: ConnectivityMatrix) -> EmbeddingResult:
        """
        Transforme une nouvelle matrice dans l'espace d'embedding appris.

        Requiert un appel préalable à fit_transform.
        """
        if not self.fitted:
            raise ValueError("Vectorizer non entraîné. Appelez fit_transform d'abord.")

        n = len(self.reference_comptes)
        compte_to_idx = {c: i for i, c in enumerate(self.reference_comptes)}

        # Aligne la matrice
        aligned = np.zeros((n, n))
        for (source, dest), vol in matrix.to_sparse_dict().items():
            i = compte_to_idx.get(source)
            j = compte_to_idx.get(dest)
            if i is not None and j is not None:
                aligned[i, j] = vol

        # Normalise
        if self.normalize:
            total = np.sum(aligned)
            if total > 0:
                aligned = aligned / total

        # Centre
        centered = aligned - self.mean_matrix

        # Vectorise
        embedding = self._svd_vectorize(centered, matrix.total_flux)
        embedding.analytique = matrix.analytique
        embedding.mois = matrix.mois

        return embedding

    def _svd_vectorize(
        self,
        matrix: np.ndarray,
        total_flux: float
    ) -> EmbeddingResult:
        """
        Vectorise une matrice centrée via SVD.

        Le vecteur résultant est les k premières valeurs singulières,
        qui capturent les modes principaux des flux.
        """
        try:
            U, sigma, Vt = svd(matrix, full_matrices=False)
        except np.linalg.LinAlgError:
            # Matrice singulière
            k = min(self.k, matrix.shape[0])
            return EmbeddingResult(
                analytique=None,
                mois=None,
                vector=np.zeros(k),
                singular_values=np.zeros(k),
                explained_variance_ratio=0.0,
                matrix_rank=0,
                total_flux=total_flux,
            )

        # Prend les k premières valeurs singulières
        k = min(self.k, len(sigma))
        vector = sigma[:k]

        # Variance expliquée
        total_variance = np.sum(sigma ** 2)
        if total_variance > 0:
            explained = np.sum(vector ** 2) / total_variance
        else:
            explained = 0.0

        # Rang effectif (valeurs singulières > epsilon)
        rank = np.sum(sigma > 1e-10)

        return EmbeddingResult(
            analytique=None,
            mois=None,
            vector=vector,
            singular_values=sigma[:k],
            explained_variance_ratio=explained,
            matrix_rank=int(rank),
            total_flux=total_flux,
        )


def vectorize_gl(
    schema: GLSchema,
    k: int = 15,
    by_analytique: bool = True,
    by_mois: bool = True
) -> Tuple[List[EmbeddingResult], SVDVectorizer]:
    """
    Fonction utilitaire pour vectoriser un GL complet.

    Args:
        schema: GLSchema enrichi
        k: Dimension de l'embedding
        by_analytique: Séparer par code analytique
        by_mois: Séparer par mois

    Returns:
        (liste d'embeddings, vectorizer entraîné)
    """
    from .connectivity import build_all_matrices

    # Construit les matrices
    matrices = build_all_matrices(schema, by_analytique, by_mois)

    # Vectorise
    vectorizer = SVDVectorizer(k=k)
    embeddings = vectorizer.fit_transform(matrices)

    return embeddings, vectorizer


def compute_embedding_statistics(embeddings: List[EmbeddingResult]) -> Dict:
    """
    Calcule des statistiques sur les embeddings.
    """
    if not embeddings:
        return {}

    vectors = np.array([e.vector for e in embeddings])

    # Centroïde
    centroid = np.mean(vectors, axis=0)

    # Dispersion
    distances_to_centroid = [np.linalg.norm(v - centroid) for v in vectors]

    # Variance expliquée moyenne
    mean_explained = np.mean([e.explained_variance_ratio for e in embeddings])

    return {
        'n_embeddings': len(embeddings),
        'dimension': embeddings[0].dimension,
        'centroid': centroid.tolist(),
        'mean_distance_to_centroid': float(np.mean(distances_to_centroid)),
        'std_distance_to_centroid': float(np.std(distances_to_centroid)),
        'max_distance_to_centroid': float(np.max(distances_to_centroid)),
        'mean_explained_variance': float(mean_explained),
    }
