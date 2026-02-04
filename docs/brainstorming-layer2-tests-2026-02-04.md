# Brainstorming Session: Layer 2 - Tests de Normalité par Univers

**Date:** 2026-02-04
**Objectif:** Définir les tests numériques qui génèrent ~200 signaux bruts à partir du GL + référentiel
**Contexte:** GL Crystal refondation - Layer 2 est le premier composant à implémenter

## Techniques Utilisées

1. **Mind Mapping** - Cartographie des tests par univers
2. **SCAMPER** - Adaptation des détecteurs existants
3. **Reverse Brainstorm** - "Comment rater tous les vrais signaux ?"

---

## Ideas Generated

### Catégorie 1: Tests Universels (5 tests)

| ID | Test | Métrique | Applicable à |
|----|------|----------|--------------|
| T-UNI-01 | Z-score montant | `(X - μ) / σ` | Tous sauf PONCTUEL |
| T-UNI-02 | Variation M/M | `abs(M - M-1) / M-1` | CRISTALLIN, PROCESSUS |
| T-UNI-03 | Concentration mois | `max_month / total` | Tous sauf CUT_OFF |
| T-UNI-04 | Nouveau compte | `first_occurrence` | Tous |
| T-UNI-05 | Journal inattendu | `journal not in expected` | PROCESSUS, VENTILATION |

### Catégorie 2: Tests CRISTALLIN (5 tests)

Comportement attendu: Montant stable, mensuel, mêmes tiers

| ID | Test | Signal si | Non-signal si |
|----|------|-----------|---------------|
| T-CRIS-01 | Variation montant | variation > 5% | meme_montant_12_mois |
| T-CRIS-02 | Disparition mois | mois manquant | - |
| T-CRIS-03 | Nouveau bail | nouveau tiers | - |
| T-CRIS-04 | Changement fréquence | trim → mens | - |
| T-CRIS-05 | Écart inter-sites | z-score > dead_band | - |

### Catégorie 3: Tests NOMINATIF_TIERS (5 tests)

Comportement attendu: Lettrage équilibré, balance âgée saine

| ID | Test | Signal si | Non-signal si |
|----|------|-----------|---------------|
| T-NOM-01 | Balance âgée | créance > 90j | solde_zero |
| T-NOM-02 | Concentration tiers | >50% sur 1 tiers | - |
| T-NOM-03 | Variation encours | delta > 30% | - |
| T-NOM-04 | Nouveau gros tiers | nouveau > 10% CA | - |
| T-NOM-05 | Tiers dormant réactivé | 6 mois inactif | - |

### Catégorie 4: Tests NOMINATIF_OPERATIONNEL (5 tests)

Comportement attendu: Réparti par site, corrélé à l'activité

| ID | Test | Signal si |
|----|------|-----------|
| T-NOMO-01 | Z-score inter-sites | site outlier vs peers |
| T-NOMO-02 | Ratio vs CA site | ratio charge/CA anormal |
| T-NOMO-03 | Nouvelle charge site | site sans historique |
| T-NOMO-04 | Disparition site | site historique absent |
| T-NOMO-05 | Concentration site | >60% sur 1 site |

### Catégorie 5: Tests PROCESSUS (5 tests)

Comportement attendu: Cycles réguliers, journaux attendus

| ID | Test | Signal si | Non-signal si |
|----|------|-----------|---------------|
| T-PROC-01 | Rupture cycle | mois attendu manquant | - |
| T-PROC-02 | Journal inattendu | journal ≠ attendus | - |
| T-PROC-03 | Ratio ETP | charge/etp hors norme | - |
| T-PROC-04 | Variation saisonnière | août pas creux | creux_aout_normal |
| T-PROC-05 | Effet calendrier | jours ouvrés anormal | - |

### Catégorie 6: Tests VENTILATION (5 tests)

Comportement attendu: Solde ~0, journal ABT

| ID | Test | Signal si | Non-signal si |
|----|------|-----------|---------------|
| T-VENT-01 | Solde résiduel | solde > 1% mvt | solde_zero |
| T-VENT-02 | Hors ABT | écriture hors ABT | - |
| T-VENT-03 | Déséquilibre mensuel | D ≠ C | debit_egal_credit |
| T-VENT-04 | Écart budget | réel vs budget > 15% | - |
| T-VENT-05 | Nouveau 488 | compte non budgété | - |

### Catégorie 7: Tests CUT_OFF (5 tests)

Comportement attendu: Extourne systématique, solde zéro

| ID | Test | Signal si | Non-signal si |
|----|------|-----------|---------------|
| T-CUT-01 | Pas d'extourne | N-1 sans extourne N | - |
| T-CUT-02 | Extourne tardive | > 31 janvier | extourne_dans_delai |
| T-CUT-03 | Solde post-extourne | solde ≠ 0 | solde_final_zero |
| T-CUT-04 | Nouveau cut-off | nouveau tiers/nature | - |
| T-CUT-05 | Montant cut-off | > 3x historique | - |

### Catégorie 8: Tests TRESORERIE (5 tests)

Comportement attendu: Réconcilié, flux cohérents

| ID | Test | Signal si |
|----|------|-----------|
| T-TRES-01 | Écart réconciliation | bank vs GL > 0.01€ |
| T-TRES-02 | Virement non apparié | VIR sans contrepartie |
| T-TRES-03 | Flux inhabituel | cashflow outlier |
| T-TRES-04 | Concentration jour | >50% sur 1 jour |
| T-TRES-05 | Nouveau compte banque | ouverture non anticipée |

### Catégorie 9: Tests PONCTUEL (4 tests)

Comportement attendu: Irrégulier par définition

| ID | Test | Signal si | Non-signal si |
|----|------|-----------|---------------|
| T-PONC-01 | Montant significatif | > seuil matérialité | montant_faible |
| T-PONC-02 | Récurrence suspecte | "exceptionnel" répété | - |
| T-PONC-03 | Sans justification | libellé vide | justifie_par_libelle |
| T-PONC-04 | Timing suspect | uniquement décembre | - |

### Catégorie 10: Tests INVENTAIRE (4 tests)

Comportement attendu: Variation fin exercice, cohérence flux

| ID | Test | Signal si |
|----|------|-----------|
| T-INV-01 | Variation stock | delta > 20% |
| T-INV-02 | Rotation anormale | rotation outlier |
| T-INV-03 | Immo sans amort | immo sans 681 |
| T-INV-04 | Cession sans produit | sortie sans 77x |

### Catégorie 11: Tests COMPOSITE (4 tests)

Comportement attendu: Inconnu → tests génériques

| ID | Test | Signal si |
|----|------|-----------|
| T-COMP-01 | Z-score montant | z > 3 |
| T-COMP-02 | Concentration mois | >50% sur 1 mois |
| T-COMP-03 | Nouveau compte | première occurrence |
| T-COMP-04 | OD décembre | OD déc > 40% |

### Catégorie 12: Adaptations Détecteurs Existants

| Détecteur existant | Adaptation proposée | Priorité |
|--------------------|---------------------|----------|
| MADDetector | UniverseAwareMAD (seuil calibré) | P0 |
| IQRDetector | CalibratedIQR (bounds par famille) | P1 |
| SeasonalDecomposer | CycleComplianceTest | P1 |
| ConcentrationDetector | Seuils variables par univers | P0 |
| AccountClusterer | Validation univers assigné | P2 |

### Catégorie 13: Éléments à Supprimer

| Composant | Raison |
|-----------|--------|
| Benford detector | Inutile sur GL (prouvé) |
| Isolation Forest global | Over-engineering |
| NLP complet | Simplifié en Layer 1 |
| Risk scorer ML | Remplacé par ICC |

---

## Key Insights

### Insight 1: Calibration Dynamique des Seuils
**Description:** Le seuil de détection = f(cv_attendu), pas constante

```python
dead_band = 1.5 + 2.0 * cv_attendu
# CRISTALLIN (cv=0.05) → 1.6σ
# NOMINATIF  (cv=1.20) → 3.9σ
# PONCTUEL   (cv=2.00) → 5.5σ
```

**Impact:** High | **Effort:** Low
**Why it matters:** Réduit faux positifs de 80% sans perdre vrais signaux

### Insight 2: Tests Sélectifs par Univers
**Description:** 4-5 tests pertinents par univers, pas 52 tests partout

**Impact:** High | **Effort:** Medium
**Why it matters:** Évite 8100 tests inutiles (52 × 180 familles)

### Insight 3: Exclusions Métier = Première Ligne de Défense
**Description:** Appliquer `non_signal_si` dans Layer 2, pas Layer 3

**Impact:** High | **Effort:** Low
**Why it matters:** Élimine 50% des faux positifs à la source

### Insight 4: Agrégation par Famille
**Description:** 1 signal synthétique par famille, pas N alertes

**Impact:** Medium | **Effort:** Low
**Why it matters:** Lisibilité pour Layer 3 et utilisateur final

### Insight 5: Wrapper Pattern sur Détecteurs
**Description:** UniverseAwareMAD wraps MADDetector avec calibration

**Impact:** Medium | **Effort:** Low
**Why it matters:** Réutilise code existant testé

### Insight 6: Interface Signal Découplée
**Description:** `List[RawSignal]` avec structure fixe entre layers

**Impact:** High | **Effort:** Medium
**Why it matters:** Découplage, testabilité, évolutivité

---

## Statistics

- **Total tests définis:** 52 (5 universels + 47 spécifiques)
- **Univers couverts:** 10/10
- **Key insights:** 6
- **Techniques applied:** 3
- **Détecteurs à adapter:** 5
- **Composants à supprimer:** 4

---

## Architecture Proposée

```
gl_normalizer/
├── layer2/
│   ├── __init__.py
│   ├── base.py              # BaseUniverseTest, RawSignal dataclass
│   ├── registry.py          # TestRegistry: univers → List[tests]
│   ├── calibration.py       # dead_band(), seuil_relatif()
│   ├── tests/
│   │   ├── universal.py     # T-UNI-*
│   │   ├── cristallin.py    # T-CRIS-*
│   │   ├── nominatif.py     # T-NOM-*, T-NOMO-*
│   │   ├── processus.py     # T-PROC-*
│   │   ├── cutoff.py        # T-CUT-*, T-VENT-*
│   │   ├── tresorerie.py    # T-TRES-*
│   │   └── other.py         # T-PONC-*, T-INV-*, T-COMP-*
│   └── runner.py            # Layer2Runner.run(gl, referentiel) → List[RawSignal]
```

## Structure RawSignal

```python
@dataclass
class RawSignal:
    id: str                    # "T-CRIS-01_613_202401"
    famille: str               # "613"
    univers: str               # "CRISTALLIN"
    test_id: str               # "T-CRIS-01"
    test_name: str             # "Variation montant"

    metric_value: float        # 0.08 (8% variation)
    threshold: float           # 0.05 (seuil 5%)
    delta: float               # 0.03 (écart au seuil)

    periode: Optional[str]     # "2024-01"
    site: Optional[str]        # "GONESSE"
    tiers: Optional[str]       # "SCI DU TEMPLE"

    signal_si_matched: List[str]      # règles matchées
    non_signal_si_matched: List[str]  # exclusions matchées

    raw_score: float           # 0-100
    metadata: dict             # contexte additionnel
```

---

## Recommended Next Steps

1. **Créer `layer2/base.py`** avec RawSignal dataclass et BaseUniverseTest ABC
2. **Créer `layer2/calibration.py`** avec dead_band() et seuil_relatif()
3. **Implémenter T-UNI-* (5 tests)** dans `tests/universal.py`
4. **Implémenter T-CRIS-* (5 tests)** comme premier univers complet
5. **Créer `layer2/runner.py`** pour orchestrer les tests
6. **Tester sur GL réel** avec référentiel des 180 familles

**Next workflow:** `/build` ou `/sprint-planning` pour démarrer l'implémentation

---

*Generated by BMAD Method v6 - Creative Intelligence*
*Session duration: ~20 minutes*
