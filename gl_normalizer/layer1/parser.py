"""
gl_normalizer/layer1/parser.py
Orchestration du Label Parser

LabelParser combine:
1. Extraction d'entités (entities.py)
2. Classification d'intention (intents.py)
3. Agrégation en LabelFeatures

Avec:
- Cache LRU par hash de libellé
- Fallback spaCy si disponible
- Enrichissement des QualifiedAnomaly
"""

import time
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from functools import lru_cache

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
    extract_with_spacy,
    is_spacy_available,
)
from .intents import (
    classify_intent,
    classify_operation,
    detect_recurring,
    detect_round_amount,
)

if TYPE_CHECKING:
    from ..layer3.base import QualifiedAnomaly


# =============================================================================
# LABEL PARSER CLASS
# =============================================================================

class LabelParser:
    """
    Parser sémantique pour libellés comptables.

    Attributes:
        config: Configuration du parser
        known_tiers: Liste de tiers connus pour fuzzy matching
        cache: Cache des résultats par hash
    """

    def __init__(
        self,
        config: Optional[ParserConfig] = None,
        known_tiers: Optional[List[str]] = None,
    ):
        self.config = config or ParserConfig()
        self.known_tiers = known_tiers or []
        self._cache: Dict[str, ParsedLabel] = {}

    def parse(self, text: str) -> ParsedLabel:
        """
        Parse un libellé et extrait les features.

        Args:
            text: Libellé brut

        Returns:
            ParsedLabel avec entités et features
        """
        if not text or not text.strip():
            return ParsedLabel(original="", normalized="", entities=[], features=LabelFeatures())

        start_time = time.time()

        # Normaliser
        normalized = ParsedLabel._normalize(text)
        label_hash = ParsedLabel._compute_hash(normalized)

        # Vérifier le cache
        if self.config.cache_enabled and label_hash in self._cache:
            return self._cache[label_hash]

        # Extraction des entités
        entities = self._extract_all_entities(text)

        # Classification
        intent, intent_conf = classify_intent(text)
        operation, op_conf = classify_operation(text)
        is_recurring, recur_conf = detect_recurring(text)
        is_round = detect_round_amount(text)

        # Construire les features
        features = self._build_features(
            entities=entities,
            intent=intent,
            intent_conf=intent_conf,
            operation=operation,
            op_conf=op_conf,
            is_recurring=is_recurring,
            is_round=is_round,
            text=text,
        )

        # Construire le résultat
        parse_time = (time.time() - start_time) * 1000

        result = ParsedLabel(
            original=text,
            normalized=normalized,
            hash=label_hash,
            entities=entities,
            features=features,
            parse_time_ms=parse_time,
        )

        # Mettre en cache
        if self.config.cache_enabled:
            self._add_to_cache(label_hash, result)

        return result

    def parse_batch(self, texts: List[str]) -> List[ParsedLabel]:
        """
        Parse plusieurs libellés.

        Args:
            texts: Liste de libellés

        Returns:
            Liste de ParsedLabel
        """
        return [self.parse(text) for text in texts]

    def _extract_all_entities(self, text: str) -> List[ExtractedEntity]:
        """Extrait toutes les entités avec fallback spaCy."""
        # Extraction regex
        entities = extract_entities(text, self.known_tiers)

        # Enrichissement spaCy si activé et disponible
        if self.config.use_spacy and is_spacy_available():
            spacy_entities = extract_with_spacy(text)
            # Fusionner sans doublons
            entities = self._merge_entities(entities, spacy_entities)

        return entities

    def _merge_entities(
        self,
        primary: List[ExtractedEntity],
        secondary: List[ExtractedEntity],
    ) -> List[ExtractedEntity]:
        """
        Fusionne deux listes d'entités sans doublons.

        Primary (regex) a priorité sur secondary (spaCy).
        """
        result = list(primary)

        for sec_entity in secondary:
            # Vérifier si une entité similaire existe déjà
            overlaps = False
            for prim_entity in primary:
                if (sec_entity.entity_type == prim_entity.entity_type and
                    sec_entity.start < prim_entity.end and
                    sec_entity.end > prim_entity.start):
                    overlaps = True
                    break

            if not overlaps:
                result.append(sec_entity)

        return result

    def _build_features(
        self,
        entities: List[ExtractedEntity],
        intent: Intent,
        intent_conf: float,
        operation: OperationType,
        op_conf: float,
        is_recurring: bool,
        is_round: bool,
        text: str,
    ) -> LabelFeatures:
        """Construit les LabelFeatures à partir des extractions."""
        features = LabelFeatures()

        # Tiers
        tiers_entities = [e for e in entities if e.entity_type == EntityType.TIERS]
        if tiers_entities:
            best_tiers = max(tiers_entities, key=lambda e: e.confidence)
            features.tiers_name = best_tiers.normalized
            features.tiers_confidence = best_tiers.confidence

        # Référence
        ref_entities = [e for e in entities if e.entity_type == EntityType.REFERENCE]
        if ref_entities:
            best_ref = max(ref_entities, key=lambda e: e.confidence)
            features.reference = best_ref.normalized
            features.has_reference = True

        # Montant
        amount_entities = [e for e in entities if e.entity_type == EntityType.MONTANT]
        if amount_entities:
            best_amount = max(amount_entities, key=lambda e: e.confidence)
            try:
                features.amount_extracted = float(best_amount.normalized.replace(",", "."))
            except (ValueError, AttributeError):
                pass

        # Date/Période
        date_entities = [e for e in entities if e.entity_type == EntityType.DATE]
        if date_entities:
            best_date = max(date_entities, key=lambda e: e.confidence)
            features.date_extracted = best_date.value
            features.period_ref = best_date.normalized

        # Lieu
        lieu_entities = [e for e in entities if e.entity_type == EntityType.LIEU]
        if lieu_entities:
            features.lieu = lieu_entities[0].normalized

        # Classification
        features.operation_type = operation
        features.intent = intent

        # Patterns
        features.is_recurring = is_recurring
        features.is_round_amount = is_round

        # Qualité
        features.useful_length = len(text.strip())
        features.language = self._detect_language(text)

        # Confiance globale = moyenne des confiances
        confidences = [e.confidence for e in entities]
        if confidences:
            features.overall_confidence = sum(confidences) / len(confidences)
        else:
            features.overall_confidence = 0.5 if intent != Intent.STANDARD else 0.3

        return features

    def _detect_language(self, text: str) -> str:
        """Détecte la langue (simple heuristique)."""
        # Mots français courants
        fr_words = {"de", "la", "le", "du", "des", "pour", "sur", "avec", "facture", "avoir"}
        # Mots anglais courants
        en_words = {"the", "of", "for", "with", "invoice", "payment", "from"}

        words = set(text.lower().split())

        fr_count = len(words & fr_words)
        en_count = len(words & en_words)

        if en_count > fr_count:
            return "EN"
        return "FR"

    def _add_to_cache(self, key: str, value: ParsedLabel):
        """Ajoute au cache avec gestion de la taille."""
        if len(self._cache) >= self.config.max_cache_size:
            # Supprimer les plus anciens (FIFO simple)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[key] = value

    def clear_cache(self):
        """Vide le cache."""
        self._cache.clear()

    def cache_stats(self) -> Dict[str, int]:
        """Retourne les stats du cache."""
        return {
            "size": len(self._cache),
            "max_size": self.config.max_cache_size,
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

# Parser singleton pour usage simple
_default_parser: Optional[LabelParser] = None


def _get_default_parser() -> LabelParser:
    """Retourne le parser par défaut (singleton)."""
    global _default_parser
    if _default_parser is None:
        _default_parser = LabelParser()
    return _default_parser


def parse_label(text: str) -> ParsedLabel:
    """
    Parse un libellé avec le parser par défaut.

    Args:
        text: Libellé à parser

    Returns:
        ParsedLabel
    """
    return _get_default_parser().parse(text)


def parse_labels(texts: List[str]) -> List[ParsedLabel]:
    """
    Parse plusieurs libellés.

    Args:
        texts: Liste de libellés

    Returns:
        Liste de ParsedLabel
    """
    return _get_default_parser().parse_batch(texts)


def enrich_anomalies(
    anomalies: List["QualifiedAnomaly"],
    libelle_extractor=None,
) -> List["QualifiedAnomaly"]:
    """
    Enrichit des QualifiedAnomaly avec le parsing des libellés.

    Args:
        anomalies: Liste d'anomalies de Layer 3
        libelle_extractor: Fonction pour extraire le libellé d'une anomalie
                          Par défaut: anomaly.signal.metadata.get("libelle", "")

    Returns:
        Liste d'anomalies enrichies (même objets, modifiés in-place)
    """
    parser = _get_default_parser()

    if libelle_extractor is None:
        def libelle_extractor(a):
            return a.signal.metadata.get("libelle", "")

    for anomaly in anomalies:
        libelle = libelle_extractor(anomaly)
        if libelle:
            parsed = parser.parse(libelle)
            # Ajouter au metadata du signal
            anomaly.signal.metadata["parsed_label"] = parsed.to_dict()
            anomaly.signal.metadata["label_features"] = parsed.features.to_dict()

            # Enrichir les champs de l'anomalie si non remplis
            if parsed.features.tiers_name:
                anomaly.signal.tiers = anomaly.signal.tiers or parsed.features.tiers_name

    return anomalies


# =============================================================================
# BATCH PROCESSING
# =============================================================================

def parse_gl_labels(
    gl_data: Any,  # pd.DataFrame
    libelle_column: str = "libelle",
    output_column: str = "parsed",
) -> Any:
    """
    Parse tous les libellés d'un DataFrame GL.

    Usage pour pré-calcul batch (optionnel, car lazy parsing préféré).

    Args:
        gl_data: DataFrame avec colonne libellé
        libelle_column: Nom de la colonne libellé
        output_column: Nom de la colonne de sortie

    Returns:
        DataFrame avec colonne parsed ajoutée
    """
    parser = LabelParser(ParserConfig(cache_enabled=True))

    # Dédupliquer les libellés uniques
    unique_labels = gl_data[libelle_column].dropna().unique()

    # Parser chaque libellé unique
    parsed_map = {}
    for label in unique_labels:
        parsed_map[label] = parser.parse(label)

    # Mapper au DataFrame
    gl_data[output_column] = gl_data[libelle_column].map(
        lambda x: parsed_map.get(x, ParsedLabel(original=x or "")).to_dict()
    )

    return gl_data
