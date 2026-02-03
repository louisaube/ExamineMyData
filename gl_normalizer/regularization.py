"""
gl_normalizer/regularization.py
Détection et analyse des régularisations comptables

Fournit:
- Identification des journaux OD/situation
- Détection des écritures de régularisation
- Analyse des patterns de clôture
- Classification des types de régularisation
"""

import pandas as pd
import numpy as np
import re
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Set, Tuple
from enum import Enum

from .accounting_context import AccountingContext, get_pcg_context


class RegularizationType(Enum):
    """Types de régularisation identifiés"""
    PROVISION = "provision"           # Dotations/reprises 68x, 78x
    CCA = "cca"                       # Charges constatées d'avance (486)
    PCA = "pca"                       # Produits constatés d'avance (487)
    FNP = "fnp"                       # Factures non parvenues (408)
    AAR = "aar"                       # Avoir à recevoir (4098)
    INVENTAIRE = "inventaire"         # Écritures d'inventaire génériques
    AMORTISSEMENT = "amortissement"   # Dotations aux amortissements
    IMPOT = "impot"                   # Provisions impôt (695, 696)
    AUTRE = "autre"


class JournalType(Enum):
    """Types de journaux comptables"""
    OD = "od"                         # Opérations diverses
    AN = "an"                         # À nouveaux
    SIT = "sit"                       # Situation
    RAN = "ran"                       # Report à nouveaux
    CLO = "clo"                       # Clôture
    INV = "inv"                       # Inventaire
    ACHAT = "achat"
    VENTE = "vente"
    BANQUE = "banque"
    CAISSE = "caisse"
    PAIE = "paie"
    AUTRE = "autre"


@dataclass
class RegularizationEntry:
    """Une écriture de régularisation identifiée"""
    date: str
    compte: str
    libelle_compte: str
    journal: str
    libelle: str
    montant: float
    type: RegularizationType
    confidence: float             # Score de confiance 0-1
    keywords_found: List[str] = field(default_factory=list)
    pcg_context: Optional[str] = None  # Info PCG si disponible


@dataclass
class JournalAnalysisResult:
    """Résultat d'analyse d'un journal"""
    code: str
    type: JournalType
    total_ecritures: int
    total_montant: float
    pct_decembre: float           # % des écritures en décembre
    pct_total: float              # % du total des écritures GL
    is_suspect: bool              # True si patterns suspects
    regularizations_count: int
    warning: str = ""


@dataclass
class RegularizationAnalysis:
    """Résultat complet de l'analyse des régularisations"""
    year: int
    total_ecritures: int
    total_regularizations: int
    regularizations: List[RegularizationEntry]
    by_type: Dict[str, int]       # Nombre par type
    by_journal: Dict[str, JournalAnalysisResult]
    impact_total: float           # Impact total sur le P&L
    risk_score: float             # Score de risque 0-1


# Mots-clés pour détecter les régularisations dans les libellés
KEYWORDS_PROVISION = [
    "provision", "prov.", "dotation", "dot.", "reprise", "repr.",
    "amortissement", "amort.", "dépréciation", "depreciation"
]

KEYWORDS_REGULARISATION = [
    "régularisation", "regularisation", "regul", "rég.",
    "constaté d'avance", "constatée d'avance", "cca", "pca",
    "facture non parvenue", "fnp", "a recevoir", "à recevoir",
    "extourne", "contre-passation", "annulation"
]

KEYWORDS_CLOTURE = [
    "clôture", "cloture", "inventaire", "situation",
    "bilan", "arrêté", "arrete", "exercice"
]

KEYWORDS_IMPOT = [
    "is ", "impôt", "impot", "taxe", "contribution",
    "cfe", "cvae", "cet"
]

# Codes journaux OD typiques
JOURNAUX_OD = {"OD", "AN", "RAN", "SIT", "CLO", "INV", "JOD", "EXT", "REG"}

# Comptes de régularisation typiques
COMPTES_REGUL = {
    "486": RegularizationType.CCA,      # CCA
    "487": RegularizationType.PCA,      # PCA
    "408": RegularizationType.FNP,      # FNP
    "4098": RegularizationType.AAR,     # AAR
    "401": RegularizationType.FNP,      # Fournisseurs (parfois FNP)
    "428": RegularizationType.INVENTAIRE,  # Charges à payer personnel
    "438": RegularizationType.INVENTAIRE,  # Charges à payer orga sociaux
    "448": RegularizationType.INVENTAIRE,  # État charges à payer
    "468": RegularizationType.INVENTAIRE,  # Divers charges à payer
}


class RegularizationDetector:
    """
    Détecte et analyse les écritures de régularisation.

    Combine:
    - Analyse des journaux OD
    - Détection de mots-clés dans les libellés
    - Classification par compte PCG
    - Scoring de confiance
    """

    def __init__(
        self,
        df: pd.DataFrame,
        year: Optional[int] = None,
        accounting_context: Optional[AccountingContext] = None,
    ):
        """
        Args:
            df: DataFrame GL
            year: Année à analyser
            accounting_context: Contexte PCG (optionnel, crée un par défaut)
        """
        self.df = df.copy()
        self.year = year
        self.ctx = accounting_context or get_pcg_context()

        if year is not None:
            self.df = self.df[self.df["annee"] == year]

    def detect_regularizations(self) -> List[RegularizationEntry]:
        """
        Détecte toutes les écritures de régularisation.

        Returns:
            Liste des régularisations triées par confiance
        """
        regularizations = []

        for _, row in self.df.iterrows():
            entry = self._analyze_entry(row)
            if entry is not None:
                regularizations.append(entry)

        # Trier par confiance décroissante
        regularizations.sort(key=lambda x: x.confidence, reverse=True)
        return regularizations

    def _analyze_entry(self, row: pd.Series) -> Optional[RegularizationEntry]:
        """Analyse une écriture pour détecter si c'est une régularisation"""
        compte = str(row.get("compte", ""))
        libelle = str(row.get("libelle", "")).lower()
        journal = str(row.get("journal", "")).upper()

        # Score de base
        confidence = 0.0
        keywords_found = []
        regul_type = RegularizationType.AUTRE

        # 1. Analyse du compte (poids: 40%)
        racine_3 = compte[:3] if len(compte) >= 3 else compte
        racine_2 = compte[:2] if len(compte) >= 2 else compte

        # Comptes de provision (68x, 78x)
        if racine_2 in ["68", "78"]:
            confidence += 0.4
            regul_type = RegularizationType.PROVISION
            if racine_2 == "68":
                keywords_found.append("compte_68x")
            else:
                keywords_found.append("compte_78x")

        # Comptes de régularisation
        elif racine_3 in COMPTES_REGUL:
            confidence += 0.35
            regul_type = COMPTES_REGUL[racine_3]
            keywords_found.append(f"compte_{racine_3}")

        # Amortissements (28x)
        elif racine_2 == "28":
            confidence += 0.35
            regul_type = RegularizationType.AMORTISSEMENT
            keywords_found.append("compte_28x")

        # Impôts (695, 696)
        elif racine_3 in ["695", "696", "699"]:
            confidence += 0.35
            regul_type = RegularizationType.IMPOT
            keywords_found.append(f"compte_{racine_3}")

        # 2. Analyse du journal (poids: 25%)
        if journal in JOURNAUX_OD:
            confidence += 0.25
            keywords_found.append(f"journal_{journal}")

        # 3. Analyse des mots-clés dans le libellé (poids: 35%)
        kw_score = 0.0

        for kw in KEYWORDS_PROVISION:
            if kw in libelle:
                kw_score += 0.15
                keywords_found.append(kw)
                if regul_type == RegularizationType.AUTRE:
                    regul_type = RegularizationType.PROVISION

        for kw in KEYWORDS_REGULARISATION:
            if kw in libelle:
                kw_score += 0.12
                keywords_found.append(kw)

        for kw in KEYWORDS_CLOTURE:
            if kw in libelle:
                kw_score += 0.08
                keywords_found.append(kw)
                if regul_type == RegularizationType.AUTRE:
                    regul_type = RegularizationType.INVENTAIRE

        for kw in KEYWORDS_IMPOT:
            if kw in libelle:
                kw_score += 0.10
                keywords_found.append(kw)
                if regul_type == RegularizationType.AUTRE:
                    regul_type = RegularizationType.IMPOT

        confidence += min(kw_score, 0.35)  # Cap à 35%

        # 4. Bonus: décembre (poids: 10%)
        mois = row.get("mois", 0)
        if mois == 12:
            confidence += 0.10
            keywords_found.append("decembre")

        # Seuil minimum de confiance
        if confidence < 0.25:
            return None

        # Contexte PCG
        pcg_info = None
        classif = self.ctx.classify_account(compte)
        if classif:
            pcg_info = f"{classif.libelle_pcg} ({classif.frequency.value})"

        # Créer l'entrée
        date_str = str(row.get("date", ""))
        if hasattr(row.get("date"), "strftime"):
            date_str = row["date"].strftime("%Y-%m-%d")

        return RegularizationEntry(
            date=date_str,
            compte=compte,
            libelle_compte=str(row.get("libelle_compte", "")),
            journal=journal,
            libelle=str(row.get("libelle", "")),
            montant=float(row.get("montant", 0)),
            type=regul_type,
            confidence=min(confidence, 1.0),
            keywords_found=list(set(keywords_found)),
            pcg_context=pcg_info,
        )

    def analyze_journals(self) -> Dict[str, JournalAnalysisResult]:
        """
        Analyse tous les journaux pour identifier les patterns suspects.

        Returns:
            Dict {code_journal: JournalAnalysisResult}
        """
        if "journal" not in self.df.columns:
            return {}

        results = {}
        total_gl = len(self.df)
        year = self.year or self.df["annee"].mode().iloc[0]
        dec_key = f"{year}-12"

        for journal in self.df["journal"].unique():
            df_journal = self.df[self.df["journal"] == journal]

            # Stats de base
            total_ecritures = len(df_journal)
            total_montant = df_journal["montant"].abs().sum()
            pct_total = (total_ecritures / total_gl * 100) if total_gl > 0 else 0

            # % en décembre
            dec_ecritures = 0
            if "periode" in df_journal.columns:
                dec_ecritures = len(df_journal[df_journal["periode"] == dec_key])
            pct_decembre = (dec_ecritures / total_ecritures * 100) if total_ecritures > 0 else 0

            # Déterminer le type de journal
            journal_upper = str(journal).upper()
            if journal_upper in JOURNAUX_OD:
                jtype = JournalType.OD
            elif any(x in journal_upper for x in ["AC", "HA", "FOU"]):
                jtype = JournalType.ACHAT
            elif any(x in journal_upper for x in ["VE", "VT", "CLI"]):
                jtype = JournalType.VENTE
            elif any(x in journal_upper for x in ["BQ", "BAN"]):
                jtype = JournalType.BANQUE
            elif any(x in journal_upper for x in ["CA", "CAI"]):
                jtype = JournalType.CAISSE
            elif any(x in journal_upper for x in ["PA", "SAL"]):
                jtype = JournalType.PAIE
            else:
                jtype = JournalType.AUTRE

            # Suspect si OD avec forte concentration en décembre
            is_suspect = jtype == JournalType.OD and pct_decembre > 50
            warning = ""
            if is_suspect:
                warning = f"Journal OD avec {pct_decembre:.0f}% des écritures en décembre"

            # Compter les régularisations dans ce journal
            reguls = self._count_regularizations_in_journal(df_journal)

            results[str(journal)] = JournalAnalysisResult(
                code=str(journal),
                type=jtype,
                total_ecritures=total_ecritures,
                total_montant=total_montant,
                pct_decembre=pct_decembre,
                pct_total=pct_total,
                is_suspect=is_suspect,
                regularizations_count=reguls,
                warning=warning,
            )

        return results

    def _count_regularizations_in_journal(self, df_journal: pd.DataFrame) -> int:
        """Compte le nombre de régularisations dans un journal"""
        count = 0
        for _, row in df_journal.iterrows():
            entry = self._analyze_entry(row)
            if entry is not None:
                count += 1
        return count

    def get_full_analysis(self) -> RegularizationAnalysis:
        """
        Analyse complète des régularisations.

        Returns:
            RegularizationAnalysis avec tous les détails
        """
        year = self.year or self.df["annee"].mode().iloc[0]

        # Détecter les régularisations
        regularizations = self.detect_regularizations()

        # Analyser les journaux
        journals = self.analyze_journals()

        # Comptage par type
        by_type = {}
        for regul in regularizations:
            type_name = regul.type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1

        # Impact total
        impact = sum(r.montant for r in regularizations)

        # Score de risque
        risk = self._compute_risk_score(regularizations, journals)

        return RegularizationAnalysis(
            year=int(year),
            total_ecritures=len(self.df),
            total_regularizations=len(regularizations),
            regularizations=regularizations,
            by_type=by_type,
            by_journal=journals,
            impact_total=impact,
            risk_score=risk,
        )

    def _compute_risk_score(
        self,
        regularizations: List[RegularizationEntry],
        journals: Dict[str, JournalAnalysisResult],
    ) -> float:
        """Calcule un score de risque global"""
        score = 0.0

        # Ratio de régularisations
        if len(self.df) > 0:
            ratio = len(regularizations) / len(self.df)
            score += min(ratio * 2, 0.3)  # Max 30%

        # Journaux suspects
        suspect_journals = [j for j in journals.values() if j.is_suspect]
        score += len(suspect_journals) * 0.15  # 15% par journal suspect

        # Forte concentration de régularisations
        high_conf = [r for r in regularizations if r.confidence > 0.7]
        if len(high_conf) > 10:
            score += 0.2

        return min(score, 1.0)

    def get_provisions_with_pcg(self) -> List[RegularizationEntry]:
        """
        Retourne les provisions avec contexte PCG enrichi.

        Returns:
            Liste des provisions de type PROVISION ou AMORTISSEMENT
        """
        all_reguls = self.detect_regularizations()
        return [
            r for r in all_reguls
            if r.type in [RegularizationType.PROVISION, RegularizationType.AMORTISSEMENT]
        ]

    def get_december_regularizations(self) -> List[RegularizationEntry]:
        """Retourne uniquement les régularisations de décembre"""
        all_reguls = self.detect_regularizations()
        return [r for r in all_reguls if "decembre" in r.keywords_found]


def detect_regularizations(
    df: pd.DataFrame,
    year: Optional[int] = None,
) -> RegularizationAnalysis:
    """
    Fonction utilitaire pour détecter les régularisations.

    Args:
        df: DataFrame GL
        year: Année à analyser

    Returns:
        RegularizationAnalysis complet
    """
    detector = RegularizationDetector(df, year)
    return detector.get_full_analysis()


if __name__ == "__main__":
    print("RegularizationDetector - Détection des régularisations comptables")
    print("=" * 60)
    print("Usage:")
    print("  from gl_normalizer.regularization import detect_regularizations")
    print("  result = detect_regularizations(df, year=2024)")
    print("  print(f'Régularisations: {result.total_regularizations}')")
    print("  for r in result.regularizations[:10]:")
    print("      print(f'{r.compte}: {r.type.value} ({r.confidence:.0%})')")
