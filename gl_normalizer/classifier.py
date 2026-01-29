"""
gl_normalizer/classifier.py
Classification des écritures comptables

Identifie:
- Les contreparties bilan (provisions, FNP, CCA...)
- Le type d'écriture (run rate, saisonnier, one-shot...)
- Les régularisations
"""

import pandas as pd
import numpy as np
import re
from typing import Optional, List, Dict, Tuple

from .config import (
    COMPTES_PROVISION,
    JOURNAUX_OD,
    EntryType,
)


class GLClassifier:
    """
    Classificateur d'écritures comptables.

    Analyse chaque écriture pour déterminer:
    - Sa contrepartie bilan (si applicable)
    - Son type (run rate, saisonnier, one-shot...)
    - Si c'est une régularisation
    """

    # Patterns pour détecter les régularisations dans les libellés
    REGUL_PATTERNS = [
        r"regul",
        r"régul",
        r"extourne",
        r"contre.?passation",
        r"annul",
        r"reprise",
        r"provision",
        r"fnp",
        r"fae",
        r"cca",
        r"pca",
        r"à.?nouveau",
        r"a.?nouveau",
    ]

    # Patterns pour détecter les charges exceptionnelles
    ONESHOT_PATTERNS = [
        r"exceptionnel",
        r"cession",
        r"amende",
        r"pénalité",
        r"contentieux",
        r"litige",
        r"rappel",
        r"arriéré",
        r"dégrèvement",
        r"remboursement",
    ]

    def __init__(self, df: pd.DataFrame):
        """
        Args:
            df: DataFrame GL harmonisé (sortie de GLLoader)
        """
        self.df = df.copy()
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile les regex pour performance"""
        self.regul_regex = re.compile(
            "|".join(self.REGUL_PATTERNS),
            re.IGNORECASE
        )
        self.oneshot_regex = re.compile(
            "|".join(self.ONESHOT_PATTERNS),
            re.IGNORECASE
        )

    def classify(self) -> pd.DataFrame:
        """
        Classifie toutes les écritures du GL.

        Returns:
            DataFrame avec colonnes de classification ajoutées
        """
        df = self.df.copy()

        # 1. Identifier les contreparties bilan
        df = self._identify_balance_counterparts(df)

        # 2. Classifier le type d'écriture
        df["entry_type"] = df.apply(self._classify_entry_type, axis=1)

        # 3. Marquer les régularisations
        df["is_regul"] = df.apply(self._is_regularization, axis=1)

        # 4. Calculer le montant P&L signé
        df["montant_pnl"] = self._compute_pnl_amount(df)

        return df

    def _identify_balance_counterparts(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Identifie les contreparties bilan pour chaque écriture P&L.

        Pour chaque écriture de charge/produit (classe 6/7), cherche
        si dans la même pièce/journal/date il y a une contrepartie
        sur un compte de provision (classe 4 principalement).
        """
        df = df.copy()
        df["contrepartie_bilan"] = None
        df["type_provision"] = None

        # Grouper par pièce/journal/date pour trouver les contreparties
        group_cols = ["date", "journal", "piece"]

        # S'assurer que les colonnes existent
        valid_group_cols = [c for c in group_cols if c in df.columns and df[c].notna().any()]

        if not valid_group_cols:
            return df

        # Pour chaque groupe d'écritures
        for _, group in df.groupby(valid_group_cols, dropna=False):
            if len(group) < 2:
                continue

            # Séparer P&L et Bilan
            mask_pnl = group["classe"].isin(["6", "7"])
            mask_bilan = ~mask_pnl

            pnl_indices = group[mask_pnl].index
            bilan_entries = group[mask_bilan]

            # Chercher les contreparties provision
            for bilan_idx, bilan_row in bilan_entries.iterrows():
                compte = str(bilan_row.get("compte", ""))
                racine_3 = compte[:3]

                if racine_3 in COMPTES_PROVISION:
                    # Affecter cette contrepartie aux écritures P&L du groupe
                    df.loc[pnl_indices, "contrepartie_bilan"] = compte
                    df.loc[pnl_indices, "type_provision"] = COMPTES_PROVISION[racine_3]
                    break

        return df

    def _classify_entry_type(self, row: pd.Series) -> str:
        """Classifie le type d'une écriture"""
        libelle = str(row.get("libelle", "")).lower()
        journal = str(row.get("journal", "")).upper()
        contrepartie = row.get("contrepartie_bilan")

        # One-shot si pattern exceptionnel détecté
        if self.oneshot_regex.search(libelle):
            return EntryType.ONE_SHOT

        # Régularisation si contrepartie provision ou pattern régul
        if contrepartie or self.regul_regex.search(libelle):
            return EntryType.REGUL

        # OD = souvent des estimatifs/provisions
        if journal in JOURNAUX_OD:
            return EntryType.ESTIMATIF

        # Par défaut = run rate
        return EntryType.RUN_RATE

    def _is_regularization(self, row: pd.Series) -> bool:
        """Détermine si l'écriture est une régularisation"""
        libelle = str(row.get("libelle", "")).lower()
        journal = str(row.get("journal", "")).upper()
        contrepartie = row.get("contrepartie_bilan")

        # A une contrepartie provision
        if contrepartie:
            return True

        # Pattern de régul dans le libellé
        if self.regul_regex.search(libelle):
            return True

        # Journal de régularisation
        if journal in JOURNAUX_OD:
            return True

        return False

    def _compute_pnl_amount(self, df: pd.DataFrame) -> pd.Series:
        """
        Calcule le montant P&L signé pour chaque écriture.

        Convention:
        - Classe 6 (charges): débit = charge positive, crédit = charge négative
        - Classe 7 (produits): crédit = produit positif, débit = produit négatif
        """
        montant_pnl = np.where(
            df["classe"] == "6",
            df["debit"] - df["credit"],   # Charges: D-C
            np.where(
                df["classe"] == "7",
                df["credit"] - df["debit"],   # Produits: C-D
                0  # Autres classes = 0 pour P&L
            )
        )
        return pd.Series(montant_pnl, index=df.index)

    def get_provision_summary(self) -> pd.DataFrame:
        """
        Retourne un résumé des écritures avec contreparties provision.
        """
        df = self.df[self.df["contrepartie_bilan"].notna()].copy()

        if df.empty:
            return pd.DataFrame()

        summary = df.groupby(["type_provision", "periode"]).agg({
            "debit": "sum",
            "credit": "sum",
            "montant": "sum",
            "compte": "nunique",
        }).reset_index()

        summary.columns = [
            "Type provision", "Période",
            "Total débit", "Total crédit", "Montant net",
            "Nb comptes"
        ]

        return summary.sort_values(["Type provision", "Période"])

    def get_regul_summary(self) -> pd.DataFrame:
        """
        Retourne un résumé des régularisations par mois.
        """
        df = self.df[self.df["is_regul"] == True].copy()

        if df.empty:
            return pd.DataFrame()

        summary = df.groupby(["periode", "entry_type"]).agg({
            "debit": "sum",
            "credit": "sum",
            "montant": "sum",
        }).reset_index()

        return summary.sort_values("periode")


def classify_gl(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fonction utilitaire pour classifier rapidement un GL.

    Args:
        df: DataFrame GL harmonisé

    Returns:
        DataFrame avec colonnes de classification
    """
    classifier = GLClassifier(df)
    return classifier.classify()


if __name__ == "__main__":
    print("GLClassifier - Classification des écritures comptables")
    print("Usage:")
    print("  from gl_normalizer.classifier import GLClassifier, classify_gl")
    print("  df_classified = classify_gl(df_harmonized)")
