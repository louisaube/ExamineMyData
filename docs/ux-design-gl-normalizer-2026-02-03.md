# UX Design Document
# GL Normalizer (ExamineMyData)

**Date:** 2026-02-03
**Designer:** BMAD UX Designer
**Version:** 1.0

---

## Project Overview

| Attribute | Value |
|-----------|-------|
| **Project** | GL Normalizer (ExamineMyData) |
| **Type** | Web Application |
| **Target Platform** | Web Desktop |
| **Accessibility** | WCAG 2.1 Level AAA |
| **Design Level** | High-level (flows + wireframes) |
| **Language** | French |

---

## Design Scope

### Screens Inventory

| Screen | Status | PRD Reference |
|--------|--------|---------------|
| **Upload** | Existing | FR-001, FR-002 |
| **Column Mapping** | NEW | FR-003 |
| **Loading** | Existing | - |
| **Results** | Existing | FR-004 to FR-018 |
| **Qualification** | NEW | FR-009, FR-010, FR-011 |
| **Settings** | Existing | STORY-027 |

**Total Screens:** 6 (4 existing + 2 new)

### User Flows

| Flow | Screens | User Stories |
|------|---------|--------------|
| Standard Analysis | Upload → Loading → Results | FR-001 to FR-015 |
| Manual Mapping | Upload → Column Mapping → Loading → Results | FR-003 |
| Anomaly Qualification | Results → Qualification → Results | FR-009 to FR-011 |
| Re-analysis | Upload → Loading → Results (with justifications) | FR-011 |
| Settings | Settings | STORY-027 |

---

## 1. User Flows

### Flow 1: Standard Analysis (Happy Path)

**Entry Point:** User lands on Upload page

```
[Upload Page]
     │
     │ User selects GL Excel file
     │ User enters year (default: 2024)
     │ User clicks "Analyser"
     ▼
[Format Detection]
     │
     ├─── Format recognized (Sage/Cegid/etc.)
     │         │
     │         ▼
     │    [Loading Page]
     │         │ Progress bar (0% → 100%)
     │         │ Status messages
     │         ▼
     │    [Results Page]
     │         │ Summary cards
     │         │ P&L breakdown
     │         │ Anomalies table
     │         │ AI analysis (if enabled)
     │         ▼
     │    [Success]
     │
     └─── Format NOT recognized
               │
               ▼
          [Column Mapping Page] (NEW)
               │ User maps columns manually
               │ User clicks "Valider"
               ▼
          [Loading Page]
               │
               ▼
          [Results Page]
```

**Decision Points:**
- Format detection → Auto (continue) or Manual mapping (redirect)

**Error Cases:**
- Invalid file format → Show error on Upload page
- Missing required columns → Show error on Mapping page
- Analysis failure → Show error on Loading page with retry option

---

### Flow 2: Column Mapping (FR-003)

**Entry Point:** Format not auto-detected

```
[Column Mapping Page]
     │
     │ Display detected columns from Excel
     │ User maps: Compte, Date, Montant, Libellé, Journal
     │
     ├─── All required columns mapped
     │         │
     │         ▼
     │    [Validate Mapping]
     │         │
     │         ├─── Valid → Continue to Loading
     │         │
     │         └─── Invalid → Show error, highlight missing
     │
     └─── User cancels
               │
               ▼
          [Upload Page]
```

---

### Flow 3: Anomaly Qualification (FR-009-011)

**Entry Point:** User clicks "Qualifier" on Results page

```
[Results Page]
     │
     │ User sees anomalies table
     │ User clicks "Qualifier les anomalies"
     ▼
[Qualification Page] (NEW)
     │
     │ Display top 10 anomalies by impact
     │ For each anomaly:
     │   - Show context (compte, montant, mois)
     │   - Show PCG context
     │   - Options: Justifié / Non justifié / À investiguer
     │   - Optional comment field
     │
     ├─── User qualifies all anomalies
     │         │
     │         ▼
     │    [Save Justifications] (YAML)
     │         │
     │         ▼
     │    [Results Page] (updated)
     │         │ Run rate recalculated
     │         │ Anomalies marked with status
     │
     └─── User skips/cancels
               │
               ▼
          [Results Page] (unchanged)
```

---

### Flow 4: Year Comparison (Optional)

**Entry Point:** User expands comparison section on Upload page

```
[Upload Page]
     │
     │ User expands "Comparer avec une autre année"
     │ User selects second GL file
     │ User enters N-1 year
     │ User clicks "Analyser"
     ▼
[Loading Page]
     │ Analyze both files
     ▼
[Results Page - Comparison Mode]
     │ Show year-over-year comparison
     │ Variation comptable vs run rate
     │ Impact des provisions
```

---

### Flow 5: Settings / API Configuration

**Entry Point:** User clicks "Paramètres" in header

```
[Settings Page]
     │
     │ Display AI status (enabled/disabled)
     │ Show provider cards (OpenAI, Anthropic, HuggingFace)
     │
     ├─── User adds token
     │         │ Enter token value
     │         │ Click "Enregistrer"
     │         │ Token validated and saved
     │         ▼
     │    [Success message]
     │
     ├─── User tests token
     │         │ Click "Tester"
     │         ▼
     │    [Test result] (success/failure)
     │
     └─── User deletes token
               │ Click "Supprimer"
               │ Confirm deletion
               ▼
          [Token removed]
```

---

## 2. Wireframes

### Screen 1: Upload Page (Existing)

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌───────────────────────────────────────────────────────────┐   │
│ │  GL Normalizer          Analyse et normalisation du P&L  │   │
│ │                                              [Paramètres] │   │
│ └───────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────┐                    │
│  │  Analyser votre Grand Livre             │                    │
│  │                                         │                    │
│  │  Fichier GL (Excel)                     │                    │
│  │  ┌─────────────────────────────────┐    │                    │
│  │  │  [Choisir un fichier]           │    │                    │
│  │  └─────────────────────────────────┘    │                    │
│  │  Format: Excel (.xlsx, .xls)            │                    │
│  │                                         │                    │
│  │  Année                                  │                    │
│  │  ┌─────────────────────────────────┐    │                    │
│  │  │  2024                           │    │                    │
│  │  └─────────────────────────────────┘    │                    │
│  │                                         │                    │
│  │  ▼ Comparer avec une autre année        │                    │
│  │    (optionnel - collapsed by default)   │                    │
│  │                                         │                    │
│  │  ┌─────────────────────────────────┐    │                    │
│  │  │       [  Analyser  ]            │    │                    │
│  │  └─────────────────────────────────┘    │                    │
│  │                                         │                    │
│  └─────────────────────────────────────────┘                    │
│                                                                  │
│  ┌─────────────────────────────────────────┐                    │
│  │  Fonctionnalités                        │                    │
│  │  • Calcul du run rate opérationnel      │                    │
│  │  • Détection des anomalies              │                    │
│  │  • Analyse des concentrations           │                    │
│  │  • Comparaison N vs N-1                 │                    │
│  │  • Export rapport Excel                 │                    │
│  │                                         │                    │
│  │  Formats supportés                      │                    │
│  │  Sage, Cegid, Quadratus, EBP, Excel     │                    │
│  └─────────────────────────────────────────┘                    │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                    GL Normalizer v2.6.0                          │
└─────────────────────────────────────────────────────────────────┘
```

**Interactions:**
- File input → Native file picker
- Year input → Number spinner (min: 2000, max: 2100)
- Details/Summary → Expand/collapse comparison section
- Analyser button → Submit form, show loading state

---

### Screen 2: Column Mapping Page (NEW)

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌───────────────────────────────────────────────────────────┐   │
│ │  GL Normalizer          Analyse et normalisation du P&L  │   │
│ │                                              [Paramètres] │   │
│ └───────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Mapping des colonnes                                       ││
│  │                                                             ││
│  │  ⚠ Le format de votre fichier n'a pas été reconnu           ││
│  │    automatiquement. Veuillez indiquer les colonnes.         ││
│  │                                                             ││
│  │  ┌───────────────────────────────────────────────────────┐  ││
│  │  │  Colonnes détectées: A, B, C, D, E, F, G, H           │  ││
│  │  └───────────────────────────────────────────────────────┘  ││
│  │                                                             ││
│  │  Colonnes requises                                          ││
│  │  ─────────────────────────────────────────────────────────  ││
│  │                                                             ││
│  │  Compte *              Libellé *                            ││
│  │  ┌─────────────────┐   ┌─────────────────┐                  ││
│  │  │ Sélectionner ▼  │   │ Sélectionner ▼  │                  ││
│  │  └─────────────────┘   └─────────────────┘                  ││
│  │                                                             ││
│  │  Date *                Montant *                            ││
│  │  ┌─────────────────┐   ┌─────────────────┐                  ││
│  │  │ Sélectionner ▼  │   │ Sélectionner ▼  │                  ││
│  │  └─────────────────┘   └─────────────────┘                  ││
│  │                                                             ││
│  │  Journal                                                    ││
│  │  ┌─────────────────┐                                        ││
│  │  │ Sélectionner ▼  │   (optionnel)                          ││
│  │  └─────────────────┘                                        ││
│  │                                                             ││
│  │  ─────────────────────────────────────────────────────────  ││
│  │                                                             ││
│  │  Aperçu des données (5 premières lignes)                    ││
│  │  ┌───────────────────────────────────────────────────────┐  ││
│  │  │ Compte │ Date       │ Libellé          │ Montant      │  ││
│  │  │ 601000 │ 2024-01-15 │ Achat matières   │ 12 500,00 €  │  ││
│  │  │ 601000 │ 2024-01-22 │ Achat matières   │  8 750,00 €  │  ││
│  │  │ ...    │ ...        │ ...              │ ...          │  ││
│  │  └───────────────────────────────────────────────────────┘  ││
│  │                                                             ││
│  │  ☐ Sauvegarder ce mapping pour une utilisation future       ││
│  │                                                             ││
│  │  ┌───────────────┐  ┌───────────────┐                       ││
│  │  │   Annuler     │  │   Valider     │                       ││
│  │  └───────────────┘  └───────────────┘                       ││
│  │                                                             ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                    GL Normalizer v2.6.0                          │
└─────────────────────────────────────────────────────────────────┘
```

**Elements:**
- Warning banner (yellow) explaining why mapping is needed
- 5 dropdown selects for column mapping
- Data preview table showing first 5 rows with mapped columns
- Checkbox to save mapping for future use
- Cancel and Validate buttons

**Validation:**
- All required (*) fields must be selected
- Selected columns must have valid data types
- Preview updates when selection changes

---

### Screen 3: Loading Page (Existing)

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌───────────────────────────────────────────────────────────┐   │
│ │  GL Normalizer          Analyse et normalisation du P&L  │   │
│ └───────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                                                                  │
│                                                                  │
│                     ┌─────────────────────┐                      │
│                     │                     │                      │
│                     │    ◠◡◠  (spinner)   │                      │
│                     │                     │                      │
│                     └─────────────────────┘                      │
│                                                                  │
│                        Analyse en cours                          │
│                                                                  │
│               Chargement du fichier GL_2024.xlsx                 │
│                                                                  │
│                     ┌─────────────────────┐                      │
│                     │████████░░░░░░░░░░░░░│  45%                 │
│                     └─────────────────────┘                      │
│                                                                  │
│              Étape 3/6: Détection des anomalies                  │
│                                                                  │
│                                                                  │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                    GL Normalizer v2.6.0                          │
└─────────────────────────────────────────────────────────────────┘
```

**Elements:**
- Animated spinner (CSS rotation)
- Main status text
- File name being processed
- Progress bar with percentage
- Current step indicator (e.g., "Étape 3/6: Détection des anomalies")

**States:**
1. Chargement du fichier (0-20%)
2. Validation des colonnes (20-30%)
3. Profilage des données (30-50%)
4. Détection des anomalies (50-70%)
5. Calcul du run rate (70-90%)
6. Génération du rapport (90-100%)

---

### Screen 4: Results Page (Existing - Enhanced)

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌───────────────────────────────────────────────────────────┐   │
│ │  GL Normalizer                           [Paramètres]     │   │
│ └───────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Résultats de l'analyse                [Télécharger Excel]      │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │  2024    │  │  45 218  │  │ 125 000€ │  │ 1.5 M€   │        │
│  │  Année   │  │ Écritures│  │ Run Rate │  │ Charges  │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│                                                                  │
│  ┌────────────────┬────────────────┬────────────────┐           │
│  │ Score risque   │ Qualité        │ Anomalies      │           │
│  │ ██████░░░ 35%  │ ████████ Good  │ 12             │           │
│  └────────────────┴────────────────┴────────────────┘           │
│                                                                  │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  Compte de Résultat                                              │
│  ┌─────────────────────────────┬─────────────────────────────┐  │
│  │         CHARGES             │         PRODUITS            │  │
│  │ ─────────────────────────── │ ─────────────────────────── │  │
│  │ 60 Achats       450 000 €   │ 70 Ventes     1 800 000 €   │  │
│  │ 61 Services     280 000 €   │ 74 Subv.        50 000 €    │  │
│  │ 62 Autres        85 000 €   │                             │  │
│  │ 63 Impôts        45 000 €   │                             │  │
│  │ 64 Personnel    620 000 €   │                             │  │
│  │ 65 Autres        35 000 €   │                             │  │
│  │ ─────────────────────────── │ ─────────────────────────── │  │
│  │ Total        1 515 000 €    │ Total        1 850 000 €    │  │
│  └─────────────────────────────┴─────────────────────────────┘  │
│                                                                  │
│           ┌─────────────────────────────────────┐                │
│           │     RÉSULTAT     +335 000 €         │                │
│           └─────────────────────────────────────┘                │
│                                                                  │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  Points d'attention (3)                                          │
│  • Concentration importante sur le compte 681000 en décembre     │
│  • Journal OD avec 45% des écritures en fin d'année             │
│  • Provision exceptionnelle détectée sur 687xxx                  │
│                                                                  │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  Anomalies détectées (12)         [Qualifier les anomalies]     │
│  ┌─────────┬────────────┬─────────┬──────────┬─────────────┐    │
│  │ Compte  │ Type       │ Sévérité│ Montant  │ Statut      │    │
│  │ 681000  │ Concentr.  │ ●High   │ 85 000€  │ ○ Pending   │    │
│  │ 617000  │ Z-score    │ ●Medium │ 12 500€  │ ○ Pending   │    │
│  │ 687000  │ Provision  │ ●High   │ 45 000€  │ ○ Pending   │    │
│  │ ...     │ ...        │ ...     │ ...      │ ...         │    │
│  └─────────┴────────────┴─────────┴──────────┴─────────────┘    │
│                                                                  │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  Analyse proactive IA (si activée)                               │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Pattern: Concentration décembre                              ││
│  │ Compte 681000 présente 85% du total en décembre             ││
│  │ [Analyser]                                                   ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│                    [Nouvelle analyse]                            │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                    GL Normalizer v2.6.0                          │
└─────────────────────────────────────────────────────────────────┘
```

---

### Screen 5: Qualification Page (NEW)

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌───────────────────────────────────────────────────────────┐   │
│ │  GL Normalizer          Qualification des anomalies       │   │
│ └───────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Qualification des anomalies                 Anomalie 1/10      │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                                                             ││
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ││
│  │  ANOMALIE #1 - Compte 681000                                ││
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ││
│  │                                                             ││
│  │  Type: Concentration mensuelle                              ││
│  │  Sévérité: ●●●○ Élevée                                      ││
│  │  Montant impacté: 85 000 €                                  ││
│  │  Mois concerné: Décembre (85% du total annuel)              ││
│  │                                                             ││
│  │  ┌───────────────────────────────────────────────────────┐  ││
│  │  │  Contexte PCG                                         │  ││
│  │  │  ─────────────────────────────────────────────────────│  ││
│  │  │  Compte: 681000 - Dotations aux amortissements        │  ││
│  │  │  Classe: 6 - Charges                                  │  ││
│  │  │  Nature: Charge d'exploitation                        │  ││
│  │  │                                                       │  ││
│  │  │  Comportement attendu: Mensuel (1/12 par mois)        │  ││
│  │  │  Comportement observé: 85% concentré en décembre      │  ││
│  │  └───────────────────────────────────────────────────────┘  ││
│  │                                                             ││
│  │  ❓ Cette concentration est-elle justifiée ?                ││
│  │                                                             ││
│  │  ○ Justifié - Dotation annuelle normale pour ce type        ││
│  │               de compte                                     ││
│  │                                                             ││
│  │  ○ Non justifié - Devrait être réparti mensuellement       ││
│  │                                                             ││
│  │  ○ À investiguer - Besoin d'informations supplémentaires    ││
│  │                                                             ││
│  │  Commentaire (optionnel)                                    ││
│  │  ┌───────────────────────────────────────────────────────┐  ││
│  │  │                                                       │  ││
│  │  │                                                       │  ││
│  │  └───────────────────────────────────────────────────────┘  ││
│  │                                                             ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  ○ ○ ○ ○ ○ ○ ○ ○ ○ ○   (progress: 1/10)                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Passer    │  │  Précédent  │  │   Suivant / Terminer   │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                    GL Normalizer v2.6.0                          │
└─────────────────────────────────────────────────────────────────┘
```

**Elements:**
- Progress indicator (1/10)
- Anomaly card with full context
- PCG context box (blue background)
- Radio buttons for qualification choice
- Optional comment textarea
- Navigation buttons (Skip, Previous, Next/Finish)
- Dot progress indicator at bottom

**Interactions:**
- Radio selection required to proceed (unless Skip)
- Comment auto-saves on blur
- "Terminer" appears on last anomaly instead of "Suivant"
- Skip increments counter without saving answer

---

### Screen 6: Settings Page (Existing)

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌───────────────────────────────────────────────────────────┐   │
│ │  GL Normalizer                                    [Accueil]│   │
│ └───────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Paramètres                                                      │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Statut IA: ● Activée                                       ││
│  │  Les fonctionnalités IA sont disponibles.                   ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  Configuration des tokens API                                    │
│                                                                  │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐ │
│  │     OpenAI       │ │    Anthropic     │ │   HuggingFace    │ │
│  │                  │ │                  │ │                  │ │
│  │ ● Configuré      │ │ ○ Non configuré  │ │ ○ Non configuré  │ │
│  │                  │ │                  │ │                  │ │
│  │ Token:           │ │ Token:           │ │ Token:           │ │
│  │ sk-...****       │ │ [____________]   │ │ [____________]   │ │
│  │                  │ │                  │ │                  │ │
│  │ [Tester][Suppr.] │ │ [Enregistrer]    │ │ [Enregistrer]    │ │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘ │
│                                                                  │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  Fonctionnalités par provider                                    │
│  ┌─────────────────┬─────────┬───────────┬─────────────────┐    │
│  │ Fonctionnalité  │ OpenAI  │ Anthropic │ HuggingFace     │    │
│  │ Drill-down IA   │   ✓     │    ✓      │       ✓         │    │
│  │ NLP Avancé      │   ✓     │    ✓      │       ○         │    │
│  │ Analyse pattern │   ✓     │    ✓      │       ✓         │    │
│  └─────────────────┴─────────┴───────────┴─────────────────┘    │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                    GL Normalizer v2.6.0                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Accessibility (WCAG 2.1 AAA)

### Global Requirements

| Criterion | WCAG Ref | Implementation |
|-----------|----------|----------------|
| **Color Contrast** | 1.4.6 | 7:1 ratio for normal text, 4.5:1 for large text |
| **Focus Visible** | 2.4.7 | 3px blue outline on all focusable elements |
| **Keyboard Navigation** | 2.1.1 | All interactions via keyboard |
| **Skip Links** | 2.4.1 | "Skip to main content" link |
| **Language** | 3.1.1 | `lang="fr"` on html element |
| **Error Identification** | 3.3.1 | Clear error messages in French |
| **Labels** | 1.3.1 | All inputs have associated labels |

### Screen-Specific Accessibility

#### Upload Page
```html
<!-- Skip link -->
<a href="#main" class="skip-link">Aller au contenu principal</a>

<!-- Form accessibility -->
<form role="form" aria-label="Formulaire d'analyse GL">
  <label for="file1">Fichier GL (Excel) <span aria-hidden="true">*</span></label>
  <input type="file" id="file1" name="file1" required aria-required="true"
         aria-describedby="file1-help">
  <small id="file1-help">Format accepté: Excel (.xlsx, .xls)</small>
</form>

<!-- Button states -->
<button type="submit" aria-busy="false">Analyser</button>
<!-- When loading: -->
<button type="submit" aria-busy="true" disabled>Analyse en cours...</button>
```

#### Loading Page
```html
<!-- Live region for progress updates -->
<div role="progressbar" aria-valuenow="45" aria-valuemin="0"
     aria-valuemax="100" aria-label="Progression de l'analyse">
  <div class="progress-fill" style="width: 45%"></div>
</div>

<!-- Status announcements -->
<div aria-live="polite" aria-atomic="true" class="status-message">
  Étape 3/6: Détection des anomalies
</div>
```

#### Results Page
```html
<!-- Data tables -->
<table aria-label="Anomalies détectées">
  <caption class="sr-only">Liste des 12 anomalies détectées dans le GL</caption>
  <thead>
    <tr>
      <th scope="col">Compte</th>
      <th scope="col">Type</th>
      <th scope="col">Sévérité</th>
      <th scope="col">Montant</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th scope="row">681000</th>
      <td>Concentration</td>
      <td><span class="severity-high" aria-label="Sévérité élevée">Élevée</span></td>
      <td>85 000 €</td>
    </tr>
  </tbody>
</table>

<!-- Severity badges with aria-labels -->
<span class="severity-badge severity-high" aria-label="Sévérité élevée">High</span>
```

#### Qualification Page
```html
<!-- Radio group -->
<fieldset>
  <legend>Cette concentration est-elle justifiée ?</legend>

  <div class="radio-option">
    <input type="radio" id="justified" name="qualification" value="justified">
    <label for="justified">
      <strong>Justifié</strong> - Dotation annuelle normale pour ce type de compte
    </label>
  </div>

  <div class="radio-option">
    <input type="radio" id="unjustified" name="qualification" value="unjustified">
    <label for="unjustified">
      <strong>Non justifié</strong> - Devrait être réparti mensuellement
    </label>
  </div>

  <div class="radio-option">
    <input type="radio" id="investigate" name="qualification" value="investigate">
    <label for="investigate">
      <strong>À investiguer</strong> - Besoin d'informations supplémentaires
    </label>
  </div>
</fieldset>

<!-- Progress indicator -->
<nav aria-label="Progression de qualification">
  <span class="sr-only">Anomalie 1 sur 10</span>
  <div class="dot-progress" role="group" aria-label="10 anomalies à qualifier">
    <span class="dot active" aria-current="step">1</span>
    <span class="dot">2</span>
    <!-- ... -->
  </div>
</nav>
```

### Keyboard Navigation Map

| Key | Action |
|-----|--------|
| `Tab` | Move to next focusable element |
| `Shift+Tab` | Move to previous focusable element |
| `Enter` | Activate button/link |
| `Space` | Toggle checkbox, select radio |
| `Escape` | Close modal/dropdown |
| `Arrow Up/Down` | Navigate within radio group |
| `Home/End` | Jump to first/last item in list |

### Screen Reader Landmarks

```html
<body>
  <a href="#main" class="skip-link">Aller au contenu principal</a>

  <header role="banner">
    <nav role="navigation" aria-label="Navigation principale">
      <!-- Logo and nav links -->
    </nav>
  </header>

  <main id="main" role="main">
    <!-- Page content -->
  </main>

  <footer role="contentinfo">
    <!-- Footer content -->
  </footer>
</body>
```

---

## 4. Component Library

### Buttons

| Variant | Usage | CSS Class |
|---------|-------|-----------|
| **Primary** | Main actions (Analyser, Valider) | `.btn-primary` |
| **Secondary** | Secondary actions (Télécharger) | `.btn-secondary` |
| **Danger** | Destructive actions (Supprimer) | `.btn-danger` |
| **Outline** | Tertiary actions | `.btn-outline` |

**Specs:**
- Min height: 44px (touch target)
- Padding: 12px 24px
- Border-radius: 8px
- Focus: 3px outline, 2px offset

### Cards

| Type | Usage |
|------|-------|
| **Summary Card** | KPI display (année, écritures, run rate) |
| **Pattern Card** | AI pattern display |
| **Provider Card** | Settings API providers |

**Specs:**
- Background: white
- Border-radius: 10px-12px
- Shadow: 0 2px 10px rgba(0,0,0,0.08)
- Padding: 20px-30px

### Form Elements

| Element | Specs |
|---------|-------|
| **Input** | Height 44px, border 2px, radius 8px |
| **Select** | Same as input, with dropdown arrow |
| **Textarea** | Min-height 80px, resize vertical |
| **Radio/Checkbox** | 20x20px, with label association |

### Tables

| Type | Usage |
|------|-------|
| **Data Table** | Anomalies, regularizations |
| **P&L Table** | Charges/Produits breakdown |

**Specs:**
- Header: dark background (#343a40), white text
- Row hover: light gray (#f1f3f5)
- Border-bottom: 1px solid #dee2e6

### Alerts / Badges

| Type | Color | Usage |
|------|-------|-------|
| **Success** | Green #28a745 | Positive status, justified |
| **Warning** | Yellow #ffc107 | Attention needed |
| **Danger** | Red #dc3545 | Error, critical severity |
| **Info** | Blue #17a2b8 | Information |

---

## 5. Design Tokens

Building on existing styles:

### Colors

```css
:root {
  /* Primary */
  --color-primary: #3182ce;
  --color-primary-dark: #2c5282;
  --color-primary-darker: #1a365d;

  /* Semantic */
  --color-success: #28a745;
  --color-warning: #ffc107;
  --color-danger: #dc3545;
  --color-info: #17a2b8;

  /* Neutral */
  --color-bg: #f5f7fa;
  --color-surface: #ffffff;
  --color-text: #333333;
  --color-text-secondary: #718096;
  --color-border: #e2e8f0;

  /* Severity */
  --color-severity-critical: #dc3545;
  --color-severity-high: #fd7e14;
  --color-severity-medium: #ffc107;
  --color-severity-low: #28a745;
}
```

### Typography

```css
:root {
  /* Font Family */
  --font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-family-mono: 'SF Mono', Monaco, monospace;

  /* Font Sizes */
  --text-xs: 0.75rem;   /* 12px */
  --text-sm: 0.875rem;  /* 14px */
  --text-base: 1rem;    /* 16px */
  --text-lg: 1.125rem;  /* 18px */
  --text-xl: 1.25rem;   /* 20px */
  --text-2xl: 1.5rem;   /* 24px */
  --text-3xl: 1.875rem; /* 30px */

  /* Line Heights */
  --leading-tight: 1.25;
  --leading-normal: 1.6;

  /* Font Weights */
  --font-normal: 400;
  --font-semibold: 600;
  --font-bold: 700;
}
```

### Spacing

```css
:root {
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;
}
```

### Borders & Shadows

```css
:root {
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;

  --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
  --shadow-md: 0 2px 10px rgba(0,0,0,0.08);
  --shadow-lg: 0 4px 20px rgba(0,0,0,0.12);
}
```

### Breakpoints

```css
:root {
  --breakpoint-sm: 600px;
  --breakpoint-md: 768px;
  --breakpoint-lg: 1024px;
  --breakpoint-xl: 1200px;
}
```

---

## 6. Developer Handoff

### Implementation Priorities

**Phase 1: New Screens**
1. Column Mapping page (FR-003)
2. Qualification page (FR-009-011)

**Phase 2: Accessibility Enhancements**
1. Add skip links to all pages
2. Add ARIA labels to interactive elements
3. Ensure 7:1 contrast ratio (WCAG AAA)
4. Add keyboard navigation support

**Phase 3: Polish**
1. Add animations (reduced motion support)
2. Improve error states
3. Add loading skeletons

### New Routes Needed

| Route | Method | Description |
|-------|--------|-------------|
| `/mapping` | GET | Column mapping page |
| `/mapping` | POST | Submit column mapping |
| `/qualify/<job_id>` | GET | Qualification page |
| `/qualify/<job_id>` | POST | Save qualifications |

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/preview/<job_id>` | GET | Get data preview for mapping |
| `/api/mapping/<job_id>` | POST | Submit column mapping |
| `/api/qualifications/<job_id>` | GET | Get anomalies to qualify |
| `/api/qualifications/<job_id>` | POST | Save qualification answers |

### Data Structures

```python
# Qualification request
class QualificationRequest:
    anomaly_id: int
    status: Literal["justified", "unjustified", "investigate"]
    comment: Optional[str]

# Mapping request
class MappingRequest:
    compte_column: str
    date_column: str
    montant_column: str
    libelle_column: str
    journal_column: Optional[str]
    save_mapping: bool
```

---

## 7. Requirements Coverage

### Functional Requirements → Screens

| FR | Requirement | Screen |
|----|-------------|--------|
| FR-001 | Chargement Excel | Upload |
| FR-002 | Détection format | Upload → auto |
| FR-003 | Mapping manuel | Column Mapping (NEW) |
| FR-004 | Concentrations | Results |
| FR-005 | Z-score | Results |
| FR-006 | Provisions | Results |
| FR-007 | Montants ronds | Results |
| FR-008 | Journaux OD | Results |
| FR-009 | Questions qualificatives | Qualification (NEW) |
| FR-010 | Justifications | Qualification (NEW) |
| FR-011 | Sauvegarde justifications | Qualification (NEW) |
| FR-012 | Run rate mensuel | Results |
| FR-013 | Neutralisation | Results (after qualification) |
| FR-014 | Rapport Excel | Results (download) |
| FR-015 | Comparatif | Results |
| FR-016 | Benford | Results (AI section) |
| FR-017 | Isolation Forest | Results (AI section) |
| FR-018 | NLP | Results (AI section) |

### NFRs Addressed

| NFR | Requirement | UX Solution |
|-----|-------------|-------------|
| NFR-001 | < 10 min analysis | Loading page with progress |
| NFR-003 | DAF utilisable | French UI, guided workflow, clear messages |
| NFR-004 | Messages d'erreur | Alert components with suggestions |
| NFR-005 | 100% recall | Results show all anomalies |
| NFR-006 | Min false positives | PCG context in qualification |

---

## 8. Sign-off Checklist

- [ ] Product Manager reviewed flows
- [ ] Architect validated feasibility
- [ ] Accessibility audit passed (WCAG AAA)
- [ ] All user stories mapped to screens
- [ ] Ready for implementation

---

*Generated by BMAD Method v6 - UX Designer*
*Design Date: 2026-02-03*
