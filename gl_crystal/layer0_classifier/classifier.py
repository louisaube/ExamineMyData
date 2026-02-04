"""
GL Crystal - Classifieur Sémantique

Orchestre la classification de tous les couples d'un GL.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from ..normalizer.schema import GLSchema, EnrichedEntry
from .univers import UniversSemantique, UNIVERS_PROFILES
from .features import extract_classification_features
from .rules import classify_couple


@dataclass
class ClassificationResult:
    """Résultat de classification pour un couple."""
    couple_id: str
    compte_general: str
    analytique: Optional[str]

    univers: UniversSemantique
    confiance: float  # 0-1
    raison: str

    # Features utilisées
    nb_ecritures: int
    volume_total: float
    shannon_brut: float
    shannon_normalise: float
    cv_montants: float
    regularite_temporelle: float
    nb_journaux: int
    nb_contreparties: int

    # Métadonnées
    famille: str = ""

    def to_dict(self) -> dict:
        return {
            'couple_id': self.couple_id,
            'compte_general': self.compte_general,
            'analytique': self.analytique,
            'univers': self.univers.value,
            'confiance': self.confiance,
            'raison': self.raison,
            'nb_ecritures': self.nb_ecritures,
            'volume_total': self.volume_total,
            'shannon_brut': self.shannon_brut,
            'shannon_normalise': self.shannon_normalise,
            'cv_montants': self.cv_montants,
            'regularite_temporelle': self.regularite_temporelle,
            'nb_journaux': self.nb_journaux,
            'nb_contreparties': self.nb_contreparties,
            'famille': self.famille,
        }


@dataclass
class ClassificationSummary:
    """Résumé de la classification d'un GL."""
    total_couples: int
    total_ecritures: int
    total_volume: float

    # Répartition par univers
    par_univers: Dict[str, Dict] = field(default_factory=dict)

    # Alertes
    faible_confiance: List[ClassificationResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'total_couples': self.total_couples,
            'total_ecritures': self.total_ecritures,
            'total_volume': self.total_volume,
            'par_univers': self.par_univers,
            'nb_faible_confiance': len(self.faible_confiance),
        }


class SemanticClassifier:
    """
    Classifieur sémantique pour GL.

    Usage:
        classifier = SemanticClassifier()
        results = classifier.classify(schema)

        # Accès aux résultats
        for r in results.classifications:
            print(f"{r.couple_id}: {r.univers.value} ({r.confiance:.0%})")

        # Résumé
        print(results.summary.par_univers)
    """

    def __init__(self, min_ecritures: int = 3):
        """
        Args:
            min_ecritures: Nombre minimum d'écritures pour classifier un couple
        """
        self.min_ecritures = min_ecritures

    def classify(self, schema: GLSchema) -> 'ClassificationResults':
        """
        Classifie tous les couples du GL.

        Args:
            schema: GLSchema enrichi

        Returns:
            ClassificationResults
        """
        # Groupe les écritures par couple
        couples = self._group_by_couple(schema.entries)

        # Classifie chaque couple
        classifications = []
        for couple_id, ecritures in couples.items():
            if len(ecritures) < self.min_ecritures:
                continue

            result = self._classify_couple(couple_id, ecritures)
            classifications.append(result)

        # Construit le résumé
        summary = self._build_summary(classifications)

        return ClassificationResults(
            classifications=classifications,
            summary=summary,
        )

    def _group_by_couple(
        self,
        entries: List[EnrichedEntry]
    ) -> Dict[str, List[EnrichedEntry]]:
        """Groupe les écritures par couple (compte|analytique)."""
        couples = defaultdict(list)
        for entry in entries:
            # Couple = compte général + analytique
            couple_id = f"{entry.compte_general}|{entry.analytique or ''}"
            couples[couple_id].append(entry)
        return dict(couples)

    def _classify_couple(
        self,
        couple_id: str,
        ecritures: List[EnrichedEntry]
    ) -> ClassificationResult:
        """Classifie un couple."""
        # Extrait les features
        features = extract_classification_features(ecritures, couple_id)

        # Applique les règles
        univers, confiance, raison = classify_couple(features)

        return ClassificationResult(
            couple_id=couple_id,
            compte_general=features.get('compte_general', ''),
            analytique=features.get('analytique'),
            univers=univers,
            confiance=confiance,
            raison=raison,
            nb_ecritures=features.get('nb_ecritures', 0),
            volume_total=features.get('volume_total', 0),
            shannon_brut=features.get('shannon_brut', 0),
            shannon_normalise=features.get('shannon_normalise', 0),
            cv_montants=features.get('cv_montants', 0),
            regularite_temporelle=features.get('regularite_temporelle', 0),
            nb_journaux=features.get('nb_journaux', 0),
            nb_contreparties=features.get('nb_contreparties', 0),
            famille=features.get('famille', ''),
        )

    def _build_summary(
        self,
        classifications: List[ClassificationResult]
    ) -> ClassificationSummary:
        """Construit le résumé de classification."""
        total_couples = len(classifications)
        total_ecritures = sum(c.nb_ecritures for c in classifications)
        total_volume = sum(c.volume_total for c in classifications)

        # Répartition par univers
        par_univers = {}
        for univers in UniversSemantique:
            couples_univers = [c for c in classifications if c.univers == univers]
            nb_couples = len(couples_univers)
            nb_ecritures = sum(c.nb_ecritures for c in couples_univers)
            volume = sum(c.volume_total for c in couples_univers)

            par_univers[univers.value] = {
                'nb_couples': nb_couples,
                'pct_couples': nb_couples / total_couples if total_couples > 0 else 0,
                'nb_ecritures': nb_ecritures,
                'pct_ecritures': nb_ecritures / total_ecritures if total_ecritures > 0 else 0,
                'volume': volume,
                'pct_volume': volume / total_volume if total_volume > 0 else 0,
                'confiance_moyenne': (
                    sum(c.confiance for c in couples_univers) / nb_couples
                    if nb_couples > 0 else 0
                ),
            }

        # Alertes : faible confiance
        faible_confiance = [c for c in classifications if c.confiance < 0.5]

        return ClassificationSummary(
            total_couples=total_couples,
            total_ecritures=total_ecritures,
            total_volume=total_volume,
            par_univers=par_univers,
            faible_confiance=faible_confiance,
        )


@dataclass
class ClassificationResults:
    """Résultats complets de classification."""
    classifications: List[ClassificationResult]
    summary: ClassificationSummary

    def get_by_univers(self, univers: UniversSemantique) -> List[ClassificationResult]:
        """Retourne les couples d'un univers."""
        return [c for c in self.classifications if c.univers == univers]

    def get_composites(self) -> List[ClassificationResult]:
        """Retourne les couples COMPOSITE (cibles de l'analyse approfondie)."""
        return self.get_by_univers(UniversSemantique.COMPOSITE)

    def get_non_classes(self) -> List[ClassificationResult]:
        """Retourne les couples non classés (backlog à qualifier)."""
        return self.get_by_univers(UniversSemantique.NON_CLASSE)

    def get_faible_confiance(self, threshold: float = 0.5) -> List[ClassificationResult]:
        """Retourne les couples avec faible confiance."""
        return [c for c in self.classifications if c.confiance < threshold]

    def get_by_famille(self, famille: str) -> List[ClassificationResult]:
        """Retourne les couples d'une famille de comptes."""
        return [c for c in self.classifications if c.famille == famille]

    def print_summary(self):
        """Affiche un résumé de la classification."""
        print(f"\n{'='*60}")
        print(f"CLASSIFICATION SÉMANTIQUE")
        print(f"{'='*60}")
        print(f"Total : {self.summary.total_couples} couples, "
              f"{self.summary.total_ecritures} écritures, "
              f"{self.summary.total_volume:,.0f} €")
        print()

        print("RÉPARTITION PAR UNIVERS")
        print("-" * 60)
        for univers, data in sorted(self.summary.par_univers.items(),
                                     key=lambda x: -x[1]['pct_volume']):
            if data['nb_couples'] == 0:
                continue
            print(f"  {univers:12} : {data['nb_couples']:4} couples "
                  f"({data['pct_couples']:5.1%}), "
                  f"{data['pct_volume']:5.1%} du volume, "
                  f"confiance moy. {data['confiance_moyenne']:.0%}")

        if self.summary.faible_confiance:
            print()
            print(f"⚠️  {len(self.summary.faible_confiance)} couples à faible confiance (<50%)")
