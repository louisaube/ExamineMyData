"""
gl_normalizer/layer4 - ICC Score (Internal Control Checklist)

Layer 4 de GL Crystal: agrège les anomalies qualifiées en un score ICC
et génère un rapport actionnable pour l'audit.

Architecture:
- base.py: ICCResult, ICCScore, UniversScore dataclasses
- scorer.py: ICCScorer - calcul du score global et par univers
- report.py: ReportGenerator - narrative auto-généré
- export.py: Export PDF/Excel/JSON

Formule de scoring:
    icc_score = 100 - Σ(anomaly_impact_i)
    where impact_i = weight_univers × pertinence_score × materiality_factor

Pipeline position:
    Layer 3 (QualifiedAnomaly) → Layer 1 (enrichment) → Layer 4 (ICC)

Usage:
    from gl_normalizer.layer4 import ICCScorer, run_icc

    scorer = ICCScorer()
    result = scorer.score(qualified_anomalies)

    print(result.global_score)  # 87.3
    print(result.summary())
    result.to_pdf("rapport_icc.pdf")
"""

from .base import (
    ICCResult,
    ICCScore,
    UniversScore,
    ICCConfig,
    ICCLevel,
    AnomalyImpact,
)
from .scorer import (
    ICCScorer,
    compute_anomaly_impact,
    compute_univers_scores,
    run_icc,
)
from .report import (
    ReportGenerator,
    generate_summary,
    generate_recommendations,
    format_top_anomalies,
)

__all__ = [
    # Base
    "ICCResult",
    "ICCScore",
    "UniversScore",
    "ICCConfig",
    "ICCLevel",
    "AnomalyImpact",
    # Scorer
    "ICCScorer",
    "compute_anomaly_impact",
    "compute_univers_scores",
    "run_icc",
    # Report
    "ReportGenerator",
    "generate_summary",
    "generate_recommendations",
    "format_top_anomalies",
]
