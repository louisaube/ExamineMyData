"""
ABTDetector - Détection des mécanismes d'abonnement
===================================================

STORY-204: Détecte les comptes 488 qui soldent à zéro (mécanisme ABT).

Le mécanisme ABT (Abonnement) est une pratique comptable courante :
- Chaque mois, provision 1/12 de la charge annuelle prévue
- En décembre, contrepassation + charge réelle
- Le compte 488 solde à zéro sur l'exercice

Ces comptes sont EXCLUS des alertes car c'est du bruit budgétaire maîtrisé.
"""

import re
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class ABTAccount:
    """Information sur un compte d'abonnement."""
    compte: str
    libelle_compte: str       # Extrait des écritures
    objet: str                # CFE, prud'hommes, formation...
    mouvement_total: float    # Somme |debit| + |credit|
    solde_annuel: float       # Doit être ~0
    provision_mensuelle: float  # Montant mensuel moyen
    ecritures_count: int
    months_with_entries: List[int]
    is_valid_abt: bool        # solde < seuil % du mouvement

    @property
    def solde_ratio(self) -> float:
        """Ratio solde / mouvement total."""
        if self.mouvement_total == 0:
            return 0.0
        return abs(self.solde_annuel) / self.mouvement_total


# Mots-clés pour identifier l'objet des ABT
ABT_KEYWORDS = {
    "CFE": ["CFE", "cotisation foncière", "cotis. foncière"],
    "CVAE": ["CVAE", "valeur ajoutée", "VA "],
    "TAXE_FONCIERE": ["taxe foncière", "taxe fonc", "foncier"],
    "PRUDHOMMES": ["prud'homme", "prudhomme", "prud homme", "CPH", "litige salarié"],
    "FORMATION": ["formation", "OPCO", "plan form"],
    "CAC": ["CAC", "commissaire aux comptes", "commiss", "audit légal"],
    "AGEFIPH": ["AGEFIPH", "handicap", "OETH"],
    "TAXE_APPRENTISSAGE": ["apprentissage", "taxe apprenti", "TA "],
    "ORGANIC": ["organic", "gestion agréé"],
    "C3S": ["C3S", "contribution sociale"],
    "PARTICIPATION": ["participation", "intéressement"],
    "CONGES_PAYES": ["congés payés", "CP ", "conges payes"],
    "BONUS": ["bonus", "prime", "gratification"],
    "ASSURANCE": ["assurance", "multirisque", "RC pro"],
    "LOYER": ["loyer", "bail", "location"],
}


class ABTDetector:
    """
    Détecte les comptes d'abonnement (488) qui soldent à zéro.

    Usage:
        detector = ABTDetector()
        abts = detector.detect(df)

        for abt in abts:
            if abt.is_valid_abt:
                print(f"{abt.compte}: {abt.objet} - {abt.provision_mensuelle}€/mois")
    """

    def __init__(self, solde_threshold: float = 0.01):
        """
        Args:
            solde_threshold: Seuil de tolérance pour le solde (défaut 1%)
                            Un compte est ABT si |solde| < threshold * mouvement
        """
        self.solde_threshold = solde_threshold

    def detect(self, df: pd.DataFrame) -> List[ABTAccount]:
        """
        Détecte tous les comptes ABT dans le GL.

        Args:
            df: DataFrame GL normalisé

        Returns:
            Liste des comptes ABT détectés
        """
        # Filtrer les comptes 488
        abt_comptes = [c for c in df["compte"].unique() if str(c).startswith("488")]

        if not abt_comptes:
            return []

        results = []
        for compte in abt_comptes:
            abt_info = self._analyze_account(df, compte)
            results.append(abt_info)

        # Trier par mouvement total décroissant
        results.sort(key=lambda x: x.mouvement_total, reverse=True)

        return results

    def _analyze_account(self, df: pd.DataFrame, compte: str) -> ABTAccount:
        """Analyse un compte 488 individuel."""
        compte_df = df[df["compte"] == compte]

        # Calculer les métriques
        total_debit = compte_df["debit"].sum()
        total_credit = compte_df["credit"].sum()
        mouvement_total = total_debit + total_credit
        solde_annuel = total_debit - total_credit

        # Extraire le libellé le plus fréquent
        libelles = compte_df["libelle"].dropna().tolist()
        libelle_compte = self._get_most_common_libelle(libelles)

        # Identifier l'objet
        objet = self._extract_object(libelles)

        # Mois avec écritures
        months = sorted(compte_df["mois"].unique().tolist())

        # Calculer la provision mensuelle moyenne
        # (hors décembre qui contient la contrepassation)
        jan_nov_df = compte_df[compte_df["mois"] != 12]
        if len(jan_nov_df) > 0:
            provision_mensuelle = jan_nov_df["debit"].sum() / max(1, jan_nov_df["mois"].nunique())
        else:
            provision_mensuelle = 0

        # Déterminer si c'est un ABT valide
        is_valid = self._is_valid_abt(mouvement_total, solde_annuel)

        return ABTAccount(
            compte=compte,
            libelle_compte=libelle_compte,
            objet=objet,
            mouvement_total=mouvement_total,
            solde_annuel=solde_annuel,
            provision_mensuelle=provision_mensuelle,
            ecritures_count=len(compte_df),
            months_with_entries=months,
            is_valid_abt=is_valid,
        )

    def _is_valid_abt(self, mouvement: float, solde: float) -> bool:
        """Vérifie si le compte est un ABT valide (solde proche de zéro)."""
        if mouvement == 0:
            return False
        ratio = abs(solde) / mouvement
        return ratio < self.solde_threshold

    def _get_most_common_libelle(self, libelles: List[str]) -> str:
        """Retourne le libellé le plus fréquent (nettoyé)."""
        if not libelles:
            return ""

        # Compter les occurrences
        counts = {}
        for lib in libelles:
            lib_clean = str(lib).strip()[:50]  # Tronquer à 50 chars
            counts[lib_clean] = counts.get(lib_clean, 0) + 1

        # Retourner le plus fréquent
        return max(counts, key=counts.get)

    def _extract_object(self, libelles: List[str]) -> str:
        """
        Extrait l'objet de l'ABT depuis les libellés.

        Utilise une recherche par mots-clés.
        """
        all_text = " ".join(str(lib) for lib in libelles).upper()

        for objet, keywords in ABT_KEYWORDS.items():
            for kw in keywords:
                if kw.upper() in all_text:
                    return objet

        # Si pas de match, essayer d'extraire un mot significatif
        # Chercher des patterns comme "ABT xxx" ou "Prov xxx"
        match = re.search(r"(?:ABT|PROV|PROVISION)[.\s]+(\w+)", all_text, re.IGNORECASE)
        if match:
            return match.group(1).upper()

        return "NON_IDENTIFIE"

    def get_valid_abts(self, df: pd.DataFrame) -> List[ABTAccount]:
        """Retourne uniquement les ABT valides (qui soldent)."""
        all_abts = self.detect(df)
        return [abt for abt in all_abts if abt.is_valid_abt]

    def get_abt_accounts_list(self, df: pd.DataFrame) -> List[str]:
        """Retourne la liste des numéros de compte ABT valides."""
        valid_abts = self.get_valid_abts(df)
        return [abt.compte for abt in valid_abts]

    def is_abt_account(self, df: pd.DataFrame, compte: str) -> bool:
        """Vérifie si un compte est un ABT valide."""
        if not str(compte).startswith("488"):
            return False
        abt_info = self._analyze_account(df, compte)
        return abt_info.is_valid_abt

    def get_summary(self, df: pd.DataFrame) -> Dict:
        """Retourne un résumé des ABT détectés."""
        abts = self.detect(df)
        valid = [a for a in abts if a.is_valid_abt]

        objects = {}
        for abt in valid:
            if abt.objet not in objects:
                objects[abt.objet] = 0
            objects[abt.objet] += 1

        return {
            "total_488_accounts": len(abts),
            "valid_abt_accounts": len(valid),
            "total_monthly_provisions": sum(a.provision_mensuelle for a in valid),
            "objects_detected": objects,
            "accounts": [
                {
                    "compte": a.compte,
                    "objet": a.objet,
                    "provision_mensuelle": round(a.provision_mensuelle, 2),
                    "solde": round(a.solde_annuel, 2),
                    "valid": a.is_valid_abt,
                }
                for a in abts
            ],
        }
