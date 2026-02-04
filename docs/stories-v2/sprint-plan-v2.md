# Sprint Plan v2 - GL Normalizer

**Date:** 2026-02-03
**Architecture:** [architecture-v2-2026-02-03.md](../architecture-v2-2026-02-03.md)

---

## Vue d'ensemble

| Epic | Stories | Points | Priorité |
|------|---------|--------|----------|
| **EPIC-201** Couche 1 - Lecture comptable | 5 | 10 | Must Have |
| **EPIC-202** Couche 2 - Tableau de passage | 2 | 8 | Must Have |
| **EPIC-203** Couche 3 - Alertes | 1 | 3 | Must Have |
| **EPIC-204** Couche 4 - IA optionnelle | 2 | 4 | Could Have |
| **Total** | **10** | **25** | |

---

## Stories par Epic

### EPIC-201 : Couche 1 - Lecture comptable

| ID | Story | Points | Dépendances |
|----|-------|--------|-------------|
| STORY-201 | GLLoader | 2 | - |
| STORY-202 | JournalClassifier | 1 | 201 |
| STORY-203 | PCGClassifier | 2 | 201 |
| STORY-204 | ABTDetector | 3 | 201, 203 |
| STORY-205 | ProvisionMatcher | 2 | 201, 203 |

**Sous-total : 10 points**

### EPIC-202 : Couche 2 - Tableau de passage

| ID | Story | Points | Dépendances |
|----|-------|--------|-------------|
| STORY-206 | PassageTableBuilder | 5 | 201-205 |
| STORY-208 | ExcelReporter | 3 | 206, 207 |

**Sous-total : 8 points**

### EPIC-203 : Couche 3 - Alertes

| ID | Story | Points | Dépendances |
|----|-------|--------|-------------|
| STORY-207 | AlertGenerator | 3 | 201-206 |

**Sous-total : 3 points**

### EPIC-204 : Couche 4 - IA optionnelle

| ID | Story | Points | Dépendances |
|----|-------|--------|-------------|
| STORY-209 | NLPKeywordExtractor | 2 | 204 |
| STORY-210 | BehaviorChangeDetector | 2 | 203 |

**Sous-total : 4 points**

---

## Ordre d'implémentation suggéré

### Sprint 1 : Fondations (10 points)

```
STORY-201 GLLoader
    ↓
STORY-202 JournalClassifier   STORY-203 PCGClassifier
    ↓                              ↓
    └──────────────┬───────────────┘
                   ↓
STORY-204 ABTDetector   STORY-205 ProvisionMatcher
```

**Livrable** : Lecture complète du GL avec classification

### Sprint 2 : Coeur (8 points)

```
STORY-206 PassageTableBuilder (5 pts)
    ↓
STORY-207 AlertGenerator (3 pts)
```

**Livrable** : Tableau de passage fonctionnel + alertes

### Sprint 3 : Finalisation (7 points)

```
STORY-208 ExcelReporter (3 pts)
STORY-209 NLPKeywordExtractor (2 pts)
STORY-210 BehaviorChangeDetector (2 pts)
```

**Livrable** : Produit complet

---

## Comparaison v1 vs v2

| Métrique | v1 | v2 |
|----------|----|----|
| Stories | 18-27 | 10 |
| Points | ~60 | 25 |
| Tests | 78 | ~20 |
| Modules IA | 5 (obligatoires) | 2 (optionnels) |
| Temps estimé | 8+ sprints | 3 sprints |

---

## Critères de validation

### Definition of Done par story

- [ ] Code implémenté
- [ ] Tests unitaires passants
- [ ] Documentation inline (docstrings)
- [ ] Revue du livrable

### Definition of Done produit

- [ ] Tableau de passage généré pour GL test MicroStars
- [ ] Run rate calculé : 861K (vs 897K brut)
- [ ] Résultat normalisé : 917K (vs 694K brut)
- [ ] < 5 alertes pertinentes générées
- [ ] Rapport Excel lisible en 30 secondes

---

## Fichiers des stories

```
docs/stories-v2/
├── sprint-plan-v2.md          # Ce fichier
├── STORY-201-gl-loader.md
├── STORY-202-journal-classifier.md
├── STORY-203-pcg-classifier.md
├── STORY-204-abt-detector.md
├── STORY-205-provision-matcher.md
├── STORY-206-passage-table-builder.md
├── STORY-207-alert-generator.md
├── STORY-208-excel-reporter.md
├── STORY-209-nlp-keywords.md
└── STORY-210-behavior-detector.md
```

---

*Document généré par BMAD Method v6 - Phase 4 Planning*
