# Product Brief v2 - GL Normalizer

**Date:** 2026-02-03
**Version:** 2.0
**Status:** Draft

---

## 1. Vision

> **"Un comptable senior automatisé, pas un data scientist lâché sur un fichier Excel."**

GL Normalizer transforme un Grand Livre brut en **tableau de passage** vers le run rate réel. C'est tout. C'est simple. C'est ce dont le DAF a besoin.

---

## 2. Le problème (reformulé)

### Ce que le DAF veut savoir

| Question | Réponse attendue |
|----------|------------------|
| "Quel est mon vrai run rate mensuel ?" | 861K (pas 897K brut) |
| "Mon résultat est-il bon ?" | 917K normalisé (pas 694K comptable) |
| "Pourquoi l'écart ?" | IS 234K + provisions 15K + ABT neutralisé |

### Ce que v1 lui donnait

- "114 montants ronds suspects"
- "Score de risque 81% - qualité Poor"
- "26 comptes avec >80% en décembre"

**Constat** : v1 liste les arbres, le DAF veut voir la forêt.

---

## 3. Ce que v2 doit faire

### Le livrable unique : Tableau de passage

```
┌────────────────────────────────────────────────────────────┐
│ TABLEAU DE PASSAGE - EXERCICE 2024                         │
├────────────────────────────────────────────────────────────┤
│ Résultat comptable                           694 000 €     │
├────────────────────────────────────────────────────────────┤
│ RETRAITEMENTS                                              │
│                                                            │
│ (+) IS annuel                               +234 000 €     │
│     One-shot → redistribué sur 12 mois                     │
│                                                            │
│ (-) Provisions créances (net)                -15 000 €     │
│     Dotation 82K - Reprise 68K = risque net               │
│                                                            │
│ (+) Exceptionnel net                          +4 000 €     │
│     67xxx - 77xxx                                          │
│                                                            │
│ (=) ABT neutralisé                                 0 €     │
│     17 comptes 488 soldent à zéro                         │
├────────────────────────────────────────────────────────────┤
│ = RÉSULTAT NORMALISÉ                         917 000 €     │
├────────────────────────────────────────────────────────────┤
│ Run rate charges : 861 K€/mois (vs 897K brut)              │
│ Écart résultat : +32%                                      │
└────────────────────────────────────────────────────────────┘
```

**C'est ça, le produit.** Un tableau qu'un DAF lit en 30 secondes.

---

## 4. Architecture en 4 couches

```
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 4 : IA (optionnelle)                               │
│  Uniquement pour libellés flous ou cas ambigus              │
├─────────────────────────────────────────────────────────────┤
│  COUCHE 3 : Alertes contextuelles                          │
│  "Provision prud'hommes 15K non budgétée" (pas "montant    │
│   rond suspect")                                            │
├─────────────────────────────────────────────────────────────┤
│  COUCHE 2 : Tableau de passage                    ← COEUR  │
│  P&L brut → P&L normalisé, ligne par ligne                  │
├─────────────────────────────────────────────────────────────┤
│  COUCHE 1 : Lecture comptable                              │
│  Journaux (OD, SAL, VTE), PCG, ABT (488), amortissements    │
└─────────────────────────────────────────────────────────────┘
```

**Inversion par rapport à v1** : Le bon sens comptable est en bas (fondation), l'IA est en haut (filet de sécurité).

---

## 5. Les 4 types de "pollution" à traiter

| Type | Détection | Traitement |
|------|-----------|------------|
| **1. ABT (comptes 488)** | Compte qui solde à zéro sur l'année | Neutraliser le bruit mensuel |
| **2. One-shots** | IS (695), exceptionnel (67/77) | Redistribuer sur 12 mois ou exclure |
| **3. Couples prov/reprise** | 68x avec 78x en face | Calculer le net |
| **4. Saisonnalité réelle** | Août creux (congés) | NE PAS toucher (c'est vrai) |

---

## 6. Ce qu'on ne fait plus

| v1 (supprimé) | Pourquoi |
|---------------|----------|
| Loi de Benford | Over-engineering - le comptable sait ce qui est suspect |
| Isolation Forest | Idem |
| XGBoost scoring | Idem |
| Autoencoder | Idem |
| "114 montants ronds" | Bruit, pas signal |
| Scoring risque générique | Inutile sans contexte métier |
| 78 tests sur détecteurs | On testait la mauvaise chose |

---

## 7. Ce qu'on garde/crée

| Fonctionnalité | Usage |
|----------------|-------|
| Classification PCG | Identifier la nature des comptes |
| Détection ABT | Repérer les comptes 488 qui soldent |
| Calcul tableau de passage | LE livrable |
| NLP léger | Extraire "prud'hommes", "CFE", "IS" des libellés |
| Alertes contextuelles | 3-5 vraies alertes utiles |

---

## 8. Utilisateurs cibles (inchangé)

| Rôle | Besoin |
|------|--------|
| **DAF** | "Mon vrai résultat en 30 secondes" |
| **Contrôleur de gestion** | "Automatiser mes retraitements mensuels" |
| **Analyste M&A** | "Run rate fiable pour valorisation" |

---

## 9. Critères de succès v2

| Métrique | Cible |
|----------|-------|
| Temps lecture rapport | < 30 secondes |
| Fausses alertes | < 3 par analyse |
| Écart brut/normalisé calculé | Toujours affiché |
| Tableau de passage fourni | 100% des analyses |
| Prise en main sans formation | Oui |

---

## 10. Ce qui change vs v1

| Aspect | v1 | v2 |
|--------|----|----|
| **Philosophie** | Détecteur d'anomalies | Calculateur de run rate |
| **Fondation** | IA + statistiques | Bon sens comptable |
| **Livrable** | Liste d'anomalies | Tableau de passage |
| **Alertes** | Génériques (montants ronds) | Contextuelles (prud'hommes non budgété) |
| **Complexité** | 78 tests, 13 classes, 5 algos IA | ~20 tests, 4 couches simples |
| **Résultat** | "Score risque 81%" | "Run rate 861K, résultat 917K" |

---

## 11. Contraintes (inchangé)

- Budget : 0€ (open source)
- Tech : Python, priorité au simple
- Prérequis : Comptabilité mensuelle

---

## 12. Prochaines étapes BMAD

1. **PRD v2** : Exigences fonctionnelles alignées sur cette vision
2. **Architecture v2** : 4 couches, modules simplifiés
3. **Stories v2** : Implémentation incrémentale

---

*Document généré par BMAD Method v6 - Phase 1 Discovery (refonte)*
