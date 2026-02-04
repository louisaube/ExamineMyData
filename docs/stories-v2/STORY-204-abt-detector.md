# STORY-204: ABTDetector - Détection des mécanismes d'abonnement

## Métadonnées
- **ID**: STORY-204
- **Epic**: EPIC-201 (Couche 1 - Lecture comptable)
- **Priorité**: Must Have
- **Estimation**: 3 points
- **Dépendances**: STORY-201, STORY-203

## User Story

**En tant que** outil d'analyse,
**Je veux** identifier les comptes d'abonnement (488) qui soldent à zéro,
**Afin de** les exclure des anomalies (c'est du bruit budgétaire, pas suspect).

## Contexte

Le mécanisme ABT (Abonnement) est une pratique comptable courante :
1. Chaque mois, le comptable provisionne 1/12 de la charge annuelle prévue
2. En décembre, il contrepasse tout et passe la charge réelle
3. Le compte 488 solde à zéro (ou quasi-zéro) sur l'exercice

**Exemple MicroStars** : 17 comptes ABT pour CFE, CVAE, prud'hommes, formation, CAC, AGEFIPH, taxes foncières, etc.

**Problème v1** : L'outil signalait "montant rond 60K suspect sur 488622900" alors que c'est un ABT de 5K/mois × 12. Absurde.

## Pattern ABT

```
Janvier:   +5,000 (provision 1/12)
Février:   +5,000
...
Novembre:  +5,000
Décembre:  -55,000 (contrepassation)
           +52,000 (charge réelle)
──────────────────
Solde:     ~0 (tolérance 1%)
```

## Acceptance Criteria

- [ ] Identifie tous les comptes 488xxx
- [ ] Calcule pour chaque compte : mouvement total, solde annuel
- [ ] Flagge comme ABT si solde < 1% du mouvement total
- [ ] Extrait l'objet de l'ABT depuis les libellés (CFE, prud'hommes, etc.)
- [ ] Liste les ABT avec leur objet et montant mensuel moyen
- [ ] Ces comptes sont **exclus** des alertes "montant rond suspect"

## Interface

```python
@dataclass
class ABTAccount:
    compte: str
    libelle_compte: str
    objet: str              # CFE, prud'hommes, formation...
    mouvement_total: float  # Somme |debit| + |credit|
    solde_annuel: float     # Doit être ~0
    provision_mensuelle: float  # Montant mensuel moyen
    is_valid_abt: bool      # solde < 1% mouvement
    ecritures_count: int

class ABTDetector:
    def detect(self, df: pd.DataFrame) -> List[ABTAccount]
    def is_abt_account(self, df: pd.DataFrame, compte: str) -> bool
    def get_abt_summary(self, df: pd.DataFrame) -> pd.DataFrame
```

## Extraction de l'objet (NLP léger)

```python
ABT_KEYWORDS = {
    'CFE': ['CFE', 'cotisation foncière'],
    'CVAE': ['CVAE', 'valeur ajoutée'],
    'TAXE_FONCIERE': ['taxe foncière', 'foncier'],
    'PRUDHOMMES': ['prud\'homme', 'prudhomme', 'CPH'],
    'FORMATION': ['formation', 'OPCO'],
    'CAC': ['CAC', 'commissaire aux comptes'],
    'AGEFIPH': ['AGEFIPH', 'handicap'],
    'TAXE_APPRENTISSAGE': ['apprentissage', 'taxe apprenti'],
}

def extract_abt_object(libelles: List[str]) -> str:
    """Extrait l'objet de l'ABT depuis les libellés."""
```

## Tests

```python
def test_detect_valid_abt():
    """Compte 488 avec solde ~0 = ABT valide."""
    df = create_abt_test_data()
    abts = detector.detect(df)
    assert len(abts) > 0
    assert abts[0].is_valid_abt == True

def test_reject_non_abt():
    """Compte 488 avec solde significatif = pas ABT."""
    df = create_non_abt_test_data()  # solde 10K
    abts = detector.detect(df)
    assert abts[0].is_valid_abt == False

def test_extract_object_cfe():
    """Extrait 'CFE' depuis les libellés."""
    libelles = ["ABT CFE 2024", "Provision CFE"]
    assert detector.extract_object(libelles) == "CFE"

def test_microstars_17_abts():
    """Détecte les 17 ABT de MicroStars."""
```

## Exemple de sortie

```
ABT Accounts Detected:
COMPTE       OBJET           PROV/MOIS    SOLDE      VALID
488100100    CFE             5,000 €      -12 €      ✓
488100200    CVAE            3,000 €      +45 €      ✓
488200100    Prud'hommes     4,333 €      0 €        ✓
488300100    Formation       2,500 €      -8 €       ✓
488400100    Taxe foncière   1,200 €      0 €        ✓
...
Total: 17 comptes ABT détectés
```

## Impact sur les alertes

Tous les comptes ABT détectés sont **exclus** de :
- Alerte "montant rond suspect"
- Alerte "concentration décembre"
- Alerte "provision non budgétée"

C'est du bruit budgétaire maîtrisé, pas une anomalie.
