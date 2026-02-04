# Sprint Plan: GL Normalizer

**Date:** 2026-02-03 (Updated: 2026-02-03)
**Project:** ExamineMyData (GL Normalizer)
**Level:** 2 (Medium feature set)
**Total Stories:** 33 (original 22 + 8 enhancement + 3 new UX)
**Total Points:** 110
**Planned Sprints:** 7
**Target Completion:** Q1 2026

---

## Executive Summary

Plan d'implémentation de GL Normalizer en **3 sprints de 2 semaines** (~6 semaines total).

- **Sprint 1** : Fondations (Import, Contexte PCG, Détection base)
- **Sprint 2** : MVP complet (Détection avancée, Qualification, Run Rate, Rapport)
- **Sprint 3** : Module IA optionnel + Polish

**Key Metrics:**

| Métrique | Valeur |
|----------|--------|
| Total Stories | 22 |
| Total Points | 78 |
| Sprints | 3 |
| Team | 1 dev + IA (vibecoding) |
| Capacité/Sprint | ~30-35 points |
| MVP | Fin Sprint 2 |

---

## Team Capacity

| Paramètre | Valeur |
|-----------|--------|
| Développeurs | 1 + IA assistance |
| Sprint length | 2 semaines |
| Heures productives/jour | 5h |
| Total heures/sprint | 50h |
| Vélocité estimée | 30-35 points/sprint |

---

## Story Inventory

### STORY-000: Setup projet

**Epic:** Infrastructure
**Priority:** Must Have
**Points:** 3

**User Story:**
En tant que développeur,
Je veux un projet Python structuré avec CI/CD,
Afin de commencer le développement sur des bases solides.

**Acceptance Criteria:**
- [ ] Structure de projet créée (gl_normalizer/)
- [ ] pyproject.toml configuré
- [ ] requirements.txt avec dépendances
- [ ] GitHub Actions pour tests
- [ ] README avec instructions d'installation
- [ ] .gitignore configuré

**Technical Notes:**
- Structure selon architecture doc
- pytest configuré
- black + flake8 configurés

---

### STORY-001: Charger fichier Excel

**Epic:** EPIC-001 Import & Parsing GL
**Priority:** Must Have
**Points:** 3
**FR:** FR-001

**User Story:**
En tant que DAF,
Je veux charger un export GL au format Excel,
Afin de commencer l'analyse de mes données.

**Acceptance Criteria:**
- [ ] Supporte .xlsx et .xls
- [ ] Gère fichiers jusqu'à 100k lignes
- [ ] Message d'erreur clair si fichier invalide
- [ ] Chargement < 30 secondes pour 50k lignes
- [ ] Retourne un DataFrame pandas

**Technical Notes:**
- Utiliser openpyxl pour .xlsx
- xlrd pour .xls (si nécessaire)
- read_only mode pour performance

**Dependencies:** STORY-000

---

### STORY-002: Détecter format automatiquement

**Epic:** EPIC-001 Import & Parsing GL
**Priority:** Should Have
**Points:** 5
**FR:** FR-002

**User Story:**
En tant que DAF,
Je veux que l'outil détecte automatiquement le format de mon GL,
Afin de ne pas avoir à configurer manuellement.

**Acceptance Criteria:**
- [ ] Détecte Sage, Cegid, Quadratus, EBP
- [ ] Analyse les en-têtes de colonnes
- [ ] Affiche le format détecté
- [ ] Propose confirmation à l'utilisateur
- [ ] Fallback sur mapping manuel si non reconnu

**Technical Notes:**
- Patterns de colonnes par format dans formats_mapping.yaml
- Score de confiance pour la détection

**Dependencies:** STORY-001

---

### STORY-003: Mapping manuel des colonnes

**Epic:** EPIC-001 Import & Parsing GL
**Priority:** Must Have
**Points:** 3
**FR:** FR-003

**User Story:**
En tant que DAF avec un format GL non standard,
Je veux mapper manuellement les colonnes,
Afin d'utiliser l'outil malgré un format non reconnu.

**Acceptance Criteria:**
- [ ] Interface CLI pour mapper: compte, date, montant, libellé, journal
- [ ] Validation des colonnes obligatoires
- [ ] Sauvegarde du mapping pour réutilisation
- [ ] Message d'erreur si colonnes manquantes

**Technical Notes:**
- Sauvegarder mapping dans config YAML
- Proposer colonnes candidates

**Dependencies:** STORY-001

---

### STORY-004: Détecter concentrations mensuelles

**Epic:** EPIC-002 Moteur de Détection
**Priority:** Must Have
**Points:** 3
**FR:** FR-004

**User Story:**
En tant que DAF,
Je veux identifier les comptes avec concentration anormale sur un mois,
Afin de repérer les provisions concentrées.

**Acceptance Criteria:**
- [ ] Calcule % mensuel par compte
- [ ] Flagge si un mois > 50% du total annuel
- [ ] Identifie particulièrement décembre
- [ ] Retourne liste d'anomalies avec détails

**Technical Notes:**
- Seuil configurable (défaut: 50%)
- Groupby compte + mois

**Dependencies:** STORY-001

---

### STORY-005: Calculer Z-scores

**Epic:** EPIC-002 Moteur de Détection
**Priority:** Must Have
**Points:** 3
**FR:** FR-005

**User Story:**
En tant que DAF,
Je veux identifier les mois statistiquement anormaux par compte,
Afin de repérer les outliers.

**Acceptance Criteria:**
- [ ] Z-score calculé pour chaque compte/mois
- [ ] Seuil configurable (défaut: |Z| > 2)
- [ ] Liste des outliers triée par Z-score
- [ ] Gère les comptes avec peu d'écritures

**Technical Notes:**
- scipy.stats.zscore ou calcul manuel
- Exclure comptes avec < 3 mois d'activité

**Dependencies:** STORY-001

---

### STORY-006: Identifier provisions

**Epic:** EPIC-002 Moteur de Détection
**Priority:** Must Have
**Points:** 5
**FR:** FR-006

**User Story:**
En tant que DAF,
Je veux identifier automatiquement les écritures de provisions,
Afin de les analyser spécifiquement.

**Acceptance Criteria:**
- [ ] Détecte mots-clés: "provision", "dotation", "reprise"
- [ ] Identifie comptes classe 68x, 78x
- [ ] Flagge journaux OD avec provisions
- [ ] Calcule solde net provisions par compte

**Technical Notes:**
- Regex sur libellés
- Classification par compte PCG
- Utiliser AccountingContext

**Dependencies:** STORY-001, STORY-009

---

### STORY-007: Détecter montants ronds

**Epic:** EPIC-002 Moteur de Détection
**Priority:** Should Have
**Points:** 2
**FR:** FR-007

**User Story:**
En tant que DAF,
Je veux repérer les montants ronds suspects,
Afin d'identifier des écritures potentiellement fabriquées.

**Acceptance Criteria:**
- [ ] Détecte multiples de 1000€ et 10000€
- [ ] Croise avec journal OD
- [ ] Score de suspicion combiné
- [ ] Seuil configurable

**Technical Notes:**
- Modulo pour détection
- Pondérer avec autres critères

**Dependencies:** STORY-001

---

### STORY-008: Analyser journaux OD

**Epic:** EPIC-002 Moteur de Détection
**Priority:** Should Have
**Points:** 3
**FR:** FR-008

**User Story:**
En tant que DAF,
Je veux analyser les journaux OD/situation,
Afin de repérer les régularisations.

**Acceptance Criteria:**
- [ ] Identifie journaux OD par code
- [ ] Calcule % d'écritures en décembre par journal
- [ ] Flagge journaux avec >50% en décembre
- [ ] Liste les écritures de régularisation

**Technical Notes:**
- Codes OD courants: OD, AN, RAN, SIT
- Configurable via YAML

**Dependencies:** STORY-001

---

### STORY-009: Implémenter AccountingContext (PCG)

**Epic:** EPIC-002b Contexte & Profiling
**Priority:** Must Have
**Points:** 5
**FR:** Nouveau

**User Story:**
En tant que DAF,
Je veux que l'outil connaisse le PCG,
Afin de contextualiser les anomalies selon le référentiel comptable.

**Acceptance Criteria:**
- [ ] Charger PCG français (comptes, libellés, classes)
- [ ] Classifier un compte (classe, nature, type)
- [ ] Définir comportement attendu par compte
- [ ] Valider compte contre PCG
- [ ] Supporter plan de compte personnalisé (optionnel)

**Technical Notes:**
- PCG en YAML (data/pcg_2025.yaml)
- Comportements: mensuel, annuel, variable
- Comptes 68x = provisions annuelles

**Dependencies:** STORY-000

---

### STORY-010: Implémenter Profiler

**Epic:** EPIC-002b Contexte & Profiling
**Priority:** Must Have
**Points:** 5
**FR:** Nouveau

**User Story:**
En tant que DAF,
Je veux un profil statistique de mes données GL,
Afin de comprendre la structure de mes données.

**Acceptance Criteria:**
- [ ] Stats par colonne (type, null%, unique, distribution)
- [ ] Profil par compte (total, nb écritures, volatilité)
- [ ] Détection problèmes qualité données
- [ ] Baseline pour comparaison

**Technical Notes:**
- pandas describe() enrichi
- Calcul volatilité (std/mean)

**Dependencies:** STORY-001

---

### STORY-011: Contextualiser anomalies PCG

**Epic:** EPIC-002b Contexte & Profiling
**Priority:** Must Have
**Points:** 3
**FR:** Nouveau

**User Story:**
En tant que DAF,
Je veux que les anomalies soient contextualisées selon le PCG,
Afin de distinguer les vraies anomalies des comportements normaux.

**Acceptance Criteria:**
- [ ] Compare comportement observé vs attendu (PCG)
- [ ] Ajuste score si comportement attendu
- [ ] Enrichit anomalie avec contexte PCG
- [ ] Génère question suggérée

**Technical Notes:**
- Ex: compte 681 concentré en décembre = normal
- Réduire score si comportement attendu

**Dependencies:** STORY-009, STORY-004, STORY-005

---

### STORY-012: Questions qualificatives

**Epic:** EPIC-003 Workflow Qualification
**Priority:** Must Have
**Points:** 3
**FR:** FR-009

**User Story:**
En tant que DAF,
Je veux répondre à des questions pour qualifier les anomalies,
Afin de distinguer les vrais problèmes des faux positifs.

**Acceptance Criteria:**
- [ ] Sélectionne top 10 anomalies par impact
- [ ] Question avec contexte (compte, montant, PCG)
- [ ] Réponses: Justifié / Non justifié / À investiguer
- [ ] Possibilité de skip

**Technical Notes:**
- CLI interactive
- Afficher contexte PCG dans la question

**Dependencies:** STORY-011

---

### STORY-013: Commentaires et justifications

**Epic:** EPIC-003 Workflow Qualification
**Priority:** Must Have
**Points:** 2
**FR:** FR-010

**User Story:**
En tant que DAF,
Je veux ajouter un commentaire pour chaque anomalie qualifiée,
Afin de documenter mes décisions.

**Acceptance Criteria:**
- [ ] Champ texte libre pour commentaire
- [ ] Commentaire optionnel mais encouragé
- [ ] Affichage dans le rapport final
- [ ] Horodatage du commentaire

**Technical Notes:**
- input() en CLI
- Stocker avec anomalie

**Dependencies:** STORY-012

---

### STORY-014: Sauvegarde justifications YAML

**Epic:** EPIC-003 Workflow Qualification
**Priority:** Must Have
**Points:** 3
**FR:** FR-011

**User Story:**
En tant que DAF,
Je veux que mes justifications soient sauvegardées,
Afin de les réutiliser lors de la prochaine analyse.

**Acceptance Criteria:**
- [ ] Sauvegarde en YAML
- [ ] Horodatage de chaque justification
- [ ] Rechargement lors d'une nouvelle analyse
- [ ] Export possible

**Technical Notes:**
- PyYAML
- Fichier: justifications.yaml

**Dependencies:** STORY-013

---

### STORY-015: Calculer run rate mensuel

**Epic:** EPIC-004 Calcul Run Rate
**Priority:** Must Have
**Points:** 3
**FR:** FR-012

**User Story:**
En tant que DAF,
Je veux calculer le run rate mensuel de chaque compte,
Afin d'avoir une vision lissée.

**Acceptance Criteria:**
- [ ] Run rate = Total annuel / 12
- [ ] Calcul par compte et global
- [ ] Comparaison avec P&L brut mensuel
- [ ] Affichage de l'écart

**Technical Notes:**
- DataFrame avec colonnes mois + run_rate

**Dependencies:** STORY-001

---

### STORY-016: Neutralisation par dispatch

**Epic:** EPIC-004 Calcul Run Rate
**Priority:** Must Have
**Points:** 5
**FR:** FR-013

**User Story:**
En tant que DAF,
Je veux neutraliser les anomalies qualifiées,
Afin d'obtenir un run rate dépollué.

**Acceptance Criteria:**
- [ ] Redistribution proportionnelle sur 12 mois
- [ ] Option: dispatch sur période spécifique
- [ ] Recalcul run rate après neutralisation
- [ ] Traçabilité des neutralisations

**Technical Notes:**
- Créer colonne montant_ajusté
- Garder montant_brut pour comparaison

**Dependencies:** STORY-014, STORY-015

---

### STORY-017: Rapport Excel multi-onglets

**Epic:** EPIC-005 Génération Rapport
**Priority:** Must Have
**Points:** 5
**FR:** FR-014

**User Story:**
En tant que DAF,
Je veux un rapport Excel complet,
Afin d'analyser et partager les résultats.

**Acceptance Criteria:**
- [ ] Onglet "Anomalies" avec score, statut, commentaire
- [ ] Onglet "Run Rate" avec comparatif mensuel
- [ ] Onglet "Détail" avec écritures flaggées
- [ ] Mise en forme conditionnelle (rouge/orange/vert)

**Technical Notes:**
- openpyxl pour génération
- Styles et couleurs

**Dependencies:** STORY-016

---

### STORY-018: Comparatif Run Rate vs Brut

**Epic:** EPIC-005 Génération Rapport
**Priority:** Must Have
**Points:** 3
**FR:** FR-015

**User Story:**
En tant que DAF,
Je veux voir clairement l'écart entre run rate et P&L brut,
Afin de mesurer l'impact des anomalies.

**Acceptance Criteria:**
- [ ] Tableau comparatif mois par mois
- [ ] Écart en valeur absolue et %
- [ ] Synthèse annuelle
- [ ] Graphique si possible

**Technical Notes:**
- Dans onglet "Run Rate" du rapport

**Dependencies:** STORY-017

---

### STORY-019: Analyse Benford (IA)

**Epic:** EPIC-006 Module IA
**Priority:** Could Have
**Points:** 3
**FR:** FR-016

**User Story:**
En tant que DAF,
Je veux détecter les montants potentiellement fabriqués,
Afin d'identifier des fraudes potentielles.

**Acceptance Criteria:**
- [ ] Analyse distribution premier chiffre
- [ ] Comparaison avec distribution théorique Benford
- [ ] Score d'anomalie Benford
- [ ] Visualisation de la distribution

**Technical Notes:**
- scipy pour chi-square test
- Seuil de significativité

**Dependencies:** STORY-001

---

### STORY-020: Isolation Forest (IA)

**Epic:** EPIC-006 Module IA
**Priority:** Could Have
**Points:** 5
**FR:** FR-017

**User Story:**
En tant que DAF,
Je veux détecter des anomalies non supervisées,
Afin d'identifier des patterns suspects non prévus.

**Acceptance Criteria:**
- [ ] Entraînement sur features numériques
- [ ] Score d'anomalie par écriture
- [ ] Seuil configurable
- [ ] Top N anomalies

**Technical Notes:**
- scikit-learn IsolationForest
- Features: montant, mois, compte (encodé)

**Dependencies:** STORY-001

---

### STORY-021: Analyse NLP libellés (IA)

**Epic:** EPIC-006 Module IA
**Priority:** Could Have
**Points:** 5
**FR:** FR-018

**User Story:**
En tant que DAF,
Je veux analyser les libellés suspects,
Afin de détecter des patterns de fraude.

**Acceptance Criteria:**
- [ ] Tokenization des libellés
- [ ] Détection mots-clés suspects
- [ ] Clustering de libellés similaires
- [ ] Score de suspicion NLP

**Technical Notes:**
- spaCy ou regex avancé
- Liste de mots suspects configurable

**Dependencies:** STORY-001

---

## Sprint Allocation

### Sprint 1 (Semaines 1-2) - 32 points

**Goal:** Import GL fonctionnel + Contexte PCG + Détection statistique de base

| Story | Description | Points | Priority |
|-------|-------------|--------|----------|
| STORY-000 | Setup projet | 3 | Must |
| STORY-001 | Charger Excel | 3 | Must |
| STORY-002 | Détecter format | 5 | Should |
| STORY-003 | Mapping manuel | 3 | Must |
| STORY-009 | AccountingContext (PCG) | 5 | Must |
| STORY-010 | Profiler | 5 | Must |
| STORY-004 | Concentrations | 3 | Must |
| STORY-005 | Z-scores | 3 | Must |
| STORY-007 | Montants ronds | 2 | Should |

**Total:** 32 points / 35 capacity (91%)

**Deliverables Sprint 1:**
- Projet setup avec CI
- Import GL multi-format fonctionnel
- PCG chargé et utilisable
- Profil statistique des données
- Détection: concentrations, Z-scores, montants ronds

**Risks:**
- Formats GL non documentés → mitigation: commencer par format connu

---

### Sprint 2 (Semaines 3-4) - 30 points

**Goal:** Détection complète + Qualification + Run Rate + Rapport = **MVP**

| Story | Description | Points | Priority |
|-------|-------------|--------|----------|
| STORY-006 | Identifier provisions | 5 | Must |
| STORY-008 | Analyser journaux OD | 3 | Should |
| STORY-011 | Contextualiser anomalies | 3 | Must |
| STORY-012 | Questions qualificatives | 3 | Must |
| STORY-013 | Commentaires | 2 | Must |
| STORY-014 | Sauvegarde YAML | 3 | Must |
| STORY-015 | Calcul run rate | 3 | Must |
| STORY-016 | Neutralisation | 5 | Must |
| STORY-017 | Rapport Excel | 5 | Must |

**Total:** 32 points / 35 capacity (91%)

**Deliverables Sprint 2:**
- Détection provisions et journaux OD
- Contextualisation PCG des anomalies
- Workflow de qualification complet
- Calcul run rate avec neutralisation
- Rapport Excel multi-onglets
- **MVP FONCTIONNEL**

**Risks:**
- Workflow qualification trop complexe → mitigation: garder simple (CLI)

---

### Sprint 3 (Semaines 5-6) - 16 points

**Goal:** Module IA optionnel + Polish final

| Story | Description | Points | Priority |
|-------|-------------|--------|----------|
| STORY-018 | Comparatif Run Rate | 3 | Must |
| STORY-019 | Benford (IA) | 3 | Could |
| STORY-020 | Isolation Forest (IA) | 5 | Could |
| STORY-021 | NLP libellés (IA) | 5 | Could |

**Total:** 16 points / 35 capacity (46%)

**Deliverables Sprint 3:**
- Comparatif amélioré dans rapport
- Module IA Benford
- Module IA Isolation Forest
- Module IA NLP

**Notes:**
- Sprint plus léger pour polish et documentation
- Module IA optionnel (dépendances séparées)

---

## Epic Traceability

| Epic | Stories | Points | Sprint |
|------|---------|--------|--------|
| Infrastructure | STORY-000 | 3 | 1 |
| EPIC-001: Import | STORY-001, 002, 003 | 11 | 1 |
| EPIC-002: Détection | STORY-004, 005, 006, 007, 008 | 16 | 1-2 |
| EPIC-002b: Contexte | STORY-009, 010, 011 | 13 | 1-2 |
| EPIC-003: Qualification | STORY-012, 013, 014 | 8 | 2 |
| EPIC-004: Run Rate | STORY-015, 016 | 8 | 2 |
| EPIC-005: Rapport | STORY-017, 018 | 8 | 2-3 |
| EPIC-006: IA | STORY-019, 020, 021 | 13 | 3 |
| EPIC-007: UX Enhancement | STORY-031, 032, 033 | 18 | 7 |

---

## Requirements Coverage

| FR | Story | Sprint |
|----|-------|--------|
| FR-001 | STORY-001 | 1 |
| FR-002 | STORY-002 | 1 |
| FR-003 | STORY-003 | 1 |
| FR-004 | STORY-004 | 1 |
| FR-005 | STORY-005 | 1 |
| FR-006 | STORY-006 | 2 |
| FR-007 | STORY-007 | 1 |
| FR-008 | STORY-008 | 2 |
| FR-009 | STORY-012 | 2 |
| FR-010 | STORY-013 | 2 |
| FR-011 | STORY-014 | 2 |
| FR-012 | STORY-015 | 2 |
| FR-013 | STORY-016 | 2 |
| FR-014 | STORY-017 | 2 |
| FR-015 | STORY-018 | 3 |
| FR-016 | STORY-019 | 3 |
| FR-017 | STORY-020 | 3 |
| FR-018 | STORY-021 | 3 |

**Coverage:** 18/18 FRs (100%)

---

### Sprint 7 (Semaines 13-14) - 18 points

**Goal:** Implémenter les nouveaux écrans UX (Column Mapping + Qualification) avec accessibilité WCAG AAA

| Story | Description | Points | Priority |
|-------|-------------|--------|----------|
| STORY-031 | Column Mapping Web UI | 5 | Must |
| STORY-032 | Qualification Web UI | 8 | Must |
| STORY-033 | WCAG AAA Accessibility | 5 | Should |

**Total:** 18 points / 35 capacity (51%)

**Deliverables Sprint 7:**
- Page Column Mapping avec preview données
- Page Qualification avec workflow 10 questions
- Conformité WCAG 2.1 AAA sur toutes les pages
- Routes API pour mapping et qualification

**Dependencies:**
- UX Design document (completed)
- Architecture validation (completed)

**Risks:**
- Complexité du workflow qualification → mitigation: suivre wireframes UX

---

## New Stories (Sprint 7)

### STORY-031: Column Mapping Web UI

**Epic:** EPIC-007 UX Enhancement
**Priority:** Must Have
**Points:** 5
**FR:** FR-003 (Web UI)
**UX Ref:** ux-design-gl-normalizer-2026-02-03.md - Screen 2

**User Story:**
En tant que DAF avec un format GL non reconnu,
Je veux mapper manuellement les colonnes via l'interface web,
Afin de pouvoir analyser mon fichier sans utiliser la CLI.

**Acceptance Criteria:**
- [ ] Route `/mapping/<job_id>` accessible après détection format échouée
- [ ] Affichage des colonnes détectées dans le fichier
- [ ] 5 dropdowns pour mapper: Compte, Date, Montant, Libellé, Journal
- [ ] Preview des 5 premières lignes avec colonnes mappées
- [ ] Validation des colonnes obligatoires (Compte, Date, Montant, Libellé)
- [ ] Option "Sauvegarder ce mapping" pour réutilisation
- [ ] Boutons Annuler (retour upload) et Valider (continue analyse)
- [ ] Messages d'erreur clairs en français
- [ ] Accessible au clavier (Tab navigation)

**Technical Notes:**
- Template: `templates/mapping.html`
- Route: `GET/POST /mapping/<job_id>`
- API: `GET /api/preview/<job_id>` pour données preview
- API: `POST /api/mapping/<job_id>` pour soumettre mapping
- Utilise `Loader.map_columns()` existant
- Stockage mapping en session ou fichier temp

**Dependencies:** Loader component (exists), UX Design

---

### STORY-032: Qualification Web UI

**Epic:** EPIC-007 UX Enhancement
**Priority:** Must Have
**Points:** 8
**FR:** FR-009, FR-010, FR-011 (Web UI)
**UX Ref:** ux-design-gl-normalizer-2026-02-03.md - Screen 5

**User Story:**
En tant que DAF,
Je veux qualifier les anomalies détectées via l'interface web,
Afin de documenter mes décisions et obtenir un run rate dépollué.

**Acceptance Criteria:**
- [ ] Route `/qualify/<job_id>` accessible depuis page Results
- [ ] Affichage des top 10 anomalies par impact
- [ ] Pour chaque anomalie:
  - Type, sévérité, montant impacté, mois concerné
  - Contexte PCG (compte, classe, comportement attendu)
  - 3 options: Justifié / Non justifié / À investiguer
  - Champ commentaire optionnel
- [ ] Navigation: Passer / Précédent / Suivant (Terminer sur dernière)
- [ ] Progress indicator (1/10, 2/10, etc.)
- [ ] Sauvegarde automatique des réponses
- [ ] Bouton "Terminer" recalcule run rate et redirige vers Results
- [ ] Accessible au clavier (Tab, Enter, flèches pour radio)

**Technical Notes:**
- Template: `templates/qualification.html`
- Route: `GET /qualify/<job_id>`
- API: `GET /api/qualifications/<job_id>` - liste anomalies
- API: `POST /api/qualifications/<job_id>` - soumettre réponses
- Utilise `Qualifier` component existant
- Stockage en YAML (justifications.yaml)

**Dependencies:** Qualifier component (exists), Detector (exists), UX Design

---

### STORY-033: WCAG AAA Accessibility Updates

**Epic:** EPIC-007 UX Enhancement
**Priority:** Should Have
**Points:** 5
**NFR:** Accessibility WCAG 2.1 Level AAA
**UX Ref:** ux-design-gl-normalizer-2026-02-03.md - Section 3

**User Story:**
En tant qu'utilisateur avec handicap visuel ou moteur,
Je veux que l'application soit conforme WCAG AAA,
Afin de pouvoir utiliser toutes les fonctionnalités.

**Acceptance Criteria:**
- [ ] Ratio de contraste 7:1 pour texte normal, 4.5:1 pour grand texte
- [ ] Skip link "Aller au contenu principal" sur toutes les pages
- [ ] Focus visible (3px outline) sur tous éléments interactifs
- [ ] Navigation complète au clavier sans piège
- [ ] `aria-label` sur tous boutons icône
- [ ] `aria-live="polite"` pour mises à jour dynamiques
- [ ] Landmarks HTML5: `<header>`, `<nav>`, `<main>`, `<footer>`
- [ ] Hiérarchie headings (H1 unique, H2 sections, H3 sous-sections)
- [ ] Labels associés à tous les inputs (`for`/`id`)
- [ ] Messages d'erreur avec `aria-invalid` et `aria-describedby`
- [ ] `lang="fr"` sur `<html>`

**Technical Notes:**
- Mettre à jour `static/style.css`
- Mettre à jour tous templates existants
- Tester avec extension Axe DevTools
- Tester navigation clavier manuelle

**Dependencies:** All existing templates

---

## Risks and Mitigation

### High

| Risk | Mitigation |
|------|------------|
| Formats GL non documentés | Commencer par format Sage (bien connu) |
| Faux positifs excessifs | Contextualisation PCG + seuils conservateurs |

### Medium

| Risk | Mitigation |
|------|------------|
| Performance sur gros fichiers | Vectorisation pandas, profiling |
| PCG incomplet | Prévoir fallback si compte non trouvé |

### Low

| Risk | Mitigation |
|------|------------|
| Dépendances IA lourdes | Module IA optionnel, dépendances séparées |

---

## Definition of Done

Pour qu'une story soit considérée complète :

- [ ] Code implémenté et commité
- [ ] Tests unitaires écrits et passants (≥70% coverage)
- [ ] Code linted (black, flake8)
- [ ] Docstrings pour fonctions publiques
- [ ] Acceptance criteria validés
- [ ] Intégré dans le workflow principal

---

## Next Steps

**Current:** Sprint 7 - UX Enhancement

**Stories à implémenter:**
1. `STORY-031` - Column Mapping Web UI (5 points)
2. `STORY-032` - Qualification Web UI (8 points)
3. `STORY-033` - WCAG AAA Accessibility (5 points)

```bash
# Pour commencer l'implémentation:
/dev-story STORY-031
```

**Sprint cadence:**
- Sprint length: 2 semaines
- Sprint 7 goal: Nouveaux écrans UX + Accessibilité AAA

---

## Sprint History

| Sprint | Status | Goal | Points |
|--------|--------|------|--------|
| Sprint 1 | Completed | Fondations + Import + Détection base | 32 |
| Sprint 2 | Completed | MVP (Qualification + Run Rate + Rapport) | 32 |
| Sprint 3 | Completed | Module IA optionnel | 16 |
| Sprint 4 | Completed | Sécurité tokens | 6 |
| Sprint 5 | Completed | Algorithmes avancés | 16 |
| Sprint 6 | Completed | UX + Performance | 18 |
| Sprint 7 | Completed | UX Screens (Mapping + Qualification) | 18 |
| Sprint 8 | **Current** | IA Improvements + Réduction Faux Positifs | 23 |

---

## Sprint 8 (Semaines 15-16) - 23 points

**Goal:** Améliorer l'efficacité de l'IA et réduire les faux positifs basé sur la recherche

**Research Reference:** `docs/research-anomaly-detection-ia-audit-2026-02-04.md`

| Story | Description | Points | Priority |
|-------|-------------|--------|----------|
| STORY-034 | SHAP Explainability pour Isolation Forest | 5 | Must |
| STORY-035 | Amélioration Benford (2ème chiffre + seuils adaptatifs) | 5 | Must |
| STORY-036 | EnsembleAnomalyScorer | 8 | Should |
| STORY-037 | Dashboard Métriques | 5 | Should |

**Total:** 23 points / 35 capacity (66%)

**Deliverables Sprint 8:**
- SHAP values pour toutes les anomalies Isolation Forest
- Benford amélioré avec moins de faux positifs
- Scoring ensemble combinant tous les détecteurs
- Page `/metrics` avec F1, Precision, Recall

**Research Insights Applied:**
- "SHAP explainability increases actionable rate to 85%"
- "Benford needs adaptive thresholds to reduce FP"
- "Hybrid approaches (stats + ML) achieve 98-99% accuracy"

---

## New Stories (Sprint 8)

### STORY-034: SHAP Explainability pour Isolation Forest

**Epic:** EPIC-008 AI Improvements
**Priority:** Must Have
**Points:** 5
**Research Ref:** Insight 2 - "Explicabilité critique"

**User Story:**
En tant que DAF,
Je veux comprendre pourquoi une anomalie a été détectée,
Afin de prendre des décisions éclairées sur sa qualification.

**Acceptance Criteria:**
- [ ] Intégration SHAP TreeExplainer pour Isolation Forest
- [ ] Calcul des top 3 features contributives par anomalie
- [ ] Affichage dans l'UI Qualification (contexte étendu)
- [ ] Format: "Cette anomalie est due à: montant élevé (45%), mois inhabituel (30%), compte rare (25%)"
- [ ] Performance: < 2s pour 100 anomalies

**Technical Notes:**
- Fichier: `src/ai/isolation_forest.py`
- Package: `shap` (ajouter à requirements.txt)
- Méthode: `explain_anomaly(anomaly_id) -> Dict[str, float]`
- UI: Ajouter section "Pourquoi cette anomalie?" dans qualification.html

**Dependencies:** STORY-020 (Isolation Forest existant)

---

### STORY-035: Amélioration Benford (2ème chiffre + seuils adaptatifs)

**Epic:** EPIC-008 AI Improvements
**Priority:** Must Have
**Points:** 5
**Research Ref:** Insight 3 - "Benford génère trop de faux positifs seul"

**User Story:**
En tant que DAF,
Je veux une analyse Benford plus précise,
Afin de réduire les faux positifs dus aux seuils comptables.

**Acceptance Criteria:**
- [ ] Analyse du 2ème chiffre (souvent négligé, 30% oversight rate)
- [ ] Seuil adaptatif basé sur log-normal cutoff
- [ ] Filtrage des montants affectés par seuils comptables (5000€, 10000€)
- [ ] Combinaison 1er + 2ème chiffre pour score final
- [ ] Réduction faux positifs de 30-50% (à mesurer)

**Technical Notes:**
- Fichier: `src/ai/benford.py`
- Nouvelle méthode: `analyze_second_digit(amounts)`
- Nouvelle méthode: `apply_adaptive_threshold(amounts, cutoff_factor=0.05)`
- Test: Comparer FP avant/après sur dataset test

**Dependencies:** STORY-019 (Benford existant)

---

### STORY-036: EnsembleAnomalyScorer

**Epic:** EPIC-008 AI Improvements
**Priority:** Should Have
**Points:** 8
**Research Ref:** Insight 1 - "Approche hybride incontournable"

**User Story:**
En tant que DAF,
Je veux un score d'anomalie combinant toutes les méthodes,
Afin d'avoir une vue unifiée et plus fiable.

**Acceptance Criteria:**
- [ ] Agrège scores de: Benford, Z-score, MAD, IQR, Isolation Forest
- [ ] Normalisation des scores sur échelle 0-100
- [ ] Stratégies de voting configurables: unanime, majorité, weighted
- [ ] Poids par défaut basés sur recherche (IF: 0.3, MAD: 0.25, Benford: 0.2, Z-score: 0.15, IQR: 0.1)
- [ ] Score final avec confidence level (High/Medium/Low)
- [ ] API: `ensemble_score(transaction) -> (score: float, confidence: str, details: dict)`

**Technical Notes:**
- Nouveau fichier: `src/ai/ensemble_scorer.py`
- Classe: `EnsembleAnomalyScorer`
- Configurable via YAML: `config/ensemble_weights.yaml`
- Intégration dans `Analyzer` existant

**Dependencies:** Tous les détecteurs existants (STORY-005, 019, 020, 024)

---

### STORY-037: Dashboard Métriques

**Epic:** EPIC-008 AI Improvements
**Priority:** Should Have
**Points:** 5
**Research Ref:** Insight 4 - "Métriques actuelles inadaptées"

**User Story:**
En tant que DAF,
Je veux voir les métriques de performance de l'outil,
Afin de comprendre son efficacité et l'améliorer.

**Acceptance Criteria:**
- [ ] Nouvelle page `/metrics/<job_id>`
- [ ] Affichage: Precision, Recall, F1-Score (si données labellisées disponibles)
- [ ] Affichage: Nb anomalies détectées, Nb qualifiées, Taux actionnable
- [ ] Graphique distribution des scores d'anomalie
- [ ] Export des métriques en JSON
- [ ] Bouton "Contribuer feedback" pour améliorer le modèle

**Technical Notes:**
- Fichier template: `templates/metrics.html`
- Route: `GET /metrics/<job_id>`
- API: `GET /api/metrics/<job_id>`
- Utilise qualifications pour calculer taux actionnable
- Si pas de labels: afficher métriques partielles

**Dependencies:** Qualification UI (STORY-032), EnsembleScorer (STORY-036)

---

## Next Steps

**Current:** Sprint 8 - AI Improvements

**Stories à implémenter:**
1. `STORY-034` - SHAP Explainability (5 points) - Must
2. `STORY-035` - Benford Improvements (5 points) - Must
3. `STORY-036` - EnsembleAnomalyScorer (8 points) - Should
4. `STORY-037` - Dashboard Métriques (5 points) - Should

```bash
# Pour commencer l'implémentation:
/dev-story STORY-034
```

**Sprint cadence:**
- Sprint length: 2 semaines
- Sprint 8 goal: Réduction faux positifs + Explicabilité IA

---

*Document généré par BMAD Method v6 - Phase 4 Implementation Planning*
*Dernière mise à jour: 2026-02-04*
