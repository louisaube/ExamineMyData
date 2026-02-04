"""
GL Crystal - Couche 2 : Graphe des Contreparties

Exploite la partie double comme système d'information.

La contrepartie n'est pas juste une vérification d'équilibre - c'est un
certificat d'origine qui qualifie la nature économique de l'écriture.

Grain d'analyse: arc dirigé (compte débit → compte crédit) × analytique × mois

Ce qu'on mesure:
- 2a. Stabilité des arcs: le profil de contreparties est-il stable mois après mois?
- 2b. Conformité au template: la contrepartie est-elle dans le pattern attendu?
- 2c. Détection de circuits: les mécanismes ABT/CCA/PCA bouclent-ils correctement?

Graphe biparti naturel:
La partie double crée un graphe biparti entre P&L (6/7) et Bilan (1-5).
Ce graphe est gratuit - il est dans le GL par construction.
"""

from .bipartite_graph import BipartiteGraph, build_bipartite_graph
from .arc_stability import ArcStabilityAnalyzer, ArcMutation
from .circuit_detector import CircuitDetector, Circuit, CircuitType
from .templates import (
    CONTREPARTIE_TEMPLATES,
    check_template_conformity,
    get_atypical_arcs,
)

__all__ = [
    'BipartiteGraph',
    'build_bipartite_graph',
    'ArcStabilityAnalyzer',
    'ArcMutation',
    'CircuitDetector',
    'Circuit',
    'CircuitType',
    'CONTREPARTIE_TEMPLATES',
    'check_template_conformity',
    'get_atypical_arcs',
]
