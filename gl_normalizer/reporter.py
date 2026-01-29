"""
gl_normalizer/reporter.py
Génération de rapports Excel et texte

Produit des rapports structurés avec:
- Synthèse brut vs normalisé
- Détail des ajustements par compte
- Anomalies EXCES / DEFICIT
- Drill-down sur les comptes clés
"""

import pandas as pd
from pathlib import Path
from typing import Optional, Union, List
from datetime import datetime

from .comparator import GLComparator, YearComparison
from .pnl_normalizer import NormalizedPLResult, ProvisionAnalysis, AnomalyDetection
from .drilldown import AccountDrilldown, VariationDrilldown


class ExcelReporter:
    """
    Générateur de rapports Excel multi-onglets.

    Onglets générés:
    - Synthèse: Vue d'ensemble de la comparaison
    - Réconciliation: Bridge brut → normalisé
    - Provisions N-1: Détail des ajustements N-1
    - Provisions N: Détail des ajustements N
    - Anomalies: Toutes les anomalies détectées
    - Drill-down: Analyse des top variations
    """

    def __init__(self, comparison: YearComparison, comparator: Optional[GLComparator] = None):
        """
        Args:
            comparison: Résultat de GLComparator.compare()
            comparator: Instance GLComparator (optionnel, pour données supplémentaires)
        """
        self.comparison = comparison
        self.comparator = comparator

    def generate(self, output_path: Union[str, Path]) -> Path:
        """
        Génère le rapport Excel complet.

        Args:
            output_path: Chemin du fichier de sortie

        Returns:
            Path du fichier créé
        """
        output_path = Path(output_path)

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            # Onglet Synthèse
            self._write_summary(writer)

            # Onglet Réconciliation
            self._write_reconciliation(writer)

            # Onglets Provisions
            self._write_provisions(writer, self.comparison.result_n1, self.comparison.year_n1)
            self._write_provisions(writer, self.comparison.result_n, self.comparison.year_n)

            # Onglet Anomalies
            self._write_anomalies(writer)

            # Onglet Drill-down
            if self.comparison.top_variations:
                self._write_drilldown(writer)

            # Onglet Données mensuelles
            if self.comparator:
                self._write_monthly_data(writer)

        return output_path

    def _write_summary(self, writer: pd.ExcelWriter):
        """Écrit l'onglet de synthèse"""
        data = [
            {"Métrique": "Période analysée", f"{self.comparison.year_n1}": self.comparison.year_n1, f"{self.comparison.year_n}": self.comparison.year_n, "Variation": ""},
            {"Métrique": "", f"{self.comparison.year_n1}": "", f"{self.comparison.year_n}": "", "Variation": ""},
            {"Métrique": "CHARGES BRUTES", f"{self.comparison.year_n1}": self.comparison.result_n1.charges_brutes, f"{self.comparison.year_n}": self.comparison.result_n.charges_brutes, "Variation": self.comparison.result_n.charges_brutes - self.comparison.result_n1.charges_brutes},
            {"Métrique": "PRODUITS BRUTS", f"{self.comparison.year_n1}": self.comparison.result_n1.produits_bruts, f"{self.comparison.year_n}": self.comparison.result_n.produits_bruts, "Variation": self.comparison.result_n.produits_bruts - self.comparison.result_n1.produits_bruts},
            {"Métrique": "RÉSULTAT BRUT", f"{self.comparison.year_n1}": self.comparison.result_n1.resultat_brut, f"{self.comparison.year_n}": self.comparison.result_n.resultat_brut, "Variation": self.comparison.variation_brute},
            {"Métrique": "", f"{self.comparison.year_n1}": "", f"{self.comparison.year_n}": "", "Variation": ""},
            {"Métrique": "Ajustement normalisation", f"{self.comparison.year_n1}": self.comparison.ajustement_n1, f"{self.comparison.year_n}": self.comparison.ajustement_n, "Variation": self.comparison.ajustement_n - self.comparison.ajustement_n1},
            {"Métrique": "Nb comptes ajustés", f"{self.comparison.year_n1}": self.comparison.result_n1.nb_comptes_ajustes, f"{self.comparison.year_n}": self.comparison.result_n.nb_comptes_ajustes, "Variation": ""},
            {"Métrique": "", f"{self.comparison.year_n1}": "", f"{self.comparison.year_n}": "", "Variation": ""},
            {"Métrique": "RÉSULTAT NORMALISÉ", f"{self.comparison.year_n1}": self.comparison.result_n1.resultat_normalise, f"{self.comparison.year_n}": self.comparison.result_n.resultat_normalise, "Variation": self.comparison.variation_normalisee},
            {"Métrique": "", f"{self.comparison.year_n1}": "", f"{self.comparison.year_n}": "", "Variation": ""},
            {"Métrique": "ÉCART BRUT vs NORMALISÉ", f"{self.comparison.year_n1}": "", f"{self.comparison.year_n}": "", "Variation": self.comparison.ecart_normalisation},
        ]

        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name="Synthèse", index=False)

    def _write_reconciliation(self, writer: pd.ExcelWriter):
        """Écrit l'onglet de réconciliation"""
        if self.comparator:
            df = self.comparator.get_reconciliation_table(self.comparison)
        else:
            # Version simplifiée
            data = [
                {"Élément": f"Variation brute {self.comparison.year_n1}→{self.comparison.year_n}", "Montant": self.comparison.variation_brute},
                {"Élément": f"Impact normalisation {self.comparison.year_n1}", "Montant": -self.comparison.ajustement_n1},
                {"Élément": f"Impact normalisation {self.comparison.year_n}", "Montant": self.comparison.ajustement_n},
                {"Élément": "Écart normalisation total", "Montant": self.comparison.ecart_normalisation},
                {"Élément": "Variation normalisée (run rate)", "Montant": self.comparison.variation_normalisee},
            ]
            df = pd.DataFrame(data)

        df.to_excel(writer, sheet_name="Réconciliation", index=False)

    def _write_provisions(self, writer: pd.ExcelWriter, result: NormalizedPLResult, year: int):
        """Écrit un onglet de provisions"""
        if not result.provisions:
            df = pd.DataFrame({"Info": [f"Aucune provision significative détectée en {year}"]})
        else:
            data = [
                {
                    "Compte": p.compte,
                    "Libellé": p.libelle_compte,
                    "Total annuel": p.total_annuel,
                    "Run rate mensuel": p.run_rate_mensuel,
                    "Décembre brut": p.decembre_brut,
                    "Décembre normalisé": p.decembre_normalise,
                    "Impact normalisation": p.ecart_decembre,
                    "Moyenne hors déc": p.moyenne_hors_dec,
                    "Écart vs moyenne": p.ecart_vs_moyenne,
                    "% Écart": p.pct_ecart,
                }
                for p in result.provisions
            ]
            df = pd.DataFrame(data)

        df.to_excel(writer, sheet_name=f"Provisions {year}", index=False)

    def _write_anomalies(self, writer: pd.ExcelWriter):
        """Écrit l'onglet des anomalies"""
        all_anomalies = []

        for year, result in [(self.comparison.year_n1, self.comparison.result_n1),
                              (self.comparison.year_n, self.comparison.result_n)]:
            for a in result.anomalies:
                all_anomalies.append({
                    "Année": year,
                    "Compte": a.compte,
                    "Libellé": a.libelle_compte,
                    "Mois": a.mois,
                    "Montant mois": a.montant_mois,
                    "Moyenne annuelle": a.moyenne_annuelle,
                    "Écart-type": a.ecart_type,
                    "Z-score": a.z_score,
                    "Écart absolu": a.ecart_absolu,
                    "Écart %": a.ecart_pct,
                    "Nature": a.nature,
                    "Interprétation": a.interpretation,
                })

        if all_anomalies:
            df = pd.DataFrame(all_anomalies)
        else:
            df = pd.DataFrame({"Info": ["Aucune anomalie détectée"]})

        df.to_excel(writer, sheet_name="Anomalies", index=False)

    def _write_drilldown(self, writer: pd.ExcelWriter):
        """Écrit l'onglet de drill-down"""
        data = []

        for analysis in self.comparison.top_variations:
            # Ligne principale du compte
            data.append({
                "Compte": analysis.compte,
                "Libellé": analysis.libelle_compte,
                "Type": "TOTAL",
                f"Montant {self.comparison.year_n1}": analysis.montant_n1,
                f"Montant {self.comparison.year_n}": analysis.montant_n,
                "Variation": analysis.variation,
            })

            # Nouvelles écritures
            for g in analysis.groupes_nouvelles[:5]:
                data.append({
                    "Compte": "",
                    "Libellé": f"  + NOUVELLE: {g.libelle_normalise[:50]}",
                    "Type": "NOUVELLE",
                    f"Montant {self.comparison.year_n1}": 0,
                    f"Montant {self.comparison.year_n}": g.montant_n,
                    "Variation": g.variation,
                })

            # Écritures disparues
            for g in analysis.groupes_disparues[:5]:
                data.append({
                    "Compte": "",
                    "Libellé": f"  - DISPARUE: {g.libelle_normalise[:50]}",
                    "Type": "DISPARUE",
                    f"Montant {self.comparison.year_n1}": g.montant_n1,
                    f"Montant {self.comparison.year_n}": 0,
                    "Variation": g.variation,
                })

            # Écritures variées
            for g in analysis.groupes_variees[:5]:
                data.append({
                    "Compte": "",
                    "Libellé": f"  ± VARIÉE: {g.libelle_normalise[:50]}",
                    "Type": "VARIEE",
                    f"Montant {self.comparison.year_n1}": g.montant_n1,
                    f"Montant {self.comparison.year_n}": g.montant_n,
                    "Variation": g.variation,
                })

            # Ligne vide de séparation
            data.append({k: "" for k in data[0].keys()})

        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name="Drill-down", index=False)

    def _write_monthly_data(self, writer: pd.ExcelWriter):
        """Écrit les données mensuelles par compte"""
        # N-1
        df_n1 = self.comparator.normalizer_n1.get_monthly_comparison()
        df_n1.to_excel(writer, sheet_name=f"Mensuel {self.comparison.year_n1}")

        # N
        df_n = self.comparator.normalizer_n.get_monthly_comparison()
        df_n.to_excel(writer, sheet_name=f"Mensuel {self.comparison.year_n}")


class TextReporter:
    """Générateur de rapports texte"""

    def __init__(self, comparison: YearComparison):
        self.comparison = comparison

    def generate(self) -> str:
        """Génère le rapport textuel complet"""
        lines = [
            "=" * 80,
            "RAPPORT DE NORMALISATION P&L",
            f"Comparaison {self.comparison.year_n1} vs {self.comparison.year_n}",
            f"Généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "=" * 80,
            "",
            self._section_summary(),
            self._section_reconciliation(),
            self._section_provisions(),
            self._section_anomalies(),
            self._section_drilldown(),
        ]

        return "\n".join(lines)

    def _section_summary(self) -> str:
        c = self.comparison
        return f"""
SYNTHÈSE
--------
                              {c.year_n1:>12}      {c.year_n:>12}      Variation
Charges brutes           {c.result_n1.charges_brutes:>12,.0f}€   {c.result_n.charges_brutes:>12,.0f}€   {c.result_n.charges_brutes - c.result_n1.charges_brutes:>+12,.0f}€
Produits bruts           {c.result_n1.produits_bruts:>12,.0f}€   {c.result_n.produits_bruts:>12,.0f}€   {c.result_n.produits_bruts - c.result_n1.produits_bruts:>+12,.0f}€
RÉSULTAT BRUT            {c.result_n1.resultat_brut:>12,.0f}€   {c.result_n.resultat_brut:>12,.0f}€   {c.variation_brute:>+12,.0f}€

Ajustement normalisation {c.ajustement_n1:>12,.0f}€   {c.ajustement_n:>12,.0f}€

RÉSULTAT NORMALISÉ       {c.result_n1.resultat_normalise:>12,.0f}€   {c.result_n.resultat_normalise:>12,.0f}€   {c.variation_normalisee:>+12,.0f}€

ÉCART (artefacts)                                              {c.ecart_normalisation:>+12,.0f}€
"""

    def _section_reconciliation(self) -> str:
        c = self.comparison
        return f"""
RÉCONCILIATION BRUT → NORMALISÉ
-------------------------------
Variation apparente (comptable):     {c.variation_brute:>+15,.0f}€
- Impact normalisation {c.year_n1}:        {-c.ajustement_n1:>+15,.0f}€
+ Impact normalisation {c.year_n}:         {c.ajustement_n:>+15,.0f}€
= Écart total normalisation:         {c.ecart_normalisation:>+15,.0f}€
VARIATION RÉELLE (run rate):         {c.variation_normalisee:>+15,.0f}€
"""

    def _section_provisions(self) -> str:
        lines = ["\nPROVISIONS / RÉGULARISATIONS", "-" * 40]

        for year, result in [(self.comparison.year_n1, self.comparison.result_n1),
                              (self.comparison.year_n, self.comparison.result_n)]:
            lines.append(f"\n{year}:")
            if not result.provisions:
                lines.append("  Aucune provision significative")
            else:
                for p in result.provisions[:10]:
                    lines.append(f"  {p.compte} {p.libelle_compte[:35]:35} Impact: {p.ecart_decembre:>+12,.0f}€")
                if len(result.provisions) > 10:
                    lines.append(f"  ... et {len(result.provisions) - 10} autres")

        return "\n".join(lines)

    def _section_anomalies(self) -> str:
        lines = ["\n\nANOMALIES DÉTECTÉES", "-" * 40]

        for year, result in [(self.comparison.year_n1, self.comparison.result_n1),
                              (self.comparison.year_n, self.comparison.result_n)]:
            lines.append(f"\n{year}:")
            if not result.anomalies:
                lines.append("  Aucune anomalie détectée")
            else:
                for a in result.anomalies[:10]:
                    lines.append(f"  [{a.nature}] {a.compte} {a.mois}: {a.montant_mois:,.0f}€ (z={a.z_score:+.1f})")

        return "\n".join(lines)

    def _section_drilldown(self) -> str:
        if not self.comparison.top_variations:
            return ""

        lines = ["\n\nTOP VARIATIONS (DRILL-DOWN)", "-" * 40]

        for analysis in self.comparison.top_variations[:5]:
            lines.append(f"\n{analysis.compte} - {analysis.libelle_compte}")
            lines.append(f"  {self.comparison.year_n1}: {analysis.montant_n1:>12,.0f}€")
            lines.append(f"  {self.comparison.year_n}: {analysis.montant_n:>12,.0f}€")
            lines.append(f"  Variation: {analysis.variation:>+12,.0f}€")

            if analysis.groupes_nouvelles:
                lines.append(f"  Nouvelles ({len(analysis.groupes_nouvelles)}):")
                for g in analysis.groupes_nouvelles[:3]:
                    lines.append(f"    + {g.libelle_normalise[:40]:40} {g.montant_n:>+10,.0f}€")

            if analysis.groupes_disparues:
                lines.append(f"  Disparues ({len(analysis.groupes_disparues)}):")
                for g in analysis.groupes_disparues[:3]:
                    lines.append(f"    - {g.libelle_normalise[:40]:40} {g.montant_n1:>10,.0f}€")

        return "\n".join(lines)


def generate_excel_report(
    comparison: YearComparison,
    output_path: Union[str, Path],
    comparator: Optional[GLComparator] = None
) -> Path:
    """
    Fonction utilitaire pour générer un rapport Excel.

    Args:
        comparison: Résultat de comparaison
        output_path: Chemin de sortie
        comparator: Instance GLComparator (optionnel)

    Returns:
        Path du fichier créé
    """
    reporter = ExcelReporter(comparison, comparator)
    return reporter.generate(output_path)


def generate_text_report(comparison: YearComparison) -> str:
    """
    Fonction utilitaire pour générer un rapport texte.

    Args:
        comparison: Résultat de comparaison

    Returns:
        Rapport formaté
    """
    reporter = TextReporter(comparison)
    return reporter.generate()


if __name__ == "__main__":
    print("Reporter - Génération de rapports Excel et texte")
    print("Usage:")
    print("  from gl_normalizer.reporter import generate_excel_report, generate_text_report")
    print("  generate_excel_report(comparison, 'rapport.xlsx', comparator)")
    print("  print(generate_text_report(comparison))")
