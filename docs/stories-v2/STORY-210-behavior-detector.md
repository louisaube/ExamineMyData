# STORY-210: Behavior Change Detector (Couche 4 - Optionnel)

## Métadonnées
- **ID**: STORY-210
- **Epic**: EPIC-204 (Couche 4 - IA optionnelle)
- **Priorité**: Could Have
- **Estimation**: 2 points
- **Dépendances**: STORY-203

## User Story

**En tant que** outil d'analyse,
**Je veux** détecter si un compte change de comportement entre N-1 et N,
**Afin de** générer une alerte contextuelle utile.

## Contexte

Un compte qui change de pattern est suspect :
- Compte mensuel qui devient annuel
- Compte stable qui devient volatile
- Compte récurrent qui disparaît

**Exemple** : Le compte 615 (entretien) était mensuel en 2023 (≈2K/mois), en 2024 il a un pic de 50K en décembre. Changement de comportement à signaler.

## Types de comportement

| Pattern | Description | Critères |
|---------|-------------|----------|
| MENSUEL | Réparti sur 12 mois | CV < 0.3, 12 mois actifs |
| SAISONNIER | Pics réguliers | CV 0.3-0.7, mois typiques |
| ANNUEL | Concentré sur 1-2 mois | > 60% sur 1-2 mois |
| VARIABLE | Irrégulier | CV > 0.7 |
| DORMANT | Peu d'activité | < 3 mois actifs |

CV = Coefficient de variation (écart-type / moyenne)

## Acceptance Criteria

- [ ] Calcule le pattern pour chaque compte (N et N-1)
- [ ] Compare les patterns N vs N-1
- [ ] Génère une alerte si changement significatif
- [ ] Fournit une description du changement
- [ ] Fonctionne même sans données N-1 (baseline PCG)

## Interface

```python
class BehaviorPattern(Enum):
    MENSUEL = "mensuel"
    SAISONNIER = "saisonnier"
    ANNUEL = "annuel"
    VARIABLE = "variable"
    DORMANT = "dormant"

@dataclass
class AccountBehavior:
    compte: str
    pattern: BehaviorPattern
    cv: float                    # Coefficient de variation
    active_months: int           # Nombre de mois avec activité
    peak_month: Optional[int]    # Mois du pic principal
    peak_pct: float              # % du total sur le pic

@dataclass
class BehaviorChange:
    compte: str
    libelle: str
    pattern_n1: BehaviorPattern
    pattern_n: BehaviorPattern
    description: str
    is_significant: bool

class BehaviorChangeDetector:
    def analyze_behavior(self, df: pd.DataFrame) -> Dict[str, AccountBehavior]
    def compare(self, df_n: pd.DataFrame, df_n1: pd.DataFrame) -> List[BehaviorChange]
    def detect_changes(self, df_n: pd.DataFrame, df_n1: pd.DataFrame) -> List[BehaviorChange]
```

## Algorithme de détection du pattern

```python
def detect_pattern(monthly_amounts: List[float]) -> BehaviorPattern:
    """Détermine le pattern d'un compte."""
    active_months = sum(1 for m in monthly_amounts if m > 0)

    if active_months < 3:
        return BehaviorPattern.DORMANT

    mean = np.mean([m for m in monthly_amounts if m > 0])
    std = np.std([m for m in monthly_amounts if m > 0])
    cv = std / mean if mean > 0 else 0

    max_month_pct = max(monthly_amounts) / sum(monthly_amounts)

    if max_month_pct > 0.6:
        return BehaviorPattern.ANNUEL
    elif cv < 0.3:
        return BehaviorPattern.MENSUEL
    elif cv < 0.7:
        return BehaviorPattern.SAISONNIER
    else:
        return BehaviorPattern.VARIABLE
```

## Tests

```python
def test_detect_mensuel():
    """12 mois à ~10K chacun = mensuel."""
    amounts = [10000] * 12
    assert detect_pattern(amounts) == BehaviorPattern.MENSUEL

def test_detect_annuel():
    """1 mois à 100K, reste à 0 = annuel."""
    amounts = [0] * 11 + [100000]
    assert detect_pattern(amounts) == BehaviorPattern.ANNUEL

def test_detect_change():
    """Compte mensuel en N-1, annuel en N = changement."""
    df_n1 = create_monthly_account_data()  # 12 × 10K
    df_n = create_annual_account_data()    # 11 × 0 + 1 × 120K
    changes = detector.compare(df_n, df_n1)
    assert len(changes) == 1
    assert changes[0].pattern_n1 == BehaviorPattern.MENSUEL
    assert changes[0].pattern_n == BehaviorPattern.ANNUEL

def test_no_change():
    """Même pattern N-1 et N = pas de changement."""
```

## Format de l'alerte générée

```
┌─────────────────────────────────────────────────────────────┐
│ ⚠️ ALERTE - Changement de comportement                      │
├─────────────────────────────────────────────────────────────┤
│ Compte   : 615000 - Entretien et réparations               │
│                                                             │
│ N-1 (2023) : Pattern MENSUEL                               │
│   • Montant moyen : 2,000 €/mois                           │
│   • Variation : faible (CV = 0.15)                         │
│                                                             │
│ N (2024) : Pattern ANNUEL                                  │
│   • Pic décembre : 50,000 € (85% du total)                 │
│   • Variation : très élevée (CV = 2.1)                     │
│                                                             │
│ QUESTION: Ce changement est-il justifié ?                   │
│           (Gros travaux en décembre ? Régularisation ?)     │
└─────────────────────────────────────────────────────────────┘
```

## Notes

- Nécessite les données N-1 pour fonctionner
- Si pas de N-1, utiliser le comportement attendu PCG comme baseline
- Seuil de significativité : changement de catégorie de pattern
