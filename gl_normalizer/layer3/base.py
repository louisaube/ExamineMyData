"""
gl_normalizer/layer3/base.py
Structures de données et classes de base pour Layer 3

Layer 3 = Filtres Métier
- Filtre de matérialité (montant > seuil)
- Exclusions métier (non_signal_si du référentiel)
- Inclusions métier (signal_si = boost pertinence)

Input: ~40 signaux FDR-filtrés de Layer 2.5
Output: ~15 anomalies qualifiées
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..layer2.base import RawSignal, Univers


class FilterReason(str, Enum):
    """Raison du filtrage d'un signal."""
    PASSED = "PASSED"                          # Signal conservé
    BELOW_MATERIALITY = "BELOW_MATERIALITY"    # Montant < seuil matérialité
    EXCLUDED_BY_RULE = "EXCLUDED_BY_RULE"      # non_signal_si match
    LOW_PERTINENCE = "LOW_PERTINENCE"          # Score pertinence < seuil
    DUPLICATE = "DUPLICATE"                    # Signal dupliqué


class PertinenceLevel(str, Enum):
    """Niveau de pertinence métier d'un signal."""
    CRITICAL = "CRITICAL"    # signal_si match + montant élevé
    HIGH = "HIGH"            # signal_si match OU montant très élevé
    MEDIUM = "MEDIUM"        # Statistiquement significatif
    LOW = "LOW"              # Limite de significativité


@dataclass
class QualifiedAnomaly:
    """
    Anomalie qualifiée après filtrage Layer 3.

    Représente un signal validé par les 3 filtres:
    1. Matérialité: montant > seuil
    2. Non-exclusion: aucun non_signal_si ne match
    3. Pertinence: score global suffisant

    Attributes:
        signal: RawSignal source de Layer 2
        materiality_amount: Montant utilisé pour test matérialité
        materiality_threshold: Seuil de matérialité appliqué
        materiality_ratio: materiality_amount / threshold

        exclusion_rules_checked: Règles non_signal_si vérifiées
        exclusion_rules_matched: Règles qui auraient exclu (si bypass)
        is_excluded: True si exclu par règle métier

        pertinence_score: Score de pertinence 0-100
        pertinence_level: Niveau catégorisé
        signal_si_matched: Règles signal_si qui boostent

        final_score: Score final combiné
        rank: Rang dans la liste finale
    """
    # Signal source
    signal: "RawSignal"

    # Matérialité
    materiality_amount: float
    materiality_threshold: float
    materiality_ratio: float = 0.0

    # Exclusions
    exclusion_rules_checked: List[str] = field(default_factory=list)
    exclusion_rules_matched: List[str] = field(default_factory=list)
    is_excluded: bool = False
    exclusion_bypassed: bool = False  # True si exclusion ignorée (override)

    # Pertinence
    pertinence_score: float = 50.0
    pertinence_level: PertinenceLevel = PertinenceLevel.MEDIUM
    signal_si_matched: List[str] = field(default_factory=list)
    pertinence_factors: Dict[str, float] = field(default_factory=dict)

    # Final
    final_score: float = 0.0
    rank: int = 0
    filter_reason: FilterReason = FilterReason.PASSED

    def __post_init__(self):
        """Calcule les champs dérivés."""
        if self.materiality_threshold > 0:
            self.materiality_ratio = self.materiality_amount / self.materiality_threshold

        if self.final_score == 0.0:
            self._compute_final_score()

    def _compute_final_score(self):
        """
        Calcule le score final combiné.

        Formule:
        final = pertinence_score × materiality_factor × pvalue_factor

        - materiality_factor: log(1 + ratio) plafonné à 2.0
        - pvalue_factor: -log10(pvalue) plafonné à 4.0
        """
        import math

        # Factor matérialité: plus c'est au-dessus du seuil, plus c'est important
        mat_factor = min(2.0, math.log1p(self.materiality_ratio))

        # Factor p-value: plus c'est significatif, plus c'est important
        pvalue = self.signal.pvalue_adjusted or self.signal.pvalue or 0.05
        pvalue_factor = min(4.0, -math.log10(max(pvalue, 1e-10)))

        # Score final
        self.final_score = self.pertinence_score * (1 + mat_factor * 0.3) * (1 + pvalue_factor * 0.2)
        self.final_score = min(100.0, self.final_score)

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour sérialisation."""
        return {
            "signal": self.signal.to_dict(),
            "materiality": {
                "amount": self.materiality_amount,
                "threshold": self.materiality_threshold,
                "ratio": self.materiality_ratio,
            },
            "exclusions": {
                "rules_checked": self.exclusion_rules_checked,
                "rules_matched": self.exclusion_rules_matched,
                "is_excluded": self.is_excluded,
                "bypassed": self.exclusion_bypassed,
            },
            "pertinence": {
                "score": self.pertinence_score,
                "level": self.pertinence_level.value,
                "signal_si_matched": self.signal_si_matched,
                "factors": self.pertinence_factors,
            },
            "final_score": self.final_score,
            "rank": self.rank,
            "filter_reason": self.filter_reason.value,
        }


@dataclass
class FilteredSignal:
    """
    Signal filtré (rejeté) par Layer 3.

    Garde trace des signaux éliminés pour audit et debug.
    """
    signal: "RawSignal"
    filter_reason: FilterReason
    filter_details: str = ""

    # Contexte du filtrage
    materiality_amount: Optional[float] = None
    materiality_threshold: Optional[float] = None
    matched_exclusion_rule: Optional[str] = None
    pertinence_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "signal_id": self.signal.id,
            "famille": self.signal.famille,
            "filter_reason": self.filter_reason.value,
            "filter_details": self.filter_details,
            "materiality_amount": self.materiality_amount,
            "materiality_threshold": self.materiality_threshold,
            "matched_exclusion_rule": self.matched_exclusion_rule,
            "pertinence_score": self.pertinence_score,
        }


@dataclass
class Layer3Result:
    """
    Résultat complet de Layer 3.

    Attributes:
        qualified: Anomalies qualifiées (passent tous les filtres)
        filtered_materiality: Filtrés par matérialité
        filtered_exclusion: Filtrés par règles métier
        filtered_pertinence: Filtrés par pertinence

        stats: Statistiques du filtrage
    """
    # Résultats
    qualified: List[QualifiedAnomaly]
    filtered_materiality: List[FilteredSignal]
    filtered_exclusion: List[FilteredSignal]
    filtered_pertinence: List[FilteredSignal]

    # Stats
    n_input: int = 0
    n_output: int = 0
    n_filtered_materiality: int = 0
    n_filtered_exclusion: int = 0
    n_filtered_pertinence: int = 0

    # Config utilisée
    materiality_threshold: float = 0.0
    pertinence_threshold: float = 0.0
    exclusion_rules_applied: int = 0

    def __post_init__(self):
        """Calcule les stats si non fournies."""
        if self.n_output == 0:
            self.n_output = len(self.qualified)
        if self.n_filtered_materiality == 0:
            self.n_filtered_materiality = len(self.filtered_materiality)
        if self.n_filtered_exclusion == 0:
            self.n_filtered_exclusion = len(self.filtered_exclusion)
        if self.n_filtered_pertinence == 0:
            self.n_filtered_pertinence = len(self.filtered_pertinence)

    @property
    def all_filtered(self) -> List[FilteredSignal]:
        """Tous les signaux filtrés."""
        return self.filtered_materiality + self.filtered_exclusion + self.filtered_pertinence

    @property
    def reduction_rate(self) -> float:
        """Taux de réduction (0 à 1)."""
        if self.n_input == 0:
            return 0.0
        return 1 - (self.n_output / self.n_input)

    def summary(self) -> str:
        """Résumé textuel."""
        return f"""
Layer 3 Results (Business Filters):
  Input signals: {self.n_input}
  Qualified anomalies: {self.n_output}

  Filtered by:
    - Materiality (<{self.materiality_threshold:,.0f}€): {self.n_filtered_materiality}
    - Business rules: {self.n_filtered_exclusion}
    - Low pertinence: {self.n_filtered_pertinence}

  Reduction rate: {self.reduction_rate:.0%}

Top 5 Anomalies:
{self._top_5_summary()}
"""

    def _top_5_summary(self) -> str:
        """Résumé des top 5 anomalies."""
        lines = []
        for i, qa in enumerate(self.qualified[:5], 1):
            lines.append(
                f"  {i}. [{qa.signal.famille}] {qa.signal.test_name} "
                f"(score={qa.final_score:.1f}, p={qa.signal.pvalue or 0:.4f})"
            )
        return "\n".join(lines) if lines else "  (aucune anomalie qualifiée)"

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "qualified": [qa.to_dict() for qa in self.qualified],
            "filtered": {
                "materiality": [fs.to_dict() for fs in self.filtered_materiality],
                "exclusion": [fs.to_dict() for fs in self.filtered_exclusion],
                "pertinence": [fs.to_dict() for fs in self.filtered_pertinence],
            },
            "stats": {
                "n_input": self.n_input,
                "n_output": self.n_output,
                "n_filtered_materiality": self.n_filtered_materiality,
                "n_filtered_exclusion": self.n_filtered_exclusion,
                "n_filtered_pertinence": self.n_filtered_pertinence,
                "reduction_rate": self.reduction_rate,
            },
            "config": {
                "materiality_threshold": self.materiality_threshold,
                "pertinence_threshold": self.pertinence_threshold,
                "exclusion_rules_applied": self.exclusion_rules_applied,
            },
        }
