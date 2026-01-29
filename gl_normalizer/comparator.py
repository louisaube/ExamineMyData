"""
gl_normalizer/comparator.py
Comparaison inter-années avec normalisation

Compare deux périodes (N-1 vs N) en neutralisant les artefacts comptables
pour obtenir le run rate opérationnel réel.
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Tuple, Union
from dataclasses import dataclass, field
from pathlib import Path

from .loader import GLLoader, load_gl
from .classifier import GLClassifier, classify_gl
from .pnl_normalizer import PnLNormalizer, NormalizedPLResult, NormalizerConfig
from .drilldown import VariationDrilldown, AccountDrilldown


@dataclass
class YearComparison:
    """Résultat de la comparaison entre deux années"""

    year_n1: int
    year_n: int

    # Résultats normalisés pour chaque année
    result_n1: NormalizedPLResult
    result_n: NormalizedPLResult

    # Variations
    variation_brute: float
    variation_normalisee: float
    ecart_normalisation: float

    # Détails des ajustements
    ajustement_n1: float
    ajustement_n: float

    # Analyses drill-down
    top_variations: List[AccountDrilldown] = field(default_factory=list)

    @property
    def summary_dict(self) -> Dict:
        """Retourne un dictionnaire résumé"""
        return {
            "Période N-1": self.year_n1,
            "Période N": self.year_n,
            "Résultat brut N-1": self.result_n1.resultat_brut,
            "Résultat brut N": self.result_n.resultat_brut,
            "Variation brute": self.variation_brute,
            "Ajustement N-1": self.ajustement_n1,
            "Ajustement N": self.ajustement_n,
            "Résultat normalisé N-1": self.result_n1.resultat_normalise,
            "Résultat normalisé N": self.result_n.resultat_normalise,
            "Variation normalisée": self.variation_normalisee,
            "Écart (brut vs normalisé)": self.ecart_normalisation,
        }

    def __repr__(self) -> str:
        return (
            f"Comparaison {self.year_n1} vs {self.year_n}:\n"
            f"  Variation brute:      {self.variation_brute:>+12,.0f}€\n"
            f"  Variation normalisée: {self.variation_normalisee:>+12,.0f}€\n"
            f"  Écart (artefacts):    {self.ecart_normalisation:>+12,.0f}€"
        )


class GLComparator:
    """
    Comparateur de GL avec normalisation complète.

    Pipeline complet:
    1. Chargement et harmonisation des deux GL
    2. Classification des écritures
    3. Normalisation P&L pour chaque année
    4. Comparaison et analyse des variations
    """

    def __init__(
        self,
        source_n1: Union[str, Path, pd.DataFrame],
        source_n: Union[str, Path, pd.DataFrame],
        year_n1: Optional[int] = None,
        year_n: Optional[int] = None,
        config: Optional[NormalizerConfig] = None,
    ):
        """
        Args:
            source_n1: Fichier GL N-1 ou DataFrame déjà chargé
            source_n: Fichier GL N ou DataFrame déjà chargé
            year_n1: Année N-1 (auto-détectée si non fournie)
            year_n: Année N (auto-détectée si non fournie)
            config: Configuration des seuils
        """
        self.config = config or NormalizerConfig()

        # Charger les données
        self.df_n1_raw = self._load_source(source_n1)
        self.df_n_raw = self._load_source(source_n)

        # Classifier
        self.df_n1 = classify_gl(self.df_n1_raw)
        self.df_n = classify_gl(self.df_n_raw)

        # Déterminer les années
        self.year_n1 = year_n1 or self._detect_year(self.df_n1)
        self.year_n = year_n or self._detect_year(self.df_n)

        # Créer les normaliseurs
        self.normalizer_n1 = PnLNormalizer(self.df_n1, self.year_n1, self.config)
        self.normalizer_n = PnLNormalizer(self.df_n, self.year_n, self.config)

    def _load_source(self, source: Union[str, Path, pd.DataFrame]) -> pd.DataFrame:
        """Charge une source (fichier ou DataFrame)"""
        if isinstance(source, pd.DataFrame):
            return source.copy()
        return load_gl(source)

    def _detect_year(self, df: pd.DataFrame) -> int:
        """Détecte l'année principale d'un GL"""
        if "annee" in df.columns:
            return int(df["annee"].mode().iloc[0])
        elif "date" in df.columns:
            dates = pd.to_datetime(df["date"], errors="coerce")
            return int(dates.dt.year.mode().iloc[0])
        raise ValueError("Impossible de détecter l'année du GL")

    def compare(
        self,
        with_drilldown: bool = True,
        top_n_variations: int = 10
    ) -> YearComparison:
        """
        Compare les deux années avec normalisation.

        Args:
            with_drilldown: Inclure l'analyse drill-down des variations
            top_n_variations: Nombre de comptes à analyser en drill-down

        Returns:
            Résultat complet de la comparaison
        """
        # Normaliser chaque année
        result_n1 = self.normalizer_n1.compute_normalized_december()
        result_n = self.normalizer_n.compute_normalized_december()

        # Calculer les variations
        variation_brute = result_n.resultat_brut - result_n1.resultat_brut
        variation_normalisee = result_n.resultat_normalise - result_n1.resultat_normalise
        ecart_normalisation = variation_brute - variation_normalisee

        # Drill-down sur les top variations
        top_variations = []
        if with_drilldown:
            drilldown = VariationDrilldown(
                self.df_n1, self.df_n,
                self.year_n1, self.year_n
            )
            top_variations = drilldown.analyze_top_variations(n=top_n_variations)

        return YearComparison(
            year_n1=self.year_n1,
            year_n=self.year_n,
            result_n1=result_n1,
            result_n=result_n,
            variation_brute=variation_brute,
            variation_normalisee=variation_normalisee,
            ecart_normalisation=ecart_normalisation,
            ajustement_n1=result_n1.total_ajustement,
            ajustement_n=result_n.total_ajustement,
            top_variations=top_variations,
        )

    def get_reconciliation_table(self, comparison: Optional[YearComparison] = None) -> pd.DataFrame:
        """
        Génère un tableau de réconciliation brut vs normalisé.

        Args:
            comparison: Résultat de compare() (optionnel, sinon recalcule)

        Returns:
            DataFrame de réconciliation
        """
        if comparison is None:
            comparison = self.compare(with_drilldown=False)

        data = [
            {
                "Élément": f"Résultat brut {comparison.year_n1}",
                "Montant": comparison.result_n1.resultat_brut,
            },
            {
                "Élément": f"Ajustement normalisation {comparison.year_n1}",
                "Montant": comparison.ajustement_n1,
            },
            {
                "Élément": f"Résultat normalisé {comparison.year_n1}",
                "Montant": comparison.result_n1.resultat_normalise,
            },
            {"Élément": "---", "Montant": 0},
            {
                "Élément": f"Résultat brut {comparison.year_n}",
                "Montant": comparison.result_n.resultat_brut,
            },
            {
                "Élément": f"Ajustement normalisation {comparison.year_n}",
                "Montant": comparison.ajustement_n,
            },
            {
                "Élément": f"Résultat normalisé {comparison.year_n}",
                "Montant": comparison.result_n.resultat_normalise,
            },
            {"Élément": "---", "Montant": 0},
            {
                "Élément": "Variation brute (comptable)",
                "Montant": comparison.variation_brute,
            },
            {
                "Élément": "Variation normalisée (run rate)",
                "Montant": comparison.variation_normalisee,
            },
            {
                "Élément": "Écart = artefacts comptables",
                "Montant": comparison.ecart_normalisation,
            },
        ]

        return pd.DataFrame(data)

    def get_provisions_comparison(self) -> pd.DataFrame:
        """
        Compare les provisions identifiées entre N-1 et N.

        Returns:
            DataFrame avec provisions des deux années
        """
        prov_n1 = self.normalizer_n1.analyze_provisions()
        prov_n = self.normalizer_n.analyze_provisions()

        # Convertir en DataFrames
        def prov_to_df(provisions, year):
            return pd.DataFrame([
                {
                    "Année": year,
                    "Compte": p.compte,
                    "Libellé": p.libelle_compte,
                    "Total annuel": p.total_annuel,
                    "Run rate": p.run_rate_mensuel,
                    "Décembre brut": p.decembre_brut,
                    "Décembre normalisé": p.decembre_normalise,
                    "Impact": p.ecart_decembre,
                }
                for p in provisions
            ])

        df_n1 = prov_to_df(prov_n1, self.year_n1)
        df_n = prov_to_df(prov_n, self.year_n)

        return pd.concat([df_n1, df_n], ignore_index=True)

    def get_anomalies_comparison(self) -> pd.DataFrame:
        """
        Compare les anomalies détectées entre N-1 et N.

        Returns:
            DataFrame avec anomalies des deux années
        """
        anom_n1 = self.normalizer_n1.detect_anomalies()
        anom_n = self.normalizer_n.detect_anomalies()

        # Convertir en DataFrames
        def anom_to_df(anomalies, year):
            return pd.DataFrame([
                {
                    "Année": year,
                    "Compte": a.compte,
                    "Libellé": a.libelle_compte,
                    "Mois": a.mois,
                    "Montant": a.montant_mois,
                    "Moyenne": a.moyenne_annuelle,
                    "Z-score": a.z_score,
                    "Nature": a.nature,
                }
                for a in anomalies
            ])

        df_n1 = anom_to_df(anom_n1, self.year_n1)
        df_n = anom_to_df(anom_n, self.year_n)

        return pd.concat([df_n1, df_n], ignore_index=True)

    def format_comparison_report(self, comparison: Optional[YearComparison] = None) -> str:
        """
        Génère un rapport textuel de la comparaison.

        Args:
            comparison: Résultat de compare() (optionnel)

        Returns:
            Rapport formaté
        """
        if comparison is None:
            comparison = self.compare()

        lines = [
            "=" * 70,
            f"COMPARAISON P&L NORMALISÉ: {comparison.year_n1} vs {comparison.year_n}",
            "=" * 70,
            "",
            "RÉSUMÉ",
            "-" * 40,
            f"                          {comparison.year_n1:>12}   {comparison.year_n:>12}   {'Variation':>12}",
            f"Résultat brut         {comparison.result_n1.resultat_brut:>12,.0f}€  {comparison.result_n.resultat_brut:>12,.0f}€  {comparison.variation_brute:>+12,.0f}€",
            f"Ajustement            {comparison.ajustement_n1:>12,.0f}€  {comparison.ajustement_n:>12,.0f}€",
            f"Résultat normalisé    {comparison.result_n1.resultat_normalise:>12,.0f}€  {comparison.result_n.resultat_normalise:>12,.0f}€  {comparison.variation_normalisee:>+12,.0f}€",
            "",
            "RÉCONCILIATION",
            "-" * 40,
            f"Variation apparente (comptable):  {comparison.variation_brute:>+15,.0f}€",
            f"Variation réelle (run rate):      {comparison.variation_normalisee:>+15,.0f}€",
            f"Écart = artefacts comptables:     {comparison.ecart_normalisation:>+15,.0f}€",
            "",
        ]

        # Top provisions N-1
        if comparison.result_n1.provisions:
            lines.append(f"TOP PROVISIONS {comparison.year_n1}")
            lines.append("-" * 40)
            for p in comparison.result_n1.provisions[:5]:
                lines.append(f"  {p.compte} {p.libelle_compte[:30]:30} Impact: {p.ecart_decembre:>+10,.0f}€")
            lines.append("")

        # Top provisions N
        if comparison.result_n.provisions:
            lines.append(f"TOP PROVISIONS {comparison.year_n}")
            lines.append("-" * 40)
            for p in comparison.result_n.provisions[:5]:
                lines.append(f"  {p.compte} {p.libelle_compte[:30]:30} Impact: {p.ecart_decembre:>+10,.0f}€")
            lines.append("")

        # Top variations
        if comparison.top_variations:
            lines.append("TOP VARIATIONS PAR COMPTE")
            lines.append("-" * 40)
            for v in comparison.top_variations[:5]:
                lines.append(f"  {v.compte} {v.libelle_compte[:30]:30} {v.variation:>+12,.0f}€")

        return "\n".join(lines)


def compare_years(
    source_n1: Union[str, Path, pd.DataFrame],
    source_n: Union[str, Path, pd.DataFrame],
    year_n1: Optional[int] = None,
    year_n: Optional[int] = None,
    config: Optional[NormalizerConfig] = None,
) -> YearComparison:
    """
    Fonction utilitaire pour comparer rapidement deux années.

    Args:
        source_n1: GL année N-1
        source_n: GL année N
        year_n1: Année N-1 (optionnel)
        year_n: Année N (optionnel)
        config: Configuration (optionnel)

    Returns:
        Résultat de comparaison
    """
    comparator = GLComparator(source_n1, source_n, year_n1, year_n, config)
    return comparator.compare()


if __name__ == "__main__":
    print("GLComparator - Comparaison inter-années avec normalisation")
    print("Usage:")
    print("  from gl_normalizer.comparator import GLComparator, compare_years")
    print("  comparison = compare_years('GL_2024.xlsx', 'GL_2025.xlsx')")
    print("  print(comparison)")
