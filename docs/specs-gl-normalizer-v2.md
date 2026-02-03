# GL Normalizer v2 - Spécifications

**Philosophie** : Un comptable senior automatisé, pas un data scientist.

**Objectif unique** : Transformer un GL brut en tableau de passage vers le run rate réel.

---

## Architecture en 4 couches

```
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 4 : IA (filet de sécurité)                         │
│  Uniquement pour les cas ambigus                            │
├─────────────────────────────────────────────────────────────┤
│  COUCHE 3 : Alertes contextuelles                          │
│  "Nouvelle provision prud'hommes 15K, non budgétée"         │
├─────────────────────────────────────────────────────────────┤
│  COUCHE 2 : Tableau de passage                             │
│  P&L brut → P&L normalisé, ligne par ligne                  │
├─────────────────────────────────────────────────────────────┤
│  COUCHE 1 : Lecture comptable                              │
│  Journaux, PCG, ABT, amortissements - bon sens codifié      │
└─────────────────────────────────────────────────────────────┘
```

---

## Couche 1 : Lecture comptable

### 1.1 Classification des journaux

| Code journal | Nature | Traitement |
|--------------|--------|------------|
| OD, OD*, AN | Opérations diverses / À-nouveau | Zone de vigilance - régularisations |
| SAL, PAI* | Paie | Récurrent mensuel, effet congés août |
| VTE, FAC* | Ventes / Facturation | Produits opérationnels |
| ACH, FRN* | Achats / Fournisseurs | Charges opérationnelles |
| BQ, BNQ* | Banque | Flux de trésorerie (hors P&L) |
| CAI* | Caisse | Flux de trésorerie (hors P&L) |

**Règle** : Tout journal OD de décembre avec volume > 3x moyenne mensuelle = drapeau rouge.

### 1.2 Classification PCG des comptes

| Classe | Nature | Comportement attendu |
|--------|--------|---------------------|
| 60 | Achats | Récurrent, corrélé à l'activité |
| 61-62 | Services extérieurs | Récurrent ou saisonnier |
| 63 | Impôts et taxes | ABT fréquent (CFE, CVAE, taxes foncières) |
| 64 | Personnel | Récurrent, creux août |
| 65 | Autres charges | Variable |
| 66 | Charges financières | Récurrent |
| 67 | Exceptionnel | One-shot par définition |
| 68 | Dotations amort/prov | À décomposer (voir 1.4) |
| 69 | IS | One-shot annuel |
| 70-74 | Produits exploitation | Récurrent |
| 75-76 | Produits financiers | Variable |
| 77 | Produits exceptionnels | One-shot |
| 78 | Reprises provisions | À coupler avec 68 |

### 1.3 Détection des mécanismes ABT (Abonnements)

**Définition** : Compte 488xxx qui solde à zéro (ou quasi-zéro) sur l'exercice.

**Pattern à détecter** :
```
Janv-Nov : provisions mensuelles régulières (même montant ou proche)
Décembre : contrepassation globale + charge réelle
Solde exercice : ~0
```

**Exemples typiques** :
- 488xxx Formation
- 488xxx Prud'hommes
- 488xxx CFE / CVAE
- 488xxx Taxes foncières
- 488xxx CAC
- 488xxx AGEFIPH

**Traitement** : Ces comptes sont du **bruit mensuel**. Le mécanisme est propre (étalement budgétaire). L'outil doit :
1. Les identifier automatiquement
2. Les exclure des "anomalies"
3. Montrer le solde net (doit être ~0)

### 1.4 Séparation amortissements vs provisions

| Type | Comptes | Comportement | Traitement run rate |
|------|---------|--------------|---------------------|
| Amortissements | 681 | Récurrent mensuel, prévisible | Aucun retraitement |
| Dépréciations actifs | 6816, 6817 | Ponctuel | Étaler ou one-shot |
| Provisions risques | 6815, 687 | Ponctuel | Analyser le motif |
| Reprises | 781, 787 | Contrepartie des provisions | Coupler avec la dotation |

**Règle clé** : Toujours lire les provisions (68x) avec leurs reprises (78x) pour calculer le **net**.

---

## Couche 2 : Tableau de passage

### 2.1 Structure du livrable

Pour chaque mois ET pour l'année :

```
┌────────────────────────────────────────────────────────────┐
│ TABLEAU DE PASSAGE - DÉCEMBRE 2024                         │
├────────────────────────────────────────────────────────────┤
│ Résultat comptable brut                      -30 000 €     │
├────────────────────────────────────────────────────────────┤
│ RETRAITEMENTS                                              │
│                                                            │
│ (-) IS (one-shot annuel)                    -234 000 €     │
│     → Étalé sur 12 mois : -19 500 €/mois                  │
│                                                            │
│ (-) Provisions créances (net)                -15 000 €     │
│     → Dotation 82K - Reprise 68K = 14K risque net         │
│                                                            │
│ (+) Contrepassation ABT                     +274 000 €     │
│     → Neutralisation du mécanisme d'étalement             │
│                                                            │
│ (-) Charges exceptionnelles nettes           -12 000 €     │
│     → 67xxx - 77xxx                                        │
├────────────────────────────────────────────────────────────┤
│ = RÉSULTAT NORMALISÉ                        +193 000 €     │
└────────────────────────────────────────────────────────────┘
```

### 2.2 Synthèse annuelle

```
┌────────────────────────────────────────────────────────────┐
│ SYNTHÈSE RUN RATE - EXERCICE 2024                          │
├────────────────────────────────────────────────────────────┤
│                          BRUT         NORMALISÉ    ÉCART   │
│ Charges mensuelles      897 K€        861 K€      -4%     │
│ Produits mensuels       955 K€        948 K€      -1%     │
│ Résultat annuel         694 K€        917 K€      +32%    │
├────────────────────────────────────────────────────────────┤
│ DÉCOMPOSITION DES RETRAITEMENTS                            │
│                                                            │
│ IS annuel redistribué                        +234 K€       │
│ Provisions créances (risque net)              -15 K€       │
│ Exceptionnel net                               +4 K€       │
│ ABT (neutre sur l'année)                        0 K€       │
│ ─────────────────────────────────────────────────────      │
│ Total retraitements                          +223 K€       │
└────────────────────────────────────────────────────────────┘
```

### 2.3 Règles de retraitement

| Élément | Règle | Justification |
|---------|-------|---------------|
| IS (695) | Étaler sur 12 mois | One-shot non-opérationnel |
| Exceptionnel (67/77) | Exclure du run rate | Par définition non récurrent |
| Provisions/reprises | Prendre le net annuel | Lire le couple ensemble |
| ABT (488 qui soldent) | Neutraliser le mensuel | Bruit budgétaire |
| Amortissements (681) | Ne pas toucher | Déjà étalés, récurrents |
| Saisonnalité août | Ne pas toucher | Effet réel (congés) |

---

## Couche 3 : Alertes contextuelles

### 3.1 Ce qu'on NE signale PAS

| Fausse alerte | Pourquoi c'est normal |
|---------------|----------------------|
| "Montant rond 60K sur 488622900" | C'est un ABT de 5K/mois × 12 |
| "Concentration décembre sur 681" | Amortissements = récurrents |
| "Creux charges en août" | Congés = réalité opérationnelle |
| "Volume OD décembre élevé" | Normal si ABT + clôture |

### 3.2 Ce qu'on SIGNALE

| Alerte utile | Contexte fourni |
|--------------|-----------------|
| "Nouvelle provision risques 15K" | "Libellé : prud'hommes. Pas d'ABT associé → non budgété" |
| "Dotation créances 82K sans reprise proportionnelle" | "Historique N-1 : 45K dotation, 40K reprise. Variation nette +37K" |
| "Compte 648 nouveau en décembre" | "Intéressement ? Prime exceptionnelle ? À qualifier" |
| "Reprise provision 68K sans dotation récente" | "Dernière dotation il y a 18 mois. Risque disparu ou opportunisme ?" |

### 3.3 Format des alertes

```
┌─────────────────────────────────────────────────────────────┐
│ ⚠ ALERTE #1 - Provision non budgétée                       │
├─────────────────────────────────────────────────────────────┤
│ Compte    : 6815 - Provisions pour risques                  │
│ Montant   : 15 000 €                                        │
│ Mois      : Décembre uniquement                             │
│ Libellé   : "Provision prud'hommes Dupont"                  │
│                                                             │
│ CONTEXTE :                                                  │
│ - Pas de compte 488 associé (non anticipé dans le budget)   │
│ - Première apparition de ce risque dans le GL               │
│ - Impact run rate si récurrent : +15K€/an                   │
│                                                             │
│ QUESTION : Ce litige est-il ponctuel ou récurrent ?         │
└─────────────────────────────────────────────────────────────┘
```

---

## Couche 4 : IA (filet de sécurité)

### 4.1 Quand l'IA intervient

| Cas | Exemple | Intervention IA |
|-----|---------|-----------------|
| Libellé flou | "Régul div." | NLP pour suggérer une catégorie |
| Compte ambigu | 658 avec comportement variable | Clustering pour comparer à l'historique |
| Changement de comportement | Compte stable qui devient volatile | Détection de rupture |
| Volume trop important pour revue manuelle | >500 écritures OD décembre | Priorisation par scoring |

### 4.2 Ce que l'IA ne fait PAS

- Ne remplace pas le classement PCG
- Ne décide pas des retraitements
- Ne génère pas d'alertes sans contexte métier
- N'est pas activée par défaut

### 4.3 Modules IA conservés (optionnels)

| Module | Usage limité à |
|--------|----------------|
| NLP libellés | Extraction mots-clés (prud'hommes, CFE, etc.) |
| Détection rupture | Compte qui change de comportement N vs N-1 |
| Clustering | Regrouper les comptes à comportement similaire |

**Modules supprimés** : Benford, Isolation Forest, XGBoost, Autoencoder, scoring de risque générique.

---

## Livrable final

### Format Excel avec 4 onglets

1. **Synthèse** : Run rate brut vs normalisé, écarts clés
2. **Tableau de passage** : Mois par mois, ligne par ligne
3. **Alertes** : Les 5-10 points à valider avec l'expert-comptable
4. **Détail retraitements** : Chaque écriture retraitée avec justification

### Temps cible

| Étape | Durée |
|-------|-------|
| Import GL | < 30 sec |
| Analyse complète | < 2 min |
| Lecture rapport par DAF | < 5 min |

---

## Métriques de succès

| Métrique | Cible |
|----------|-------|
| Faux positifs (alertes inutiles) | < 10% |
| Couverture retraitements | 100% des one-shots identifiés |
| Écart run rate brut/normalisé calculé | Toujours affiché |
| Temps de prise en main | < 15 min sans formation |

---

## Ce qu'on jette de v1

- 7 fichiers de tests → 2 fichiers (couche 1 + couche 2)
- 78 fonctions de test → ~20 tests ciblés
- 5 algorithmes IA en fondation → 0 (IA en couche 4 optionnelle)
- Scoring de risque générique → Supprimé
- Questions drill-down génériques → Alertes contextuelles

---

*"L'outil doit faire le travail d'un comptable senior en 2 minutes, pas celui d'un data scientist en 2 heures."*
