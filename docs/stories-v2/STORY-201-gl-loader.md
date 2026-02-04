# STORY-201: GLLoader - Chargement et normalisation du GL

## Métadonnées
- **ID**: STORY-201
- **Epic**: EPIC-201 (Couche 1 - Lecture comptable)
- **Priorité**: Must Have
- **Estimation**: 2 points
- **Dépendances**: Aucune (première story)

## User Story

**En tant que** DAF,
**Je veux** charger mon export GL Excel,
**Afin de** lancer l'analyse sans configuration complexe.

## Contexte

Le GLLoader est le point d'entrée. Il doit :
1. Accepter les formats Excel courants (.xlsx, .xls)
2. Détecter automatiquement le format (Sage, Cegid, etc.)
3. Normaliser les colonnes vers un schéma standard

## Acceptance Criteria

- [ ] Charge fichiers .xlsx et .xls jusqu'à 200k lignes
- [ ] Détecte automatiquement : Sage, Cegid, Quadratus, EBP
- [ ] Normalise vers colonnes standard : `compte`, `date`, `mois`, `libelle`, `journal`, `debit`, `credit`, `montant`
- [ ] Message d'erreur clair si format non reconnu
- [ ] Temps de chargement < 30 sec pour 100k lignes

## Schéma de sortie

```python
DataFrame normalisé:
- compte: str        # "601000"
- date: datetime     # 2024-12-31
- mois: int          # 12
- libelle: str       # "Achat matières"
- journal: str       # "ACH"
- debit: float       # 1000.00
- credit: float      # 0.00
- montant: float     # 1000.00 (debit - credit)
```

## Tests

```python
def test_load_xlsx():
    """Charge un fichier Excel standard."""

def test_detect_sage_format():
    """Détecte le format Sage automatiquement."""

def test_normalize_columns():
    """Normalise les colonnes vers le schéma standard."""

def test_large_file_performance():
    """100k lignes en < 30 sec."""
```

## Notes techniques

- Utiliser `openpyxl` pour .xlsx, `xlrd` pour .xls
- Détection format par noms de colonnes (patterns)
- Mapping configurable dans `data/formats_mapping.yaml`
