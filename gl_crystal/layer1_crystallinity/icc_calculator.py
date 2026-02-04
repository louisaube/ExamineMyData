"""
GL Crystal - Calculateur ICC

Calcule l'Indice de Cristallinité Comptable pour chaque couple (compte, analytique).

Le grain d'analyse est le couple, pas la ligne individuelle.
C'est le changement de paradigme fondamental de GL Crystal.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict
import numpy as np

from ..normalizer.schema import GLSchema, EnrichedEntry, NatureCompte
from .metrics import (
    compute_cv_decompose,
    compute_entropy_libelles,
    compute_regularite_temporelle,
    compute_diversite_journaux,
    compute_concentration_contreparties,
    compute_icc_composite,
)


@dataclass
class ICCScore:
    """
    Score ICC pour un couple (compte, analytique).

    Contient le score composite et les scores par axe.
    """
    # Identifiants
    compte: str
    analytique: Optional[str]

    # Score composite
    icc: float  # 0 = amorphe, 1 = cristallin

    # Scores par axe
    score_montants: float
    score_libelles: float
    score_temporalite: float
    score_journaux: float
    score_contreparties: float

    # Métriques détaillées
    cv_total: float
    entropy_normalized: float
    n_ecritures: int
    n_mois: int
    n_journaux: int
    n_contreparties: int

    # Classification
    classification: str = ""  # "cristallin", "vitreux", "amorphe"

    # Z-score par rapport aux pairs
    zscore: Optional[float] = None

    def __post_init__(self):
        """Détermine la classification après création."""
        if self.icc >= 0.7:
            self.classification = "cristallin"
        elif self.icc >= 0.4:
            self.classification = "vitreux"
        else:
            self.classification = "amorphe"


@dataclass
class CoupleAnalysis:
    """
    Analyse complète d'un couple (compte, analytique).

    Contient les données brutes et les métriques calculées.
    """
    compte: str
    analytique: Optional[str]
    famille: str  # Racine à 3 chiffres

    # Données agrégées
    ecritures: List[EnrichedEntry] = field(default_factory=list)
    montant_total: float = 0.0
    n_ecritures: int = 0

    # Métriques par axe
    cv_metrics: Dict = field(default_factory=dict)
    entropy_metrics: Dict = field(default_factory=dict)
    regularite_metrics: Dict = field(default_factory=dict)
    journaux_metrics: Dict = field(default_factory=dict)
    contreparties_metrics: Dict = field(default_factory=dict)

    # Score ICC
    icc_score: Optional[ICCScore] = None


class ICCCalculator:
    """
    Calculateur de l'Indice de Cristallinité Comptable.

    Usage:
        calculator = ICCCalculator()
        results = calculator.compute(schema)

        # Accès aux scores
        for score in results.scores:
            print(f"{score.compte}/{score.analytique}: ICC={score.icc:.2f}")

        # Heatmap data
        heatmap = calculator.get_heatmap_data(results)
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        Initialise le calculateur.

        Args:
            weights: Poids des axes ICC (optionnel)
        """
        self.weights = weights or {
            'montants': 0.20,
            'libelles': 0.20,
            'temporalite': 0.20,
            'journaux': 0.20,
            'contreparties': 0.20,
        }

    def compute(self, schema: GLSchema,
                filter_nature: Optional[Set[NatureCompte]] = None) -> 'ICCResults':
        """
        Calcule l'ICC pour tous les couples du GL.

        Args:
            schema: GLSchema enrichi
            filter_nature: Filtrer par nature de compte (ex: {CHARGE, PRODUIT})

        Returns:
            ICCResults contenant les scores et analyses
        """
        # Groupe les écritures par couple
        couples = self._group_by_couple(schema.entries, filter_nature)

        # Analyse chaque couple
        analyses = []
        for (compte, analytique), ecritures in couples.items():
            analysis = self._analyze_couple(compte, analytique, ecritures)
            analyses.append(analysis)

        # Calcule les z-scores par famille
        self._compute_zscores(analyses)

        # Construit les résultats
        return ICCResults(
            analyses=analyses,
            n_couples=len(analyses),
            n_ecritures=len(schema.entries),
            familles=self._get_familles(analyses),
            analytiques=self._get_analytiques(analyses),
        )

    def _group_by_couple(
        self,
        entries: List[EnrichedEntry],
        filter_nature: Optional[Set[NatureCompte]] = None
    ) -> Dict[Tuple[str, Optional[str]], List[EnrichedEntry]]:
        """Groupe les écritures par couple (compte, analytique)."""
        couples = defaultdict(list)

        for entry in entries:
            # Filtre par nature si spécifié
            if filter_nature and entry.nature not in filter_nature:
                continue

            key = (entry.compte_general, entry.analytique)
            couples[key].append(entry)

        return dict(couples)

    def _analyze_couple(
        self,
        compte: str,
        analytique: Optional[str],
        ecritures: List[EnrichedEntry]
    ) -> CoupleAnalysis:
        """Analyse un couple et calcule son ICC."""
        # Extrait les données pour les métriques
        montants = [e.montant_signe for e in ecritures]
        libelles = [e.libelle_ecriture for e in ecritures]
        mois = [e.mois_comptable for e in ecritures if e.mois_comptable]
        journaux = [e.journal_code for e in ecritures]

        # Contreparties (premier compte de la liste)
        contreparties = []
        for e in ecritures:
            if e.contrepartie_comptes:
                contreparties.append(e.contrepartie_comptes[0])

        # Fournisseurs (compte auxiliaire si disponible)
        fournisseurs = [e.compte_auxiliaire for e in ecritures
                        if e.compte_auxiliaire]

        # Calcul des métriques par axe
        cv_metrics = compute_cv_decompose(montants, fournisseurs, mois)
        entropy_metrics = compute_entropy_libelles(libelles)
        regularite_metrics = compute_regularite_temporelle(montants, mois)
        journaux_metrics = compute_diversite_journaux(journaux)
        contreparties_metrics = compute_concentration_contreparties(contreparties)

        # Calcul de l'ICC composite
        icc = compute_icc_composite(
            cv_metrics, entropy_metrics, regularite_metrics,
            journaux_metrics, contreparties_metrics,
            self.weights
        )

        # Scores par axe (pour le détail)
        cv = cv_metrics.get('cv_total', 0)
        score_montants = max(0, 1 - min(cv, 2) / 2)
        score_libelles = max(0, 1 - entropy_metrics.get('entropy_normalized', 0))
        score_temporalite = regularite_metrics.get('score_regularite', 0.5)
        score_journaux = journaux_metrics.get('score_purete', 1.0)
        score_contreparties = contreparties_metrics.get('herfindahl', 1.0)

        # Crée le score ICC
        icc_score = ICCScore(
            compte=compte,
            analytique=analytique,
            icc=icc,
            score_montants=score_montants,
            score_libelles=score_libelles,
            score_temporalite=score_temporalite,
            score_journaux=score_journaux,
            score_contreparties=score_contreparties,
            cv_total=cv_metrics.get('cv_total', 0),
            entropy_normalized=entropy_metrics.get('entropy_normalized', 0),
            n_ecritures=len(ecritures),
            n_mois=len(set(mois)),
            n_journaux=journaux_metrics.get('n_journaux', 0),
            n_contreparties=contreparties_metrics.get('n_contreparties', 0),
        )

        # Famille (racine 3 chiffres)
        famille = compte[:3] if len(compte) >= 3 else compte

        return CoupleAnalysis(
            compte=compte,
            analytique=analytique,
            famille=famille,
            ecritures=ecritures,
            montant_total=sum(abs(m) for m in montants),
            n_ecritures=len(ecritures),
            cv_metrics=cv_metrics,
            entropy_metrics=entropy_metrics,
            regularite_metrics=regularite_metrics,
            journaux_metrics=journaux_metrics,
            contreparties_metrics=contreparties_metrics,
            icc_score=icc_score,
        )

    def _compute_zscores(self, analyses: List[CoupleAnalysis]):
        """
        Calcule les z-scores par famille.

        Le z-score mesure la déviation d'un couple par rapport aux autres
        couples de la même famille de comptes.
        """
        # Groupe par famille
        by_famille: Dict[str, List[CoupleAnalysis]] = defaultdict(list)
        for analysis in analyses:
            by_famille[analysis.famille].append(analysis)

        # Calcule le z-score pour chaque famille
        for famille, famille_analyses in by_famille.items():
            if len(famille_analyses) < 2:
                # Pas assez de pairs pour calculer un z-score
                for a in famille_analyses:
                    if a.icc_score:
                        a.icc_score.zscore = 0.0
                continue

            # Distribution des ICC dans la famille
            icc_values = [a.icc_score.icc for a in famille_analyses if a.icc_score]
            if not icc_values or len(icc_values) < 2:
                continue

            mean_icc = np.mean(icc_values)
            std_icc = np.std(icc_values)

            if std_icc == 0:
                for a in famille_analyses:
                    if a.icc_score:
                        a.icc_score.zscore = 0.0
            else:
                for a in famille_analyses:
                    if a.icc_score:
                        a.icc_score.zscore = float(
                            (a.icc_score.icc - mean_icc) / std_icc
                        )

    def _get_familles(self, analyses: List[CoupleAnalysis]) -> Set[str]:
        """Retourne l'ensemble des familles de comptes."""
        return {a.famille for a in analyses}

    def _get_analytiques(self, analyses: List[CoupleAnalysis]) -> Set[str]:
        """Retourne l'ensemble des codes analytiques."""
        return {a.analytique for a in analyses if a.analytique}


@dataclass
class ICCResults:
    """
    Résultats du calcul ICC.

    Contient:
    - Les analyses détaillées par couple
    - Les statistiques globales
    - Les méthodes d'accès et de filtrage
    """
    analyses: List[CoupleAnalysis]
    n_couples: int
    n_ecritures: int
    familles: Set[str]
    analytiques: Set[str]

    @property
    def scores(self) -> List[ICCScore]:
        """Retourne la liste des scores ICC."""
        return [a.icc_score for a in self.analyses if a.icc_score]

    def get_amorphes(self, threshold: float = 0.4) -> List[ICCScore]:
        """Retourne les couples amorphes (ICC < threshold)."""
        return [s for s in self.scores if s.icc < threshold]

    def get_cristallins(self, threshold: float = 0.7) -> List[ICCScore]:
        """Retourne les couples cristallins (ICC >= threshold)."""
        return [s for s in self.scores if s.icc >= threshold]

    def get_alertes_zscore(self, threshold: float = -2.0) -> List[ICCScore]:
        """
        Retourne les couples avec z-score significativement bas.

        Ces couples sont anormalement amorphes par rapport à leurs pairs.
        """
        return [s for s in self.scores
                if s.zscore is not None and s.zscore < threshold]

    def get_by_famille(self, famille: str) -> List[ICCScore]:
        """Retourne les scores d'une famille de comptes."""
        return [a.icc_score for a in self.analyses
                if a.famille == famille and a.icc_score]

    def get_by_analytique(self, analytique: str) -> List[ICCScore]:
        """Retourne les scores d'un code analytique."""
        return [a.icc_score for a in self.analyses
                if a.analytique == analytique and a.icc_score]

    def get_heatmap_data(self) -> Dict[str, Dict[str, float]]:
        """
        Retourne les données pour une heatmap.

        Structure: {analytique: {famille: icc}}
        """
        heatmap = defaultdict(dict)
        for analysis in self.analyses:
            if analysis.icc_score and analysis.analytique:
                ana = analysis.analytique
                fam = analysis.famille
                heatmap[ana][fam] = analysis.icc_score.icc
        return dict(heatmap)

    def get_stats(self) -> Dict:
        """Retourne les statistiques globales."""
        if not self.scores:
            return {
                'n_couples': 0,
                'icc_mean': 0,
                'icc_std': 0,
                'n_cristallins': 0,
                'n_amorphes': 0,
            }

        icc_values = [s.icc for s in self.scores]
        return {
            'n_couples': len(self.scores),
            'icc_mean': float(np.mean(icc_values)),
            'icc_std': float(np.std(icc_values)),
            'icc_median': float(np.median(icc_values)),
            'n_cristallins': len(self.get_cristallins()),
            'n_amorphes': len(self.get_amorphes()),
            'n_familles': len(self.familles),
            'n_analytiques': len(self.analytiques),
        }

    def top_amorphes(self, n: int = 20) -> List[ICCScore]:
        """Retourne les N couples les plus amorphes."""
        return sorted(self.scores, key=lambda s: s.icc)[:n]

    def bottom_amorphes(self, n: int = 20) -> List[ICCScore]:
        """Retourne les N couples les plus cristallins."""
        return sorted(self.scores, key=lambda s: s.icc, reverse=True)[:n]
