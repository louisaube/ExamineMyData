"""
gl_normalizer/drilldown.py
Analyse fine (drill-down) des variations par compte

Objectif: Expliquer POURQUOI un compte varie, pas juste COMBIEN.
"""

import pandas as pd
import numpy as np
import re
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field


@dataclass
class EntryGroup:
    """Groupe d'écritures de même nature (libellé normalisé)"""

    libelle_normalise: str
    montant_n1: float
    montant_n: float
    variation: float
    nb_ecritures_n1: int
    nb_ecritures_n: int
    status: str  # "NOUVELLE", "DISPARUE", "VARIEE", "STABLE"

    @property
    def variation_pct(self) -> float:
        if self.montant_n1 == 0:
            return 100.0 if self.montant_n != 0 else 0.0
        return (self.variation / abs(self.montant_n1)) * 100

    def __repr__(self) -> str:
        return (
            f"{self.status}: {self.libelle_normalise[:40]} | "
            f"N-1: {self.montant_n1:,.0f}€ → N: {self.montant_n:,.0f}€ "
            f"({self.variation:+,.0f}€)"
        )


@dataclass
class VariationBridge:
    """Pont de variation expliquant le passage de N-1 à N"""

    compte: str
    libelle_compte: str
    montant_n1: float
    montant_n: float
    variation_totale: float

    # Décomposition de la variation
    nouvelles_ecritures: float      # Montant des écritures nouvelles
    ecritures_disparues: float      # Montant des écritures disparues
    ecritures_variees: float        # Variation des écritures communes

    # Détail par groupe
    groupes: List[EntryGroup] = field(default_factory=list)

    @property
    def is_reconciled(self) -> bool:
        """Vérifie que le bridge est équilibré"""
        total_explique = (
            self.montant_n1
            + self.nouvelles_ecritures
            - self.ecritures_disparues
            + self.ecritures_variees
        )
        return abs(total_explique - self.montant_n) < 0.01

    def __repr__(self) -> str:
        return (
            f"Bridge {self.compte}:\n"
            f"  N-1: {self.montant_n1:,.0f}€\n"
            f"  + Nouvelles: {self.nouvelles_ecritures:+,.0f}€\n"
            f"  - Disparues: {self.ecritures_disparues:+,.0f}€\n"
            f"  ± Variations: {self.ecritures_variees:+,.0f}€\n"
            f"  = N: {self.montant_n:,.0f}€"
        )


@dataclass
class AccountDrilldown:
    """Analyse complète d'un compte"""

    compte: str
    libelle_compte: str
    periode_n1: str
    periode_n: str

    # Montants
    montant_n1: float
    montant_n: float
    variation: float

    # Bridge
    bridge: VariationBridge

    # Écritures détaillées
    ecritures_n1: pd.DataFrame = field(repr=False, default=None)
    ecritures_n: pd.DataFrame = field(repr=False, default=None)

    # Groupes par nature
    groupes_nouvelles: List[EntryGroup] = field(default_factory=list)
    groupes_disparues: List[EntryGroup] = field(default_factory=list)
    groupes_variees: List[EntryGroup] = field(default_factory=list)


class VariationDrilldown:
    """
    Analyseur de variations pour drill-down détaillé.

    Permet de comprendre les variations entre deux périodes
    en décomposant par nature d'écriture.
    """

    # Patterns à retirer pour normaliser les libellés
    NORMALIZE_PATTERNS = [
        r"\d{2}/\d{2}/\d{4}",           # Dates DD/MM/YYYY
        r"\d{4}-\d{2}-\d{2}",           # Dates YYYY-MM-DD
        r"\d{2}\.\d{2}\.\d{4}",         # Dates DD.MM.YYYY
        r"n[°o]?\s*\d+",                # Numéros (n°123, no 456)
        r"#\d+",                         # Références #123
        r"\b\d{6,}\b",                  # Longs numéros (factures)
        r"facture\s+\d+",               # Facture 12345
        r"fact\.?\s*\d+",               # Fact. 12345
        r"\bdu\s+\d{2}/\d{2}",          # du 01/01
        r"\b(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\b",
        r"\b(jan|fev|mar|avr|mai|jun|jul|aou|sep|oct|nov|dec)\b",
        r"\b20\d{2}\b",                 # Années 2020-2099
    ]

    def __init__(
        self,
        df_n1: pd.DataFrame,
        df_n: pd.DataFrame,
        year_n1: int,
        year_n: int,
        mois: int = 12,
    ):
        """
        Args:
            df_n1: GL année N-1 (harmonisé et classifié)
            df_n: GL année N (harmonisé et classifié)
            year_n1: Année N-1
            year_n: Année N
            mois: Mois à comparer (défaut: 12 = décembre)
        """
        self.year_n1 = year_n1
        self.year_n = year_n
        self.mois = mois

        self.periode_n1 = f"{year_n1}-{mois:02d}"
        self.periode_n = f"{year_n}-{mois:02d}"

        # Filtrer sur la période
        self.df_n1 = df_n1[df_n1["periode"] == self.periode_n1].copy()
        self.df_n = df_n[df_n["periode"] == self.periode_n].copy()

        # Compiler les patterns de normalisation
        self.normalize_regex = re.compile(
            "|".join(self.NORMALIZE_PATTERNS),
            re.IGNORECASE
        )

    def analyze_account(self, compte: str) -> AccountDrilldown:
        """
        Analyse détaillée d'un compte spécifique.

        Args:
            compte: Numéro de compte à analyser

        Returns:
            Analyse complète avec bridge et groupes
        """
        # Filtrer les écritures du compte
        ec_n1 = self.df_n1[self.df_n1["compte"] == compte].copy()
        ec_n = self.df_n[self.df_n["compte"] == compte].copy()

        # Calculer montant_pnl si absent
        for df in [ec_n1, ec_n]:
            if "montant_pnl" not in df.columns:
                df["montant_pnl"] = df["debit"] - df["credit"]

        # Normaliser les libellés
        ec_n1["libelle_norm"] = ec_n1["libelle"].apply(self._normalize_libelle)
        ec_n["libelle_norm"] = ec_n["libelle"].apply(self._normalize_libelle)

        # Montants totaux
        montant_n1 = ec_n1["montant_pnl"].sum() if len(ec_n1) > 0 else 0
        montant_n = ec_n["montant_pnl"].sum() if len(ec_n) > 0 else 0
        variation = montant_n - montant_n1

        # Grouper par libellé normalisé
        groups_n1 = ec_n1.groupby("libelle_norm").agg({
            "montant_pnl": "sum",
            "libelle": "count"
        }).rename(columns={"libelle": "nb_ecritures"})

        groups_n = ec_n.groupby("libelle_norm").agg({
            "montant_pnl": "sum",
            "libelle": "count"
        }).rename(columns={"libelle": "nb_ecritures"})

        # Identifier nouvelles, disparues, variées
        all_libelles = set(groups_n1.index) | set(groups_n.index)

        groupes_nouvelles = []
        groupes_disparues = []
        groupes_variees = []

        for lib in all_libelles:
            m_n1 = groups_n1.loc[lib, "montant_pnl"] if lib in groups_n1.index else 0
            m_n = groups_n.loc[lib, "montant_pnl"] if lib in groups_n.index else 0
            nb_n1 = int(groups_n1.loc[lib, "nb_ecritures"]) if lib in groups_n1.index else 0
            nb_n = int(groups_n.loc[lib, "nb_ecritures"]) if lib in groups_n.index else 0

            if lib not in groups_n1.index:
                status = "NOUVELLE"
                groupes_nouvelles.append(EntryGroup(
                    libelle_normalise=lib,
                    montant_n1=0,
                    montant_n=m_n,
                    variation=m_n,
                    nb_ecritures_n1=0,
                    nb_ecritures_n=nb_n,
                    status=status,
                ))
            elif lib not in groups_n.index:
                status = "DISPARUE"
                groupes_disparues.append(EntryGroup(
                    libelle_normalise=lib,
                    montant_n1=m_n1,
                    montant_n=0,
                    variation=-m_n1,
                    nb_ecritures_n1=nb_n1,
                    nb_ecritures_n=0,
                    status=status,
                ))
            else:
                var = m_n - m_n1
                status = "STABLE" if abs(var) < 1 else "VARIEE"
                if status == "VARIEE":
                    groupes_variees.append(EntryGroup(
                        libelle_normalise=lib,
                        montant_n1=m_n1,
                        montant_n=m_n,
                        variation=var,
                        nb_ecritures_n1=nb_n1,
                        nb_ecritures_n=nb_n,
                        status=status,
                    ))

        # Trier par impact
        groupes_nouvelles.sort(key=lambda x: abs(x.variation), reverse=True)
        groupes_disparues.sort(key=lambda x: abs(x.variation), reverse=True)
        groupes_variees.sort(key=lambda x: abs(x.variation), reverse=True)

        # Construire le bridge
        nouvelles_total = sum(g.montant_n for g in groupes_nouvelles)
        disparues_total = sum(g.montant_n1 for g in groupes_disparues)
        variees_total = sum(g.variation for g in groupes_variees)

        bridge = VariationBridge(
            compte=compte,
            libelle_compte=self._get_libelle_compte(compte, ec_n1, ec_n),
            montant_n1=montant_n1,
            montant_n=montant_n,
            variation_totale=variation,
            nouvelles_ecritures=nouvelles_total,
            ecritures_disparues=disparues_total,
            ecritures_variees=variees_total,
            groupes=groupes_nouvelles + groupes_disparues + groupes_variees,
        )

        return AccountDrilldown(
            compte=compte,
            libelle_compte=bridge.libelle_compte,
            periode_n1=self.periode_n1,
            periode_n=self.periode_n,
            montant_n1=montant_n1,
            montant_n=montant_n,
            variation=variation,
            bridge=bridge,
            ecritures_n1=ec_n1,
            ecritures_n=ec_n,
            groupes_nouvelles=groupes_nouvelles,
            groupes_disparues=groupes_disparues,
            groupes_variees=groupes_variees,
        )

    def analyze_top_variations(
        self,
        n: int = 10,
        classes: Optional[List[str]] = None
    ) -> List[AccountDrilldown]:
        """
        Analyse les N comptes avec les plus grandes variations.

        Args:
            n: Nombre de comptes à analyser
            classes: Classes à inclure (défaut: ["6", "7"])

        Returns:
            Liste des analyses triées par variation décroissante
        """
        classes = classes or ["6", "7"]

        # Agréger par compte pour chaque période
        agg_n1 = self.df_n1.groupby("compte")["montant_pnl"].sum() if "montant_pnl" in self.df_n1.columns else self.df_n1.groupby("compte").apply(lambda x: (x["debit"] - x["credit"]).sum())
        agg_n = self.df_n.groupby("compte")["montant_pnl"].sum() if "montant_pnl" in self.df_n.columns else self.df_n.groupby("compte").apply(lambda x: (x["debit"] - x["credit"]).sum())

        # Calculer les variations
        all_comptes = set(agg_n1.index) | set(agg_n.index)
        variations = []

        for compte in all_comptes:
            # Filtrer par classe
            if not any(str(compte).startswith(c) for c in classes):
                continue

            m_n1 = agg_n1.get(compte, 0)
            m_n = agg_n.get(compte, 0)
            var = m_n - m_n1

            if var != 0:
                variations.append((compte, var))

        # Trier par variation absolue
        variations.sort(key=lambda x: abs(x[1]), reverse=True)

        # Analyser les top N
        results = []
        for compte, _ in variations[:n]:
            results.append(self.analyze_account(compte))

        return results

    def _normalize_libelle(self, libelle: str) -> str:
        """Normalise un libellé en retirant dates, numéros, etc."""
        if pd.isna(libelle):
            return ""

        # Convertir en string et uppercase
        lib = str(libelle).upper().strip()

        # Retirer les patterns
        lib = self.normalize_regex.sub("", lib)

        # Nettoyer espaces multiples
        lib = re.sub(r"\s+", " ", lib).strip()

        # Retirer ponctuation de fin
        lib = lib.rstrip(".-_/\\")

        return lib if lib else "AUTRE"

    def _get_libelle_compte(
        self,
        compte: str,
        df_n1: pd.DataFrame,
        df_n: pd.DataFrame
    ) -> str:
        """Récupère le libellé d'un compte"""
        for df in [df_n, df_n1]:
            if "libelle_compte" in df.columns and len(df) > 0:
                val = df["libelle_compte"].iloc[0]
                if pd.notna(val) and str(val).strip():
                    return str(val).strip()
        return ""

    def format_drilldown_report(self, analysis: AccountDrilldown) -> str:
        """
        Formate un rapport textuel du drill-down.

        Args:
            analysis: Résultat de analyze_account

        Returns:
            Rapport formaté en texte
        """
        lines = [
            "=" * 70,
            f"DRILL-DOWN COMPTE {analysis.compte}",
            f"{analysis.libelle_compte}",
            "=" * 70,
            "",
            "MONTANTS",
            f"  {self.periode_n1}: {analysis.montant_n1:>15,.0f}€",
            f"  {self.periode_n}: {analysis.montant_n:>15,.0f}€",
            f"  VARIATION:    {analysis.variation:>15,.0f}€",
            "",
            "BRIDGE DE VARIATION",
            f"  Montant {self.periode_n1}:        {analysis.montant_n1:>12,.0f}€",
            f"  + Nouvelles écritures:   {analysis.bridge.nouvelles_ecritures:>+12,.0f}€",
            f"  - Écritures disparues:   {-analysis.bridge.ecritures_disparues:>+12,.0f}€",
            f"  ± Variations:            {analysis.bridge.ecritures_variees:>+12,.0f}€",
            f"  = Montant {self.periode_n}:        {analysis.montant_n:>12,.0f}€",
            "",
        ]

        if analysis.groupes_nouvelles:
            lines.append(f"NOUVELLES ÉCRITURES ({len(analysis.groupes_nouvelles)})")
            for g in analysis.groupes_nouvelles[:10]:
                lines.append(f"  {g.libelle_normalise[:45]:45} {g.montant_n:>12,.0f}€")
            if len(analysis.groupes_nouvelles) > 10:
                lines.append(f"  ... et {len(analysis.groupes_nouvelles) - 10} autres")
            lines.append("")

        if analysis.groupes_disparues:
            lines.append(f"ÉCRITURES DISPARUES ({len(analysis.groupes_disparues)})")
            for g in analysis.groupes_disparues[:10]:
                lines.append(f"  {g.libelle_normalise[:45]:45} {g.montant_n1:>12,.0f}€")
            if len(analysis.groupes_disparues) > 10:
                lines.append(f"  ... et {len(analysis.groupes_disparues) - 10} autres")
            lines.append("")

        if analysis.groupes_variees:
            lines.append(f"ÉCRITURES VARIÉES ({len(analysis.groupes_variees)})")
            for g in analysis.groupes_variees[:10]:
                lines.append(
                    f"  {g.libelle_normalise[:35]:35} "
                    f"{g.montant_n1:>10,.0f}€ → {g.montant_n:>10,.0f}€ "
                    f"({g.variation:+,.0f}€)"
                )
            if len(analysis.groupes_variees) > 10:
                lines.append(f"  ... et {len(analysis.groupes_variees) - 10} autres")

        return "\n".join(lines)


if __name__ == "__main__":
    print("VariationDrilldown - Analyse fine des variations par compte")
    print("Usage:")
    print("  from gl_normalizer.drilldown import VariationDrilldown")
    print("  drilldown = VariationDrilldown(df_2024, df_2025, 2024, 2025)")
    print("  analysis = drilldown.analyze_account('631111000')")
    print("  print(drilldown.format_drilldown_report(analysis))")
