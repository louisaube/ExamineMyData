"""
GL Crystal - Graphe Biparti des Contreparties

La partie double crée un graphe biparti naturel entre:
- Comptes de résultat (classes 6 et 7) = P&L
- Comptes de bilan (classes 1-5) = Bilan

Ce graphe encode la structure des flux comptables.
Il est gratuit - il est dans le GL par construction.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
import numpy as np

from ..normalizer.schema import GLSchema, EnrichedEntry, NatureCompte


@dataclass
class Arc:
    """
    Arc dirigé dans le graphe des contreparties.

    Représente un flux de compte_source vers compte_dest.
    """
    compte_source: str
    compte_dest: str
    montant: float = 0.0
    n_ecritures: int = 0
    mois: Optional[str] = None
    analytique: Optional[str] = None

    @property
    def key(self) -> Tuple[str, str]:
        return (self.compte_source, self.compte_dest)


@dataclass
class BipartiteGraph:
    """
    Graphe biparti P&L ↔ Bilan.

    Les nœuds sont des comptes.
    Les arcs sont des flux (débit → crédit).
    """
    # Nœuds par partie
    nodes_pnl: Set[str] = field(default_factory=set)      # Classes 6-7
    nodes_bilan: Set[str] = field(default_factory=set)    # Classes 1-5

    # Arcs
    arcs: List[Arc] = field(default_factory=list)

    # Index pour accès rapide
    arcs_by_source: Dict[str, List[Arc]] = field(default_factory=dict)
    arcs_by_dest: Dict[str, List[Arc]] = field(default_factory=dict)

    # Métadonnées
    mois: Optional[str] = None
    analytique: Optional[str] = None
    total_flux: float = 0.0

    def add_arc(self, arc: Arc):
        """Ajoute un arc au graphe."""
        self.arcs.append(arc)
        self.total_flux += arc.montant

        if arc.compte_source not in self.arcs_by_source:
            self.arcs_by_source[arc.compte_source] = []
        self.arcs_by_source[arc.compte_source].append(arc)

        if arc.compte_dest not in self.arcs_by_dest:
            self.arcs_by_dest[arc.compte_dest] = []
        self.arcs_by_dest[arc.compte_dest].append(arc)

    def get_outgoing(self, compte: str) -> List[Arc]:
        """Retourne les arcs sortants d'un compte."""
        return self.arcs_by_source.get(compte, [])

    def get_incoming(self, compte: str) -> List[Arc]:
        """Retourne les arcs entrants vers un compte."""
        return self.arcs_by_dest.get(compte, [])

    def get_contreparties(self, compte: str) -> Set[str]:
        """Retourne les comptes de contrepartie (entrants + sortants)."""
        outgoing = {arc.compte_dest for arc in self.get_outgoing(compte)}
        incoming = {arc.compte_source for arc in self.get_incoming(compte)}
        return outgoing | incoming

    def get_arc_weights(self) -> Dict[Tuple[str, str], float]:
        """Retourne les poids des arcs (montants)."""
        weights = {}
        for arc in self.arcs:
            key = arc.key
            if key not in weights:
                weights[key] = 0.0
            weights[key] += arc.montant
        return weights

    def to_adjacency_matrix(
        self,
        compte_order: Optional[List[str]] = None
    ) -> Tuple[np.ndarray, List[str]]:
        """
        Convertit le graphe en matrice d'adjacence.

        Returns:
            (matrice, liste_des_comptes)
        """
        if compte_order is None:
            all_comptes = self.nodes_pnl | self.nodes_bilan
            compte_order = sorted(all_comptes)

        n = len(compte_order)
        compte_idx = {c: i for i, c in enumerate(compte_order)}
        matrix = np.zeros((n, n))

        for arc in self.arcs:
            i = compte_idx.get(arc.compte_source)
            j = compte_idx.get(arc.compte_dest)
            if i is not None and j is not None:
                matrix[i, j] += arc.montant

        return matrix, compte_order


def build_bipartite_graph(
    schema: GLSchema,
    mois: Optional[str] = None,
    analytique: Optional[str] = None
) -> BipartiteGraph:
    """
    Construit le graphe biparti P&L ↔ Bilan depuis un GLSchema.

    Le graphe capture les flux entre comptes de résultat et comptes de bilan.

    Args:
        schema: GLSchema enrichi (avec contreparties identifiées)
        mois: Filtre par mois (optionnel)
        analytique: Filtre par code analytique (optionnel)

    Returns:
        BipartiteGraph
    """
    graph = BipartiteGraph(mois=mois, analytique=analytique)

    # Filtre les écritures
    entries = schema.entries
    if mois:
        entries = [e for e in entries if e.mois_comptable == mois]
    if analytique:
        entries = [e for e in entries if e.analytique == analytique]

    # Agrège les flux par (source, dest)
    flux: Dict[Tuple[str, str], Dict] = defaultdict(
        lambda: {'montant': 0.0, 'n_ecritures': 0}
    )

    for entry in entries:
        compte = entry.compte_general
        classe = int(compte[0]) if compte and compte[0].isdigit() else 0

        # Classifie le nœud
        if classe in [6, 7]:
            graph.nodes_pnl.add(compte)
        elif classe in [1, 2, 3, 4, 5]:
            graph.nodes_bilan.add(compte)

        # Ajoute les arcs vers les contreparties
        if entry.contrepartie_comptes:
            for cp_compte in entry.contrepartie_comptes:
                cp_classe = int(cp_compte[0]) if cp_compte and cp_compte[0].isdigit() else 0

                # Classifie la contrepartie
                if cp_classe in [6, 7]:
                    graph.nodes_pnl.add(cp_compte)
                elif cp_classe in [1, 2, 3, 4, 5]:
                    graph.nodes_bilan.add(cp_compte)

                # Détermine le sens de l'arc selon débit/crédit
                if entry.debit > 0:
                    # Débit sur le compte, crédit sur la contrepartie
                    source, dest = compte, cp_compte
                    montant = entry.debit
                else:
                    # Crédit sur le compte, débit sur la contrepartie
                    source, dest = cp_compte, compte
                    montant = entry.credit

                key = (source, dest)
                flux[key]['montant'] += montant
                flux[key]['n_ecritures'] += 1

    # Crée les arcs
    for (source, dest), data in flux.items():
        arc = Arc(
            compte_source=source,
            compte_dest=dest,
            montant=data['montant'],
            n_ecritures=data['n_ecritures'],
            mois=mois,
            analytique=analytique,
        )
        graph.add_arc(arc)

    return graph


def build_monthly_graphs(
    schema: GLSchema,
    analytique: Optional[str] = None
) -> Dict[str, BipartiteGraph]:
    """
    Construit un graphe par mois.

    Args:
        schema: GLSchema enrichi
        analytique: Filtre par code analytique (optionnel)

    Returns:
        Dict {mois: BipartiteGraph}
    """
    # Identifie les mois présents
    mois_set = {e.mois_comptable for e in schema.entries if e.mois_comptable}
    if analytique:
        mois_set = {e.mois_comptable for e in schema.entries
                    if e.mois_comptable and e.analytique == analytique}

    # Construit un graphe par mois
    graphs = {}
    for mois in sorted(mois_set):
        graphs[mois] = build_bipartite_graph(schema, mois=mois, analytique=analytique)

    return graphs


def compute_graph_signature(graph: BipartiteGraph) -> Dict[str, float]:
    """
    Calcule la signature d'un graphe pour comparaison.

    La signature capture les propriétés structurelles du graphe.

    Returns:
        Dict de métriques
    """
    n_arcs = len(graph.arcs)
    n_nodes_pnl = len(graph.nodes_pnl)
    n_nodes_bilan = len(graph.nodes_bilan)

    # Degré moyen
    degrees = defaultdict(int)
    for arc in graph.arcs:
        degrees[arc.compte_source] += 1
        degrees[arc.compte_dest] += 1
    avg_degree = np.mean(list(degrees.values())) if degrees else 0

    # Concentration des flux (top 5 arcs / total)
    arc_weights = list(graph.get_arc_weights().values())
    if arc_weights:
        top5 = sorted(arc_weights, reverse=True)[:5]
        concentration = sum(top5) / sum(arc_weights) if sum(arc_weights) > 0 else 0
    else:
        concentration = 0

    return {
        'n_arcs': n_arcs,
        'n_nodes_pnl': n_nodes_pnl,
        'n_nodes_bilan': n_nodes_bilan,
        'total_flux': graph.total_flux,
        'avg_degree': float(avg_degree),
        'concentration_top5': concentration,
    }
