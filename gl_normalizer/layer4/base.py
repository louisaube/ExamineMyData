"""
gl_normalizer/layer4/base.py
Structures de données pour le scoring ICC

Définit les dataclasses pour:
- ICCResult: Résultat complet du scoring
- ICCScore: Score global avec détails
- UniversScore: Score par univers (radar)
- AnomalyImpact: Impact calculé par anomalie
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from ..layer2.base import Univers
    from ..layer3.base import QualifiedAnomaly


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class ICCConfig:
    """
    Configuration du scoring ICC.

    Attributes:
        max_score: Score maximum (défaut: 100)
        min_score: Score minimum (défaut: 0)
        max_impact_per_anomaly: Impact max par anomalie (défaut: 15)
        top_n_anomalies: Nombre d'anomalies dans le top N (défaut: 5)
        univers_weights: Poids par univers (optionnel)
    """
    max_score: float = 100.0
    min_score: float = 0.0
    max_impact_per_anomaly: float = 15.0
    top_n_anomalies: int = 5

    # Poids par univers (risque relatif)
    univers_weights: Dict[str, float] = field(default_factory=lambda: {
        "CRISTALLIN": 0.8,           # Charges fixes: risque modéré
        "NOMINATIF_TIERS": 1.2,      # Auxiliaires: risque élevé (tiers)
        "NOMINATIF_OPERATIONNEL": 1.0,
        "PROCESSUS": 1.0,
        "VENTILATION": 0.9,
        "CUT_OFF": 1.3,              # Cut-off: risque élevé (timing)
        "TRESORERIE": 0.7,           # Trésorerie: risque faible (rapprochement)
        "PONCTUEL": 1.4,             # Exceptionnel: risque très élevé
        "INVENTAIRE": 1.1,           # Stocks/Immos: risque élevé
        "COMPOSITE": 1.0,
    })

    # Seuils de niveau
    thresholds: Dict[str, float] = field(default_factory=lambda: {
        "EXCELLENT": 90.0,
        "BON": 75.0,
        "ACCEPTABLE": 60.0,
        "ATTENTION": 40.0,
        "CRITIQUE": 0.0,
    })


class ICCLevel(str, Enum):
    """Niveau de qualité ICC."""
    EXCELLENT = "EXCELLENT"    # >= 90
    BON = "BON"                # >= 75
    ACCEPTABLE = "ACCEPTABLE"  # >= 60
    ATTENTION = "ATTENTION"    # >= 40
    CRITIQUE = "CRITIQUE"      # < 40


# =============================================================================
# STRUCTURES DE DONNÉES
# =============================================================================

@dataclass
class AnomalyImpact:
    """
    Impact calculé d'une anomalie sur le score ICC.

    Attributes:
        anomaly: QualifiedAnomaly source
        base_impact: Impact de base (pertinence_score normalisé)
        univers_weight: Poids de l'univers
        materiality_factor: Facteur de matérialité
        final_impact: Impact final sur le score
    """
    anomaly_id: str
    famille: str
    univers: str
    test_name: str

    base_impact: float
    univers_weight: float
    materiality_factor: float
    final_impact: float

    # Détails
    pertinence_score: float
    materiality_amount: float
    materiality_threshold: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_id": self.anomaly_id,
            "famille": self.famille,
            "univers": self.univers,
            "test_name": self.test_name,
            "impacts": {
                "base": self.base_impact,
                "univers_weight": self.univers_weight,
                "materiality_factor": self.materiality_factor,
                "final": self.final_impact,
            },
            "details": {
                "pertinence_score": self.pertinence_score,
                "materiality_amount": self.materiality_amount,
                "materiality_threshold": self.materiality_threshold,
            },
        }


@dataclass
class UniversScore:
    """
    Score pour un univers (axe du radar).

    Attributes:
        univers: Nom de l'univers
        score: Score 0-100
        anomaly_count: Nombre d'anomalies
        total_impact: Impact total
        total_materiality: Matérialité totale
    """
    univers: str
    score: float
    anomaly_count: int = 0
    total_impact: float = 0.0
    total_materiality: float = 0.0

    @property
    def level(self) -> ICCLevel:
        """Niveau de qualité pour cet univers."""
        if self.score >= 90:
            return ICCLevel.EXCELLENT
        elif self.score >= 75:
            return ICCLevel.BON
        elif self.score >= 60:
            return ICCLevel.ACCEPTABLE
        elif self.score >= 40:
            return ICCLevel.ATTENTION
        else:
            return ICCLevel.CRITIQUE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "univers": self.univers,
            "score": self.score,
            "level": self.level.value,
            "anomaly_count": self.anomaly_count,
            "total_impact": self.total_impact,
            "total_materiality": self.total_materiality,
        }


@dataclass
class ICCScore:
    """
    Score ICC global avec détails.

    Attributes:
        value: Score 0-100
        level: Niveau (EXCELLENT, BON, etc.)
        total_impact: Somme des impacts
        anomaly_count: Nombre d'anomalies
    """
    value: float
    level: ICCLevel
    total_impact: float
    anomaly_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "level": self.level.value,
            "total_impact": self.total_impact,
            "anomaly_count": self.anomaly_count,
        }


@dataclass
class ICCResult:
    """
    Résultat complet du scoring ICC.

    Attributes:
        score: Score global
        univers_scores: Scores par univers (radar)
        impacts: Impacts par anomalie
        top_anomalies: Top N anomalies
        narrative: Résumé textuel
        recommendations: Liste de recommandations
    """
    # Score principal
    score: ICCScore

    # Détails par univers
    univers_scores: Dict[str, UniversScore]

    # Impacts détaillés
    impacts: List[AnomalyImpact]

    # Top anomalies
    top_anomalies: List[Dict[str, Any]]

    # Narrative
    narrative: str = ""
    recommendations: List[str] = field(default_factory=list)

    # Metadata
    period: str = ""
    entity: str = ""
    generated_at: datetime = field(default_factory=datetime.now)
    config_used: Optional[ICCConfig] = None

    # Stats
    total_materiality: float = 0.0
    coverage_rate: float = 0.0  # % familles avec anomalies

    @property
    def global_score(self) -> float:
        """Score global (raccourci)."""
        return self.score.value

    @property
    def level(self) -> ICCLevel:
        """Niveau global (raccourci)."""
        return self.score.level

    def summary(self) -> str:
        """Résumé textuel du résultat."""
        lines = [
            "=" * 60,
            f"  ICC SCORE: {self.score.value:.1f}/100 ({self.score.level.value})",
            "=" * 60,
            "",
            f"Anomalies qualifiées: {self.score.anomaly_count}",
            f"Matérialité totale: {self.total_materiality:,.0f}€",
            f"Impact total: {self.score.total_impact:.1f} points",
            "",
            "Scores par univers:",
        ]

        for univers, us in sorted(self.univers_scores.items(), key=lambda x: x[1].score):
            bar = "█" * int(us.score / 5) + "░" * (20 - int(us.score / 5))
            lines.append(f"  {univers:25s} {bar} {us.score:5.1f} ({us.anomaly_count} anom.)")

        if self.top_anomalies:
            lines.extend(["", "Top 5 anomalies:"])
            for i, a in enumerate(self.top_anomalies[:5], 1):
                lines.append(f"  {i}. [{a['famille']}] {a['test_name']}: {a['final_impact']:.1f} pts")

        if self.recommendations:
            lines.extend(["", "Recommandations:"])
            for rec in self.recommendations[:3]:
                lines.append(f"  • {rec}")

        return "\n".join(lines)

    def radar_data(self) -> Dict[str, float]:
        """Données pour le radar chart."""
        return {u: s.score for u, s in self.univers_scores.items()}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score.to_dict(),
            "univers_scores": {u: s.to_dict() for u, s in self.univers_scores.items()},
            "impacts": [i.to_dict() for i in self.impacts],
            "top_anomalies": self.top_anomalies,
            "narrative": self.narrative,
            "recommendations": self.recommendations,
            "metadata": {
                "period": self.period,
                "entity": self.entity,
                "generated_at": self.generated_at.isoformat(),
                "total_materiality": self.total_materiality,
                "coverage_rate": self.coverage_rate,
            },
        }

    def to_json(self) -> str:
        """Export JSON."""
        import json
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
