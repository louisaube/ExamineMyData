# STORY-202: JournalClassifier - Classification des journaux

## Métadonnées
- **ID**: STORY-202
- **Epic**: EPIC-201 (Couche 1 - Lecture comptable)
- **Priorité**: Must Have
- **Estimation**: 1 point
- **Dépendances**: STORY-201

## User Story

**En tant que** outil d'analyse,
**Je veux** identifier la nature de chaque journal,
**Afin de** savoir où chercher les régularisations (OD).

## Contexte

Les journaux OD (Opérations Diverses) sont la zone de vigilance principale. C'est là que se passent :
- Les écritures de régularisation
- Les provisions
- Les corrections

## Classification cible

| Pattern | Type | Description |
|---------|------|-------------|
| OD, OD*, AN, RAN | OD | Opérations diverses - vigilance |
| SAL, PAI*, PAIE | PAIE | Salaires - récurrent |
| VTE, VE, FAC* | VENTE | Facturation clients |
| ACH, HA, FRN* | ACHAT | Fournisseurs |
| BQ, BNQ*, BAN* | BANQUE | Trésorerie (hors P&L) |
| CAI* | CAISSE | Trésorerie (hors P&L) |

## Acceptance Criteria

- [ ] Classifie chaque journal selon les patterns ci-dessus
- [ ] Identifie tous les journaux OD
- [ ] Calcule le volume par journal et par mois
- [ ] Flagge si OD décembre > 3x moyenne mensuelle
- [ ] Gère les codes journal inconnus (classés "AUTRE")

## Interface

```python
class JournalClassifier:
    def classify(self, journal_code: str) -> JournalType
    def get_od_journals(self, df: pd.DataFrame) -> List[str]
    def flag_december_spike(self, df: pd.DataFrame) -> Optional[Alert]
    def get_journal_stats(self, df: pd.DataFrame) -> pd.DataFrame
```

## Tests

```python
def test_classify_od():
    assert classifier.classify("OD") == JournalType.OD
    assert classifier.classify("OD1") == JournalType.OD

def test_classify_paie():
    assert classifier.classify("SAL") == JournalType.PAIE
    assert classifier.classify("PAIE01") == JournalType.PAIE

def test_december_spike_detection():
    """Détecte quand OD décembre > 3x moyenne."""

def test_unknown_journal():
    assert classifier.classify("XYZ") == JournalType.AUTRE
```

## Exemple de sortie

```
Journal Stats:
JOURNAL  TYPE    TOTAL_ECRITURES  DEC_ECRITURES  DEC_RATIO  SPIKE
OD       OD      8,251            4,129          50%        ⚠️ OUI
SAL      PAIE    2,400            200            8%         NON
ACH      ACHAT   45,000           3,800          8%         NON
VTE      VENTE   38,000           3,200          8%         NON
```
