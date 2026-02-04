"""
GL Crystal - Détection de Circuits ABT/CCA/PCA

Les mécanismes ABT (Abonnement), CCA (Charges Constatées d'Avance),
PCA (Produits Constatés d'Avance) créent des circuits fermés dans le graphe.

Circuit ABT pour une charge:
    Mois 1-11 : 6xx → 488  (dotation mensuelle)
    Mois 12   : 488 → 6xx  (contrepassation) + 6xx → 401/512 (charge réelle)

Le 488 doit solder à zéro en fin d'exercice. S'il ne solde pas, le circuit
est incomplet. Si la charge réelle dévie significativement de la provision
cumulée, c'est une information de pilotage (sous/sur-provisionnement).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
from enum import Enum
import numpy as np

from ..normalizer.schema import GLSchema, EnrichedEntry


class CircuitType(Enum):
    """Type de circuit comptable."""
    ABT = "abt"            # Abonnement (488)
    CCA = "cca"            # Charges Constatées d'Avance (486)
    PCA = "pca"            # Produits Constatés d'Avance (487)
    FNP = "fnp"            # Factures Non Parvenues (408)
    PROVISION = "provision" # Provisions génériques (481, 15x)


# Comptes de bilan utilisés dans les circuits
CIRCUIT_BILAN_ACCOUNTS = {
    CircuitType.ABT: ['488'],           # Charges à payer
    CircuitType.CCA: ['486'],           # Charges constatées d'avance
    CircuitType.PCA: ['487'],           # Produits constatés d'avance
    CircuitType.FNP: ['408'],           # Fournisseurs - factures non parvenues
    CircuitType.PROVISION: ['481', '15'], # Provisions diverses
}


@dataclass
class Circuit:
    """
    Représente un circuit comptable (ABT, CCA, PCA, etc.).

    Un circuit lie un compte de résultat (P&L) à un compte de bilan
    par des écritures de dotation et de reprise.
    """
    type_circuit: CircuitType
    compte_resultat: str        # Compte P&L (ex: "606320")
    compte_bilan: str           # Compte bilan (ex: "488000")
    analytique: Optional[str]

    # Mouvements
    dotations: List[Dict] = field(default_factory=list)     # Vers bilan
    reprises: List[Dict] = field(default_factory=list)      # Depuis bilan
    charges_reelles: List[Dict] = field(default_factory=list)  # Vers 401/512

    # Totaux
    total_dotations: float = 0.0
    total_reprises: float = 0.0
    total_charges_reelles: float = 0.0

    # Solde et statut
    solde_bilan: float = 0.0     # Ce qui reste sur le compte de bilan
    est_boucle: bool = False     # Solde ≈ 0 ?
    ecart_provision: float = 0.0  # (réel - provision) / provision

    # Métriques de qualité
    n_mois_dotation: int = 0
    regularite_dotations: float = 0.0  # CV des dotations mensuelles

    def compute_status(self, tolerance: float = 0.01):
        """Calcule le statut du circuit après avoir collecté les mouvements."""
        self.total_dotations = sum(d.get('montant', 0) for d in self.dotations)
        self.total_reprises = sum(r.get('montant', 0) for r in self.reprises)
        self.total_charges_reelles = sum(c.get('montant', 0) for c in self.charges_reelles)

        # Solde du compte de bilan
        self.solde_bilan = self.total_dotations - self.total_reprises

        # Est-ce bouclé ? (solde proche de zéro par rapport aux mouvements)
        total_mvt = self.total_dotations + self.total_reprises
        if total_mvt > 0:
            self.est_boucle = abs(self.solde_bilan) / total_mvt < tolerance
        else:
            self.est_boucle = True

        # Écart provision vs réel
        if self.total_dotations > 0:
            self.ecart_provision = (
                (self.total_charges_reelles - self.total_dotations)
                / self.total_dotations
            )
        else:
            self.ecart_provision = 0.0

        # Nombre de mois avec dotation
        mois_dotation = {d.get('mois') for d in self.dotations if d.get('mois')}
        self.n_mois_dotation = len(mois_dotation)

        # Régularité des dotations (CV)
        if self.dotations and len(self.dotations) > 1:
            montants = [d.get('montant', 0) for d in self.dotations]
            mean = np.mean(montants)
            if mean > 0:
                self.regularite_dotations = float(np.std(montants) / mean)


@dataclass
class CircuitSummary:
    """Résumé d'un circuit pour le reporting."""
    type_circuit: str
    compte_resultat: str
    compte_bilan: str
    analytique: Optional[str]
    provision_cumulee: float
    charge_reelle: float
    solde_residuel: float
    est_boucle: bool
    ecart_pct: float
    severite: str  # "ok", "attention", "alerte"
    description: str


class CircuitDetector:
    """
    Détecteur de circuits comptables.

    Identifie les mécanismes ABT, CCA, PCA et vérifie leur bouclage.
    """

    def __init__(self, tolerance: float = 0.01):
        """
        Args:
            tolerance: Seuil de tolérance pour considérer un circuit bouclé
        """
        self.tolerance = tolerance

    def detect(self, schema: GLSchema) -> 'CircuitResults':
        """
        Détecte tous les circuits dans le GL.

        Args:
            schema: GLSchema enrichi

        Returns:
            CircuitResults
        """
        circuits = []

        # Identifie les comptes de bilan de circuit
        for circuit_type, prefixes in CIRCUIT_BILAN_ACCOUNTS.items():
            type_circuits = self._detect_type(schema, circuit_type, prefixes)
            circuits.extend(type_circuits)

        # Calcule les statuts
        for circuit in circuits:
            circuit.compute_status(self.tolerance)

        return CircuitResults(circuits=circuits)

    def _detect_type(
        self,
        schema: GLSchema,
        circuit_type: CircuitType,
        bilan_prefixes: List[str]
    ) -> List[Circuit]:
        """Détecte les circuits d'un type donné."""
        # Trouve toutes les écritures touchant ces comptes de bilan
        bilan_entries = []
        for entry in schema.entries:
            compte = entry.compte_general
            if any(compte.startswith(p) for p in bilan_prefixes):
                bilan_entries.append(entry)

        if not bilan_entries:
            return []

        # Groupe par (compte_bilan, analytique)
        groups: Dict[Tuple[str, Optional[str]], List[EnrichedEntry]] = defaultdict(list)
        for entry in bilan_entries:
            key = (entry.compte_general, entry.analytique)
            groups[key].append(entry)

        # Pour chaque groupe, identifie le circuit
        circuits = []
        for (compte_bilan, analytique), entries in groups.items():
            # Identifie le compte de résultat associé (contrepartie la plus fréquente)
            compte_resultat = self._find_compte_resultat(entries)
            if not compte_resultat:
                continue

            circuit = Circuit(
                type_circuit=circuit_type,
                compte_resultat=compte_resultat,
                compte_bilan=compte_bilan,
                analytique=analytique,
            )

            # Classe les mouvements
            for entry in entries:
                mvt = {
                    'mois': entry.mois_comptable,
                    'montant': abs(entry.montant_signe),
                    'sens': 'debit' if entry.debit > 0 else 'credit',
                    'libelle': entry.libelle_ecriture,
                    'contrepartie': entry.contrepartie_comptes[0] if entry.contrepartie_comptes else None,
                }

                # Dotation = crédit sur 488 (augmente la provision)
                # Reprise = débit sur 488 (consomme la provision)
                if entry.credit > 0:
                    circuit.dotations.append(mvt)
                else:
                    circuit.reprises.append(mvt)

            # Identifie les charges réelles (contreparties 401, 512)
            circuit.charges_reelles = self._find_charges_reelles(
                schema, compte_resultat, analytique
            )

            circuits.append(circuit)

        return circuits

    def _find_compte_resultat(self, entries: List[EnrichedEntry]) -> Optional[str]:
        """
        Trouve le compte de résultat associé au circuit.

        C'est la contrepartie P&L la plus fréquente.
        """
        contreparties = defaultdict(int)
        for entry in entries:
            for cp in entry.contrepartie_comptes:
                # Est-ce un compte P&L ?
                if cp and cp[0] in ('6', '7'):
                    contreparties[cp] += 1

        if not contreparties:
            return None

        return max(contreparties, key=contreparties.get)

    def _find_charges_reelles(
        self,
        schema: GLSchema,
        compte_resultat: str,
        analytique: Optional[str]
    ) -> List[Dict]:
        """
        Trouve les charges réelles (contrepartie 401/512) pour un compte.
        """
        charges = []

        for entry in schema.entries:
            if entry.compte_general != compte_resultat:
                continue
            if analytique and entry.analytique != analytique:
                continue

            # Contrepartie de type fournisseur/banque ?
            for cp in entry.contrepartie_comptes:
                if cp and (cp.startswith('401') or cp.startswith('512')):
                    charges.append({
                        'mois': entry.mois_comptable,
                        'montant': abs(entry.montant_signe),
                        'contrepartie': cp,
                        'libelle': entry.libelle_ecriture,
                    })
                    break

        return charges


@dataclass
class CircuitResults:
    """Résultats de la détection de circuits."""
    circuits: List[Circuit]

    def get_circuits_ouverts(self) -> List[Circuit]:
        """Retourne les circuits non bouclés."""
        return [c for c in self.circuits if not c.est_boucle]

    def get_circuits_par_type(self, circuit_type: CircuitType) -> List[Circuit]:
        """Retourne les circuits d'un type donné."""
        return [c for c in self.circuits if c.type_circuit == circuit_type]

    def get_circuits_par_analytique(self, analytique: str) -> List[Circuit]:
        """Retourne les circuits d'un site donné."""
        return [c for c in self.circuits if c.analytique == analytique]

    def get_ecarts_significatifs(self, threshold: float = 0.1) -> List[Circuit]:
        """
        Retourne les circuits avec écart provision/réel significatif.

        Un écart > threshold (ex: 10%) signale un sous/sur-provisionnement.
        """
        return [c for c in self.circuits if abs(c.ecart_provision) > threshold]

    def to_summaries(self) -> List[CircuitSummary]:
        """Convertit en résumés pour le reporting."""
        summaries = []
        for c in self.circuits:
            # Détermine la sévérité
            if not c.est_boucle and abs(c.solde_bilan) > 1000:
                severite = "alerte"
                description = f"Circuit ouvert, solde résiduel {c.solde_bilan:,.0f}€"
            elif abs(c.ecart_provision) > 0.2:
                severite = "attention"
                direction = "sous" if c.ecart_provision < 0 else "sur"
                description = f"{direction.capitalize()}-provisionnement {abs(c.ecart_provision)*100:.0f}%"
            elif not c.est_boucle:
                severite = "attention"
                description = f"Circuit non soldé ({c.solde_bilan:,.0f}€)"
            else:
                severite = "ok"
                description = "Circuit bouclé correctement"

            summaries.append(CircuitSummary(
                type_circuit=c.type_circuit.value,
                compte_resultat=c.compte_resultat,
                compte_bilan=c.compte_bilan,
                analytique=c.analytique,
                provision_cumulee=c.total_dotations,
                charge_reelle=c.total_charges_reelles,
                solde_residuel=c.solde_bilan,
                est_boucle=c.est_boucle,
                ecart_pct=c.ecart_provision,
                severite=severite,
                description=description,
            ))

        return summaries

    def get_stats(self) -> Dict:
        """Retourne les statistiques globales."""
        return {
            'n_circuits': len(self.circuits),
            'n_boucles': len([c for c in self.circuits if c.est_boucle]),
            'n_ouverts': len(self.get_circuits_ouverts()),
            'n_ecarts_significatifs': len(self.get_ecarts_significatifs()),
            'par_type': {
                t.value: len(self.get_circuits_par_type(t))
                for t in CircuitType
            },
        }
