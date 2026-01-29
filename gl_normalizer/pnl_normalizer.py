"""
gl_normalizer/pnl_normalizer.py
Normalisation P&L avec redistribution des provisions et détection d'anomalies

Objectif: Transformer le P&L comptable en "run rate" opérationnel réel
en neutralisant les artefacts comptables (régularisations, provisions...).
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Tuple, Union
from dataclasses import dataclass, field

from .config import NormalizerConfig, COMPTES_CHARGES


@dataclass
class ProvisionAnalysis:
    """Analyse d'une régularisation de provision sur un compte"""

    compte: str
    libelle_compte: str
    total_annuel: float           # Total comptabilisé sur l'année
    run_rate_mensuel: float       # Charge mensuelle normalisée (total/12)
    decembre_brut: float          # Décembre tel que comptabilisé
    decembre_normalise: float     # Décembre après redistribution
    ecart_decembre: float         # Impact normalisation = normalisé - brut
    moyenne_hors_dec: float       # Moyenne des 11 autres mois
    ecart_vs_moyenne: float       # Écart décembre vs moyenne autres mois

    @property
    def pct_ecart(self) -> float:
        """Pourcentage d'écart décembre vs moyenne"""
        if self.moyenne_hors_dec == 0:
            return 0.0
        return (self.decembre_brut - self.moyenne_hors_dec) / abs(self.moyenne_hors_dec) * 100

    def __repr__(self) -> str:
        return (
            f"Compte {self.compte}: "
            f"Run rate={self.run_rate_mensuel:,.0f}€/mois, "
            f"Déc brut={self.decembre_brut:,.0f}€, "
            f"Impact={self.ecart_decembre:+,.0f}€"
        )


@dataclass
class AnomalyDetection:
    """Anomalie détectée sur un compte pour un mois donné"""

    compte: str
    libelle_compte: str
    mois: str                     # Format YYYY-MM
    montant_mois: float           # Valeur du mois
    moyenne_annuelle: float       # Moyenne de tous les mois
    ecart_type: float             # Écart-type annuel
    z_score: float                # Score standardisé
    ecart_absolu: float           # Différence vs moyenne
    ecart_pct: float              # % différence vs moyenne
    nature: str                   # "EXCES" ou "DEFICIT"

    @property
    def interpretation(self) -> str:
        """Interprétation de l'anomalie"""
        if self.nature == "EXCES":
            if self.ecart_pct > 100:
                return "Probable provision oubliée ou facture exceptionnelle"
            elif self.ecart_pct > 50:
                return "Charge concentrée - vérifier la nature"
            else:
                return "Légèrement supérieur à la moyenne"
        else:  # DEFICIT
            if self.ecart_pct < -50:
                return "Probable sur-provisionnement antérieur ou reprise"
            elif self.ecart_pct < -30:
                return "Charge sous moyenne - régularisation possible"
            else:
                return "Légèrement inférieur à la moyenne"

    def __repr__(self) -> str:
        return (
            f"{self.mois} - {self.compte}: "
            f"{self.montant_mois:,.0f}€ vs moy {self.moyenne_annuelle:,.0f}€ "
            f"(z={self.z_score:+.1f}, {self.nature})"
        )


@dataclass
class NormalizedPLResult:
    """Résultat complet de la normalisation P&L"""

    year: int

    # Totaux bruts
    charges_brutes: float
    produits_bruts: float
    resultat_brut: float

    # Totaux normalisés
    charges_normalisees: float
    produits_normalises: float
    resultat_normalise: float

    # Impact de la normalisation
    total_ajustement: float
    nb_comptes_ajustes: int

    # Détails
    provisions: List[ProvisionAnalysis] = field(default_factory=list)
    anomalies: List[AnomalyDetection] = field(default_factory=list)

    # DataFrames pour analyse détaillée
    monthly_by_compte: pd.DataFrame = field(default=None, repr=False)


class PnLNormalizer:
    """
    Normalisateur de P&L avec redistribution des provisions.

    Fonctionnalités:
    1. Analyse des provisions/régularisations par compte
    2. Redistribution sur 12 mois (calcul du run rate)
    3. Détection des anomalies statistiques
    4. Calcul du P&L normalisé
    """

    def __init__(
        self,
        df_gl: pd.DataFrame,
        year: int,
        config: Optional[NormalizerConfig] = None
    ):
        """
        Args:
            df_gl: GL classifié (avec colonnes harmonisées et classifiées)
            year: Année à analyser
            config: Configuration des seuils (optionnel)
        """
        self.df_gl = df_gl.copy()
        self.year = year
        self.config = config or NormalizerConfig()

        # Filtrer sur l'année
        self.df_gl = self.df_gl[self.df_gl["annee"] == year].copy()

        # Filtrer sur P&L (classes 6 et 7)
        self.df_pnl = self.df_gl[self.df_gl["classe"].isin(["6", "7"])].copy()

        # Assurer que montant_pnl existe
        if "montant_pnl" not in self.df_pnl.columns:
            self.df_pnl["montant_pnl"] = np.where(
                self.df_pnl["classe"] == "6",
                self.df_pnl["debit"] - self.df_pnl["credit"],
                self.df_pnl["credit"] - self.df_pnl["debit"]
            )

        # Préparer les données mensuelles
        self._prepare_monthly_data()

    def _prepare_monthly_data(self):
        """Prépare les agrégations mensuelles par compte"""

        # Agréger par compte et période
        self.monthly_by_compte = self.df_pnl.groupby(
            ["compte", "periode"]
        ).agg({
            "montant_pnl": "sum",
            "debit": "sum",
            "credit": "sum",
            "libelle_compte": "first",
            "classe": "first",
        }).reset_index()

        # Pivot pour avoir mois en colonnes
        self.pivot_comptes = self.monthly_by_compte.pivot_table(
            index="compte",
            columns="periode",
            values="montant_pnl",
            aggfunc="sum",
            fill_value=0
        )

        # Récupérer les libellés de compte
        self.compte_labels = self.monthly_by_compte.groupby("compte")[
            "libelle_compte"
        ].first().to_dict()

        # Identifier les mois disponibles
        self.mois_disponibles = sorted(self.pivot_comptes.columns.tolist())
        self.mois_decembre = f"{self.year}-12"
        self.mois_hors_decembre = [
            m for m in self.mois_disponibles
            if m != self.mois_decembre
        ]

    def analyze_provisions(
        self,
        seuil_regul: Optional[float] = None
    ) -> List[ProvisionAnalysis]:
        """
        Analyse les comptes avec régularisation significative.

        Un compte est considéré comme ayant une régularisation si
        son décembre s'écarte significativement de la moyenne des autres mois.

        Args:
            seuil_regul: Seuil minimum d'écart en € (défaut: config)

        Returns:
            Liste des analyses de provision triées par impact décroissant
        """
        seuil = seuil_regul or self.config.seuil_regul
        analyses = []

        for compte in self.pivot_comptes.index:
            # Ne traiter que les charges (classe 6)
            if not str(compte).startswith("6"):
                continue

            row = self.pivot_comptes.loc[compte]

            # Total annuel
            total_annuel = row.sum()

            # Valeur décembre
            dec_value = row.get(self.mois_decembre, 0)

            # Moyenne et stats des autres mois
            autres_mois_values = [row.get(m, 0) for m in self.mois_hors_decembre]
            moyenne_hors_dec = np.mean(autres_mois_values) if autres_mois_values else 0

            # Écart décembre vs moyenne
            ecart_vs_moyenne = dec_value - moyenne_hors_dec

            # Ignorer si écart non significatif
            if abs(ecart_vs_moyenne) < seuil:
                continue

            # Run rate = total annuel / 12
            run_rate = total_annuel / self.config.nb_mois

            # Décembre normalisé = run rate
            dec_normalise = run_rate

            # Impact = normalisé - brut
            ecart_normalisation = dec_normalise - dec_value

            analyses.append(ProvisionAnalysis(
                compte=compte,
                libelle_compte=self._get_libelle_compte(compte),
                total_annuel=total_annuel,
                run_rate_mensuel=run_rate,
                decembre_brut=dec_value,
                decembre_normalise=dec_normalise,
                ecart_decembre=ecart_normalisation,
                moyenne_hors_dec=moyenne_hors_dec,
                ecart_vs_moyenne=ecart_vs_moyenne,
            ))

        # Trier par impact décroissant
        analyses.sort(key=lambda x: abs(x.ecart_decembre), reverse=True)

        return analyses

    def detect_anomalies(
        self,
        z_threshold: Optional[float] = None,
        min_ecart_absolu: Optional[float] = None,
        min_ecart_pct: Optional[float] = None,
        classes: Optional[List[str]] = None,
        mois_cible: Optional[str] = None,
    ) -> List[AnomalyDetection]:
        """
        Détecte les mois anormalement élevés ou bas pour chaque compte.

        Une anomalie est détectée si:
        - Le z-score dépasse le seuil
        - ET l'écart absolu dépasse le minimum
        - ET l'écart en % dépasse le minimum

        Args:
            z_threshold: Seuil z-score (défaut: config)
            min_ecart_absolu: Écart minimum en € (défaut: config)
            min_ecart_pct: Écart minimum en % (défaut: config)
            classes: Classes de compte à analyser (défaut: ["6"])
            mois_cible: Si spécifié, ne cherche les anomalies que sur ce mois

        Returns:
            Liste des anomalies triées par z-score décroissant
        """
        z_threshold = z_threshold or self.config.z_score_threshold
        min_ecart_absolu = min_ecart_absolu or self.config.min_ecart_absolu
        min_ecart_pct = min_ecart_pct or self.config.min_ecart_pct
        classes = classes or ["6"]

        anomalies = []
        mois_a_analyser = [mois_cible] if mois_cible else self.mois_disponibles

        for compte in self.pivot_comptes.index:
            # Filtrer par classe
            if not any(str(compte).startswith(c) for c in classes):
                continue

            row = self.pivot_comptes.loc[compte]
            values = row.values

            # Stats
            moyenne = np.mean(values)
            ecart_type = np.std(values)

            # Ignorer si pas de variation significative
            if ecart_type < 100:
                continue

            # Analyser chaque mois
            for mois in mois_a_analyser:
                if mois not in row.index:
                    continue

                val = row[mois]

                # Z-score
                z_score = (val - moyenne) / ecart_type if ecart_type > 0 else 0

                # Écarts
                ecart_absolu = val - moyenne
                ecart_pct = (ecart_absolu / moyenne * 100) if moyenne != 0 else 0

                # Vérifier si anomalie
                is_anomaly = (
                    abs(z_score) >= z_threshold and
                    abs(ecart_absolu) >= min_ecart_absolu and
                    abs(ecart_pct) >= min_ecart_pct
                )

                if is_anomaly:
                    anomalies.append(AnomalyDetection(
                        compte=compte,
                        libelle_compte=self._get_libelle_compte(compte),
                        mois=mois,
                        montant_mois=val,
                        moyenne_annuelle=moyenne,
                        ecart_type=ecart_type,
                        z_score=z_score,
                        ecart_absolu=ecart_absolu,
                        ecart_pct=ecart_pct,
                        nature="EXCES" if z_score > 0 else "DEFICIT",
                    ))

        # Trier par z-score décroissant
        anomalies.sort(key=lambda x: abs(x.z_score), reverse=True)

        return anomalies

    def compute_normalized_december(
        self,
        provisions: Optional[List[ProvisionAnalysis]] = None
    ) -> NormalizedPLResult:
        """
        Calcule le P&L de décembre normalisé.

        Args:
            provisions: Liste des analyses (optionnel, sinon recalcule)

        Returns:
            Résultat complet avec brut, normalisé et détails
        """
        if provisions is None:
            provisions = self.analyze_provisions()

        # Données décembre brut
        dec_data = self.df_pnl[self.df_pnl["periode"] == self.mois_decembre]

        charges_brutes = dec_data[dec_data["classe"] == "6"]["montant_pnl"].sum()
        produits_bruts = dec_data[dec_data["classe"] == "7"]["montant_pnl"].sum()
        resultat_brut = produits_bruts - charges_brutes

        # Total des ajustements
        total_ajustement = sum(p.ecart_decembre for p in provisions)

        # P&L normalisé
        charges_normalisees = charges_brutes + total_ajustement
        resultat_normalise = produits_bruts - charges_normalisees

        # Anomalies décembre
        anomalies = self.detect_anomalies(mois_cible=self.mois_decembre)

        return NormalizedPLResult(
            year=self.year,
            charges_brutes=charges_brutes,
            produits_bruts=produits_bruts,
            resultat_brut=resultat_brut,
            charges_normalisees=charges_normalisees,
            produits_normalises=produits_bruts,  # Pas de normalisation sur produits
            resultat_normalise=resultat_normalise,
            total_ajustement=total_ajustement,
            nb_comptes_ajustes=len(provisions),
            provisions=provisions,
            anomalies=anomalies,
            monthly_by_compte=self.monthly_by_compte,
        )

    def get_monthly_comparison(self) -> pd.DataFrame:
        """
        Retourne un tableau de comparaison mensuelle par compte.

        Inclut stats et écarts pour identifier visuellement les anomalies.
        """
        df = self.pivot_comptes.copy()

        # Ajouter stats
        df["TOTAL"] = df[self.mois_disponibles].sum(axis=1)
        df["MOYENNE"] = df[self.mois_disponibles].mean(axis=1)
        df["ECART_TYPE"] = df[self.mois_disponibles].std(axis=1)

        if self.mois_decembre in df.columns:
            df["DEC_BRUT"] = df[self.mois_decembre]
            df["DEC_VS_MOY"] = df["DEC_BRUT"] - df["MOYENNE"]
            df["DEC_VS_MOY_PCT"] = np.where(
                df["MOYENNE"] != 0,
                df["DEC_VS_MOY"] / df["MOYENNE"].abs() * 100,
                0
            )
            df["RUN_RATE"] = df["TOTAL"] / self.config.nb_mois
            df["IMPACT_NORM"] = df["RUN_RATE"] - df["DEC_BRUT"]

        # Ajouter libellés
        df["LIBELLE"] = df.index.map(self.compte_labels)

        return df.sort_values("DEC_VS_MOY", key=abs, ascending=False)

    def _get_libelle_compte(self, compte: str) -> str:
        """Récupère le libellé d'un compte"""
        return self.compte_labels.get(compte, "")


def normalize_pnl(
    df_gl: pd.DataFrame,
    year: int,
    config: Optional[NormalizerConfig] = None
) -> NormalizedPLResult:
    """
    Fonction utilitaire pour normaliser rapidement un P&L.

    Args:
        df_gl: GL classifié
        year: Année à analyser
        config: Configuration (optionnel)

    Returns:
        Résultat de normalisation complet
    """
    normalizer = PnLNormalizer(df_gl, year, config)
    return normalizer.compute_normalized_december()


if __name__ == "__main__":
    print("PnLNormalizer - Normalisation P&L avec redistribution des provisions")
    print("Usage:")
    print("  from gl_normalizer.pnl_normalizer import PnLNormalizer, normalize_pnl")
    print("  result = normalize_pnl(df_gl, 2024)")
    print("  print(f'Résultat normalisé: {result.resultat_normalise:,.0f}€')")
