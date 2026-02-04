# STORY-207: AlertGenerator - Génération d'alertes contextuelles

## Métadonnées
- **ID**: STORY-207
- **Epic**: EPIC-203 (Couche 3 - Alertes contextuelles)
- **Priorité**: Must Have
- **Estimation**: 3 points
- **Dépendances**: STORY-201 à STORY-206

## User Story

**En tant que** DAF,
**Je veux** 3-5 alertes vraiment utiles,
**Afin de** savoir quoi challenger avec mon expert-comptable.

## Contexte

**v1 générait du bruit** : "114 montants ronds suspects", "26 comptes concentrés en décembre".

**v2 génère du signal** : "Provision prud'hommes 15K non budgétée, libellé 'litige Dupont'".

## Ce qu'on NE signale PAS

| Fausse alerte v1 | Pourquoi c'est normal |
|------------------|----------------------|
| Montant rond sur compte 488 | C'est un ABT (5K × 12) |
| Concentration décembre sur 681 | Amortissements récurrents |
| Creux charges en août | Congés = réalité |
| Volume OD décembre élevé | Normal si ABT + clôture |

## Ce qu'on SIGNALE

| Alerte utile | Contexte |
|--------------|----------|
| Provision non budgétée | Pas d'ABT 488 associé |
| Reprise orpheline | Sans dotation récente |
| Compte nouveau en décembre | Apparition suspecte |
| Changement de comportement | Pattern différent de N-1 |

## Acceptance Criteria

- [ ] Maximum 10 alertes par analyse
- [ ] Chaque alerte a : type, compte, montant, contexte, question
- [ ] Les ABT sont exclus des alertes
- [ ] Les amortissements récurrents sont exclus
- [ ] La saisonnalité août est exclue
- [ ] Priorité 1-3 pour chaque alerte

## Interface

```python
class AlertType(Enum):
    PROVISION_NON_BUDGETEE = "provision_non_budgetee"
    REPRISE_ORPHELINE = "reprise_orpheline"
    COMPTE_NOUVEAU_DECEMBRE = "compte_nouveau_decembre"
    CHANGEMENT_COMPORTEMENT = "changement_comportement"

@dataclass
class Alert:
    type: AlertType
    compte: str
    libelle_compte: str
    montant: float
    mois: int
    libelle_ecriture: str
    contexte: str           # Explication métier
    question: str           # Action suggérée
    priorite: int           # 1 (haute) à 3 (basse)

class AlertGenerator:
    def __init__(self,
                 pcg: PCGClassifier,
                 abt_accounts: List[ABTAccount],
                 provisions: List[ProvisionCouple])

    def generate(self, df: pd.DataFrame) -> List[Alert]
    def filter_noise(self, alerts: List[Alert]) -> List[Alert]
    def prioritize(self, alerts: List[Alert]) -> List[Alert]
```

## Format d'une alerte

```
┌─────────────────────────────────────────────────────────────┐
│ ⚠️ ALERTE #1 - Provision non budgétée              [P1]     │
├─────────────────────────────────────────────────────────────┤
│ Compte   : 6815000 - Provisions pour risques                │
│ Montant  : 15 000 €                                         │
│ Mois     : Décembre uniquement                              │
│ Libellé  : "Provision prud'hommes Dupont"                   │
│                                                             │
│ CONTEXTE:                                                   │
│ • Pas de compte 488 associé → non anticipé dans le budget   │
│ • Première apparition de ce risque dans le GL               │
│ • Impact run rate si récurrent : +15K€/an                   │
│                                                             │
│ QUESTION: Ce litige est-il ponctuel ou récurrent ?          │
│           Si récurrent, prévoir ABT pour N+1.               │
└─────────────────────────────────────────────────────────────┘
```

## Règles de génération

### Provision non budgétée
```python
def detect_unbudgeted_provision(df, abt_accounts):
    """
    Condition:
    - Compte 6815, 687 avec montant significatif
    - Pas de compte 488 associé (même libellé/objet)
    - Apparition ponctuelle (pas mensuelle)
    """
```

### Reprise orpheline
```python
def detect_orphan_reprise(df, provisions):
    """
    Condition:
    - Compte 78x avec reprise significative
    - Pas de dotation 68x correspondante dans les 18 derniers mois
    """
```

### Compte nouveau décembre
```python
def detect_new_december_account(df):
    """
    Condition:
    - Compte qui n'existe pas de janvier à novembre
    - Apparaît uniquement en décembre
    - Montant significatif (> 5K)
    """
```

## Tests

```python
def test_exclude_abt_from_alerts():
    """Les comptes ABT ne génèrent pas d'alerte."""

def test_exclude_amortissements():
    """Les 681 récurrents ne génèrent pas d'alerte."""

def test_detect_unbudgeted_provision():
    """Provision sans ABT = alerte."""

def test_detect_orphan_reprise():
    """Reprise sans dotation = alerte."""

def test_max_10_alerts():
    """Jamais plus de 10 alertes."""

def test_prioritization():
    """Alertes triées par priorité."""
```

## Exemple de sortie

```
Alerts Generated: 4

#1 [P1] Provision non budgétée
   6815000 - 15,000€ - "Prud'hommes Dupont"

#2 [P2] Reprise orpheline
   7816000 - 25,000€ - Sans dotation récente

#3 [P2] Compte nouveau décembre
   648000 - 8,000€ - "Prime exceptionnelle"

#4 [P3] Changement comportement
   615000 - Pattern mensuel → pic décembre
```
