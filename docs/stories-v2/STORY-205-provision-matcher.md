# STORY-205: ProvisionMatcher - Couplage provisions/reprises

## Métadonnées
- **ID**: STORY-205
- **Epic**: EPIC-201 (Couche 1 - Lecture comptable)
- **Priorité**: Must Have
- **Estimation**: 2 points
- **Dépendances**: STORY-201, STORY-203

## User Story

**En tant que** outil d'analyse,
**Je veux** coupler chaque dotation (68x) avec sa reprise (78x),
**Afin de** calculer l'impact net des provisions sur le run rate.

## Contexte

Les provisions et reprises doivent être lues **ensemble** :
- Dotation créances douteuses : 82K
- Reprise créances douteuses : 68K
- **Impact net** : +14K de risque

**Problème v1** : L'outil listait séparément dotations et reprises sans calculer le net.

## Règles de couplage

| Dotation | Reprise | Nature |
|----------|---------|--------|
| 6811 | 7811 | Amortissements immo. incorporelles |
| 6812 | 7812 | Amortissements immo. corporelles |
| 6815 | 7815 | Provisions pour risques |
| 6816 | 7816 | Dépréciations immo. |
| 6817 | 7817 | Dépréciations actif circulant |
| 681 | 781 | Amortissements et provisions expl. |
| 686 | 786 | Dotations/reprises financières |
| 687 | 787 | Dotations/reprises exceptionnelles |

## Acceptance Criteria

- [ ] Identifie tous les comptes de dotation (68x)
- [ ] Identifie tous les comptes de reprise (78x)
- [ ] Couple dotation ↔ reprise par suffixe (6815 ↔ 7815)
- [ ] Calcule le montant net (dotation - reprise)
- [ ] Identifie les dotations orphelines (sans reprise)
- [ ] Identifie les reprises orphelines (sans dotation récente)

## Interface

```python
@dataclass
class ProvisionCouple:
    compte_dotation: str
    compte_reprise: Optional[str]
    libelle: str
    montant_dotation: float
    montant_reprise: float
    montant_net: float          # dotation - reprise
    is_matched: bool            # reprise trouvée ?
    is_orphan_reprise: bool     # reprise sans dotation récente ?

class ProvisionMatcher:
    def match(self, df: pd.DataFrame) -> List[ProvisionCouple]
    def get_net_provisions(self, df: pd.DataFrame) -> float
    def get_orphan_reprises(self, df: pd.DataFrame) -> List[ProvisionCouple]
    def get_provisions_summary(self, df: pd.DataFrame) -> pd.DataFrame
```

## Tests

```python
def test_match_simple():
    """6815 dotation 100K + 7815 reprise 60K = net 40K."""
    df = create_provision_test_data()
    couples = matcher.match(df)
    assert couples[0].montant_net == 40_000

def test_orphan_dotation():
    """Dotation sans reprise = orpheline."""
    df = create_orphan_dotation_data()
    couples = matcher.match(df)
    assert couples[0].is_matched == False

def test_orphan_reprise():
    """Reprise sans dotation récente = suspecte."""
    df = create_orphan_reprise_data()
    couples = matcher.match(df)
    assert couples[0].is_orphan_reprise == True

def test_net_calculation():
    """Calcul correct du net provisions."""
```

## Exemple de sortie

```
Provisions/Reprises Analysis:
COMPTE_DOT  COMPTE_REP  LIBELLÉ                DOTATION   REPRISE    NET       STATUS
6815000     7815000     Provisions risques     82,000     68,000     +14,000   Couplé
6817000     -           Dépréc. créances       45,000     0          +45,000   Orpheline
-           7816000     Reprise dépréc. immo   0          25,000     -25,000   ⚠️ Orpheline

Net total provisions: +34,000 €
```

## Alertes générées

Les reprises orphelines génèrent une alerte :
> "Reprise de 25K sur 7816 sans dotation récente. Risque disparu ou opportunisme ?"
