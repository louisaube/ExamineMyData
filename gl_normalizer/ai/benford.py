"""
Benford's Law Analysis
======================

Détection d'anomalies basée sur la loi de Benford.
La loi de Benford prédit la distribution des premiers chiffres dans les données naturelles.

Principe:
- Le chiffre 1 apparaît en première position ~30.1% du temps
- Le chiffre 9 apparaît en première position ~4.6% du temps
- Les écarts significatifs peuvent indiquer une manipulation

Usage:
    analyzer = BenfordAnalyzer(df)
    results = analyzer.analyze()
    suspicious = analyzer.get_suspicious_entries()
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from scipy import stats


# Distribution théorique de Benford pour le premier chiffre
BENFORD_FIRST_DIGIT = {
    1: 0.301,
    2: 0.176,
    3: 0.125,
    4: 0.097,
    5: 0.079,
    6: 0.067,
    7: 0.058,
    8: 0.051,
    9: 0.046,
}

# Distribution théorique pour le deuxième chiffre
BENFORD_SECOND_DIGIT = {
    0: 0.120,
    1: 0.114,
    2: 0.109,
    3: 0.104,
    4: 0.100,
    5: 0.097,
    6: 0.093,
    7: 0.090,
    8: 0.088,
    9: 0.085,
}


@dataclass
class BenfordResult:
    """Résultat de l'analyse Benford"""
    digit: int
    expected_pct: float
    observed_pct: float
    count: int
    deviation: float  # Écart en points de pourcentage
    z_score: float
    is_suspicious: bool


@dataclass
class BenfordAnalysis:
    """Analyse complète Benford"""
    first_digit_results: List[BenfordResult]
    second_digit_results: List[BenfordResult]
    chi_square_first: float
    chi_square_second: float
    p_value_first: float
    p_value_second: float
    mad_first: float  # Mean Absolute Deviation
    mad_second: float
    conformity_first: str  # "Acceptable", "Marginally Acceptable", "Non-conforming"
    conformity_second: str
    total_entries: int
    suspicious_amounts: List[float]


class BenfordAnalyzer:
    """
    Analyseur basé sur la loi de Benford.

    Détecte les anomalies dans la distribution des premiers chiffres
    des montants comptables.
    """

    # Seuils MAD (Mean Absolute Deviation) selon Nigrini
    MAD_THRESHOLDS = {
        "close_conformity": 0.006,
        "acceptable": 0.012,
        "marginally_acceptable": 0.015,
    }

    def __init__(
        self,
        df: pd.DataFrame,
        amount_column: str = "montant",
        min_entries: int = 100,
    ):
        """
        Initialise l'analyseur Benford.

        Args:
            df: DataFrame avec les écritures comptables
            amount_column: Colonne contenant les montants
            min_entries: Nombre minimum d'écritures pour analyse fiable
        """
        self.df = df.copy()
        self.amount_column = amount_column
        self.min_entries = min_entries

        # Préparer les montants (valeurs absolues, exclure zéros)
        self._prepare_amounts()

    def _prepare_amounts(self):
        """Prépare les montants pour l'analyse"""
        # Prendre les valeurs absolues et exclure les zéros
        amounts = self.df[self.amount_column].abs()
        self.amounts = amounts[amounts > 0].values
        self.n = len(self.amounts)

    def _extract_first_digit(self, number: float) -> int:
        """Extrait le premier chiffre significatif"""
        if number <= 0:
            return 0
        # Convertir en string et prendre le premier chiffre non-zéro
        s = f"{number:.10f}".lstrip("0").lstrip(".")
        if s:
            return int(s[0])
        return 0

    def _extract_second_digit(self, number: float) -> int:
        """Extrait le deuxième chiffre significatif"""
        if number <= 0:
            return 0
        s = f"{number:.10f}".lstrip("0").lstrip(".")
        if len(s) >= 2:
            # Ignorer le point décimal
            digits = s.replace(".", "")
            if len(digits) >= 2:
                return int(digits[1])
        return 0

    def _calculate_mad(
        self,
        observed: Dict[int, float],
        expected: Dict[int, float],
    ) -> float:
        """Calcule le Mean Absolute Deviation"""
        deviations = []
        for digit in expected:
            obs = observed.get(digit, 0)
            exp = expected[digit]
            deviations.append(abs(obs - exp))
        return np.mean(deviations)

    def _get_conformity_level(self, mad: float) -> str:
        """Détermine le niveau de conformité basé sur le MAD"""
        if mad <= self.MAD_THRESHOLDS["close_conformity"]:
            return "Close Conformity"
        elif mad <= self.MAD_THRESHOLDS["acceptable"]:
            return "Acceptable"
        elif mad <= self.MAD_THRESHOLDS["marginally_acceptable"]:
            return "Marginally Acceptable"
        else:
            return "Non-conforming"

    def analyze(self) -> BenfordAnalysis:
        """
        Effectue l'analyse Benford complète.

        Returns:
            BenfordAnalysis avec tous les résultats
        """
        if self.n < self.min_entries:
            raise ValueError(
                f"Insuffisant: {self.n} écritures (min: {self.min_entries})"
            )

        # Extraire les chiffres
        first_digits = [self._extract_first_digit(a) for a in self.amounts]
        second_digits = [self._extract_second_digit(a) for a in self.amounts]

        # Compter les occurrences
        first_counts = pd.Series(first_digits).value_counts()
        second_counts = pd.Series(second_digits).value_counts()

        # Calculer les pourcentages observés
        first_observed = {d: first_counts.get(d, 0) / self.n for d in range(1, 10)}
        second_observed = {d: second_counts.get(d, 0) / self.n for d in range(0, 10)}

        # Analyser premier chiffre
        first_results = []
        for digit in range(1, 10):
            expected = BENFORD_FIRST_DIGIT[digit]
            observed = first_observed.get(digit, 0)
            count = first_counts.get(digit, 0)
            deviation = observed - expected

            # Z-score pour ce chiffre
            std_error = np.sqrt(expected * (1 - expected) / self.n)
            z_score = deviation / std_error if std_error > 0 else 0

            first_results.append(BenfordResult(
                digit=digit,
                expected_pct=expected * 100,
                observed_pct=observed * 100,
                count=count,
                deviation=deviation * 100,
                z_score=z_score,
                is_suspicious=abs(z_score) > 2.0,  # Seuil à 2 sigma
            ))

        # Analyser deuxième chiffre
        second_results = []
        for digit in range(0, 10):
            expected = BENFORD_SECOND_DIGIT[digit]
            observed = second_observed.get(digit, 0)
            count = second_counts.get(digit, 0)
            deviation = observed - expected

            std_error = np.sqrt(expected * (1 - expected) / self.n)
            z_score = deviation / std_error if std_error > 0 else 0

            second_results.append(BenfordResult(
                digit=digit,
                expected_pct=expected * 100,
                observed_pct=observed * 100,
                count=count,
                deviation=deviation * 100,
                z_score=z_score,
                is_suspicious=abs(z_score) > 2.0,
            ))

        # Test Chi-carré
        first_expected_counts = [BENFORD_FIRST_DIGIT[d] * self.n for d in range(1, 10)]
        first_observed_counts = [first_counts.get(d, 0) for d in range(1, 10)]
        chi2_first, p_first = stats.chisquare(first_observed_counts, first_expected_counts)

        second_expected_counts = [BENFORD_SECOND_DIGIT[d] * self.n for d in range(0, 10)]
        second_observed_counts = [second_counts.get(d, 0) for d in range(0, 10)]
        chi2_second, p_second = stats.chisquare(second_observed_counts, second_expected_counts)

        # MAD
        mad_first = self._calculate_mad(first_observed, BENFORD_FIRST_DIGIT)
        mad_second = self._calculate_mad(second_observed, BENFORD_SECOND_DIGIT)

        # Identifier les montants suspects (contribuant aux déviations)
        suspicious_amounts = self._identify_suspicious_amounts(first_results)

        return BenfordAnalysis(
            first_digit_results=first_results,
            second_digit_results=second_results,
            chi_square_first=chi2_first,
            chi_square_second=chi2_second,
            p_value_first=p_first,
            p_value_second=p_second,
            mad_first=mad_first,
            mad_second=mad_second,
            conformity_first=self._get_conformity_level(mad_first),
            conformity_second=self._get_conformity_level(mad_second),
            total_entries=self.n,
            suspicious_amounts=suspicious_amounts,
        )

    def _identify_suspicious_amounts(
        self,
        results: List[BenfordResult],
    ) -> List[float]:
        """Identifie les montants contribuant aux anomalies"""
        suspicious = []

        # Chiffres sur-représentés
        over_represented = [r.digit for r in results if r.z_score > 2.0]

        for amount in self.amounts:
            first_digit = self._extract_first_digit(amount)
            if first_digit in over_represented:
                suspicious.append(amount)

        # Retourner les plus fréquents
        if suspicious:
            return sorted(set(suspicious), reverse=True)[:100]
        return []

    def get_suspicious_entries(
        self,
        threshold_zscore: float = 2.0,
    ) -> pd.DataFrame:
        """
        Retourne les écritures avec montants suspects.

        Args:
            threshold_zscore: Seuil Z-score pour considérer un chiffre suspect

        Returns:
            DataFrame des écritures suspectes
        """
        analysis = self.analyze()

        # Chiffres suspects
        suspicious_digits = {
            r.digit for r in analysis.first_digit_results
            if abs(r.z_score) > threshold_zscore
        }

        if not suspicious_digits:
            return pd.DataFrame()

        # Filtrer les écritures
        mask = self.df[self.amount_column].abs().apply(
            lambda x: self._extract_first_digit(x) in suspicious_digits
        )

        result = self.df[mask].copy()
        result["benford_first_digit"] = result[self.amount_column].abs().apply(
            self._extract_first_digit
        )

        return result

    def detect_round_numbers(
        self,
        thresholds: List[int] = [100, 1000, 10000],
    ) -> pd.DataFrame:
        """
        Détecte les montants ronds (souvent suspects).

        Args:
            thresholds: Multiples à détecter

        Returns:
            DataFrame avec statistiques sur les montants ronds
        """
        results = []

        for threshold in thresholds:
            # Compter les montants divisibles par le seuil
            mask = (self.df[self.amount_column].abs() % threshold == 0) & \
                   (self.df[self.amount_column].abs() >= threshold)
            count = mask.sum()
            pct = count / self.n * 100 if self.n > 0 else 0

            results.append({
                "threshold": threshold,
                "count": count,
                "percentage": pct,
                "expected_pct": 1 / threshold * 100,  # Approximation
                "is_suspicious": pct > (1 / threshold * 100) * 3,  # 3x attendu
            })

        return pd.DataFrame(results)

    def summary(self) -> Dict:
        """Retourne un résumé de l'analyse"""
        try:
            analysis = self.analyze()
            return {
                "total_entries": analysis.total_entries,
                "conformity_first_digit": analysis.conformity_first,
                "conformity_second_digit": analysis.conformity_second,
                "mad_first": round(analysis.mad_first, 4),
                "mad_second": round(analysis.mad_second, 4),
                "chi_square_first": round(analysis.chi_square_first, 2),
                "p_value_first": round(analysis.p_value_first, 4),
                "suspicious_digits": [
                    r.digit for r in analysis.first_digit_results if r.is_suspicious
                ],
                "nb_suspicious_amounts": len(analysis.suspicious_amounts),
            }
        except ValueError as e:
            return {"error": str(e)}


def analyze_benford(
    df: pd.DataFrame,
    amount_column: str = "montant",
) -> BenfordAnalysis:
    """
    Fonction utilitaire pour analyser rapidement avec Benford.

    Args:
        df: DataFrame avec les écritures
        amount_column: Colonne des montants

    Returns:
        BenfordAnalysis
    """
    analyzer = BenfordAnalyzer(df, amount_column)
    return analyzer.analyze()
