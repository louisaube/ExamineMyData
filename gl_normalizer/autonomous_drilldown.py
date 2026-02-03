"""
STORY-030: Autonomous Drill-down - Analyse proactive autonome

Génère et exécute des analyses complémentaires basées sur les patterns détectés.
Implémente l'autonomie encadrée de l'IA.

"Liberté d'interrogation dans un cadre défini"
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Callable
import pandas as pd
import numpy as np
from datetime import datetime

from .pattern_detector import Pattern, PatternType, PatternSeverity


class QuestionType(Enum):
    """Types de questions de drill-down"""
    DETAIL_VIEW = "detail_view"          # Voir le détail des écritures
    TREND_ANALYSIS = "trend_analysis"    # Analyser l'évolution
    COMPARISON = "comparison"            # Comparer avec autre chose
    COUNTERPARTY = "counterparty"        # Identifier les contreparties
    BREAKDOWN = "breakdown"              # Décomposition par sous-catégorie


@dataclass
class Question:
    """Question de drill-down générée"""
    question_id: str
    question_type: QuestionType
    text: str
    pattern_ref: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5  # 1-10, 1 = haute priorité

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.question_id,
            "type": self.question_type.value,
            "text": self.text,
            "pattern_ref": self.pattern_ref,
            "parameters": self.parameters,
            "priority": self.priority
        }


@dataclass
class DrilldownResult:
    """Résultat d'une analyse drill-down"""
    question_id: str
    success: bool
    title: str
    summary: str
    data: Optional[pd.DataFrame] = None
    insights: List[str] = field(default_factory=list)
    follow_up_questions: List[Question] = field(default_factory=list)
    chart_data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "question_id": self.question_id,
            "success": self.success,
            "title": self.title,
            "summary": self.summary,
            "insights": self.insights,
            "follow_up_questions": [q.to_dict() for q in self.follow_up_questions]
        }
        if self.data is not None:
            result["data"] = self.data.head(50).to_dict(orient='records')
            result["row_count"] = len(self.data)
        if self.chart_data:
            result["chart_data"] = self.chart_data
        return result


class DrilldownGenerator:
    """
    Génère des questions de drill-down pertinentes basées sur les patterns.

    Enrichit les questions avec le contexte PCG et les détails spécifiques.
    """

    # Contexte PCG (Plan Comptable Général) français
    PCG_CONTEXT = {
        '1': {'name': 'Capitaux', 'description': 'Capital, réserves, provisions réglementées'},
        '2': {'name': 'Immobilisations', 'description': 'Actifs durables (matériel, immo incorporelles)'},
        '3': {'name': 'Stocks', 'description': 'Marchandises, matières premières, en-cours'},
        '4': {'name': 'Tiers', 'description': 'Clients, fournisseurs, État, personnel'},
        '5': {'name': 'Financier', 'description': 'Banque, caisse, VMP'},
        '6': {'name': 'Charges', 'description': 'Achats, services, personnel, impôts'},
        '7': {'name': 'Produits', 'description': 'Ventes, subventions, produits financiers'},
    }

    # Sous-classes importantes avec interprétations contextuelles
    PCG_SUBCLASSES = {
        '60': 'Achats (marchandises, MP, approvisionnements)',
        '61': 'Services extérieurs (sous-traitance, locations)',
        '62': 'Autres services (honoraires, publicité, transports)',
        '63': 'Impôts et taxes',
        '64': 'Charges de personnel (salaires, charges sociales)',
        '65': 'Autres charges de gestion courante',
        '66': 'Charges financières (intérêts)',
        '67': 'Charges exceptionnelles',
        '68': 'Dotations aux amortissements et provisions',
        '69': 'Participation et impôts sur bénéfices',
        '70': 'Ventes et prestations de services',
        '71': 'Production stockée (variation)',
        '72': 'Production immobilisée',
        '74': 'Subventions d\'exploitation',
        '75': 'Autres produits de gestion courante',
        '76': 'Produits financiers',
        '77': 'Produits exceptionnels',
        '78': 'Reprises sur amortissements et provisions',
        '79': 'Transferts de charges',
        '40': 'Fournisseurs et comptes rattachés',
        '41': 'Clients et comptes rattachés',
        '42': 'Personnel et comptes rattachés',
        '43': 'Sécurité sociale et organismes sociaux',
        '44': 'État et autres collectivités',
        '46': 'Débiteurs/créditeurs divers',
        '47': 'Comptes transitoires (CCA, PCA, FAE, FNP)',
        '48': 'Comptes de régularisation (charges/produits constatés d\'avance)',
        '49': 'Dépréciations des comptes de tiers',
    }

    def __init__(self, patterns: List[Pattern]):
        self.patterns = patterns
        self._question_counter = 0

    def _next_id(self) -> str:
        self._question_counter += 1
        return f"Q{self._question_counter:03d}"

    def _get_pcg_context(self, account: str) -> Dict[str, str]:
        """Récupère le contexte PCG pour un compte"""
        if not account:
            return {'classe': '', 'name': '', 'description': '', 'subclass': ''}

        account_str = str(account)
        classe = account_str[0] if account_str else ''
        subclass = account_str[:2] if len(account_str) >= 2 else ''

        classe_info = self.PCG_CONTEXT.get(classe, {'name': 'Inconnu', 'description': ''})
        subclass_desc = self.PCG_SUBCLASSES.get(subclass, '')

        return {
            'classe': classe,
            'name': classe_info['name'],
            'description': classe_info['description'],
            'subclass': subclass_desc
        }

    def _format_amount(self, amount: Optional[float]) -> str:
        """Formate un montant pour l'affichage"""
        if amount is None:
            return "N/A"
        if abs(amount) >= 1_000_000:
            return f"{amount/1_000_000:,.1f}M€"
        elif abs(amount) >= 1_000:
            return f"{amount/1_000:,.0f}K€"
        else:
            return f"{amount:,.0f}€"

    def generate_all(self) -> List[Question]:
        """Génère toutes les questions pour tous les patterns"""
        questions = []

        for pattern in self.patterns:
            questions.extend(self._generate_for_pattern(pattern))

        # Trier par priorité
        questions.sort(key=lambda q: q.priority)

        return questions

    def _generate_for_pattern(self, pattern: Pattern) -> List[Question]:
        """Génère les questions contextualisées pour un pattern spécifique"""
        questions = []
        pcg = self._get_pcg_context(pattern.account)
        amount_str = self._format_amount(pattern.amount)

        # Générer des questions enrichies selon le type de pattern
        if pattern.pattern_type == PatternType.YEAR_END_SPIKE:
            questions.extend(self._generate_year_end_questions(pattern, pcg, amount_str))
        elif pattern.pattern_type == PatternType.CONCENTRATION:
            questions.extend(self._generate_concentration_questions(pattern, pcg, amount_str))
        elif pattern.pattern_type == PatternType.RATIO_ANOMALY:
            questions.extend(self._generate_ratio_questions(pattern, pcg))
        elif pattern.pattern_type == PatternType.ROUND_NUMBER:
            questions.extend(self._generate_round_number_questions(pattern, amount_str))
        elif pattern.pattern_type == PatternType.DUPLICATE_AMOUNT:
            questions.extend(self._generate_duplicate_questions(pattern, amount_str))
        else:
            # Fallback: utiliser les questions suggérées par le pattern
            for i, suggestion in enumerate(pattern.suggested_questions[:3]):
                questions.append(self._create_question(
                    suggestion, pattern, pcg, i
                ))

        return questions

    def _generate_year_end_questions(self, pattern: Pattern, pcg: Dict, amount_str: str) -> List[Question]:
        """Questions contextuelles pour les pics de fin d'année"""
        questions = []
        account = pattern.account or ''
        details = pattern.details
        ratio = details.get('ratio', 0)
        monthly_avg = details.get('monthly_average', 0)

        # Interprétation contextuelle selon la classe de compte
        classe = pcg.get('classe', '')

        if classe == '7':
            # Produits - possibilité de produit à recevoir, régularisation, rattrapage
            interpretation = "produit à recevoir régularisé, rattrapage de facturation, ou extourne"
        elif classe == '6':
            # Charges - possibilité de provision, régularisation, charge exceptionnelle
            if pcg.get('subclass', '').startswith('Dotations'):
                interpretation = "dotation aux provisions ou amortissement exceptionnel"
            else:
                interpretation = "charge constatée d'avance, provision, ou facture non parvenue régularisée"
        elif classe == '4':
            # Tiers - possibilité de régularisation de solde
            interpretation = "régularisation de compte tiers, lettrage, ou écriture de clôture"
        else:
            interpretation = "écriture de régularisation ou opération exceptionnelle"

        questions.append(Question(
            question_id=self._next_id(),
            question_type=QuestionType.DETAIL_VIEW,
            text=f"Le compte {account} ({pcg.get('subclass', pcg.get('name', ''))}) concentre {amount_str} en décembre ({ratio:.1f}x la moyenne de {self._format_amount(monthly_avg)}). S'agit-il d'un {interpretation} ?",
            pattern_ref=pattern.pattern_type.value,
            parameters={"account": account, "amount": pattern.amount, "date": pattern.date, **details},
            priority=self._calculate_priority(pattern, 0)
        ))

        questions.append(Question(
            question_id=self._next_id(),
            question_type=QuestionType.TREND_ANALYSIS,
            text=f"Voir l'évolution mensuelle du compte {account} pour identifier si ce pic de {amount_str} est récurrent ou exceptionnel",
            pattern_ref=pattern.pattern_type.value,
            parameters={"account": account, "amount": pattern.amount, **details},
            priority=self._calculate_priority(pattern, 1)
        ))

        questions.append(Question(
            question_id=self._next_id(),
            question_type=QuestionType.COUNTERPARTY,
            text=f"Identifier le(s) tiers/contreparties de ces {amount_str} en décembre sur {account} (journal OD, fournisseur spécifique ?)",
            pattern_ref=pattern.pattern_type.value,
            parameters={"account": account, "amount": pattern.amount, **details},
            priority=self._calculate_priority(pattern, 2)
        ))

        return questions

    def _generate_concentration_questions(self, pattern: Pattern, pcg: Dict, amount_str: str) -> List[Question]:
        """Questions contextuelles pour les concentrations"""
        questions = []
        account = pattern.account or ''
        details = pattern.details
        concentration_pct = details.get('concentration_pct', 0)
        total_classe = details.get('total_classe', 0)
        classe_name = details.get('classe', '')

        questions.append(Question(
            question_id=self._next_id(),
            question_type=QuestionType.BREAKDOWN,
            text=f"Le compte {account} ({pcg.get('subclass', '')}) représente {concentration_pct:.0f}% des {classe_name} ({amount_str} sur {self._format_amount(total_classe)}). Décomposer par tiers/nature pour comprendre cette concentration.",
            pattern_ref=pattern.pattern_type.value,
            parameters={"account": account, "amount": pattern.amount, **details},
            priority=self._calculate_priority(pattern, 0)
        ))

        questions.append(Question(
            question_id=self._next_id(),
            question_type=QuestionType.TREND_ANALYSIS,
            text=f"Cette concentration de {concentration_pct:.0f}% sur {account} est-elle stable dans le temps ou récente ?",
            pattern_ref=pattern.pattern_type.value,
            parameters={"account": account, **details},
            priority=self._calculate_priority(pattern, 1)
        ))

        questions.append(Question(
            question_id=self._next_id(),
            question_type=QuestionType.COMPARISON,
            text=f"Comparer la répartition des {classe_name} avec N-1 : le compte {account} était-il déjà aussi dominant ?",
            pattern_ref=pattern.pattern_type.value,
            parameters={"account": account, **details},
            priority=self._calculate_priority(pattern, 2)
        ))

        return questions

    def _generate_ratio_questions(self, pattern: Pattern, pcg: Dict) -> List[Question]:
        """Questions contextuelles pour les anomalies de ratio"""
        questions = []
        details = pattern.details
        ratio = details.get('ratio', 0)

        if 'salaires' in details:
            # Ratio charges sociales / salaires
            salaires = details.get('salaires', 0)
            charges_soc = details.get('charges_sociales', 0)

            questions.append(Question(
                question_id=self._next_id(),
                question_type=QuestionType.BREAKDOWN,
                text=f"Ratio charges sociales/salaires de {ratio*100:.1f}% (normal: 40-60%). Décomposer les comptes 64x ({self._format_amount(salaires)}) et 645-647 ({self._format_amount(charges_soc)}) pour identifier l'écart.",
                pattern_ref=pattern.pattern_type.value,
                parameters={**details},
                priority=self._calculate_priority(pattern, 0)
            ))

            if ratio < 0.40:
                questions.append(Question(
                    question_id=self._next_id(),
                    question_type=QuestionType.DETAIL_VIEW,
                    text=f"Le ratio bas suggère des provisions manquantes ou des indemnités exonérées. Vérifier les comptes 645 (URSSAF), 647 (autres organismes) et les provisions 438.",
                    pattern_ref=pattern.pattern_type.value,
                    parameters={**details},
                    priority=self._calculate_priority(pattern, 1)
                ))

        elif 'achats' in details:
            # Ratio achats / ventes
            achats = details.get('achats', 0)
            ventes = details.get('ventes', 0)
            marge = details.get('marge_brute_pct', 0)

            questions.append(Question(
                question_id=self._next_id(),
                question_type=QuestionType.TREND_ANALYSIS,
                text=f"Marge brute de seulement {marge:.1f}% (achats {self._format_amount(achats)} / ventes {self._format_amount(ventes)}). Évolution mensuelle pour identifier si c'est structurel ou ponctuel.",
                pattern_ref=pattern.pattern_type.value,
                parameters={**details},
                priority=self._calculate_priority(pattern, 0)
            ))

            questions.append(Question(
                question_id=self._next_id(),
                question_type=QuestionType.BREAKDOWN,
                text=f"Décomposer les achats (601-607) par fournisseur : hausse des prix d'achat ou nouveaux fournisseurs ?",
                pattern_ref=pattern.pattern_type.value,
                parameters={**details},
                priority=self._calculate_priority(pattern, 1)
            ))

        return questions

    def _generate_round_number_questions(self, pattern: Pattern, amount_str: str) -> List[Question]:
        """Questions contextuelles pour les montants ronds"""
        questions = []
        details = pattern.details
        count = details.get('count', 0)

        questions.append(Question(
            question_id=self._next_id(),
            question_type=QuestionType.DETAIL_VIEW,
            text=f"{count} écritures avec montants très ronds (multiples de 10K€, total {amount_str}). Lister pour vérifier s'il s'agit d'estimations, provisions, ou erreurs.",
            pattern_ref=pattern.pattern_type.value,
            parameters={**details},
            priority=self._calculate_priority(pattern, 0)
        ))

        questions.append(Question(
            question_id=self._next_id(),
            question_type=QuestionType.BREAKDOWN,
            text=f"Quels journaux contiennent ces {count} montants ronds ? (OD = probable estimation, ACH/VTE = suspect)",
            pattern_ref=pattern.pattern_type.value,
            parameters={**details},
            priority=self._calculate_priority(pattern, 1)
        ))

        return questions

    def _generate_duplicate_questions(self, pattern: Pattern, amount_str: str) -> List[Question]:
        """Questions contextuelles pour les montants dupliqués"""
        questions = []
        details = pattern.details
        count = details.get('count', 0)

        questions.append(Question(
            question_id=self._next_id(),
            question_type=QuestionType.DETAIL_VIEW,
            text=f"Montant {amount_str} répété {count} fois. Lister ces écritures pour vérifier : abonnement récurrent, double saisie, ou fraude potentielle ?",
            pattern_ref=pattern.pattern_type.value,
            parameters={"amount": pattern.amount, **details},
            priority=self._calculate_priority(pattern, 0)
        ))

        questions.append(Question(
            question_id=self._next_id(),
            question_type=QuestionType.COUNTERPARTY,
            text=f"Identifier les contreparties des {count} écritures de {amount_str} : même tiers ou dispersé ?",
            pattern_ref=pattern.pattern_type.value,
            parameters={"amount": pattern.amount, **details},
            priority=self._calculate_priority(pattern, 1)
        ))

        return questions

    def _create_question(self, text: str, pattern: Pattern, pcg: Dict, index: int) -> Question:
        """Crée une question avec contexte enrichi"""
        q_type = self._infer_question_type(text)

        # Enrichir le texte avec le contexte PCG si disponible
        if pattern.account and pcg.get('subclass'):
            text = text + f" (compte de type: {pcg['subclass']})"

        return Question(
            question_id=self._next_id(),
            question_type=q_type,
            text=text,
            pattern_ref=pattern.pattern_type.value,
            parameters={
                "account": pattern.account,
                "amount": pattern.amount,
                "date": pattern.date,
                "pcg_context": pcg,
                **pattern.details
            },
            priority=self._calculate_priority(pattern, index)
        )

    def _infer_question_type(self, text: str) -> QuestionType:
        """Infère le type de question à partir du texte"""
        text_lower = text.lower()

        if any(w in text_lower for w in ['détail', 'lister', 'voir']):
            return QuestionType.DETAIL_VIEW
        elif any(w in text_lower for w in ['évolution', 'tendance', 'mensuel']):
            return QuestionType.TREND_ANALYSIS
        elif any(w in text_lower for w in ['comparer', 'comparaison', 'n-1']):
            return QuestionType.COMPARISON
        elif any(w in text_lower for w in ['contrepartie', 'fournisseur', 'client', 'tiers']):
            return QuestionType.COUNTERPARTY
        else:
            return QuestionType.BREAKDOWN

    def _calculate_priority(self, pattern: Pattern, question_index: int) -> int:
        """Calcule la priorité d'une question"""
        base_priority = {
            PatternSeverity.CRITICAL: 1,
            PatternSeverity.HIGH: 3,
            PatternSeverity.MEDIUM: 5,
            PatternSeverity.LOW: 7
        }.get(pattern.severity, 5)

        return min(10, base_priority + question_index)


class DrilldownExecutor:
    """
    Exécute les analyses de drill-down sur les données GL.

    Contraintes de l'autonomie encadrée:
    - Uniquement sur les données fournies (pas d'accès externe)
    - Types d'analyses prédéfinis
    - Max 3 niveaux de profondeur
    - Timeout par analyse
    """

    MAX_DEPTH = 3
    MAX_ROWS_RETURN = 100

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self._normalize_columns()
        self._executors: Dict[QuestionType, Callable] = {
            QuestionType.DETAIL_VIEW: self._execute_detail_view,
            QuestionType.TREND_ANALYSIS: self._execute_trend_analysis,
            QuestionType.COMPARISON: self._execute_comparison,
            QuestionType.COUNTERPARTY: self._execute_counterparty,
            QuestionType.BREAKDOWN: self._execute_breakdown
        }

    def _normalize_columns(self):
        """Normalise les noms de colonnes"""
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

        if 'montant' not in self.df.columns:
            if 'debit' in self.df.columns and 'credit' in self.df.columns:
                self.df['montant'] = self.df['debit'].fillna(0) - self.df['credit'].fillna(0)

    def execute(self, question: Question) -> DrilldownResult:
        """Exécute une analyse drill-down"""
        executor = self._executors.get(question.question_type)

        if not executor:
            return DrilldownResult(
                question_id=question.question_id,
                success=False,
                title="Type d'analyse non supporté",
                summary=f"Le type {question.question_type.value} n'est pas implémenté"
            )

        try:
            return executor(question)
        except Exception as e:
            return DrilldownResult(
                question_id=question.question_id,
                success=False,
                title="Erreur d'analyse",
                summary=f"Erreur lors de l'exécution: {str(e)}"
            )

    def execute_batch(self, questions: List[Question], max_count: int = 5) -> List[DrilldownResult]:
        """Exécute plusieurs analyses (mode automatique)"""
        results = []
        for question in questions[:max_count]:
            results.append(self.execute(question))
        return results

    def _execute_detail_view(self, question: Question) -> DrilldownResult:
        """Affiche le détail des écritures pour un compte/critère"""
        params = question.parameters
        account = params.get('account')

        if not account:
            return DrilldownResult(
                question_id=question.question_id,
                success=False,
                title="Paramètre manquant",
                summary="Aucun compte spécifié pour le détail"
            )

        # Filtrer par compte
        filtered = self.df[self.df['compte'].astype(str).str.startswith(str(account)[:3])]

        if filtered.empty:
            return DrilldownResult(
                question_id=question.question_id,
                success=False,
                title=f"Aucune écriture",
                summary=f"Pas d'écritures trouvées pour le compte {account}"
            )

        # Statistiques
        total_debit = filtered['debit'].sum() if 'debit' in filtered.columns else 0
        total_credit = filtered['credit'].sum() if 'credit' in filtered.columns else 0
        count = len(filtered)

        insights = [
            f"Total débit: {total_debit:,.2f}€",
            f"Total crédit: {total_credit:,.2f}€",
            f"Solde: {total_debit - total_credit:,.2f}€",
            f"Nombre d'écritures: {count}"
        ]

        # Questions de suivi
        follow_ups = []
        if 'date' in filtered.columns:
            follow_ups.append(Question(
                question_id=f"{question.question_id}_trend",
                question_type=QuestionType.TREND_ANALYSIS,
                text=f"Voir l'évolution mensuelle du compte {account}",
                parameters={"account": account},
                priority=5
            ))

        return DrilldownResult(
            question_id=question.question_id,
            success=True,
            title=f"Détail du compte {account}",
            summary=f"{count} écritures pour un solde de {total_debit - total_credit:,.2f}€",
            data=filtered.head(self.MAX_ROWS_RETURN),
            insights=insights,
            follow_up_questions=follow_ups
        )

    def _execute_trend_analysis(self, question: Question) -> DrilldownResult:
        """Analyse l'évolution mensuelle"""
        params = question.parameters
        account = params.get('account')

        df = self.df.copy()

        if account:
            df = df[df['compte'].astype(str).str.startswith(str(account)[:3])]

        if 'date' not in df.columns:
            return DrilldownResult(
                question_id=question.question_id,
                success=False,
                title="Données insuffisantes",
                summary="Colonne date manquante pour l'analyse de tendance"
            )

        try:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.dropna(subset=['date'])
            df['mois'] = df['date'].dt.to_period('M')

            if 'montant' in df.columns:
                monthly = df.groupby('mois')['montant'].agg(['sum', 'count']).reset_index()
                monthly.columns = ['mois', 'total', 'nb_ecritures']
                monthly['mois'] = monthly['mois'].astype(str)

                # Calcul tendance
                avg = monthly['total'].mean()
                std = monthly['total'].std()
                max_month = monthly.loc[monthly['total'].abs().idxmax(), 'mois']
                max_val = monthly['total'].abs().max()

                insights = [
                    f"Moyenne mensuelle: {avg:,.0f}€",
                    f"Écart-type: {std:,.0f}€",
                    f"Mois avec plus fort montant: {max_month} ({max_val:,.0f}€)"
                ]

                # Données pour graphique
                chart_data = {
                    "type": "line",
                    "labels": monthly['mois'].tolist(),
                    "values": monthly['total'].tolist()
                }

                return DrilldownResult(
                    question_id=question.question_id,
                    success=True,
                    title=f"Évolution mensuelle{' - ' + str(account) if account else ''}",
                    summary=f"Moyenne de {avg:,.0f}€/mois sur {len(monthly)} mois",
                    data=monthly,
                    insights=insights,
                    chart_data=chart_data
                )
        except Exception as e:
            return DrilldownResult(
                question_id=question.question_id,
                success=False,
                title="Erreur d'analyse",
                summary=str(e)
            )

        return DrilldownResult(
            question_id=question.question_id,
            success=False,
            title="Données insuffisantes",
            summary="Impossible de calculer la tendance"
        )

    def _execute_comparison(self, question: Question) -> DrilldownResult:
        """Compare deux périodes ou deux comptes"""
        params = question.parameters

        # Comparaison S1 vs S2
        df = self.df.copy()

        if 'date' not in df.columns:
            return DrilldownResult(
                question_id=question.question_id,
                success=False,
                title="Comparaison impossible",
                summary="Colonne date requise pour la comparaison"
            )

        try:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.dropna(subset=['date'])
            df['semestre'] = df['date'].dt.month.apply(lambda m: 'S1' if m <= 6 else 'S2')

            if 'montant' in df.columns:
                by_sem = df.groupby('semestre')['montant'].sum()

                s1 = by_sem.get('S1', 0)
                s2 = by_sem.get('S2', 0)
                variation = ((s2 - s1) / abs(s1) * 100) if s1 != 0 else 0

                insights = [
                    f"S1: {s1:,.0f}€",
                    f"S2: {s2:,.0f}€",
                    f"Variation: {variation:+.1f}%"
                ]

                return DrilldownResult(
                    question_id=question.question_id,
                    success=True,
                    title="Comparaison S1 vs S2",
                    summary=f"Variation de {variation:+.1f}% entre les deux semestres",
                    insights=insights,
                    chart_data={
                        "type": "bar",
                        "labels": ["S1", "S2"],
                        "values": [s1, s2]
                    }
                )
        except Exception as e:
            return DrilldownResult(
                question_id=question.question_id,
                success=False,
                title="Erreur",
                summary=str(e)
            )

        return DrilldownResult(
            question_id=question.question_id,
            success=False,
            title="Comparaison impossible",
            summary="Données insuffisantes"
        )

    def _execute_counterparty(self, question: Question) -> DrilldownResult:
        """Identifie les principales contreparties"""
        params = question.parameters
        account = params.get('account')

        df = self.df.copy()

        if account:
            df = df[df['compte'].astype(str).str.startswith(str(account)[:3])]

        # Chercher colonne tiers/auxiliaire
        tiers_col = None
        for col in df.columns:
            col_lower = col.lower()
            if any(w in col_lower for w in ['tiers', 'auxiliaire', 'aux', 'fournisseur', 'client']):
                tiers_col = col
                break

        if tiers_col and 'montant' in df.columns:
            by_tiers = df.groupby(tiers_col)['montant'].agg(['sum', 'count'])
            by_tiers = by_tiers.sort_values('sum', key=abs, ascending=False).head(10)
            by_tiers = by_tiers.reset_index()
            by_tiers.columns = ['tiers', 'total', 'nb_ecritures']

            top_tiers = by_tiers.iloc[0]['tiers'] if len(by_tiers) > 0 else "N/A"
            top_amount = by_tiers.iloc[0]['total'] if len(by_tiers) > 0 else 0

            return DrilldownResult(
                question_id=question.question_id,
                success=True,
                title="Principales contreparties",
                summary=f"Top tiers: {top_tiers} ({top_amount:,.0f}€)",
                data=by_tiers,
                insights=[
                    f"Top 1: {by_tiers.iloc[0]['tiers']} - {by_tiers.iloc[0]['total']:,.0f}€" if len(by_tiers) > 0 else "",
                    f"Top 2: {by_tiers.iloc[1]['tiers']} - {by_tiers.iloc[1]['total']:,.0f}€" if len(by_tiers) > 1 else "",
                    f"Top 3: {by_tiers.iloc[2]['tiers']} - {by_tiers.iloc[2]['total']:,.0f}€" if len(by_tiers) > 2 else ""
                ]
            )

        return DrilldownResult(
            question_id=question.question_id,
            success=False,
            title="Contreparties non identifiables",
            summary="Aucune colonne tiers/auxiliaire trouvée dans les données"
        )

    def _execute_breakdown(self, question: Question) -> DrilldownResult:
        """Décomposition par sous-catégorie"""
        params = question.parameters
        account = params.get('account')

        df = self.df.copy()

        if account:
            # Breakdown par sous-compte
            prefix = str(account)[:2]
            df = df[df['compte'].astype(str).str.startswith(prefix)]
            df['sous_compte'] = df['compte'].astype(str).str[:3]
            group_col = 'sous_compte'
            title = f"Décomposition du compte {prefix}x"
        else:
            # Breakdown par classe
            df['classe'] = df['compte'].astype(str).str[0]
            group_col = 'classe'
            title = "Décomposition par classe de compte"

        if 'montant' not in df.columns:
            return DrilldownResult(
                question_id=question.question_id,
                success=False,
                title="Données insuffisantes",
                summary="Colonne montant manquante"
            )

        breakdown = df.groupby(group_col)['montant'].agg(['sum', 'count'])
        breakdown = breakdown.sort_values('sum', key=abs, ascending=False)
        breakdown = breakdown.reset_index()
        breakdown.columns = [group_col, 'total', 'nb_ecritures']

        total = breakdown['total'].sum()
        breakdown['pct'] = (breakdown['total'] / total * 100).round(1) if total != 0 else 0

        insights = []
        for _, row in breakdown.head(5).iterrows():
            insights.append(f"{row[group_col]}: {row['total']:,.0f}€ ({row['pct']:.1f}%)")

        return DrilldownResult(
            question_id=question.question_id,
            success=True,
            title=title,
            summary=f"{len(breakdown)} catégories, total {total:,.0f}€",
            data=breakdown,
            insights=insights,
            chart_data={
                "type": "pie",
                "labels": breakdown[group_col].tolist()[:10],
                "values": breakdown['total'].abs().tolist()[:10]
            }
        )


class AutonomousAnalyzer:
    """
    Orchestrateur de l'analyse autonome encadrée.

    Combine PatternDetector, DrilldownGenerator et DrilldownExecutor
    pour fournir une analyse proactive complète.

    Contraintes de l'autonomie encadrée:
    - Périmètre données: Uniquement le fichier GL fourni
    - Types d'analyses: Liste prédéfinie (pas de code arbitraire)
    - Profondeur: Max 3 niveaux de drill-down
    - Temps: Max 30 secondes par analyse
    - Confidentialité: Aucune donnée envoyée à l'extérieur sans accord
    """

    def __init__(self, df: pd.DataFrame):
        from .pattern_detector import PatternDetector
        self.df = df
        self.pattern_detector = PatternDetector(df)
        self.patterns: List[Pattern] = []
        self.questions: List[Question] = []
        self.results: List[DrilldownResult] = []

    def analyze(self, auto_execute: bool = False, max_auto_questions: int = 5) -> Dict[str, Any]:
        """
        Lance l'analyse autonome.

        Args:
            auto_execute: Si True, exécute automatiquement les questions prioritaires
            max_auto_questions: Nombre max de questions à exécuter en auto

        Returns:
            Dictionnaire avec patterns, questions et résultats
        """
        # 1. Détecter les patterns
        self.patterns = self.pattern_detector.detect_all()

        # 2. Générer les questions
        generator = DrilldownGenerator(self.patterns)
        self.questions = generator.generate_all()

        # 3. Exécuter si mode auto
        if auto_execute and self.questions:
            executor = DrilldownExecutor(self.df)
            self.results = executor.execute_batch(self.questions, max_auto_questions)

        return self.to_dict()

    def execute_question(self, question_id: str) -> Optional[DrilldownResult]:
        """Exécute une question spécifique par son ID"""
        question = next((q for q in self.questions if q.question_id == question_id), None)

        if not question:
            return None

        executor = DrilldownExecutor(self.df)
        result = executor.execute(question)
        self.results.append(result)

        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patterns": [p.to_dict() for p in self.patterns],
            "questions": [q.to_dict() for q in self.questions],
            "results": [r.to_dict() for r in self.results],
            "summary": {
                "pattern_count": len(self.patterns),
                "question_count": len(self.questions),
                "executed_count": len(self.results),
                "critical_patterns": sum(1 for p in self.patterns if p.severity == PatternSeverity.CRITICAL),
                "high_patterns": sum(1 for p in self.patterns if p.severity == PatternSeverity.HIGH)
            }
        }


def run_autonomous_analysis(df: pd.DataFrame, auto_execute: bool = False) -> Dict[str, Any]:
    """
    Fonction utilitaire pour lancer l'analyse autonome.

    Args:
        df: DataFrame avec les données GL
        auto_execute: Si True, exécute les 5 premières questions automatiquement

    Returns:
        Résultats de l'analyse autonome
    """
    analyzer = AutonomousAnalyzer(df)
    return analyzer.analyze(auto_execute=auto_execute)
