# STORY-030: Autonomie encadrée de l'IA (Drill-down automatique)

## Métadonnées
- **ID**: STORY-030
- **Sprint**: 7
- **Priorité**: Medium
- **Estimation**: 5 points
- **Dépendances**: STORY-027 (tokens configurés)

## Concept

**"Liberté d'interrogation dans un cadre défini"**

L'idée est de permettre à l'IA d'avoir une autonomie encadrée pour :
1. Identifier des patterns qui méritent investigation
2. Générer automatiquement des questions de drill-down
3. Proposer des analyses complémentaires sans intervention utilisateur
4. Formuler des hypothèses basées sur les données observées

## User Story

**En tant que** analyste financier utilisant GL Normalizer,
**Je veux** que l'IA identifie automatiquement les points nécessitant une investigation approfondie,
**Afin de** ne pas manquer d'anomalies subtiles que je n'aurais pas pensé à chercher.

## Exemples concrets

### Exemple 1 : Détection de pattern suspect
```
L'IA détecte : "Le compte 615000 (Entretien) a un montant de 50,000€
le 28 décembre, alors que la moyenne mensuelle est de 2,000€"

L'IA propose automatiquement :
→ "Voulez-vous voir le détail des écritures du 28/12 sur ce compte ?"
→ "Y a-t-il d'autres comptes avec ce pattern de pic en décembre ?"
→ "Quel est le fournisseur concerné ?"
```

### Exemple 2 : Corrélation inter-comptes
```
L'IA détecte : "Augmentation de 40% des charges de personnel (64x)
mais diminution de 20% des charges sociales (645)"

L'IA propose :
→ "Cette divergence peut indiquer des provisions manquantes"
→ "Voulez-vous vérifier les ratios charges sociales / masse salariale ?"
→ "Comparer avec N-1 pour valider la cohérence ?"
```

### Exemple 3 : Anomalie sectorielle
```
L'IA détecte : "Ratio achats/CA de 78% vs 62% l'année précédente"

L'IA propose :
→ "Analyser l'évolution des prix d'achat ?"
→ "Identifier les fournisseurs avec augmentation significative ?"
→ "Vérifier s'il y a eu des achats exceptionnels ?"
```

## Architecture technique

### 1. Moteur de détection de patterns
```python
class PatternDetector:
    """Identifie les patterns nécessitant investigation"""

    def detect_year_end_spikes(self, df) -> List[Pattern]:
        """Détecte les pics de fin d'année suspects"""

    def detect_ratio_anomalies(self, df) -> List[Pattern]:
        """Détecte les ratios incohérents"""

    def detect_correlation_breaks(self, df) -> List[Pattern]:
        """Détecte les ruptures de corrélation"""
```

### 2. Générateur de questions
```python
class DrilldownGenerator:
    """Génère des questions de drill-down pertinentes"""

    def generate_questions(self, pattern: Pattern) -> List[Question]:
        """Génère des questions basées sur un pattern détecté"""

    def prioritize(self, questions: List[Question]) -> List[Question]:
        """Priorise les questions par pertinence"""
```

### 3. Exécuteur de drill-down
```python
class DrilldownExecutor:
    """Exécute les analyses demandées"""

    def execute(self, question: Question, df: DataFrame) -> DrilldownResult:
        """Exécute l'analyse et retourne les résultats"""
```

## Contraintes (le "cadre")

L'IA opère dans des limites définies :

| Contrainte | Description |
|------------|-------------|
| **Périmètre données** | Uniquement le fichier GL fourni |
| **Types d'analyses** | Liste prédéfinie (pas de code arbitraire) |
| **Profondeur** | Max 3 niveaux de drill-down |
| **Temps** | Max 30 secondes par analyse |
| **Confidentialité** | Aucune donnée envoyée à l'extérieur sans accord |

## Interface utilisateur

### Option 1 : Questions interactives
```
┌─────────────────────────────────────────────────────────┐
│ 🔍 L'IA a identifié 3 points à investiguer            │
│                                                         │
│ 1. Pic de 50K€ sur le compte 615000 le 28/12          │
│    [Voir détail] [Ignorer]                             │
│                                                         │
│ 2. Divergence charges sociales / masse salariale       │
│    [Analyser] [Ignorer]                                │
│                                                         │
│ 3. Ratio achats/CA en hausse de 16 points             │
│    [Investiguer] [Ignorer]                             │
└─────────────────────────────────────────────────────────┘
```

### Option 2 : Mode automatique
L'utilisateur peut activer un mode où l'IA exécute automatiquement
les 5 premières questions prioritaires et affiche les résultats.

## Critères d'acceptation

- [x] Détection automatique d'au moins 5 types de patterns
- [x] Génération de questions pertinentes (>80% jugées utiles)
- [x] Interface claire pour accepter/refuser les analyses
- [x] Temps de réponse < 5 secondes par question
- [x] Mode batch pour analyse automatique
- [ ] Log des analyses proposées/acceptées pour amélioration

## Tâches

- [x] Concevoir le moteur de détection de patterns (`pattern_detector.py`)
- [x] Implémenter les générateurs de questions (`autonomous_drilldown.py`)
- [x] Créer l'interface de drill-down interactif (`results.html`)
- [x] Ajouter API endpoints (`/api/drilldown/`)
- [ ] Intégrer avec les providers IA (OpenAI/Anthropic) - future iteration
- [ ] Tests utilisateurs pour valider la pertinence

## Notes

Cette feature transforme l'outil d'un "analyseur passif" en un
"assistant analytique proactif" qui guide l'utilisateur vers
les zones à risque sans lui imposer d'analyse particulière.

L'autonomie est "encadrée" car :
- L'IA ne peut pas accéder à des données externes
- Chaque action doit être validée par l'utilisateur (sauf mode auto)
- Les types d'analyses sont prédéfinis et auditables
- L'utilisateur garde le contrôle final
