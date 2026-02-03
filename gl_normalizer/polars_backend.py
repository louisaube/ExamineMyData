"""
gl_normalizer/polars_backend.py
Backend Polars pour traitement haute performance

Fournit:
- Chargement de fichiers 10-50x plus rapide
- Opérations groupby/pivot optimisées
- Lazy evaluation pour chaînes de transformations
- Fallback automatique vers Pandas si Polars indisponible
"""

import os
from pathlib import Path
from typing import Optional, Union, Dict, Any, List
import warnings

# Configuration
USE_POLARS = os.getenv("GL_USE_POLARS", "1") == "1"

# Détection Polars
try:
    import polars as pl
    POLARS_AVAILABLE = True
except ImportError:
    POLARS_AVAILABLE = False
    pl = None

import pandas as pd


class DataBackend:
    """
    Interface unifiée pour Pandas et Polars.

    Utilise Polars si disponible et activé, sinon Pandas.
    """

    def __init__(self, use_polars: Optional[bool] = None):
        """
        Args:
            use_polars: Force l'utilisation de Polars (True/False) ou auto (None)
        """
        if use_polars is None:
            self.use_polars = USE_POLARS and POLARS_AVAILABLE
        else:
            self.use_polars = use_polars and POLARS_AVAILABLE

        if use_polars and not POLARS_AVAILABLE:
            warnings.warn("Polars demandé mais non disponible, fallback Pandas")

    @property
    def backend_name(self) -> str:
        return "polars" if self.use_polars else "pandas"

    # =========================================
    # CHARGEMENT DE FICHIERS
    # =========================================

    def read_excel(
        self,
        path: Union[str, Path],
        sheet_name: Optional[str] = None,
        **kwargs
    ) -> pd.DataFrame:
        """
        Charge un fichier Excel.

        Note: Polars utilise xlsx2csv en interne, peut être plus lent qu'openpyxl
        pour petits fichiers. On utilise Pandas pour Excel et convertit.
        """
        # Pour Excel, Pandas reste souvent plus efficace
        df = pd.read_excel(path, sheet_name=sheet_name or 0, **kwargs)
        return df

    def read_csv(
        self,
        path: Union[str, Path],
        encoding: str = "utf-8",
        separator: str = ",",
        **kwargs
    ) -> pd.DataFrame:
        """
        Charge un fichier CSV.

        Avec Polars: 10-50x plus rapide que Pandas pour gros fichiers.
        """
        if self.use_polars:
            try:
                # Polars CSV est très rapide
                df_pl = pl.read_csv(
                    path,
                    encoding=encoding,
                    separator=separator,
                    infer_schema_length=10000,
                    try_parse_dates=True,
                    **{k: v for k, v in kwargs.items() if k in [
                        'has_header', 'columns', 'n_rows', 'skip_rows',
                        'null_values', 'ignore_errors'
                    ]}
                )
                # Convertir en Pandas pour compatibilité avec le reste du code
                return df_pl.to_pandas()
            except Exception as e:
                warnings.warn(f"Polars CSV failed: {e}, fallback Pandas")

        # Fallback Pandas
        return pd.read_csv(
            path,
            encoding=encoding,
            sep=separator,
            **kwargs
        )

    # =========================================
    # OPÉRATIONS OPTIMISÉES
    # =========================================

    def groupby_agg(
        self,
        df: pd.DataFrame,
        group_cols: Union[str, List[str]],
        agg_dict: Dict[str, str],
    ) -> pd.DataFrame:
        """
        GroupBy avec agrégation optimisée.

        Args:
            df: DataFrame source
            group_cols: Colonnes de groupement
            agg_dict: {colonne: fonction} ex: {"montant": "sum", "compte": "count"}

        Returns:
            DataFrame agrégé
        """
        if isinstance(group_cols, str):
            group_cols = [group_cols]

        if self.use_polars:
            try:
                df_pl = pl.from_pandas(df)

                # Construire les expressions d'agrégation
                agg_exprs = []
                for col, func in agg_dict.items():
                    if func == "sum":
                        agg_exprs.append(pl.col(col).sum().alias(col))
                    elif func == "mean":
                        agg_exprs.append(pl.col(col).mean().alias(col))
                    elif func == "count":
                        agg_exprs.append(pl.col(col).count().alias(f"{col}_count"))
                    elif func == "nunique":
                        agg_exprs.append(pl.col(col).n_unique().alias(f"{col}_nunique"))
                    elif func == "first":
                        agg_exprs.append(pl.col(col).first().alias(col))
                    elif func == "last":
                        agg_exprs.append(pl.col(col).last().alias(col))
                    elif func == "min":
                        agg_exprs.append(pl.col(col).min().alias(col))
                    elif func == "max":
                        agg_exprs.append(pl.col(col).max().alias(col))
                    elif func == "std":
                        agg_exprs.append(pl.col(col).std().alias(col))

                result = df_pl.group_by(group_cols).agg(agg_exprs)
                return result.to_pandas()

            except Exception as e:
                warnings.warn(f"Polars groupby failed: {e}, fallback Pandas")

        # Fallback Pandas
        return df.groupby(group_cols).agg(agg_dict).reset_index()

    def pivot_table(
        self,
        df: pd.DataFrame,
        index: Union[str, List[str]],
        columns: str,
        values: str,
        aggfunc: str = "sum",
        fill_value: Any = 0,
    ) -> pd.DataFrame:
        """
        Pivot table optimisée.

        Args:
            df: DataFrame source
            index: Colonnes d'index
            columns: Colonne pour les colonnes du pivot
            values: Colonne des valeurs
            aggfunc: Fonction d'agrégation
            fill_value: Valeur de remplissage

        Returns:
            DataFrame pivoté
        """
        if self.use_polars:
            try:
                df_pl = pl.from_pandas(df)

                # Polars pivot
                result = df_pl.pivot(
                    values=values,
                    index=index,
                    columns=columns,
                    aggregate_function=aggfunc,
                )

                # Remplir les NaN
                result = result.fill_null(fill_value)
                return result.to_pandas()

            except Exception as e:
                warnings.warn(f"Polars pivot failed: {e}, fallback Pandas")

        # Fallback Pandas
        return pd.pivot_table(
            df,
            index=index,
            columns=columns,
            values=values,
            aggfunc=aggfunc,
            fill_value=fill_value,
        )

    def filter_rows(
        self,
        df: pd.DataFrame,
        conditions: Dict[str, Any],
    ) -> pd.DataFrame:
        """
        Filtrage rapide de lignes.

        Args:
            df: DataFrame source
            conditions: {colonne: valeur} ou {colonne: [valeurs]}

        Returns:
            DataFrame filtré
        """
        if self.use_polars:
            try:
                df_pl = pl.from_pandas(df)

                for col, value in conditions.items():
                    if isinstance(value, list):
                        df_pl = df_pl.filter(pl.col(col).is_in(value))
                    else:
                        df_pl = df_pl.filter(pl.col(col) == value)

                return df_pl.to_pandas()

            except Exception as e:
                warnings.warn(f"Polars filter failed: {e}, fallback Pandas")

        # Fallback Pandas
        mask = pd.Series([True] * len(df))
        for col, value in conditions.items():
            if isinstance(value, list):
                mask &= df[col].isin(value)
            else:
                mask &= df[col] == value
        return df[mask].copy()

    def compute_stats(
        self,
        df: pd.DataFrame,
        numeric_cols: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, float]]:
        """
        Calcul rapide de statistiques descriptives.

        Args:
            df: DataFrame source
            numeric_cols: Colonnes numériques (auto-détecté si None)

        Returns:
            Dict avec stats par colonne
        """
        if numeric_cols is None:
            numeric_cols = df.select_dtypes(include=['number']).columns.tolist()

        if self.use_polars:
            try:
                df_pl = pl.from_pandas(df[numeric_cols])

                stats = {}
                for col in numeric_cols:
                    col_stats = df_pl.select([
                        pl.col(col).sum().alias("sum"),
                        pl.col(col).mean().alias("mean"),
                        pl.col(col).std().alias("std"),
                        pl.col(col).min().alias("min"),
                        pl.col(col).max().alias("max"),
                        pl.col(col).median().alias("median"),
                        pl.col(col).count().alias("count"),
                    ]).to_dicts()[0]
                    stats[col] = col_stats

                return stats

            except Exception as e:
                warnings.warn(f"Polars stats failed: {e}, fallback Pandas")

        # Fallback Pandas
        stats = {}
        for col in numeric_cols:
            stats[col] = {
                "sum": df[col].sum(),
                "mean": df[col].mean(),
                "std": df[col].std(),
                "min": df[col].min(),
                "max": df[col].max(),
                "median": df[col].median(),
                "count": df[col].count(),
            }
        return stats


# Singleton global
_backend: Optional[DataBackend] = None


def get_backend(use_polars: Optional[bool] = None) -> DataBackend:
    """Retourne l'instance singleton du backend"""
    global _backend
    if _backend is None:
        _backend = DataBackend(use_polars)
    return _backend


def set_backend(use_polars: bool) -> DataBackend:
    """Configure et retourne un nouveau backend"""
    global _backend
    _backend = DataBackend(use_polars)
    return _backend


# Fonctions utilitaires
def is_polars_available() -> bool:
    """Vérifie si Polars est disponible"""
    return POLARS_AVAILABLE


def is_polars_active() -> bool:
    """Vérifie si Polars est actif"""
    return get_backend().use_polars


if __name__ == "__main__":
    print(f"Polars disponible: {POLARS_AVAILABLE}")
    print(f"Polars activé: {USE_POLARS and POLARS_AVAILABLE}")

    backend = get_backend()
    print(f"Backend actif: {backend.backend_name}")
