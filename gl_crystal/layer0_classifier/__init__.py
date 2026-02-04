"""
GL Crystal - Couche 0 : Classification Sémantique

C'est le cœur de la v2. Sans classification préalable, tout le reste mesure du bruit.

Avant de mesurer quoi que ce soit, il faut comprendre à quel type d'activité
comptable on a affaire. Cinq univers identifiés empiriquement :

1. CRISTALLIN (14%) - Même opération répétée. Loyer mensuel, abonnement fixe.
   Entropie quasi nulle. Contrôle pertinent : régularité temporelle.

2. NOMINATIF (47.5%) - Entropie élevée en apparence, mais la variation vient
   des noms propres. Facturation familles (97 libellés = 97 noms de famille).
   Contrôle pertinent : arithmétique (N × tarif).

3. INVENTAIRE (2.7%) - Amortissements, provisions par immobilisation.
   Shannon explose mais c'est un calcul déterministe.
   Contrôle pertinent : conformité au tableau d'amortissement.

4. VENTILATION (5%) - Prêts internes, répartitions analytiques.
   Fausse diversité : même flux découpé entre N centres de coût.
   Contrôle pertinent : somme des ventilations = flux source.

5. COMPOSITE (6.1%) - Le vrai bazar. Multi-journaux, multi-natures.
   C'est la seule cible légitime de l'analyse d'entropie approfondie.

Le "non classé" (~25%) est le backlog à qualifier progressivement.
"""

from .univers import UniversSemantique, UNIVERS_PROFILES, UniversProfile
from .features import extract_classification_features, normalize_proper_nouns
from .rules import classify_couple
from .classifier import SemanticClassifier, ClassificationResult, ClassificationResults

__all__ = [
    'UniversSemantique',
    'UNIVERS_PROFILES',
    'UniversProfile',
    'extract_classification_features',
    'normalize_proper_nouns',
    'classify_couple',
    'SemanticClassifier',
    'ClassificationResult',
    'ClassificationResults',
]
