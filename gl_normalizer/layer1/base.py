"""
gl_normalizer/layer1/base.py
Structures de données pour le Label Parser

Définit les dataclasses et enums utilisés par Layer 1:
- ParsedLabel: Résultat complet du parsing
- LabelFeatures: Features extraites
- ExtractedEntity: Entité avec position et confiance
- OperationType, Intent: Enums de classification
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
import hashlib


class OperationType(str, Enum):
    """Type d'opération comptable détecté."""
    ACHAT = "ACHAT"
    VENTE = "VENTE"
    PROVISION = "PROVISION"
    DOTATION = "DOTATION"
    REPRISE = "REPRISE"
    SALAIRE = "SALAIRE"
    CHARGE_FIXE = "CHARGE_FIXE"
    INVESTISSEMENT = "INVESTISSEMENT"
    CESSION = "CESSION"
    REGULARISATION = "REGULARISATION"
    EXTOURNE = "EXTOURNE"
    VIREMENT = "VIREMENT"
    INCONNU = "INCONNU"


class Intent(str, Enum):
    """Intention détectée dans le libellé."""
    STANDARD = "STANDARD"           # Opération normale
    REGULARISATION = "REGULARISATION"  # Correction/ajustement
    EXTOURNE = "EXTOURNE"           # Annulation
    PROVISION = "PROVISION"         # Dotation provision
    CLOTURE = "CLOTURE"             # Écriture de clôture
    INTERCO = "INTERCO"             # Inter-compagnie
    MANUEL = "MANUEL"               # Écriture manuelle identifiée
    AUTOMATIQUE = "AUTOMATIQUE"     # Écriture automatique


class EntityType(str, Enum):
    """Type d'entité extraite."""
    TIERS = "TIERS"           # Nom fournisseur/client
    MONTANT = "MONTANT"       # Montant numérique
    DATE = "DATE"             # Date ou période
    REFERENCE = "REFERENCE"   # N° facture, bon commande
    LIEU = "LIEU"             # Site, agence, pays
    PROJET = "PROJET"         # Code projet


@dataclass
class ExtractedEntity:
    """
    Entité extraite du libellé.

    Attributes:
        entity_type: Type d'entité
        value: Valeur extraite (string)
        normalized: Valeur normalisée (optionnel)
        start: Position début dans le libellé
        end: Position fin
        confidence: Score de confiance 0-1
        source: Méthode d'extraction (regex, spacy, fuzzy)
    """
    entity_type: EntityType
    value: str
    normalized: Optional[str] = None
    start: int = 0
    end: int = 0
    confidence: float = 1.0
    source: str = "regex"

    def __post_init__(self):
        if self.normalized is None:
            self.normalized = self.value.strip().upper()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.entity_type.value,
            "value": self.value,
            "normalized": self.normalized,
            "span": [self.start, self.end],
            "confidence": self.confidence,
            "source": self.source,
        }


@dataclass
class LabelFeatures:
    """
    Features extraites du libellé.

    Résumé structuré des entités et classifications.
    """
    # Entités principales
    tiers_name: Optional[str] = None
    tiers_confidence: float = 0.0

    reference: Optional[str] = None
    reference_type: Optional[str] = None  # FACTURE, BON_COMMANDE, etc.

    amount_extracted: Optional[float] = None
    amount_currency: str = "EUR"

    date_extracted: Optional[str] = None
    period_ref: Optional[str] = None  # "janvier 2024", "Q1 2024"

    lieu: Optional[str] = None

    # Classification
    operation_type: OperationType = OperationType.INCONNU
    intent: Intent = Intent.STANDARD

    # Patterns
    is_recurring: bool = False
    is_round_amount: bool = False
    has_reference: bool = False

    # Qualité
    useful_length: int = 0  # Longueur sans bruit
    language: str = "FR"
    overall_confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tiers": {
                "name": self.tiers_name,
                "confidence": self.tiers_confidence,
            },
            "reference": {
                "value": self.reference,
                "type": self.reference_type,
            },
            "amount": {
                "value": self.amount_extracted,
                "currency": self.amount_currency,
            },
            "date": {
                "extracted": self.date_extracted,
                "period": self.period_ref,
            },
            "lieu": self.lieu,
            "classification": {
                "operation_type": self.operation_type.value,
                "intent": self.intent.value,
            },
            "patterns": {
                "is_recurring": self.is_recurring,
                "is_round_amount": self.is_round_amount,
                "has_reference": self.has_reference,
            },
            "quality": {
                "useful_length": self.useful_length,
                "language": self.language,
                "confidence": self.overall_confidence,
            },
        }


@dataclass
class ParsedLabel:
    """
    Résultat complet du parsing d'un libellé.

    Attributes:
        original: Libellé original
        normalized: Libellé normalisé (uppercase, trim)
        hash: Hash MD5 pour cache/dédup
        entities: Liste des entités extraites
        features: Features agrégées
        raw_extractions: Détails bruts (debug)
    """
    original: str
    normalized: str = ""
    hash: str = ""

    entities: List[ExtractedEntity] = field(default_factory=list)
    features: LabelFeatures = field(default_factory=LabelFeatures)

    raw_extractions: Dict[str, Any] = field(default_factory=dict)
    parse_time_ms: float = 0.0

    def __post_init__(self):
        if not self.normalized:
            self.normalized = self._normalize(self.original)
        if not self.hash:
            self.hash = self._compute_hash(self.normalized)

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalise un libellé."""
        if not text:
            return ""
        # Uppercase, trim, collapse whitespace
        import re
        normalized = text.strip().upper()
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized

    @staticmethod
    def _compute_hash(text: str) -> str:
        """Calcule hash MD5 pour cache."""
        return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]

    def get_entities_by_type(self, entity_type: EntityType) -> List[ExtractedEntity]:
        """Retourne les entités d'un type donné."""
        return [e for e in self.entities if e.entity_type == entity_type]

    def has_entity(self, entity_type: EntityType) -> bool:
        """Vérifie si une entité de ce type existe."""
        return any(e.entity_type == entity_type for e in self.entities)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original": self.original,
            "normalized": self.normalized,
            "hash": self.hash,
            "entities": [e.to_dict() for e in self.entities],
            "features": self.features.to_dict(),
            "parse_time_ms": self.parse_time_ms,
        }

    def summary(self) -> str:
        """Résumé one-line du parsing."""
        parts = []
        if self.features.tiers_name:
            parts.append(f"Tiers: {self.features.tiers_name}")
        if self.features.reference:
            parts.append(f"Réf: {self.features.reference}")
        if self.features.operation_type != OperationType.INCONNU:
            parts.append(f"Type: {self.features.operation_type.value}")
        if self.features.intent != Intent.STANDARD:
            parts.append(f"Intent: {self.features.intent.value}")

        if not parts:
            return f"[{self.hash}] (pas d'extraction)"

        return f"[{self.hash}] " + " | ".join(parts)


@dataclass
class ParserConfig:
    """
    Configuration du LabelParser.

    Attributes:
        use_spacy: Utiliser spaCy NER (si disponible)
        use_fuzzy: Utiliser matching fuzzy pour tiers
        min_confidence: Seuil de confiance minimum
        cache_enabled: Activer le cache par hash
        max_cache_size: Taille max du cache
    """
    use_spacy: bool = True
    use_fuzzy: bool = True
    min_confidence: float = 0.5
    cache_enabled: bool = True
    max_cache_size: int = 10000

    # Patterns personnalisés
    custom_tiers_patterns: List[str] = field(default_factory=list)
    custom_reference_patterns: List[str] = field(default_factory=list)

    # Timeouts
    spacy_timeout_ms: int = 100
    total_timeout_ms: int = 500
