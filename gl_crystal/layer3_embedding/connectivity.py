"""
GL Crystal - Matrice de Connectivité

Pour chaque (établissement, mois), on construit la matrice A où:
A[i,j] = Σ(montants des écritures débit sur compte i, crédit sur compte j)

Cette matrice EST le graphe des contreparties sous forme matricielle.
Sa structure encode la "forme comptable" de l'établissement pour ce mois.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict
import numpy as np

from ..normalizer.schema import GLSchema, EnrichedEntry


@dataclass
class ConnectivityMatrix:
    """
    Matrice de connectivité pour un (analytique, mois).

    La matrice encode les flux entre comptes.
    C'est la représentation matricielle du graphe biparti.
    """
    analytique: Optional[str]
    mois: Optional[str]

    # Matrice et index
    matrix: np.ndarray = None
    compte_to_idx: Dict[str, int] = field(default_factory=dict)
    idx_to_compte: Dict[int, str] = field(default_factory=dict)

    # Métadonnées
    n_comptes: int = 0
    total_flux: float = 0.0
    n_arcs: int = 0

    @property
    def shape(self) -> Tuple[int, int]:
        return self.matrix.shape if self.matrix is not None else (0, 0)

    def get_flux(self, source: str, dest: str) -> float:
        """Retourne le flux entre deux comptes."""
        i = self.compte_to_idx.get(source)
        j = self.compte_to_idx.get(dest)
        if i is None or j is None:
            return 0.0
        return float(self.matrix[i, j])

    def get_outgoing_total(self, compte: str) -> float:
        """Retourne le total des flux sortants d'un compte."""
        i = self.compte_to_idx.get(compte)
        if i is None:
            return 0.0
        return float(np.sum(self.matrix[i, :]))

    def get_incoming_total(self, compte: str) -> float:
        """Retourne le total des flux entrants vers un compte."""
        j = self.compte_to_idx.get(compte)
        if j is None:
            return 0.0
        return float(np.sum(self.matrix[:, j]))

    def get_top_arcs(self, n: int = 10) -> List[Tuple[str, str, float]]:
        """Retourne les N arcs avec le plus gros volume."""
        arcs = []
        for i in range(self.n_comptes):
            for j in range(self.n_comptes):
                if self.matrix[i, j] > 0:
                    source = self.idx_to_compte[i]
                    dest = self.idx_to_compte[j]
                    arcs.append((source, dest, float(self.matrix[i, j])))

        return sorted(arcs, key=lambda x: x[2], reverse=True)[:n]

    def to_sparse_dict(self) -> Dict[Tuple[str, str], float]:
        """Convertit en représentation sparse (dict des arcs non nuls)."""
        sparse = {}
        for i in range(self.n_comptes):
            for j in range(self.n_comptes):
                if self.matrix[i, j] > 0:
                    source = self.idx_to_compte[i]
                    dest = self.idx_to_compte[j]
                    sparse[(source, dest)] = float(self.matrix[i, j])
        return sparse

    def normalize(self, method: str = 'total') -> 'ConnectivityMatrix':
        """
        Retourne une version normalisée de la matrice.

        Args:
            method: 'total' (par flux total), 'row' (par ligne), 'col' (par colonne)
        """
        new_matrix = ConnectivityMatrix(
            analytique=self.analytique,
            mois=self.mois,
            compte_to_idx=self.compte_to_idx.copy(),
            idx_to_compte=self.idx_to_compte.copy(),
            n_comptes=self.n_comptes,
            total_flux=1.0,
            n_arcs=self.n_arcs,
        )

        if method == 'total':
            if self.total_flux > 0:
                new_matrix.matrix = self.matrix / self.total_flux
            else:
                new_matrix.matrix = self.matrix.copy()
        elif method == 'row':
            row_sums = self.matrix.sum(axis=1, keepdims=True)
            row_sums[row_sums == 0] = 1
            new_matrix.matrix = self.matrix / row_sums
        elif method == 'col':
            col_sums = self.matrix.sum(axis=0, keepdims=True)
            col_sums[col_sums == 0] = 1
            new_matrix.matrix = self.matrix / col_sums
        else:
            new_matrix.matrix = self.matrix.copy()

        return new_matrix


def build_connectivity_matrix(
    schema: GLSchema,
    analytique: Optional[str] = None,
    mois: Optional[str] = None,
    compte_filter: Optional[Set[str]] = None,
    min_volume: float = 0.0
) -> ConnectivityMatrix:
    """
    Construit la matrice de connectivité pour un (analytique, mois).

    La matrice A est construite telle que:
    A[i,j] = somme des flux du compte i (au débit) vers le compte j (au crédit)

    Args:
        schema: GLSchema enrichi
        analytique: Code analytique (None = tous)
        mois: Mois comptable (None = tous)
        compte_filter: Ensemble de comptes à inclure (None = tous)
        min_volume: Volume minimum pour inclure un arc

    Returns:
        ConnectivityMatrix
    """
    # Filtre les écritures
    entries = schema.entries
    if analytique:
        entries = [e for e in entries if e.analytique == analytique]
    if mois:
        entries = [e for e in entries if e.mois_comptable == mois]

    # Collecte tous les comptes
    comptes: Set[str] = set()
    for entry in entries:
        comptes.add(entry.compte_general)
        for cp in entry.contrepartie_comptes:
            comptes.add(cp)

    if compte_filter:
        comptes = comptes & compte_filter

    # Tri pour avoir un ordre déterministe
    comptes_sorted = sorted(comptes)
    n = len(comptes_sorted)

    # Index bidirectionnel
    compte_to_idx = {c: i for i, c in enumerate(comptes_sorted)}
    idx_to_compte = {i: c for i, c in enumerate(comptes_sorted)}

    # Construit la matrice
    matrix = np.zeros((n, n))
    flux_dict = defaultdict(float)

    for entry in entries:
        compte = entry.compte_general
        if compte not in compte_to_idx:
            continue

        montant = abs(entry.montant_signe)

        for cp in entry.contrepartie_comptes:
            if cp not in compte_to_idx:
                continue

            # Détermine le sens
            if entry.debit > 0:
                source, dest = compte, cp
            else:
                source, dest = cp, compte

            i = compte_to_idx[source]
            j = compte_to_idx[dest]
            flux_dict[(i, j)] += montant

    # Remplit la matrice (filtre par volume minimum)
    n_arcs = 0
    total_flux = 0.0
    for (i, j), vol in flux_dict.items():
        if vol >= min_volume:
            matrix[i, j] = vol
            total_flux += vol
            if vol > 0:
                n_arcs += 1

    return ConnectivityMatrix(
        analytique=analytique,
        mois=mois,
        matrix=matrix,
        compte_to_idx=compte_to_idx,
        idx_to_compte=idx_to_compte,
        n_comptes=n,
        total_flux=total_flux,
        n_arcs=n_arcs,
    )


def build_all_matrices(
    schema: GLSchema,
    by_analytique: bool = True,
    by_mois: bool = True
) -> Dict[Tuple[Optional[str], Optional[str]], ConnectivityMatrix]:
    """
    Construit les matrices de connectivité pour toutes les combinaisons.

    Args:
        schema: GLSchema enrichi
        by_analytique: Séparer par code analytique
        by_mois: Séparer par mois

    Returns:
        Dict {(analytique, mois): ConnectivityMatrix}
    """
    # Identifie les dimensions
    analytiques = {None}
    mois_set = {None}

    if by_analytique:
        analytiques = {e.analytique for e in schema.entries if e.analytique}
    if by_mois:
        mois_set = {e.mois_comptable for e in schema.entries if e.mois_comptable}

    # Construit chaque matrice
    matrices = {}
    for ana in analytiques:
        for mois in mois_set:
            key = (ana, mois)
            matrices[key] = build_connectivity_matrix(
                schema, analytique=ana, mois=mois
            )

    return matrices


def compute_matrix_similarity(
    m1: ConnectivityMatrix,
    m2: ConnectivityMatrix,
    method: str = 'cosine'
) -> float:
    """
    Calcule la similarité entre deux matrices de connectivité.

    Args:
        m1, m2: Matrices à comparer
        method: 'cosine', 'frobenius', 'jaccard'

    Returns:
        Score de similarité (0 = différent, 1 = identique)
    """
    # Aligne les matrices sur les mêmes comptes
    all_comptes = set(m1.compte_to_idx.keys()) | set(m2.compte_to_idx.keys())
    n = len(all_comptes)
    comptes_sorted = sorted(all_comptes)
    compte_to_idx = {c: i for i, c in enumerate(comptes_sorted)}

    # Reconstruit les matrices alignées
    aligned1 = np.zeros((n, n))
    aligned2 = np.zeros((n, n))

    for (source, dest), vol in m1.to_sparse_dict().items():
        i = compte_to_idx.get(source)
        j = compte_to_idx.get(dest)
        if i is not None and j is not None:
            aligned1[i, j] = vol

    for (source, dest), vol in m2.to_sparse_dict().items():
        i = compte_to_idx.get(source)
        j = compte_to_idx.get(dest)
        if i is not None and j is not None:
            aligned2[i, j] = vol

    if method == 'cosine':
        # Cosine similarity sur les matrices aplaties
        v1 = aligned1.flatten()
        v2 = aligned2.flatten()
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(v1, v2) / (norm1 * norm2))

    elif method == 'frobenius':
        # Similarité basée sur la norme de Frobenius
        # Normalise d'abord
        if m1.total_flux > 0:
            aligned1 = aligned1 / m1.total_flux
        if m2.total_flux > 0:
            aligned2 = aligned2 / m2.total_flux
        diff_norm = np.linalg.norm(aligned1 - aligned2, 'fro')
        max_norm = max(np.linalg.norm(aligned1, 'fro'),
                       np.linalg.norm(aligned2, 'fro'))
        if max_norm == 0:
            return 1.0
        return float(1 - diff_norm / (2 * max_norm))

    elif method == 'jaccard':
        # Jaccard sur les arcs non nuls
        arcs1 = set(m1.to_sparse_dict().keys())
        arcs2 = set(m2.to_sparse_dict().keys())
        if not arcs1 and not arcs2:
            return 1.0
        intersection = len(arcs1 & arcs2)
        union = len(arcs1 | arcs2)
        return intersection / union if union > 0 else 0.0

    return 0.0
