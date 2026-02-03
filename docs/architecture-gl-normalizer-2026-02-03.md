# Architecture Document
# GL Normalizer (ExamineMyData)

**Date:** 2026-02-03
**Version:** 1.0
**Project:** ExamineMyData
**Type:** Python CLI Tool
**Level:** 2 (Medium feature set)
**PRD:** [docs/prd-gl-normalizer-2026-02-03.md](./prd-gl-normalizer-2026-02-03.md)

---

## 1. Executive Summary

Ce document décrit l'architecture technique de **GL Normalizer**, un outil Python CLI open source qui analyse les exports Grand Livre (GL) pour détecter les anomalies comptables et calculer le vrai run rate opérationnel.

### Architectural Pattern

**Layered Architecture (Monolith Python)** - Simple, maintenable, adapté à un outil CLI open source.

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pattern | Layered Monolith | Simplicité, maintenabilité, projet solo |
| Language | Python 3.9+ | Écosystème data science, NFR-009 |
| Data | pandas DataFrames | Standard manipulation données tabulaires |
| Context | PCG + Plan de compte | Contextualisation comptable des anomalies |
| IA | Optionnel (scikit-learn) | Enrichissement sans dépendance obligatoire |

---

## 2. Architectural Drivers

Les NFRs qui influencent le plus l'architecture :

| NFR | Driver | Impact |
|-----|--------|--------|
| **NFR-001** | Analyse < 10 min (50k lignes) | Optimisation pandas, vectorisation |
| **NFR-005** | 100% recall (zéro faux négatif) | Détection exhaustive, seuils conservateurs |
| **NFR-006** | Faux positifs → 0% | Contextualisation PCG, qualification fine |
| **NFR-003** | Utilisable sans formation | Messages clairs, workflow guidé |
| **NFR-009** | Python 3.9+ | Compatibilité libs |

**Driver principal** : Équilibre entre **exhaustivité** (100% recall) et **précision** (zéro bruit), grâce au contexte comptable (PCG).

---

## 3. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI / Entry                              │
│                    (main.py, argparse/click)                     │
├─────────────────────────────────────────────────────────────────┤
│                        Orchestrator                              │
│              (workflow, coordination des modules)                │
├───────────────────┬─────────────────────┬───────────────────────┤
│      CONTEXT      │      ANALYSIS       │        OUTPUT         │
├───────────────────┼─────────────────────┼───────────────────────┤
│                   │                     │                       │
│  ┌─────────────┐  │  ┌───────────────┐  │  ┌─────────────────┐  │
│  │   Loader    │  │  │   Profiler    │  │  │   Qualifier     │  │
│  │  (Excel,    │  │  │  (stats par   │  │  │  (questions,    │  │
│  │   formats)  │  │  │   colonne)    │  │  │  justifications)│  │
│  └─────────────┘  │  └───────────────┘  │  └─────────────────┘  │
│                   │                     │                       │
│  ┌─────────────┐  │  ┌───────────────┐  │  ┌─────────────────┐  │
│  │ Accounting  │  │  │   Detector    │  │  │   Normalizer    │  │
│  │  Context    │  │  │  (anomalies   │  │  │  (run rate,     │  │
│  │ (PCG, plan  │  │  │  + contexte)  │  │  │   dispatch)     │  │
│  │ de compte)  │  │  │               │  │  │                 │  │
│  └─────────────┘  │  └───────────────┘  │  └─────────────────┘  │
│                   │                     │                       │
│                   │  ┌───────────────┐  │  ┌─────────────────┐  │
│                   │  │  AI Module    │  │  │    Reporter     │  │
│                   │  │  (profil IA,  │  │  │   (Excel)       │  │
│                   │  │   optionnel)  │  │  │                 │  │
│                   │  └───────────────┘  │  └─────────────────┘  │
│                   │                     │                       │
├───────────────────┴─────────────────────┴───────────────────────┤
│                        Data Layer                                │
│              (pandas DataFrames, YAML config, I/O)               │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. INPUT
   User → CLI → Loader
              ↓
   Excel GL File → DataFrame (gl_data)

2. CONTEXT
   AccountingContext → PCG / Plan de compte
   Profiler → Stats par colonne, profil par compte
              ↓
   Contexte comptable enrichi

3. ANALYSIS
   Profiler → Profil statistique (baseline)
   AI Module → Profil comptable attendu vs réel
   Detector → Anomalies contextualisées
              ↓
   DataFrame (anomalies)

4. QUALIFICATION
   Qualifier → Questions avec contexte PCG
   User → Réponses, justifications
              ↓
   Anomalies qualifiées + sauvegarde YAML

5. OUTPUT
   Normalizer → Run rate dépollué
   Reporter → Rapport Excel
              ↓
   User ← Fichier Excel final
```

---

## 4. Technology Stack

### Core

| Category | Technology | Version | Rationale |
|----------|------------|---------|-----------|
| **Language** | Python | 3.9+ | NFR-009, écosystème data |
| **Data Processing** | pandas | 2.0+ | Standard manipulation tabulaire |
| **Numerical** | numpy | 1.24+ | Calculs vectorisés |
| **Excel I/O** | openpyxl | 3.1+ | Lecture/écriture Excel native |
| **Statistics** | scipy | 1.10+ | Z-scores, distributions |
| **Config** | PyYAML | 6.0+ | Sauvegarder justifications |
| **CLI** | click | 8.0+ | Interface utilisateur CLI |

### Optional (IA)

| Category | Technology | Version | Rationale |
|----------|------------|---------|-----------|
| **ML** | scikit-learn | 1.3+ | Isolation Forest |
| **Gradient Boosting** | xgboost | 2.0+ | Classification risque |
| **NLP** | spaCy / regex | - | Analyse libellés |

### Development

| Category | Technology | Rationale |
|----------|------------|-----------|
| **Testing** | pytest | Standard Python |
| **Coverage** | pytest-cov | NFR-008 |
| **Linting** | black, flake8, mypy | NFR-007 |
| **CI** | GitHub Actions | Open source friendly |

---

## 5. System Components

### 5.1 Loader

**Purpose:** Charger et parser les fichiers GL Excel multi-formats.

**Responsibilities:**
- Charger fichiers .xlsx, .xls
- Détecter automatiquement le format (Sage, Cegid, Quadratus, EBP)
- Mapper les colonnes (auto ou manuel)
- Valider les colonnes obligatoires
- Normaliser les types de données

**Interface:**
```python
class Loader:
    def load(self, filepath: str) -> pd.DataFrame
    def detect_format(self, df: pd.DataFrame) -> str
    def map_columns(self, df: pd.DataFrame, mapping: dict) -> pd.DataFrame
    def validate(self, df: pd.DataFrame) -> ValidationResult
```

**FRs Addressed:** FR-001, FR-002, FR-003

---

### 5.2 AccountingContext

**Purpose:** Fournir le contexte comptable (PCG, plan de compte) pour contextualiser les analyses.

**Responsibilities:**
- Charger le PCG (Plan Comptable Général) français
- Charger un plan de compte personnalisé (optionnel)
- Classifier les comptes (classe, nature, type)
- Définir le comportement attendu par compte
- Valider les comptes contre le référentiel

**Interface:**
```python
class AccountingContext:
    def load_pcg(self, version: str = "2025") -> pd.DataFrame
    def load_custom_plan(self, filepath: str) -> pd.DataFrame
    def classify_account(self, compte: str) -> AccountClassification
    def get_expected_behavior(self, compte: str) -> ExpectedBehavior
    def validate_account(self, compte: str) -> bool
    def get_account_info(self, compte: str) -> AccountInfo
```

**Data Model - PCG:**
```python
@dataclass
class AccountClassification:
    compte: str
    classe: int           # 1-8
    nature: str           # actif, passif, charge, produit
    type: str             # exploitation, financier, exceptionnel
    libelle_pcg: str      # Libellé officiel PCG
    is_provision: bool    # Compte de provision ?
    is_amortissement: bool

@dataclass
class ExpectedBehavior:
    compte: str
    pattern: str          # mensuel, annuel, trimestriel, variable
    typical_month: int    # Mois typique (12 pour décembre, None si mensuel)
    volatility: str       # low, medium, high
    description: str
```

**FRs Addressed:** Nouveau (enrichit FR-004 à FR-008)

---

### 5.3 Profiler

**Purpose:** Analyser statistiquement les données GL pour établir un profil de référence.

**Responsibilities:**
- Profiler chaque colonne (type, null%, unique, distribution)
- Profiler chaque compte (total, nb écritures, volatilité)
- Détecter les problèmes de qualité des données
- Calculer le profil attendu (baseline)
- Identifier les patterns saisonniers

**Interface:**
```python
class Profiler:
    def profile_columns(self, df: pd.DataFrame) -> ColumnProfile
    def profile_accounts(self, df: pd.DataFrame) -> pd.DataFrame
    def detect_data_quality_issues(self, df: pd.DataFrame) -> List[QualityIssue]
    def compute_baseline(self, df: pd.DataFrame) -> BaselineProfile
    def detect_seasonality(self, df: pd.DataFrame) -> SeasonalityProfile
```

**FRs Addressed:** Nouveau (enrichit détection)

---

### 5.4 Detector

**Purpose:** Détecter les anomalies comptables en utilisant le contexte et le profil.

**Responsibilities:**
- Détecter concentrations mensuelles anormales
- Calculer Z-scores par compte/mois
- Identifier les écritures de provisions
- Détecter montants ronds suspects
- Analyser journaux OD/situation
- **Contextualiser** avec le comportement attendu (PCG)

**Interface:**
```python
class Detector:
    def __init__(self, context: AccountingContext, profiler: Profiler)

    def detect_all(self, df: pd.DataFrame) -> pd.DataFrame
    def detect_concentrations(self, df: pd.DataFrame) -> List[Anomaly]
    def detect_zscore_outliers(self, df: pd.DataFrame) -> List[Anomaly]
    def detect_provisions(self, df: pd.DataFrame) -> List[Anomaly]
    def detect_round_amounts(self, df: pd.DataFrame) -> List[Anomaly]
    def detect_od_patterns(self, df: pd.DataFrame) -> List[Anomaly]

    def contextualize_anomaly(self, anomaly: Anomaly) -> ContextualizedAnomaly
```

**Contextualisation:**
```python
@dataclass
class ContextualizedAnomaly:
    anomaly: Anomaly
    expected_behavior: ExpectedBehavior
    deviation_from_expected: str
    pcg_context: str           # Info du PCG sur ce compte
    severity_adjusted: float   # Score ajusté selon contexte
    question_suggested: str    # Question suggérée pour qualification
```

**FRs Addressed:** FR-004, FR-005, FR-006, FR-007, FR-008

---

### 5.5 AIModule (Optionnel)

**Purpose:** Enrichir la détection avec des techniques IA avancées.

**Responsibilities:**
- Loi de Benford (montants fabriqués)
- Isolation Forest (anomalies non supervisées)
- Analyse NLP des libellés
- Établir le profil comptable IA (attendu vs réel)
- Scorer les anomalies par ML

**Interface:**
```python
class AIModule:
    def benford_analysis(self, amounts: pd.Series) -> BenfordResult
    def isolation_forest(self, df: pd.DataFrame) -> pd.DataFrame
    def nlp_analyze_labels(self, labels: pd.Series) -> pd.DataFrame
    def compute_expected_profile(self, df: pd.DataFrame) -> AIProfile
    def score_anomalies(self, anomalies: pd.DataFrame) -> pd.DataFrame
```

**FRs Addressed:** FR-016, FR-017, FR-018

---

### 5.6 Qualifier

**Purpose:** Gérer le workflow de qualification des anomalies par l'utilisateur.

**Responsibilities:**
- Sélectionner les top N anomalies à qualifier
- Présenter les questions avec contexte PCG
- Collecter les réponses et commentaires
- Sauvegarder les justifications (YAML)
- Charger les justifications précédentes

**Interface:**
```python
class Qualifier:
    def select_top_anomalies(self, anomalies: pd.DataFrame, n: int = 10) -> pd.DataFrame
    def generate_question(self, anomaly: ContextualizedAnomaly) -> Question
    def present_questions(self, anomalies: pd.DataFrame) -> List[QualificationResult]
    def save_justifications(self, results: List[QualificationResult], filepath: str)
    def load_justifications(self, filepath: str) -> List[QualificationResult]
```

**Question Format:**
```python
@dataclass
class Question:
    anomaly_id: int
    compte: str
    compte_libelle: str       # Du PCG
    anomaly_type: str
    anomaly_description: str
    pcg_context: str          # "Selon le PCG, ce compte est..."
    expected_behavior: str    # "Comportement attendu: mensuel"
    actual_behavior: str      # "Comportement observé: 80% en décembre"
    question_text: str        # Question formatée
    options: List[str]        # ["Justifié", "Non justifié", "À investiguer"]
```

**FRs Addressed:** FR-009, FR-010, FR-011

---

### 5.7 Normalizer

**Purpose:** Calculer le run rate réel et neutraliser les anomalies.

**Responsibilities:**
- Calculer run rate mensuel (total/12)
- Neutraliser les anomalies qualifiées
- Dispatcher sur période (redistribution)
- Calculer le P&L dépollué

**Interface:**
```python
class Normalizer:
    def calculate_run_rate(self, df: pd.DataFrame) -> pd.DataFrame
    def neutralize_anomalies(self, df: pd.DataFrame, qualified: pd.DataFrame) -> pd.DataFrame
    def dispatch_on_period(self, amount: float, months: List[int]) -> Dict[int, float]
    def compute_clean_pnl(self, df: pd.DataFrame) -> pd.DataFrame
```

**FRs Addressed:** FR-012, FR-013

---

### 5.8 Reporter

**Purpose:** Générer le rapport Excel final.

**Responsibilities:**
- Créer rapport multi-onglets
- Onglet "Anomalies" avec scores et statuts
- Onglet "Run Rate" avec comparatif
- Onglet "Détail" avec écritures flaggées
- Onglet "Contexte PCG" avec infos référentiel
- Mise en forme conditionnelle

**Interface:**
```python
class Reporter:
    def generate_report(self,
                       gl_data: pd.DataFrame,
                       anomalies: pd.DataFrame,
                       run_rate: pd.DataFrame,
                       context: AccountingContext,
                       output_path: str) -> str
```

**FRs Addressed:** FR-014, FR-015

---

## 6. Data Architecture

### 6.1 Core DataFrames

**gl_data (DataFrame principal)**
```
├── compte: str           # Numéro de compte (ex: "681000")
├── date: datetime        # Date de l'écriture
├── mois: int             # Mois (1-12)
├── libelle: str          # Libellé de l'écriture
├── journal: str          # Code journal (ex: "OD", "VE")
├── montant: float        # Montant signé
├── debit: float          # Montant débit
├── credit: float         # Montant crédit
└── [colonnes enrichies]
    ├── classe: int                # Classe PCG (1-8)
    ├── nature: str                # charge, produit, actif, passif
    ├── compte_libelle: str        # Libellé PCG
    ├── expected_behavior: str     # Comportement attendu
    ├── z_score: float             # Z-score calculé
    ├── is_provision: bool         # Est une provision ?
    ├── is_anomaly: bool           # Flaggé comme anomalie ?
    ├── anomaly_type: str          # Type d'anomalie
    └── anomaly_score: float       # Score de l'anomalie
```

**anomalies (DataFrame)**
```
├── id: int               # ID unique
├── compte: str           # Compte concerné
├── compte_libelle: str   # Libellé PCG
├── mois: int             # Mois concerné (ou None si annuel)
├── type: str             # concentration, zscore, provision, round, od
├── description: str      # Description de l'anomalie
├── score: float          # Score de gravité (0-100)
├── montant_impact: float # Impact en euros
├── pcg_context: str      # Contexte PCG
├── expected_behavior: str# Comportement attendu
├── actual_behavior: str  # Comportement observé
├── status: str           # pending, justified, unjustified, investigate
├── comment: str          # Commentaire utilisateur
└── qualified_at: datetime# Date de qualification
```

**run_rate (DataFrame)**
```
├── compte: str           # Numéro de compte
├── compte_libelle: str   # Libellé PCG
├── classe: int           # Classe PCG
├── jan..dec: float       # Montants mensuels (12 colonnes)
├── total_brut: float     # Total annuel brut
├── total_ajuste: float   # Total après neutralisation
├── run_rate_brut: float  # total_brut / 12
├── run_rate_ajuste: float# total_ajuste / 12
├── ecart_dec: float      # décembre - run_rate
└── pct_dec: float        # % de décembre sur total
```

**pcg (DataFrame référentiel)**
```
├── compte: str           # Numéro de compte
├── libelle: str          # Libellé officiel
├── classe: int           # Classe (1-8)
├── nature: str           # actif, passif, charge, produit
├── type: str             # exploitation, financier, exceptionnel
├── is_provision: bool    # Compte de provision
├── is_amortissement: bool# Compte d'amortissement
├── expected_pattern: str # mensuel, annuel, variable
└── typical_month: int    # Mois typique (12 pour annuel)
```

### 6.2 Persistence (YAML)

**justifications.yaml**
```yaml
version: "1.0"
generated_at: "2026-02-03T10:00:00Z"
gl_file: "GL_2025.xlsx"
justifications:
  - anomaly_id: 1
    compte: "681000"
    type: "concentration"
    status: "justified"
    comment: "Dotation annuelle normale"
    qualified_at: "2026-02-03T10:15:00Z"
  - anomaly_id: 2
    compte: "617000"
    type: "zscore"
    status: "unjustified"
    comment: "À revoir avec le service achat"
    qualified_at: "2026-02-03T10:17:00Z"
```

---

## 7. NFR Coverage

### NFR-001: Performance (< 10 min pour 50k lignes)

**Solution:**
- Utilisation de pandas vectorisé (pas de boucles Python)
- Chargement optimisé avec openpyxl (read_only mode)
- Calculs Z-scores via numpy (vectorisé)
- Pas de recalcul inutile (caching intermédiaire)

**Implementation Notes:**
```python
# Bon: vectorisé
df['z_score'] = (df['montant'] - df.groupby('compte')['montant'].transform('mean')) / \
                df.groupby('compte')['montant'].transform('std')

# Mauvais: boucle
for idx, row in df.iterrows():  # À éviter
    ...
```

**Validation:**
- Benchmark sur fichier 50k lignes < 10 min
- Profiling avec cProfile si nécessaire

---

### NFR-003: Utilisabilité DAF

**Solution:**
- CLI avec workflow guidé step-by-step
- Messages en français, clairs et actionnables
- Progress bar pour opérations longues
- Questions contextualisées avec info PCG
- Rapport Excel auto-formaté (pas de traitement manuel)

**Implementation Notes:**
```python
# Exemple de question contextualisée
"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANOMALIE #1 - Compte 681000 (Dotations aux amortissements)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Type: Concentration mensuelle
Montant impacté: 125 000 €
Mois concerné: Décembre (85% du total annuel)

📋 Contexte PCG:
   Ce compte enregistre les dotations aux amortissements.
   Comportement attendu: Mensuel (1/12 par mois)
   Comportement observé: 85% en décembre

❓ Cette concentration est-elle justifiée ?

[1] Justifié - Dotation annuelle normale
[2] Non justifié - Devrait être mensuel
[3] À investiguer - Besoin d'infos supplémentaires

Votre choix (1/2/3):
"""
```

---

### NFR-005: Zéro faux négatif (100% recall)

**Solution:**
- Seuils conservateurs par défaut
- Détection multi-critères (concentration ET z-score ET provisions)
- Comparaison au comportement attendu PCG
- Flag si déviation du pattern attendu

**Implementation Notes:**
- Z-score seuil par défaut: |Z| > 1.5 (conservateur)
- Concentration seuil: > 40% (conservateur)
- Si compte de provision → toujours flaggé

---

### NFR-006: Faux positifs → 0%

**Solution:**
- Contextualisation PCG (un compte de dotation annuelle en décembre = normal)
- Score ajusté selon le comportement attendu
- Qualification utilisateur pour confirmation
- Apprentissage des justifications précédentes

**Implementation Notes:**
```python
def adjust_score(anomaly, expected_behavior):
    """Ajuste le score selon le contexte PCG"""
    if expected_behavior.pattern == "annuel" and anomaly.mois == 12:
        # Compte annuel concentré en décembre = attendu
        return anomaly.score * 0.3  # Score réduit
    return anomaly.score
```

---

### NFR-007: Code quality (PEP8, documenté)

**Solution:**
- black pour formatage automatique
- flake8 pour linting
- mypy pour type checking
- Docstrings Google style
- README complet

---

### NFR-008: Tests unitaires

**Solution:**
- pytest pour tous les tests
- Coverage > 70% sur fonctions critiques
- Tests sur jeux de données avec anomalies connues
- CI avec GitHub Actions

**Test Structure:**
```
tests/
├── test_loader.py
├── test_accounting_context.py
├── test_profiler.py
├── test_detector.py
├── test_qualifier.py
├── test_normalizer.py
├── test_reporter.py
├── fixtures/
│   ├── sample_gl.xlsx
│   ├── sample_pcg.yaml
│   └── expected_anomalies.yaml
└── conftest.py
```

---

## 8. Project Structure

```
gl_normalizer/
├── __init__.py              # API publique
├── __main__.py              # Entry point CLI
├── cli.py                   # Interface ligne de commande
├── orchestrator.py          # Coordination workflow
│
├── context/
│   ├── __init__.py
│   ├── loader.py            # Chargement GL
│   ├── accounting.py        # AccountingContext (PCG)
│   └── formats/
│       ├── sage.py
│       ├── cegid.py
│       ├── quadratus.py
│       └── ebp.py
│
├── analysis/
│   ├── __init__.py
│   ├── profiler.py          # Analyse statistique
│   ├── detector.py          # Détection anomalies
│   └── ai/
│       ├── __init__.py
│       ├── benford.py
│       ├── isolation.py
│       └── nlp.py
│
├── qualification/
│   ├── __init__.py
│   ├── qualifier.py         # Workflow questions
│   └── storage.py           # Sauvegarde YAML
│
├── output/
│   ├── __init__.py
│   ├── normalizer.py        # Calcul run rate
│   └── reporter.py          # Génération Excel
│
├── data/
│   ├── pcg_2025.yaml        # PCG français
│   └── formats_mapping.yaml # Mappings par format
│
└── config.py                # Configuration globale
```

---

## 9. Testing Strategy

### Unit Tests

| Module | Coverage Target | Key Tests |
|--------|-----------------|-----------|
| Loader | 80% | Formats detection, column mapping |
| AccountingContext | 90% | PCG loading, classification |
| Profiler | 80% | Stats calculation, baseline |
| Detector | 90% | All anomaly types, contextualisation |
| Normalizer | 90% | Run rate calculation, dispatch |
| Reporter | 70% | Excel generation |

### Integration Tests

- Full workflow avec fichier GL sample
- Vérification que toutes les anomalies connues sont détectées
- Vérification du rapport Excel généré

### Test Data

Fichiers de test avec anomalies connues :
- `test_concentration.xlsx` - Provisions concentrées en décembre
- `test_zscore.xlsx` - Outliers statistiques
- `test_provisions.xlsx` - Dotations/reprises
- `test_clean.xlsx` - Fichier sans anomalie (baseline)

---

## 10. Traceability

### FR → Components

| FR | Components | Notes |
|----|------------|-------|
| FR-001 | Loader | Chargement Excel |
| FR-002 | Loader, formats/* | Détection format |
| FR-003 | Loader | Mapping manuel |
| FR-004 | Detector, AccountingContext | Concentrations + contexte |
| FR-005 | Detector, Profiler | Z-scores |
| FR-006 | Detector, AccountingContext | Provisions |
| FR-007 | Detector | Montants ronds |
| FR-008 | Detector | Journaux OD |
| FR-009 | Qualifier | Questions |
| FR-010 | Qualifier | Commentaires |
| FR-011 | Qualifier, storage | Sauvegarde |
| FR-012 | Normalizer | Run rate |
| FR-013 | Normalizer | Neutralisation |
| FR-014 | Reporter | Rapport Excel |
| FR-015 | Reporter | Comparatif |
| FR-016 | ai/benford | Benford |
| FR-017 | ai/isolation | Isolation Forest |
| FR-018 | ai/nlp | NLP libellés |

### NFR → Architecture

| NFR | Solution | Components |
|-----|----------|------------|
| NFR-001 | Vectorisation pandas | Tous |
| NFR-003 | CLI guidé, messages FR | cli.py, Qualifier |
| NFR-005 | Seuils conservateurs | Detector |
| NFR-006 | Contexte PCG | AccountingContext, Detector |
| NFR-007 | black, flake8, mypy | CI |
| NFR-008 | pytest, 70%+ coverage | tests/ |
| NFR-009 | Python 3.9+ | requirements.txt |
| NFR-010 | Tests multi-OS | CI |

---

## 11. Trade-offs

### Decision 1: Monolith vs Microservices

**Choice:** Monolith Python

**Trade-off:**
- ✓ Gain: Simplicité, déploiement facile (pip install), maintenabilité solo
- ✗ Lose: Scalabilité (pas de parallélisation distribuée)

**Rationale:** Outil CLI single-user, pas besoin de scaling horizontal.

---

### Decision 2: PCG embarqué vs API externe

**Choice:** PCG embarqué (YAML)

**Trade-off:**
- ✓ Gain: Fonctionne offline, pas de dépendance externe, rapide
- ✗ Lose: Mise à jour manuelle si PCG change

**Rationale:** PCG change rarement, embarqué = plus fiable.

---

### Decision 3: IA optionnelle vs obligatoire

**Choice:** IA optionnelle (dépendances séparées)

**Trade-off:**
- ✓ Gain: Installation légère par défaut, fonctionne sans GPU/ML
- ✗ Lose: Moins de détection avancée si désactivé

**Rationale:** Accessibilité maximale, l'IA enrichit mais n'est pas critique.

---

## 12. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-03 | BMAD Architect | Initial architecture |

---

*Document généré par BMAD Method v6 - Phase 3 Solutioning*
