"""
JournalClassifier - Classification des journaux comptables
==========================================================

STORY-202: Identifie la nature des journaux (OD, SAL, VTE, ACH, BQ).

Les journaux OD de décembre avec volume anormal sont des zones de vigilance.
"""

import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum


class JournalType(Enum):
    """Types de journaux comptables."""
    OD = "od"           # Opérations diverses - zone de vigilance
    PAIE = "paie"       # Paie / Salaires
    VENTE = "vente"     # Ventes / Facturation clients
    ACHAT = "achat"     # Achats / Fournisseurs
    BANQUE = "banque"   # Banque
    CAISSE = "caisse"   # Caisse
    ANOUVEAUX = "anouveaux"  # À-nouveaux
    AUTRE = "autre"     # Non classifié


@dataclass
class JournalInfo:
    """Information sur un journal."""
    code: str
    type: JournalType
    entries_count: int
    total_debit: float
    total_credit: float
    months_active: List[int]
    december_ratio: float  # % des écritures en décembre


# Patterns de codes journaux par type
JOURNAL_PATTERNS = {
    JournalType.OD: [
        "OD", "DIV", "DIVERS", "OPERATIONS", "OP", "AJUST",
        "REG", "REGUL", "REGULARISATION", "SITUATION", "SIT",
        "CLO", "CLOTURE", "EXTOURNE", "EXT",
    ],
    JournalType.PAIE: [
        "SAL", "SALAIRE", "SALAIRES", "PAI", "PAIE",
        "PAYE", "SOCIAL", "SOC", "RH",
    ],
    JournalType.VENTE: [
        "VTE", "VENTE", "VENTES", "FAC", "FACT", "FACTURATION",
        "CLI", "CLIENT", "CLIENTS", "CA",
    ],
    JournalType.ACHAT: [
        "ACH", "ACHAT", "ACHATS", "FRN", "FOURNISSEUR",
        "FOURNISSEURS", "FOURN", "HAF",
    ],
    JournalType.BANQUE: [
        "BQ", "BNQ", "BANQUE", "BANK", "BP", "CE", "CCP",
        "TRESORERIE", "TRES",
    ],
    JournalType.CAISSE: [
        "CAI", "CAISSE", "CASH", "ESP", "ESPECES",
    ],
    JournalType.ANOUVEAUX: [
        "AN", "ANOUV", "ANOUVEAUX", "A-NOUVEAUX", "OUV",
        "OUVERTURE", "RAN", "REPORT",
    ],
}


class JournalClassifier:
    """
    Classifie les journaux comptables.

    Usage:
        classifier = JournalClassifier()
        journal_type = classifier.classify("OD")  # JournalType.OD

        # Analyse complète
        analysis = classifier.analyze(df)
        od_journals = analysis.od_journals
    """

    def __init__(self):
        # Construire un index inversé pour lookup rapide
        self._pattern_index = {}
        for jtype, patterns in JOURNAL_PATTERNS.items():
            for pattern in patterns:
                self._pattern_index[pattern.upper()] = jtype

    def classify(self, journal_code: str) -> JournalType:
        """
        Classifie un code journal.

        Args:
            journal_code: Code du journal (ex: "OD", "SAL")

        Returns:
            JournalType correspondant
        """
        code = str(journal_code).strip().upper()

        # Match exact
        if code in self._pattern_index:
            return self._pattern_index[code]

        # Match partiel (le code contient un pattern)
        for pattern, jtype in self._pattern_index.items():
            if pattern in code or code in pattern:
                return jtype

        return JournalType.AUTRE

    def analyze(self, df: pd.DataFrame) -> "JournalAnalysis":
        """
        Analyse tous les journaux d'un GL.

        Args:
            df: DataFrame GL normalisé

        Returns:
            JournalAnalysis avec détails par journal
        """
        journals_info = {}

        for journal in df["journal"].unique():
            journal_df = df[df["journal"] == journal]

            # Calculer le ratio décembre
            total = len(journal_df)
            december_count = len(journal_df[journal_df["mois"] == 12])
            december_ratio = december_count / total if total > 0 else 0

            journals_info[journal] = JournalInfo(
                code=journal,
                type=self.classify(journal),
                entries_count=total,
                total_debit=journal_df["debit"].sum(),
                total_credit=journal_df["credit"].sum(),
                months_active=sorted(journal_df["mois"].unique().tolist()),
                december_ratio=december_ratio,
            )

        return JournalAnalysis(journals_info, df)

    def get_od_journals(self, df: pd.DataFrame) -> List[str]:
        """Retourne les codes des journaux de type OD."""
        return [
            j for j in df["journal"].unique()
            if self.classify(j) == JournalType.OD
        ]

    def is_od_journal(self, journal_code: str) -> bool:
        """Vérifie si un journal est de type OD."""
        return self.classify(journal_code) == JournalType.OD


@dataclass
class JournalAnalysis:
    """Résultat de l'analyse des journaux."""
    journals: Dict[str, JournalInfo]
    _df: pd.DataFrame

    @property
    def od_journals(self) -> List[str]:
        """Liste des journaux OD."""
        return [j for j, info in self.journals.items() if info.type == JournalType.OD]

    @property
    def od_december_spike(self) -> bool:
        """
        Détecte si les journaux OD ont un pic anormal en décembre.

        Règle: Volume OD décembre > 3x moyenne mensuelle jan-nov
        """
        od_journals = self.od_journals
        if not od_journals:
            return False

        od_df = self._df[self._df["journal"].isin(od_journals)]
        if len(od_df) == 0:
            return False

        # Compter par mois
        monthly = od_df.groupby("mois").size()

        # Moyenne jan-nov
        jan_nov = monthly[monthly.index != 12]
        avg_jan_nov = jan_nov.mean() if len(jan_nov) > 0 else 0

        # Volume décembre
        dec_volume = monthly.get(12, 0)

        # Spike si > 3x moyenne
        return dec_volume > (avg_jan_nov * 3) if avg_jan_nov > 0 else False

    @property
    def od_december_spike_ratio(self) -> float:
        """Ratio volume OD décembre / moyenne jan-nov."""
        od_journals = self.od_journals
        if not od_journals:
            return 0.0

        od_df = self._df[self._df["journal"].isin(od_journals)]
        if len(od_df) == 0:
            return 0.0

        monthly = od_df.groupby("mois").size()
        jan_nov = monthly[monthly.index != 12]
        avg_jan_nov = jan_nov.mean() if len(jan_nov) > 0 else 0
        dec_volume = monthly.get(12, 0)

        return dec_volume / avg_jan_nov if avg_jan_nov > 0 else 0.0

    def get_summary(self) -> Dict:
        """Résumé de l'analyse."""
        by_type = {}
        for info in self.journals.values():
            type_name = info.type.value
            if type_name not in by_type:
                by_type[type_name] = {"count": 0, "entries": 0}
            by_type[type_name]["count"] += 1
            by_type[type_name]["entries"] += info.entries_count

        return {
            "total_journals": len(self.journals),
            "by_type": by_type,
            "od_journals": self.od_journals,
            "od_december_spike": self.od_december_spike,
            "od_december_spike_ratio": round(self.od_december_spike_ratio, 1),
        }
