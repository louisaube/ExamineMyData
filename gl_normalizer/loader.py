"""
gl_normalizer/loader.py
Chargement et harmonisation des fichiers GL (Grand Livre)

Supporte plusieurs formats d'export comptable:
- Sage
- Cegid
- Quadratus
- EBP
- Export générique CSV/Excel

Fonctionnalités:
- Détection automatique du format
- Validation des headers avec suggestions
- Support des colonnes analytiques
"""

import pandas as pd
import numpy as np
import logging
from pathlib import Path
from typing import Optional, Union, List, Dict, Tuple
from datetime import datetime
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

from .config import (
    COLUMN_MAPPINGS,
    STANDARD_COLUMNS,
    STANDARD_ANALYTICAL_COLUMNS,
    REQUIRED_COLUMNS,
    OPTIONAL_COLUMNS,
    HeaderValidation,
    ColumnMapping,
)


class HeaderValidator:
    """
    Validateur de headers avec détection automatique et suggestions.

    Permet de:
    - Détecter le format du fichier (Sage, Cegid, etc.)
    - Valider que les colonnes requises sont présentes
    - Suggérer des mappings pour les colonnes non reconnues
    - Identifier les colonnes analytiques
    """

    def __init__(self, columns: List[str]):
        """
        Args:
            columns: Liste des noms de colonnes du fichier source
        """
        self.source_columns = columns
        self.source_columns_lower = {col.lower(): col for col in columns}

    def validate(self) -> HeaderValidation:
        """
        Valide les headers et retourne le résultat.

        Returns:
            HeaderValidation avec tous les détails du mapping
        """
        # Détecter le format
        detected_format, format_score = self._detect_format()

        # Construire les mappings
        mappings = self._build_mappings(detected_format)

        # Identifier les colonnes mappées et non mappées
        mapped_source_cols = {m.source_name for m in mappings}
        unmapped = [col for col in self.source_columns if col not in mapped_source_cols]

        # Vérifier les colonnes requises
        mapped_standard = {m.standard_name for m in mappings}
        missing_required = [col for col in REQUIRED_COLUMNS if col not in mapped_standard]

        # Suggestions pour les colonnes manquantes
        suggestions = {}
        for missing in missing_required:
            suggestions[missing] = self._suggest_columns(missing, unmapped)

        # Colonnes analytiques trouvées
        analytical_found = [
            m.source_name for m in mappings
            if m.is_analytical
        ]

        return HeaderValidation(
            is_valid=len(missing_required) == 0,
            detected_format=detected_format,
            mappings=mappings,
            missing_required=missing_required,
            unmapped_columns=unmapped,
            suggestions=suggestions,
            analytical_columns_found=analytical_found,
        )

    def _detect_format(self) -> Tuple[str, float]:
        """Détecte le format d'export comptable"""
        best_format = "generic"
        best_score = 0

        for format_name, mapping in COLUMN_MAPPINGS.items():
            score = self._compute_format_score(mapping)
            if score > best_score:
                best_score = score
                best_format = format_name

        return best_format, best_score

    def _compute_format_score(self, mapping: Dict[str, List[str]]) -> float:
        """Calcule un score de correspondance pour un format"""
        matches = 0
        total = 0

        for standard_name, possible_names in mapping.items():
            if standard_name in REQUIRED_COLUMNS:
                total += 2  # Poids double pour colonnes requises
            else:
                total += 1

            for possible in possible_names:
                if possible.lower() in self.source_columns_lower:
                    if standard_name in REQUIRED_COLUMNS:
                        matches += 2
                    else:
                        matches += 1
                    break

        return matches / total if total > 0 else 0

    def _build_mappings(self, format_name: str) -> List[ColumnMapping]:
        """Construit les mappings pour le format détecté"""
        mappings = []
        mapping_dict = COLUMN_MAPPINGS.get(format_name, COLUMN_MAPPINGS["generic"])
        used_source_cols = set()

        for standard_name, possible_names in mapping_dict.items():
            for possible in possible_names:
                if possible.lower() in self.source_columns_lower:
                    source_col = self.source_columns_lower[possible.lower()]
                    if source_col not in used_source_cols:
                        mappings.append(ColumnMapping(
                            standard_name=standard_name,
                            source_name=source_col,
                            is_required=standard_name in REQUIRED_COLUMNS,
                            is_analytical=standard_name in STANDARD_ANALYTICAL_COLUMNS,
                            confidence=1.0,
                        ))
                        used_source_cols.add(source_col)
                        break

        # Essayer de trouver des mappings par similarité pour les colonnes manquantes
        mapped_standards = {m.standard_name for m in mappings}
        all_standards = REQUIRED_COLUMNS + OPTIONAL_COLUMNS + STANDARD_ANALYTICAL_COLUMNS

        for standard_name in all_standards:
            if standard_name not in mapped_standards:
                best_match, score = self._find_similar_column(standard_name, used_source_cols)
                if best_match and score > 0.6:
                    mappings.append(ColumnMapping(
                        standard_name=standard_name,
                        source_name=best_match,
                        is_required=standard_name in REQUIRED_COLUMNS,
                        is_analytical=standard_name in STANDARD_ANALYTICAL_COLUMNS,
                        confidence=score,
                    ))
                    used_source_cols.add(best_match)

        return mappings

    def _find_similar_column(
        self,
        target: str,
        exclude: set
    ) -> Tuple[Optional[str], float]:
        """Trouve la colonne source la plus similaire"""
        best_match = None
        best_score = 0

        for col in self.source_columns:
            if col in exclude:
                continue

            # Score de similarité
            score = SequenceMatcher(None, target.lower(), col.lower()).ratio()

            # Bonus si contient le mot clé
            if target.lower() in col.lower() or col.lower() in target.lower():
                score += 0.3

            if score > best_score:
                best_score = score
                best_match = col

        return best_match, min(best_score, 1.0)

    def _suggest_columns(self, missing: str, candidates: List[str]) -> List[str]:
        """Suggère des colonnes candidates pour un mapping manquant"""
        scores = []
        for col in candidates:
            score = SequenceMatcher(None, missing.lower(), col.lower()).ratio()
            if missing.lower() in col.lower():
                score += 0.3
            scores.append((col, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [col for col, score in scores[:5] if score > 0.3]


class GLLoader:
    """
    Chargeur de fichiers GL avec détection automatique du format,
    validation des headers et support analytique.
    """

    def __init__(self, file_path: Union[str, Path]):
        """
        Args:
            file_path: Chemin vers le fichier GL (Excel ou CSV)
        """
        self.file_path = Path(file_path)
        self.raw_df: Optional[pd.DataFrame] = None
        self.df: Optional[pd.DataFrame] = None
        self.validation: Optional[HeaderValidation] = None

    def validate_headers(self, sheet_name: Union[str, int] = 0) -> HeaderValidation:
        """
        Valide les headers du fichier sans charger toutes les données.

        Args:
            sheet_name: Feuille Excel à analyser

        Returns:
            HeaderValidation avec résultat et suggestions
        """
        # Lire seulement les headers (première ligne)
        if self.raw_df is None:
            self.raw_df = self._read_file(sheet_name)

        validator = HeaderValidator(list(self.raw_df.columns))
        self.validation = validator.validate()

        return self.validation

    def load(
        self,
        sheet_name: Union[str, int] = 0,
        custom_mapping: Optional[Dict[str, str]] = None,
        validate: bool = True,
    ) -> pd.DataFrame:
        """
        Charge et harmonise le fichier GL.

        Args:
            sheet_name: Nom ou index de la feuille Excel
            custom_mapping: Mapping personnalisé {colonne_source: colonne_standard}
            validate: Valider les headers avant chargement

        Returns:
            DataFrame harmonisé avec colonnes standardisées

        Raises:
            ValueError: Si validation échoue et colonnes requises manquantes
        """
        # Charger le fichier brut
        if self.raw_df is None:
            self.raw_df = self._read_file(sheet_name)

        # Valider les headers
        if validate and self.validation is None:
            self.validate_headers(sheet_name)

        # Appliquer le mapping personnalisé si fourni
        if custom_mapping:
            self.df = self._apply_custom_mapping(custom_mapping)
        elif self.validation:
            if not self.validation.is_valid:
                missing = ", ".join(self.validation.missing_required)
                raise ValueError(
                    f"Colonnes requises manquantes: {missing}\n"
                    f"Utilisez validate_headers() pour voir les suggestions."
                )
            self.df = self._apply_validation_mapping()
        else:
            self.df = self._apply_auto_mapping()

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

    def _apply_validation_mapping(self) -> pd.DataFrame:
        """Applique le mapping issu de la validation"""
        df = self.raw_df.copy()

        # Créer le dictionnaire de renommage
        rename_dict = {}
        for mapping in self.validation.mappings:
            rename_dict[mapping.source_name] = mapping.standard_name

        df = df.rename(columns=rename_dict)

        # S'assurer que toutes les colonnes standard existent
        all_cols = STANDARD_COLUMNS + STANDARD_ANALYTICAL_COLUMNS
        for col in all_cols:
            if col not in df.columns:
                df[col] = np.nan

        return df

    def _apply_custom_mapping(self, mapping: Dict[str, str]) -> pd.DataFrame:
        """Applique un mapping personnalisé"""
        df = self.raw_df.copy()
        df = df.rename(columns=mapping)

        for col in STANDARD_COLUMNS:
            if col not in df.columns:
                df[col] = np.nan

        return df

    def _apply_auto_mapping(self) -> pd.DataFrame:
        """Applique un mapping automatique basé sur la détection"""
        validator = HeaderValidator(list(self.raw_df.columns))
        validation = validator.validate()
        self.validation = validation

        return self._apply_validation_mapping()

    def _add_computed_columns(self) -> pd.DataFrame:
        """Ajoute les colonnes calculées"""
        df = self.df.copy()

        # Convertir la date avec logging des erreurs
        dates_avant = df["date"].notna().sum()
        df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)
        dates_invalides = dates_avant - df["date"].notna().sum()
        if dates_invalides > 0:
            logger.warning(f"{dates_invalides} dates invalides converties en NaT")

        # Extraire période, année, mois
        df["annee"] = df["date"].dt.year
        df["mois"] = df["date"].dt.month
        df["periode"] = df["date"].dt.strftime("%Y-%m")

        # Extraire classe et racines du compte
        df["compte"] = df["compte"].astype(str).str.strip()
        df["classe"] = df["compte"].str[0]
        df["racine_2"] = df["compte"].str[:2]
        df["racine_3"] = df["compte"].str[:3]

        # Calculer le montant signé (débit - crédit) avec logging
        debit_avant = df["debit"].notna().sum()
        df["debit"] = pd.to_numeric(df["debit"], errors="coerce").fillna(0)
        debit_invalides = debit_avant - (df["debit"] != 0).sum()

        credit_avant = df["credit"].notna().sum()
        df["credit"] = pd.to_numeric(df["credit"], errors="coerce").fillna(0)
        credit_invalides = credit_avant - (df["credit"] != 0).sum()

        if debit_invalides > 0 or credit_invalides > 0:
            logger.warning(f"Montants non numériques: {debit_invalides} débits, {credit_invalides} crédits")

        df["montant"] = df["debit"] - df["credit"]

        # Normaliser les colonnes analytiques
        for axe in STANDARD_ANALYTICAL_COLUMNS:
            if axe in df.columns:
                df[axe] = df[axe].fillna("").astype(str).str.strip()
                # Remplacer les valeurs vides par NaN pour filtrage ultérieur
                df[axe] = df[axe].replace("", np.nan)

        return df

    def _clean_data(self) -> pd.DataFrame:
        """Nettoie les données"""
        df = self.df.copy()

        # Supprimer les lignes sans compte
        df = df[df["compte"].notna() & (df["compte"] != "") & (df["compte"] != "nan")]

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

        summary = {
            "fichier": str(self.file_path),
            "format_detecte": self.validation.detected_format if self.validation else "auto",
            "nb_ecritures": len(self.df),
            "periode": f"{self.df['periode'].min()} à {self.df['periode'].max()}",
            "nb_comptes": self.df["compte"].nunique(),
            "total_debit": self.df["debit"].sum(),
            "total_credit": self.df["credit"].sum(),
            "equilibre": abs(self.df["debit"].sum() - self.df["credit"].sum()) < 0.01,
            "journaux": sorted(self.df["journal"].dropna().unique().tolist()),
        }

        # Ajouter info analytique
        for axe in STANDARD_ANALYTICAL_COLUMNS:
            if axe in self.df.columns and self.df[axe].notna().any():
                summary[f"nb_{axe}"] = self.df[axe].nunique()
                summary[f"valeurs_{axe}"] = sorted(self.df[axe].dropna().unique().tolist()[:20])

        return summary

    def get_analytical_axes(self) -> Dict[str, List[str]]:
        """Retourne les axes analytiques et leurs valeurs"""
        if self.df is None:
            return {}

        axes = {}
        for axe in STANDARD_ANALYTICAL_COLUMNS:
            if axe in self.df.columns and self.df[axe].notna().any():
                axes[axe] = sorted(self.df[axe].dropna().unique().tolist())

        return axes


def validate_gl_headers(
    file_path: Union[str, Path],
    sheet_name: Union[str, int] = 0
) -> HeaderValidation:
    """
    Valide les headers d'un fichier GL.

    Args:
        file_path: Chemin du fichier
        sheet_name: Feuille Excel

    Returns:
        HeaderValidation avec détails et suggestions
    """
    loader = GLLoader(file_path)
    return loader.validate_headers(sheet_name)


def load_gl(
    file_path: Union[str, Path],
    sheet_name: Union[str, int] = 0,
    custom_mapping: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """
    Charge et harmonise un fichier GL.

    Args:
        file_path: Chemin vers le fichier
        sheet_name: Feuille Excel à charger
        custom_mapping: Mapping personnalisé optionnel

    Returns:
        DataFrame harmonisé
    """
    loader = GLLoader(file_path)
    return loader.load(sheet_name, custom_mapping)


def load_multiple_gl(
    file_paths: List[Union[str, Path]],
    labels: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    Charge et concatène plusieurs fichiers GL.

    Args:
        file_paths: Liste des chemins de fichiers
        labels: Labels pour identifier chaque fichier

    Returns:
        DataFrame unique avec colonne 'source'
    """
    dfs = []

    for i, path in enumerate(file_paths):
        df = load_gl(path)
        df["source"] = labels[i] if labels and i < len(labels) else Path(path).stem
        dfs.append(df)

    return pd.concat(dfs, ignore_index=True)


if __name__ == "__main__":
    print("GLLoader - Chargement et harmonisation des fichiers GL")
    print("")
    print("Validation des headers:")
    print("  from gl_normalizer.loader import validate_gl_headers")
    print("  validation = validate_gl_headers('mon_gl.xlsx')")
    print("  print(validation.summary())")
    print("")
    print("Chargement:")
    print("  from gl_normalizer.loader import load_gl")
    print("  df = load_gl('mon_gl.xlsx')")
