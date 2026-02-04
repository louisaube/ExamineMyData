# STORY-206: PassageTableBuilder - Construction du tableau de passage

## Métadonnées
- **ID**: STORY-206
- **Epic**: EPIC-202 (Couche 2 - Tableau de passage)
- **Priorité**: Must Have (CRITIQUE)
- **Estimation**: 5 points
- **Dépendances**: STORY-201 à STORY-205 (toute la couche 1)

## User Story

**En tant que** DAF,
**Je veux** un tableau de passage clair P&L brut → P&L normalisé,
**Afin de** comprendre mon vrai run rate en 30 secondes.

## Contexte

**C'est LE livrable de l'outil.** Tout le reste existe pour alimenter ce tableau.

Le tableau de passage montre :
1. Le résultat comptable brut
2. Chaque retraitement (IS, provisions, ABT, exceptionnel)
3. Le résultat normalisé
4. Le run rate mensuel

## Règles de retraitement

| Élément | Règle | Justification |
|---------|-------|---------------|
| IS (695) | Étaler sur 12 mois | One-shot non-opérationnel |
| Exceptionnel (67/77) | Exclure | Non récurrent |
| Provisions nettes | Étaler le net | Lisser l'impact |
| ABT (488) | Neutraliser mensuel | Bruit budgétaire |
| Amortissements (681) | Ne pas toucher | Déjà récurrents |
| Saisonnalité août | Ne pas toucher | Effet réel |

## Acceptance Criteria

- [ ] Génère un tableau de passage pour chaque mois
- [ ] Génère une synthèse annuelle
- [ ] Chaque ligne de retraitement est justifiée
- [ ] Calcule le run rate brut vs normalisé
- [ ] Affiche l'écart en valeur et en %
- [ ] Format lisible en 30 secondes

## Interface

```python
@dataclass
class Retraitement:
    type: str               # IS, PROVISION, ABT, EXCEPTIONNEL
    compte: str
    libelle: str
    montant_brut: float
    montant_retraite: float
    justification: str

@dataclass
class MonthlyPassage:
    mois: int
    resultat_brut: float
    retraitements: List[Retraitement]
    resultat_normalise: float

@dataclass
class AnnualSummary:
    charges_brut: float
    charges_normalise: float
    produits_brut: float
    produits_normalise: float
    resultat_brut: float
    resultat_normalise: float
    ecart_valeur: float
    ecart_pct: float
    run_rate_brut: float
    run_rate_normalise: float
    retraitements: List[Retraitement]

class PassageTableBuilder:
    def __init__(self,
                 pcg: PCGClassifier,
                 abt_detector: ABTDetector,
                 provision_matcher: ProvisionMatcher)

    def build_monthly(self, df: pd.DataFrame) -> List[MonthlyPassage]
    def build_annual(self, df: pd.DataFrame) -> AnnualSummary
    def get_run_rate(self, df: pd.DataFrame) -> RunRate
```

## Format du tableau mensuel

```
┌────────────────────────────────────────────────────────────┐
│ TABLEAU DE PASSAGE - DÉCEMBRE 2024                         │
├────────────────────────────────────────────────────────────┤
│ Résultat comptable brut                      -30 000 €     │
├────────────────────────────────────────────────────────────┤
│ RETRAITEMENTS                                              │
│                                                            │
│ (+) IS redistribué (1/12)                   +19 500 €      │
│     695000 - 234K annuel étalé sur 12 mois                │
│                                                            │
│ (+) Provisions créances (net annuel /12)     +1 167 €      │
│     Dotation 82K - Reprise 68K = 14K net                  │
│                                                            │
│ (+) Neutralisation ABT                      +45 000 €      │
│     17 comptes 488 - bruit budgétaire                     │
│                                                            │
│ (-) Exceptionnel net                        -12 000 €      │
│     67xxx: -15K, 77xxx: +3K                               │
├────────────────────────────────────────────────────────────┤
│ = RÉSULTAT NORMALISÉ                        +23 667 €      │
└────────────────────────────────────────────────────────────┘
```

## Format de la synthèse annuelle

```
┌────────────────────────────────────────────────────────────┐
│ SYNTHÈSE RUN RATE - EXERCICE 2024                          │
├────────────────────────────────────────────────────────────┤
│                          BRUT      NORMALISÉ    ÉCART      │
│ Charges mensuelles      897 K€      861 K€      -4%       │
│ Produits mensuels       955 K€      948 K€      -1%       │
│ Résultat annuel         694 K€      917 K€      +32%      │
├────────────────────────────────────────────────────────────┤
│ DÉCOMPOSITION DES RETRAITEMENTS                            │
│                                                            │
│ IS redistribué sur 12 mois                  +234 K€        │
│ Provisions créances (net)                    -14 K€        │
│ Exceptionnel net exclu                        +3 K€        │
│ ABT (neutre sur l'année)                       0 K€        │
│ ────────────────────────────────────────────────────       │
│ Total retraitements                         +223 K€        │
└────────────────────────────────────────────────────────────┘
```

## Tests

```python
def test_is_redistribution():
    """IS de 234K redistribué en 12 × 19.5K."""

def test_provision_net():
    """Provision net calculé correctement."""

def test_abt_neutralized():
    """ABT neutralisé = 0 sur l'année."""

def test_exceptionnel_excluded():
    """67/77 exclus du run rate."""

def test_annual_summary():
    """Synthèse annuelle correcte."""

def test_ecart_calculation():
    """Écart brut/normalisé calculé en % et valeur."""
```

## Notes

Cette story est la plus importante du projet. Le tableau de passage EST le produit.
