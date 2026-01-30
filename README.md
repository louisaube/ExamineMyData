# GL Normalizer

**Traquer les provisions pour révéler le véritable Run Rate opérationnel.**

Outil d'analyse du Grand Livre (GL) qui **dépollue le P&L** des artefacts comptables (provisions injustifiées, enveloppes gonflées/dégonflées) pour calculer le **run rate réel** de l'entreprise.

## Prérequis

> ⚠️ **Comptabilité mensuelle requise**
>
> Cet outil nécessite une comptabilité tenue mensuellement. L'analyse repose sur la comparaison des patterns mensuels pour détecter les anomalies de provisionnement.

## Problématique

Les entreprises manipulent (consciemment ou non) leurs provisions :

| Pratique | Description | Effet sur le P&L |
|----------|-------------|------------------|
| **Enveloppes gonflées** | Provisions excessives par prudence ou pour lisser | Cache la vraie performance |
| **Enveloppes dégonflées** | Sous-provisionnement pour améliorer le résultat | Embellit artificiellement |
| **Provisions sans justification** | Maintien de provisions historiques jamais reprises | Réserve cachée |
| **Concentrations fin d'année** | Toutes les dotations en décembre | Écrase un mois, fausse les autres |
| **Reprises opportunistes** | Reprise de provisions au "bon moment" | Améliore artificiellement |

**L'objectif** : Exploiter la stabilité de la situation de fin d'année (quand tout est "tombé") pour calculer le véritable niveau de charges opérationnelles.

## Principe de fonctionnement

```
P&L Comptable (pollué)
        ↓
    ANALYSE
    - Détection des concentrations mensuelles anormales
    - Identification des patterns de provisionnement
    - Comparaison N vs N-1
        ↓
    DÉPOLLUTION
    - Redistribution des provisions sur 12 mois
    - Neutralisation des one-shots
    - Calcul du run rate mensuel
        ↓
Run Rate Réel (dépollué)
```

## Installation

```bash
pip install -r requirements.txt
```

Dépendances optionnelles pour le module IA :
```bash
pip install scikit-learn xgboost torch sentence-transformers
```

## Usage rapide

```python
from gl_normalizer import compare_years, generate_excel_report

# Comparer deux années (nécessite comptabilité mensuelle)
comparison = compare_years("GL_2024.xlsx", "GL_2025.xlsx")

# Résultats
print(f"Variation comptable:  {comparison.variation_brute:>+12,.0f}€")
print(f"Variation run rate:   {comparison.variation_normalisee:>+12,.0f}€")
print(f"Impact provisions:    {comparison.ecart_normalisation:>+12,.0f}€")

# Rapport Excel
generate_excel_report(comparison, "analyse_provisions.xlsx")
```

## Fonctionnalités principales

### 1. Traquer les provisions suspectes

```python
from gl_normalizer import PnLNormalizer

normalizer = PnLNormalizer(df, 2025)

# Provisions avec comportement anormal
provisions = normalizer.analyze_provisions()
for p in provisions[:5]:
    print(f"{p.compte}: Déc={p.decembre_brut:,.0f}€, Run rate={p.run_rate:,.0f}€, Écart={p.ecart_decembre:+,.0f}€")
```

### 2. Détecter les anomalies statistiques

```python
# Z-score pour identifier les mois anormaux
anomalies = normalizer.detect_anomalies()
for a in anomalies:
    print(f"{a.compte} mois {a.mois}: {a.nature} (z={a.z_score:+.1f})")
```

### 3. Analyser les journaux OD/Situation

```python
from gl_normalizer import ContentAnalyzer

analyzer = ContentAnalyzer(df, 2025)

# Identifier les journaux de régularisation
journals = analyzer.analyze_journals()
for j in journals:
    if j.is_od or j.is_situation:
        print(f"Journal {j.journal}: {j.nb_ecritures} écritures, {j.pct_decembre:.0f}% en décembre")
```

### 4. Module IA - Détection avancée

```python
from gl_normalizer.ai import RiskScorer

# Score de risque multi-modèles
scorer = RiskScorer(df)
scorer.fit()

# Écritures les plus suspectes
top_risks = scorer.get_top_anomalies(100)
print(top_risks[["compte", "libelle", "montant", "final_score", "risk_level"]])

# Explication d'une écriture
explanation = scorer.explain_entry(top_risks.index[0])
print(f"Facteurs: {explanation['contributing_factors']}")
```

## Structure du package

```
gl_normalizer/
├── __init__.py          # API publique
├── config.py            # Configuration
├── loader.py            # Chargement GL (multi-formats)
├── classifier.py        # Classification des écritures
├── pnl_normalizer.py    # Calcul du run rate
├── content_analyzer.py  # Analyse OD/patterns
├── drilldown.py         # Analyse par compte
├── comparator.py        # Comparaison N vs N-1
├── reporter.py          # Rapports Excel/texte
└── ai/                  # Module IA
    ├── benford.py       # Loi de Benford
    ├── isolation_forest.py
    ├── autoencoder.py   # Deep Learning
    ├── nlp_analyzer.py  # Analyse libellés
    ├── xgboost_scorer.py
    └── risk_scorer.py   # Score combiné
```

## Méthodologie

### Calcul du Run Rate

```
Total_annuel = Σ(charges mois 1 à 12)
Run_rate_mensuel = Total_annuel / 12

Si Décembre_brut >> Run_rate_mensuel → Concentration suspecte
Si Décembre_brut << Run_rate_mensuel → Sous-provisionnement
```

### Indicateurs de provisions suspectes

| Indicateur | Signal |
|------------|--------|
| Concentration > 50% en décembre | Provision annuelle concentrée |
| Z-score > 2 | Mois statistiquement anormal |
| Journal OD + montant rond | Écriture de régularisation |
| Libellé "provision", "dotation", "reprise" | Écriture de provision |
| Écart N/N-1 > 30% sans explication | Enveloppe modifiée |

### Module IA - Techniques utilisées

| Technique | Usage |
|-----------|-------|
| **Loi de Benford** | Détecter les montants fabriqués |
| **Isolation Forest** | Anomalies non supervisées |
| **Autoencoder** | Patterns complexes |
| **NLP** | Libellés suspects |
| **XGBoost** | Classification à risque |

## Formats supportés

- Sage
- Cegid
- Quadratus
- EBP
- Export Excel générique

Détection automatique du format et mapping des colonnes.

## Limites

- **Nécessite une comptabilité mensuelle** - Pas d'analyse possible sur comptabilité annuelle
- Ne juge pas la pertinence économique des provisions
- Ne détecte pas les erreurs d'imputation comptable
- Ne remplace pas le jugement de l'analyste/auditeur

## Licence

MIT

## Version

2.0.0 - Avec module IA
