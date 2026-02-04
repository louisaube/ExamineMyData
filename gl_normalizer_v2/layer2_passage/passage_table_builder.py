"""
PassageTableBuilder - Tableau de passage brut → normalisé
=========================================================

STORY-206: LE LIVRABLE PRINCIPAL.

Construit le tableau de passage qui montre comment passer
du P&L brut au P&L normalisé, ligne par ligne.

C'est ça que le DAF veut voir en 30 secondes.
"""

import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum

from ..layer1_reading import (
    PCGClassifier,
    ABTDetector,
    ABTAccount,
    ProvisionMatcher,
    ProvisionCouple,
)


class RetraitementType(Enum):
    """Types de retraitements."""
    IS = "is"                     # Impôt sur les sociétés (redistribué)
    EXCEPTIONNEL = "exceptionnel"  # Charges/produits exceptionnels (exclus)
    PROVISION_NET = "provision"    # Provisions nettes (dotations - reprises)
    ABT = "abt"                   # Abonnements (neutralisés mensuellement)
    AMORTISSEMENT = "amortissement"  # Note: généralement PAS retraité


@dataclass
class Retraitement:
    """Un retraitement individuel."""
    type: RetraitementType
    compte: str
    libelle: str
    montant_brut: float        # Montant dans le P&L brut
    montant_retraite: float    # Ajustement (+ ou -)
    justification: str
    mois_origine: Optional[int] = None  # Mois où le montant était comptabilisé


@dataclass
class MonthlyPassage:
    """Tableau de passage pour un mois."""
    mois: int
    annee: int

    # Résultats bruts
    charges_brut: float
    produits_brut: float
    resultat_brut: float

    # Retraitements
    retraitements: List[Retraitement] = field(default_factory=list)

    # Résultats normalisés
    charges_normalise: float = 0.0
    produits_normalise: float = 0.0
    resultat_normalise: float = 0.0

    @property
    def total_retraitements(self) -> float:
        return sum(r.montant_retraite for r in self.retraitements)


@dataclass
class AnnualSummary:
    """Synthèse annuelle du tableau de passage."""
    annee: int

    # Brut
    charges_brut: float
    produits_brut: float
    resultat_brut: float

    # Normalisé
    charges_normalise: float
    produits_normalise: float
    resultat_normalise: float

    # Détail des retraitements
    retraitements: List[Retraitement] = field(default_factory=list)

    # Métriques
    @property
    def ecart_resultat(self) -> float:
        return self.resultat_normalise - self.resultat_brut

    @property
    def ecart_resultat_pct(self) -> float:
        if self.resultat_brut == 0:
            return 0.0
        return (self.ecart_resultat / abs(self.resultat_brut)) * 100

    @property
    def total_retraitements(self) -> float:
        return sum(r.montant_retraite for r in self.retraitements)


@dataclass
class RunRate:
    """Run rate mensuel."""
    charges_brut_mensuel: float
    charges_normalise_mensuel: float
    produits_brut_mensuel: float
    produits_normalise_mensuel: float
    resultat_brut_mensuel: float
    resultat_normalise_mensuel: float

    @property
    def ecart_charges_pct(self) -> float:
        if self.charges_brut_mensuel == 0:
            return 0.0
        return ((self.charges_normalise_mensuel - self.charges_brut_mensuel)
                / self.charges_brut_mensuel) * 100


class PassageTableBuilder:
    """
    Construit le tableau de passage P&L brut → normalisé.

    Usage:
        builder = PassageTableBuilder(pcg, abt_detector, provision_matcher)

        # Analyse
        monthly = builder.build_monthly(df)
        annual = builder.build_annual(df)
        run_rate = builder.compute_run_rate(df)

        # Afficher le résultat clé
        print(f"Résultat brut: {annual.resultat_brut:,.0f}€")
        print(f"Résultat normalisé: {annual.resultat_normalise:,.0f}€")
        print(f"Écart: {annual.ecart_resultat_pct:+.1f}%")
    """

    def __init__(
        self,
        pcg: Optional[PCGClassifier] = None,
        abt_detector: Optional[ABTDetector] = None,
        provision_matcher: Optional[ProvisionMatcher] = None,
    ):
        self.pcg = pcg or PCGClassifier()
        self.abt_detector = abt_detector or ABTDetector()
        self.provision_matcher = provision_matcher or ProvisionMatcher()

    def build_monthly(self, df: pd.DataFrame) -> List[MonthlyPassage]:
        """
        Construit le tableau de passage pour chaque mois.

        Args:
            df: DataFrame GL normalisé

        Returns:
            Liste de MonthlyPassage (un par mois)
        """
        # Pré-calculs
        abts = self.abt_detector.get_valid_abts(df)
        abt_comptes = [a.compte for a in abts]
        provisions = self.provision_matcher.match(df)

        # Enrichir avec PCG
        df_enriched = self.pcg.classify_dataframe(df)

        results = []
        annee = df["annee"].mode().iloc[0] if len(df) > 0 else 2024

        for mois in range(1, 13):
            mois_df = df_enriched[df_enriched["mois"] == mois]

            if len(mois_df) == 0:
                # Mois sans données
                results.append(MonthlyPassage(
                    mois=mois,
                    annee=annee,
                    charges_brut=0,
                    produits_brut=0,
                    resultat_brut=0,
                ))
                continue

            # Calcul brut
            charges_brut = mois_df[mois_df["pcg_classe"] == 6]["montant"].sum()
            produits_brut = mois_df[mois_df["pcg_classe"] == 7]["montant"].sum()
            resultat_brut = produits_brut - charges_brut

            passage = MonthlyPassage(
                mois=mois,
                annee=annee,
                charges_brut=abs(charges_brut),
                produits_brut=abs(produits_brut),
                resultat_brut=resultat_brut,
            )

            # Calculer les retraitements pour ce mois
            retraitements = self._compute_monthly_retraitements(
                mois_df, mois, abts, abt_comptes, provisions, df_enriched
            )
            passage.retraitements = retraitements

            # Appliquer les retraitements
            total_retrait = sum(r.montant_retraite for r in retraitements)
            passage.resultat_normalise = resultat_brut + total_retrait

            # Répartir sur charges/produits (simplifié)
            if total_retrait >= 0:
                passage.charges_normalise = abs(charges_brut) - total_retrait
                passage.produits_normalise = abs(produits_brut)
            else:
                passage.charges_normalise = abs(charges_brut)
                passage.produits_normalise = abs(produits_brut) + total_retrait

            results.append(passage)

        return results

    def _compute_monthly_retraitements(
        self,
        mois_df: pd.DataFrame,
        mois: int,
        abts: List[ABTAccount],
        abt_comptes: List[str],
        provisions: List[ProvisionCouple],
        df_full: pd.DataFrame,
    ) -> List[Retraitement]:
        """Calcule les retraitements pour un mois donné."""
        retraitements = []

        # 1. IS (compte 69) - Redistribuer sur 12 mois
        is_df = mois_df[mois_df["is_is"] == True]
        if len(is_df) > 0:
            is_montant = abs(is_df["montant"].sum())
            # En décembre: l'IS est passé, on doit l'étaler
            # Autres mois: on ajoute 1/12 de l'IS annuel
            is_annuel = abs(df_full[df_full["is_is"] == True]["montant"].sum())
            is_mensuel = is_annuel / 12

            if mois == 12 and is_montant > is_mensuel * 2:
                # Gros IS passé en décembre → retraiter
                retraitements.append(Retraitement(
                    type=RetraitementType.IS,
                    compte="695xxx",
                    libelle="IS annuel redistribué",
                    montant_brut=is_montant,
                    montant_retraite=is_montant - is_mensuel,  # Réduire la charge
                    justification=f"IS {is_annuel:,.0f}€ étalé sur 12 mois",
                    mois_origine=12,
                ))

        # 2. Exceptionnel (67/77) - Exclure
        except_charges = mois_df[mois_df["compte"].str.startswith("67")]["montant"].sum()
        except_produits = mois_df[mois_df["compte"].str.startswith("77")]["montant"].sum()
        except_net = abs(except_charges) - abs(except_produits)

        if abs(except_net) > 1000:  # Seuil de matérialité
            retraitements.append(Retraitement(
                type=RetraitementType.EXCEPTIONNEL,
                compte="67/77",
                libelle="Exceptionnel net",
                montant_brut=except_net,
                montant_retraite=-except_net if except_net > 0 else abs(except_net),
                justification="Charges/produits exceptionnels exclus du run rate",
                mois_origine=mois,
            ))

        # 3. ABT - Neutraliser le bruit mensuel
        for abt in abts:
            abt_mois_df = mois_df[mois_df["compte"] == abt.compte]
            if len(abt_mois_df) > 0:
                abt_montant = abt_mois_df["montant"].sum()
                # En décembre: grosse contrepassation → neutraliser
                if mois == 12 and abs(abt_montant) > abt.provision_mensuelle * 2:
                    retraitements.append(Retraitement(
                        type=RetraitementType.ABT,
                        compte=abt.compte,
                        libelle=f"ABT {abt.objet}",
                        montant_brut=abt_montant,
                        montant_retraite=-abt_montant,  # Neutraliser
                        justification=f"Contrepassation ABT (solde annuel: {abt.solde_annuel:,.0f}€)",
                        mois_origine=mois,
                    ))

        # 4. Provisions nettes (si concentration en décembre)
        if mois == 12:
            for prov in provisions:
                if prov.type_provision != "amortissement":
                    # Vérifier si concentration en décembre
                    dec_dots = [d for d in prov.detail_dotations if d["mois"] == 12]
                    if dec_dots and prov.montant_net > 10000:
                        dec_amount = sum(d["montant"] for d in dec_dots)
                        if dec_amount > prov.montant_dotation * 0.5:
                            retraitements.append(Retraitement(
                                type=RetraitementType.PROVISION_NET,
                                compte=prov.compte_dotation,
                                libelle=prov.libelle[:40],
                                montant_brut=dec_amount,
                                montant_retraite=-(dec_amount - prov.montant_net / 12),
                                justification=f"Provision {prov.type_provision} nette: {prov.montant_net:,.0f}€",
                                mois_origine=12,
                            ))

        return retraitements

    def build_annual(self, df: pd.DataFrame) -> AnnualSummary:
        """
        Construit la synthèse annuelle du tableau de passage.

        Args:
            df: DataFrame GL normalisé

        Returns:
            AnnualSummary avec totaux et détail des retraitements
        """
        monthly = self.build_monthly(df)
        annee = df["annee"].mode().iloc[0] if len(df) > 0 else 2024

        # Totaux bruts
        charges_brut = sum(m.charges_brut for m in monthly)
        produits_brut = sum(m.produits_brut for m in monthly)
        resultat_brut = produits_brut - charges_brut

        # Totaux normalisés
        charges_normalise = sum(m.charges_normalise for m in monthly)
        produits_normalise = sum(m.produits_normalise for m in monthly)
        resultat_normalise = produits_normalise - charges_normalise

        # Consolider les retraitements par type
        all_retraitements = []
        for m in monthly:
            all_retraitements.extend(m.retraitements)

        # Grouper par type
        consolidated = self._consolidate_retraitements(all_retraitements)

        return AnnualSummary(
            annee=annee,
            charges_brut=charges_brut,
            produits_brut=produits_brut,
            resultat_brut=resultat_brut,
            charges_normalise=charges_normalise,
            produits_normalise=produits_normalise,
            resultat_normalise=resultat_normalise,
            retraitements=consolidated,
        )

    def _consolidate_retraitements(
        self, retraitements: List[Retraitement]
    ) -> List[Retraitement]:
        """Consolide les retraitements par type."""
        by_type: Dict[RetraitementType, List[Retraitement]] = {}

        for r in retraitements:
            if r.type not in by_type:
                by_type[r.type] = []
            by_type[r.type].append(r)

        consolidated = []
        for rtype, items in by_type.items():
            if len(items) == 1:
                consolidated.append(items[0])
            else:
                # Consolider
                total_brut = sum(r.montant_brut for r in items)
                total_retraite = sum(r.montant_retraite for r in items)
                consolidated.append(Retraitement(
                    type=rtype,
                    compte=items[0].compte,
                    libelle=f"{rtype.value.upper()} consolidé ({len(items)} éléments)",
                    montant_brut=total_brut,
                    montant_retraite=total_retraite,
                    justification=", ".join(set(r.justification for r in items)),
                ))

        return consolidated

    def compute_run_rate(self, df: pd.DataFrame) -> RunRate:
        """
        Calcule le run rate mensuel brut et normalisé.

        Args:
            df: DataFrame GL normalisé

        Returns:
            RunRate avec les moyennes mensuelles
        """
        annual = self.build_annual(df)

        return RunRate(
            charges_brut_mensuel=annual.charges_brut / 12,
            charges_normalise_mensuel=annual.charges_normalise / 12,
            produits_brut_mensuel=annual.produits_brut / 12,
            produits_normalise_mensuel=annual.produits_normalise / 12,
            resultat_brut_mensuel=annual.resultat_brut / 12,
            resultat_normalise_mensuel=annual.resultat_normalise / 12,
        )

    def get_passage_table_text(self, df: pd.DataFrame) -> str:
        """
        Génère le tableau de passage en format texte.

        C'est ça que le DAF lit en 30 secondes.
        """
        annual = self.build_annual(df)
        run_rate = self.compute_run_rate(df)

        lines = [
            "=" * 60,
            "TABLEAU DE PASSAGE - P&L BRUT → NORMALISÉ",
            "=" * 60,
            "",
            f"Résultat comptable brut            {annual.resultat_brut:>15,.0f} €",
            "",
            "RETRAITEMENTS",
            "-" * 60,
        ]

        for r in annual.retraitements:
            signe = "+" if r.montant_retraite > 0 else ""
            lines.append(
                f"  {r.libelle:<35} {signe}{r.montant_retraite:>12,.0f} €"
            )
            lines.append(f"    → {r.justification}")

        lines.extend([
            "-" * 60,
            f"Total retraitements                {annual.total_retraitements:>15,.0f} €",
            "",
            "=" * 60,
            f"RÉSULTAT NORMALISÉ                 {annual.resultat_normalise:>15,.0f} €",
            f"Écart vs brut                      {annual.ecart_resultat_pct:>+14.1f} %",
            "=" * 60,
            "",
            "RUN RATE MENSUEL",
            f"  Charges brut:      {run_rate.charges_brut_mensuel:>12,.0f} €/mois",
            f"  Charges normalisé: {run_rate.charges_normalise_mensuel:>12,.0f} €/mois",
            f"  Écart:             {run_rate.ecart_charges_pct:>+11.1f} %",
        ])

        return "\n".join(lines)
