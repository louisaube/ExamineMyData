"""
GL Crystal - Stabilité des Arcs

Mesure la stabilité des arcs mois après mois.

Pour chaque couple (compte, analytique), le profil de contreparties
devrait être stable. Un loyer (613) pointe vers 401-bailleur, 12 mois sur 12.

Si en septembre un arc nouveau apparaît vers 471 (attente) ou vers
un 401 inconnu, c'est un signal.

Métriques:
- Distance de Jaccard entre graphe M et graphe M-1
- Distance de Kullback-Leibler sur la distribution des volumes par arc
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
import numpy as np
from enum import Enum

from .bipartite_graph import BipartiteGraph, build_monthly_graphs
from ..normalizer.schema import GLSchema


class MutationType(Enum):
    """Type de mutation d'arc."""
    NEW_ARC = "new_arc"           # Arc apparu ce mois
    DISAPPEARED = "disappeared"   # Arc disparu ce mois
    VOLUME_SPIKE = "volume_spike" # Volume significativement plus élevé
    VOLUME_DROP = "volume_drop"   # Volume significativement plus bas
    NEW_PATTERN = "new_pattern"   # Nouveau pattern de contreparties


@dataclass
class ArcMutation:
    """
    Mutation détectée sur un arc.

    Représente un changement significatif dans le profil de contreparties.
    """
    mois: str
    compte_source: str
    compte_dest: str
    mutation_type: MutationType
    montant_actuel: float
    montant_precedent: float
    score_anomalie: float  # 0-1, plus haut = plus anormal
    analytique: Optional[str] = None
    description: str = ""

    @property
    def arc_key(self) -> Tuple[str, str]:
        return (self.compte_source, self.compte_dest)


class ArcStabilityAnalyzer:
    """
    Analyseur de stabilité des arcs dans le temps.

    Détecte les mutations (arcs nouveaux, disparus, ou avec volume atypique).
    """

    def __init__(self, volume_threshold: float = 2.0, min_volume: float = 100.0):
        """
        Args:
            volume_threshold: Multiplicateur pour détecter les spikes/drops
            min_volume: Volume minimum pour considérer un arc significatif
        """
        self.volume_threshold = volume_threshold
        self.min_volume = min_volume

    def analyze(
        self,
        schema: GLSchema,
        analytique: Optional[str] = None
    ) -> 'StabilityResults':
        """
        Analyse la stabilité des arcs sur tout l'exercice.

        Args:
            schema: GLSchema enrichi
            analytique: Filtre par code analytique

        Returns:
            StabilityResults avec les mutations détectées
        """
        # Construit les graphes mensuels
        monthly_graphs = build_monthly_graphs(schema, analytique=analytique)
        sorted_months = sorted(monthly_graphs.keys())

        if len(sorted_months) < 2:
            return StabilityResults(mutations=[], monthly_distances=[])

        # Analyse les transitions mois à mois
        mutations = []
        monthly_distances = []

        for i in range(1, len(sorted_months)):
            prev_month = sorted_months[i-1]
            curr_month = sorted_months[i]
            prev_graph = monthly_graphs[prev_month]
            curr_graph = monthly_graphs[curr_month]

            # Distance de Jaccard
            jaccard = self._compute_jaccard_distance(prev_graph, curr_graph)
            monthly_distances.append({
                'from_month': prev_month,
                'to_month': curr_month,
                'jaccard_distance': jaccard,
            })

            # Détecte les mutations
            month_mutations = self._detect_mutations(
                prev_graph, curr_graph, curr_month, analytique
            )
            mutations.extend(month_mutations)

        return StabilityResults(
            mutations=mutations,
            monthly_distances=monthly_distances,
            monthly_graphs=monthly_graphs,
        )

    def _compute_jaccard_distance(
        self,
        graph1: BipartiteGraph,
        graph2: BipartiteGraph
    ) -> float:
        """
        Calcule la distance de Jaccard entre deux graphes.

        Jaccard = 1 - |intersection| / |union|
        Distance = 1 signifie graphes totalement différents
        Distance = 0 signifie graphes identiques
        """
        arcs1 = {arc.key for arc in graph1.arcs}
        arcs2 = {arc.key for arc in graph2.arcs}

        if not arcs1 and not arcs2:
            return 0.0

        intersection = len(arcs1 & arcs2)
        union = len(arcs1 | arcs2)

        return 1.0 - (intersection / union) if union > 0 else 0.0

    def _compute_kl_divergence(
        self,
        graph1: BipartiteGraph,
        graph2: BipartiteGraph
    ) -> float:
        """
        Calcule la divergence de Kullback-Leibler sur les distributions de volumes.

        Mesure combien la distribution des volumes a changé.
        """
        weights1 = graph1.get_arc_weights()
        weights2 = graph2.get_arc_weights()

        # Union des arcs
        all_arcs = set(weights1.keys()) | set(weights2.keys())
        if not all_arcs:
            return 0.0

        # Normalise en distributions
        total1 = sum(weights1.values()) or 1
        total2 = sum(weights2.values()) or 1

        # KL divergence avec smoothing
        epsilon = 1e-10
        kl = 0.0
        for arc in all_arcs:
            p = (weights1.get(arc, 0) / total1) + epsilon
            q = (weights2.get(arc, 0) / total2) + epsilon
            kl += p * np.log(p / q)

        return float(kl)

    def _detect_mutations(
        self,
        prev_graph: BipartiteGraph,
        curr_graph: BipartiteGraph,
        curr_month: str,
        analytique: Optional[str]
    ) -> List[ArcMutation]:
        """Détecte les mutations entre deux mois consécutifs."""
        mutations = []

        prev_arcs = {arc.key: arc for arc in prev_graph.arcs}
        curr_arcs = {arc.key: arc for arc in curr_graph.arcs}

        # Arcs nouveaux
        for key, arc in curr_arcs.items():
            if key not in prev_arcs and arc.montant >= self.min_volume:
                mutations.append(ArcMutation(
                    mois=curr_month,
                    compte_source=arc.compte_source,
                    compte_dest=arc.compte_dest,
                    mutation_type=MutationType.NEW_ARC,
                    montant_actuel=arc.montant,
                    montant_precedent=0.0,
                    score_anomalie=0.8,  # Score élevé pour nouvel arc significatif
                    analytique=analytique,
                    description=f"Nouvel arc {arc.compte_source}→{arc.compte_dest}",
                ))

        # Arcs disparus
        for key, arc in prev_arcs.items():
            if key not in curr_arcs and arc.montant >= self.min_volume:
                mutations.append(ArcMutation(
                    mois=curr_month,
                    compte_source=arc.compte_source,
                    compte_dest=arc.compte_dest,
                    mutation_type=MutationType.DISAPPEARED,
                    montant_actuel=0.0,
                    montant_precedent=arc.montant,
                    score_anomalie=0.6,
                    analytique=analytique,
                    description=f"Arc disparu {arc.compte_source}→{arc.compte_dest}",
                ))

        # Changements de volume significatifs
        for key in prev_arcs.keys() & curr_arcs.keys():
            prev_vol = prev_arcs[key].montant
            curr_vol = curr_arcs[key].montant

            if prev_vol < self.min_volume and curr_vol < self.min_volume:
                continue

            ratio = curr_vol / prev_vol if prev_vol > 0 else float('inf')

            if ratio > self.volume_threshold:
                mutations.append(ArcMutation(
                    mois=curr_month,
                    compte_source=key[0],
                    compte_dest=key[1],
                    mutation_type=MutationType.VOLUME_SPIKE,
                    montant_actuel=curr_vol,
                    montant_precedent=prev_vol,
                    score_anomalie=min(0.9, ratio / 5),  # Score proportionnel
                    analytique=analytique,
                    description=f"Volume x{ratio:.1f} sur {key[0]}→{key[1]}",
                ))
            elif ratio < 1 / self.volume_threshold:
                mutations.append(ArcMutation(
                    mois=curr_month,
                    compte_source=key[0],
                    compte_dest=key[1],
                    mutation_type=MutationType.VOLUME_DROP,
                    montant_actuel=curr_vol,
                    montant_precedent=prev_vol,
                    score_anomalie=min(0.7, (1/ratio) / 5),
                    analytique=analytique,
                    description=f"Volume ÷{1/ratio:.1f} sur {key[0]}→{key[1]}",
                ))

        return mutations


@dataclass
class StabilityResults:
    """Résultats de l'analyse de stabilité."""
    mutations: List[ArcMutation]
    monthly_distances: List[Dict]
    monthly_graphs: Dict[str, BipartiteGraph] = None

    def get_mutations_by_month(self, mois: str) -> List[ArcMutation]:
        """Retourne les mutations d'un mois spécifique."""
        return [m for m in self.mutations if m.mois == mois]

    def get_mutations_by_type(self, mutation_type: MutationType) -> List[ArcMutation]:
        """Retourne les mutations d'un type spécifique."""
        return [m for m in self.mutations if m.mutation_type == mutation_type]

    def get_high_score_mutations(self, threshold: float = 0.7) -> List[ArcMutation]:
        """Retourne les mutations avec score élevé."""
        return [m for m in self.mutations if m.score_anomalie >= threshold]

    def get_average_jaccard(self) -> float:
        """Retourne la distance de Jaccard moyenne."""
        if not self.monthly_distances:
            return 0.0
        return np.mean([d['jaccard_distance'] for d in self.monthly_distances])

    def get_volatility_by_month(self) -> Dict[str, float]:
        """Retourne la volatilité (distance Jaccard) par mois."""
        return {d['to_month']: d['jaccard_distance'] for d in self.monthly_distances}
