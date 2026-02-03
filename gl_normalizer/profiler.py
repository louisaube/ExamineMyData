"""
gl_normalizer/profiler.py
Profilage statistique des données GL

Fournit:
- Analyse statistique par colonne
- Profil des comptes (distribution, comportement)
- Baseline pour détection d'anomalies
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from enum import Enum


class DataQuality(Enum):
    """Qualité des données"""
    EXCELLENT = "excellent"    # < 1% valeurs manquantes/invalides
    GOOD = "good"             # 1-5%
    ACCEPTABLE = "acceptable"  # 5-10%
    POOR = "poor"             # > 10%


@dataclass
class ColumnProfile:
    """Profil statistique d'une colonne"""
    name: str
    dtype: str
    count: int
    null_count: int
    null_pct: float
    unique_count: int
    unique_pct: float

    # Stats numériques (si applicable)
    mean: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    median: Optional[float] = None
    q25: Optional[float] = None
    q75: Optional[float] = None
    skewness: Optional[float] = None
    kurtosis: Optional[float] = None

    # Stats catégorielles (si applicable)
    top_values: Optional[Dict[str, int]] = None
    mode: Optional[str] = None
    mode_count: Optional[int] = None

    def __repr__(self) -> str:
        null_info = f"nulls={self.null_pct:.1f}%"
        if self.mean is not None:
            return f"{self.name}: {self.dtype} [{null_info}] mean={self.mean:,.0f}"
        return f"{self.name}: {self.dtype} [{null_info}] unique={self.unique_count}"


@dataclass
class AccountProfile:
    """Profil statistique d'un compte"""
    compte: str
    libelle: str
    nb_ecritures: int
    nb_mois_actifs: int

    # Montants
    total_debit: float
    total_credit: float
    total_net: float
    montant_moyen: float
    montant_median: float
    montant_std: float
    montant_min: float
    montant_max: float

    # Distribution mensuelle
    mensuel_mean: float
    mensuel_std: float
    mensuel_cv: float           # Coefficient de variation
    mois_min: str
    mois_max: str
    range_mensuel: float        # Max - Min mensuel

    # Patterns
    concentration_decembre: float  # % du total en décembre
    saisonnalite: float           # Score de saisonnalité (0-1)
    regularite: float             # Score de régularité (0-1)

    # Classification
    behavior_type: str            # "regulier", "saisonnier", "ponctuel", "irregulier"
    risk_score: float             # Score de risque d'anomalie (0-1)


@dataclass
class BaselineProfile:
    """Baseline pour la comparaison et détection d'anomalies"""
    year: int
    total_ecritures: int
    total_comptes: int

    # Totaux globaux
    total_charges: float
    total_produits: float
    resultat: float

    # Moyennes globales
    charge_mensuelle_moyenne: float
    produit_mensuel_moyen: float

    # Distribution
    distribution_mois: Dict[str, float]
    distribution_classe: Dict[str, float]
    distribution_journal: Dict[str, float]

    # Comptes actifs par mois
    comptes_actifs_par_mois: Dict[str, int]

    # Références pour Z-scores
    seuils_zscore: Dict[str, float]


@dataclass
class DataProfileResult:
    """Résultat complet du profilage"""
    data_quality: DataQuality
    row_count: int
    column_count: int
    columns: List[ColumnProfile]
    accounts: List[AccountProfile]
    baseline: Optional[BaselineProfile] = None
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class Profiler:
    """
    Analyse statistique des données GL pour profilage et détection d'anomalies.

    Fournit:
    - Profil par colonne (types, distributions, valeurs manquantes)
    - Profil par compte (comportement, patterns)
    - Baseline pour comparaison
    """

    def __init__(self, df: pd.DataFrame, year: Optional[int] = None):
        """
        Args:
            df: DataFrame GL chargé et harmonisé
            year: Année à analyser (si None, utilise toutes les données)
        """
        self.df = df.copy()
        self.year = year

        if year is not None:
            self.df = self.df[self.df["annee"] == year].copy()

    def profile_columns(self) -> List[ColumnProfile]:
        """
        Analyse statistique de chaque colonne.

        Returns:
            Liste de ColumnProfile pour chaque colonne
        """
        profiles = []

        for col in self.df.columns:
            series = self.df[col]

            # Stats de base
            count = len(series)
            null_count = series.isna().sum()
            null_pct = (null_count / count * 100) if count > 0 else 0
            unique_count = series.nunique()
            unique_pct = (unique_count / count * 100) if count > 0 else 0

            profile = ColumnProfile(
                name=col,
                dtype=str(series.dtype),
                count=count,
                null_count=null_count,
                null_pct=null_pct,
                unique_count=unique_count,
                unique_pct=unique_pct,
            )

            # Stats numériques
            if pd.api.types.is_numeric_dtype(series):
                valid = series.dropna()
                if len(valid) > 0:
                    profile.mean = float(valid.mean())
                    profile.std = float(valid.std())
                    profile.min = float(valid.min())
                    profile.max = float(valid.max())
                    profile.median = float(valid.median())
                    profile.q25 = float(valid.quantile(0.25))
                    profile.q75 = float(valid.quantile(0.75))

                    # Skewness et kurtosis si assez de données
                    if len(valid) > 3:
                        profile.skewness = float(valid.skew())
                        profile.kurtosis = float(valid.kurtosis())

            # Stats catégorielles
            else:
                valid = series.dropna()
                if len(valid) > 0:
                    value_counts = valid.value_counts()
                    profile.top_values = value_counts.head(10).to_dict()
                    profile.mode = str(value_counts.index[0])
                    profile.mode_count = int(value_counts.iloc[0])

            profiles.append(profile)

        return profiles

    def profile_accounts(self) -> List[AccountProfile]:
        """
        Analyse statistique par compte.

        Returns:
            Liste de AccountProfile pour chaque compte
        """
        if "compte" not in self.df.columns:
            return []

        profiles = []

        # Agréger par compte
        for compte in self.df["compte"].unique():
            df_compte = self.df[self.df["compte"] == compte]

            # Infos de base
            libelle = df_compte["libelle_compte"].iloc[0] if "libelle_compte" in df_compte else ""
            nb_ecritures = len(df_compte)

            # Montants
            total_debit = df_compte["debit"].sum()
            total_credit = df_compte["credit"].sum()
            total_net = df_compte["montant"].sum()

            montants = df_compte["montant"].abs()
            montant_moyen = montants.mean()
            montant_median = montants.median()
            montant_std = montants.std()
            montant_min = montants.min()
            montant_max = montants.max()

            # Agrégation mensuelle
            if "periode" in df_compte.columns:
                mensuel = df_compte.groupby("periode")["montant"].sum()
                nb_mois_actifs = len(mensuel)
                mensuel_mean = mensuel.abs().mean()
                mensuel_std = mensuel.abs().std()
                mensuel_cv = (mensuel_std / mensuel_mean * 100) if mensuel_mean > 0 else 0

                mois_min = str(mensuel.abs().idxmin()) if len(mensuel) > 0 else ""
                mois_max = str(mensuel.abs().idxmax()) if len(mensuel) > 0 else ""
                range_mensuel = mensuel.abs().max() - mensuel.abs().min()

                # Concentration en décembre
                year = self.year or df_compte["annee"].mode().iloc[0]
                dec_key = f"{year}-12"
                dec_value = abs(mensuel.get(dec_key, 0))
                total_abs = mensuel.abs().sum()
                concentration_decembre = (dec_value / total_abs * 100) if total_abs > 0 else 0

                # Score de saisonnalité (basé sur coefficient de variation)
                saisonnalite = min(mensuel_cv / 100, 1.0) if mensuel_cv > 0 else 0

                # Score de régularité (inverse de la saisonnalité)
                regularite = max(1 - saisonnalite, 0)
            else:
                nb_mois_actifs = 1
                mensuel_mean = total_net
                mensuel_std = 0
                mensuel_cv = 0
                mois_min = mois_max = ""
                range_mensuel = 0
                concentration_decembre = 0
                saisonnalite = 0
                regularite = 1

            # Déterminer le type de comportement
            if regularite > 0.7:
                behavior_type = "regulier"
            elif saisonnalite > 0.5:
                behavior_type = "saisonnier"
            elif nb_mois_actifs <= 2:
                behavior_type = "ponctuel"
            else:
                behavior_type = "irregulier"

            # Score de risque (comptes irréguliers ou à forte concentration)
            risk_score = 0.0
            if concentration_decembre > 50:
                risk_score += 0.4
            if saisonnalite > 0.6:
                risk_score += 0.3
            if nb_mois_actifs < 6:
                risk_score += 0.3
            risk_score = min(risk_score, 1.0)

            profiles.append(AccountProfile(
                compte=str(compte),
                libelle=str(libelle),
                nb_ecritures=nb_ecritures,
                nb_mois_actifs=nb_mois_actifs,
                total_debit=total_debit,
                total_credit=total_credit,
                total_net=total_net,
                montant_moyen=montant_moyen,
                montant_median=montant_median,
                montant_std=montant_std,
                montant_min=montant_min,
                montant_max=montant_max,
                mensuel_mean=mensuel_mean,
                mensuel_std=mensuel_std,
                mensuel_cv=mensuel_cv,
                mois_min=mois_min,
                mois_max=mois_max,
                range_mensuel=range_mensuel,
                concentration_decembre=concentration_decembre,
                saisonnalite=saisonnalite,
                regularite=regularite,
                behavior_type=behavior_type,
                risk_score=risk_score,
            ))

        # Trier par risque décroissant
        profiles.sort(key=lambda x: x.risk_score, reverse=True)
        return profiles

    def compute_baseline(self) -> BaselineProfile:
        """
        Calcule le baseline statistique pour référence.

        Returns:
            BaselineProfile avec statistiques de référence
        """
        year = self.year or self.df["annee"].mode().iloc[0]

        # Totaux
        total_ecritures = len(self.df)
        total_comptes = self.df["compte"].nunique()

        # P&L
        charges = self.df[self.df["classe"] == "6"]["montant"].sum()
        produits = self.df[self.df["classe"] == "7"]["montant"].sum()
        resultat = produits - abs(charges)

        # Moyennes mensuelles
        nb_mois = self.df["periode"].nunique()
        charge_mensuelle = abs(charges) / nb_mois if nb_mois > 0 else 0
        produit_mensuel = abs(produits) / nb_mois if nb_mois > 0 else 0

        # Distributions
        dist_mois = self.df.groupby("periode")["montant"].sum().abs().to_dict()
        dist_classe = self.df.groupby("classe")["montant"].sum().abs().to_dict()

        dist_journal = {}
        if "journal" in self.df.columns:
            dist_journal = self.df.groupby("journal")["montant"].sum().abs().to_dict()

        # Comptes actifs par mois
        comptes_par_mois = self.df.groupby("periode")["compte"].nunique().to_dict()

        # Seuils Z-score par catégorie
        seuils = self._compute_zscore_thresholds()

        return BaselineProfile(
            year=int(year),
            total_ecritures=total_ecritures,
            total_comptes=total_comptes,
            total_charges=abs(charges),
            total_produits=abs(produits),
            resultat=resultat,
            charge_mensuelle_moyenne=charge_mensuelle,
            produit_mensuel_moyen=produit_mensuel,
            distribution_mois=dist_mois,
            distribution_classe=dist_classe,
            distribution_journal=dist_journal,
            comptes_actifs_par_mois=comptes_par_mois,
            seuils_zscore=seuils,
        )

    def _compute_zscore_thresholds(self) -> Dict[str, float]:
        """Calcule les seuils Z-score par type de compte"""
        seuils = {}

        # Grouper par racine de compte (2 premiers caractères)
        if "racine_2" in self.df.columns:
            for racine in self.df["racine_2"].unique():
                df_racine = self.df[self.df["racine_2"] == racine]
                if "periode" in df_racine.columns:
                    mensuel = df_racine.groupby("periode")["montant"].sum()
                    if len(mensuel) > 2:
                        std = mensuel.std()
                        # Seuil = 2 écarts-types (ajustable)
                        seuils[str(racine)] = float(2 * std) if std > 0 else 1000

        return seuils

    def profile(self) -> DataProfileResult:
        """
        Profil complet des données.

        Returns:
            DataProfileResult avec tous les profils
        """
        columns = self.profile_columns()
        accounts = self.profile_accounts()
        baseline = self.compute_baseline()

        # Évaluer la qualité des données
        null_pcts = [c.null_pct for c in columns]
        avg_null = sum(null_pcts) / len(null_pcts) if null_pcts else 0

        if avg_null < 1:
            quality = DataQuality.EXCELLENT
        elif avg_null < 5:
            quality = DataQuality.GOOD
        elif avg_null < 10:
            quality = DataQuality.ACCEPTABLE
        else:
            quality = DataQuality.POOR

        # Warnings et recommandations
        warnings = []
        recommendations = []

        # Check colonnes critiques
        for col in columns:
            if col.name in ["compte", "date", "debit", "credit"] and col.null_pct > 1:
                warnings.append(f"Colonne critique '{col.name}' a {col.null_pct:.1f}% de valeurs manquantes")

        # Check comptes à risque
        high_risk = [a for a in accounts if a.risk_score > 0.7]
        if high_risk:
            warnings.append(f"{len(high_risk)} comptes identifiés à haut risque d'anomalie")
            recommendations.append("Vérifier en priorité les comptes: " +
                                 ", ".join([a.compte for a in high_risk[:5]]))

        # Check concentration décembre
        dec_heavy = [a for a in accounts if a.concentration_decembre > 80]
        if dec_heavy:
            recommendations.append(f"{len(dec_heavy)} comptes avec >80% de mouvement en décembre")

        return DataProfileResult(
            data_quality=quality,
            row_count=len(self.df),
            column_count=len(self.df.columns),
            columns=columns,
            accounts=accounts,
            baseline=baseline,
            warnings=warnings,
            recommendations=recommendations,
        )

    def get_summary(self) -> Dict[str, Any]:
        """Retourne un résumé du profil"""
        result = self.profile()

        return {
            "quality": result.data_quality.value,
            "rows": result.row_count,
            "columns": result.column_count,
            "accounts": len(result.accounts),
            "baseline_charges": result.baseline.total_charges if result.baseline else 0,
            "baseline_produits": result.baseline.total_produits if result.baseline else 0,
            "warnings_count": len(result.warnings),
            "high_risk_accounts": len([a for a in result.accounts if a.risk_score > 0.7]),
        }

    def to_dataframe(self) -> Dict[str, pd.DataFrame]:
        """
        Exporte les profils en DataFrames.

        Returns:
            Dict avec 'columns' et 'accounts' DataFrames
        """
        columns = self.profile_columns()
        accounts = self.profile_accounts()

        df_columns = pd.DataFrame([
            {
                "column": c.name,
                "dtype": c.dtype,
                "null_pct": c.null_pct,
                "unique_count": c.unique_count,
                "mean": c.mean,
                "std": c.std,
                "min": c.min,
                "max": c.max,
            }
            for c in columns
        ])

        df_accounts = pd.DataFrame([
            {
                "compte": a.compte,
                "libelle": a.libelle,
                "nb_ecritures": a.nb_ecritures,
                "total_net": a.total_net,
                "mensuel_mean": a.mensuel_mean,
                "mensuel_cv": a.mensuel_cv,
                "concentration_dec": a.concentration_decembre,
                "behavior": a.behavior_type,
                "risk_score": a.risk_score,
            }
            for a in accounts
        ])

        return {
            "columns": df_columns,
            "accounts": df_accounts,
        }


def profile_gl(df: pd.DataFrame, year: Optional[int] = None) -> DataProfileResult:
    """
    Fonction utilitaire pour profiler un GL.

    Args:
        df: DataFrame GL
        year: Année à analyser

    Returns:
        DataProfileResult complet
    """
    profiler = Profiler(df, year)
    return profiler.profile()


if __name__ == "__main__":
    print("Profiler - Analyse statistique des données GL")
    print("=" * 50)
    print("Usage:")
    print("  from gl_normalizer.profiler import Profiler, profile_gl")
    print("  result = profile_gl(df, year=2024)")
    print("  print(result.data_quality)")
    print("  print(result.warnings)")
