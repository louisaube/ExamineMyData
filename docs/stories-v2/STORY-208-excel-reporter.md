# STORY-208: ExcelReporter - Génération du rapport Excel

## Métadonnées
- **ID**: STORY-208
- **Epic**: EPIC-202 (Couche 2 - Tableau de passage)
- **Priorité**: Must Have
- **Estimation**: 3 points
- **Dépendances**: STORY-206, STORY-207

## User Story

**En tant que** DAF,
**Je veux** un rapport Excel que je peux ouvrir et comprendre en 30 secondes,
**Afin de** challenger les chiffres avec mon expert-comptable.

## Contexte

Le rapport Excel est le **livrable final**. Il doit être :
- Lisible sans formation
- Imprimable sur 2-3 pages
- Partageable par email

## Structure du rapport

### Onglet 1 : Synthèse (30 secondes de lecture)

```
┌────────────────────────────────────────────────────────────┐
│           GL NORMALIZER - SYNTHÈSE EXERCICE 2024           │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  RÉSULTAT                    BRUT        NORMALISÉ         │
│  ─────────────────────────────────────────────────         │
│  Annuel                     694 K€        917 K€   +32%   │
│  Run rate mensuel            58 K€         76 K€   +32%   │
│                                                            │
│  CHARGES                     BRUT        NORMALISÉ         │
│  ─────────────────────────────────────────────────         │
│  Run rate mensuel           897 K€        861 K€   -4%    │
│                                                            │
├────────────────────────────────────────────────────────────┤
│  PRINCIPAUX RETRAITEMENTS                                  │
│                                                            │
│  • IS redistribué sur 12 mois              +234 K€        │
│  • Provisions créances (net)                -14 K€        │
│  • Exceptionnel exclu                        +3 K€        │
│  ─────────────────────────────────────────────────         │
│  Total                                     +223 K€        │
│                                                            │
├────────────────────────────────────────────────────────────┤
│  ⚠️ ALERTES (4)                                            │
│                                                            │
│  #1 Provision prud'hommes 15K non budgétée                │
│  #2 Reprise dépréciation 25K sans dotation récente        │
│  #3 Prime exceptionnelle 8K en décembre                   │
│  #4 Compte 615 comportement inhabituel                     │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### Onglet 2 : Tableau de passage mensuel

| Mois | Résultat brut | IS | Prov net | ABT | Except | Normalisé |
|------|---------------|-----|----------|-----|--------|-----------|
| Janv | 45 K | +19.5K | +1.2K | 0 | 0 | 66 K |
| Fév | 52 K | +19.5K | +1.2K | 0 | 0 | 73 K |
| ... | ... | ... | ... | ... | ... | ... |
| Déc | -30 K | +19.5K | +1.2K | +45K | -12K | 24 K |
| **Total** | **694 K** | **+234K** | **+14K** | **0** | **-25K** | **917 K** |

### Onglet 3 : Alertes détaillées

Une ligne par alerte avec :
- Priorité
- Type
- Compte
- Montant
- Libellé extrait
- Contexte
- Question/Action

### Onglet 4 : Détail retraitements

Liste de toutes les écritures retraitées avec :
- Date
- Compte
- Libellé
- Montant brut
- Montant retraité
- Type de retraitement
- Justification

## Acceptance Criteria

- [ ] 4 onglets : Synthèse, Passage mensuel, Alertes, Détail
- [ ] Onglet Synthèse lisible en 30 secondes
- [ ] Mise en forme conditionnelle (couleurs)
- [ ] Totaux et sous-totaux calculés
- [ ] Génération < 10 secondes
- [ ] Compatible Excel, LibreOffice, Google Sheets

## Interface

```python
class ExcelReporter:
    def generate(self,
                 summary: AnnualSummary,
                 monthly: List[MonthlyPassage],
                 alerts: List[Alert],
                 retraitements_detail: pd.DataFrame,
                 output_path: str) -> str

    def _create_summary_sheet(self, wb, summary, alerts)
    def _create_passage_sheet(self, wb, monthly)
    def _create_alerts_sheet(self, wb, alerts)
    def _create_detail_sheet(self, wb, retraitements)
    def _apply_formatting(self, wb)
```

## Tests

```python
def test_generate_excel():
    """Génère un fichier Excel valide."""

def test_four_sheets():
    """Le fichier a 4 onglets."""

def test_summary_content():
    """L'onglet synthèse contient les bons chiffres."""

def test_formatting():
    """Mise en forme appliquée."""

def test_generation_time():
    """Génération < 10 secondes."""
```

## Notes techniques

- Utiliser `openpyxl` pour la génération
- Styles prédéfinis pour cohérence visuelle
- Largeurs de colonnes auto-ajustées
- Freeze panes sur les en-têtes
