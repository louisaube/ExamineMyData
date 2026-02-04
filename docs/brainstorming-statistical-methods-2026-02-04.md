# Brainstorming Session: Méthodes Statistiques Distribution-Free pour Layer 2

**Date:** 2026-02-04
**Objectif:** Sélectionner et intégrer des méthodes statistiques modernes adaptées aux données comptables
**Contexte:** GL Crystal refondation - remplacement des seuils heuristiques par des méthodes avec garanties formelles

## Techniques Used

1. **Research** - Analyse de la littérature récente (2022-2024)
2. **SWOT** - Évaluation forces/faiblesses de chaque méthode
3. **Decision Matrix** - Mapping méthode × univers

---

## Méthodes Retenues (V1)

### 1. Conformal Prediction (Vovk 2005, Bates et al. 2023)

**Fichier:** `calibration.py`

**Principe:** P-value distribution-free avec garantie de couverture finie.
Au lieu de z > seuil, on calcule: "quelle fraction des points de calibration
sont au moins aussi extrêmes que le nouveau point?"

**Garantie:** Sous échangeabilité, P(p-value ≤ α) ≤ α

**Implémentation:**
```python
def conformal_pvalue(x_new, calibration_set):
    scores = [nonconformity(x, calibration_set) for x in calibration_set]
    score_new = nonconformity(x_new, calibration_set)
    return (1 + sum(s >= score_new for s in scores)) / (1 + len(scores))
```

**Usage:**
- Standard pour toutes les familles avec ≥6 mois de données
- Fallback: dead_band heuristique si <6 mois

**Impact:** Remplace les z-scores gaussiens par des p-values exactes sans hypothèse distributionnelle.

---

### 2. Matrix Profile (Yeh et al. 2016, STUMPY 2019-2024)

**Fichier:** `statistical.py`

**Principe:** Trouve le "discord" (sous-séquence la plus atypique) dans une série temporelle.
Le discord est le point ayant la plus grande distance à son plus proche voisin.

**Avantage:** Aucun paramètre à définir pour "anormal". La méthode trouve automatiquement
LE mois qui ne ressemble à aucun autre.

**Implémentation:**
```python
import stumpy
mp = stumpy.stump(monthly_amounts, m=3)  # fenêtre 3 mois
discord_idx = mp[:, 0].argmax()
```

**Usage:**
- CRISTALLIN (7 familles): loyers, abonnements fixes
- PROCESSUS (16 familles): charges sociales, fiscales cycliques

**Impact:** Détection de rupture sans seuil arbitraire.

---

### 3. Benjamini-Hochberg FDR (1995)

**Fichier:** `fdr_filter.py`

**Principe:** Contrôle du False Discovery Rate. Avec 230 familles × 18 tests = 4140 hypothèses,
sans correction on a quasi-certitude de faux positifs. BH garantit:
"parmi les signaux remontés, au plus α% sont des faux positifs"

**Implémentation:**
```python
from scipy.stats import false_discovery_control
adjusted = false_discovery_control(raw_pvalues, method='bh')
signals = [s for s, p in zip(all_signals, adjusted) if p < 0.05]
```

**Usage:** Layer 2.5 - entre génération des signaux et filtrage métier

**Impact:** ~200 signaux bruts → ~40 signaux statistiquement significatifs

---

### 4. ECOD (Li et al. 2022)

**Fichier:** `statistical.py`

**Principe:** Scoring multivarié via CDF empirique. Chaque dimension contribue
indépendamment au score d'anomalie via sa position dans la distribution empirique.

**Avantage:** Pas d'hypothèse de distribution, interprétable (on sait quelle feature est anormale).

**Usage:**
- COMPOSITE: familles non classifiables
- NOMINATIF_OPERATIONNEL: scoring multi-features (montant × site × fréquence)

---

## Méthodes Différées (V2)

### BOCPD (Adams & MacKay 2007)

**Principe:** Détecte QUAND une série change de régime, pas juste SI elle est anormale.

**Exemple:** Loyer passant de 2500€ à 2700€ en mars = "changement de régime en mars, p=94%"

**Raison du report:** Matrix Profile discord fait 80% du travail. BOCPD ajoute
la distinction "changement permanent vs one-off" - utile mais pas critique pour V1.

---

## Méthodes Rejetées

| Méthode | Raison du rejet |
|---------|-----------------|
| Autoencodeurs | 12 points par série - ridicule pour deep learning |
| Transformers (TimesFM, Chronos) | Besoin de milliers de points |
| Graph Neural Networks | Pas de structure de graphe naturelle |
| LLM-based anomaly detection | Boîte noire, non auditable |
| Isolation Forest global | Over-engineering, déjà éliminé en v1 |
| Benford's Law | Inutile sur GL (prouvé statistiquement) |

---

## Architecture Finale

```
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 2: Tests (génère signaux avec p-values)                   │
├─────────────────────────────────────────────────────────────────┤
│  Conformal Prediction → toutes familles (≥6 mois)               │
│  Dead Band fallback   → familles avec <6 mois                   │
│  Matrix Profile       → CRISTALLIN (7) + PROCESSUS (16)         │
│  ECOD                 → COMPOSITE + NOMINATIF_OPE               │
│                                                                 │
│  Output: ~200 signaux avec p-value chacun                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 2.5: BH-FDR Filter                                        │
├─────────────────────────────────────────────────────────────────┤
│  adjusted = false_discovery_control(pvalues, method='bh')       │
│  Output: ~40 signaux FDR-contrôlés                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 3: Filtres Métier                                         │
│  - Matérialité (> seuil €)                                      │
│  - Exclusions (non_signal_si)                                   │
│  Output: ~15 anomalies qualifiées                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Insights

### Insight 1: Conformal = Standard, Dead Band = Fallback
**Impact:** High | **Effort:** Low
Le conformal p-value est distribution-free et garantit une couverture exacte.
Dead band ne sert que pour les familles PONCTUEL avec peu de données.

### Insight 2: BH-FDR est Critique
**Impact:** Critical | **Effort:** Trivial (5 lignes)
Sans correction multiple testing, on retombe dans le piège du Normalizer v1
(2061 "anomalies" dont 80% de bruit statistique).

### Insight 3: Matrix Profile Ciblé
**Impact:** High | **Effort:** Low
STUMPY sur 23 familles = <1 seconde. Détecte les discords sans paramètre.

### Insight 4: ECOD pour Multivarié
**Impact:** Medium | **Effort:** Low
Quand on ne sait pas quelle feature sera anormale (COMPOSITE),
ECOD score toutes les dimensions indépendamment.

---

## Dépendances Ajoutées

```
numpy          # Déjà présent
scipy          # Pour BH-FDR (false_discovery_control)
stumpy         # Matrix Profile (optionnel, fallback implémenté)
```

---

## Fichiers Créés/Modifiés

| Fichier | Changements |
|---------|-------------|
| `calibration.py` | +conformal_pvalue(), conformal_or_fallback() |
| `statistical.py` | NOUVEAU - Matrix Profile, ECOD |
| `fdr_filter.py` | NOUVEAU - BH-FDR |
| `base.py` | +pvalue, pvalue_adjusted, detection_method |
| `runner.py` | NOUVEAU - Layer2Runner orchestration |
| `__init__.py` | Exports mis à jour |

---

## Next Steps

1. **Layer 3:** Implémenter filtres métier (matérialité, exclusions signal_si/non_signal_si)
2. **Test réel:** Valider sur GL Finthesis avec référentiel 180 familles
3. **V2:** Ajouter BOCPD pour détection de changement de régime

---

*Generated by BMAD Method v6 - Creative Intelligence*
*Session duration: ~30 minutes*
