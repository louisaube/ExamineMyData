"""
gl_normalizer/layer4/report.py
Génération de rapports ICC

Produit:
- Narrative auto-généré (executive summary)
- Recommandations basées sur les anomalies
- Formatage des top anomalies
- Export PDF/Excel
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from .base import ICCResult, ICCLevel, UniversScore, AnomalyImpact


# =============================================================================
# NARRATIVE GENERATION
# =============================================================================

LEVEL_DESCRIPTIONS = {
    ICCLevel.EXCELLENT: "Le contrôle interne présente un niveau de qualité excellent.",
    ICCLevel.BON: "Le contrôle interne est satisfaisant avec quelques points d'attention mineurs.",
    ICCLevel.ACCEPTABLE: "Le contrôle interne est acceptable mais nécessite des améliorations.",
    ICCLevel.ATTENTION: "Le contrôle interne présente des faiblesses significatives à corriger.",
    ICCLevel.CRITIQUE: "Le contrôle interne présente des défaillances critiques nécessitant une action immédiate.",
}

UNIVERS_DESCRIPTIONS = {
    "CRISTALLIN": "charges fixes et récurrentes",
    "NOMINATIF_TIERS": "auxiliaires fournisseurs et clients",
    "NOMINATIF_OPERATIONNEL": "comptes de personnel et opérationnels",
    "PROCESSUS": "processus d'achat et de vente",
    "VENTILATION": "analytique et ventilation",
    "CUT_OFF": "séparation des exercices (cut-off)",
    "TRESORERIE": "trésorerie et rapprochements",
    "PONCTUEL": "opérations exceptionnelles",
    "INVENTAIRE": "stocks et immobilisations",
    "COMPOSITE": "écritures composites",
}


def generate_summary(result: ICCResult) -> str:
    """
    Génère le résumé exécutif (narrative).

    Args:
        result: ICCResult

    Returns:
        Résumé textuel
    """
    lines = []

    # Header
    period_str = f" pour la période {result.period}" if result.period else ""
    entity_str = f" de {result.entity}" if result.entity else ""
    lines.append(f"## Rapport ICC{entity_str}{period_str}")
    lines.append("")

    # Score global
    lines.append(f"### Score Global: {result.score.value:.1f}/100 ({result.score.level.value})")
    lines.append("")
    lines.append(LEVEL_DESCRIPTIONS.get(result.score.level, ""))
    lines.append("")

    # Statistiques clés
    lines.append("### Chiffres Clés")
    lines.append(f"- **Anomalies détectées:** {result.score.anomaly_count}")
    lines.append(f"- **Matérialité totale:** {result.total_materiality:,.0f}€")
    lines.append(f"- **Impact total:** {result.score.total_impact:.1f} points")
    lines.append("")

    # Points faibles (univers avec score < 75)
    weak_univers = [
        (u, s) for u, s in result.univers_scores.items()
        if s.score < 75 and s.anomaly_count > 0
    ]
    if weak_univers:
        weak_univers.sort(key=lambda x: x[1].score)
        lines.append("### Points d'Attention")
        for univers, score in weak_univers[:3]:
            desc = UNIVERS_DESCRIPTIONS.get(univers, univers.lower())
            lines.append(f"- **{univers}** ({score.score:.0f}/100): {score.anomaly_count} anomalie(s) "
                        f"dans les {desc}")
        lines.append("")

    # Points forts (univers avec score >= 90)
    strong_univers = [
        (u, s) for u, s in result.univers_scores.items()
        if s.score >= 90
    ]
    if strong_univers:
        lines.append("### Points Forts")
        for univers, score in sorted(strong_univers, key=lambda x: x[1].score, reverse=True)[:3]:
            desc = UNIVERS_DESCRIPTIONS.get(univers, univers.lower())
            lines.append(f"- **{univers}** ({score.score:.0f}/100): Contrôle satisfaisant des {desc}")
        lines.append("")

    return "\n".join(lines)


def generate_recommendations(result: ICCResult) -> List[str]:
    """
    Génère les recommandations basées sur les anomalies.

    Args:
        result: ICCResult

    Returns:
        Liste de recommandations
    """
    recommendations = []

    # Recommandations par niveau
    if result.score.level == ICCLevel.CRITIQUE:
        recommendations.append(
            "URGENT: Mettre en place un plan d'action immédiat pour corriger les défaillances critiques."
        )

    if result.score.level in [ICCLevel.CRITIQUE, ICCLevel.ATTENTION]:
        recommendations.append(
            "Renforcer les contrôles de supervision sur les écritures manuelles et exceptionnelles."
        )

    # Recommandations par univers faible
    weak_univers = [
        (u, s) for u, s in result.univers_scores.items()
        if s.score < 60 and s.anomaly_count > 0
    ]

    for univers, score in weak_univers[:3]:
        if univers == "CUT_OFF":
            recommendations.append(
                f"Revoir les procédures de cut-off: {score.anomaly_count} anomalie(s) détectée(s) "
                f"pour une matérialité de {score.total_materiality:,.0f}€."
            )
        elif univers == "PONCTUEL":
            recommendations.append(
                f"Renforcer la revue des opérations exceptionnelles: {score.anomaly_count} écriture(s) "
                f"à investiguer."
            )
        elif univers == "NOMINATIF_TIERS":
            recommendations.append(
                f"Analyser les écarts sur comptes auxiliaires: {score.anomaly_count} anomalie(s) "
                f"totalisant {score.total_materiality:,.0f}€."
            )
        elif univers == "INVENTAIRE":
            recommendations.append(
                f"Vérifier les mouvements de stocks/immobilisations: {score.anomaly_count} "
                f"variation(s) anormale(s)."
            )
        else:
            desc = UNIVERS_DESCRIPTIONS.get(univers, univers.lower())
            recommendations.append(
                f"Investiguer les {desc}: {score.anomaly_count} anomalie(s) détectée(s)."
            )

    # Recommandations basées sur les top anomalies
    if result.top_anomalies:
        top = result.top_anomalies[0]
        recommendations.append(
            f"Priorité: Analyser l'anomalie [{top['famille']}] {top['test_name']} "
            f"(impact: {top['final_impact']:.1f} pts, montant: {top['materiality_amount']:,.0f}€)."
        )

    # Recommandation générique si score bon
    if result.score.level in [ICCLevel.EXCELLENT, ICCLevel.BON]:
        recommendations.append(
            "Maintenir le niveau de contrôle actuel et documenter les bonnes pratiques."
        )

    return recommendations[:5]  # Max 5 recommandations


def format_top_anomalies(result: ICCResult, max_items: int = 5) -> str:
    """
    Formate les top anomalies en texte.

    Args:
        result: ICCResult
        max_items: Nombre max d'anomalies

    Returns:
        Texte formaté
    """
    if not result.top_anomalies:
        return "Aucune anomalie significative détectée."

    lines = ["### Top Anomalies", ""]

    for i, a in enumerate(result.top_anomalies[:max_items], 1):
        lines.append(f"{i}. **[{a['famille']}] {a['test_name']}**")
        lines.append(f"   - Univers: {a['univers']}")
        lines.append(f"   - Impact: {a['final_impact']:.1f} points")
        lines.append(f"   - Pertinence: {a['pertinence_score']:.0f}/100")
        lines.append(f"   - Montant: {a['materiality_amount']:,.0f}€")
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# REPORT GENERATOR CLASS
# =============================================================================

class ReportGenerator:
    """
    Générateur de rapports ICC.

    Usage:
        generator = ReportGenerator()
        report = generator.generate(icc_result)
        generator.to_pdf(report, "rapport.pdf")
    """

    def __init__(self):
        pass

    def generate(self, result: ICCResult) -> Dict[str, Any]:
        """
        Génère un rapport complet.

        Args:
            result: ICCResult

        Returns:
            Dict avec toutes les sections du rapport
        """
        # Générer narrative et recommandations
        narrative = generate_summary(result)
        recommendations = generate_recommendations(result)

        # Mettre à jour le result
        result.narrative = narrative
        result.recommendations = recommendations

        return {
            "metadata": {
                "title": f"Rapport ICC{' - ' + result.entity if result.entity else ''}",
                "period": result.period,
                "entity": result.entity,
                "generated_at": result.generated_at.isoformat(),
                "score": result.score.value,
                "level": result.score.level.value,
            },
            "executive_summary": narrative,
            "score_details": result.score.to_dict(),
            "univers_analysis": {u: s.to_dict() for u, s in result.univers_scores.items()},
            "top_anomalies": result.top_anomalies,
            "recommendations": recommendations,
            "full_impacts": [i.to_dict() for i in result.impacts],
        }

    def to_markdown(self, result: ICCResult) -> str:
        """
        Génère un rapport Markdown.

        Args:
            result: ICCResult

        Returns:
            Rapport en Markdown
        """
        report = self.generate(result)

        sections = [
            f"# {report['metadata']['title']}",
            f"*Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}*",
            "",
            report["executive_summary"],
            "",
            format_top_anomalies(result),
            "",
            "### Recommandations",
            "",
        ]

        for rec in report["recommendations"]:
            sections.append(f"- {rec}")

        return "\n".join(sections)

    def to_html(self, result: ICCResult) -> str:
        """
        Génère un rapport HTML simple.

        Args:
            result: ICCResult

        Returns:
            Rapport en HTML
        """
        md = self.to_markdown(result)

        # Conversion Markdown → HTML basique
        html_content = md.replace("\n", "<br>\n")
        html_content = html_content.replace("# ", "<h1>").replace("## ", "<h2>").replace("### ", "<h3>")
        html_content = html_content.replace("**", "<strong>").replace("**", "</strong>")

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Rapport ICC</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #2c3e50; }}
        h2 {{ color: #34495e; }}
        .score {{ font-size: 48px; font-weight: bold; color: {self._score_color(result.score.value)}; }}
    </style>
</head>
<body>
    <div class="score">{result.score.value:.0f}/100</div>
    {html_content}
</body>
</html>"""

    def _score_color(self, score: float) -> str:
        """Couleur selon le score."""
        if score >= 90:
            return "#27ae60"  # Vert
        elif score >= 75:
            return "#2ecc71"  # Vert clair
        elif score >= 60:
            return "#f39c12"  # Orange
        elif score >= 40:
            return "#e67e22"  # Orange foncé
        else:
            return "#e74c3c"  # Rouge
