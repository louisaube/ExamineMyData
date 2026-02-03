# STORY-209: NLP Keywords Extractor (Couche 4 - Optionnel)

## Métadonnées
- **ID**: STORY-209
- **Epic**: EPIC-204 (Couche 4 - IA optionnelle)
- **Priorité**: Could Have
- **Estimation**: 2 points
- **Dépendances**: STORY-204

## User Story

**En tant que** outil d'analyse,
**Je veux** extraire automatiquement les mots-clés métier des libellés,
**Afin de** identifier l'objet des ABT et provisions sans configuration.

## Contexte

L'extraction de mots-clés aide à :
1. Identifier l'objet des comptes ABT (CFE, prud'hommes, formation...)
2. Catégoriser les provisions
3. Contextualiser les alertes

**Important** : Pas de ML complexe. Juste du pattern matching intelligent.

## Mots-clés cibles

```python
KEYWORDS = {
    # Taxes et impôts
    'CFE': ['CFE', 'cotisation foncière', 'fonciere entreprise'],
    'CVAE': ['CVAE', 'valeur ajoutée', 'valeur ajoutee'],
    'TAXE_FONCIERE': ['taxe foncière', 'taxe fonciere', 'foncier'],
    'TAXE_APPRENTISSAGE': ['apprentissage', 'taxe apprenti'],
    'IS': ['IS', 'impôt société', 'impot societe', 'impôt bénéfice'],

    # Social et RH
    'PRUDHOMMES': ['prud\'homme', 'prudhomme', 'CPH', 'litige salarié'],
    'FORMATION': ['formation', 'OPCO', 'plan formation'],
    'AGEFIPH': ['AGEFIPH', 'handicap', 'OETH'],
    'CONGES_PAYES': ['congés payés', 'conges payes', 'CP'],

    # Audit et conseil
    'CAC': ['CAC', 'commissaire aux comptes', 'commissaire comptes'],
    'EXPERT_COMPTABLE': ['expert comptable', 'expertise comptable'],
    'AVOCAT': ['avocat', 'honoraires avocat', 'frais juridique'],

    # Autres
    'LOYER': ['loyer', 'bail', 'location'],
    'ASSURANCE': ['assurance', 'prime assurance'],
    'MAINTENANCE': ['maintenance', 'entretien', 'contrat maintenance'],
}
```

## Acceptance Criteria

- [ ] Extrait les mots-clés depuis les libellés d'écritures
- [ ] Gère les accents et la casse
- [ ] Retourne le mot-clé le plus probable
- [ ] Fonctionne sans dépendance externe (regex uniquement)
- [ ] Configurable via fichier YAML

## Interface

```python
class NLPKeywordExtractor:
    def __init__(self, keywords_file: str = "data/keywords.yaml")

    def extract(self, libelle: str) -> List[str]
    def extract_best(self, libelle: str) -> Optional[str]
    def categorize(self, libelle: str) -> str  # TAXES, SOCIAL, AUDIT, AUTRE
    def extract_from_series(self, libelles: pd.Series) -> pd.Series
```

## Implémentation (simple)

```python
import re
from unidecode import unidecode

class NLPKeywordExtractor:
    def __init__(self, keywords: dict):
        self.keywords = keywords
        # Pré-compiler les patterns
        self.patterns = {}
        for key, terms in keywords.items():
            pattern = '|'.join(re.escape(t) for t in terms)
            self.patterns[key] = re.compile(pattern, re.IGNORECASE)

    def extract(self, libelle: str) -> List[str]:
        # Normaliser (accents, casse)
        normalized = unidecode(libelle.lower())

        found = []
        for key, pattern in self.patterns.items():
            if pattern.search(normalized) or pattern.search(libelle):
                found.append(key)
        return found

    def extract_best(self, libelle: str) -> Optional[str]:
        found = self.extract(libelle)
        return found[0] if found else None
```

## Tests

```python
def test_extract_cfe():
    assert extractor.extract_best("ABT CFE 2024") == "CFE"
    assert extractor.extract_best("Cotisation foncière") == "CFE"

def test_extract_prudhommes():
    assert extractor.extract_best("Provision prud'hommes") == "PRUDHOMMES"
    assert extractor.extract_best("Litige CPH Dupont") == "PRUDHOMMES"

def test_extract_with_accents():
    assert extractor.extract_best("Congés payés") == "CONGES_PAYES"

def test_no_match():
    assert extractor.extract_best("Achat fournitures") is None

def test_multiple_matches():
    """Si plusieurs mots-clés, retourne le premier."""
```

## Utilisation

```python
# Dans ABTDetector
def get_abt_object(self, df: pd.DataFrame, compte: str) -> str:
    libelles = df[df['compte'] == compte]['libelle'].tolist()
    for libelle in libelles:
        keyword = self.nlp.extract_best(libelle)
        if keyword:
            return keyword
    return "INCONNU"
```

## Notes

- Pas de spaCy, pas de NLTK, pas de transformers
- Juste du regex intelligent
- Configurable sans code (YAML)
- Dépendance unique : `unidecode` pour normaliser les accents
