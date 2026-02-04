"""
GL CRYSTAL - Moteur d'Analyse Topologique du Grand Livre

Un changement de paradigme : on passe de l'analyse de lignes à l'analyse de topologies.

Architecture v2.0:
- layer0_classifier/  : Classification sémantique (5 univers) - LE PRÉREQUIS
- normalizer/  : Ingestion et normalisation vers schéma canonique
- layer1_crystallinity/  : Indice de Cristallinité Comptable (ICC) calibré par univers
- layer2_graph/  : Graphe biparti des contreparties
- layer3_embedding/  : Embedding topologique (vectorisation de sets)
- output/  : Visualisations et rapports

Insight central v2.0:
L'entropie sans sa cause ne veut rien dire. Une forte entropie dans un couple
NOMINATIF (facturation familles) est ATTENDUE et bénigne. Une faible entropie
dans un couple COMPOSITE est ANORMALE et suspecte.

Le scoring devient: surprise = |ICC_observé - ICC_attendu_pour_univers|
Le z-score se calcule dans le groupe univers × famille, pas juste famille.

Principes fondateurs:
- P1: Le conteneur (compte, analytique), pas la ligne individuelle
- P2: La contrepartie est un certificat d'origine
- P3: Deux topologies (PCG statique vs émergente), un signal
- P4: La comparaison de pairs bat l'algorithme
- P5: Le contrôle dynamique bat le contrôle statique
- P6: Classifie AVANT de mesurer (v2.0)
"""

__version__ = "2.0.0"

# Layer 0 - Classification sémantique (point d'entrée)
from .layer0_classifier import (
    UniversSemantique,
    UNIVERS_PROFILES,
    SemanticClassifier,
    ClassificationResult,
    ClassificationResults,
    extract_classification_features,
    normalize_proper_nouns,
)
