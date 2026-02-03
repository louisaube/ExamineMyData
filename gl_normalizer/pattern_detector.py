"""
STORY-030: Pattern Detector - Détection automatique de patterns suspects

Identifie les anomalies et patterns nécessitant investigation approfondie.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
import pandas as pd
import numpy as np


class PatternType(Enum):
    """Types de patterns détectables"""
    YEAR_END_SPIKE = "year_end_spike"
    RATIO_ANOMALY = "ratio_anomaly"
    CORRELATION_BREAK = "correlation_break"
    UNUSUAL_COUNTERPARTY = "unusual_counterparty"
    ROUND_NUMBER = "round_number"
    DUPLICATE_AMOUNT = "duplicate_amount"
    MISSING_EXPECTED = "missing_expected"
    CONCENTRATION = "concentration"


class PatternSeverity(Enum):
    """Niveau de sévérité du pattern"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Pattern:
    """Pattern détecté nécessitant investigation"""
    pattern_type: PatternType
    severity: PatternSeverity
    title: str
    description: str
    account: Optional[str] = None
    amount: Optional[float] = None
    date: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    suggested_questions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.pattern_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "account": self.account,
            "amount": self.amount,
            "date": self.date,
            "details": self.details,
            "questions": self.suggested_questions
        }


class PatternDetector:
    """
    Détecteur de patterns suspects dans les données GL.

    Implémente la détection automatique pour l'autonomie encadrée de l'IA.
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self._normalize_columns()

    def _normalize_columns(self):
        """Normalise les noms de colonnes pour la détection"""
        col_mapping = {}
        for col in self.df.columns:
            col_lower = col.lower()
            if 'compte' in col_lower or 'account' in col_lower:
                col_mapping[col] = 'compte'
            elif 'debit' in col_lower:
                col_mapping[col] = 'debit'
            elif 'credit' in col_lower:
                col_mapping[col] = 'credit'
            elif 'date' in col_lower:
                col_mapping[col] = 'date'
            elif 'libell' in col_lower or 'label' in col_lower:
                col_mapping[col] = 'libelle'
            elif 'journal' in col_lower:
                col_mapping[col] = 'journal'

        if col_mapping:
            self.df = self.df.rename(columns=col_mapping)

        # Créer colonne montant si nécessaire
        if 'montant' not in self.df.columns:
            if 'debit' in self.df.columns and 'credit' in self.df.columns:
                self.df['montant'] = self.df['debit'].fillna(0) - self.df['credit'].fillna(0)

    def detect_all(self) -> List[Pattern]:
        """Détecte tous les patterns suspects"""
        patterns = []

        patterns.extend(self.detect_year_end_spikes())
        patterns.extend(self.detect_round_numbers())
        patterns.extend(self.detect_concentration())
        patterns.extend(self.detect_ratio_anomalies())
        patterns.extend(self.detect_duplicate_amounts())

        # Trier par sévérité
        severity_order = {
            PatternSeverity.CRITICAL: 0,
            PatternSeverity.HIGH: 1,
            PatternSeverity.MEDIUM: 2,
            PatternSeverity.LOW: 3
        }
        patterns.sort(key=lambda p: severity_order[p.severity])

        return patterns

    def detect_year_end_spikes(self) -> List[Pattern]:
        """
        Détecte les pics de fin d'année suspects.

        Ex: Compte 615000 avec 50K€ le 28/12 vs moyenne 2K€/mois
        """
        patterns = []

        if 'date' not in self.df.columns or 'compte' not in self.df.columns:
            return patterns

        try:
            # Convertir dates
            df = self.df.copy()
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.dropna(subset=['date'])

            if df.empty:
                return patterns

            # Identifier décembre
            df['month'] = df['date'].dt.month
            df['is_december'] = df['month'] == 12

            # Pour chaque compte, comparer décembre vs reste de l'année
            if 'montant' in df.columns:
                for compte in df['compte'].unique():
                    compte_df = df[df['compte'] == compte]

                    dec_total = abs(compte_df[compte_df['is_december']]['montant'].sum())
                    other_months = compte_df[~compte_df['is_december']]

                    if len(other_months) > 0:
                        monthly_avg = abs(other_months['montant'].sum()) / 11

                        # Si décembre > 5x la moyenne mensuelle et montant significatif
                        if monthly_avg > 0 and dec_total > monthly_avg * 5 and dec_total > 10000:
                            ratio = dec_total / monthly_avg
                            patterns.append(Pattern(
                                pattern_type=PatternType.YEAR_END_SPIKE,
                                severity=PatternSeverity.HIGH if ratio > 10 else PatternSeverity.MEDIUM,
                                title=f"Pic de fin d'année sur {compte}",
                                description=f"Montant décembre ({dec_total:,.0f}€) = {ratio:.1f}x la moyenne mensuelle ({monthly_avg:,.0f}€)",
                                account=str(compte),
                                amount=dec_total,
                                date="Décembre",
                                details={
                                    "december_total": dec_total,
                                    "monthly_average": monthly_avg,
                                    "ratio": ratio
                                },
                                suggested_questions=[
                                    f"Voir le détail des écritures de décembre sur {compte}",
                                    "Y a-t-il d'autres comptes avec ce pattern ?",
                                    "Quelle est la contrepartie principale ?"
                                ]
                            ))
        except Exception:
            pass

        return patterns[:5]  # Limiter à 5 patterns max

    def detect_round_numbers(self) -> List[Pattern]:
        """
        Détecte les montants ronds suspects (potentiel fraude/estimation).

        Ex: Montants exactement 10000, 50000, 100000...
        """
        patterns = []

        if 'montant' not in self.df.columns:
            return patterns

        try:
            # Montants ronds significatifs (>5000€ et divisible par 1000)
            df = self.df.copy()
            df['abs_montant'] = df['montant'].abs()

            round_amounts = df[
                (df['abs_montant'] >= 5000) &
                (df['abs_montant'] % 1000 == 0) &
                (df['abs_montant'] % 10000 == 0)  # Très ronds (dizaines de milliers)
            ]

            if len(round_amounts) > 0:
                # Compter les occurrences
                count = len(round_amounts)
                total = round_amounts['abs_montant'].sum()

                if count >= 3 and total > 50000:
                    patterns.append(Pattern(
                        pattern_type=PatternType.ROUND_NUMBER,
                        severity=PatternSeverity.MEDIUM,
                        title=f"{count} écritures avec montants très ronds",
                        description=f"Total de {total:,.0f}€ en montants multiples de 10K€",
                        amount=total,
                        details={
                            "count": count,
                            "amounts": round_amounts['abs_montant'].value_counts().head(5).to_dict()
                        },
                        suggested_questions=[
                            "Lister les écritures avec montants ronds",
                            "Vérifier si ce sont des estimations ou provisions",
                            "Identifier les journaux concernés"
                        ]
                    ))
        except Exception:
            pass

        return patterns

    def detect_concentration(self) -> List[Pattern]:
        """
        Détecte les concentrations anormales sur certains comptes.

        Ex: 80% des charges sur un seul fournisseur
        """
        patterns = []

        if 'compte' not in self.df.columns or 'montant' not in self.df.columns:
            return patterns

        try:
            # Analyser par classe de compte
            df = self.df.copy()
            df['classe'] = df['compte'].astype(str).str[0]

            for classe in ['6', '7']:  # Charges et produits
                classe_df = df[df['classe'] == classe]

                if len(classe_df) == 0:
                    continue

                total = classe_df['montant'].abs().sum()
                if total == 0:
                    continue

                # Top compte
                by_compte = classe_df.groupby('compte')['montant'].apply(lambda x: x.abs().sum())
                top_compte = by_compte.idxmax()
                top_amount = by_compte.max()
                concentration = top_amount / total * 100

                if concentration > 50 and top_amount > 100000:
                    classe_name = "charges" if classe == '6' else "produits"
                    patterns.append(Pattern(
                        pattern_type=PatternType.CONCENTRATION,
                        severity=PatternSeverity.HIGH if concentration > 70 else PatternSeverity.MEDIUM,
                        title=f"Concentration {concentration:.0f}% sur compte {top_compte}",
                        description=f"{top_amount:,.0f}€ sur {total:,.0f}€ de {classe_name}",
                        account=str(top_compte),
                        amount=top_amount,
                        details={
                            "concentration_pct": concentration,
                            "total_classe": total,
                            "classe": classe_name
                        },
                        suggested_questions=[
                            f"Détail des écritures du compte {top_compte}",
                            f"Évolution mensuelle de ce compte",
                            "Comparaison avec N-1 si disponible"
                        ]
                    ))
        except Exception:
            pass

        return patterns[:3]

    def detect_ratio_anomalies(self) -> List[Pattern]:
        """
        Détecte les ratios incohérents entre comptes liés.

        Ex: Charges de personnel sans charges sociales proportionnelles
        """
        patterns = []

        if 'compte' not in self.df.columns or 'montant' not in self.df.columns:
            return patterns

        try:
            df = self.df.copy()
            df['compte_3'] = df['compte'].astype(str).str[:3]

            # Ratio charges sociales / salaires
            salaires = df[df['compte_3'].isin(['641', '642', '643'])]['montant'].abs().sum()
            charges_soc = df[df['compte_3'].isin(['645', '646', '647'])]['montant'].abs().sum()

            if salaires > 100000:
                ratio = charges_soc / salaires if salaires > 0 else 0

                # Ratio normal entre 40% et 60%
                if ratio < 0.30 or ratio > 0.70:
                    severity = PatternSeverity.HIGH if ratio < 0.20 or ratio > 0.80 else PatternSeverity.MEDIUM
                    status = "anormalement bas" if ratio < 0.40 else "anormalement élevé"

                    patterns.append(Pattern(
                        pattern_type=PatternType.RATIO_ANOMALY,
                        severity=severity,
                        title=f"Ratio charges sociales/salaires {status}",
                        description=f"Ratio de {ratio*100:.1f}% (attendu: 40-60%)",
                        details={
                            "salaires": salaires,
                            "charges_sociales": charges_soc,
                            "ratio": ratio
                        },
                        suggested_questions=[
                            "Vérifier les provisions pour charges sociales",
                            "Y a-t-il des indemnités non soumises ?",
                            "Comparer avec les ratios sectoriels"
                        ]
                    ))

            # Ratio achats / ventes (pour entreprises commerciales)
            achats = df[df['compte_3'].isin(['601', '602', '607'])]['montant'].abs().sum()
            ventes = df[df['compte_3'].isin(['701', '702', '707'])]['montant'].abs().sum()

            if ventes > 100000 and achats > 0:
                ratio = achats / ventes

                if ratio > 0.85:
                    patterns.append(Pattern(
                        pattern_type=PatternType.RATIO_ANOMALY,
                        severity=PatternSeverity.MEDIUM,
                        title=f"Ratio achats/ventes élevé ({ratio*100:.0f}%)",
                        description=f"Marge brute de seulement {(1-ratio)*100:.1f}%",
                        details={
                            "achats": achats,
                            "ventes": ventes,
                            "ratio": ratio,
                            "marge_brute_pct": (1-ratio)*100
                        },
                        suggested_questions=[
                            "Analyser l'évolution des prix d'achat",
                            "Identifier les fournisseurs principaux",
                            "Vérifier la politique de prix de vente"
                        ]
                    ))
        except Exception:
            pass

        return patterns

    def detect_duplicate_amounts(self) -> List[Pattern]:
        """
        Détecte les montants identiques répétés (potentiel doublon).
        """
        patterns = []

        if 'montant' not in self.df.columns:
            return patterns

        try:
            df = self.df.copy()
            df['abs_montant'] = df['montant'].abs()

            # Montants significatifs répétés
            amount_counts = df[df['abs_montant'] > 1000]['abs_montant'].value_counts()

            suspicious = amount_counts[amount_counts >= 5]

            for amount, count in suspicious.head(3).items():
                if amount > 5000:  # Montant significatif
                    patterns.append(Pattern(
                        pattern_type=PatternType.DUPLICATE_AMOUNT,
                        severity=PatternSeverity.LOW,
                        title=f"Montant {amount:,.0f}€ répété {count} fois",
                        description="Possibles doublons ou écritures récurrentes à vérifier",
                        amount=amount,
                        details={
                            "count": count,
                            "total": amount * count
                        },
                        suggested_questions=[
                            f"Lister les {count} écritures de {amount:,.0f}€",
                            "Vérifier si ce sont des doublons",
                            "Identifier le pattern de ces écritures"
                        ]
                    ))
        except Exception:
            pass

        return patterns


def detect_patterns(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Fonction utilitaire pour détecter les patterns.

    Returns:
        Liste de patterns sous forme de dictionnaires
    """
    detector = PatternDetector(df)
    patterns = detector.detect_all()
    return [p.to_dict() for p in patterns]
