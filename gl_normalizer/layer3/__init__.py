"""
gl_normalizer/layer3 - Filtres Métier (v2)

Layer 3 de GL Crystal: filtre les signaux FDR de Layer 2.5 avec:
- Matérialité: montant > seuil configurable
- Exclusions: règles non_signal_si du référentiel
- Pertinence: score combiné stat × matérialité × métier

Architecture:
- base.py: QualifiedAnomaly, FilteredSignal, Layer3Result
- materiality.py: check_materiality(), seuils par univers
- business_rules.py: non_signal_si, signal_si, SignalContext
- pertinence.py: compute_pertinence(), scores composites
- runner.py: Layer3Runner orchestration

Pipeline:
    Layer 2: ~200 signaux bruts (p-values)
    Layer 2.5: ~40 signaux (FDR-contrôlés)
    Layer 3: ~15 anomalies qualifiées

Usage:
    from gl_normalizer.layer3 import Layer3Runner, run_full_pipeline

    # Option 1: Pipeline séparé
    runner = Layer3Runner(referentiel)
    result = runner.run(layer2_signals)

    # Option 2: Pipeline complet
    result = run_full_pipeline(gl, referentiel)

    print(result.summary())
    for anomaly in result.qualified:
        print(f"{anomaly.rank}. {anomaly.signal.famille}: {anomaly.final_score:.1f}")
"""

from .base import (
    FilterReason,
    PertinenceLevel,
    QualifiedAnomaly,
    FilteredSignal,
    Layer3Result,
)
from .materiality import (
    check_materiality,
    compute_materiality_amount,
    get_materiality_threshold,
    compute_materiality_score,
    DEFAULT_MATERIALITY_THRESHOLD,
    UNIVERS_MATERIALITY,
)
from .business_rules import (
    ExclusionRule,
    InclusionRule,
    SignalContext,
    check_exclusions,
    check_inclusions,
    compute_signal_context,
    get_exclusion_rules_for_family,
    STANDARD_EXCLUSION_RULES,
    STANDARD_INCLUSION_RULES,
)
from .pertinence import (
    compute_pertinence,
    compute_statistical_score,
    compute_business_score,
    compute_context_score,
    passes_pertinence_threshold,
    PertinenceResult,
    DEFAULT_PERTINENCE_THRESHOLD,
    WEIGHTS,
)
from .runner import (
    Layer3Runner,
    run_layer3,
    run_full_pipeline,
)

__all__ = [
    # Base
    "FilterReason",
    "PertinenceLevel",
    "QualifiedAnomaly",
    "FilteredSignal",
    "Layer3Result",
    # Materiality
    "check_materiality",
    "compute_materiality_amount",
    "get_materiality_threshold",
    "compute_materiality_score",
    "DEFAULT_MATERIALITY_THRESHOLD",
    "UNIVERS_MATERIALITY",
    # Business Rules
    "ExclusionRule",
    "InclusionRule",
    "SignalContext",
    "check_exclusions",
    "check_inclusions",
    "compute_signal_context",
    "get_exclusion_rules_for_family",
    "STANDARD_EXCLUSION_RULES",
    "STANDARD_INCLUSION_RULES",
    # Pertinence
    "compute_pertinence",
    "compute_statistical_score",
    "compute_business_score",
    "compute_context_score",
    "passes_pertinence_threshold",
    "PertinenceResult",
    "DEFAULT_PERTINENCE_THRESHOLD",
    "WEIGHTS",
    # Runner
    "Layer3Runner",
    "run_layer3",
    "run_full_pipeline",
]
