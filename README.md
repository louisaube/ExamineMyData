# GL Normalizer

Analyse et normalisation du P&L pour comparer deux périodes comptables en **neutralisant les artefacts comptables** (régularisations, provisions concentrées, charges one-shot) et obtenir le **run rate opérationnel réel**.

## Problématique

Le P&L de décembre est souvent pollué par :

| Type | Exemple | Impact |
|------|---------|--------|
| Régularisations pluriannuelles | Dégrèvements TS 2022/2023/2024 | Gonfle/dégonfle artificiellement |
| Dotations annuelles concentrées | IS, amortissements | Charge 12 mois sur 1 mois |
| Provisions oubliées | FNP, charges à payer | Charges mal réparties |
| Sur-provisionnement antérieur | Reprise de provisions | Allège artificiellement |

**Résultat** : Une variation apparente de +556k€ peut être en réalité de -3k€.

## Installation

```bash
pip install -r requirements.txt
```

Ou avec pip editable :

```bash
pip install -e .
```

## Usage rapide

```python
from gl_normalizer import compare_years, generate_excel_report

# Comparer deux années
comparison = compare_years("GL_2024.xlsx", "GL_2025.xlsx")

# Afficher les résultats
print(f"Variation brute (comptable):  {comparison.variation_brute:>+12,.0f}€")
print(f"Variation réelle (run rate): {comparison.variation_normalisee:>+12,.0f}€")
print(f"Écart (artefacts):           {comparison.ecart_normalisation:>+12,.0f}€")

# Générer un rapport Excel
generate_excel_report(comparison, "rapport_normalisation.xlsx")
```

## Usage avancé

### Charger et classifier un GL

```python
from gl_normalizer import load_gl, classify_gl

# Charger (détection automatique du format: Sage, Cegid, générique)
df = load_gl("mon_gl.xlsx")

# Classifier les écritures
df_classified = classify_gl(df)
```

### Analyser les provisions

```python
from gl_normalizer import PnLNormalizer

normalizer = PnLNormalizer(df_classified, 2025)

# Provisions avec impact significatif
provisions = normalizer.analyze_provisions()
for p in provisions[:5]:
    print(f"{p.compte}: Déc brut={p.decembre_brut:,.0f}€, Impact={p.ecart_decembre:+,.0f}€")

# Anomalies statistiques (z-score)
anomalies = normalizer.detect_anomalies()
for a in anomalies[:5]:
    print(f"{a.compte} {a.mois}: {a.nature} (z={a.z_score:+.1f})")
```

### Drill-down sur un compte

```python
from gl_normalizer.drilldown import VariationDrilldown

drilldown = VariationDrilldown(df_2024, df_2025, 2024, 2025)
analysis = drilldown.analyze_account("631111000")

# Rapport formaté
print(drilldown.format_drilldown_report(analysis))

# Ou accès aux données
print(f"Nouvelles écritures: {len(analysis.groupes_nouvelles)}")
print(f"Écritures disparues: {len(analysis.groupes_disparues)}")
```

### Comparaison complète avec rapport

```python
from gl_normalizer import GLComparator, generate_excel_report, generate_text_report

comparator = GLComparator("GL_2024.xlsx", "GL_2025.xlsx")
comparison = comparator.compare()

# Rapport Excel multi-onglets
generate_excel_report(comparison, "rapport.xlsx", comparator)

# Rapport texte
print(generate_text_report(comparison))
```

## Structure du package

```
gl_normalizer/
├── __init__.py          # API publique
├── config.py            # Configuration et constantes
├── loader.py            # Chargement et harmonisation GL
├── classifier.py        # Classification des écritures
├── pnl_normalizer.py    # Redistribution des provisions
├── drilldown.py         # Analyse fine par compte
├── comparator.py        # Comparaison inter-années
└── reporter.py          # Génération des rapports
```

## Méthodologie

### 1. Chargement & Harmonisation
- Détection automatique du format (Sage, Cegid, export brut)
- Normalisation des colonnes : date, compte, journal, débit, crédit
- Ajout colonnes calculées : période, classe, racine

### 2. Classification des Écritures
- Identification des contreparties bilan (classe 4)
- Attribution d'un type : RUN_RATE, SEASONAL, ESTIMATIF, ONE_SHOT
- Règles basées sur : journal, contrepartie, libellé, montant

### 3. Détection d'Anomalies
```
Z-score = (Valeur_mois - Moyenne_année) / Écart_type_année

EXCES si : Z > seuil ET |écart| > min_absolu ET |écart%| > min_pct
DEFICIT si : Z < -seuil (mêmes conditions)
```

### 4. Redistribution des Provisions
```
Total_annuel = Σ(charges mois 1 à 12)
Run_rate_mensuel = Total_annuel / 12
Décembre_normalisé = Run_rate_mensuel
Impact = Décembre_normalisé - Décembre_brut
```

### 5. Drill-down
- Normalisation des libellés (retrait dates, numéros)
- Regroupement par nature
- Identification : NOUVELLES, DISPARUES, VARIÉES
- Construction du bridge de variation

## Configuration

```python
from gl_normalizer import NormalizerConfig

config = NormalizerConfig(
    z_score_threshold=1.5,      # Écarts-types pour anomalie
    min_ecart_absolu=2000,      # € minimum pour signaler
    min_ecart_pct=30,           # % minimum pour signaler
    seuil_regul=2000,           # Régularisation significative
)

comparison = compare_years("GL_2024.xlsx", "GL_2025.xlsx", config=config)
```

## Limites

- Ne juge pas la pertinence comptable des écritures
- Ne détecte pas les erreurs de classification de compte
- N'anticipe pas les provisions futures
- Ne remplace pas le jugement de l'analyste

## Licence

MIT
