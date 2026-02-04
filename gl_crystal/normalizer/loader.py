"""
GL Crystal - Loader
Chargement et normalisation des GL depuis différents formats.

Formats supportés:
- Sage
- Cegid
- Quadratus
- EBP
- Générique (avec mapping manuel)

La détection du format est automatique via fuzzy matching sur les noms de colonnes.
"""

import pandas as pd
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass

from .schema import GLEntry, GLSchema


@dataclass
class ColumnMapping:
    """Mapping des colonnes source vers le schéma canonique."""
    date_ecriture: Optional[str] = None
    journal_code: Optional[str] = None
    journal_libelle: Optional[str] = None
    compte_general: Optional[str] = None
    compte_libelle: Optional[str] = None
    compte_auxiliaire: Optional[str] = None
    analytique: Optional[str] = None
    libelle_ecriture: Optional[str] = None
    debit: Optional[str] = None
    credit: Optional[str] = None
    piece: Optional[str] = None


# Patterns de détection par format
FORMAT_PATTERNS = {
    'sage': {
        'date': ['date écriture', 'date_ecriture', 'dateecr', 'date ecr'],
        'journal_code': ['code journal', 'journal', 'jal'],
        'journal_libelle': ['libellé journal', 'nom journal'],
        'compte': ['compte général', 'compte', 'n° compte', 'numero compte'],
        'compte_libelle': ['intitulé compte', 'libellé compte', 'nom compte'],
        'auxiliaire': ['compte auxiliaire', 'auxiliaire', 'tiers'],
        'analytique': ['section analytique', 'analytique', 'centre', 'axe'],
        'libelle': ['libellé écriture', 'libellé', 'designation'],
        'debit': ['débit', 'debit', 'montant débit'],
        'credit': ['crédit', 'credit', 'montant crédit'],
        'piece': ['n° pièce', 'piece', 'référence', 'ref'],
    },
    'cegid': {
        'date': ['DATE', 'DATEPCE', 'DATE_PIECE'],
        'journal_code': ['JOURNAL', 'JNL', 'CODE_JNL'],
        'compte': ['COMPTE', 'CPT', 'NUM_COMPTE'],
        'compte_libelle': ['LIBELLE_COMPTE', 'LIB_CPT'],
        'libelle': ['LIBELLE', 'LIB', 'DESIGNATION'],
        'debit': ['DEBIT', 'MT_DEBIT'],
        'credit': ['CREDIT', 'MT_CREDIT'],
        'piece': ['PIECE', 'NUM_PIECE', 'REF'],
    },
    'quadratus': {
        'date': ['DatePiece', 'Date'],
        'journal_code': ['CodeJournal', 'Journal'],
        'compte': ['Compte', 'NumeroCompte'],
        'compte_libelle': ['LibelleCompte'],
        'libelle': ['Libelle', 'LibellePiece'],
        'debit': ['Debit', 'MontantDebit'],
        'credit': ['Credit', 'MontantCredit'],
        'piece': ['NumeroPiece', 'Piece'],
    },
    'ebp': {
        'date': ['Date', 'Date écriture'],
        'journal_code': ['Journal', 'Code journal'],
        'compte': ['N° de compte', 'Compte', 'NumCompte'],
        'compte_libelle': ['Libellé compte'],
        'libelle': ['Libellé', 'Intitulé'],
        'debit': ['Débit', 'Montant débit'],
        'credit': ['Crédit', 'Montant crédit'],
        'piece': ['N° pièce', 'Pièce'],
    },
}

# Colonnes requises
REQUIRED_COLUMNS = ['date', 'compte', 'debit', 'credit']
OPTIONAL_COLUMNS = ['journal_code', 'journal_libelle', 'compte_libelle',
                    'auxiliaire', 'analytique', 'libelle', 'piece']


class GLLoader:
    """
    Chargeur de GL multi-format.

    Détecte automatiquement le format et normalise vers le schéma canonique.
    """

    def __init__(self):
        self.detected_format: Optional[str] = None
        self.column_mapping: Optional[ColumnMapping] = None
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def load(self, file_path: str, sheet_name: Optional[str] = None,
             manual_mapping: Optional[Dict[str, str]] = None) -> GLSchema:
        """
        Charge un fichier GL et retourne un GLSchema normalisé.

        Args:
            file_path: Chemin vers le fichier (Excel ou CSV)
            sheet_name: Nom de la feuille Excel (optionnel)
            manual_mapping: Mapping manuel des colonnes (optionnel)

        Returns:
            GLSchema normalisé et validé
        """
        self.warnings = []
        self.errors = []

        # Lecture du fichier
        df = self._read_file(file_path, sheet_name)
        if df is None or df.empty:
            raise ValueError(f"Impossible de lire le fichier: {file_path}")

        # Détection du format et mapping
        if manual_mapping:
            self.column_mapping = self._apply_manual_mapping(manual_mapping)
            self.detected_format = 'manual'
        else:
            self.detected_format, self.column_mapping = self._detect_format(df)

        # Validation des colonnes requises
        missing = self._validate_required_columns(df)
        if missing:
            raise ValueError(f"Colonnes manquantes: {missing}")

        # Extraction de l'analytique si composite
        df = self._extract_analytique_composite(df)

        # Conversion en GLEntry
        entries = self._convert_to_entries(df)

        # Construction du schéma
        schema = GLSchema(
            source_file=str(file_path),
            source_format=self.detected_format or 'unknown',
            date_extraction=date.today(),
            entries=entries,
            colonnes_manquantes=[c for c in OPTIONAL_COLUMNS
                                 if getattr(self.column_mapping, c, None) is None],
        )

        # Calcul des statistiques et validation
        schema.compute_stats()
        schema.validate_equilibre()

        return schema

    def _read_file(self, file_path: str, sheet_name: Optional[str]) -> Optional[pd.DataFrame]:
        """Lit un fichier Excel ou CSV."""
        path = Path(file_path)
        suffix = path.suffix.lower()

        try:
            if suffix in ['.xlsx', '.xls']:
                if sheet_name:
                    df = pd.read_excel(file_path, sheet_name=sheet_name)
                else:
                    # Essaie la première feuille
                    df = pd.read_excel(file_path, sheet_name=0)
            elif suffix == '.csv':
                # Essaie différents séparateurs
                for sep in [';', ',', '\t']:
                    try:
                        df = pd.read_csv(file_path, sep=sep, encoding='utf-8')
                        if len(df.columns) > 3:
                            break
                    except:
                        continue
                else:
                    df = pd.read_csv(file_path)
            else:
                raise ValueError(f"Format de fichier non supporté: {suffix}")

            # Nettoyage des noms de colonnes
            df.columns = [str(c).strip() for c in df.columns]
            return df

        except Exception as e:
            self.errors.append(f"Erreur lecture fichier: {e}")
            return None

    def _detect_format(self, df: pd.DataFrame) -> Tuple[str, ColumnMapping]:
        """
        Détecte le format du GL par fuzzy matching sur les colonnes.

        Returns:
            (format_name, column_mapping)
        """
        columns_lower = {c.lower(): c for c in df.columns}
        best_format = None
        best_score = 0
        best_mapping = None

        for format_name, patterns in FORMAT_PATTERNS.items():
            mapping = ColumnMapping()
            score = 0

            for field, pattern_list in patterns.items():
                for pattern in pattern_list:
                    pattern_lower = pattern.lower()
                    # Match exact ou partiel
                    for col_lower, col_orig in columns_lower.items():
                        if pattern_lower == col_lower or pattern_lower in col_lower:
                            self._set_mapping_field(mapping, field, col_orig)
                            score += 1
                            break

            if score > best_score:
                best_score = score
                best_format = format_name
                best_mapping = mapping

        # Fallback: essaie de matcher les colonnes requises de manière générique
        if best_score < len(REQUIRED_COLUMNS):
            mapping = self._generic_column_detection(df)
            if self._count_mapped_required(mapping) > best_score:
                best_format = 'generic'
                best_mapping = mapping

        return best_format or 'unknown', best_mapping or ColumnMapping()

    def _generic_column_detection(self, df: pd.DataFrame) -> ColumnMapping:
        """Détection générique des colonnes par mots-clés."""
        mapping = ColumnMapping()
        columns_lower = {c.lower(): c for c in df.columns}

        generic_patterns = {
            'date': ['date', 'dt'],
            'compte': ['compte', 'cpt', 'account', 'num'],
            'debit': ['debit', 'débit', 'dt'],
            'credit': ['credit', 'crédit', 'ct', 'cr'],
            'journal_code': ['journal', 'jnl', 'jal'],
            'libelle': ['libelle', 'libellé', 'lib', 'label', 'designation'],
            'piece': ['piece', 'pièce', 'ref', 'num'],
            'analytique': ['analytique', 'ana', 'centre', 'section', 'axe'],
        }

        for field, patterns in generic_patterns.items():
            for pattern in patterns:
                for col_lower, col_orig in columns_lower.items():
                    if pattern in col_lower:
                        self._set_mapping_field(mapping, field, col_orig)
                        break

        return mapping

    def _set_mapping_field(self, mapping: ColumnMapping, field: str, value: str):
        """Définit un champ du mapping."""
        field_map = {
            'date': 'date_ecriture',
            'compte': 'compte_general',
            'compte_libelle': 'compte_libelle',
            'auxiliaire': 'compte_auxiliaire',
            'journal_code': 'journal_code',
            'journal_libelle': 'journal_libelle',
            'libelle': 'libelle_ecriture',
            'debit': 'debit',
            'credit': 'credit',
            'piece': 'piece',
            'analytique': 'analytique',
        }
        attr = field_map.get(field, field)
        if hasattr(mapping, attr) and getattr(mapping, attr) is None:
            setattr(mapping, attr, value)

    def _count_mapped_required(self, mapping: ColumnMapping) -> int:
        """Compte les colonnes requises mappées."""
        count = 0
        if mapping.date_ecriture:
            count += 1
        if mapping.compte_general:
            count += 1
        if mapping.debit:
            count += 1
        if mapping.credit:
            count += 1
        return count

    def _apply_manual_mapping(self, manual: Dict[str, str]) -> ColumnMapping:
        """Applique un mapping manuel."""
        return ColumnMapping(
            date_ecriture=manual.get('date_ecriture') or manual.get('date'),
            journal_code=manual.get('journal_code') or manual.get('journal'),
            journal_libelle=manual.get('journal_libelle'),
            compte_general=manual.get('compte_general') or manual.get('compte'),
            compte_libelle=manual.get('compte_libelle'),
            compte_auxiliaire=manual.get('compte_auxiliaire') or manual.get('auxiliaire'),
            analytique=manual.get('analytique'),
            libelle_ecriture=manual.get('libelle_ecriture') or manual.get('libelle'),
            debit=manual.get('debit'),
            credit=manual.get('credit'),
            piece=manual.get('piece'),
        )

    def _validate_required_columns(self, df: pd.DataFrame) -> List[str]:
        """Valide que les colonnes requises sont présentes."""
        missing = []
        if not self.column_mapping.date_ecriture or \
           self.column_mapping.date_ecriture not in df.columns:
            missing.append('date_ecriture')
        if not self.column_mapping.compte_general or \
           self.column_mapping.compte_general not in df.columns:
            missing.append('compte_general')
        if not self.column_mapping.debit or \
           self.column_mapping.debit not in df.columns:
            missing.append('debit')
        if not self.column_mapping.credit or \
           self.column_mapping.credit not in df.columns:
            missing.append('credit')
        return missing

    def _extract_analytique_composite(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extrait l'analytique depuis un champ composite.

        Exemples:
        - "606320SDV" → compte="606320", analytique="SDV"
        - "606320-SDV" → compte="606320", analytique="SDV"
        """
        if self.column_mapping.analytique and \
           self.column_mapping.analytique in df.columns:
            # Analytique déjà séparé
            return df

        compte_col = self.column_mapping.compte_general
        if not compte_col or compte_col not in df.columns:
            return df

        # Détecte si le compte contient un suffixe analytique
        sample = df[compte_col].dropna().astype(str).head(100)

        # Pattern: chiffres suivis de lettres
        pattern = re.compile(r'^(\d{5,8})([A-Z]{2,5})$')
        matches = sum(1 for v in sample if pattern.match(v))

        if matches > len(sample) * 0.1:  # >10% des comptes ont ce pattern
            # Extraction
            def extract(val):
                val = str(val)
                m = pattern.match(val)
                if m:
                    return m.group(1), m.group(2)
                return val, None

            extracted = df[compte_col].astype(str).apply(extract)
            df['_compte_clean'] = extracted.apply(lambda x: x[0])
            df['_analytique_extracted'] = extracted.apply(lambda x: x[1])

            # Met à jour le mapping
            self.column_mapping.compte_general = '_compte_clean'
            if not self.column_mapping.analytique:
                self.column_mapping.analytique = '_analytique_extracted'

            self.warnings.append(
                "Analytique extrait depuis le compte composite"
            )

        return df

    def _convert_to_entries(self, df: pd.DataFrame) -> List[GLEntry]:
        """Convertit le DataFrame en liste de GLEntry."""
        entries = []
        m = self.column_mapping

        for idx, row in df.iterrows():
            try:
                # Date
                date_val = row[m.date_ecriture]
                if pd.isna(date_val):
                    continue
                if isinstance(date_val, str):
                    date_val = pd.to_datetime(date_val).date()
                elif isinstance(date_val, datetime):
                    date_val = date_val.date()
                elif isinstance(date_val, pd.Timestamp):
                    date_val = date_val.date()

                # Montants
                debit = self._parse_amount(row.get(m.debit, 0))
                credit = self._parse_amount(row.get(m.credit, 0))

                # Skip lignes sans montant
                if debit == 0 and credit == 0:
                    continue

                entry = GLEntry(
                    date_ecriture=date_val,
                    piece=str(row.get(m.piece, '')) if m.piece and pd.notna(row.get(m.piece)) else f"L{idx}",
                    journal_code=str(row.get(m.journal_code, '')) if m.journal_code and pd.notna(row.get(m.journal_code)) else '',
                    journal_libelle=str(row.get(m.journal_libelle, '')) if m.journal_libelle and pd.notna(row.get(m.journal_libelle)) else '',
                    compte_general=str(row[m.compte_general]).strip(),
                    compte_libelle=str(row.get(m.compte_libelle, '')) if m.compte_libelle and pd.notna(row.get(m.compte_libelle)) else '',
                    compte_auxiliaire=str(row.get(m.compte_auxiliaire, '')) if m.compte_auxiliaire and pd.notna(row.get(m.compte_auxiliaire)) else None,
                    analytique=str(row.get(m.analytique, '')) if m.analytique and pd.notna(row.get(m.analytique)) else None,
                    libelle_ecriture=str(row.get(m.libelle_ecriture, '')) if m.libelle_ecriture and pd.notna(row.get(m.libelle_ecriture)) else '',
                    debit=debit,
                    credit=credit,
                    ligne_id=int(idx),
                )
                entries.append(entry)

            except Exception as e:
                self.warnings.append(f"Ligne {idx} ignorée: {e}")
                continue

        return entries

    def _parse_amount(self, value: Any) -> float:
        """Parse un montant depuis différents formats."""
        if pd.isna(value):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # Nettoie le string
            value = value.strip()
            value = value.replace(' ', '')
            value = value.replace('€', '')
            # Gère les formats européens (1.234,56 → 1234.56)
            if ',' in value and '.' in value:
                value = value.replace('.', '').replace(',', '.')
            elif ',' in value:
                value = value.replace(',', '.')
            try:
                return float(value)
            except ValueError:
                return 0.0
        return 0.0

    def get_format_info(self) -> Dict:
        """Retourne les informations sur le format détecté."""
        return {
            'format': self.detected_format,
            'mapping': self.column_mapping.__dict__ if self.column_mapping else None,
            'warnings': self.warnings,
            'errors': self.errors,
        }
