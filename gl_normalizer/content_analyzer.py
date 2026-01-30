"""
gl_normalizer/content_analyzer.py
Analyse du contenu des écritures comptables

Analyse sémantique des écritures:
- Identification des patterns dans les libellés
- Détection des régularisations par mots-clés
- Analyse des journaux OD/Situation
- Classification du contenu
"""

import pandas as pd
import numpy as np
import re
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field
from collections import Counter

from .config import JOURNAUX_OD, COMPTES_PROVISION


@dataclass
class JournalAnalysis:
    """Analyse d'un journal comptable"""

    journal: str
    nb_ecritures: int
    total_debit: float
    total_credit: float
    nb_comptes_distincts: int
    is_od: bool                    # Journal d'OD/régularisation
    is_situation: bool             # Journal de situation
    mois_concentration: Dict[str, float]  # Répartition par mois
    top_comptes: List[Tuple[str, float]]  # Top comptes par montant

    @property
    def pct_decembre(self) -> float:
        """% des écritures en décembre"""
        return self.mois_concentration.get("12", 0)

    def __repr__(self) -> str:
        type_jal = "OD" if self.is_od else ("SIT" if self.is_situation else "STD")
        return (
            f"Journal {self.journal} [{type_jal}]: "
            f"{self.nb_ecritures} écritures, "
            f"Débit={self.total_debit:,.0f}€, "
            f"Déc={self.pct_decembre:.0f}%"
        )


@dataclass
class ContentPattern:
    """Pattern détecté dans les libellés"""

    pattern: str                   # Mot-clé ou regex
    category: str                  # REGUL, PROVISION, REPRISE, EXCEPTIONNEL, etc.
    nb_occurrences: int
    total_debit: float
    total_credit: float
    comptes_concernes: List[str]
    exemples_libelles: List[str]

    @property
    def montant_net(self) -> float:
        return self.total_debit - self.total_credit

    def __repr__(self) -> str:
        return (
            f"[{self.category}] '{self.pattern}': "
            f"{self.nb_occurrences} écritures, "
            f"Net={self.montant_net:+,.0f}€"
        )


@dataclass
class AccountContent:
    """Analyse du contenu d'un compte"""

    compte: str
    libelle_compte: str
    nb_ecritures: int
    total_debit: float
    total_credit: float

    # Répartition par journal
    par_journal: Dict[str, float]
    pct_od: float                  # % venant de journaux OD

    # Patterns détectés
    patterns_trouves: List[ContentPattern]

    # Libellés uniques
    libelles_uniques: List[str]

    # Écritures significatives (> seuil)
    ecritures_significatives: pd.DataFrame = field(repr=False, default=None)

    @property
    def is_regul_heavy(self) -> bool:
        """Le compte a beaucoup de régularisations"""
        return self.pct_od > 50 or any(
            p.category in ["REGUL", "PROVISION", "REPRISE"]
            for p in self.patterns_trouves
        )


class ContentAnalyzer:
    """
    Analyseur de contenu des écritures comptables.

    Analyse:
    1. Les journaux (identification OD, situation, concentration temporelle)
    2. Les patterns dans les libellés (régularisations, provisions, etc.)
    3. Le contenu détaillé par compte
    """

    # Journaux d'OD et situation
    JOURNAUX_OD = ["OD", "AN", "RAN", "EXT", "EXTOURNE"]
    JOURNAUX_SITUATION = ["SIT", "SITUATION", "CLO", "CLOTURE", "BILAN", "BIL"]

    # Patterns de régularisation dans les libellés
    PATTERNS_REGUL = {
        "REGUL": [r"\bregul", r"\brégul", r"regularisation", r"régularisation"],
        "EXTOURNE": [r"extourne", r"contre.?passation", r"annulation"],
        "REPRISE": [r"\breprise\b", r"reprise provision", r"reprise de provision"],
        "PROVISION": [r"\bprovision\b", r"\bdotation\b", r"\bprov\b"],
        "FNP": [r"\bfnp\b", r"facture.?non.?parvenue", r"fact.*non.*parv"],
        "CCA": [r"\bcca\b", r"charge.*constat.*avance", r"charge.*d'avance"],
        "FAE": [r"\bfae\b", r"facture.*à.*établir"],
        "A_NOUVEAU": [r"à.?nouveau", r"a.?nouveau", r"\ban\b", r"report"],
    }

    # Patterns de charges exceptionnelles
    PATTERNS_EXCEPTIONNEL = {
        "EXCEPTIONNEL": [r"exceptionnel", r"exception"],
        "DEGREVEMENT": [r"dégrèvement", r"degrevement", r"dégrev"],
        "CONTENTIEUX": [r"contentieux", r"litige", r"procès"],
        "AMENDE": [r"amende", r"pénalité", r"penalite"],
        "CESSION": [r"cession", r"vente.*immob"],
        "RAPPEL": [r"rappel", r"arriéré", r"arriere"],
        "REMBOURSEMENT": [r"remboursement", r"rembours"],
    }

    # Patterns de charges récurrentes
    PATTERNS_RECURRENT = {
        "LOYER": [r"\bloyer\b", r"location", r"bail"],
        "SALAIRE": [r"salaire", r"paie", r"remuneration"],
        "ASSURANCE": [r"assurance", r"prime.*assur"],
        "ENERGIE": [r"électricité", r"electricite", r"gaz", r"energie"],
        "TELECOM": [r"téléphone", r"telephone", r"internet", r"telecom"],
        "ABONNEMENT": [r"abonnement", r"abonn"],
    }

    def __init__(self, df: pd.DataFrame, year: int):
        """
        Args:
            df: DataFrame GL harmonisé
            year: Année à analyser
        """
        self.df = df.copy()
        self.year = year

        # Filtrer sur l'année
        if "annee" in self.df.columns:
            self.df = self.df[self.df["annee"] == year].copy()

        # Normaliser les libellés pour recherche
        if "libelle" in self.df.columns and not self.df.empty:
            self.df["libelle_lower"] = self.df["libelle"].fillna("").astype(str).str.lower()

        # Compiler tous les patterns
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile les regex pour performance"""
        self.compiled_patterns = {}

        all_patterns = {
            **self.PATTERNS_REGUL,
            **self.PATTERNS_EXCEPTIONNEL,
            **self.PATTERNS_RECURRENT,
        }

        for category, patterns in all_patterns.items():
            self.compiled_patterns[category] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

    def analyze_journals(self) -> List[JournalAnalysis]:
        """
        Analyse tous les journaux du GL.

        Returns:
            Liste des analyses par journal
        """
        analyses = []

        if "journal" not in self.df.columns:
            return analyses

        for journal in self.df["journal"].unique():
            if pd.isna(journal) or journal == "":
                continue

            df_jal = self.df[self.df["journal"] == journal]

            # Identifier le type de journal
            jal_upper = str(journal).upper()
            is_od = any(od in jal_upper for od in self.JOURNAUX_OD)
            is_situation = any(sit in jal_upper for sit in self.JOURNAUX_SITUATION)

            # Répartition par mois
            mois_dist = {}
            if "mois" in df_jal.columns:
                total = len(df_jal)
                for mois, count in df_jal["mois"].value_counts().items():
                    mois_dist[str(int(mois))] = (count / total * 100) if total > 0 else 0

            # Top comptes
            top_comptes = []
            if "compte" in df_jal.columns:
                compte_totals = df_jal.groupby("compte")["montant"].sum().abs()
                for compte, montant in compte_totals.nlargest(5).items():
                    top_comptes.append((compte, montant))

            analyses.append(JournalAnalysis(
                journal=journal,
                nb_ecritures=len(df_jal),
                total_debit=df_jal["debit"].sum(),
                total_credit=df_jal["credit"].sum(),
                nb_comptes_distincts=df_jal["compte"].nunique(),
                is_od=is_od,
                is_situation=is_situation,
                mois_concentration=mois_dist,
                top_comptes=top_comptes,
            ))

        # Trier par nb écritures décroissant
        analyses.sort(key=lambda x: x.nb_ecritures, reverse=True)

        return analyses

    def analyze_patterns(self) -> List[ContentPattern]:
        """
        Détecte les patterns dans les libellés.

        Returns:
            Liste des patterns trouvés
        """
        if "libelle_lower" not in self.df.columns:
            return []

        patterns_found = []

        for category, compiled_list in self.compiled_patterns.items():
            # Créer un masque pour toutes les variantes du pattern
            mask = pd.Series(False, index=self.df.index)

            for regex in compiled_list:
                mask |= self.df["libelle_lower"].str.contains(regex, na=False, regex=True)

            if not mask.any():
                continue

            df_match = self.df[mask]

            patterns_found.append(ContentPattern(
                pattern=category,
                category=self._get_pattern_category(category),
                nb_occurrences=len(df_match),
                total_debit=df_match["debit"].sum(),
                total_credit=df_match["credit"].sum(),
                comptes_concernes=df_match["compte"].unique().tolist()[:10],
                exemples_libelles=df_match["libelle"].dropna().unique().tolist()[:5],
            ))

        # Trier par montant net décroissant
        patterns_found.sort(key=lambda x: abs(x.montant_net), reverse=True)

        return patterns_found

    def _get_pattern_category(self, pattern_name: str) -> str:
        """Retourne la catégorie macro d'un pattern"""
        if pattern_name in self.PATTERNS_REGUL:
            return "REGUL"
        elif pattern_name in self.PATTERNS_EXCEPTIONNEL:
            return "EXCEPTIONNEL"
        elif pattern_name in self.PATTERNS_RECURRENT:
            return "RECURRENT"
        return "AUTRE"

    def _safe_get_december_od(self, od_concentration: pd.DataFrame) -> float:
        """Récupère le % OD de décembre de manière sécurisée"""
        if od_concentration.empty:
            return 0.0
        december_data = od_concentration[od_concentration["Mois"] == 12]["% OD"]
        if december_data.empty:
            return 0.0
        return float(december_data.iloc[0])

    def analyze_account_content(
        self,
        compte: str,
        seuil_significatif: float = 5000
    ) -> AccountContent:
        """
        Analyse détaillée du contenu d'un compte.

        Args:
            compte: Numéro de compte
            seuil_significatif: Seuil pour écritures significatives

        Returns:
            Analyse du contenu
        """
        df_compte = self.df[self.df["compte"] == compte]

        if df_compte.empty:
            return None

        # Répartition par journal
        par_journal = {}
        total_montant = df_compte["montant"].abs().sum()

        for journal, group in df_compte.groupby("journal"):
            montant_jal = group["montant"].abs().sum()
            par_journal[journal] = montant_jal

        # % OD
        montant_od = sum(
            v for k, v in par_journal.items()
            if any(od in str(k).upper() for od in self.JOURNAUX_OD + self.JOURNAUX_SITUATION)
        )
        pct_od = (montant_od / total_montant * 100) if total_montant > 0 else 0

        # Patterns dans ce compte
        patterns_trouves = []
        if "libelle_lower" in df_compte.columns:
            for category, compiled_list in self.compiled_patterns.items():
                for regex in compiled_list:
                    if df_compte["libelle_lower"].str.contains(regex, na=False, regex=True).any():
                        df_match = df_compte[
                            df_compte["libelle_lower"].str.contains(regex, na=False, regex=True)
                        ]
                        patterns_trouves.append(ContentPattern(
                            pattern=category,
                            category=self._get_pattern_category(category),
                            nb_occurrences=len(df_match),
                            total_debit=df_match["debit"].sum(),
                            total_credit=df_match["credit"].sum(),
                            comptes_concernes=[compte],
                            exemples_libelles=df_match["libelle"].dropna().unique().tolist()[:3],
                        ))
                        break  # Une seule occurrence par catégorie

        # Libellés uniques
        libelles_uniques = df_compte["libelle"].dropna().unique().tolist()[:20]

        # Écritures significatives
        ecritures_sig = df_compte[df_compte["montant"].abs() >= seuil_significatif].copy()
        if not ecritures_sig.empty:
            ecritures_sig = ecritures_sig.sort_values("montant", key=abs, ascending=False)

        # Libellé compte
        libelle_compte = ""
        if "libelle_compte" in df_compte.columns:
            libelle_compte = df_compte["libelle_compte"].iloc[0] if len(df_compte) > 0 else ""

        return AccountContent(
            compte=compte,
            libelle_compte=str(libelle_compte) if pd.notna(libelle_compte) else "",
            nb_ecritures=len(df_compte),
            total_debit=df_compte["debit"].sum(),
            total_credit=df_compte["credit"].sum(),
            par_journal=par_journal,
            pct_od=pct_od,
            patterns_trouves=patterns_trouves,
            libelles_uniques=libelles_uniques,
            ecritures_significatives=ecritures_sig,
        )

    def get_od_concentration(self) -> pd.DataFrame:
        """
        Analyse la concentration des OD par mois.

        Returns:
            DataFrame avec % OD par mois
        """
        if "journal" not in self.df.columns or "mois" not in self.df.columns or self.df.empty:
            return pd.DataFrame()

        # Identifier les écritures OD
        mask_od = self.df["journal"].fillna("").astype(str).str.upper().apply(
            lambda x: any(od in x for od in self.JOURNAUX_OD + self.JOURNAUX_SITUATION)
        )

        # Agréger par mois
        result = []
        for mois in range(1, 13):
            mois_mask = self.df["mois"] == mois
            df_mois = self.df[mois_mask]
            df_od_mois = self.df[mask_od & mois_mask]

            total_mois = df_mois["montant"].abs().sum()
            od_mois = df_od_mois["montant"].abs().sum()

            result.append({
                "Mois": mois,
                "Total écritures": len(df_mois),
                "Écritures OD": len(df_od_mois),
                "Montant total": total_mois,
                "Montant OD": od_mois,
                "% OD": (od_mois / total_mois * 100) if total_mois > 0 else 0,
            })

        return pd.DataFrame(result)

    def get_regul_entries(self) -> pd.DataFrame:
        """
        Retourne toutes les écritures identifiées comme régularisations.

        Returns:
            DataFrame des écritures de régul
        """
        if "libelle_lower" not in self.df.columns:
            return pd.DataFrame()

        # Créer masque pour patterns de régul
        mask = pd.Series(False, index=self.df.index)

        for category, compiled_list in self.compiled_patterns.items():
            if category in self.PATTERNS_REGUL or category in ["DEGREVEMENT", "REMBOURSEMENT"]:
                for regex in compiled_list:
                    mask |= self.df["libelle_lower"].str.contains(regex, na=False, regex=True)

        # Ajouter les écritures de journaux OD
        if "journal" in self.df.columns and not self.df.empty:
            mask_od = self.df["journal"].fillna("").astype(str).str.upper().apply(
                lambda x: any(od in x for od in self.JOURNAUX_OD + self.JOURNAUX_SITUATION)
            )
            mask |= mask_od

        df_regul = self.df[mask].copy()

        if not df_regul.empty:
            df_regul = df_regul.sort_values("montant", key=abs, ascending=False)

        return df_regul

    def summary(self) -> Dict:
        """
        Retourne un résumé de l'analyse de contenu.
        """
        journals = self.analyze_journals()
        patterns = self.analyze_patterns()
        od_concentration = self.get_od_concentration()

        # Compter journaux OD
        nb_jal_od = sum(1 for j in journals if j.is_od or j.is_situation)

        # Patterns de régul
        patterns_regul = [p for p in patterns if p.category == "REGUL"]
        patterns_except = [p for p in patterns if p.category == "EXCEPTIONNEL"]

        return {
            "nb_journaux": len(journals),
            "nb_journaux_od": nb_jal_od,
            "journaux_od": [j.journal for j in journals if j.is_od or j.is_situation],
            "patterns_regul": len(patterns_regul),
            "montant_regul": sum(p.montant_net for p in patterns_regul),
            "patterns_except": len(patterns_except),
            "montant_except": sum(p.montant_net for p in patterns_except),
            "pct_od_decembre": self._safe_get_december_od(od_concentration),
        }


def analyze_content(df: pd.DataFrame, year: int) -> Dict:
    """
    Fonction utilitaire pour analyser le contenu d'un GL.

    Args:
        df: DataFrame GL
        year: Année

    Returns:
        Dict avec résumé de l'analyse
    """
    analyzer = ContentAnalyzer(df, year)
    return analyzer.summary()


if __name__ == "__main__":
    print("ContentAnalyzer - Analyse du contenu des écritures")
    print("Usage:")
    print("  from gl_normalizer.content_analyzer import ContentAnalyzer")
    print("  analyzer = ContentAnalyzer(df, 2024)")
    print("  journals = analyzer.analyze_journals()")
    print("  patterns = analyzer.analyze_patterns()")
