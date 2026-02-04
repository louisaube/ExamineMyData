"""
gl_normalizer/layer1 - Label Parser (Semantic Enrichment)

Layer 1 de GL Crystal: enrichit les anomalies qualifiées avec
la sémantique extraite des libellés comptables.

Architecture:
- base.py: ParsedLabel, LabelFeatures, OperationType
- entities.py: extract_entities() - Regex + spaCy NER
- intents.py: classify_intent() - Détection intention
- parser.py: LabelParser orchestration

Principe: Lazy Parsing
- Ne parse PAS les 200K écritures du GL
- Parse seulement les ~15 anomalies qualifiées de Layer 3
- Cache par hash de libellé pour déduplication

Pipeline position:
    Layer 3 (QualifiedAnomaly) → Layer 1 (enrichissement) → Layer 4 (ICC)

Usage:
    from gl_normalizer.layer1 import LabelParser, parse_labels

    # Option 1: Parser instance
    parser = LabelParser()
    parsed = parser.parse("FA-2024-0123 ACME Corp loyer janvier")

    # Option 2: Batch sur anomalies
    enriched = parse_labels(qualified_anomalies)
"""

from .base import (
    ParsedLabel,
    LabelFeatures,
    ExtractedEntity,
    EntityType,
    OperationType,
    Intent,
    ParserConfig,
)
from .entities import (
    extract_entities,
    extract_amount,
    extract_date,
    extract_reference,
    extract_tiers,
)
from .intents import (
    classify_intent,
    classify_operation,
    detect_recurring,
    INTENT_PATTERNS,
)
from .parser import (
    LabelParser,
    parse_label,
    parse_labels,
    enrich_anomalies,
)

__all__ = [
    # Base
    "ParsedLabel",
    "LabelFeatures",
    "ExtractedEntity",
    "EntityType",
    "OperationType",
    "Intent",
    "ParserConfig",
    # Entities
    "extract_entities",
    "extract_amount",
    "extract_date",
    "extract_reference",
    "extract_tiers",
    # Intents
    "classify_intent",
    "classify_operation",
    "detect_recurring",
    "INTENT_PATTERNS",
    # Parser
    "LabelParser",
    "parse_label",
    "parse_labels",
    "enrich_anomalies",
]
