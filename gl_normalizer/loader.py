"""
gl_normalizer/loader.py
Chargement et harmonisation des fichiers GL (Grand Livre)

Supporte plusieurs formats d'export comptable:
- Sage
- Cegid
- Export générique CSV/Excel
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Union, List, Tuple
from datetime import datetime

from .config import COLUMN_MAPPINGS, STANDARD_COLUMNS, COMPUTED_COLUMNS


class GLLoader:
    """
    Chargeur de fichiers GL avec détection automatique du format
    et harmonisation des colonnes.
    """

    def __init__(self, file_path: Union[str, Path]):
        """
        Args:
            file_path: Chemin vers le fichier GL (Excel ou CSV)
        """
        self.file_path = Path(file_path)
        self.raw_df: Optional[pd.DataFrame] = None
        self.df: Optional[pd.DataFrame] = None
        self.detected_format: Optional[str] = None

    def load(self, sheet_name: Union[str, int] = 0) -> pd.DataFrame:
        """
        Charge et harmonise le fichier GL.

        Args:
            sheet_name: Nom ou index de la feuille Excel (si applicable)

        Returns:
            DataFrame harmonisé avec colonnes standardisées
        """
        # Charger le fichier brut
        self.raw_df = self._read_file(sheet_name)

        # Détecter le format
        self.detected_format = self._detect_format()

        # Harmoniser les colonnes
        self.df = self._harmonize_columns()

        # Ajouter les colonnes calculées
        self.df = self._add_computed_columns()

        # Nettoyer les données
        self.df = self._clean_data()

        return self.df

    def _read_file(self, sheet_name: Union[str, int] = 0) -> pd.DataFrame:
        """Lit le fichier selon son extension"""
        suffix = self.file_path.suffix.lower()

        if suffix in [".xlsx", ".xls", ".xlsm"]:
            return pd.read_excel(self.file_path, sheet_name=sheet_name)
        elif suffix == ".csv":
            # Tenter plusieurs encodages et séparateurs
            for encoding in ["utf-8", "latin-1", "cp1252"]:
                for sep in [";", ",", "\t"]:
                    try:
                        df = pd.read_csv(
                            self.file_path,
                            encoding=encoding,
                            sep=sep
                        )
                        if len(df.columns) > 1:
                            return df
                    except Exception:
                        continue
            raise ValueError(f"Impossible de lire le fichier CSV: {self.file_path}")
        else:
            raise ValueError(f"Format non supporté: {suffix}")

    def _detect_format(self) -> str:
        """Détecte automatiquement le format d'export comptable"""
        columns = set(self.raw_df.columns.str.lower())

        # Patterns caractéristiques de chaque format
        sage_patterns = {"n° compte", "code journal", "libellé écriture"}
        cegid_patterns = {"compte", "journal", "libelle"}

        columns_lower = set(col.lower() for col in self.raw_df.columns)

        # Score de correspondance pour chaque format
        for format_name, mapping in COLUMN_MAPPINGS.items():
            expected_cols = set(col.lower() for col in mapping.values())
            match_score = len(expected_cols & columns_lower) / len(expected_cols)
            if match_score > 0.7:
                return format_name

        # Fallback sur generic
        return "generic"

    def _harmonize_columns(self) -> pd.DataFrame:
        """Harmonise les noms de colonnes selon le format détecté"""
        df = self.raw_df.copy()

        # Récupérer le mapping pour ce format
        mapping = COLUMN_MAPPINGS.get(self.detected_format, COLUMN_MAPPINGS["generic"])

        # Créer le mapping inversé (colonne source -> colonne standard)
        col_rename = {}
        for std_name, source_name in mapping.items():
            # Chercher la colonne (case insensitive)
            for col in df.columns:
                if col.lower() == source_name.lower():
                    col_rename[col] = std_name
                    break

        # Renommer
        df = df.rename(columns=col_rename)

        # S'assurer que toutes les colonnes standard existent
        for col in STANDARD_COLUMNS:
            if col not in df.columns:
                df[col] = np.nan

        return df

    def _add_computed_columns(self) -> pd.DataFrame:
        """Ajoute les colonnes calculées"""
        df = self.df.copy()

        # Convertir la date
        df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)

        # Extraire période, année, mois
        df["annee"] = df["date"].dt.year
        df["mois"] = df["date"].dt.month
        df["periode"] = df["date"].dt.strftime("%Y-%m")

        # Extraire classe et racines du compte
        df["compte"] = df["compte"].astype(str).str.strip()
        df["classe"] = df["compte"].str[0]
        df["racine_2"] = df["compte"].str[:2]
        df["racine_3"] = df["compte"].str[:3]

        # Calculer le montant signé (débit - crédit)
        df["debit"] = pd.to_numeric(df["debit"], errors="coerce").fillna(0)
        df["credit"] = pd.to_numeric(df["credit"], errors="coerce").fillna(0)
        df["montant"] = df["debit"] - df["credit"]

        return df

    def _clean_data(self) -> pd.DataFrame:
        """Nettoie les données"""
        df = self.df.copy()

        # Supprimer les lignes sans compte
        df = df[df["compte"].notna() & (df["compte"] != "")]

        # Supprimer les lignes sans montant
        df = df[(df["debit"] != 0) | (df["credit"] != 0)]

        # Nettoyer les libellés
        if "libelle" in df.columns:
            df["libelle"] = df["libelle"].fillna("").astype(str).str.strip()

        # Normaliser le journal
        if "journal" in df.columns:
            df["journal"] = df["journal"].fillna("").astype(str).str.upper().str.strip()

        return df

    def get_summary(self) -> dict:
        """Retourne un résumé du GL chargé"""
        if self.df is None:
            return {"error": "Aucun fichier chargé"}

        return {
            "fichier": str(self.file_path),
            "format_detecte": self.detected_format,
            "nb_ecritures": len(self.df),
            "periode": f"{self.df['periode'].min()} à {self.df['periode'].max()}",
            "nb_comptes": self.df["compte"].nunique(),
            "total_debit": self.df["debit"].sum(),
            "total_credit": self.df["credit"].sum(),
            "equilibre": abs(self.df["debit"].sum() - self.df["credit"].sum()) < 0.01,
            "journaux": sorted(self.df["journal"].unique().tolist()),
        }


def load_gl(
    file_path: Union[str, Path],
    sheet_name: Union[str, int] = 0
) -> pd.DataFrame:
    """
    Fonction utilitaire pour charger rapidement un GL.

    Args:
        file_path: Chemin vers le fichier
        sheet_name: Feuille Excel à charger

    Returns:
        DataFrame harmonisé
    """
    loader = GLLoader(file_path)
    return loader.load(sheet_name)


def load_multiple_gl(
    file_paths: List[Union[str, Path]],
    labels: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    Charge et concatène plusieurs fichiers GL.

    Args:
        file_paths: Liste des chemins de fichiers
        labels: Labels pour identifier chaque fichier (optionnel)

    Returns:
        DataFrame unique avec colonne 'source' identifiant l'origine
    """
    dfs = []

    for i, path in enumerate(file_paths):
        df = load_gl(path)
        df["source"] = labels[i] if labels and i < len(labels) else Path(path).stem
        dfs.append(df)

    return pd.concat(dfs, ignore_index=True)


if __name__ == "__main__":
    print("GLLoader - Chargement et harmonisation des fichiers GL")
    print("Usage:")
    print("  from gl_normalizer.loader import GLLoader, load_gl")
    print("  df = load_gl('mon_fichier_gl.xlsx')")
