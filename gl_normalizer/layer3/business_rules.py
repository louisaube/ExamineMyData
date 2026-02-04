"""
gl_normalizer/layer3/business_rules.py
Règles Métier: signal_si et non_signal_si

Gère les règles métier du référentiel sémantique:

- non_signal_si: Règles d'exclusion
  "Si cette condition est vraie, ce n'est PAS une anomalie"
  Exemples: montant_rond, meme_montant_12_mois, label_identique

- signal_si: Règles d'inclusion (boost de pertinence)
  "Si cette condition est vraie, c'est PLUS PROBABLEMENT une anomalie"
  Exemples: nouveau_fournisseur, montant_inhabituel

Le référentiel définit ces règles par famille comptable.
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Tuple, Optional, Callable, TYPE_CHECKING
import re

if TYPE_CHECKING:
    from ..layer2.base import RawSignal


# =============================================================================
# RÈGLES D'EXCLUSION (non_signal_si)
# =============================================================================

@dataclass
class ExclusionRule:
    """
    Règle d'exclusion métier.

    Attributes:
        id: Identifiant unique (ex: "EXC-ROUND")
        name: Nom lisible (ex: "Montant rond")
        condition: Fonction (signal, context) → bool
        description: Explication de la règle
    """
    id: str
    name: str
    condition: Callable[["RawSignal", Dict[str, Any]], bool]
    description: str = ""


# Contexte standard pour évaluer les règles
# Le runner doit enrichir ce contexte avec les données du GL
@dataclass
class SignalContext:
    """
    Contexte enrichi pour évaluer les règles métier.

    Calculé par le runner à partir des données GL.
    """
    # Caractéristiques du montant
    is_round: bool = False                  # Montant rond (ex: 1000, 5000)
    is_round_thousands: bool = False        # Rond en milliers
    same_amount_3m: bool = False            # Même montant sur 3 mois
    same_amount_12m: bool = False           # Même montant sur 12 mois

    # Caractéristiques du libellé
    repetitive_label: bool = False          # Libellé identique récurrent
    contains_regularisation: bool = False   # Contient "régul", "correction"
    contains_extourne: bool = False         # Contient "extourne", "annulation"

    # Caractéristiques du compte
    solde_zero: bool = False                # Solde à zéro en fin de période
    extourne_ok: bool = False               # Extourne dans délai normal

    # Caractéristiques de fréquence
    is_monthly_recurrent: bool = False      # Apparaît tous les mois
    is_quarterly_recurrent: bool = False    # Apparaît tous les trimestres

    # Metadata additionnelle
    extra: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra is None:
            self.extra = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_round": self.is_round,
            "is_round_thousands": self.is_round_thousands,
            "same_amount_3m": self.same_amount_3m,
            "same_amount_12m": self.same_amount_12m,
            "repetitive_label": self.repetitive_label,
            "contains_regularisation": self.contains_regularisation,
            "contains_extourne": self.contains_extourne,
            "solde_zero": self.solde_zero,
            "extourne_ok": self.extourne_ok,
            "is_monthly_recurrent": self.is_monthly_recurrent,
            "is_quarterly_recurrent": self.is_quarterly_recurrent,
            "extra": self.extra,
        }


# =============================================================================
# RÈGLES D'EXCLUSION STANDARD
# =============================================================================

def _check_montant_rond(signal: "RawSignal", context: SignalContext) -> bool:
    """Montant rond = pas une anomalie."""
    return context.is_round


def _check_meme_montant_12m(signal: "RawSignal", context: SignalContext) -> bool:
    """Même montant sur 12 mois = charge fixe normale."""
    return context.same_amount_12m


def _check_label_identique(signal: "RawSignal", context: SignalContext) -> bool:
    """Libellé identique récurrent = pas une anomalie."""
    return context.repetitive_label


def _check_solde_zero(signal: "RawSignal", context: SignalContext) -> bool:
    """Solde à zéro = compte soldé normalement."""
    return context.solde_zero


def _check_extourne_delai(signal: "RawSignal", context: SignalContext) -> bool:
    """Extourne dans délai = cut-off normal."""
    return context.extourne_ok


def _check_regularisation(signal: "RawSignal", context: SignalContext) -> bool:
    """Écriture de régularisation identifiée."""
    return context.contains_regularisation


def _check_monthly_recurrent(signal: "RawSignal", context: SignalContext) -> bool:
    """Charge mensuelle récurrente = normale."""
    return context.is_monthly_recurrent and signal.test_id in ["L2-VAR"]


STANDARD_EXCLUSION_RULES: List[ExclusionRule] = [
    ExclusionRule(
        id="EXC-ROUND",
        name="Montant rond",
        condition=lambda s, c: _check_montant_rond(s, c),
        description="Montant rond (1000€, 5000€...) indique souvent une provision ou estimation normale",
    ),
    ExclusionRule(
        id="EXC-SAME12M",
        name="Même montant 12 mois",
        condition=lambda s, c: _check_meme_montant_12m(s, c),
        description="Même montant chaque mois sur 12 mois = charge fixe normale",
    ),
    ExclusionRule(
        id="EXC-LABEL",
        name="Libellé identique récurrent",
        condition=lambda s, c: _check_label_identique(s, c),
        description="Écritures avec libellé identique répété = automatisme normal",
    ),
    ExclusionRule(
        id="EXC-ZERO",
        name="Solde à zéro",
        condition=lambda s, c: _check_solde_zero(s, c),
        description="Compte soldé à zéro en fin de période = pas d'anomalie",
    ),
    ExclusionRule(
        id="EXC-EXTOURNE",
        name="Extourne dans délai",
        condition=lambda s, c: _check_extourne_delai(s, c),
        description="CCA/PCA extournée dans le délai attendu = cut-off normal",
    ),
    ExclusionRule(
        id="EXC-REGUL",
        name="Régularisation identifiée",
        condition=lambda s, c: _check_regularisation(s, c),
        description="Écriture de régularisation explicite dans le libellé",
    ),
    ExclusionRule(
        id="EXC-RECUR",
        name="Charge mensuelle récurrente",
        condition=lambda s, c: _check_monthly_recurrent(s, c),
        description="Variation sur charge mensuelle récurrente = ajustement normal",
    ),
]


def get_exclusion_rules_for_family(
    famille: str,
    referentiel: Dict[str, Any],
) -> List[str]:
    """
    Récupère les règles non_signal_si du référentiel pour une famille.

    Args:
        famille: Code famille PCG
        referentiel: Référentiel sémantique

    Returns:
        Liste des identifiants de règles applicables
    """
    ref_entry = referentiel.get(famille, {})
    non_signal_si = ref_entry.get("non_signal_si", [])

    # Les règles peuvent être des strings simples ou des dicts
    rules = []
    for rule in non_signal_si:
        if isinstance(rule, str):
            rules.append(rule)
        elif isinstance(rule, dict):
            rules.append(rule.get("id", rule.get("rule", str(rule))))

    return rules


def parse_exclusion_rule(rule_text: str) -> Optional[str]:
    """
    Parse une règle non_signal_si du référentiel.

    Mapping des règles textuelles vers les IDs standard:
    - "montant_rond" → EXC-ROUND
    - "meme_montant_12_mois" → EXC-SAME12M
    - etc.
    """
    rule_lower = rule_text.lower().replace(" ", "_")

    mappings = {
        "montant_rond": "EXC-ROUND",
        "round_amount": "EXC-ROUND",
        "meme_montant_12_mois": "EXC-SAME12M",
        "meme_montant_12m": "EXC-SAME12M",
        "same_amount_12m": "EXC-SAME12M",
        "label_identique": "EXC-LABEL",
        "repetitive_label": "EXC-LABEL",
        "solde_zero": "EXC-ZERO",
        "zero_balance": "EXC-ZERO",
        "extourne_dans_delai": "EXC-EXTOURNE",
        "extourne_ok": "EXC-EXTOURNE",
        "regularisation": "EXC-REGUL",
        "regul": "EXC-REGUL",
        "mensuel_recurrent": "EXC-RECUR",
        "monthly_recurrent": "EXC-RECUR",
    }

    for pattern, rule_id in mappings.items():
        if pattern in rule_lower:
            return rule_id

    return None


def check_exclusions(
    signal: "RawSignal",
    context: SignalContext,
    referentiel: Dict[str, Any],
    rules: Optional[List[ExclusionRule]] = None,
) -> Tuple[bool, List[str], List[str]]:
    """
    Vérifie si un signal doit être exclu par les règles métier.

    Args:
        signal: RawSignal à évaluer
        context: SignalContext avec les caractéristiques
        referentiel: Référentiel sémantique
        rules: Règles à appliquer (défaut: STANDARD_EXCLUSION_RULES)

    Returns:
        Tuple (is_excluded, rules_checked, rules_matched):
        - is_excluded: True si au moins une règle matche
        - rules_checked: IDs des règles vérifiées
        - rules_matched: IDs des règles qui ont matché
    """
    if rules is None:
        rules = STANDARD_EXCLUSION_RULES

    # Récupérer les règles applicables pour cette famille
    family_rules = get_exclusion_rules_for_family(signal.famille, referentiel)

    # Parser les règles du référentiel
    applicable_rule_ids = set()
    for rule_text in family_rules:
        rule_id = parse_exclusion_rule(rule_text)
        if rule_id:
            applicable_rule_ids.add(rule_id)

    # Si pas de règles spécifiées, appliquer toutes les règles standard
    if not applicable_rule_ids:
        applicable_rule_ids = {r.id for r in rules}

    rules_checked = []
    rules_matched = []

    for rule in rules:
        if rule.id not in applicable_rule_ids:
            continue

        rules_checked.append(rule.id)

        try:
            if rule.condition(signal, context):
                rules_matched.append(rule.id)
        except Exception:
            # En cas d'erreur, ne pas exclure
            pass

    is_excluded = len(rules_matched) > 0
    return (is_excluded, rules_checked, rules_matched)


# =============================================================================
# RÈGLES D'INCLUSION (signal_si) - BOOST PERTINENCE
# =============================================================================

@dataclass
class InclusionRule:
    """
    Règle d'inclusion métier (boost de pertinence).

    Attributes:
        id: Identifiant unique
        name: Nom lisible
        condition: Fonction (signal, context) → bool
        boost: Points de pertinence ajoutés si match (0-30)
        description: Explication
    """
    id: str
    name: str
    condition: Callable[["RawSignal", Dict[str, Any]], bool]
    boost: float = 10.0
    description: str = ""


def _check_first_time(signal: "RawSignal", context: SignalContext) -> bool:
    """Première occurrence de ce type d'écriture."""
    return context.extra.get("is_first_occurrence", False)


def _check_year_end(signal: "RawSignal", context: SignalContext) -> bool:
    """Écriture en fin d'exercice (décembre)."""
    periode = signal.periode or ""
    return periode.endswith("-12") or periode.endswith("12")


def _check_high_amount(signal: "RawSignal", context: SignalContext) -> bool:
    """Montant exceptionnellement élevé (>3σ)."""
    return context.extra.get("is_high_amount", False)


def _check_unusual_journal(signal: "RawSignal", context: SignalContext) -> bool:
    """Journal inhabituel pour ce compte."""
    return context.extra.get("unusual_journal", False)


STANDARD_INCLUSION_RULES: List[InclusionRule] = [
    InclusionRule(
        id="INC-FIRST",
        name="Première occurrence",
        condition=lambda s, c: _check_first_time(s, c),
        boost=15.0,
        description="Première fois qu'une écriture de ce type apparaît",
    ),
    InclusionRule(
        id="INC-YEAREND",
        name="Fin d'exercice",
        condition=lambda s, c: _check_year_end(s, c),
        boost=10.0,
        description="Écriture passée en décembre (risque de window dressing)",
    ),
    InclusionRule(
        id="INC-HIGH",
        name="Montant exceptionnellement élevé",
        condition=lambda s, c: _check_high_amount(s, c),
        boost=20.0,
        description="Montant dépasse 3 écarts-types de la moyenne historique",
    ),
    InclusionRule(
        id="INC-JOURNAL",
        name="Journal inhabituel",
        condition=lambda s, c: _check_unusual_journal(s, c),
        boost=15.0,
        description="Écriture passée dans un journal inattendu pour ce compte",
    ),
]


def check_inclusions(
    signal: "RawSignal",
    context: SignalContext,
    referentiel: Dict[str, Any],
    rules: Optional[List[InclusionRule]] = None,
) -> Tuple[float, List[str]]:
    """
    Vérifie les règles signal_si et calcule le boost de pertinence.

    Args:
        signal: RawSignal à évaluer
        context: SignalContext
        referentiel: Référentiel sémantique
        rules: Règles à appliquer

    Returns:
        Tuple (total_boost, rules_matched):
        - total_boost: Points de pertinence à ajouter
        - rules_matched: IDs des règles qui ont matché
    """
    if rules is None:
        rules = STANDARD_INCLUSION_RULES

    total_boost = 0.0
    rules_matched = []

    for rule in rules:
        try:
            if rule.condition(signal, context):
                total_boost += rule.boost
                rules_matched.append(rule.id)
        except Exception:
            pass

    return (total_boost, rules_matched)


# =============================================================================
# COMPUTE SIGNAL CONTEXT
# =============================================================================

def compute_signal_context(
    signal: "RawSignal",
    historical_amounts: List[float],
    historical_labels: Optional[List[str]] = None,
) -> SignalContext:
    """
    Calcule le contexte d'un signal à partir des données historiques.

    Args:
        signal: RawSignal
        historical_amounts: Liste des montants historiques
        historical_labels: Liste des libellés historiques (optionnel)

    Returns:
        SignalContext enrichi
    """
    context = SignalContext()

    # Caractéristiques du montant
    if signal.metric_value > 0:
        amount = signal.metric_value
        context.is_round = _is_round_amount(amount)
        context.is_round_thousands = _is_round_thousands(amount)

    # Même montant récurrent
    if historical_amounts:
        context.same_amount_3m = _check_same_amount(historical_amounts, months=3)
        context.same_amount_12m = _check_same_amount(historical_amounts, months=12)
        context.is_monthly_recurrent = len(historical_amounts) >= 6

    # Caractéristiques du libellé
    if historical_labels:
        context.repetitive_label = _check_repetitive_labels(historical_labels)

    # Solde (si disponible dans metadata)
    if signal.metadata.get("solde") == 0:
        context.solde_zero = True

    return context


def _is_round_amount(amount: float, tolerance: float = 0.01) -> bool:
    """Vérifie si un montant est rond (100, 500, 1000...)."""
    if amount <= 0:
        return False

    for base in [100, 500, 1000, 5000, 10000]:
        if abs(amount % base) < tolerance * base:
            return True

    return False


def _is_round_thousands(amount: float) -> bool:
    """Vérifie si un montant est rond en milliers."""
    if amount < 1000:
        return False
    return abs(amount % 1000) < 1


def _check_same_amount(amounts: List[float], months: int = 12, tolerance: float = 0.001) -> bool:
    """Vérifie si les derniers N mois ont le même montant."""
    if len(amounts) < months:
        return False

    recent = amounts[-months:]
    if not recent:
        return False

    first = recent[0]
    if first == 0:
        return all(a == 0 for a in recent)

    return all(abs(a - first) / abs(first) < tolerance for a in recent)


def _check_repetitive_labels(labels: List[str], min_repeat: int = 3) -> bool:
    """Vérifie si un libellé se répète fréquemment."""
    if len(labels) < min_repeat:
        return False

    # Normaliser les libellés
    normalized = [l.strip().lower() for l in labels if l]

    # Compter les occurrences
    from collections import Counter
    counts = Counter(normalized)

    if not counts:
        return False

    # Le libellé le plus fréquent représente-t-il >50% des écritures?
    most_common_count = counts.most_common(1)[0][1]
    return most_common_count >= min_repeat and most_common_count / len(normalized) > 0.5
