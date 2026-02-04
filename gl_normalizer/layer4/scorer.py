"""
gl_normalizer/layer4/scorer.py
Calcul du score ICC

Formule de scoring:
    icc_score = 100 - Σ(anomaly_impact_i)

Où anomaly_impact =
    base_impact × univers_weight × materiality_factor

Avec:
    base_impact = pertinence_score / 100 × max_impact
    materiality_factor = log10(1 + amount/total) × scaling
"""

import math
from typing import List, Dict, Optional, TYPE_CHECKING
from collections import defaultdict

from .base import (
    ICCResult,
    ICCScore,
    UniversScore,
    ICCConfig,
    ICCLevel,
    AnomalyImpact,
)

if TYPE_CHECKING:
    from ..layer3.base import QualifiedAnomaly


# =============================================================================
# IMPACT CALCULATION
# =============================================================================

def compute_anomaly_impact(
    anomaly: "QualifiedAnomaly",
    config: ICCConfig,
    total_materiality: float,
) -> AnomalyImpact:
    """
    Calcule l'impact d'une anomalie sur le score ICC.

    Args:
        anomaly: QualifiedAnomaly de Layer 3
        config: Configuration ICC
        total_materiality: Matérialité totale (pour normaliser)

    Returns:
        AnomalyImpact avec les détails du calcul
    """
    # Extraire les valeurs
    univers_str = anomaly.signal.univers.value if hasattr(anomaly.signal.univers, 'value') else str(anomaly.signal.univers)
    pertinence = anomaly.pertinence_score
    mat_amount = anomaly.materiality_amount
    mat_threshold = anomaly.materiality_threshold

    # 1. Base impact: pertinence normalisée
    # pertinence est sur 0-100, on normalise à 0-max_impact
    base_impact = (pertinence / 100.0) * config.max_impact_per_anomaly

    # 2. Poids de l'univers
    univers_weight = config.univers_weights.get(univers_str, 1.0)

    # 3. Facteur de matérialité
    # Plus le montant est élevé par rapport au total, plus l'impact est fort
    if total_materiality > 0 and mat_amount > 0:
        # log scale pour éviter que les gros montants écrasent tout
        materiality_factor = math.log10(1 + mat_amount / max(total_materiality, 1)) * 3 + 1
        materiality_factor = min(2.0, max(0.5, materiality_factor))
    else:
        materiality_factor = 1.0

    # 4. Impact final
    final_impact = base_impact * univers_weight * materiality_factor
    final_impact = min(config.max_impact_per_anomaly, final_impact)

    return AnomalyImpact(
        anomaly_id=anomaly.signal.id,
        famille=anomaly.signal.famille,
        univers=univers_str,
        test_name=anomaly.signal.test_name,
        base_impact=base_impact,
        univers_weight=univers_weight,
        materiality_factor=materiality_factor,
        final_impact=final_impact,
        pertinence_score=pertinence,
        materiality_amount=mat_amount,
        materiality_threshold=mat_threshold,
    )


def compute_univers_scores(
    impacts: List[AnomalyImpact],
    config: ICCConfig,
) -> Dict[str, UniversScore]:
    """
    Calcule les scores par univers pour le radar chart.

    Chaque univers a un score de 100 - impacts_du_univers.

    Args:
        impacts: Liste des impacts calculés
        config: Configuration ICC

    Returns:
        Dict univers → UniversScore
    """
    # Grouper par univers
    by_univers: Dict[str, List[AnomalyImpact]] = defaultdict(list)
    for impact in impacts:
        by_univers[impact.univers].append(impact)

    # Calculer le score par univers
    scores = {}

    # Tous les univers (même ceux sans anomalie)
    all_univers = set(config.univers_weights.keys())
    all_univers.update(by_univers.keys())

    for univers in all_univers:
        univers_impacts = by_univers.get(univers, [])

        total_impact = sum(i.final_impact for i in univers_impacts)
        total_materiality = sum(i.materiality_amount for i in univers_impacts)

        # Score: 100 - impacts (min 0)
        score = max(0, 100 - total_impact)

        scores[univers] = UniversScore(
            univers=univers,
            score=score,
            anomaly_count=len(univers_impacts),
            total_impact=total_impact,
            total_materiality=total_materiality,
        )

    return scores


def compute_global_score(
    impacts: List[AnomalyImpact],
    config: ICCConfig,
) -> ICCScore:
    """
    Calcule le score ICC global.

    Args:
        impacts: Liste des impacts
        config: Configuration

    Returns:
        ICCScore global
    """
    total_impact = sum(i.final_impact for i in impacts)
    score_value = max(config.min_score, config.max_score - total_impact)

    # Déterminer le niveau
    level = ICCLevel.CRITIQUE
    for level_name, threshold in sorted(config.thresholds.items(), key=lambda x: x[1], reverse=True):
        if score_value >= threshold:
            level = ICCLevel(level_name)
            break

    return ICCScore(
        value=score_value,
        level=level,
        total_impact=total_impact,
        anomaly_count=len(impacts),
    )


# =============================================================================
# ICC SCORER CLASS
# =============================================================================

class ICCScorer:
    """
    Calculateur de score ICC.

    Usage:
        scorer = ICCScorer()
        result = scorer.score(qualified_anomalies)
        print(result.summary())
    """

    def __init__(self, config: Optional[ICCConfig] = None):
        self.config = config or ICCConfig()

    def score(
        self,
        anomalies: List["QualifiedAnomaly"],
        period: str = "",
        entity: str = "",
    ) -> ICCResult:
        """
        Calcule le score ICC pour une liste d'anomalies qualifiées.

        Args:
            anomalies: Liste des QualifiedAnomaly de Layer 3
            period: Période analysée (ex: "2024-01")
            entity: Entité analysée (ex: "ACME Corp")

        Returns:
            ICCResult complet
        """
        if not anomalies:
            return self._empty_result(period, entity)

        # Calculer la matérialité totale
        total_materiality = sum(a.materiality_amount for a in anomalies)

        # Calculer l'impact de chaque anomalie
        impacts = [
            compute_anomaly_impact(a, self.config, total_materiality)
            for a in anomalies
        ]

        # Trier par impact décroissant
        impacts.sort(key=lambda x: x.final_impact, reverse=True)

        # Score global
        global_score = compute_global_score(impacts, self.config)

        # Scores par univers
        univers_scores = compute_univers_scores(impacts, self.config)

        # Top anomalies
        top_anomalies = [
            {
                "anomaly_id": i.anomaly_id,
                "famille": i.famille,
                "univers": i.univers,
                "test_name": i.test_name,
                "final_impact": i.final_impact,
                "pertinence_score": i.pertinence_score,
                "materiality_amount": i.materiality_amount,
            }
            for i in impacts[:self.config.top_n_anomalies]
        ]

        # Calculer le coverage
        unique_familles = len(set(a.signal.famille for a in anomalies))
        # Approximation: 180 familles au total
        coverage_rate = unique_familles / 180.0

        return ICCResult(
            score=global_score,
            univers_scores=univers_scores,
            impacts=impacts,
            top_anomalies=top_anomalies,
            period=period,
            entity=entity,
            config_used=self.config,
            total_materiality=total_materiality,
            coverage_rate=coverage_rate,
        )

    def _empty_result(self, period: str, entity: str) -> ICCResult:
        """Résultat vide quand pas d'anomalies."""
        return ICCResult(
            score=ICCScore(
                value=100.0,
                level=ICCLevel.EXCELLENT,
                total_impact=0.0,
                anomaly_count=0,
            ),
            univers_scores={
                u: UniversScore(univers=u, score=100.0)
                for u in self.config.univers_weights.keys()
            },
            impacts=[],
            top_anomalies=[],
            period=period,
            entity=entity,
            config_used=self.config,
            total_materiality=0.0,
            coverage_rate=0.0,
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def run_icc(
    anomalies: List["QualifiedAnomaly"],
    config: Optional[ICCConfig] = None,
    period: str = "",
    entity: str = "",
) -> ICCResult:
    """
    Fonction raccourcie pour calculer le score ICC.

    Args:
        anomalies: Liste des QualifiedAnomaly
        config: Configuration (optionnel)
        period: Période
        entity: Entité

    Returns:
        ICCResult
    """
    scorer = ICCScorer(config)
    return scorer.score(anomalies, period, entity)


def score_from_layer3(
    layer3_result: "Layer3Result",
    config: Optional[ICCConfig] = None,
) -> ICCResult:
    """
    Calcule le score ICC directement depuis un Layer3Result.

    Args:
        layer3_result: Résultat de Layer 3
        config: Configuration ICC

    Returns:
        ICCResult
    """
    return run_icc(layer3_result.qualified, config)
