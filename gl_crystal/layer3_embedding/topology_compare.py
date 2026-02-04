"""
GL Crystal - Comparaison Embedding vs PCG

La distance entre comptes dans l'embedding émergent est une distance FONCTIONNELLE,
pas taxonomique. Le 641 et le 431 seront proches (couplage mécanique paie/charges
sociales). Le 641 et le 642 seront proches dans le PCG mais potentiellement
distants dans l'embedding si leur profil de contreparties diffère.

La comparaison entre l'embedding émergent et la hiérarchie PCG révèle:
- Les couplages attendus (641↔431 : mécanique, normal)
- Les couplages inattendus (606↔758 : transfert de charges suspect)
- Les découplages surprenants (deux comptes frères dans le PCG qui ont des
  comportements radicalement différents)

Le PCG ne doit pas être l'input de l'embedding. Il doit être le benchmark.
On laisse l'embedding émerger des données, puis on mesure la divergence
avec la structure attendue du PCG. Cette divergence EST l'information intéressante.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
import numpy as np
from collections import defaultdict

from .connectivity import ConnectivityMatrix, build_connectivity_matrix
from ..normalizer.schema import GLSchema


@dataclass
class TopologyDivergence:
    """
    Divergence entre topologie émergente et structure PCG.

    Identifie les couplages/découplages qui divergent des attentes.
    """
    # Comptes impliqués
    compte1: str
    compte2: str

    # Distances
    distance_emergente: float      # Distance dans l'embedding
    distance_pcg: float            # Distance dans l'arbre PCG

    # Type de divergence
    type_divergence: str  # "couplage_inattendu", "decouplage_surprenant", "conforme"

    # Interprétation
    description: str = ""
    is_signal: bool = False  # Vaut-il la peine d'être investigué?


@dataclass
class AccountProximity:
    """Proximité entre deux comptes dans l'espace émergent."""
    compte1: str
    compte2: str
    distance: float
    cooccurrence_count: int  # Nombre de fois qu'ils apparaissent ensemble
    flux_volume: float       # Volume des flux entre eux


# Distance PCG simplifiée (basée sur le préfixe commun)
def compute_pcg_distance(compte1: str, compte2: str) -> float:
    """
    Calcule la distance taxonomique dans l'arbre PCG.

    Basée sur la longueur du préfixe commun.
    - Même classe (ex: 641 et 645) = proche
    - Classes différentes (ex: 641 et 431) = distant
    """
    # Préfixe commun
    min_len = min(len(compte1), len(compte2))
    prefix_len = 0
    for i in range(min_len):
        if compte1[i] == compte2[i]:
            prefix_len += 1
        else:
            break

    # Normalise : 0 = identique, 1 = rien en commun
    max_len = max(len(compte1), len(compte2))
    if max_len == 0:
        return 1.0

    # Plus le préfixe est long, plus les comptes sont proches
    return 1.0 - (prefix_len / max_len)


class TopologyComparator:
    """
    Compare la topologie émergente avec la hiérarchie PCG.

    Identifie les divergences significatives entre la structure
    fonctionnelle (ce que font les comptes) et la structure
    taxonomique (comment ils sont classés).
    """

    def __init__(
        self,
        distance_threshold: float = 0.3,
        min_cooccurrence: int = 5
    ):
        """
        Args:
            distance_threshold: Seuil pour considérer deux comptes comme proches
            min_cooccurrence: Minimum de co-occurrences pour être significatif
        """
        self.distance_threshold = distance_threshold
        self.min_cooccurrence = min_cooccurrence

    def analyze(
        self,
        schema: GLSchema,
        focus_classes: Optional[Set[str]] = None
    ) -> 'TopologyComparisonResult':
        """
        Analyse les divergences topologie émergente vs PCG.

        Args:
            schema: GLSchema enrichi
            focus_classes: Classes de comptes à analyser (ex: {'6', '7'})

        Returns:
            TopologyComparisonResult
        """
        # Construit la matrice de connectivité globale
        matrix = build_connectivity_matrix(schema)

        # Calcule les proximités émergentes
        proximities = self._compute_emergent_proximities(matrix, focus_classes)

        # Compare avec le PCG
        divergences = self._find_divergences(proximities)

        # Statistiques
        stats = self._compute_stats(proximities, divergences)

        return TopologyComparisonResult(
            proximities=proximities,
            divergences=divergences,
            stats=stats,
        )

    def _compute_emergent_proximities(
        self,
        matrix: ConnectivityMatrix,
        focus_classes: Optional[Set[str]] = None
    ) -> List[AccountProximity]:
        """Calcule les proximités émergentes entre comptes."""
        proximities = []

        comptes = list(matrix.compte_to_idx.keys())

        # Filtre par classe si spécifié
        if focus_classes:
            comptes = [c for c in comptes if c and c[0] in focus_classes]

        # Pour chaque paire de comptes
        for i, c1 in enumerate(comptes):
            for c2 in comptes[i+1:]:
                # Volume des flux entre eux (dans les deux sens)
                flux_12 = matrix.get_flux(c1, c2)
                flux_21 = matrix.get_flux(c2, c1)
                total_flux = flux_12 + flux_21

                if total_flux == 0:
                    continue

                # Co-occurrence (présence dans les mêmes pièces)
                # Approximation via le flux
                cooccurrence = 1 if total_flux > 0 else 0

                # Distance émergente (inverse du flux normalisé)
                max_flux = max(
                    matrix.get_outgoing_total(c1),
                    matrix.get_outgoing_total(c2),
                    matrix.get_incoming_total(c1),
                    matrix.get_incoming_total(c2),
                    1.0
                )
                distance = 1.0 - (total_flux / max_flux)

                proximities.append(AccountProximity(
                    compte1=c1,
                    compte2=c2,
                    distance=distance,
                    cooccurrence_count=cooccurrence,
                    flux_volume=total_flux,
                ))

        return proximities

    def _find_divergences(
        self,
        proximities: List[AccountProximity]
    ) -> List[TopologyDivergence]:
        """Identifie les divergences entre topologie émergente et PCG."""
        divergences = []

        for prox in proximities:
            if prox.flux_volume == 0:
                continue

            c1, c2 = prox.compte1, prox.compte2
            dist_emergente = prox.distance
            dist_pcg = compute_pcg_distance(c1, c2)

            # Couplage inattendu: proches fonctionnellement, distants dans PCG
            # Ex: 641 et 431 (classes différentes mais couplés par la paie)
            if dist_emergente < self.distance_threshold and dist_pcg > 0.5:
                type_div = "couplage_inattendu"
                is_signal = True
                description = (
                    f"Comptes {c1} et {c2} sont fonctionnellement couplés "
                    f"(flux {prox.flux_volume:,.0f}€) mais distants dans le PCG"
                )

            # Découplage surprenant: proches dans PCG, distants fonctionnellement
            # Ex: deux comptes de la même famille qui ne communiquent jamais
            elif dist_emergente > 0.7 and dist_pcg < 0.3:
                type_div = "decouplage_surprenant"
                is_signal = True
                description = (
                    f"Comptes {c1} et {c2} sont proches dans le PCG "
                    f"mais ont des comportements très différents"
                )

            else:
                type_div = "conforme"
                is_signal = False
                description = ""

            divergences.append(TopologyDivergence(
                compte1=c1,
                compte2=c2,
                distance_emergente=dist_emergente,
                distance_pcg=dist_pcg,
                type_divergence=type_div,
                description=description,
                is_signal=is_signal,
            ))

        return divergences

    def _compute_stats(
        self,
        proximities: List[AccountProximity],
        divergences: List[TopologyDivergence]
    ) -> Dict:
        """Calcule les statistiques de comparaison."""
        n_couplages_inattendus = sum(
            1 for d in divergences if d.type_divergence == "couplage_inattendu"
        )
        n_decouplages = sum(
            1 for d in divergences if d.type_divergence == "decouplage_surprenant"
        )
        n_conformes = sum(
            1 for d in divergences if d.type_divergence == "conforme"
        )

        # Corrélation entre distances
        if divergences:
            dist_emergentes = [d.distance_emergente for d in divergences]
            dist_pcg = [d.distance_pcg for d in divergences]
            correlation = float(np.corrcoef(dist_emergentes, dist_pcg)[0, 1])
            if np.isnan(correlation):
                correlation = 0.0
        else:
            correlation = 0.0

        return {
            'n_paires_analysees': len(proximities),
            'n_couplages_inattendus': n_couplages_inattendus,
            'n_decouplages_surprenants': n_decouplages,
            'n_conformes': n_conformes,
            'correlation_distances': correlation,
            'taux_divergence': (n_couplages_inattendus + n_decouplages) / len(divergences)
                               if divergences else 0.0,
        }


@dataclass
class TopologyComparisonResult:
    """Résultat de la comparaison topologique."""
    proximities: List[AccountProximity]
    divergences: List[TopologyDivergence]
    stats: Dict

    def get_signals(self) -> List[TopologyDivergence]:
        """Retourne les divergences significatives à investiguer."""
        return [d for d in self.divergences if d.is_signal]

    def get_couplages_inattendus(self) -> List[TopologyDivergence]:
        """Retourne les couplages fonctionnels inattendus."""
        return [d for d in self.divergences
                if d.type_divergence == "couplage_inattendu"]

    def get_decouplages_surprenants(self) -> List[TopologyDivergence]:
        """Retourne les découplages surprenants."""
        return [d for d in self.divergences
                if d.type_divergence == "decouplage_surprenant"]

    def get_top_proximities(self, n: int = 20) -> List[AccountProximity]:
        """Retourne les N paires les plus proches fonctionnellement."""
        return sorted(self.proximities, key=lambda x: x.distance)[:n]


# Couplages attendus (connus du métier)
EXPECTED_COUPLINGS = {
    # Paie
    ('641', '421'): "Salaires → Personnel à payer",
    ('641', '431'): "Salaires → URSSAF",
    ('641', '437'): "Salaires → Autres organismes sociaux",
    ('645', '431'): "Charges sociales → URSSAF",
    ('645', '437'): "Charges sociales → Autres organismes",

    # Achats
    ('601', '401'): "Achats → Fournisseurs",
    ('606', '401'): "Fournitures → Fournisseurs",
    ('607', '401'): "Marchandises → Fournisseurs",

    # Ventes
    ('706', '411'): "Prestations → Clients",
    ('707', '411'): "Ventes → Clients",

    # Provisions
    ('681', '28'): "Dotations → Amortissements",
    ('681', '15'): "Dotations → Provisions",
    ('781', '28'): "Reprises → Amortissements",
    ('781', '15'): "Reprises → Provisions",

    # ABT
    ('6', '488'): "Charges → Charges à payer (ABT)",

    # Financier
    ('661', '512'): "Intérêts → Banque",
    ('627', '512'): "Frais bancaires → Banque",
}


def is_expected_coupling(compte1: str, compte2: str) -> Tuple[bool, str]:
    """
    Vérifie si un couplage est attendu.

    Returns:
        (est_attendu, description)
    """
    # Vérifie les deux sens
    for (c1, c2), desc in EXPECTED_COUPLINGS.items():
        if compte1.startswith(c1) and compte2.startswith(c2):
            return True, desc
        if compte1.startswith(c2) and compte2.startswith(c1):
            return True, desc

    return False, ""
