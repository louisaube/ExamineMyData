# STORY-203: PCGClassifier - Classification PCG des comptes

## Métadonnées
- **ID**: STORY-203
- **Epic**: EPIC-201 (Couche 1 - Lecture comptable)
- **Priorité**: Must Have
- **Estimation**: 2 points
- **Dépendances**: STORY-201

## User Story

**En tant que** outil d'analyse,
**Je veux** connaître la nature comptable de chaque compte,
**Afin de** savoir quel comportement est attendu (récurrent, annuel, etc.).

## Contexte

Le PCG (Plan Comptable Général) définit la nature de chaque compte. Cette connaissance est essentielle pour distinguer :
- Ce qui est **normal** (amortissements mensuels)
- Ce qui est **suspect** (provision décembre sans ABT)

## Classification PCG

| Classe | Nature | Comportement attendu |
|--------|--------|---------------------|
| 60 | Achats | Récurrent, corrélé activité |
| 61-62 | Services ext. | Récurrent ou saisonnier |
| 63 | Impôts/taxes | ABT fréquent (CFE, CVAE) |
| 64 | Personnel | Récurrent, creux août |
| 65 | Autres charges | Variable |
| 66 | Charges fin. | Récurrent |
| 67 | Exceptionnel | **One-shot** |
| 681 | Dot. amort. | Récurrent mensuel |
| 6815, 687 | Dot. provisions | **À analyser** |
| 69 | IS | **One-shot annuel** |
| 70-74 | Produits expl. | Récurrent |
| 77 | Produits except. | **One-shot** |
| 78 | Reprises | **À coupler avec 68** |

## Acceptance Criteria

- [ ] Charge le référentiel PCG depuis `data/pcg_2025.yaml`
- [ ] Classifie chaque compte par classe, nature, comportement
- [ ] Identifie les comptes de provision (681x, 687)
- [ ] Identifie les comptes de reprise (781, 787)
- [ ] Identifie les comptes one-shot (67, 69, 77)
- [ ] Retourne le comportement attendu (mensuel, annuel, variable)

## Interface

```python
@dataclass
class PCGInfo:
    compte: str
    classe: int
    nature: str           # charge, produit
    type_ops: str         # exploitation, financier, exceptionnel
    libelle: str
    is_provision: bool
    is_reprise: bool
    is_amortissement: bool
    is_one_shot: bool
    expected_behavior: str  # mensuel, annuel, variable

class PCGClassifier:
    def __init__(self, pcg_file: str = "data/pcg_2025.yaml")
    def classify(self, compte: str) -> PCGInfo
    def is_provision(self, compte: str) -> bool
    def is_reprise(self, compte: str) -> bool
    def is_one_shot(self, compte: str) -> bool
    def get_expected_behavior(self, compte: str) -> str
```

## Tests

```python
def test_classify_amortissement():
    info = classifier.classify("681100")
    assert info.is_amortissement == True
    assert info.expected_behavior == "mensuel"

def test_classify_provision():
    info = classifier.classify("681500")
    assert info.is_provision == True

def test_classify_is():
    info = classifier.classify("695000")
    assert info.is_one_shot == True
    assert info.expected_behavior == "annuel"

def test_classify_exceptionnel():
    info = classifier.classify("671000")
    assert info.is_one_shot == True
    assert info.type_ops == "exceptionnel"
```

## Fichier PCG (extrait)

```yaml
# data/pcg_2025.yaml
comptes:
  "60":
    libelle: "Achats"
    nature: "charge"
    type: "exploitation"
    behavior: "mensuel"

  "681":
    libelle: "Dotations aux amortissements"
    nature: "charge"
    type: "exploitation"
    behavior: "mensuel"
    is_amortissement: true

  "6815":
    libelle: "Dotations aux provisions"
    nature: "charge"
    type: "exploitation"
    behavior: "variable"
    is_provision: true

  "695":
    libelle: "Impôt sur les bénéfices"
    nature: "charge"
    type: "exploitation"
    behavior: "annuel"
    is_one_shot: true
```
