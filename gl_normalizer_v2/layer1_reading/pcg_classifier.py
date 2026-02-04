"""
PCGClassifier - Classification Plan Comptable Général
=====================================================

STORY-203: Classe chaque compte selon le PCG français.

Identifie la nature (charge, produit), le type (exploitation, financier, exceptionnel)
et le comportement attendu (mensuel, annuel, saisonnier).
"""

import pandas as pd
from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum


class AccountNature(Enum):
    """Nature du compte."""
    ACTIF = "actif"
    PASSIF = "passif"
    CHARGE = "charge"
    PRODUIT = "produit"
    SPECIAL = "special"  # Comptes 8 et 0


class AccountType(Enum):
    """Type de compte (pour charges/produits)."""
    EXPLOITATION = "exploitation"
    FINANCIER = "financier"
    EXCEPTIONNEL = "exceptionnel"
    IMPOT = "impot"
    NON_APPLICABLE = "n/a"


class BehaviorPattern(Enum):
    """Pattern de comportement attendu."""
    MENSUEL = "mensuel"         # Réparti sur 12 mois
    ANNUEL = "annuel"           # Concentré sur 1-2 mois
    SAISONNIER = "saisonnier"   # Pics réguliers
    VARIABLE = "variable"       # Irrégulier
    ABT_PROBABLE = "abt"        # Probablement un abonnement


@dataclass
class Behavior:
    """Comportement attendu d'un compte."""
    pattern: BehaviorPattern
    typical_month: Optional[int] = None  # Mois typique (12 pour annuel déc)
    description: str = ""


@dataclass
class PCGInfo:
    """Information PCG sur un compte."""
    compte: str
    classe: int
    nature: AccountNature
    type: AccountType
    libelle: str
    is_provision: bool
    is_reprise: bool
    is_amortissement: bool
    is_exceptionnel: bool
    is_is: bool  # Impôt sur les sociétés
    is_abt_candidate: bool  # Compte 488
    behavior: Behavior


# Définition des classes PCG
PCG_CLASSES = {
    1: {"nature": AccountNature.PASSIF, "libelle": "Capitaux propres"},
    2: {"nature": AccountNature.ACTIF, "libelle": "Immobilisations"},
    3: {"nature": AccountNature.ACTIF, "libelle": "Stocks"},
    4: {"nature": AccountNature.SPECIAL, "libelle": "Tiers"},  # Actif ou passif
    5: {"nature": AccountNature.ACTIF, "libelle": "Financier"},
    6: {"nature": AccountNature.CHARGE, "libelle": "Charges"},
    7: {"nature": AccountNature.PRODUIT, "libelle": "Produits"},
    8: {"nature": AccountNature.SPECIAL, "libelle": "Comptes spéciaux"},
}

# Détail des charges (classe 6)
CHARGES_DETAIL = {
    "60": {"type": AccountType.EXPLOITATION, "libelle": "Achats", "behavior": BehaviorPattern.MENSUEL},
    "61": {"type": AccountType.EXPLOITATION, "libelle": "Services extérieurs", "behavior": BehaviorPattern.MENSUEL},
    "62": {"type": AccountType.EXPLOITATION, "libelle": "Autres services extérieurs", "behavior": BehaviorPattern.MENSUEL},
    "63": {"type": AccountType.EXPLOITATION, "libelle": "Impôts et taxes", "behavior": BehaviorPattern.ABT_PROBABLE},
    "64": {"type": AccountType.EXPLOITATION, "libelle": "Charges de personnel", "behavior": BehaviorPattern.MENSUEL},
    "65": {"type": AccountType.EXPLOITATION, "libelle": "Autres charges de gestion", "behavior": BehaviorPattern.VARIABLE},
    "66": {"type": AccountType.FINANCIER, "libelle": "Charges financières", "behavior": BehaviorPattern.MENSUEL},
    "67": {"type": AccountType.EXCEPTIONNEL, "libelle": "Charges exceptionnelles", "behavior": BehaviorPattern.VARIABLE},
    "68": {"type": AccountType.EXPLOITATION, "libelle": "Dotations aux amort. et prov.", "behavior": BehaviorPattern.MENSUEL},
    "69": {"type": AccountType.IMPOT, "libelle": "Impôts sur les bénéfices", "behavior": BehaviorPattern.ANNUEL},
}

# Détail des produits (classe 7)
PRODUITS_DETAIL = {
    "70": {"type": AccountType.EXPLOITATION, "libelle": "Ventes", "behavior": BehaviorPattern.MENSUEL},
    "71": {"type": AccountType.EXPLOITATION, "libelle": "Production stockée", "behavior": BehaviorPattern.VARIABLE},
    "72": {"type": AccountType.EXPLOITATION, "libelle": "Production immobilisée", "behavior": BehaviorPattern.VARIABLE},
    "74": {"type": AccountType.EXPLOITATION, "libelle": "Subventions d'exploitation", "behavior": BehaviorPattern.VARIABLE},
    "75": {"type": AccountType.EXPLOITATION, "libelle": "Autres produits de gestion", "behavior": BehaviorPattern.VARIABLE},
    "76": {"type": AccountType.FINANCIER, "libelle": "Produits financiers", "behavior": BehaviorPattern.VARIABLE},
    "77": {"type": AccountType.EXCEPTIONNEL, "libelle": "Produits exceptionnels", "behavior": BehaviorPattern.VARIABLE},
    "78": {"type": AccountType.EXPLOITATION, "libelle": "Reprises sur amort. et prov.", "behavior": BehaviorPattern.VARIABLE},
    "79": {"type": AccountType.EXPLOITATION, "libelle": "Transferts de charges", "behavior": BehaviorPattern.VARIABLE},
}

# Comptes de provision (dotations)
PROVISION_ACCOUNTS = ["681", "686", "687"]

# Comptes de reprise
REPRISE_ACCOUNTS = ["781", "786", "787"]

# Comptes d'amortissement (dotations récurrentes)
AMORTISSEMENT_ACCOUNTS = ["6811", "6812"]


class PCGClassifier:
    """
    Classifie les comptes selon le PCG.

    Usage:
        pcg = PCGClassifier()
        info = pcg.classify("681000")
        print(info.libelle)  # "Dotations aux amort. et prov."
        print(info.is_provision)  # True
    """

    def classify(self, compte: str) -> PCGInfo:
        """
        Classifie un compte selon le PCG.

        Args:
            compte: Numéro de compte (ex: "601000", "681000")

        Returns:
            PCGInfo avec toutes les informations
        """
        compte = str(compte).strip()

        if not compte or not compte[0].isdigit():
            return self._unknown_account(compte)

        classe = int(compte[0])

        if classe not in PCG_CLASSES:
            return self._unknown_account(compte)

        # Infos de base
        classe_info = PCG_CLASSES[classe]
        nature = classe_info["nature"]

        # Déterminer le type et comportement
        type_compte = AccountType.NON_APPLICABLE
        behavior = Behavior(BehaviorPattern.VARIABLE)
        libelle = classe_info["libelle"]

        # Charges (classe 6)
        if classe == 6 and len(compte) >= 2:
            prefix = compte[:2]
            if prefix in CHARGES_DETAIL:
                detail = CHARGES_DETAIL[prefix]
                type_compte = detail["type"]
                libelle = detail["libelle"]
                behavior = Behavior(
                    pattern=detail["behavior"],
                    typical_month=12 if detail["behavior"] == BehaviorPattern.ANNUEL else None,
                )

        # Produits (classe 7)
        elif classe == 7 and len(compte) >= 2:
            prefix = compte[:2]
            if prefix in PRODUITS_DETAIL:
                detail = PRODUITS_DETAIL[prefix]
                type_compte = detail["type"]
                libelle = detail["libelle"]
                behavior = Behavior(pattern=detail["behavior"])

        # Déterminer les flags spéciaux
        is_provision = any(compte.startswith(p) for p in PROVISION_ACCOUNTS)
        is_reprise = any(compte.startswith(p) for p in REPRISE_ACCOUNTS)
        is_amortissement = any(compte.startswith(p) for p in AMORTISSEMENT_ACCOUNTS)
        is_exceptionnel = compte.startswith("67") or compte.startswith("77")
        is_is = compte.startswith("69")
        is_abt_candidate = compte.startswith("488")

        # Ajuster le comportement pour cas spéciaux
        if is_amortissement:
            behavior = Behavior(BehaviorPattern.MENSUEL, description="Amortissements récurrents")
        elif is_is:
            behavior = Behavior(BehaviorPattern.ANNUEL, typical_month=12, description="IS annuel")
        elif is_abt_candidate:
            behavior = Behavior(BehaviorPattern.ABT_PROBABLE, description="Compte d'abonnement probable")

        return PCGInfo(
            compte=compte,
            classe=classe,
            nature=nature,
            type=type_compte,
            libelle=libelle,
            is_provision=is_provision,
            is_reprise=is_reprise,
            is_amortissement=is_amortissement,
            is_exceptionnel=is_exceptionnel,
            is_is=is_is,
            is_abt_candidate=is_abt_candidate,
            behavior=behavior,
        )

    def _unknown_account(self, compte: str) -> PCGInfo:
        """Retourne une info par défaut pour compte inconnu."""
        return PCGInfo(
            compte=compte,
            classe=0,
            nature=AccountNature.SPECIAL,
            type=AccountType.NON_APPLICABLE,
            libelle="Compte non classifié",
            is_provision=False,
            is_reprise=False,
            is_amortissement=False,
            is_exceptionnel=False,
            is_is=False,
            is_abt_candidate=False,
            behavior=Behavior(BehaviorPattern.VARIABLE),
        )

    def classify_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Enrichit un DataFrame avec les classifications PCG.

        Args:
            df: DataFrame avec colonne 'compte'

        Returns:
            DataFrame enrichi avec colonnes PCG
        """
        df = df.copy()

        # Classifier chaque compte unique
        comptes = df["compte"].unique()
        classifications = {c: self.classify(c) for c in comptes}

        # Ajouter les colonnes
        df["pcg_classe"] = df["compte"].map(lambda c: classifications[c].classe)
        df["pcg_nature"] = df["compte"].map(lambda c: classifications[c].nature.value)
        df["pcg_type"] = df["compte"].map(lambda c: classifications[c].type.value)
        df["pcg_libelle"] = df["compte"].map(lambda c: classifications[c].libelle)
        df["is_provision"] = df["compte"].map(lambda c: classifications[c].is_provision)
        df["is_reprise"] = df["compte"].map(lambda c: classifications[c].is_reprise)
        df["is_amortissement"] = df["compte"].map(lambda c: classifications[c].is_amortissement)
        df["is_exceptionnel"] = df["compte"].map(lambda c: classifications[c].is_exceptionnel)
        df["is_is"] = df["compte"].map(lambda c: classifications[c].is_is)

        return df

    def get_provision_accounts(self, df: pd.DataFrame) -> list:
        """Retourne les comptes de provision (68x)."""
        return [c for c in df["compte"].unique() if self.classify(c).is_provision]

    def get_reprise_accounts(self, df: pd.DataFrame) -> list:
        """Retourne les comptes de reprise (78x)."""
        return [c for c in df["compte"].unique() if self.classify(c).is_reprise]

    def get_is_accounts(self, df: pd.DataFrame) -> list:
        """Retourne les comptes d'IS (69x)."""
        return [c for c in df["compte"].unique() if self.classify(c).is_is]

    def get_exceptional_accounts(self, df: pd.DataFrame) -> list:
        """Retourne les comptes exceptionnels (67x, 77x)."""
        return [c for c in df["compte"].unique() if self.classify(c).is_exceptionnel]
