# GL Crystal - Brainstorming Complet

**Date:** 2026-02-04
**Sujets:** Layer 1, Layer 4, Pipeline, Tests, Référentiel

---

## Sommaire Exécutif

| Sujet | Insights clés | Prochaine action |
|-------|---------------|------------------|
| Layer 1 | Lazy parsing (~15 anomalies), extraction hiérarchique | Implémenter `layer1/` |
| Layer 4 | Score ICC = 100 - Σ(impacts), radar par univers | Implémenter `layer4/` |
| Pipeline | Option C (Lazy L1) recommandée | Créer orchestrateur |
| Tests | Golden Set obligatoire, CI/CD métriques | Créer dataset test |
| Référentiel | YAML + Pydantic, héritage par univers | Créer schéma |

---

## 1. Layer 1: Label Parser

### Objectif
Enrichir les ~15 anomalies qualifiées avec sémantique extraite des libellés comptables.

### Architecture

```
Libellé brut → Regex (patterns) → spaCy (NER) → [LLM fallback]
                     │                  │              │
                     ▼                  ▼              ▼
              Montant/Date        Nom Tiers      Cas complexes
              Référence           Intent
```

### Features à extraire

| Feature | Type | Exemple |
|---------|------|---------|
| `tiers_name` | string | "ACME Corp" |
| `operation_type` | enum | ACHAT, VENTE, PROVISION |
| `reference` | string | "FA-2024-0123" |
| `period_ref` | string | "janvier 2024" |
| `amount_extracted` | float | 1234.56 |
| `is_recurring` | bool | true |
| `intent` | enum | REGULARISATION, EXTOURNE |
| `confidence` | float | 0.85 |

### Décision: Lazy Parsing
- **Ne PAS parser** les 200K écritures du GL
- **Parser seulement** les ~15 anomalies de Layer 3
- **Cache** par hash de libellé pour dédup

### Stack technique
- `regex` - Patterns connus (montants, dates, références)
- `spacy` fr_core_news_md - NER français
- `rapidfuzz` - Matching fuzzy noms tiers
- `langdetect` - Détection langue (FR/EN)

---

## 2. Layer 4: ICC Score

### Objectif
Produire un score ICC (Internal Control Checklist) de 0-100 et un rapport actionnable.

### Formule de scoring

```python
# Score global
icc_score = 100 - sum(anomaly_impact for a in qualified_anomalies)

# Impact par anomalie
anomaly_impact = weight_univers[a.univers] * a.pertinence_score * materiality_factor(a)

# Facteur matérialité
materiality_factor = log10(1 + a.materiality_amount / total_materiality) * 10
```

### Output structure

```python
@dataclass
class ICCResult:
    # Scores
    global_score: float          # 0-100
    score_by_univers: Dict[Univers, float]
    trend_vs_n1: Optional[float]

    # Top anomalies
    top_5_anomalies: List[QualifiedAnomaly]

    # Narrative
    executive_summary: str       # Auto-généré
    recommendations: List[str]

    # Metadata
    period: str
    entity: str
    generated_at: datetime

    # Export
    def to_pdf(self) -> bytes
    def to_excel(self) -> bytes
    def to_json(self) -> dict
```

### Radar par univers

```
            CRISTALLIN
                 │
    COMPOSITE ───┼─── NOMINATIF_TIERS
                 │
  INVENTAIRE ────┼──── NOMINATIF_OP
                 │
    PONCTUEL ────┼──── PROCESSUS
                 │
   TRESORERIE ───┼─── VENTILATION
                 │
              CUT_OFF
```

---

## 3. Intégration Pipeline

### Architecture finale

```
GL DataFrame
     │
     ▼
┌─────────┐
│ Layer 0 │ Classification par famille → univers
└────┬────┘
     │
     ▼
┌─────────┐
│ Layer 2 │ Tests numériques → ~200 signaux (p-values)
└────┬────┘
     │ BH-FDR α=0.05
     ▼
┌─────────┐
│Layer 2.5│ Correction multiple → ~40 signaux
└────┬────┘
     │
     ▼
┌─────────┐
│ Layer 3 │ Filtres métier → ~15 anomalies qualifiées
└────┬────┘
     │ Lazy trigger
     ▼
┌─────────┐
│ Layer 1 │ Enrichissement sémantique libellés
└────┬────┘
     │
     ▼
┌─────────┐
│ Layer 4 │ Score ICC + Rapport
└─────────┘
     │
     ▼
  OUTPUT (PDF/Excel/JSON)
```

### API suggérée

```python
from gl_normalizer.crystal import run_crystal_pipeline

result = run_crystal_pipeline(
    gl=df,
    referentiel=referentiel,
    config=CrystalConfig(
        fdr_alpha=0.05,
        materiality_threshold=5000,
        pertinence_threshold=40,
        parse_labels=True,
    )
)

print(result.icc.global_score)  # 87.3
print(result.icc.executive_summary)
result.icc.to_pdf("rapport_icc_2024_01.pdf")
```

---

## 4. Stratégie de Tests

### Pyramide

| Niveau | Quantité | Scope | Fréquence |
|--------|----------|-------|-----------|
| Unit | 50+ | Fonctions isolées | Chaque commit |
| Integration | 10-15 | L2→L3, L3→L4 | Chaque PR |
| E2E | 2-3 | Pipeline complet | Nightly |

### Datasets requis

| Dataset | Lignes | Usage | Création |
|---------|--------|-------|----------|
| `test_synthetic.csv` | 100 | Unit tests | Généré |
| `test_realistic.csv` | 10K | Integration | Anonymisé |
| `golden_set.json` | 50 anomalies | Validation précision | Expert |
| `stress_test.csv` | 1M | Performance | Généré |

### Golden Set format

```json
{
  "anomalies": [
    {
      "famille": "613",
      "periode": "2024-01",
      "expected_detection": true,
      "expected_univers": "CRISTALLIN",
      "rationale": "Loyer doublé en janvier",
      "validated_by": "expert_audit"
    }
  ]
}
```

### Métriques CI/CD

```yaml
# .github/workflows/test.yml
- name: Run tests with metrics
  run: |
    pytest tests/ --cov=gl_normalizer --cov-report=xml
    python scripts/compute_metrics.py

- name: Check thresholds
  run: |
    # Fail if precision < 80% or recall < 90%
    python scripts/check_thresholds.py
```

---

## 5. Référentiel Sémantique

### Structure YAML

```yaml
# referentiel/familles.yaml
meta:
  version: "1.0.0"
  updated: "2026-02-04"

defaults_by_univers:
  CRISTALLIN:
    cv_attendu: 0.05
    seuil_materialite: 2000
    frequence: MENSUELLE
    tests: [L2-VAR, L2-MISSING]

  NOMINATIF_TIERS:
    cv_attendu: 0.50
    seuil_materialite: 10000
    frequence: VARIABLE
    tests: [L2-VAR, L2-CONC, L2-DISCORD]

familles:
  "601":
    nom: "Achats stockés - Matières premières"
    univers: INVENTAIRE
    # Hérite defaults INVENTAIRE sauf override
    cv_attendu: 0.35  # Override
    non_signal_si:
      - montant_rond
    signal_si:
      - new_supplier

  "613":
    nom: "Locations"
    univers: CRISTALLIN
    # Hérite tout de CRISTALLIN
    non_signal_si:
      - meme_montant_12_mois
      - montant_rond
```

### Validation Pydantic

```python
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class Univers(str, Enum):
    CRISTALLIN = "CRISTALLIN"
    NOMINATIF_TIERS = "NOMINATIF_TIERS"
    # ... etc

class FamilleConfig(BaseModel):
    nom: str
    univers: Univers
    cv_attendu: float = Field(ge=0, le=5)
    seuil_materialite: Optional[int] = None
    frequence: str = "MENSUELLE"
    tests: List[str] = ["L2-VAR"]
    non_signal_si: List[str] = []
    signal_si: List[str] = []

class Referentiel(BaseModel):
    meta: dict
    defaults_by_univers: Dict[Univers, dict]
    familles: Dict[str, FamilleConfig]

    def get_famille(self, code: str) -> FamilleConfig:
        """Retourne config avec héritage appliqué."""
        famille = self.familles[code]
        defaults = self.defaults_by_univers[famille.univers]
        return famille.copy(update={
            k: v for k, v in defaults.items()
            if getattr(famille, k, None) is None
        })
```

---

## Statistiques Brainstorm

| Métrique | Valeur |
|----------|--------|
| Sujets couverts | 5 |
| Techniques utilisées | SCAMPER, Mind Map, Starbursting |
| Insights extraits | 15 |
| Durée estimée | 45 min |

---

## Prochaines Étapes

1. **Implémenter Layer 1** (`gl_normalizer/layer1/`)
   - `parser.py` - LabelParser class
   - `entities.py` - NER extraction
   - `intents.py` - Classification intention

2. **Implémenter Layer 4** (`gl_normalizer/layer4/`)
   - `scorer.py` - ICCScorer
   - `report.py` - ReportGenerator
   - `export.py` - PDF/Excel/JSON

3. **Créer Référentiel** (`referentiel/`)
   - `familles.yaml` - 180 familles
   - `schema.py` - Validation Pydantic
   - `loader.py` - Chargement avec héritage

4. **Créer Golden Set**
   - Identifier 50+ anomalies réelles
   - Valider avec expert audit
   - Documenter rationale

---

*Generated by BMAD Method - Creative Intelligence*
*Session: 2026-02-04*
