"""
GLLoader - Chargement et normalisation du Grand Livre
=====================================================

STORY-201: Charge les exports GL Excel et normalise vers un schéma standard.

Formats supportés: Sage, Cegid, Quadratus, EBP, Excel générique.
"""

import pandas as pd
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
from enum import Enum


class GLFormat(Enum):
    """Formats de GL supportés."""
    SAGE = "sage"
    CEGID = "cegid"
    QUADRATUS = "quadratus"
    EBP = "ebp"
    GENERIC = "generic"
    UNKNOWN = "unknown"


@dataclass
class LoadResult:
    """Résultat du chargement."""
    df: pd.DataFrame
    format_detected: GLFormat
    rows_count: int
    columns_original: List[str]
    warnings: List[str]


# Colonnes standard après normalisation
STANDARD_COLUMNS = [
    "compte",      # str: numéro de compte (ex: "601000")
    "date",        # datetime: date de l'écriture
    "mois",        # int: mois (1-12)
    "annee",       # int: année
    "libelle",     # str: libellé de l'écriture
    "journal",     # str: code journal (ex: "OD", "ACH")
    "debit",       # float: montant débit
    "credit",      # float: montant crédit
    "montant",     # float: montant signé (debit - credit)
]

# Patterns de colonnes par format
FORMAT_PATTERNS = {
    GLFormat.SAGE: {
        "compte": ["Compte", "N° Compte", "Numéro de compte", "CompteNum"],
        "date": ["Date", "Date écriture", "DateEcriture"],
        "libelle": ["Libellé", "Libelle", "LibelleEcriture"],
        "journal": ["Journal", "Code Journal", "JournalCode"],
        "debit": ["Débit", "Debit", "MontantDebit"],
        "credit": ["Crédit", "Credit", "MontantCredit"],
    },
    GLFormat.CEGID: {
        "compte": ["COMPTE", "NUMCOMPTE", "NUM_COMPTE"],
        "date": ["DATE", "DATECPT", "DATE_PIECE"],
        "libelle": ["LIBELLE", "LIB", "LIBECR"],
        "journal": ["JOURNAL", "JNL", "CODE_JOURNAL"],
        "debit": ["DEBIT", "MT_DEBIT", "MONTANT_DEBIT"],
        "credit": ["CREDIT", "MT_CREDIT", "MONTANT_CREDIT"],
    },
    GLFormat.QUADRATUS: {
        "compte": ["Compte", "NumCpte", "N°Compte"],
        "date": ["Date", "DatePiece"],
        "libelle": ["Libellé", "Libelle"],
        "journal": ["Journal", "Jal"],
        "debit": ["Débit", "Debit"],
        "credit": ["Crédit", "Credit"],
    },
    GLFormat.EBP: {
        "compte": ["Compte", "N° de compte"],
        "date": ["Date"],
        "libelle": ["Libellé"],
        "journal": ["Journal"],
        "debit": ["Débit"],
        "credit": ["Crédit"],
    },
}


class GLLoader:
    """
    Charge et normalise les exports Grand Livre.

    Usage:
        loader = GLLoader()
        result = loader.load("mon_gl.xlsx")
        df = result.df  # DataFrame normalisé
    """

    def __init__(self, custom_mapping: Optional[Dict[str, str]] = None):
        """
        Args:
            custom_mapping: Mapping personnalisé colonne_source → colonne_standard
        """
        self.custom_mapping = custom_mapping or {}

    def load(self, filepath: str, sheet_name: Optional[str] = None) -> LoadResult:
        """
        Charge un fichier GL Excel et normalise les colonnes.

        Args:
            filepath: Chemin vers le fichier Excel
            sheet_name: Nom de la feuille (None = première feuille)

        Returns:
            LoadResult avec DataFrame normalisé
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Fichier non trouvé: {filepath}")

        # Charger le fichier
        df_raw = self._read_excel(path, sheet_name)
        columns_original = list(df_raw.columns)

        # Détecter le format
        format_detected = self._detect_format(df_raw)

        # Normaliser les colonnes
        df_normalized = self._normalize_columns(df_raw, format_detected)

        # Valider et enrichir
        df_final, warnings = self._validate_and_enrich(df_normalized)

        return LoadResult(
            df=df_final,
            format_detected=format_detected,
            rows_count=len(df_final),
            columns_original=columns_original,
            warnings=warnings,
        )

    def _read_excel(self, path: Path, sheet_name: Optional[str]) -> pd.DataFrame:
        """Lit le fichier Excel."""
        suffix = path.suffix.lower()

        if suffix == ".xlsx":
            engine = "openpyxl"
        elif suffix == ".xls":
            engine = "xlrd"
        else:
            # Tenter openpyxl par défaut
            engine = "openpyxl"

        try:
            df = pd.read_excel(
                path,
                sheet_name=sheet_name or 0,
                engine=engine,
                dtype=str,  # Tout en string d'abord
            )
        except Exception as e:
            raise ValueError(f"Erreur lecture Excel: {e}")

        return df

    def _detect_format(self, df: pd.DataFrame) -> GLFormat:
        """Détecte le format du GL basé sur les noms de colonnes."""
        columns = [str(c).strip().upper() for c in df.columns]

        # Compter les correspondances par format
        scores = {}
        for fmt, patterns in FORMAT_PATTERNS.items():
            score = 0
            for std_col, variants in patterns.items():
                for variant in variants:
                    if variant.upper() in columns:
                        score += 1
                        break
            scores[fmt] = score

        # Le format avec le meilleur score
        best_format = max(scores, key=scores.get)

        if scores[best_format] >= 4:  # Au moins 4 colonnes reconnues
            return best_format
        else:
            return GLFormat.GENERIC

    def _normalize_columns(self, df: pd.DataFrame, fmt: GLFormat) -> pd.DataFrame:
        """Normalise les colonnes vers le schéma standard."""
        df = df.copy()

        # Créer le mapping
        mapping = {}

        # D'abord le custom mapping (prioritaire)
        mapping.update(self.custom_mapping)

        # Puis le mapping du format détecté
        if fmt in FORMAT_PATTERNS:
            for std_col, variants in FORMAT_PATTERNS[fmt].items():
                for variant in variants:
                    for col in df.columns:
                        if str(col).strip().upper() == variant.upper():
                            if std_col not in mapping.values():
                                mapping[col] = std_col
                            break

        # Appliquer le mapping (renommer les colonnes trouvées)
        df = df.rename(columns=mapping)

        # Vérifier les colonnes obligatoires
        required = ["compte", "date", "libelle", "journal"]
        missing = [c for c in required if c not in df.columns]

        if missing:
            # Tenter un mapping générique
            df = self._generic_mapping(df, missing)

        return df

    def _generic_mapping(self, df: pd.DataFrame, missing: List[str]) -> pd.DataFrame:
        """Mapping générique pour colonnes manquantes."""
        columns_lower = {str(c).lower(): c for c in df.columns}

        generic_patterns = {
            "compte": ["compte", "account", "cpt", "num"],
            "date": ["date", "dt"],
            "libelle": ["libelle", "label", "description", "lib"],
            "journal": ["journal", "jnl", "jal"],
            "debit": ["debit", "deb", "dt"],
            "credit": ["credit", "cred", "ct"],
        }

        for col in missing:
            if col in generic_patterns:
                for pattern in generic_patterns[col]:
                    for col_lower, col_orig in columns_lower.items():
                        if pattern in col_lower and col not in df.columns:
                            df = df.rename(columns={col_orig: col})
                            break

        return df

    def _validate_and_enrich(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """Valide et enrichit le DataFrame."""
        warnings = []
        df = df.copy()

        # Vérifier colonnes obligatoires
        required = ["compte", "date"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Colonne obligatoire manquante: {col}")

        # Nettoyer compte
        df["compte"] = df["compte"].astype(str).str.strip()
        df = df[df["compte"].notna() & (df["compte"] != "") & (df["compte"] != "nan")]

        # Parser date
        df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)
        invalid_dates = df["date"].isna().sum()
        if invalid_dates > 0:
            warnings.append(f"{invalid_dates} lignes avec date invalide (ignorées)")
            df = df[df["date"].notna()]

        # Extraire mois et année
        df["mois"] = df["date"].dt.month
        df["annee"] = df["date"].dt.year

        # Nettoyer libellé
        if "libelle" not in df.columns:
            df["libelle"] = ""
            warnings.append("Colonne libelle absente, ajoutée vide")
        df["libelle"] = df["libelle"].fillna("").astype(str)

        # Nettoyer journal
        if "journal" not in df.columns:
            df["journal"] = "OD"
            warnings.append("Colonne journal absente, défaut 'OD'")
        df["journal"] = df["journal"].fillna("OD").astype(str).str.strip().str.upper()

        # Nettoyer debit/credit
        for col in ["debit", "credit"]:
            if col not in df.columns:
                df[col] = 0.0
            else:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace(",", ".").str.replace(" ", ""),
                    errors="coerce"
                ).fillna(0.0)

        # Calculer montant signé (debit - credit pour les charges)
        df["montant"] = df["debit"] - df["credit"]

        # Réordonner les colonnes
        final_cols = [c for c in STANDARD_COLUMNS if c in df.columns]
        extra_cols = [c for c in df.columns if c not in STANDARD_COLUMNS]
        df = df[final_cols + extra_cols]

        # Reset index
        df = df.reset_index(drop=True)

        return df, warnings

    def get_summary(self, df: pd.DataFrame) -> Dict:
        """Retourne un résumé du GL chargé."""
        return {
            "rows": len(df),
            "accounts": df["compte"].nunique(),
            "journals": df["journal"].nunique(),
            "date_min": df["date"].min().strftime("%Y-%m-%d") if len(df) > 0 else None,
            "date_max": df["date"].max().strftime("%Y-%m-%d") if len(df) > 0 else None,
            "total_debit": df["debit"].sum(),
            "total_credit": df["credit"].sum(),
            "journals_list": sorted(df["journal"].unique().tolist()),
        }
