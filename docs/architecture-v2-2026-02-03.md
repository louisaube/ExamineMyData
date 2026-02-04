# Architecture v2 - GL Normalizer

**Date:** 2026-02-03
**Version:** 2.0
**PRD:** [prd-v2-2026-02-03.md](./prd-v2-2026-02-03.md)

---

## 1. Principe directeur

> **"Le bon sens comptable en fondation, l'IA en filet de sécurité."**

---

## 2. Architecture 4 couches

```
┌─────────────────────────────────────────────────────────────┐
│                         RAPPORT                             │
│                    (Excel / Console)                        │
├─────────────────────────────────────────────────────────────┤
│  COUCHE 4 : IA (optionnelle)                               │
│  ┌─────────────┐  ┌─────────────┐                          │
│  │ NLP Keywords│  │ Behavior    │                          │
│  │ Extractor   │  │ Change      │                          │
│  └─────────────┘  └─────────────┘                          │
├─────────────────────────────────────────────────────────────┤
│  COUCHE 3 : Alertes contextuelles                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  AlertGenerator                      │   │
│  │  - Nouvelles provisions non budgétées               │   │
│  │  - Reprises orphelines                              │   │
│  │  - Changements de comportement                      │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  COUCHE 2 : Tableau de passage                   ← COEUR   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │               PassageTableBuilder                    │   │
│  │  - Résultat brut → Résultat normalisé               │   │
│  │  - Retraitements ligne par ligne                    │   │
│  │  - Run rate brut vs normalisé                       │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  COUCHE 1 : Lecture comptable                              │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐  │
│  │  Journal  │ │    PCG    │ │    ABT    │ │   Prov/   │  │
│  │ Classifier│ │ Classifier│ │ Detector  │ │  Reprise  │  │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘  │
├─────────────────────────────────────────────────────────────┤
│                      DATA LAYER                             │
│              (pandas DataFrame, YAML config)                │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Flux de données

```
INPUT: GL Excel
       │
       ▼
┌──────────────────┐
│   GLLoader       │  → DataFrame standardisé
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ COUCHE 1         │
│ Lecture comptable│
│                  │
│ - JournalClassifier: OD/SAL/VTE/ACH/BQ
│ - PCGClassifier: classe, nature, comportement
│ - ABTDetector: comptes 488 qui soldent
│ - ProvisionMatcher: 68x ↔ 78x
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ COUCHE 2         │  ← COEUR
│ Tableau passage  │
│                  │
│ - Calcul retraitements (IS, prov, ABT, except)
│ - Génération tableau mensuel
│ - Génération synthèse annuelle
│ - Calcul run rate brut vs normalisé
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ COUCHE 3         │
│ Alertes          │
│                  │
│ - Filtrage: que les alertes utiles
│ - Contextualisation: libellé, historique
│ - Priorisation: max 5-10 alertes
└──────────────────┘
       │
       ▼ (optionnel)
┌──────────────────┐
│ COUCHE 4         │
│ IA               │
│                  │
│ - NLP: extraction mots-clés libellés
│ - Behavior: détection changement N vs N-1
└──────────────────┘
       │
       ▼
OUTPUT: Rapport Excel
        - Onglet Synthèse (30 sec de lecture)
        - Onglet Tableau passage mensuel
        - Onglet Alertes (3-5 max)
        - Onglet Détail retraitements
```

---

## 4. Composants

### 4.1 GLLoader

**Responsabilité:** Charger le GL et normaliser les colonnes.

```python
class GLLoader:
    def load(self, filepath: str) -> pd.DataFrame
    def detect_format(self, df: pd.DataFrame) -> str  # Sage, Cegid, etc.
    def normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame
```

**Colonnes normalisées:**
- `compte`: str
- `date`: datetime
- `mois`: int (1-12)
- `libelle`: str
- `journal`: str
- `debit`: float
- `credit`: float
- `montant`: float (debit - credit, signé)

---

### 4.2 Couche 1 : Modules de lecture comptable

#### JournalClassifier

```python
class JournalClassifier:
    def classify(self, journal_code: str) -> JournalType
    def get_od_journals(self, df: pd.DataFrame) -> List[str]
    def flag_december_od_spike(self, df: pd.DataFrame) -> bool
```

**JournalType:** OD, PAIE, VENTE, ACHAT, BANQUE, AUTRE

---

#### PCGClassifier

```python
class PCGClassifier:
    def __init__(self, pcg_file: str = "pcg_2025.yaml")

    def classify(self, compte: str) -> PCGInfo
    def get_expected_behavior(self, compte: str) -> Behavior
    def is_provision_account(self, compte: str) -> bool
    def is_reprise_account(self, compte: str) -> bool

@dataclass
class PCGInfo:
    compte: str
    classe: int          # 1-8
    nature: str          # charge, produit, actif, passif
    libelle: str         # Libellé PCG
    is_provision: bool
    is_amortissement: bool
    is_exceptionnel: bool

@dataclass
class Behavior:
    pattern: str         # mensuel, annuel, saisonnier
    typical_month: int   # 12 pour annuel, None pour mensuel
```

---

#### ABTDetector

```python
class ABTDetector:
    """Détecte les comptes d'abonnement (488) qui soldent à zéro."""

    def detect(self, df: pd.DataFrame) -> List[ABTAccount]
    def is_abt_account(self, df: pd.DataFrame, compte: str) -> bool
    def get_abt_object(self, df: pd.DataFrame, compte: str) -> str  # "CFE", "prud'hommes"

@dataclass
class ABTAccount:
    compte: str
    libelle: str           # Extrait des écritures
    total_mouvement: float # Somme |debit| + |credit|
    solde_annuel: float    # Doit être ~0
    objet: str             # CFE, formation, prud'hommes...
    is_valid_abt: bool     # solde < 1% du mouvement
```

**Logique:**
1. Filtrer comptes 488xxx
2. Calculer somme des mouvements et solde
3. Si solde < 1% du mouvement total → ABT valide
4. Extraire l'objet depuis les libellés (NLP léger)

---

#### ProvisionMatcher

```python
class ProvisionMatcher:
    """Couple les provisions (68x) avec leurs reprises (78x)."""

    def match(self, df: pd.DataFrame) -> List[ProvisionCouple]
    def get_net_provision(self, df: pd.DataFrame, compte_68: str) -> float

@dataclass
class ProvisionCouple:
    compte_dotation: str   # 681xxx, 687xxx
    compte_reprise: str    # 781xxx, 787xxx (si existe)
    montant_dotation: float
    montant_reprise: float
    montant_net: float     # dotation - reprise
    is_matched: bool       # Reprise trouvée ?
```

---

### 4.3 Couche 2 : PassageTableBuilder

```python
class PassageTableBuilder:
    """Construit le tableau de passage brut → normalisé."""

    def __init__(self,
                 pcg: PCGClassifier,
                 abt_detector: ABTDetector,
                 provision_matcher: ProvisionMatcher)

    def build_monthly(self, df: pd.DataFrame) -> List[MonthlyPassage]
    def build_annual(self, df: pd.DataFrame) -> AnnualSummary
    def compute_run_rate(self, df: pd.DataFrame) -> RunRate

@dataclass
class Retraitement:
    type: str              # IS, PROVISION, ABT, EXCEPTIONNEL
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
    ecart_pct: float
    retraitements: List[Retraitement]

@dataclass
class RunRate:
    charges_brut_mensuel: float
    charges_normalise_mensuel: float
    produits_brut_mensuel: float
    produits_normalise_mensuel: float
```

**Règles de retraitement:**

| Type | Règle |
|------|-------|
| IS (695) | Redistribuer sur 12 mois |
| Exceptionnel (67/77) | Exclure du run rate |
| Provisions nettes | Prendre le net annuel |
| ABT (488) | Neutraliser le bruit mensuel |
| Amortissements (681) | Ne pas toucher |

---

### 4.4 Couche 3 : AlertGenerator

```python
class AlertGenerator:
    """Génère uniquement les alertes utiles."""

    def generate(self,
                 df: pd.DataFrame,
                 passage: AnnualSummary,
                 abt_accounts: List[ABTAccount],
                 provisions: List[ProvisionCouple]) -> List[Alert]

@dataclass
class Alert:
    type: str              # PROVISION_NON_BUDGETEE, REPRISE_ORPHELINE, etc.
    compte: str
    montant: float
    mois: int
    libelle_extrait: str
    contexte: str          # Explication métier
    question: str          # Action suggérée
    priorite: int          # 1-3

class AlertType(Enum):
    PROVISION_NON_BUDGETEE = "Nouvelle provision sans ABT associé"
    REPRISE_ORPHELINE = "Reprise sans dotation récente"
    COMPTE_NOUVEAU_DECEMBRE = "Compte apparu uniquement en décembre"
    CHANGEMENT_COMPORTEMENT = "Pattern différent de N-1"
    CONCENTRATION_ANORMALE = "Concentration hors pattern attendu"
```

**Filtrage:**
- Maximum 10 alertes
- Exclure les ABT (pas suspect)
- Exclure les amortissements (récurrents)
- Exclure la saisonnalité août (réelle)

---

### 4.5 Couche 4 : IA (optionnelle)

#### NLPKeywordExtractor

```python
class NLPKeywordExtractor:
    """Extrait les mots-clés métier des libellés."""

    KEYWORDS = {
        'taxes': ['CFE', 'CVAE', 'taxe foncière', 'taxe apprentissage'],
        'social': ['prud\'hommes', 'AGEFIPH', 'formation'],
        'audit': ['CAC', 'commissaire'],
        'impot': ['IS', 'impôt société'],
    }

    def extract(self, libelle: str) -> List[str]
    def categorize(self, libelle: str) -> str
```

---

#### BehaviorChangeDetector

```python
class BehaviorChangeDetector:
    """Détecte les changements de comportement N vs N-1."""

    def compare(self, df_n: pd.DataFrame, df_n1: pd.DataFrame) -> List[BehaviorChange]

@dataclass
class BehaviorChange:
    compte: str
    pattern_n1: str        # mensuel, annuel, etc.
    pattern_n: str
    description: str
```

---

### 4.6 Reporter

```python
class ExcelReporter:
    """Génère le rapport Excel final."""

    def generate(self,
                 summary: AnnualSummary,
                 monthly: List[MonthlyPassage],
                 alerts: List[Alert],
                 output_path: str) -> str

# Onglets:
# 1. Synthèse (1 page, 30 sec de lecture)
# 2. Tableau de passage mensuel
# 3. Alertes (3-5 max)
# 4. Détail retraitements
```

---

## 5. Structure du projet

```
gl_normalizer/
├── __init__.py
├── __main__.py
├── cli.py                    # Interface utilisateur
│
├── loader/
│   ├── __init__.py
│   ├── gl_loader.py          # Chargement GL
│   └── formats/              # Détection Sage, Cegid, etc.
│
├── layer1_reading/           # Couche 1
│   ├── __init__.py
│   ├── journal_classifier.py
│   ├── pcg_classifier.py
│   ├── abt_detector.py
│   └── provision_matcher.py
│
├── layer2_passage/           # Couche 2 (COEUR)
│   ├── __init__.py
│   └── passage_table_builder.py
│
├── layer3_alerts/            # Couche 3
│   ├── __init__.py
│   └── alert_generator.py
│
├── layer4_ai/                # Couche 4 (optionnelle)
│   ├── __init__.py
│   ├── nlp_extractor.py
│   └── behavior_detector.py
│
├── output/
│   ├── __init__.py
│   └── excel_reporter.py
│
├── data/
│   └── pcg_2025.yaml         # Référentiel PCG
│
└── config.py
```

---

## 6. Tests (simplifiés)

```
tests/
├── test_layer1_reading.py    # Journaux, PCG, ABT, provisions
├── test_layer2_passage.py    # Tableau de passage (CRITIQUE)
├── test_layer3_alerts.py     # Alertes contextuelles
├── test_integration.py       # Flux complet
└── fixtures/
    ├── gl_microstars.xlsx    # GL réel anonymisé
    └── expected_passage.yaml # Résultat attendu
```

**Estimation:** ~20 tests (vs 78 en v1)

---

## 7. Métriques de validation

| Métrique | Cible | Test |
|----------|-------|------|
| Temps analyse 50k lignes | < 2 min | Benchmark |
| Temps lecture rapport | < 30 sec | User test |
| Fausses alertes | < 3 | Test sur 10 GL |
| Tableau de passage | 100% généré | Test automatisé |
| ABT détectés | 100% | Test sur GL MicroStars |

---

## 8. Ce qui est supprimé de v1

| Module v1 | Statut |
|-----------|--------|
| `analysis/profiler.py` | Supprimé (over-engineering) |
| `analysis/ai/benford.py` | Supprimé |
| `analysis/ai/isolation.py` | Supprimé |
| `analysis/ai/autoencoder.py` | Supprimé |
| `analysis/ai/xgboost_scorer.py` | Supprimé |
| `qualification/qualifier.py` | Simplifié (alertes seulement) |
| `drilldown/` | Supprimé |
| `advanced_stats/` | Supprimé |

---

## 9. Dépendances

### Core (obligatoire)
```
pandas>=2.0
openpyxl>=3.1
pyyaml>=6.0
```

### Optionnel (Couche 4)
```
# Aucune dépendance ML
# NLP fait avec regex simple
```

**Installation légère** : pas de scikit-learn, pas de xgboost, pas de tensorflow.

---

*Document généré par BMAD Method v6 - Phase 3 Solutioning (refonte)*
