"""
AlertGenerator - Génération d'alertes contextuelles
===================================================

STORY-207: Génère uniquement les alertes UTILES.

Ce qu'on NE signale PAS:
- Montant rond sur compte ABT (c'est un abonnement)
- Concentration décembre sur amortissements (c'est récurrent)
- Creux août (c'est les congés)

Ce qu'on SIGNALE:
- Provision non budgétée (pas d'ABT associé)
- Reprise orpheline (sans dotation récente)
- Compte nouveau en décembre
- Changement de comportement N vs N-1
"""

import pandas as pd
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

from ..layer1_reading import (
    PCGClassifier,
    ABTDetector,
    ABTAccount,
    ProvisionMatcher,
    ProvisionCouple,
)


class AlertType(Enum):
    """Types d'alertes."""
    PROVISION_NON_BUDGETEE = "provision_non_budgetee"
    REPRISE_ORPHELINE = "reprise_orpheline"
    COMPTE_NOUVEAU_DECEMBRE = "compte_nouveau_decembre"
    CHANGEMENT_COMPORTEMENT = "changement_comportement"
    CONCENTRATION_ANORMALE = "concentration_anormale"


@dataclass
class Alert:
    """Une alerte contextuelle."""
    type: AlertType
    compte: str
    libelle_compte: str
    montant: float
    mois: Optional[int]
    libelle_ecriture: str
    contexte: str           # Explication métier
    question: str           # Action suggérée
    priorite: int           # 1 (haute) à 3 (basse)

    def to_text(self) -> str:
        """Formate l'alerte en texte."""
        priority_icon = {1: "🔴", 2: "🟡", 3: "🟢"}.get(self.priorite, "⚪")
        mois_str = f"Mois {self.mois}" if self.mois else "Annuel"

        return f"""
┌{'─' * 60}┐
│ {priority_icon} ALERTE [{self.type.value.upper()}]
├{'─' * 60}┤
│ Compte  : {self.compte} - {self.libelle_compte[:40]}
│ Montant : {self.montant:,.0f} €
│ Période : {mois_str}
│ Libellé : {self.libelle_ecriture[:50]}
│
│ CONTEXTE:
│ {self.contexte}
│
│ QUESTION: {self.question}
└{'─' * 60}┘
"""


class AlertGenerator:
    """
    Génère des alertes contextuelles utiles.

    Usage:
        generator = AlertGenerator(pcg, abt_accounts, provisions)
        alerts = generator.generate(df)

        for alert in alerts:
            print(alert.to_text())
    """

    def __init__(
        self,
        pcg: Optional[PCGClassifier] = None,
        abt_detector: Optional[ABTDetector] = None,
        provision_matcher: Optional[ProvisionMatcher] = None,
        max_alerts: int = 10,
    ):
        self.pcg = pcg or PCGClassifier()
        self.abt_detector = abt_detector or ABTDetector()
        self.provision_matcher = provision_matcher or ProvisionMatcher()
        self.max_alerts = max_alerts

    def generate(self, df: pd.DataFrame) -> List[Alert]:
        """
        Génère les alertes pour un GL.

        Args:
            df: DataFrame GL normalisé

        Returns:
            Liste d'alertes (max 10), triées par priorité
        """
        # Pré-calculs
        abt_accounts = self.abt_detector.get_valid_abts(df)
        abt_comptes = [a.compte for a in abt_accounts]
        provisions = self.provision_matcher.match(df)

        alerts = []

        # 1. Provisions non budgétées
        alerts.extend(self._detect_unbudgeted_provisions(df, abt_comptes))

        # 2. Reprises orphelines
        alerts.extend(self._detect_orphan_reprises(df, provisions))

        # 3. Comptes nouveaux en décembre
        alerts.extend(self._detect_new_december_accounts(df, abt_comptes))

        # 4. Concentrations anormales (hors ABT et amortissements)
        alerts.extend(self._detect_abnormal_concentrations(df, abt_comptes))

        # Filtrer le bruit et trier par priorité
        alerts = self._filter_noise(alerts, abt_comptes)
        alerts = sorted(alerts, key=lambda a: (a.priorite, -a.montant))

        return alerts[:self.max_alerts]

    def _detect_unbudgeted_provisions(
        self, df: pd.DataFrame, abt_comptes: List[str]
    ) -> List[Alert]:
        """
        Détecte les provisions sans ABT associé.

        Une provision en 6815 sans compte 488 correspondant = non budgétée.
        """
        alerts = []

        # Comptes de provision pour risques (pas amortissements)
        prov_comptes = [
            c for c in df["compte"].unique()
            if str(c).startswith(("6815", "686", "687"))
        ]

        for compte in prov_comptes:
            compte_df = df[df["compte"] == compte]
            montant = abs(compte_df["montant"].sum())

            if montant < 5000:  # Seuil de matérialité
                continue

            # Vérifier s'il y a un ABT associé
            # Chercher un compte 488 avec un libellé similaire
            libelles = compte_df["libelle"].dropna().tolist()
            has_abt = self._has_matching_abt(libelles, abt_comptes, df)

            if not has_abt:
                # Vérifier la concentration en décembre
                dec_df = compte_df[compte_df["mois"] == 12]
                dec_pct = len(dec_df) / len(compte_df) if len(compte_df) > 0 else 0

                if dec_pct > 0.5:  # Plus de 50% en décembre
                    libelle_sample = libelles[0] if libelles else ""
                    pcg_info = self.pcg.classify(compte)

                    alerts.append(Alert(
                        type=AlertType.PROVISION_NON_BUDGETEE,
                        compte=compte,
                        libelle_compte=pcg_info.libelle,
                        montant=montant,
                        mois=12,
                        libelle_ecriture=libelle_sample[:60],
                        contexte=(
                            f"• Pas de compte 488 associé → non anticipé dans le budget\n"
                            f"│ • {dec_pct*100:.0f}% du montant passé en décembre\n"
                            f"│ • Impact run rate si récurrent: {montant:,.0f}€/an"
                        ),
                        question="Ce risque est-il ponctuel ou doit-il être budgété pour N+1?",
                        priorite=1 if montant > 20000 else 2,
                    ))

        return alerts

    def _has_matching_abt(
        self, libelles: List[str], abt_comptes: List[str], df: pd.DataFrame
    ) -> bool:
        """Vérifie s'il existe un ABT avec un libellé similaire."""
        if not libelles or not abt_comptes:
            return False

        # Extraire les mots-clés des libellés de provision
        prov_text = " ".join(str(l).upper() for l in libelles)

        # Chercher dans les ABT
        for abt_compte in abt_comptes:
            abt_df = df[df["compte"] == abt_compte]
            abt_libelles = abt_df["libelle"].dropna().tolist()
            abt_text = " ".join(str(l).upper() for l in abt_libelles)

            # Match simple par mots-clés communs
            prov_words = set(prov_text.split())
            abt_words = set(abt_text.split())
            common = prov_words & abt_words

            # Si au moins 2 mots en commun (hors mots courants)
            common = {w for w in common if len(w) > 3}
            if len(common) >= 2:
                return True

        return False

    def _detect_orphan_reprises(
        self, df: pd.DataFrame, provisions: List[ProvisionCouple]
    ) -> List[Alert]:
        """
        Détecte les reprises sans dotation correspondante.

        Une reprise 78x sans dotation 68x récente = suspecte.
        """
        alerts = []

        # Comptes de reprise
        reprise_comptes = [c for c in df["compte"].unique() if str(c).startswith("78")]

        # Reprises couplées
        coupled = {p.compte_reprise for p in provisions if p.compte_reprise and p.is_matched}

        for compte in reprise_comptes:
            if compte in coupled:
                continue  # Déjà couplée

            compte_df = df[df["compte"] == compte]
            montant = abs(compte_df["montant"].sum())

            if montant < 10000:
                continue

            libelles = compte_df["libelle"].dropna().tolist()
            libelle_sample = libelles[0] if libelles else ""
            pcg_info = self.pcg.classify(compte)

            alerts.append(Alert(
                type=AlertType.REPRISE_ORPHELINE,
                compte=compte,
                libelle_compte=pcg_info.libelle,
                montant=montant,
                mois=None,
                libelle_ecriture=libelle_sample[:60],
                contexte=(
                    f"• Reprise de {montant:,.0f}€ sans dotation correspondante récente\n"
                    f"│ • Vérifier si le risque a réellement disparu\n"
                    f"│ • Ou si c'est une reprise opportuniste pour améliorer le résultat"
                ),
                question="Cette reprise est-elle justifiée par la disparition du risque?",
                priorite=2,
            ))

        return alerts

    def _detect_new_december_accounts(
        self, df: pd.DataFrame, abt_comptes: List[str]
    ) -> List[Alert]:
        """
        Détecte les comptes qui apparaissent uniquement en décembre.

        Un compte charge qui n'existe pas jan-nov et apparaît en décembre = suspect.
        """
        alerts = []

        # Comptes actifs par mois
        jan_nov = df[df["mois"] != 12]["compte"].unique()
        december = df[df["mois"] == 12]["compte"].unique()

        # Comptes nouveaux en décembre
        new_in_dec = set(december) - set(jan_nov)

        for compte in new_in_dec:
            # Ignorer les ABT
            if compte in abt_comptes:
                continue

            # Ignorer les non-charges/produits
            pcg_info = self.pcg.classify(compte)
            if pcg_info.classe not in [6, 7]:
                continue

            compte_df = df[df["compte"] == compte]
            montant = abs(compte_df["montant"].sum())

            if montant < 5000:
                continue

            libelles = compte_df["libelle"].dropna().tolist()
            libelle_sample = libelles[0] if libelles else ""

            alerts.append(Alert(
                type=AlertType.COMPTE_NOUVEAU_DECEMBRE,
                compte=compte,
                libelle_compte=pcg_info.libelle,
                montant=montant,
                mois=12,
                libelle_ecriture=libelle_sample[:60],
                contexte=(
                    f"• Ce compte n'existait pas de janvier à novembre\n"
                    f"│ • Apparition uniquement en décembre: {montant:,.0f}€\n"
                    f"│ • Peut être une régularisation ou une nouvelle charge"
                ),
                question="Cette charge est-elle récurrente ou exceptionnelle?",
                priorite=2 if montant > 10000 else 3,
            ))

        return alerts

    def _detect_abnormal_concentrations(
        self, df: pd.DataFrame, abt_comptes: List[str]
    ) -> List[Alert]:
        """
        Détecte les concentrations anormales (hors cas normaux).

        Exclusions:
        - ABT (normal)
        - Amortissements (normal si mensuel ou annuel)
        - IS (traité séparément)
        """
        alerts = []

        # Calculer la concentration décembre par compte
        for compte in df["compte"].unique():
            # Exclusions
            if compte in abt_comptes:
                continue

            pcg_info = self.pcg.classify(compte)

            # Ignorer IS (traité ailleurs)
            if pcg_info.is_is:
                continue

            # Ignorer amortissements récurrents
            if pcg_info.is_amortissement:
                continue

            # Ignorer exceptionnel (par définition variable)
            if pcg_info.is_exceptionnel:
                continue

            compte_df = df[df["compte"] == compte]
            total = abs(compte_df["montant"].sum())

            if total < 10000:
                continue

            dec_df = compte_df[compte_df["mois"] == 12]
            dec_amount = abs(dec_df["montant"].sum())
            dec_pct = dec_amount / total if total > 0 else 0

            # Concentration > 60% en décembre = anormal pour un compte d'exploitation
            if dec_pct > 0.6 and pcg_info.behavior.pattern.value == "mensuel":
                libelles = compte_df["libelle"].dropna().tolist()
                libelle_sample = libelles[0] if libelles else ""

                alerts.append(Alert(
                    type=AlertType.CONCENTRATION_ANORMALE,
                    compte=compte,
                    libelle_compte=pcg_info.libelle,
                    montant=dec_amount,
                    mois=12,
                    libelle_ecriture=libelle_sample[:60],
                    contexte=(
                        f"• {dec_pct*100:.0f}% du montant annuel passé en décembre\n"
                        f"│ • Comportement attendu: {pcg_info.behavior.pattern.value}\n"
                        f"│ • Montant décembre: {dec_amount:,.0f}€ sur {total:,.0f}€ annuel"
                    ),
                    question="Cette concentration est-elle justifiée?",
                    priorite=3,
                ))

        return alerts

    def _filter_noise(
        self, alerts: List[Alert], abt_comptes: List[str]
    ) -> List[Alert]:
        """Filtre les fausses alertes."""
        filtered = []

        for alert in alerts:
            # Double check: pas d'alerte sur ABT
            if alert.compte in abt_comptes:
                continue

            # Pas d'alerte sur montants insignifiants
            if alert.montant < 5000:
                continue

            filtered.append(alert)

        return filtered

    def get_alerts_text(self, df: pd.DataFrame) -> str:
        """Génère toutes les alertes en format texte."""
        alerts = self.generate(df)

        if not alerts:
            return "Aucune alerte significative détectée."

        lines = [
            "=" * 60,
            f"ALERTES CONTEXTUELLES ({len(alerts)} alertes)",
            "=" * 60,
        ]

        for i, alert in enumerate(alerts, 1):
            lines.append(f"\n#{i} " + alert.to_text())

        return "\n".join(lines)
