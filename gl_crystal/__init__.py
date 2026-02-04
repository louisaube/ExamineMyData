"""
GL CRYSTAL - Moteur d'Analyse Topologique du Grand Livre

Un changement de paradigme : on passe de l'analyse de lignes à l'analyse de topologies.

Architecture:
- normalizer/  : Ingestion et normalisation vers schéma canonique
- layer1_crystallinity/  : Indice de Cristallinité Comptable (ICC)
- layer2_graph/  : Graphe biparti des contreparties
- layer3_embedding/  : Embedding topologique (vectorisation de sets)
- output/  : Visualisations et rapports

Principes fondateurs:
- P1: Le conteneur (compte, analytique), pas la ligne individuelle
- P2: La contrepartie est un certificat d'origine
- P3: Deux topologies (PCG statique vs émergente), un signal
- P4: La comparaison de pairs bat l'algorithme
- P5: Le contrôle dynamique bat le contrôle statique
"""

__version__ = "1.0.0"
