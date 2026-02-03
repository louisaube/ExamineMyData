"""
STORY-030: AI-Enhanced Drill-down Analysis

Intègre les providers IA (OpenAI/Anthropic) pour des analyses plus intelligentes.
Utilise le secrets_manager pour récupérer les tokens API.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .pattern_detector import Pattern, PatternType, PatternSeverity
from .autonomous_drilldown import Question, QuestionType, DrilldownResult
from .secrets_manager import get_secrets_manager, SecretType

logger = logging.getLogger(__name__)


@dataclass
class AIAnalysisResult:
    """Résultat d'une analyse IA"""
    success: bool
    provider: str
    analysis: str
    recommendations: List[str]
    confidence: float
    raw_response: Optional[Dict[str, Any]] = None


class AIAnalyzer:
    """
    Analyseur utilisant les LLMs pour enrichir les analyses drill-down.

    Supporte OpenAI et Anthropic via les tokens configurés dans secrets_manager.
    """

    SYSTEM_PROMPT = """Tu es un expert-comptable français spécialisé dans l'analyse
des grands livres (GL). Tu analyses les patterns et anomalies détectés dans les données
comptables pour fournir des recommandations pertinentes.

Contexte: Plan Comptable Général (PCG) français
- Classe 1: Capitaux
- Classe 2: Immobilisations
- Classe 3: Stocks
- Classe 4: Tiers (clients, fournisseurs)
- Classe 5: Financier
- Classe 6: Charges
- Classe 7: Produits

Réponds de manière concise et actionnable."""

    def __init__(self):
        self.secrets_mgr = get_secrets_manager()
        self._openai_client = None
        self._anthropic_client = None

    def _get_openai_client(self):
        """Initialise le client OpenAI si disponible"""
        if self._openai_client is not None:
            return self._openai_client

        api_key = self.secrets_mgr.get_secret(SecretType.OPENAI_API_KEY, prompt_if_missing=False)
        if not api_key:
            return None

        try:
            import openai
            self._openai_client = openai.OpenAI(api_key=api_key)
            return self._openai_client
        except ImportError:
            logger.warning("Module openai non installé. pip install openai")
            return None
        except Exception as e:
            logger.error(f"Erreur initialisation OpenAI: {e}")
            return None

    def _get_anthropic_client(self):
        """Initialise le client Anthropic si disponible"""
        if self._anthropic_client is not None:
            return self._anthropic_client

        api_key = self.secrets_mgr.get_secret(SecretType.ANTHROPIC_API_KEY, prompt_if_missing=False)
        if not api_key:
            return None

        try:
            import anthropic
            self._anthropic_client = anthropic.Anthropic(api_key=api_key)
            return self._anthropic_client
        except ImportError:
            logger.warning("Module anthropic non installé. pip install anthropic")
            return None
        except Exception as e:
            logger.error(f"Erreur initialisation Anthropic: {e}")
            return None

    def is_available(self) -> bool:
        """Vérifie si au moins un provider IA est disponible"""
        return self._get_openai_client() is not None or self._get_anthropic_client() is not None

    def get_available_provider(self) -> Optional[str]:
        """Retourne le provider disponible (priorité: Anthropic > OpenAI)"""
        if self._get_anthropic_client():
            return "anthropic"
        if self._get_openai_client():
            return "openai"
        return None

    def analyze_pattern(self, pattern: Pattern, context: Dict[str, Any] = None) -> AIAnalysisResult:
        """
        Analyse un pattern avec l'IA pour obtenir des insights supplémentaires.

        Args:
            pattern: Pattern détecté à analyser
            context: Contexte supplémentaire (données, stats, etc.)

        Returns:
            AIAnalysisResult avec l'analyse et les recommandations
        """
        provider = self.get_available_provider()

        if not provider:
            return AIAnalysisResult(
                success=False,
                provider="none",
                analysis="Aucun provider IA configuré. Configurez un token dans /settings.",
                recommendations=[],
                confidence=0.0
            )

        prompt = self._build_pattern_prompt(pattern, context)

        try:
            if provider == "anthropic":
                return self._analyze_with_anthropic(prompt)
            else:
                return self._analyze_with_openai(prompt)
        except Exception as e:
            logger.error(f"Erreur analyse IA: {e}")
            return AIAnalysisResult(
                success=False,
                provider=provider,
                analysis=f"Erreur lors de l'analyse: {str(e)}",
                recommendations=[],
                confidence=0.0
            )

    def enhance_questions(self, patterns: List[Pattern], existing_questions: List[Question]) -> List[Question]:
        """
        Utilise l'IA pour générer des questions supplémentaires pertinentes.

        Args:
            patterns: Liste des patterns détectés
            existing_questions: Questions déjà générées

        Returns:
            Liste de nouvelles questions suggérées par l'IA
        """
        provider = self.get_available_provider()

        if not provider:
            return []

        prompt = self._build_questions_prompt(patterns, existing_questions)

        try:
            if provider == "anthropic":
                result = self._analyze_with_anthropic(prompt)
            else:
                result = self._analyze_with_openai(prompt)

            if result.success:
                return self._parse_questions_from_response(result.analysis, len(existing_questions))
            return []
        except Exception as e:
            logger.error(f"Erreur génération questions IA: {e}")
            return []

    def _build_pattern_prompt(self, pattern: Pattern, context: Dict[str, Any] = None) -> str:
        """Construit le prompt pour l'analyse d'un pattern"""
        prompt = f"""Analyse ce pattern détecté dans un grand livre comptable:

Type: {pattern.pattern_type.value}
Sévérité: {pattern.severity.value}
Titre: {pattern.title}
Description: {pattern.description}
Compte concerné: {pattern.account or 'N/A'}
Montant: {f'{pattern.amount:,.0f}€' if pattern.amount else 'N/A'}

Détails supplémentaires:
{json.dumps(pattern.details, indent=2, default=str)}
"""

        if context:
            prompt += f"\nContexte additionnel:\n{json.dumps(context, indent=2, default=str)}"

        prompt += """

Fournis:
1. Une analyse concise (2-3 phrases) de ce que ce pattern indique
2. 3 recommandations d'actions concrètes
3. Un niveau de confiance (0-100%) sur la pertinence de cette anomalie

Format de réponse JSON:
{
  "analysis": "...",
  "recommendations": ["...", "...", "..."],
  "confidence": 85
}"""

        return prompt

    def _build_questions_prompt(self, patterns: List[Pattern], existing: List[Question]) -> str:
        """Construit le prompt pour générer des questions supplémentaires"""
        patterns_summary = "\n".join([
            f"- {p.pattern_type.value}: {p.title} (sévérité: {p.severity.value})"
            for p in patterns[:5]
        ])

        existing_summary = "\n".join([
            f"- {q.text}"
            for q in existing[:10]
        ])

        return f"""En tant qu'expert-comptable, génère 3-5 questions d'investigation supplémentaires
basées sur ces patterns détectés dans un grand livre:

Patterns détectés:
{patterns_summary}

Questions déjà générées:
{existing_summary}

Génère des questions DIFFÉRENTES et COMPLÉMENTAIRES qui pourraient révéler
d'autres anomalies ou approfondir l'analyse.

Format de réponse JSON:
{{
  "questions": [
    {{"text": "...", "type": "detail_view|trend_analysis|comparison|counterparty|breakdown", "priority": 1-10}},
    ...
  ]
}}"""

    def _analyze_with_openai(self, prompt: str) -> AIAnalysisResult:
        """Effectue l'analyse avec OpenAI"""
        client = self._get_openai_client()

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )

        content = response.choices[0].message.content

        try:
            # Essayer de parser le JSON
            data = json.loads(content)
            return AIAnalysisResult(
                success=True,
                provider="openai",
                analysis=data.get("analysis", content),
                recommendations=data.get("recommendations", []),
                confidence=data.get("confidence", 70) / 100,
                raw_response=data
            )
        except json.JSONDecodeError:
            # Réponse texte brute
            return AIAnalysisResult(
                success=True,
                provider="openai",
                analysis=content,
                recommendations=[],
                confidence=0.7
            )

    def _analyze_with_anthropic(self, prompt: str) -> AIAnalysisResult:
        """Effectue l'analyse avec Anthropic"""
        client = self._get_anthropic_client()

        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1000,
            system=self.SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        content = response.content[0].text

        try:
            data = json.loads(content)
            return AIAnalysisResult(
                success=True,
                provider="anthropic",
                analysis=data.get("analysis", content),
                recommendations=data.get("recommendations", []),
                confidence=data.get("confidence", 70) / 100,
                raw_response=data
            )
        except json.JSONDecodeError:
            return AIAnalysisResult(
                success=True,
                provider="anthropic",
                analysis=content,
                recommendations=[],
                confidence=0.7
            )

    def _parse_questions_from_response(self, response: str, offset: int) -> List[Question]:
        """Parse les questions depuis la réponse IA"""
        questions = []

        try:
            data = json.loads(response)
            raw_questions = data.get("questions", [])

            for i, q in enumerate(raw_questions[:5]):
                q_type = QuestionType.BREAKDOWN
                type_str = q.get("type", "breakdown").lower()

                type_mapping = {
                    "detail_view": QuestionType.DETAIL_VIEW,
                    "trend_analysis": QuestionType.TREND_ANALYSIS,
                    "comparison": QuestionType.COMPARISON,
                    "counterparty": QuestionType.COUNTERPARTY,
                    "breakdown": QuestionType.BREAKDOWN
                }
                q_type = type_mapping.get(type_str, QuestionType.BREAKDOWN)

                questions.append(Question(
                    question_id=f"AI{offset + i + 1:03d}",
                    question_type=q_type,
                    text=q.get("text", ""),
                    pattern_ref="ai_generated",
                    parameters={},
                    priority=min(10, max(1, q.get("priority", 5)))
                ))
        except (json.JSONDecodeError, KeyError):
            pass

        return questions


def get_ai_analyzer() -> AIAnalyzer:
    """Factory pour obtenir l'analyseur IA"""
    return AIAnalyzer()


def enhance_analysis_with_ai(patterns: List[Pattern], questions: List[Question]) -> Dict[str, Any]:
    """
    Fonction utilitaire pour enrichir une analyse avec l'IA.

    Args:
        patterns: Patterns détectés
        questions: Questions générées

    Returns:
        Dictionnaire avec les enrichissements IA
    """
    analyzer = get_ai_analyzer()

    if not analyzer.is_available():
        return {
            "ai_available": False,
            "provider": None,
            "enhanced_patterns": [],
            "additional_questions": []
        }

    enhanced = []
    for pattern in patterns[:3]:  # Limiter à 3 patterns pour les coûts
        result = analyzer.analyze_pattern(pattern)
        if result.success:
            enhanced.append({
                "pattern_type": pattern.pattern_type.value,
                "ai_analysis": result.analysis,
                "ai_recommendations": result.recommendations,
                "ai_confidence": result.confidence
            })

    additional_questions = analyzer.enhance_questions(patterns, questions)

    return {
        "ai_available": True,
        "provider": analyzer.get_available_provider(),
        "enhanced_patterns": enhanced,
        "additional_questions": [q.to_dict() for q in additional_questions]
    }
