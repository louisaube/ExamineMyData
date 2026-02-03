# STORY-028: Migration Polars pour performance

## Métadonnées
- **ID**: STORY-028
- **Sprint**: 6-7
- **Priorité**: Medium
- **Estimation**: 8 points
- **Dépendances**: Aucune (refactoring interne)

## User Story

**En tant que** utilisateur analysant des fichiers volumineux (78K+ écritures),
**Je veux** que l'analyse se termine en moins de 30 secondes,
**Afin de** pouvoir travailler efficacement sans attendre plusieurs minutes.

## Contexte

### Problème actuel
- Pandas mono-thread, pas de lazy evaluation
- 78K écritures = 60-120 secondes d'analyse
- 5+ copies de DataFrame en mémoire (~1.5 GB intermédiaire)
- GroupBy en boucle = complexité O(n²)

### Solution Polars
- Multi-threading automatique
- Lazy evaluation native (query optimization)
- Gestion mémoire optimisée (zero-copy)
- API similaire à Pandas (migration facilitée)

### Benchmarks attendus
| Opération | Pandas | Polars | Gain |
|-----------|--------|--------|------|
| Chargement CSV 78K | 3s | 0.3s | 10x |
| GroupBy agrégation | 5s | 0.2s | 25x |
| Pivot table | 8s | 0.5s | 16x |
| Total analyse | 60s | 5-10s | 6-12x |

## Critères d'acceptation

### AC-1: Compatibilité fonctionnelle
- [ ] Tous les tests existants passent
- [ ] Résultats d'analyse identiques à Pandas
- [ ] Pas de régression sur les rapports Excel

### AC-2: Performance
- [ ] Analyse 78K écritures < 30 secondes
- [ ] Mémoire peak < 500 MB (vs 2.5 GB actuel)
- [ ] Chargement fichier < 2 secondes

### AC-3: Fallback Pandas
- [ ] Si Polars échoue, fallback automatique sur Pandas
- [ ] Log des performances pour monitoring
- [ ] Configuration pour forcer Pandas si besoin

## Stratégie de migration

### Phase 1: Dual-mode (Sprint 6)
```python
# Configuration
USE_POLARS = True  # Toggle

# Wrapper transparent
def load_dataframe(path):
    if USE_POLARS and POLARS_AVAILABLE:
        return load_with_polars(path)
    return load_with_pandas(path)
```

### Phase 2: Migration modules critiques
1. `loader.py` - Chargement fichiers (impact max)
2. `pnl_normalizer.py` - Calculs lourds (groupby, pivot)
3. `detector.py` - Détection anomalies
4. `profiler.py` - Stats descriptives

### Phase 3: Nettoyage (Sprint 7)
- Supprimer code Pandas si Polars stable
- Optimiser queries Polars (lazy chains)
- Documentation des patterns Polars

## Design technique

### Nouvelle dépendance
```toml
# pyproject.toml
[project.dependencies]
polars = ">=1.0.0"
```

### Pattern de conversion
```python
import polars as pl

# Pandas
df.groupby("compte")["montant"].sum()

# Polars équivalent
df.group_by("compte").agg(pl.col("montant").sum())

# Polars lazy (recommandé)
(
    df.lazy()
    .group_by("compte")
    .agg(pl.col("montant").sum())
    .collect()
)
```

### Fichiers à modifier
| Fichier | Effort | Impact |
|---------|--------|--------|
| `loader.py` | Medium | High |
| `pnl_normalizer.py` | High | High |
| `detector.py` | Medium | Medium |
| `profiler.py` | Low | Medium |
| `analyzer.py` | Low | Low |

## Tâches

### Sprint 6
- [ ] Ajouter Polars aux dépendances
- [ ] Créer wrapper dual-mode dans `loader.py`
- [ ] Migrer `loader.py` (chargement)
- [ ] Migrer `pnl_normalizer.py` (calculs critiques)
- [ ] Tests de performance comparatifs

### Sprint 7
- [ ] Migrer modules restants
- [ ] Optimiser lazy evaluation
- [ ] Supprimer code Pandas si stable
- [ ] Documentation migration

## Tests

### Tests de non-régression
```python
def test_results_identical():
    """Vérifie que Polars produit les mêmes résultats que Pandas"""
    df_pandas = load_with_pandas("test_data.csv")
    df_polars = load_with_polars("test_data.csv")

    result_pandas = analyze_with_pandas(df_pandas)
    result_polars = analyze_with_polars(df_polars)

    assert result_pandas.run_rate == result_polars.run_rate
    assert len(result_pandas.anomalies) == len(result_polars.anomalies)
```

### Tests de performance
```python
def test_performance_78k():
    """Vérifie le temps d'exécution sur gros fichier"""
    import time

    start = time.time()
    result = analyze_large_file("78k_entries.csv")
    elapsed = time.time() - start

    assert elapsed < 30, f"Trop lent: {elapsed}s"
```

## Risques et mitigations

| Risque | Probabilité | Impact | Mitigation |
|--------|-------------|--------|------------|
| API différente cause bugs | Medium | High | Tests exhaustifs, migration progressive |
| Dépendance Polars instable | Low | Medium | Fallback Pandas automatique |
| Performance non atteinte | Low | Medium | Optimisation lazy, profiling |

## Ressources

- [Polars User Guide](https://pola-rs.github.io/polars/py-polars/html/reference/)
- [Coming from Pandas](https://pola-rs.github.io/polars-book/user-guide/migration/pandas/)
- [Benchmark Polars vs Pandas](https://h2oai.github.io/db-benchmark/)
