"""
gl_normalizer/detector.py
Détecteurs d'anomalies avancés pour GL

Fournit:
- Détection de concentrations (journal, période, fournisseur)
- Détection de montants ronds
- Détection de séquences (numéros de pièce)
- Score global d'anomalie
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from enum import Enum


class AnomalyType(Enum):
    """Types d'anomalies détectées"""
    CONCENTRATION_MOIS = "concentration_mois"
    CONCENTRATION_JOURNAL = "concentration_journal"
    CONCENTRATION_COMPTE = "concentration_compte"
    MONTANT_ROND = "montant_rond"
    MONTANT_REPETITIF = "montant_repetitif"
    SEQUENCE_MANQUANTE = "sequence_manquante"
    RATIO_SUSPECT = "ratio_suspect"
    ZSCORE_ELEVE = "zscore_eleve"


class Severity(Enum):
    """Niveau de sévérité"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ConcentrationAnomaly:
    """Anomalie de concentration détectée"""
    type: AnomalyType
    dimension: str              # Ex: "journal", "periode", "compte"
    value: str                  # Ex: "OD", "2024-12", "631000"
    percentage: float           # % de concentration
    amount: float               # Montant concerné
    count: int                  # Nombre d'écritures
    threshold: float            # Seuil utilisé
    severity: Severity
    details: str = ""

    def __repr__(self) -> str:
        return (
            f"[{self.severity.value.upper()}] {self.type.value}: "
            f"{self.dimension}={self.value} ({self.percentage:.1f}%)"
        )


@dataclass
class RoundAmountAnomaly:
    """Anomalie de montant rond détectée"""
    compte: str
    libelle_compte: str
    amount: float
    roundness_type: str         # "exact_thousand", "exact_hundred", etc.
    occurrences: int
    total_amount: float
    pct_of_account: float
    severity: Severity
    sample_libelles: List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"[{self.severity.value.upper()}] Montant rond {self.roundness_type}: "
            f"{self.amount:,.0f}€ x{self.occurrences} ({self.pct_of_account:.1f}%)"
        )


@dataclass
class DetectionResult:
    """Résultat complet de la détection"""
    concentrations: List[ConcentrationAnomaly]
    round_amounts: List[RoundAmountAnomaly]
    total_anomalies: int
    risk_score: float           # Score global 0-1
    summary: Dict[str, int]     # Nombre par type


class ConcentrationDetector:
    """
    Détecte les concentrations anormales dans les données.

    Une concentration est suspecte quand un pourcentage élevé
    d'écritures/montants est concentré sur une dimension.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        year: Optional[int] = None,
        threshold_pct: float = 50.0,
    ):
        """
        Args:
            df: DataFrame GL
            year: Année à analyser
            threshold_pct: Seuil de concentration en %
        """
        self.df = df.copy()
        self.year = year
        self.threshold_pct = threshold_pct

        if year is not None:
            self.df = self.df[self.df["annee"] == year]

    def detect_month_concentration(self) -> List[ConcentrationAnomaly]:
        """
        Détecte les concentrations par mois.

        Un mois avec >50% des mouvements est suspect.
        """
        anomalies = []

        if "periode" not in self.df.columns:
            return anomalies

        # Concentration par montant
        monthly = self.df.groupby("periode")["montant"].agg(["sum", "count"])
        total_amount = monthly["sum"].abs().sum()
        total_count = monthly["count"].sum()

        for periode, row in monthly.iterrows():
            pct_amount = (abs(row["sum"]) / total_amount * 100) if total_amount > 0 else 0
            pct_count = (row["count"] / total_count * 100) if total_count > 0 else 0

            # Concentration par montant
            if pct_amount > self.threshold_pct:
                severity = self._get_severity(pct_amount)
                anomalies.append(ConcentrationAnomaly(
                    type=AnomalyType.CONCENTRATION_MOIS,
                    dimension="periode",
                    value=str(periode),
                    percentage=pct_amount,
                    amount=abs(row["sum"]),
                    count=int(row["count"]),
                    threshold=self.threshold_pct,
                    severity=severity,
                    details=f"{pct_amount:.1f}% du montant total, {pct_count:.1f}% des écritures",
                ))

        return anomalies

    def detect_journal_concentration(self) -> List[ConcentrationAnomaly]:
        """
        Détecte les concentrations par journal.

        Focus sur les journaux OD avec forte concentration en fin d'année.
        """
        anomalies = []

        if "journal" not in self.df.columns:
            return anomalies

        # Concentration globale par journal
        by_journal = self.df.groupby("journal")["montant"].agg(["sum", "count"])
        total_amount = by_journal["sum"].abs().sum()

        for journal, row in by_journal.iterrows():
            pct = (abs(row["sum"]) / total_amount * 100) if total_amount > 0 else 0

            # Seuil plus bas pour journaux OD (souvent suspects)
            threshold = self.threshold_pct * 0.7 if str(journal).upper() in ["OD", "AN", "SIT"] else self.threshold_pct

            if pct > threshold:
                severity = self._get_severity(pct)
                anomalies.append(ConcentrationAnomaly(
                    type=AnomalyType.CONCENTRATION_JOURNAL,
                    dimension="journal",
                    value=str(journal),
                    percentage=pct,
                    amount=abs(row["sum"]),
                    count=int(row["count"]),
                    threshold=threshold,
                    severity=severity,
                    details=f"Journal {journal}: {pct:.1f}% du total",
                ))

        # Concentration OD en décembre
        if "periode" in self.df.columns:
            year = self.year or self.df["annee"].mode().iloc[0]
            dec_key = f"{year}-12"

            df_dec = self.df[self.df["periode"] == dec_key]
            df_od = df_dec[df_dec["journal"].str.upper().isin(["OD", "AN", "SIT"])]

            if len(df_dec) > 0:
                pct_od_dec = len(df_od) / len(df_dec) * 100
                if pct_od_dec > 40:  # >40% d'OD en décembre est suspect
                    anomalies.append(ConcentrationAnomaly(
                        type=AnomalyType.CONCENTRATION_JOURNAL,
                        dimension="journal_decembre",
                        value="OD en décembre",
                        percentage=pct_od_dec,
                        amount=df_od["montant"].abs().sum(),
                        count=len(df_od),
                        threshold=40,
                        severity=Severity.HIGH if pct_od_dec > 60 else Severity.MEDIUM,
                        details=f"{pct_od_dec:.1f}% des écritures de décembre sont des OD",
                    ))

        return anomalies

    def detect_account_concentration(self, min_amount: float = 10000) -> List[ConcentrationAnomaly]:
        """
        Détecte les comptes avec concentration anormale sur un mois.

        Args:
            min_amount: Montant minimum pour considérer
        """
        anomalies = []

        if "compte" not in self.df.columns or "periode" not in self.df.columns:
            return anomalies

        # Analyser par compte
        for compte in self.df["compte"].unique():
            df_compte = self.df[self.df["compte"] == compte]
            total = df_compte["montant"].abs().sum()

            if total < min_amount:
                continue

            # Distribution mensuelle
            monthly = df_compte.groupby("periode")["montant"].sum().abs()

            for periode, montant in monthly.items():
                pct = (montant / total * 100) if total > 0 else 0

                if pct > 80:  # >80% sur un mois est très suspect
                    libelle = df_compte["libelle_compte"].iloc[0] if "libelle_compte" in df_compte else ""
                    severity = Severity.CRITICAL if pct > 95 else Severity.HIGH

                    anomalies.append(ConcentrationAnomaly(
                        type=AnomalyType.CONCENTRATION_COMPTE,
                        dimension="compte_periode",
                        value=f"{compte} ({periode})",
                        percentage=pct,
                        amount=montant,
                        count=len(df_compte[df_compte["periode"] == periode]),
                        threshold=80,
                        severity=severity,
                        details=f"Compte {compte} ({libelle}): {pct:.1f}% en {periode}",
                    ))

        return anomalies

    def detect_all(self) -> List[ConcentrationAnomaly]:
        """Détecte toutes les concentrations"""
        anomalies = []
        anomalies.extend(self.detect_month_concentration())
        anomalies.extend(self.detect_journal_concentration())
        anomalies.extend(self.detect_account_concentration())

        # Trier par sévérité
        severity_order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
        anomalies.sort(key=lambda x: (severity_order[x.severity], -x.percentage))

        return anomalies

    def _get_severity(self, pct: float) -> Severity:
        """Détermine la sévérité selon le pourcentage"""
        if pct > 90:
            return Severity.CRITICAL
        elif pct > 70:
            return Severity.HIGH
        elif pct > 50:
            return Severity.MEDIUM
        else:
            return Severity.LOW


class RoundAmountDetector:
    """
    Détecte les montants ronds suspects.

    Les montants ronds (1000, 5000, 10000, etc.) peuvent indiquer
    des provisions estimées, des écritures d'ajustement, ou des fraudes.
    """

    # Montants ronds typiques à surveiller
    ROUND_AMOUNTS = [
        (1000, "thousand"),
        (5000, "5k"),
        (10000, "10k"),
        (25000, "25k"),
        (50000, "50k"),
        (100000, "100k"),
        (250000, "250k"),
        (500000, "500k"),
        (1000000, "million"),
    ]

    def __init__(
        self,
        df: pd.DataFrame,
        year: Optional[int] = None,
        tolerance: float = 0.01,  # 1% tolerance
        min_occurrences: int = 2,
    ):
        """
        Args:
            df: DataFrame GL
            year: Année à analyser
            tolerance: Tolérance pour considérer un montant comme rond
            min_occurrences: Nombre minimum d'occurrences pour signaler
        """
        self.df = df.copy()
        self.year = year
        self.tolerance = tolerance
        self.min_occurrences = min_occurrences

        if year is not None:
            self.df = self.df[self.df["annee"] == year]

    def detect(self) -> List[RoundAmountAnomaly]:
        """
        Détecte les montants ronds par compte.

        Returns:
            Liste des anomalies de montants ronds
        """
        anomalies = []

        if "compte" not in self.df.columns:
            return anomalies

        # Analyser par compte
        for compte in self.df["compte"].unique():
            df_compte = self.df[self.df["compte"] == compte]
            total_compte = df_compte["montant"].abs().sum()

            if total_compte == 0:
                continue

            libelle = df_compte["libelle_compte"].iloc[0] if "libelle_compte" in df_compte else ""

            # Vérifier chaque type de montant rond
            for round_val, round_type in self.ROUND_AMOUNTS:
                # Trouver les écritures proches du montant rond
                matches = df_compte[
                    (df_compte["montant"].abs() >= round_val * (1 - self.tolerance)) &
                    (df_compte["montant"].abs() <= round_val * (1 + self.tolerance))
                ]

                if len(matches) >= self.min_occurrences:
                    total_round = matches["montant"].abs().sum()
                    pct = (total_round / total_compte * 100) if total_compte > 0 else 0

                    # Sévérité basée sur le nombre et le pourcentage
                    if pct > 50 or len(matches) > 10:
                        severity = Severity.HIGH
                    elif pct > 30 or len(matches) > 5:
                        severity = Severity.MEDIUM
                    else:
                        severity = Severity.LOW

                    # Échantillon de libellés
                    sample_libelles = matches["libelle"].head(3).tolist() if "libelle" in matches else []

                    anomalies.append(RoundAmountAnomaly(
                        compte=str(compte),
                        libelle_compte=str(libelle),
                        amount=round_val,
                        roundness_type=round_type,
                        occurrences=len(matches),
                        total_amount=total_round,
                        pct_of_account=pct,
                        severity=severity,
                        sample_libelles=sample_libelles,
                    ))

        # Détecter aussi les montants exactement répétés
        anomalies.extend(self._detect_repetitive_amounts())

        # Trier par sévérité et pourcentage
        severity_order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
        anomalies.sort(key=lambda x: (severity_order[x.severity], -x.pct_of_account))

        return anomalies

    def _detect_repetitive_amounts(self) -> List[RoundAmountAnomaly]:
        """Détecte les montants exactement répétés (même valeur multiple fois)"""
        anomalies = []

        # Grouper par montant exact
        amount_counts = self.df.groupby("montant").agg({
            "compte": "first",
            "libelle_compte": lambda x: x.iloc[0] if len(x) > 0 else "",
            "libelle": lambda x: list(x.head(3)),
        }).reset_index()

        amount_counts["count"] = self.df.groupby("montant").size().values

        # Filtrer les répétitions suspectes
        for _, row in amount_counts.iterrows():
            if row["count"] >= 3 and abs(row["montant"]) > 1000:
                # Vérifier si c'est déjà un montant rond standard
                is_standard_round = any(
                    abs(abs(row["montant"]) - r[0]) < r[0] * 0.01
                    for r in self.ROUND_AMOUNTS
                )

                if not is_standard_round:
                    total = abs(row["montant"]) * row["count"]
                    anomalies.append(RoundAmountAnomaly(
                        compte=str(row["compte"]),
                        libelle_compte=str(row["libelle_compte"]),
                        amount=abs(row["montant"]),
                        roundness_type="repetitif",
                        occurrences=int(row["count"]),
                        total_amount=total,
                        pct_of_account=0,  # Pas calculable ici
                        severity=Severity.MEDIUM if row["count"] > 5 else Severity.LOW,
                        sample_libelles=row["libelle"] if isinstance(row["libelle"], list) else [],
                    ))

        return anomalies


class AnomalyDetector:
    """
    Détecteur d'anomalies principal combinant toutes les méthodes.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        year: Optional[int] = None,
    ):
        """
        Args:
            df: DataFrame GL
            year: Année à analyser
        """
        self.df = df.copy()
        self.year = year

        if year is not None:
            self.df = self.df[self.df["annee"] == year]

    def detect_all(self) -> DetectionResult:
        """
        Exécute tous les détecteurs et retourne un résultat consolidé.

        Returns:
            DetectionResult avec toutes les anomalies
        """
        # Détection des concentrations
        conc_detector = ConcentrationDetector(self.df, self.year)
        concentrations = conc_detector.detect_all()

        # Détection des montants ronds
        round_detector = RoundAmountDetector(self.df, self.year)
        round_amounts = round_detector.detect()

        # Compter par type
        summary = {
            "concentration_mois": len([c for c in concentrations if c.type == AnomalyType.CONCENTRATION_MOIS]),
            "concentration_journal": len([c for c in concentrations if c.type == AnomalyType.CONCENTRATION_JOURNAL]),
            "concentration_compte": len([c for c in concentrations if c.type == AnomalyType.CONCENTRATION_COMPTE]),
            "montants_ronds": len(round_amounts),
        }

        total = len(concentrations) + len(round_amounts)

        # Score de risque global
        risk_score = self._compute_risk_score(concentrations, round_amounts)

        return DetectionResult(
            concentrations=concentrations,
            round_amounts=round_amounts,
            total_anomalies=total,
            risk_score=risk_score,
            summary=summary,
        )

    def _compute_risk_score(
        self,
        concentrations: List[ConcentrationAnomaly],
        round_amounts: List[RoundAmountAnomaly],
    ) -> float:
        """Calcule un score de risque global entre 0 et 1"""
        score = 0.0

        # Points pour concentrations
        for c in concentrations:
            if c.severity == Severity.CRITICAL:
                score += 0.25
            elif c.severity == Severity.HIGH:
                score += 0.15
            elif c.severity == Severity.MEDIUM:
                score += 0.08
            else:
                score += 0.03

        # Points pour montants ronds
        for r in round_amounts:
            if r.severity == Severity.HIGH:
                score += 0.10
            elif r.severity == Severity.MEDIUM:
                score += 0.05
            else:
                score += 0.02

        return min(score, 1.0)

    def get_summary(self) -> Dict:
        """Retourne un résumé rapide"""
        result = self.detect_all()
        return {
            "total_anomalies": result.total_anomalies,
            "risk_score": result.risk_score,
            "by_type": result.summary,
            "critical_count": len([c for c in result.concentrations if c.severity == Severity.CRITICAL]),
            "high_count": len([c for c in result.concentrations if c.severity == Severity.HIGH]) +
                         len([r for r in result.round_amounts if r.severity == Severity.HIGH]),
        }


def detect_anomalies(df: pd.DataFrame, year: Optional[int] = None) -> DetectionResult:
    """
    Fonction utilitaire pour détecter les anomalies.

    Args:
        df: DataFrame GL
        year: Année à analyser

    Returns:
        DetectionResult complet
    """
    detector = AnomalyDetector(df, year)
    return detector.detect_all()


if __name__ == "__main__":
    print("Detector - Détection d'anomalies avancée")
    print("=" * 50)
    print("Usage:")
    print("  from gl_normalizer.detector import detect_anomalies")
    print("  result = detect_anomalies(df, year=2024)")
    print("  print(f'Risk score: {result.risk_score:.2f}')")
    print("  for c in result.concentrations:")
    print("      print(c)")
