# Product Requirements Document (PRD)
# GL Normalizer (ExamineMyData)

**Date:** 2026-02-03
**Version:** 1.0
**Project:** ExamineMyData
**Type:** Web Application
**Level:** 2 (Medium feature set)
**Status:** Draft
**Product Brief:** [docs/product-brief-examinedata-2026-02-02.md](./product-brief-examinedata-2026-02-02.md)

---

## 1. Executive Summary

**GL Normalizer** est un outil Python open source d'analyse du Grand Livre (GL) qui recalcule le **vrai run rate opérationnel** en identifiant et qualifiant les provisions, irrégularités de charges, et oublis des mois passés.

### Business Objectives

- Démocratiser l'analyse de run rate (open source)
- Automatiser le travail manuel des contrôleurs de gestion
- Fournir une vision lissée du P&L, sans bruit comptable

### Success Metrics

| Métrique | Cible |
|----------|-------|
| Précision détection | 100% (zéro faux négatif) |
| Faux positifs | Tendant vers 0% |
| Temps d'analyse | < 10 minutes |
| Utilisabilité | DAF sans formation |

---

## 2. User Personas

### Persona 1: DAF (Directeur Administratif et Financier)

| Attribut | Valeur |
|----------|--------|
| **Rôle** | Pilotage financier stratégique |
| **Usage** | Vision run rate mensuelle/annuelle |
| **Tech level** | Moyen (Excel expert, Python novice) |
| **Pain points** | P&L bruité, comparaisons impossibles |
| **Besoin** | Résultat clair, rapide, fiable |

### Persona 2: Contrôleur de Gestion

| Attribut | Valeur |
|----------|--------|
| **Rôle** | Analyse mensuelle détaillée |
| **Usage** | Retraitements, explications des écarts |
| **Tech level** | Bon (Excel avancé, scripts basiques) |
| **Pain points** | Travail manuel répétitif |
| **Besoin** | Automatisation, gain de temps |

### Persona 3: Analyste M&A / Auditeur

| Attribut | Valeur |
|----------|--------|
| **Rôle** | Due diligence, audit ponctuel |
| **Usage** | Analyse one-shot sur dossiers |
| **Tech level** | Variable |
| **Pain points** | Manque de temps, données hétérogènes |
| **Besoin** | Détection rapide des anomalies |

---

## 3. Functional Requirements (FRs)

### 3.1 Import & Parsing GL

#### FR-001: Chargement Excel
**Priority:** Must Have

**Description:**
L'utilisateur peut charger un export GL au format Excel (.xlsx, .xls).

**Acceptance Criteria:**
- [ ] Supporte fichiers .xlsx et .xls
- [ ] Gère fichiers jusqu'à 100k lignes
- [ ] Affiche message d'erreur si format invalide
- [ ] Temps de chargement < 30 secondes pour 50k lignes

---

#### FR-002: Détection automatique du format
**Priority:** Should Have

**Description:**
Le système détecte automatiquement le format du GL (Sage, Cegid, Quadratus, EBP) et mappe les colonnes.

**Acceptance Criteria:**
- [ ] Détecte Sage, Cegid, Quadratus, EBP
- [ ] Affiche le format détecté à l'utilisateur
- [ ] Propose confirmation avant traitement
- [ ] Fallback sur mapping manuel si non reconnu

**Dependencies:** FR-001

---

#### FR-003: Mapping manuel des colonnes
**Priority:** Must Have

**Description:**
Si le format n'est pas reconnu, l'utilisateur peut mapper manuellement les colonnes requises.

**Acceptance Criteria:**
- [ ] Interface de mapping colonnes (compte, date, montant, libellé, journal)
- [ ] Validation des colonnes obligatoires
- [ ] Sauvegarde du mapping pour réutilisation
- [ ] Message d'erreur si colonnes manquantes

**Dependencies:** FR-001

---

### 3.2 Moteur de Détection

#### FR-004: Détection concentrations mensuelles
**Priority:** Must Have

**Description:**
Le système détecte les comptes avec concentration anormale sur un mois (>50% du total annuel).

**Acceptance Criteria:**
- [ ] Calcule % mensuel par compte
- [ ] Flagge si un mois > 50% du total
- [ ] Identifie particulièrement décembre
- [ ] Affiche le détail de la concentration

---

#### FR-005: Calcul Z-score
**Priority:** Must Have

**Description:**
Le système calcule le Z-score par compte/mois pour identifier les outliers statistiques.

**Acceptance Criteria:**
- [ ] Z-score calculé pour chaque compte/mois
- [ ] Seuil configurable (défaut: |Z| > 2)
- [ ] Liste des outliers triée par Z-score
- [ ] Explication du calcul accessible

---

#### FR-006: Identification des provisions
**Priority:** Must Have

**Description:**
Le système identifie les écritures de provisions (dotations, reprises) via mots-clés et patterns.

**Acceptance Criteria:**
- [ ] Détecte mots-clés: "provision", "dotation", "reprise"
- [ ] Identifie comptes de classe 68x, 78x
- [ ] Flagge les journaux OD avec provisions
- [ ] Calcule le solde net provisions

---

#### FR-007: Détection montants ronds
**Priority:** Should Have

**Description:**
Le système flagge les montants ronds suspects (multiples de 1000€, 10000€).

**Acceptance Criteria:**
- [ ] Détecte multiples de 1000€ et 10000€
- [ ] Croise avec journal OD et libellé provision
- [ ] Score de suspicion combiné
- [ ] Seuil configurable

---

#### FR-008: Analyse journaux OD/situation
**Priority:** Should Have

**Description:**
Le système analyse les journaux OD et de situation pour détecter les régularisations.

**Acceptance Criteria:**
- [ ] Identifie journaux OD par code
- [ ] Calcule % d'écritures en décembre par journal
- [ ] Flagge journaux avec >50% en décembre
- [ ] Liste les écritures de régularisation

---

### 3.3 Workflow Qualification

#### FR-009: Questions qualificatives
**Priority:** Must Have

**Description:**
Le système présente max 10 questions qualificatives pour les anomalies les plus significatives.

**Acceptance Criteria:**
- [ ] Sélectionne top 10 anomalies par impact
- [ ] Question claire avec contexte (compte, montant, période)
- [ ] Réponses possibles: Justifié / Non justifié / À investiguer
- [ ] Possibilité de skip une question

---

#### FR-010: Justification et commentaires
**Priority:** Must Have

**Description:**
L'utilisateur peut ajouter un commentaire de justification pour chaque anomalie.

**Acceptance Criteria:**
- [ ] Champ texte libre pour commentaire
- [ ] Commentaire optionnel mais encouragé
- [ ] Affichage du commentaire dans le rapport
- [ ] Pas de limite de caractères

---

#### FR-011: Sauvegarde des justifications
**Priority:** Must Have

**Description:**
Les justifications sont sauvegardées pour traçabilité et réutilisation.

**Acceptance Criteria:**
- [ ] Sauvegarde dans fichier JSON/YAML
- [ ] Horodatage de chaque justification
- [ ] Rechargement possible lors d'une nouvelle analyse
- [ ] Export possible des justifications

---

### 3.4 Calcul Run Rate

#### FR-012: Calcul run rate mensuel
**Priority:** Must Have

**Description:**
Le système calcule le run rate mensuel par redistribution des charges sur 12 mois.

**Acceptance Criteria:**
- [ ] Run rate = Total annuel / 12
- [ ] Calcul par compte et global
- [ ] Comparaison avec P&L brut mensuel
- [ ] Affichage de l'écart run rate vs brut

---

#### FR-013: Neutralisation par dispatch
**Priority:** Must Have

**Description:**
Les anomalies qualifiées sont neutralisées par dispatch sur la période concernée.

**Acceptance Criteria:**
- [ ] Redistribution proportionnelle sur 12 mois
- [ ] Option: dispatch sur période spécifique
- [ ] Recalcul du run rate après neutralisation
- [ ] Traçabilité des neutralisations

**Dependencies:** FR-009, FR-010

---

### 3.5 Génération Rapport

#### FR-014: Rapport Excel
**Priority:** Must Have

**Description:**
Le système génère un rapport Excel avec les anomalies scorées et qualifiées.

**Acceptance Criteria:**
- [ ] Onglet "Anomalies" avec score, statut, commentaire
- [ ] Onglet "Run Rate" avec comparatif mensuel
- [ ] Onglet "Détail" avec toutes les écritures flaggées
- [ ] Mise en forme conditionnelle (rouge/orange/vert)

---

#### FR-015: Comparatif Run Rate vs Brut
**Priority:** Must Have

**Description:**
Le rapport affiche clairement le run rate dépollué vs le P&L brut.

**Acceptance Criteria:**
- [ ] Tableau comparatif mois par mois
- [ ] Graphique de tendance (si Excel le supporte)
- [ ] Écart en valeur absolue et %
- [ ] Synthèse annuelle

**Dependencies:** FR-012, FR-014

---

### 3.6 Module IA (Optionnel)

#### FR-016: Loi de Benford
**Priority:** Could Have

**Description:**
Appliquer la loi de Benford pour détecter les montants potentiellement fabriqués.

**Acceptance Criteria:**
- [ ] Analyse distribution premier chiffre
- [ ] Comparaison avec distribution théorique
- [ ] Score d'anomalie Benford
- [ ] Visualisation de la distribution

---

#### FR-017: Isolation Forest
**Priority:** Could Have

**Description:**
Utiliser Isolation Forest pour détection d'anomalies non supervisée.

**Acceptance Criteria:**
- [ ] Entraînement sur les features numériques
- [ ] Score d'anomalie par écriture
- [ ] Seuil configurable
- [ ] Explication des features contributives

---

#### FR-018: Analyse NLP libellés
**Priority:** Could Have

**Description:**
Analyser les libellés par NLP pour détecter patterns suspects.

**Acceptance Criteria:**
- [ ] Tokenization des libellés
- [ ] Détection mots-clés suspects
- [ ] Clustering de libellés similaires
- [ ] Score de suspicion NLP

---

## 4. Non-Functional Requirements (NFRs)

### 4.1 Performance

#### NFR-001: Temps d'analyse
**Priority:** Must Have

**Description:**
Analyse complète d'un GL (50k lignes) en moins de 10 minutes.

**Acceptance Criteria:**
- [ ] Benchmark sur fichier 50k lignes < 10 min
- [ ] Progression affichée pendant l'analyse
- [ ] Pas de freeze de l'interface

---

#### NFR-002: Temps de chargement
**Priority:** Should Have

**Description:**
Chargement d'un fichier Excel en moins de 30 secondes.

**Acceptance Criteria:**
- [ ] Fichier 50k lignes < 30 sec
- [ ] Indicateur de progression

---

### 4.2 Usability

#### NFR-003: Utilisabilité DAF
**Priority:** Must Have

**Description:**
Un DAF peut utiliser l'outil sans formation technique.

**Acceptance Criteria:**
- [ ] Documentation utilisateur claire
- [ ] Messages en français
- [ ] Workflow guidé étape par étape
- [ ] Pas de ligne de commande complexe

---

#### NFR-004: Messages d'erreur
**Priority:** Must Have

**Description:**
Messages d'erreur clairs et actionnables en français.

**Acceptance Criteria:**
- [ ] Erreurs en français
- [ ] Suggestion de correction
- [ ] Pas de stack trace technique

---

### 4.3 Reliability

#### NFR-005: Zéro faux négatif
**Priority:** Must Have

**Description:**
100% des vraies anomalies doivent être détectées.

**Acceptance Criteria:**
- [ ] Tests sur jeux de données avec anomalies connues
- [ ] Recall = 100% sur tests
- [ ] Revue manuelle des cas limites

---

#### NFR-006: Faux positifs minimaux
**Priority:** Must Have

**Description:**
Taux de faux positifs tendant vers 0%.

**Acceptance Criteria:**
- [ ] Precision mesurée sur tests
- [ ] Amélioration continue des seuils
- [ ] Feedback utilisateur intégré

---

### 4.4 Maintainability

#### NFR-007: Code quality
**Priority:** Should Have

**Description:**
Code Python documenté et PEP8 compliant.

**Acceptance Criteria:**
- [ ] Docstrings pour fonctions publiques
- [ ] Linting PEP8 (flake8/black)
- [ ] Type hints

---

#### NFR-008: Tests unitaires
**Priority:** Should Have

**Description:**
Tests unitaires couvrant les fonctions critiques.

**Acceptance Criteria:**
- [ ] Coverage > 70% sur fonctions critiques
- [ ] CI/CD avec tests automatiques
- [ ] Tests de non-régression

---

### 4.5 Compatibility

#### NFR-009: Version Python
**Priority:** Must Have

**Description:**
Compatible Python 3.9+.

**Acceptance Criteria:**
- [ ] Tests sur Python 3.9, 3.10, 3.11, 3.12
- [ ] Requirements.txt à jour

---

#### NFR-010: Multi-plateforme
**Priority:** Should Have

**Description:**
Fonctionne sur Windows, Mac, Linux.

**Acceptance Criteria:**
- [ ] Tests sur les 3 OS
- [ ] Documentation d'installation par OS

---

## 5. Epics

### EPIC-001: Import & Parsing GL

**Description:**
Permettre le chargement et le parsing de fichiers GL multi-formats.

**Functional Requirements:**
- FR-001: Chargement Excel
- FR-002: Détection automatique format
- FR-003: Mapping manuel colonnes

**Story Count Estimate:** 3-5 stories

**Priority:** Must Have

**Business Value:**
Fondation technique - sans import, pas d'analyse possible.

---

### EPIC-002: Moteur de Détection

**Description:**
Détecter automatiquement les anomalies et provisions suspectes.

**Functional Requirements:**
- FR-004: Détection concentrations mensuelles
- FR-005: Calcul Z-score
- FR-006: Identification provisions
- FR-007: Détection montants ronds
- FR-008: Analyse journaux OD

**Story Count Estimate:** 5-7 stories

**Priority:** Must Have

**Business Value:**
Coeur de la valeur ajoutée - automatisation de la détection.

---

### EPIC-003: Workflow Qualification

**Description:**
Permettre à l'utilisateur de qualifier et justifier les anomalies détectées.

**Functional Requirements:**
- FR-009: Questions qualificatives (max 10)
- FR-010: Justification et commentaires
- FR-011: Sauvegarde des justifications

**Story Count Estimate:** 3-4 stories

**Priority:** Must Have

**Business Value:**
Différenciation clé - qualification humaine + traçabilité.

---

### EPIC-004: Calcul Run Rate

**Description:**
Calculer le run rate réel par neutralisation des anomalies.

**Functional Requirements:**
- FR-012: Calcul run rate mensuel
- FR-013: Neutralisation par dispatch

**Story Count Estimate:** 2-3 stories

**Priority:** Must Have

**Business Value:**
Objectif final - le run rate dépollué.

---

### EPIC-005: Génération Rapport

**Description:**
Produire un rapport Excel exploitable.

**Functional Requirements:**
- FR-014: Rapport Excel
- FR-015: Comparatif Run Rate vs Brut

**Story Count Estimate:** 2-3 stories

**Priority:** Must Have

**Business Value:**
Livrable final - ce que le DAF utilise.

---

### EPIC-006: Module IA (Optionnel)

**Description:**
Enrichir la détection avec des techniques IA avancées.

**Functional Requirements:**
- FR-016: Loi de Benford
- FR-017: Isolation Forest
- FR-018: Analyse NLP libellés

**Story Count Estimate:** 3-5 stories

**Priority:** Could Have

**Business Value:**
Valeur ajoutée différenciante - détection avancée.

---

## 6. Traceability Matrix

| Epic | FRs | NFRs liés | Stories | Priority |
|------|-----|-----------|---------|----------|
| EPIC-001 | FR-001, FR-002, FR-003 | NFR-002, NFR-009, NFR-010 | 3-5 | Must |
| EPIC-002 | FR-004, FR-005, FR-006, FR-007, FR-008 | NFR-001, NFR-005, NFR-006 | 5-7 | Must |
| EPIC-003 | FR-009, FR-010, FR-011 | NFR-003, NFR-004 | 3-4 | Must |
| EPIC-004 | FR-012, FR-013 | NFR-001, NFR-005 | 2-3 | Must |
| EPIC-005 | FR-014, FR-015 | NFR-003 | 2-3 | Must |
| EPIC-006 | FR-016, FR-017, FR-018 | NFR-001, NFR-007 | 3-5 | Could |

**Total estimé:** 18-27 stories

---

## 7. Prioritization Summary

### Functional Requirements

| Priority | Count | FRs |
|----------|-------|-----|
| **Must Have** | 10 | FR-001, FR-003, FR-004, FR-005, FR-006, FR-009, FR-010, FR-011, FR-012, FR-013, FR-014, FR-015 |
| **Should Have** | 4 | FR-002, FR-007, FR-008 |
| **Could Have** | 3 | FR-016, FR-017, FR-018 |

### Non-Functional Requirements

| Priority | Count | NFRs |
|----------|-------|------|
| **Must Have** | 6 | NFR-001, NFR-003, NFR-004, NFR-005, NFR-006, NFR-009 |
| **Should Have** | 4 | NFR-002, NFR-007, NFR-008, NFR-010 |

### Epics

| Priority | Count | Epics |
|----------|-------|-------|
| **Must Have** | 5 | EPIC-001 à EPIC-005 |
| **Could Have** | 1 | EPIC-006 |

---

## 8. Key User Flows

### Flow 1: Analyse standard

```
1. Charger fichier GL Excel
   ↓
2. Confirmation format détecté (ou mapping manuel)
   ↓
3. Lancement analyse automatique
   ↓
4. Réponse aux questions qualificatives (max 10)
   ↓
5. Génération rapport Excel
   ↓
6. Consultation run rate vs P&L brut
```

### Flow 2: Ré-analyse avec justifications

```
1. Charger fichier GL Excel
   ↓
2. Charger justifications précédentes
   ↓
3. Analyse avec anomalies déjà qualifiées
   ↓
4. Qualifier uniquement les nouvelles anomalies
   ↓
5. Mise à jour rapport
```

---

## 9. Dependencies

### Internal Dependencies

- Python 3.9+
- pandas, openpyxl pour Excel
- scikit-learn pour IA (optionnel)
- numpy, scipy pour statistiques

### External Dependencies

- Aucune API externe
- Aucune base de données
- Fichiers locaux uniquement

---

## 10. Assumptions

1. Les utilisateurs ont une **comptabilité mensuelle**
2. Les exports GL sont au **format standard** (ou mappable)
3. Les utilisateurs savent **lire un fichier Excel**
4. Les fichiers GL contiennent les colonnes minimales (compte, date, montant, libellé)
5. L'analyse porte sur une **année fiscale complète**

---

## 11. Out of Scope (v1)

- Interface web / UI graphique
- Connexion directe aux ERP
- Multi-utilisateurs / collaboration
- API REST
- Base de données persistante
- Analyse multi-années automatique

---

## 12. Open Questions

1. **Format de sauvegarde des justifications** : JSON ou YAML ?
2. **Seuils par défaut** : Quelles valeurs initiales pour Z-score, concentration, etc. ?
3. **Comparaison N/N-1** : Inclure dans v1 ou reporter à v2 ?

---

## 13. Stakeholders

| Stakeholder | Influence | Intérêt |
|-------------|-----------|---------|
| **Créateur/Mainteneur** | High | Vision, développement, décisions |
| **Communauté comptable/finance** | Medium | Utilisateurs finaux, feedback |

---

## 14. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-03 | BMAD PM | Initial PRD |

---

*Document généré par BMAD Method v6 - Phase 2 Requirements*
