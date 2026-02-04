# GL Crystal - Brainstorming Orchestration, Référentiel, UI, Performance, Déploiement

**Date:** 2026-02-04

---

## Récapitulatif Insights

| Sujet | Insight Principal | Priorité |
|-------|-------------------|----------|
| **Orchestrateur** | Single entry point `run_crystal(gl, referentiel)` | P1 |
| **Référentiel** | Héritage univers→famille, validation Pydantic | P1 |
| **UI** | Streamlit MVP + export HTML pour portabilité | P2 |
| **Performance** | Polars + vectorisation = 2-3× speedup | P2 |
| **Déploiement** | CLI first, puis REST API | P1 |

---

## 1. Orchestrateur Pipeline

### Architecture

```
gl_normalizer/
├── crystal.py          # CrystalPipeline, run_crystal()
├── config.py           # CrystalConfig dataclass
└── result.py           # CrystalResult aggregate
```

### API proposée

```python
from gl_normalizer.crystal import run_crystal, CrystalConfig

# Usage simple
result = run_crystal(gl, referentiel)
print(result.icc.global_score)

# Usage avancé
config = CrystalConfig(
    fdr_alpha=0.05,
    materiality_threshold=5000,
    pertinence_threshold=40,
    parse_labels=True,
)
result = run_crystal(gl, referentiel, config)
result.to_pdf("rapport.pdf")
```

### CrystalResult

```python
@dataclass
class CrystalResult:
    # Résultats intermédiaires
    layer2_result: Layer2Result
    layer3_result: Layer3Result
    icc_result: ICCResult

    # Raccourcis
    @property
    def score(self) -> float:
        return self.icc_result.global_score

    @property
    def anomalies(self) -> List[QualifiedAnomaly]:
        return self.layer3_result.qualified

    # Exports
    def to_pdf(self, path: str): ...
    def to_excel(self, path: str): ...
    def to_json(self) -> str: ...
    def summary(self) -> str: ...
```

---

## 2. Référentiel 180 Familles

### Structure fichiers

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
    tests_applicables: [L2-VAR, L2-MISSING]
    non_signal_si: [montant_rond]

  NOMINATIF_TIERS:
    cv_attendu: 0.50
    seuil_materialite: 10000
    frequence: VARIABLE
    tests_applicables: [L2-VAR, L2-CONC, L2-DISCORD]

  # ... autres univers

familles:
  "601":
    nom: "Achats stockés - Matières premières"
    univers: INVENTAIRE
    cv_attendu: 0.35  # Override

  "613":
    nom: "Locations"
    univers: CRISTALLIN
    non_signal_si:
      - montant_rond
      - meme_montant_12_mois

  # ... 180 familles
```

### Validation Pydantic

```python
class FamilleConfig(BaseModel):
    code: str
    nom: str
    univers: Univers
    cv_attendu: float = Field(ge=0, le=5, default=None)
    seuil_materialite: Optional[int] = None
    frequence: Literal["MENSUELLE", "TRIMESTRIELLE", "ANNUELLE", "VARIABLE"] = None
    tests_applicables: List[str] = None
    non_signal_si: List[str] = []
    signal_si: List[str] = []

    model_config = ConfigDict(extra="forbid")
```

---

## 3. UI/Dashboard

### Stack recommandée

**Phase 1: MVP Streamlit**
- Temps: 1 jour
- Features: Upload CSV, score, radar, top anomalies
- Déploiement: Streamlit Cloud (gratuit)

**Phase 2: HTML export**
- Temps: 0.5 jour
- Features: Rapport standalone sans serveur
- Usage: Partage par email, archive

**Phase 3 (optionnel): React + FastAPI**
- Temps: 1 semaine
- Features: Full app, multi-users, historique
- Usage: Production enterprise

### Composants Streamlit

```python
# app.py
import streamlit as st
from gl_normalizer.crystal import run_crystal

st.title("GL Crystal - Audit Interne")

uploaded = st.file_uploader("Grand Livre (CSV)")
if uploaded:
    gl = pd.read_csv(uploaded)
    result = run_crystal(gl, referentiel)

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Score ICC", f"{result.score:.1f}/100")
    with col2:
        st.metric("Anomalies", result.icc_result.score.anomaly_count)

    # Radar chart
    fig = px.line_polar(result.icc_result.radar_data(), ...)
    st.plotly_chart(fig)

    # Table anomalies
    st.dataframe(result.top_anomalies_df())
```

---

## 4. Performance

### Optimisations prioritaires

| Optimisation | Gain estimé | Effort |
|--------------|-------------|--------|
| Polars au lieu de Pandas | 2-3× | Low |
| Vectorisation numpy L2 | 1.5× | Medium |
| Cache parsing L1 | Variable | Done ✓ |
| Multiprocessing tests | 1.5× | Medium |

### Polars migration

```python
# Avant (Pandas)
df = pd.read_csv("gl.csv")
grouped = df.groupby("famille")["montant"].agg(["mean", "std"])

# Après (Polars) - 3× plus rapide
import polars as pl
df = pl.read_csv("gl.csv")
grouped = df.group_by("famille").agg([
    pl.col("montant").mean().alias("mean"),
    pl.col("montant").std().alias("std"),
])
```

### Benchmarks cibles

| Volume | Cible | Stack |
|--------|-------|-------|
| 10K lignes | <2s | Pandas |
| 100K lignes | <10s | Pandas optimisé |
| 1M lignes | <30s | Polars |
| 10M lignes | <5min | Polars + chunking |

---

## 5. Déploiement

### CLI (Typer)

```python
# gl_normalizer/cli.py
import typer
app = typer.Typer()

@app.command()
def analyze(
    gl_path: Path,
    output: Path = Path("report.html"),
    referentiel: Path = None,
    format: str = "html",
    quiet: bool = False,
):
    """Analyse un Grand Livre et génère un rapport ICC."""
    gl = load_gl(gl_path)
    ref = load_referentiel(referentiel)
    result = run_crystal(gl, ref)

    if quiet:
        print(f"{result.score:.1f}")
    else:
        export(result, output, format)

@app.command()
def validate(referentiel: Path):
    """Valide un fichier référentiel."""
    ...

if __name__ == "__main__":
    app()
```

### Installation

```bash
# Installation locale
pip install -e .

# Usage
gl-crystal analyze data/gl.csv --output rapport.html
gl-crystal analyze data/gl.csv --format json > result.json
```

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .
COPY gl_normalizer/ gl_normalizer/
COPY referentiel/ referentiel/

RUN pip install -e .

# CLI par défaut
ENTRYPOINT ["gl-crystal"]
CMD ["--help"]
```

```bash
# Build & run
docker build -t gl-crystal .
docker run -v $(pwd)/data:/data gl-crystal analyze /data/gl.csv
```

---

## Prochaines Étapes Recommandées

1. **P1: crystal.py** - Orchestrateur single entry point
2. **P1: cli.py** - Interface ligne de commande
3. **P1: referentiel/** - Structure YAML + loader
4. **P2: app.py** - Streamlit dashboard MVP
5. **P2: Polars** - Migration pour performance

---

*Generated by BMAD Method - Creative Intelligence*
*Session: 2026-02-04*
