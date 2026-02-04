"""
ProvisionMatcher - Couplage provisions et reprises
==================================================

STORY-205: Couple les dotations (68x) avec leurs reprises (78x).

Règle clé: Toujours lire les provisions avec leurs reprises pour calculer le NET.
Une dotation de 82K avec une reprise de 68K = 14K de risque net.
"""

import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class ProvisionCouple:
    """Couple dotation/reprise."""
    compte_dotation: str      # 681xxx, 687xxx
    compte_reprise: Optional[str]  # 781xxx, 787xxx (si existe)
    libelle: str
    montant_dotation: float
    montant_reprise: float
    montant_net: float        # dotation - reprise
    is_matched: bool          # Reprise trouvée ?
    type_provision: str       # amortissement, depreciation, risques
    detail_dotations: List[Dict]  # Détail par mois
    detail_reprises: List[Dict]   # Détail par mois


# Mapping entre comptes de dotation et de reprise
PROVISION_MAPPING = {
    # Amortissements
    "6811": "7811",  # Dotations/Reprises amortissements immobilisations incorporelles
    "6812": "7812",  # Dotations/Reprises amortissements immobilisations corporelles
    # Dépréciations
    "6816": "7816",  # Dotations/Reprises dépréciations immobilisations
    "6817": "7817",  # Dotations/Reprises dépréciations actifs circulants
    # Provisions pour risques et charges
    "6815": "7815",  # Dotations/Reprises provisions d'exploitation
    "686": "786",    # Dotations/Reprises provisions financières
    "687": "787",    # Dotations/Reprises provisions exceptionnelles
}

# Types de provisions
PROVISION_TYPES = {
    "6811": "amortissement",
    "6812": "amortissement",
    "6816": "depreciation",
    "6817": "depreciation",
    "6815": "risques_exploitation",
    "686": "risques_financiers",
    "687": "risques_exceptionnels",
}


class ProvisionMatcher:
    """
    Couple les dotations aux provisions avec leurs reprises.

    Usage:
        matcher = ProvisionMatcher()
        couples = matcher.match(df)

        for c in couples:
            print(f"{c.libelle}: dotation {c.montant_dotation}, reprise {c.montant_reprise}")
            print(f"  → Impact net: {c.montant_net}")
    """

    def match(self, df: pd.DataFrame) -> List[ProvisionCouple]:
        """
        Identifie et couple toutes les provisions/reprises.

        Args:
            df: DataFrame GL normalisé

        Returns:
            Liste des couples dotation/reprise
        """
        results = []

        # Identifier tous les comptes de dotation présents
        comptes = df["compte"].unique()

        # Pour chaque préfixe de dotation
        for prefix_dot, prefix_rep in PROVISION_MAPPING.items():
            # Trouver les comptes qui commencent par ce préfixe
            comptes_dot = [c for c in comptes if str(c).startswith(prefix_dot)]
            comptes_rep = [c for c in comptes if str(c).startswith(prefix_rep)]

            for compte_dot in comptes_dot:
                # Chercher le compte de reprise correspondant
                suffix = str(compte_dot)[len(prefix_dot):]
                compte_rep_attendu = prefix_rep + suffix

                compte_rep = compte_rep_attendu if compte_rep_attendu in comptes_rep else None

                # Analyser le couple
                couple = self._analyze_couple(df, compte_dot, compte_rep, prefix_dot)
                results.append(couple)

        # Trier par montant net décroissant
        results.sort(key=lambda x: abs(x.montant_net), reverse=True)

        return results

    def _analyze_couple(
        self,
        df: pd.DataFrame,
        compte_dot: str,
        compte_rep: Optional[str],
        prefix: str
    ) -> ProvisionCouple:
        """Analyse un couple dotation/reprise."""
        # Données dotation
        dot_df = df[df["compte"] == compte_dot]
        montant_dot = dot_df["debit"].sum() - dot_df["credit"].sum()
        montant_dot = abs(montant_dot)  # Dotations en positif

        # Extraire le libellé
        libelles = dot_df["libelle"].dropna().tolist()
        libelle = self._get_libelle(libelles, compte_dot)

        # Données reprise
        if compte_rep:
            rep_df = df[df["compte"] == compte_rep]
            montant_rep = rep_df["credit"].sum() - rep_df["debit"].sum()
            montant_rep = abs(montant_rep)  # Reprises en positif
        else:
            montant_rep = 0.0

        # Détail par mois
        detail_dot = self._get_monthly_detail(dot_df, "dotation")
        detail_rep = self._get_monthly_detail(
            df[df["compte"] == compte_rep], "reprise"
        ) if compte_rep else []

        # Type de provision
        type_prov = PROVISION_TYPES.get(prefix, "autre")

        return ProvisionCouple(
            compte_dotation=compte_dot,
            compte_reprise=compte_rep,
            libelle=libelle,
            montant_dotation=montant_dot,
            montant_reprise=montant_rep,
            montant_net=montant_dot - montant_rep,
            is_matched=compte_rep is not None and montant_rep > 0,
            type_provision=type_prov,
            detail_dotations=detail_dot,
            detail_reprises=detail_rep,
        )

    def _get_monthly_detail(self, df: pd.DataFrame, type_: str) -> List[Dict]:
        """Extrait le détail mensuel."""
        if df is None or len(df) == 0:
            return []

        monthly = df.groupby("mois").agg({
            "debit": "sum",
            "credit": "sum",
        }).reset_index()

        monthly["montant"] = monthly["debit"] - monthly["credit"]
        if type_ == "reprise":
            monthly["montant"] = -monthly["montant"]

        return [
            {"mois": int(row["mois"]), "montant": round(row["montant"], 2)}
            for _, row in monthly.iterrows()
            if row["montant"] != 0
        ]

    def _get_libelle(self, libelles: List[str], compte: str) -> str:
        """Extrait un libellé représentatif."""
        if not libelles:
            return f"Compte {compte}"

        # Prendre le libellé le plus long (souvent le plus descriptif)
        libelles_clean = [str(l).strip() for l in libelles if l]
        if not libelles_clean:
            return f"Compte {compte}"

        return max(libelles_clean, key=len)[:60]

    def get_net_provision(self, df: pd.DataFrame, compte_dot: str) -> float:
        """
        Calcule le montant net d'une provision (dotation - reprise).

        Args:
            df: DataFrame GL
            compte_dot: Compte de dotation (68x)

        Returns:
            Montant net (positif = charge nette)
        """
        couples = self.match(df)
        for couple in couples:
            if couple.compte_dotation == compte_dot:
                return couple.montant_net
        return 0.0

    def get_amortissements(self, df: pd.DataFrame) -> List[ProvisionCouple]:
        """Retourne uniquement les amortissements (6811, 6812)."""
        couples = self.match(df)
        return [c for c in couples if c.type_provision == "amortissement"]

    def get_provisions_risques(self, df: pd.DataFrame) -> List[ProvisionCouple]:
        """Retourne les provisions pour risques (6815, 686, 687)."""
        couples = self.match(df)
        return [c for c in couples if "risques" in c.type_provision]

    def get_depreciations(self, df: pd.DataFrame) -> List[ProvisionCouple]:
        """Retourne les dépréciations (6816, 6817)."""
        couples = self.match(df)
        return [c for c in couples if c.type_provision == "depreciation"]

    def get_orphan_reprises(self, df: pd.DataFrame) -> List[str]:
        """
        Identifie les reprises sans dotation correspondante.

        Ce sont des alertes potentielles.
        """
        couples = self.match(df)
        coupled_reprises = {c.compte_reprise for c in couples if c.compte_reprise}

        # Tous les comptes de reprise
        comptes = df["compte"].unique()
        all_reprises = [c for c in comptes if str(c).startswith("78")]

        # Reprises orphelines
        orphans = [c for c in all_reprises if c not in coupled_reprises]

        return orphans

    def get_summary(self, df: pd.DataFrame) -> Dict:
        """Résumé des provisions."""
        couples = self.match(df)

        summary = {
            "total_couples": len(couples),
            "total_dotations": sum(c.montant_dotation for c in couples),
            "total_reprises": sum(c.montant_reprise for c in couples),
            "total_net": sum(c.montant_net for c in couples),
            "by_type": {},
            "orphan_reprises": self.get_orphan_reprises(df),
        }

        # Grouper par type
        for couple in couples:
            t = couple.type_provision
            if t not in summary["by_type"]:
                summary["by_type"][t] = {
                    "count": 0,
                    "dotations": 0,
                    "reprises": 0,
                    "net": 0,
                }
            summary["by_type"][t]["count"] += 1
            summary["by_type"][t]["dotations"] += couple.montant_dotation
            summary["by_type"][t]["reprises"] += couple.montant_reprise
            summary["by_type"][t]["net"] += couple.montant_net

        return summary
