# Product Brief - GL Normalizer (ExamineMyData)

**Date:** 2026-02-02
**Project:** ExamineMyData
**Type:** Web Application
**Level:** 2 (Medium feature set)
**Status:** Draft

---

## 1. Executive Summary

**GL Normalizer** est un outil d'analyse du Grand Livre (GL) qui recalcule le **vrai run rate opérationnel** en identifiant et qualifiant les provisions, irrégularités de charges, et oublis des mois passés.

L'objectif : fournir une vision lissée du résultat opérationnel, débarrassée du "bruit" mensuel (écritures de régularisation, provisions concentrées, rattrapages).

**Cible :** DAF, contrôleurs de gestion, analystes M&A, auditeurs.

---

## 2. Problem Statement

### Le problème

Les P&L mensuels sont **pollués** par des écritures comptables qui ne reflètent pas la réalité opérationnelle :
- Provisions concentrées en fin d'année
- Rattrapages et oublis des mois passés
- Écritures de régularisation dans tous les sens

**Exemple concret :** Comparer décembre 2024 vs décembre 2025 est quasi impossible - les deux mois sont "archis pollués" par des écritures de régularisation.

### Situation actuelle

Les utilisateurs font face au problème de 3 façons :
1. **Excel manuel** - Retraitements fastidieux
2. **Retraitements à la main** - Chronophage et source d'erreurs
3. **Ignorent le problème** - Décisions basées sur des données faussées

### Impact si non résolu

- **Mauvaises décisions de gestion** basées sur des P&L bruités
- **Temps perdu** en analyse manuelle et retraitements

---

## 3. Target Audience

### Utilisateurs principaux

| Rôle | Usage |
|------|-------|
| **DAF** | Pilotage financier, vision run rate |
| **Contrôleur de gestion** | Analyse mensuelle (objectif : automatiser/remplacer une partie de leur travail) |

### Utilisateurs secondaires

| Rôle | Usage |
|------|-------|
| **Analystes M&A** | Due diligence, valorisation |
| **Auditeurs** | Contrôle ponctuel |

### Besoins clés adressés

1. Identification automatique des comportements non prévisibles
2. Détection des écritures de régularisation
3. Vision run rate lissée sans retraitement manuel

---

## 4. Solution Overview

### Proposition de valeur

Outil Python qui analyse automatiquement les exports GL pour :
- Détecter les anomalies et provisions suspectes
- Qualifier les écritures via un workflow de questions (max 10)
- Calculer le run rate réel par neutralisation et dispatch sur période

### Fonctionnalités core

- **Import GL multi-formats** : Sage, Cegid, Quadratus, EBP, Excel générique
- **Détection anomalies statistiques** : Z-scores, concentrations mensuelles, patterns
- **Analyse provisions** : Dotations, reprises, montants ronds, journaux OD
- **Module IA** (optionnel) : Benford, Isolation Forest, NLP libellés, XGBoost
- **Workflow qualification** : Max 10 questions avec détail pour chaque anomalie
- **Rapport Excel** : Anomalies scorées, run rate recalculé
- **Justification via commentaires** : Traçabilité des raisons de qualification

### Workflow utilisateur

```
1. IMPORT
   └── Charger export GL (multi-formats supportés)

2. DÉTECTION
   └── Anomalies identifiées automatiquement

3. QUALIFICATION
   └── Répondre aux questions (max 10) avec détail
       - "Cette provision est-elle justifiée ?"
       - "Ce rattrapage est-il récurrent ?"

4. RÉSULTAT
   └── Run rate dépollué + rapport Excel
```

---

## 5. Business Objectives

### Objectif

Projet **open source / communautaire** visant à démocratiser l'analyse de run rate.

### Métriques de succès

| Métrique | Cible |
|----------|-------|
| Précision des détections | 100% (zéro faux négatif) |
| Nombre d'utilisateurs | Croissance organique |
| Contributeurs GitHub | > 0 |

### Valeur business

- **Gain de temps** : Automatisation vs analyse manuelle
- **Réduction d'erreurs** : Détection systématique vs oublis humains

---

## 6. Scope

### IN SCOPE (v1)

- Import GL multi-formats (Sage, Cegid, Quadratus, EBP, Excel)
- Détection anomalies statistiques
- Analyse provisions
- Module IA (optionnel)
- Rapport Excel
- Workflow de questions qualificatives (max 10)
- Justification via commentaires (traçabilité)

### OUT OF SCOPE (v1)

- Interface web / UI graphique
- Connexion directe aux ERP
- Multi-utilisateurs / collaboration
- API REST

### FUTUR (v2+)

- Analyse explicative (pourquoi cette anomalie ?)

---

## 7. Stakeholders

| Stakeholder | Influence | Intérêt |
|-------------|-----------|---------|
| **Créateur/Mainteneur** | High | Vision, développement, décisions |
| **Communauté comptable/finance** | Medium | Utilisateurs finaux, feedback |

---

## 8. Constraints & Assumptions

### Contraintes

- **Budget** : 0€ (projet open source)
- **Temps** : Développement sur temps libre
- **Tech** : Python, IA-assisted (vibecoding), priorité à la logique

### Hypothèses

- Les utilisateurs ont une **comptabilité mensuelle**
- Les exports GL sont au **format standard** (ou mappable)
- Les utilisateurs savent **lire un fichier Excel**

---

## 9. Success Criteria

| Critère | Mesure |
|---------|--------|
| Détection exhaustive | 100% des anomalies réelles détectées |
| Accessibilité | Un DAF peut utiliser l'outil sans formation |
| Performance | Analyse complète en moins de 10 minutes |
| Communauté | Contributeurs externes sur le repo GitHub |

---

## 10. Timeline

| Jalon | Date cible |
|-------|------------|
| **MVP fonctionnel** | Q1 2026 |

---

## 11. Risks

| Risque | Probabilité | Impact | Mitigation |
|--------|-------------|--------|------------|
| **Faux positifs** - Trop d'alertes = image "usine à gaz" | Medium | High | Seuils ajustables, qualification utilisateur |
| **Formats GL** - Pas assez adaptatif | Medium | Medium | Architecture de mapping extensible |
| **Module IA** - Non pertinent ou trop coûteux | Medium | Medium | IA optionnelle, approche statistique d'abord |

---

## 12. Appendix

### Formats GL supportés

| Format | Statut |
|--------|--------|
| Sage | Supporté |
| Cegid | Supporté |
| Quadratus | Supporté |
| EBP | Supporté |
| Excel générique | Supporté (mapping auto) |

### Techniques IA prévues

| Technique | Usage |
|-----------|-------|
| Loi de Benford | Détecter les montants fabriqués |
| Isolation Forest | Anomalies non supervisées |
| Autoencoder | Patterns complexes |
| NLP | Libellés suspects |
| XGBoost | Classification à risque |

---

*Document généré par BMAD Method v6 - Phase 1 Discovery*
