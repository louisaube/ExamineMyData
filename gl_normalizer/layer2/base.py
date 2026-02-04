"""
gl_normalizer/layer2/base.py
Structures de données et classes de base pour Layer 2

Définit:
- Univers: Enum des 10 univers sémantiques
- RawSignal: Signal brut généré par un test
- FamilySignal: Signal agrégé par famille
- BaseUniverseTest: Classe abstraite pour les tests par univers
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


class Univers(str, Enum):
    """
    Univers sémantiques pour classification des familles comptables.

    Chaque univers a un comportement attendu différent et donc
    des tests de normalité spécifiques.
    """
    CRISTALLIN = "CRISTALLIN"              # Charges fixes récurrentes (loyers, abonnements)
    NOMINATIF_TIERS = "NOMINATIF_TIERS"    # Auxiliaires clients/fournisseurs (411, 401)
    NOMINATIF_OPERATIONNEL = "NOMINATIF_OPERATIONNEL"  # Charges par site
    PROCESSUS = "PROCESSUS"                # Cycles réguliers (social, fiscal)
    VENTILATION = "VENTILATION"            # ABT, analytique (488)
    CUT_OFF = "CUT_OFF"                    # Régularisations (CCA, PCA, FNP, FAE)
    TRESORERIE = "TRESORERIE"              # Comptes bancaires et virements
    PONCTUEL = "PONCTUEL"                  # Exceptionnel (67x, 77x)
    INVENTAIRE = "INVENTAIRE"              # Stocks et immobilisations
    COMPOSITE = "COMPOSITE"                # Non classifiable


@dataclass
class RawSignal:
    """
    Signal brut généré par un test de normalité.

    Structure standard pour le découplage Layer 2 ↔ Layer 3.
    Chaque test génère 0 à N RawSignal selon les anomalies détectées.

    Attributes:
        id: Identifiant unique du signal (ex: "T-CRIS-01_613_202401")
        famille: Code famille PCG (ex: "613")
        univers: Univers sémantique de la famille
        test_id: Identifiant du test (ex: "T-CRIS-01")
        test_name: Nom lisible du test (ex: "Variation montant")

        metric_value: Valeur mesurée (ex: 0.08 pour 8% de variation)
        threshold: Seuil de déclenchement utilisé
        delta: Écart au seuil (metric_value - threshold)

        periode: Période concernée si applicable (ex: "2024-01")
        site: Code site si test inter-sites
        tiers: Nom tiers si test nominatif

        signal_si_matched: Règles signal_si du référentiel matchées
        non_signal_si_matched: Exclusions non_signal_si matchées

        raw_score: Score brut 0-100 avant filtrage Layer 3
        metadata: Données additionnelles pour contexte
    """
    # Identification
    id: str
    famille: str
    univers: Univers
    test_id: str
    test_name: str

    # Mesure
    metric_value: float
    threshold: float
    delta: float

    # Contexte optionnel
    periode: Optional[str] = None
    site: Optional[str] = None
    tiers: Optional[str] = None

    # Règles référentiel
    signal_si_matched: List[str] = field(default_factory=list)
    non_signal_si_matched: List[str] = field(default_factory=list)

    # Scoring
    raw_score: float = 0.0

    # P-value (Conformal Prediction ou autre méthode distribution-free)
    pvalue: Optional[float] = None
    pvalue_adjusted: Optional[float] = None  # Après correction BH-FDR
    detection_method: str = "threshold"  # "conformal", "matrix_profile", "ecod", "threshold"

    # Métadonnées
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Calcule le score brut si non fourni."""
        if self.raw_score == 0.0 and self.delta > 0:
            # Score = écart normalisé par le seuil, plafonné à 100
            self.raw_score = min(100.0, (self.delta / max(self.threshold, 0.01)) * 50)

    @property
    def is_excluded(self) -> bool:
        """True si une exclusion métier s'applique."""
        return len(self.non_signal_si_matched) > 0

    @property
    def severity(self) -> str:
        """
        Sévérité basée sur la p-value (si disponible) ou le score brut.

        P-value severity:
        - p < 0.001: CRITICAL
        - p < 0.01:  HIGH
        - p < 0.05:  MEDIUM
        - p >= 0.05: LOW
        """
        if self.pvalue is not None:
            if self.pvalue < 0.001:
                return "CRITICAL"
            elif self.pvalue < 0.01:
                return "HIGH"
            elif self.pvalue < 0.05:
                return "MEDIUM"
            else:
                return "LOW"
        else:
            # Fallback sur raw_score
            if self.raw_score >= 80:
                return "CRITICAL"
            elif self.raw_score >= 60:
                return "HIGH"
            elif self.raw_score >= 40:
                return "MEDIUM"
            else:
                return "LOW"

    @property
    def is_significant(self) -> bool:
        """True si statistiquement significatif (p < 0.05 ou score élevé)."""
        if self.pvalue_adjusted is not None:
            return self.pvalue_adjusted < 0.05
        if self.pvalue is not None:
            return self.pvalue < 0.05
        return self.raw_score >= 50

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour sérialisation."""
        return {
            "id": self.id,
            "famille": self.famille,
            "univers": self.univers.value if isinstance(self.univers, Enum) else self.univers,
            "test_id": self.test_id,
            "test_name": self.test_name,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "delta": self.delta,
            "periode": self.periode,
            "site": self.site,
            "tiers": self.tiers,
            "signal_si_matched": self.signal_si_matched,
            "non_signal_si_matched": self.non_signal_si_matched,
            "raw_score": self.raw_score,
            "pvalue": self.pvalue,
            "pvalue_adjusted": self.pvalue_adjusted,
            "detection_method": self.detection_method,
            "is_excluded": self.is_excluded,
            "is_significant": self.is_significant,
            "severity": self.severity,
            "metadata": self.metadata,
        }


@dataclass
class FamilySignal:
    """
    Signal agrégé par famille comptable.

    Layer 2 retourne 1 FamilySignal par famille ayant au moins un signal,
    pas N RawSignal individuels. Cela simplifie Layer 3.

    Attributes:
        famille: Code famille PCG
        univers: Univers sémantique
        tests_triggered: Liste des test_id ayant déclenché
        max_score: Score maximum parmi les signaux
        signals: Liste des RawSignal sous-jacents
        summary: Résumé textuel des anomalies
    """
    famille: str
    univers: Univers
    tests_triggered: List[str]
    max_score: float
    signals: List[RawSignal]
    summary: str = ""

    @property
    def count(self) -> int:
        """Nombre de signaux pour cette famille."""
        return len(self.signals)

    @property
    def has_exclusions(self) -> bool:
        """True si au moins un signal a une exclusion."""
        return any(s.is_excluded for s in self.signals)

    @property
    def active_signals(self) -> List[RawSignal]:
        """Signaux non exclus par les règles métier."""
        return [s for s in self.signals if not s.is_excluded]

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "famille": self.famille,
            "univers": self.univers.value if isinstance(self.univers, Enum) else self.univers,
            "tests_triggered": self.tests_triggered,
            "max_score": self.max_score,
            "count": self.count,
            "has_exclusions": self.has_exclusions,
            "summary": self.summary,
            "signals": [s.to_dict() for s in self.signals],
        }


class BaseUniverseTest(ABC):
    """
    Classe abstraite pour les tests de normalité par univers.

    Chaque test hérite de cette classe et implémente:
    - test_id: Identifiant unique (ex: "T-CRIS-01")
    - test_name: Nom lisible
    - applicable_univers: Liste des univers où le test s'applique
    - run(): Exécution du test sur les données d'une famille

    Usage:
        class VariationMontantTest(BaseUniverseTest):
            test_id = "T-CRIS-01"
            test_name = "Variation montant"
            applicable_univers = [Univers.CRISTALLIN]

            def run(self, famille_data, referentiel_entry) -> List[RawSignal]:
                # Implementation...
    """

    # À surcharger dans les sous-classes
    test_id: str = "T-BASE-00"
    test_name: str = "Base Test"
    applicable_univers: List[Univers] = field(default_factory=list)

    def __init__(self, referentiel: Dict[str, Any]):
        """
        Args:
            referentiel: Dictionnaire du référentiel sémantique (famille → metadata)
        """
        self.referentiel = referentiel

    def applies_to(self, univers: Univers) -> bool:
        """Vérifie si le test s'applique à cet univers."""
        return univers in self.applicable_univers

    def get_threshold(self, famille: str) -> float:
        """
        Récupère le seuil calibré pour cette famille.

        Utilise calibration.dead_band() avec le cv_montant du référentiel.
        À surcharger si le test utilise un autre type de seuil.
        """
        from .calibration import dead_band

        ref_entry = self.referentiel.get(famille, {})
        cv_montant = ref_entry.get("cv_montant", 1.0)
        return dead_band(cv_montant)

    def check_exclusions(
        self,
        signal_context: Dict[str, Any],
        famille: str
    ) -> List[str]:
        """
        Vérifie si des exclusions métier s'appliquent.

        Args:
            signal_context: Contexte du signal (montant_rond, meme_montant_12m, etc.)
            famille: Code famille pour lookup référentiel

        Returns:
            Liste des exclusions matchées (vide si aucune)
        """
        ref_entry = self.referentiel.get(famille, {})
        non_signal_si = ref_entry.get("non_signal_si", [])

        matched = []
        for exclusion in non_signal_si:
            # Parse simple des exclusions courantes
            if "montant_rond" in exclusion and signal_context.get("is_round", False):
                matched.append(exclusion)
            elif "meme_montant_12_mois" in exclusion and signal_context.get("same_amount_12m", False):
                matched.append(exclusion)
            elif "label_identique" in exclusion and signal_context.get("repetitive_label", False):
                matched.append(exclusion)
            elif "solde_zero" in exclusion and signal_context.get("solde_zero", False):
                matched.append(exclusion)
            elif "extourne_dans_delai" in exclusion and signal_context.get("extourne_ok", False):
                matched.append(exclusion)

        return matched

    def check_inclusions(
        self,
        signal_context: Dict[str, Any],
        famille: str
    ) -> List[str]:
        """
        Vérifie si des règles signal_si matchent (boost de pertinence).

        Args:
            signal_context: Contexte du signal
            famille: Code famille

        Returns:
            Liste des signal_si matchés
        """
        ref_entry = self.referentiel.get(famille, {})
        signal_si = ref_entry.get("signal_si", [])

        matched = []
        for rule in signal_si:
            # Les règles signal_si sont généralement des conditions textuelles
            # On les retourne pour information, le matching exact est dans le test
            if any(keyword in rule.lower() for keyword in signal_context.get("keywords", [])):
                matched.append(rule)

        return matched

    def create_signal(
        self,
        famille: str,
        univers: Univers,
        metric_value: float,
        threshold: float,
        periode: Optional[str] = None,
        site: Optional[str] = None,
        tiers: Optional[str] = None,
        signal_context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RawSignal:
        """
        Factory method pour créer un RawSignal standardisé.

        Args:
            famille: Code famille PCG
            univers: Univers sémantique
            metric_value: Valeur mesurée
            threshold: Seuil utilisé
            periode: Période si applicable
            site: Site si inter-sites
            tiers: Tiers si nominatif
            signal_context: Contexte pour exclusions
            metadata: Données additionnelles

        Returns:
            RawSignal configuré avec exclusions vérifiées
        """
        signal_context = signal_context or {}
        metadata = metadata or {}

        # Vérifier exclusions et inclusions
        exclusions = self.check_exclusions(signal_context, famille)
        inclusions = self.check_inclusions(signal_context, famille)

        # Générer ID unique
        signal_id = f"{self.test_id}_{famille}"
        if periode:
            signal_id += f"_{periode.replace('-', '')}"
        if site:
            signal_id += f"_{site}"

        return RawSignal(
            id=signal_id,
            famille=famille,
            univers=univers,
            test_id=self.test_id,
            test_name=self.test_name,
            metric_value=metric_value,
            threshold=threshold,
            delta=max(0, metric_value - threshold),
            periode=periode,
            site=site,
            tiers=tiers,
            signal_si_matched=inclusions,
            non_signal_si_matched=exclusions,
            metadata=metadata,
        )

    @abstractmethod
    def run(
        self,
        famille: str,
        famille_data: "pd.DataFrame",
        univers: Univers,
    ) -> List[RawSignal]:
        """
        Exécute le test sur les données d'une famille.

        Args:
            famille: Code famille PCG (ex: "613")
            famille_data: DataFrame des écritures de cette famille
                         Colonnes attendues: periode, montant, journal, libelle, site...
            univers: Univers sémantique de la famille

        Returns:
            Liste de RawSignal (vide si aucune anomalie détectée)
        """
        pass
