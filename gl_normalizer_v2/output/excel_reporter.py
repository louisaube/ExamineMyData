"""
ExcelReporter - Génération du rapport Excel
===========================================

STORY-208: Génère le rapport Excel final.

4 onglets:
1. Synthèse (30 sec de lecture)
2. Tableau de passage mensuel
3. Alertes (3-5 max)
4. Détail retraitements
"""

import pandas as pd
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from ..layer2_passage import PassageTableBuilder, AnnualSummary, MonthlyPassage, RunRate
from ..layer3_alerts import AlertGenerator, Alert


class ExcelReporter:
    """
    Génère le rapport Excel final.

    Usage:
        reporter = ExcelReporter(builder, alert_generator)
        path = reporter.generate(df, "rapport_gl.xlsx")
    """

    def __init__(
        self,
        passage_builder: Optional[PassageTableBuilder] = None,
        alert_generator: Optional[AlertGenerator] = None,
    ):
        self.passage_builder = passage_builder or PassageTableBuilder()
        self.alert_generator = alert_generator or AlertGenerator()

    def generate(self, df: pd.DataFrame, output_path: str) -> str:
        """
        Génère le rapport Excel complet.

        Args:
            df: DataFrame GL normalisé
            output_path: Chemin du fichier de sortie

        Returns:
            Chemin du fichier généré
        """
        # Calculer les données
        monthly = self.passage_builder.build_monthly(df)
        annual = self.passage_builder.build_annual(df)
        run_rate = self.passage_builder.compute_run_rate(df)
        alerts = self.alert_generator.generate(df)

        # Créer le writer Excel
        path = Path(output_path)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            # Onglet 1: Synthèse
            self._write_synthese(writer, annual, run_rate, alerts)

            # Onglet 2: Tableau de passage mensuel
            self._write_passage_mensuel(writer, monthly)

            # Onglet 3: Alertes
            self._write_alertes(writer, alerts)

            # Onglet 4: Détail retraitements
            self._write_detail_retraitements(writer, annual, monthly)

        return str(path)

    def _write_synthese(
        self,
        writer: pd.ExcelWriter,
        annual: AnnualSummary,
        run_rate: RunRate,
        alerts: List[Alert],
    ):
        """Onglet Synthèse - lisible en 30 secondes."""
        data = {
            "Indicateur": [
                "RÉSULTAT",
                "Résultat comptable brut",
                "Résultat normalisé",
                "Écart",
                "",
                "RUN RATE MENSUEL",
                "Charges brut",
                "Charges normalisé",
                "Écart charges",
                "",
                "RETRAITEMENTS",
                "Total retraitements",
                "",
                "ALERTES",
                f"Nombre d'alertes",
            ],
            "Valeur": [
                "",
                f"{annual.resultat_brut:,.0f} €",
                f"{annual.resultat_normalise:,.0f} €",
                f"{annual.ecart_resultat_pct:+.1f} %",
                "",
                "",
                f"{run_rate.charges_brut_mensuel:,.0f} €/mois",
                f"{run_rate.charges_normalise_mensuel:,.0f} €/mois",
                f"{run_rate.ecart_charges_pct:+.1f} %",
                "",
                "",
                f"{annual.total_retraitements:,.0f} €",
                "",
                "",
                f"{len(alerts)}",
            ],
        }

        df_synthese = pd.DataFrame(data)
        df_synthese.to_excel(writer, sheet_name="Synthèse", index=False)

    def _write_passage_mensuel(
        self, writer: pd.ExcelWriter, monthly: List[MonthlyPassage]
    ):
        """Onglet Tableau de passage mensuel."""
        data = []
        for m in monthly:
            data.append({
                "Mois": m.mois,
                "Charges brut": m.charges_brut,
                "Produits brut": m.produits_brut,
                "Résultat brut": m.resultat_brut,
                "Retraitements": m.total_retraitements,
                "Résultat normalisé": m.resultat_normalise,
            })

        # Ajouter total
        data.append({
            "Mois": "TOTAL",
            "Charges brut": sum(m.charges_brut for m in monthly),
            "Produits brut": sum(m.produits_brut for m in monthly),
            "Résultat brut": sum(m.resultat_brut for m in monthly),
            "Retraitements": sum(m.total_retraitements for m in monthly),
            "Résultat normalisé": sum(m.resultat_normalise for m in monthly),
        })

        df_passage = pd.DataFrame(data)
        df_passage.to_excel(writer, sheet_name="Passage mensuel", index=False)

    def _write_alertes(self, writer: pd.ExcelWriter, alerts: List[Alert]):
        """Onglet Alertes."""
        if not alerts:
            df_alertes = pd.DataFrame({
                "Message": ["Aucune alerte significative détectée"]
            })
        else:
            data = []
            for i, alert in enumerate(alerts, 1):
                data.append({
                    "#": i,
                    "Priorité": alert.priorite,
                    "Type": alert.type.value,
                    "Compte": alert.compte,
                    "Libellé": alert.libelle_compte,
                    "Montant": alert.montant,
                    "Mois": alert.mois or "Annuel",
                    "Contexte": alert.contexte.replace("\n│", " ").replace("\n", " "),
                    "Question": alert.question,
                })
            df_alertes = pd.DataFrame(data)

        df_alertes.to_excel(writer, sheet_name="Alertes", index=False)

    def _write_detail_retraitements(
        self,
        writer: pd.ExcelWriter,
        annual: AnnualSummary,
        monthly: List[MonthlyPassage],
    ):
        """Onglet Détail des retraitements."""
        data = []

        # Retraitements consolidés
        for r in annual.retraitements:
            data.append({
                "Type": r.type.value,
                "Compte": r.compte,
                "Libellé": r.libelle,
                "Montant brut": r.montant_brut,
                "Retraitement": r.montant_retraite,
                "Justification": r.justification,
            })

        if not data:
            data.append({
                "Type": "Aucun",
                "Compte": "-",
                "Libellé": "Aucun retraitement effectué",
                "Montant brut": 0,
                "Retraitement": 0,
                "Justification": "-",
            })

        df_detail = pd.DataFrame(data)
        df_detail.to_excel(writer, sheet_name="Détail retraitements", index=False)

    def generate_text_report(self, df: pd.DataFrame) -> str:
        """
        Génère un rapport texte (pour affichage console).

        Args:
            df: DataFrame GL normalisé

        Returns:
            Rapport en format texte
        """
        annual = self.passage_builder.build_annual(df)
        run_rate = self.passage_builder.compute_run_rate(df)
        alerts = self.alert_generator.generate(df)

        lines = [
            "=" * 70,
            "GL NORMALIZER v2 - RAPPORT D'ANALYSE",
            f"Généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "=" * 70,
            "",
            self.passage_builder.get_passage_table_text(df),
            "",
            "=" * 70,
            f"ALERTES ({len(alerts)} alertes)",
            "=" * 70,
        ]

        if alerts:
            for i, alert in enumerate(alerts, 1):
                lines.append(f"\n#{i} {alert.to_text()}")
        else:
            lines.append("\nAucune alerte significative.")

        lines.extend([
            "",
            "=" * 70,
            "FIN DU RAPPORT",
            "=" * 70,
        ])

        return "\n".join(lines)
