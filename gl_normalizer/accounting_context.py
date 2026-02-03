"""
gl_normalizer/accounting_context.py
Contexte comptable et référentiel PCG (Plan Comptable Général)

Fournit:
- Classification des comptes selon le PCG français
- Comportements attendus par type de compte
- Contexte métier pour la détection d'anomalies
"""

import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from enum import Enum


class AccountClass(Enum):
    """Classes de comptes selon le PCG"""
    CAPITAUX = "1"           # Classe 1 - Comptes de capitaux
    IMMOBILISATIONS = "2"    # Classe 2 - Immobilisations
    STOCKS = "3"             # Classe 3 - Stocks et en-cours
    TIERS = "4"              # Classe 4 - Comptes de tiers
    FINANCIERS = "5"         # Classe 5 - Comptes financiers
    CHARGES = "6"            # Classe 6 - Comptes de charges
    PRODUITS = "7"           # Classe 7 - Comptes de produits


class ChargeFrequency(Enum):
    """Fréquence attendue des charges"""
    MENSUELLE = "mensuelle"       # Charge récurrente chaque mois
    TRIMESTRIELLE = "trimestrielle"
    ANNUELLE = "annuelle"         # Charge concentrée (IS, CFE, etc.)
    VARIABLE = "variable"         # Dépend de l'activité
    EXCEPTIONNELLE = "exceptionnelle"


class AccountBehavior(Enum):
    """Comportement attendu du compte"""
    REGULIER = "regulier"         # Montants stables mois après mois
    SAISONNIER = "saisonnier"     # Pics prévisibles (énergie, etc.)
    PROVISION = "provision"       # Compte de dotation/reprise
    REGULARISATION = "regularisation"  # Écritures d'inventaire
    PONCTUEL = "ponctuel"         # Opérations ponctuelles


@dataclass
class AccountClassification:
    """Classification complète d'un compte"""
    compte: str
    classe: AccountClass
    libelle_pcg: str
    categorie: str               # Sous-catégorie (achats, services, etc.)
    frequency: ChargeFrequency
    behavior: AccountBehavior
    is_provision_compte: bool    # Compte de provision (68x, 78x)
    is_regul_typical: bool       # Compte souvent régularisé
    note: str = ""


@dataclass
class ExpectedBehavior:
    """Comportement attendu pour un compte"""
    compte: str
    monthly_expected: bool        # Devrait avoir des mouvements chaque mois
    year_end_spike_normal: bool   # Un pic en fin d'année est normal
    reversal_expected: bool       # Des reprises sont attendues
    seasonal_pattern: Optional[List[int]] = None  # Mois de pic attendus
    typical_variation_pct: float = 30.0  # Variation typique acceptable


# Référentiel PCG simplifié pour les comptes de charges (classe 6)
PCG_CHARGES = {
    # Achats (60)
    "601": ("Achats stockés - Matières premières", "achats", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "602": ("Achats stockés - Autres approvisionnements", "achats", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "604": ("Achats d'études et prestations", "achats", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "606": ("Achats non stockés", "achats", ChargeFrequency.MENSUELLE, AccountBehavior.REGULIER),
    "607": ("Achats de marchandises", "achats", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),

    # Services extérieurs (61)
    "611": ("Sous-traitance générale", "services", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "612": ("Redevances de crédit-bail", "services", ChargeFrequency.MENSUELLE, AccountBehavior.REGULIER),
    "613": ("Locations", "services", ChargeFrequency.MENSUELLE, AccountBehavior.REGULIER),
    "614": ("Charges locatives", "services", ChargeFrequency.TRIMESTRIELLE, AccountBehavior.SAISONNIER),
    "615": ("Entretien et réparations", "services", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "616": ("Primes d'assurance", "services", ChargeFrequency.ANNUELLE, AccountBehavior.PONCTUEL),
    "617": ("Études et recherches", "services", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "618": ("Divers services extérieurs", "services", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),

    # Autres services extérieurs (62)
    "621": ("Personnel extérieur", "services", ChargeFrequency.MENSUELLE, AccountBehavior.REGULIER),
    "622": ("Rémunérations d'intermédiaires", "services", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "623": ("Publicité, publications", "services", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "624": ("Transports de biens et collectifs", "services", ChargeFrequency.MENSUELLE, AccountBehavior.REGULIER),
    "625": ("Déplacements, missions", "services", ChargeFrequency.MENSUELLE, AccountBehavior.REGULIER),
    "626": ("Frais postaux et télécoms", "services", ChargeFrequency.MENSUELLE, AccountBehavior.REGULIER),
    "627": ("Services bancaires", "services", ChargeFrequency.MENSUELLE, AccountBehavior.REGULIER),
    "628": ("Divers autres services", "services", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),

    # Impôts et taxes (63)
    "631": ("Impôts, taxes sur rémunérations", "taxes", ChargeFrequency.ANNUELLE, AccountBehavior.REGULARISATION),
    "633": ("Impôts, taxes sur rémunérations", "taxes", ChargeFrequency.MENSUELLE, AccountBehavior.REGULIER),
    "635": ("Autres impôts, taxes", "taxes", ChargeFrequency.ANNUELLE, AccountBehavior.PONCTUEL),
    "637": ("Autres impôts, taxes", "taxes", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),

    # Charges de personnel (64)
    "641": ("Rémunérations du personnel", "personnel", ChargeFrequency.MENSUELLE, AccountBehavior.REGULIER),
    "644": ("Rémunération du travail de l'exploitant", "personnel", ChargeFrequency.MENSUELLE, AccountBehavior.REGULIER),
    "645": ("Charges de sécurité sociale", "personnel", ChargeFrequency.MENSUELLE, AccountBehavior.REGULIER),
    "647": ("Autres charges sociales", "personnel", ChargeFrequency.MENSUELLE, AccountBehavior.REGULIER),
    "648": ("Autres charges de personnel", "personnel", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),

    # Autres charges de gestion courante (65)
    "651": ("Redevances pour concessions", "autres", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "654": ("Pertes sur créances irrécouvrables", "autres", ChargeFrequency.EXCEPTIONNELLE, AccountBehavior.PONCTUEL),
    "658": ("Charges diverses de gestion", "autres", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),

    # Charges financières (66)
    "661": ("Charges d'intérêts", "financier", ChargeFrequency.MENSUELLE, AccountBehavior.REGULIER),
    "664": ("Pertes sur créances liées", "financier", ChargeFrequency.EXCEPTIONNELLE, AccountBehavior.PONCTUEL),
    "665": ("Escomptes accordés", "financier", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "666": ("Pertes de change", "financier", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "668": ("Autres charges financières", "financier", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),

    # Charges exceptionnelles (67)
    "671": ("Charges exceptionnelles sur opérations de gestion", "exceptionnel", ChargeFrequency.EXCEPTIONNELLE, AccountBehavior.PONCTUEL),
    "675": ("Valeurs comptables des éléments d'actif cédés", "exceptionnel", ChargeFrequency.EXCEPTIONNELLE, AccountBehavior.PONCTUEL),
    "678": ("Autres charges exceptionnelles", "exceptionnel", ChargeFrequency.EXCEPTIONNELLE, AccountBehavior.PONCTUEL),

    # Dotations aux amortissements et provisions (68)
    "681": ("Dotations aux amort. et prov. - exploitation", "dotations", ChargeFrequency.MENSUELLE, AccountBehavior.PROVISION),
    "686": ("Dotations aux amort. et prov. - financier", "dotations", ChargeFrequency.ANNUELLE, AccountBehavior.PROVISION),
    "687": ("Dotations aux amort. et prov. - exceptionnel", "dotations", ChargeFrequency.EXCEPTIONNELLE, AccountBehavior.PROVISION),

    # Impôts sur les bénéfices (69)
    "695": ("Impôts sur les bénéfices", "is", ChargeFrequency.ANNUELLE, AccountBehavior.REGULARISATION),
    "696": ("Suppléments d'IS", "is", ChargeFrequency.ANNUELLE, AccountBehavior.REGULARISATION),
    "698": ("Intégration fiscale", "is", ChargeFrequency.ANNUELLE, AccountBehavior.REGULARISATION),
    "699": ("Produits - Report IS", "is", ChargeFrequency.ANNUELLE, AccountBehavior.REGULARISATION),
}

# Comptes de produits (classe 7)
PCG_PRODUITS = {
    "701": ("Ventes de produits finis", "ventes", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "706": ("Prestations de services", "ventes", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "707": ("Ventes de marchandises", "ventes", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "708": ("Produits des activités annexes", "ventes", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "709": ("RRR accordés", "ventes", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),

    "713": ("Variation des stocks", "stocks", ChargeFrequency.ANNUELLE, AccountBehavior.REGULARISATION),

    "721": ("Production immobilisée - Immob. incorporelles", "production", ChargeFrequency.VARIABLE, AccountBehavior.PONCTUEL),
    "722": ("Production immobilisée - Immob. corporelles", "production", ChargeFrequency.VARIABLE, AccountBehavior.PONCTUEL),

    "741": ("Subventions d'exploitation", "subventions", ChargeFrequency.VARIABLE, AccountBehavior.PONCTUEL),
    "747": ("Quote-part subventions virées au résultat", "subventions", ChargeFrequency.ANNUELLE, AccountBehavior.REGULARISATION),

    "751": ("Redevances pour concessions", "autres", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "758": ("Produits divers de gestion courante", "autres", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),

    "761": ("Produits de participations", "financier", ChargeFrequency.ANNUELLE, AccountBehavior.PONCTUEL),
    "764": ("Revenus des VMP", "financier", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "765": ("Escomptes obtenus", "financier", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "766": ("Gains de change", "financier", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),
    "768": ("Autres produits financiers", "financier", ChargeFrequency.VARIABLE, AccountBehavior.REGULIER),

    "771": ("Produits exceptionnels sur opérations de gestion", "exceptionnel", ChargeFrequency.EXCEPTIONNELLE, AccountBehavior.PONCTUEL),
    "775": ("Produits des cessions d'éléments d'actif", "exceptionnel", ChargeFrequency.EXCEPTIONNELLE, AccountBehavior.PONCTUEL),
    "778": ("Autres produits exceptionnels", "exceptionnel", ChargeFrequency.EXCEPTIONNELLE, AccountBehavior.PONCTUEL),

    "781": ("Reprises sur amort. et prov. - exploitation", "reprises", ChargeFrequency.ANNUELLE, AccountBehavior.PROVISION),
    "786": ("Reprises sur prov. - financier", "reprises", ChargeFrequency.ANNUELLE, AccountBehavior.PROVISION),
    "787": ("Reprises sur prov. - exceptionnel", "reprises", ChargeFrequency.EXCEPTIONNELLE, AccountBehavior.PROVISION),
}

# Comptes typiquement régularisés en fin d'exercice
COMPTES_REGUL_TYPIQUES = {
    "486": "Charges constatées d'avance",
    "487": "Produits constatés d'avance",
    "408": "Fournisseurs - Factures non parvenues",
    "418": "Clients - Produits non encore facturés",
    "428": "Personnel - Charges à payer",
    "438": "Organismes sociaux - Charges à payer",
    "448": "État - Charges à payer",
    "468": "Divers - Charges à payer",
}


class AccountingContext:
    """
    Fournit le contexte comptable basé sur le PCG français.

    Permet de:
    - Classifier un compte selon le référentiel
    - Connaître le comportement attendu (mensuel, annuel, etc.)
    - Identifier les comptes à risque de régularisation
    """

    def __init__(self, version: str = "2025"):
        """
        Args:
            version: Version du PCG (pour évolution future)
        """
        self.version = version
        self._pcg = {**PCG_CHARGES, **PCG_PRODUITS}
        self._regul_comptes = COMPTES_REGUL_TYPIQUES

    def load_pcg(self) -> pd.DataFrame:
        """
        Charge le référentiel PCG sous forme de DataFrame.

        Returns:
            DataFrame avec colonnes: racine, libelle, categorie, frequency, behavior
        """
        data = []
        for racine, (libelle, categorie, freq, behavior) in self._pcg.items():
            data.append({
                "racine": racine,
                "libelle_pcg": libelle,
                "categorie": categorie,
                "frequency": freq.value,
                "behavior": behavior.value,
                "is_provision": racine.startswith(("68", "78")),
                "is_regul_typical": racine in ["631", "695", "696", "713", "747"],
            })
        return pd.DataFrame(data)

    def classify_account(self, compte: str) -> Optional[AccountClassification]:
        """
        Classifie un compte selon le PCG.

        Args:
            compte: Numéro de compte (ex: "601000", "6311000")

        Returns:
            AccountClassification ou None si non trouvé
        """
        # Essayer avec racines décroissantes (3 chars, puis 2)
        for length in [3, 2]:
            racine = compte[:length]
            if racine in self._pcg:
                libelle, categorie, freq, behavior = self._pcg[racine]
                classe = self._get_account_class(compte)
                return AccountClassification(
                    compte=compte,
                    classe=classe,
                    libelle_pcg=libelle,
                    categorie=categorie,
                    frequency=freq,
                    behavior=behavior,
                    is_provision_compte=racine.startswith(("68", "78")),
                    is_regul_typical=racine in ["631", "695", "696", "713", "747"],
                )
        return None

    def get_expected_behavior(self, compte: str) -> ExpectedBehavior:
        """
        Retourne le comportement attendu pour un compte.

        Args:
            compte: Numéro de compte

        Returns:
            ExpectedBehavior avec les attentes
        """
        classification = self.classify_account(compte)

        if classification is None:
            # Comportement par défaut pour comptes non référencés
            return ExpectedBehavior(
                compte=compte,
                monthly_expected=True,
                year_end_spike_normal=False,
                reversal_expected=False,
                typical_variation_pct=50.0,
            )

        # Déterminer les attentes selon la classification
        monthly = classification.frequency == ChargeFrequency.MENSUELLE
        spike_normal = classification.frequency in [ChargeFrequency.ANNUELLE, ChargeFrequency.EXCEPTIONNELLE]
        reversal = classification.is_provision_compte

        # Mois de pic typiques
        seasonal = None
        if classification.behavior == AccountBehavior.SAISONNIER:
            seasonal = [1, 4, 7, 10]  # Trimestriel par défaut
        elif classification.frequency == ChargeFrequency.ANNUELLE:
            seasonal = [12]  # Fin d'année

        # Variation acceptable
        if classification.behavior == AccountBehavior.REGULIER:
            variation = 30.0
        elif classification.behavior == AccountBehavior.SAISONNIER:
            variation = 50.0
        else:
            variation = 100.0  # Large pour les comptes ponctuels

        return ExpectedBehavior(
            compte=compte,
            monthly_expected=monthly,
            year_end_spike_normal=spike_normal,
            reversal_expected=reversal,
            seasonal_pattern=seasonal,
            typical_variation_pct=variation,
        )

    def is_regul_account(self, compte: str) -> bool:
        """Vérifie si le compte est typiquement régularisé"""
        racine = compte[:3]
        return racine in self._regul_comptes or racine in ["631", "695", "696"]

    def is_provision_account(self, compte: str) -> bool:
        """Vérifie si c'est un compte de dotation/reprise"""
        return compte[:2] in ["68", "78"]

    def get_category(self, compte: str) -> str:
        """Retourne la catégorie du compte (achats, services, personnel, etc.)"""
        classification = self.classify_account(compte)
        return classification.categorie if classification else "inconnu"

    def _get_account_class(self, compte: str) -> AccountClass:
        """Retourne la classe du compte"""
        classe_char = compte[0]
        mapping = {
            "1": AccountClass.CAPITAUX,
            "2": AccountClass.IMMOBILISATIONS,
            "3": AccountClass.STOCKS,
            "4": AccountClass.TIERS,
            "5": AccountClass.FINANCIERS,
            "6": AccountClass.CHARGES,
            "7": AccountClass.PRODUITS,
        }
        return mapping.get(classe_char, AccountClass.CHARGES)

    def analyze_accounts(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Enrichit un DataFrame de GL avec les informations PCG.

        Args:
            df: DataFrame avec colonne 'compte'

        Returns:
            DataFrame enrichi avec classification PCG
        """
        # Extraire les comptes uniques
        comptes_uniques = df["compte"].unique()

        # Classifier chaque compte
        classifications = []
        for compte in comptes_uniques:
            classif = self.classify_account(str(compte))
            behavior = self.get_expected_behavior(str(compte))

            classifications.append({
                "compte": compte,
                "pcg_libelle": classif.libelle_pcg if classif else "",
                "pcg_categorie": classif.categorie if classif else "inconnu",
                "pcg_frequency": classif.frequency.value if classif else "variable",
                "pcg_behavior": classif.behavior.value if classif else "regulier",
                "pcg_is_provision": classif.is_provision_compte if classif else False,
                "pcg_is_regul_typical": classif.is_regul_typical if classif else False,
                "expected_monthly": behavior.monthly_expected,
                "expected_year_end_spike": behavior.year_end_spike_normal,
                "typical_variation_pct": behavior.typical_variation_pct,
            })

        df_pcg = pd.DataFrame(classifications)

        # Merger avec le DataFrame original
        return df.merge(df_pcg, on="compte", how="left")

    def get_risk_accounts(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Identifie les comptes à risque de régularisation.

        Args:
            df: DataFrame avec colonne 'compte'

        Returns:
            DataFrame des comptes à surveiller
        """
        comptes = df["compte"].unique()

        risks = []
        for compte in comptes:
            classif = self.classify_account(str(compte))
            if classif and (classif.is_regul_typical or classif.is_provision_compte):
                risks.append({
                    "compte": compte,
                    "libelle_pcg": classif.libelle_pcg,
                    "categorie": classif.categorie,
                    "risk_type": "provision" if classif.is_provision_compte else "regularisation",
                    "frequency": classif.frequency.value,
                })

        return pd.DataFrame(risks)


def get_pcg_context(version: str = "2025") -> AccountingContext:
    """Factory function pour créer un contexte PCG"""
    return AccountingContext(version)


if __name__ == "__main__":
    print("AccountingContext - Référentiel PCG français")
    print("=" * 50)

    ctx = AccountingContext()

    # Test classification
    test_comptes = ["601000", "631100", "695000", "681100", "706000"]

    print("\nClassification des comptes:")
    for compte in test_comptes:
        classif = ctx.classify_account(compte)
        if classif:
            print(f"  {compte}: {classif.libelle_pcg}")
            print(f"    -> Catégorie: {classif.categorie}")
            print(f"    -> Fréquence: {classif.frequency.value}")
            print(f"    -> Provision: {classif.is_provision_compte}")

    # Test comportement attendu
    print("\nComportements attendus:")
    for compte in test_comptes:
        behavior = ctx.get_expected_behavior(compte)
        print(f"  {compte}:")
        print(f"    -> Mensuel: {behavior.monthly_expected}")
        print(f"    -> Pic fin d'année normal: {behavior.year_end_spike_normal}")
        print(f"    -> Variation typique: {behavior.typical_variation_pct}%")
