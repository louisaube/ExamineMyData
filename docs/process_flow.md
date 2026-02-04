# ExamineMyData - Processus de bout en bout

## Vue d'ensemble

ExamineMyData est une application d'analyse de Grand Livre (GL) qui transforme des données comptables brutes en insights opérationnels via un pipeline multi-couches.

## Diagramme de flux principal

```mermaid
flowchart TB
    subgraph INPUT["1. ENTRÉE"]
        A[📁 Fichier GL<br/>Excel/CSV] --> B{Mode}
        B -->|1 fichier| C[Analyse annuelle]
        B -->|2 fichiers| D[Comparaison N/N-1]
    end

    subgraph LOAD["2. CHARGEMENT"]
        E[🔍 GLLoader<br/>Détection format] --> F[📊 Normalisation<br/>Colonnes standard]
        F --> G[🏷️ GLClassifier<br/>Classification écritures]
    end

    subgraph ANALYZE["3. ANALYSES"]
        direction TB
        subgraph CORE["Tier 1: Core"]
            H1[📊 Profiler]
            H2[🎯 AnomalyDetector]
            H3[🔄 RegularizationDetector]
            H4[📉 PnLNormalizer]
            H5[📚 AccountingContext]
        end

        subgraph ADVANCED["Tier 2: Avancé"]
            I1[📈 MAD/IQR]
            I2[🌊 Saisonnalité]
            I3[🔗 Clustering]
        end

        subgraph AI["Tier 3: IA/ML"]
            J1[🔢 Benford's Law]
            J2[🌲 Isolation Forest]
            J3[📝 NLP Analysis]
            J4[⚠️ Risk Score]
        end

        subgraph CRYSTAL["Tier 4: GL Crystal v2.0"]
            K1[Layer 0: Semantic<br/>5 univers]
            K2[Layer 1: ICC<br/>Indice Cristallinité]
            K3[Layer 2: Graph<br/>Contreparties]
            K4[Layer 3: Embedding]
        end

        subgraph DRILLDOWN["Autonomous Drilldown"]
            L1[🔬 PatternDetector]
            L2[❓ QuestionGenerator]
            L3[⚡ QuestionExecutor]
        end
    end

    subgraph COMPARE["4. COMPARAISON (optionnel)"]
        M[📊 GLComparator] --> N[Variations brutes]
        N --> O[Variations normalisées]
        O --> P[Top N Drill-down]
    end

    subgraph OUTPUT["5. SORTIES"]
        Q[🖥️ Web UI<br/>Dashboard]
        R[📑 Excel Report<br/>Multi-sheet]
        S[🔌 API REST<br/>JSON]
    end

    INPUT --> LOAD
    LOAD --> ANALYZE
    ANALYZE --> COMPARE
    COMPARE --> OUTPUT
    ANALYZE --> OUTPUT

    style CORE fill:#00ff8822,stroke:#00ff88
    style ADVANCED fill:#ffc80022,stroke:#ffc800
    style AI fill:#ff646422,stroke:#ff6464
    style CRYSTAL fill:#b464ff22,stroke:#b464ff
```

## Séquence détaillée

```mermaid
sequenceDiagram
    participant U as Utilisateur
    participant W as FastAPI (main.py)
    participant L as GLLoader
    participant A as GLAnalyzer
    participant C as Cache
    participant R as Reporter

    U->>W: POST /analyze (fichier GL)
    W->>W: Validation fichier
    W->>C: Créer job_id (PENDING)
    W-->>U: Redirect /loading/{job_id}

    Note over W,A: Traitement asynchrone

    W->>L: load(fichier)
    L->>L: Détection format (Sage/Cegid/...)
    L->>L: Normalisation colonnes
    L-->>W: DataFrame normalisé

    W->>A: analyze(df)

    rect rgb(0, 255, 136, 0.1)
        Note over A: Tier 1: Core
        A->>A: Profiler.profile()
        A->>A: AnomalyDetector.detect()
        A->>A: RegularizationDetector.analyze()
        A->>A: PnLNormalizer.normalize()
        A->>A: AccountingContext.contextualize()
    end

    rect rgb(255, 200, 0, 0.1)
        Note over A: Tier 2: Advanced
        A->>A: MAD/IQR detection
        A->>A: Seasonality decomposition
        A->>A: Account clustering
    end

    rect rgb(255, 100, 100, 0.1)
        Note over A: Tier 3: AI/ML
        A->>A: Benford analysis
        A->>A: Isolation Forest
        A->>A: NLP on labels
        A->>A: Combined risk score
    end

    rect rgb(180, 100, 255, 0.1)
        Note over A: Tier 4: Crystal
        A->>A: Semantic classification
        A->>A: ICC computation
        A->>A: Graph analysis
    end

    A-->>W: FullAnalysisResult
    W->>C: set(job_id, result)

    U->>W: GET /results/{job_id}
    W->>C: get(job_id)
    W-->>U: Page résultats

    U->>W: GET /report/{job_id}
    W->>R: generate(result)
    R-->>U: Fichier Excel
```

## Architecture des modules

```mermaid
graph LR
    subgraph Orchestration
        MAIN[main.py<br/>FastAPI]
        ANALYZER[GLAnalyzer<br/>Orchestrateur]
    end

    subgraph Chargement
        LOADER[GLLoader]
        CLASSIFIER[GLClassifier]
    end

    subgraph "Analyses Core"
        PROFILER[Profiler]
        DETECTOR[AnomalyDetector]
        REGULARIZATION[RegularizationDetector]
        NORMALIZER[PnLNormalizer]
        CONTEXT[AccountingContext]
    end

    subgraph "Analyses Avancées"
        STATS[AdvancedStats]
        COMPARATOR[GLComparator]
    end

    subgraph "AI Pipeline"
        BENFORD[BenfordAnalyzer]
        ISOFOREST[IsolationForest]
        NLP[NLPAnalyzer]
        RISK[RiskScorer]
    end

    subgraph "GL Crystal"
        SEMANTIC[SemanticClassifier]
        ICC[ICCCalculator]
        GRAPH[GraphAnalyzer]
        EMBED[Embedding]
    end

    subgraph "Drilldown"
        PATTERN[PatternDetector]
        QUESTION[QuestionGenerator]
        EXECUTOR[DrilldownExecutor]
    end

    subgraph Sortie
        REPORTER[ExcelReporter]
        CACHE[AnalysisCache]
    end

    MAIN --> LOADER
    MAIN --> ANALYZER
    LOADER --> CLASSIFIER

    ANALYZER --> PROFILER
    ANALYZER --> DETECTOR
    ANALYZER --> REGULARIZATION
    ANALYZER --> NORMALIZER
    ANALYZER --> CONTEXT
    ANALYZER --> STATS
    ANALYZER --> COMPARATOR

    ANALYZER --> BENFORD
    ANALYZER --> ISOFOREST
    ANALYZER --> NLP
    ANALYZER --> RISK

    ANALYZER --> SEMANTIC
    SEMANTIC --> ICC
    ICC --> GRAPH
    GRAPH --> EMBED

    ANALYZER --> PATTERN
    PATTERN --> QUESTION
    QUESTION --> EXECUTOR

    ANALYZER --> CACHE
    CACHE --> REPORTER
```

## Détail des analyses

### Tier 1: Core (toujours exécuté)

| Module | Fonction | Sortie |
|--------|----------|--------|
| **Profiler** | Statistiques de base, qualité données | DataProfileResult |
| **AnomalyDetector** | Concentrations, montants ronds | DetectionResult |
| **RegularizationDetector** | Provisions (68x) / Reprises (78x) | RegularizationAnalysis |
| **PnLNormalizer** | Run rate = Total/12, écart décembre | RunRateResult |
| **AccountingContext** | Classification PCG, comportement attendu | ContextualizedAnomaly |

### Tier 2: Avancé (conditionnel)

| Module | Fonction | Condition |
|--------|----------|-----------|
| **MAD** | Median Absolute Deviation | Données suffisantes |
| **IQR** | Interquartile Range | Données suffisantes |
| **Seasonality** | Décomposition saisonnière | >= 12 mois |
| **Clustering** | Groupement comportemental | >= 10 comptes |

### Tier 3: IA/ML (optionnel)

| Module | Fonction | Dépendances |
|--------|----------|-------------|
| **Benford** | Loi de Benford (chiffres fabriqués) | numpy |
| **IsolationForest** | Détection anomalies non-supervisée | scikit-learn |
| **NLP** | Analyse des libellés | - |
| **RiskScorer** | Score combiné 0-100 | Tous les précédents |

### Tier 4: GL Crystal v2.0 (topologique)

| Layer | Fonction | Sortie |
|-------|----------|--------|
| **0: Semantic** | Classification en 5 univers | Universe (CRISTALLIN, NOMINATIF, INVENTAIRE, VENTILATION, COMPOSITE) |
| **1: ICC** | Indice de cristallinité (0-1) | ICC score + Surprise metric |
| **2: Graph** | Analyse bipartite contreparties | Graph metrics |
| **3: Embedding** | Représentation vectorielle | Vectors |

## Sorties générées

### Interface Web

- **Upload** (`/`) - Formulaire de téléchargement
- **Loading** (`/loading/{id}`) - Page de chargement avec polling
- **Results** (`/results/{id}`) - Dashboard interactif
- **Report** (`/report/{id}`) - Téléchargement Excel
- **Qualification** (`/qualification/{id}`) - Qualification anomalies

### Rapport Excel (multi-feuilles)

| Feuille | Contenu |
|---------|---------|
| **Synthèse** | Métriques clés, brut vs normalisé |
| **Réconciliation** | Pont de variance |
| **Provisions** | Détail des ajustements par compte |
| **Anomalies** | Liste complète avec contexte PCG |
| **Drill-down** | Top variations (si comparaison) |
| **Notes** | Warnings et recommandations |
| **Données mensuelles** | Breakdown mensuel |
| **Crystal ICC** | Top surprises (si activé) |

### API REST

```
GET  /api/status/{job_id}        → Statut du job
GET  /api/drilldown/{job_id}     → Questions générées
POST /api/drilldown/{job_id}/{q} → Exécuter question
GET  /api/settings/status        → Statut IA
```

## Formules clés

### Run Rate (normalisation)

```
Run Rate mensuel = Total annuel / 12

Écart décembre = Décembre brut - Run Rate

Si Écart > 0 → Sur-provisionnement probable
Si Écart < 0 → Sous-provisionnement probable

Résultat normalisé = Résultat brut - Σ(Écarts décembre)
```

### Indice de Cristallinité (ICC)

```
ICC = f(
    variation_montants,      # Écart-type des montants
    entropie_libellés,       # Diversité des descriptions
    régularité_temporelle,   # Distribution dans le temps
    diversité_journaux,      # Nombre de journaux distincts
    concentration_contreparties  # Concentration sur tiers
)

ICC ∈ [0, 1]
  0 = Amorphe (très variable)
  1 = Cristallin (très régulier)

Surprise = |ICC_observé - ICC_attendu_univers|
```

### Risk Score

```
Risk Score = w1 * Benford_score
           + w2 * IsoForest_score
           + w3 * NLP_score
           + w4 * Concentration_score

Score ∈ [0, 100]
  0-20:   MINIMAL
  20-40:  LOW
  40-60:  MEDIUM
  60-80:  HIGH
  80-100: CRITICAL
```
