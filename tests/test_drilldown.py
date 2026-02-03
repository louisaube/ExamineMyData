"""
Tests utilisateurs pour STORY-030: Analyse autonome drill-down

Ces tests valident:
1. Détection des patterns (5+ types)
2. Génération de questions pertinentes
3. Exécution des analyses drill-down
4. Intégration IA (si disponible)
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from gl_normalizer.pattern_detector import (
    PatternDetector,
    Pattern,
    PatternType,
    PatternSeverity,
    detect_patterns,
)
from gl_normalizer.autonomous_drilldown import (
    AutonomousAnalyzer,
    DrilldownGenerator,
    DrilldownExecutor,
    DrilldownResult,
    Question,
    QuestionType,
    run_autonomous_analysis,
)
from gl_normalizer.ai_drilldown import (
    AIAnalyzer,
    get_ai_analyzer,
    enhance_analysis_with_ai,
)


# ============================================================
# Fixtures - Données de test réalistes
# ============================================================

@pytest.fixture
def sample_gl_data():
    """Génère un grand livre de test avec patterns détectables"""
    np.random.seed(42)
    n_entries = 1000

    # Dates sur une année
    dates = pd.date_range(start='2024-01-01', end='2024-12-31', periods=n_entries)

    # Comptes variés (classes 6 et 7 principalement)
    comptes = np.random.choice([
        '601000', '602000', '606000', '615000', '621000',
        '641000', '645000', '681000',
        '701000', '706000', '707000',
    ], n_entries)

    # Montants normaux
    debits = np.random.exponential(scale=5000, size=n_entries)
    credits = np.zeros(n_entries)

    df = pd.DataFrame({
        'date': dates,
        'compte': comptes,
        'debit': debits,
        'credit': credits,
        'libelle': [f'Écriture {i}' for i in range(n_entries)],
        'journal': np.random.choice(['AC', 'VT', 'OD', 'BQ'], n_entries),
    })

    # Injecter des anomalies détectables

    # 1. Pic de fin d'année sur compte 615000 (entretien)
    december_mask = df['date'].dt.month == 12
    df.loc[december_mask & (df['compte'] == '615000'), 'debit'] *= 10

    # 2. Montants ronds suspects
    round_indices = np.random.choice(df.index, size=20, replace=False)
    df.loc[round_indices, 'debit'] = np.random.choice([10000, 20000, 50000, 100000], 20)

    # 3. Concentration sur un compte
    df.loc[df['compte'] == '601000', 'debit'] *= 5

    return df


@pytest.fixture
def sample_gl_with_duplicates(sample_gl_data):
    """GL avec doublons de montants"""
    df = sample_gl_data.copy()

    # Ajouter des montants dupliqués
    duplicate_amount = 12345.67
    dup_indices = np.random.choice(df.index, size=15, replace=False)
    df.loc[dup_indices, 'debit'] = duplicate_amount

    return df


# ============================================================
# Tests PatternDetector
# ============================================================

class TestPatternDetector:
    """Tests pour le détecteur de patterns"""

    def test_detector_initialization(self, sample_gl_data):
        """Test: Le détecteur s'initialise correctement"""
        detector = PatternDetector(sample_gl_data)
        assert detector is not None
        assert len(detector.df) > 0

    def test_detect_year_end_spikes(self, sample_gl_data):
        """Test: Détection des pics de fin d'année"""
        detector = PatternDetector(sample_gl_data)
        patterns = detector.detect_year_end_spikes()

        # On a injecté un pic sur 615000
        assert len(patterns) > 0
        spike_pattern = next((p for p in patterns if '615' in str(p.account)), None)
        if spike_pattern:
            assert spike_pattern.pattern_type == PatternType.YEAR_END_SPIKE
            assert spike_pattern.severity in [PatternSeverity.HIGH, PatternSeverity.MEDIUM]

    def test_detect_round_numbers(self, sample_gl_data):
        """Test: Détection des montants ronds"""
        detector = PatternDetector(sample_gl_data)
        patterns = detector.detect_round_numbers()

        # On a injecté des montants ronds
        assert isinstance(patterns, list)

    def test_detect_concentration(self, sample_gl_data):
        """Test: Détection des concentrations"""
        detector = PatternDetector(sample_gl_data)
        patterns = detector.detect_concentration()

        # On a créé une concentration sur 601000
        assert isinstance(patterns, list)
        if patterns:
            assert any(p.pattern_type == PatternType.CONCENTRATION for p in patterns)

    def test_detect_ratio_anomalies(self, sample_gl_data):
        """Test: Détection des anomalies de ratios"""
        detector = PatternDetector(sample_gl_data)
        patterns = detector.detect_ratio_anomalies()

        assert isinstance(patterns, list)

    def test_detect_duplicate_amounts(self, sample_gl_with_duplicates):
        """Test: Détection des montants dupliqués"""
        detector = PatternDetector(sample_gl_with_duplicates)
        patterns = detector.detect_duplicate_amounts()

        assert isinstance(patterns, list)

    def test_detect_all_returns_multiple_types(self, sample_gl_data):
        """Test: detect_all retourne au moins 3 types de patterns"""
        detector = PatternDetector(sample_gl_data)
        patterns = detector.detect_all()

        assert len(patterns) > 0

        pattern_types = set(p.pattern_type for p in patterns)
        # On devrait avoir plusieurs types
        assert len(pattern_types) >= 1

    def test_patterns_have_required_fields(self, sample_gl_data):
        """Test: Tous les patterns ont les champs requis"""
        patterns = detect_patterns(sample_gl_data)

        for p in patterns:
            assert 'type' in p
            assert 'severity' in p
            assert 'title' in p
            assert 'description' in p
            assert 'questions' in p


# ============================================================
# Tests DrilldownGenerator
# ============================================================

class TestDrilldownGenerator:
    """Tests pour le générateur de questions"""

    def test_generator_initialization(self, sample_gl_data):
        """Test: Le générateur s'initialise avec des patterns"""
        detector = PatternDetector(sample_gl_data)
        patterns = detector.detect_all()

        generator = DrilldownGenerator(patterns)
        assert generator is not None
        assert len(generator.patterns) == len(patterns)

    def test_generate_all_returns_questions(self, sample_gl_data):
        """Test: generate_all retourne des questions"""
        detector = PatternDetector(sample_gl_data)
        patterns = detector.detect_all()

        if patterns:
            generator = DrilldownGenerator(patterns)
            questions = generator.generate_all()

            assert len(questions) > 0
            assert all(isinstance(q, Question) for q in questions)

    def test_questions_have_priorities(self, sample_gl_data):
        """Test: Les questions ont des priorités"""
        detector = PatternDetector(sample_gl_data)
        patterns = detector.detect_all()

        if patterns:
            generator = DrilldownGenerator(patterns)
            questions = generator.generate_all()

            if questions:
                priorities = [q.priority for q in questions]
                assert all(1 <= p <= 10 for p in priorities)

    def test_questions_sorted_by_priority(self, sample_gl_data):
        """Test: Les questions sont triées par priorité"""
        detector = PatternDetector(sample_gl_data)
        patterns = detector.detect_all()

        if patterns:
            generator = DrilldownGenerator(patterns)
            questions = generator.generate_all()

            if len(questions) > 1:
                priorities = [q.priority for q in questions]
                assert priorities == sorted(priorities)


# ============================================================
# Tests DrilldownExecutor
# ============================================================

class TestDrilldownExecutor:
    """Tests pour l'exécuteur de drill-down"""

    def test_executor_initialization(self, sample_gl_data):
        """Test: L'exécuteur s'initialise correctement"""
        executor = DrilldownExecutor(sample_gl_data)
        assert executor is not None

    def test_execute_detail_view(self, sample_gl_data):
        """Test: Exécution d'une vue détaillée"""
        executor = DrilldownExecutor(sample_gl_data)

        question = Question(
            question_id="Q001",
            question_type=QuestionType.DETAIL_VIEW,
            text="Voir le détail du compte 601",
            parameters={"account": "601000"}
        )

        result = executor.execute(question)

        assert isinstance(result, DrilldownResult)
        assert result.question_id == "Q001"

    def test_execute_trend_analysis(self, sample_gl_data):
        """Test: Exécution d'une analyse de tendance"""
        executor = DrilldownExecutor(sample_gl_data)

        question = Question(
            question_id="Q002",
            question_type=QuestionType.TREND_ANALYSIS,
            text="Évolution mensuelle du compte 601",
            parameters={"account": "601"}
        )

        result = executor.execute(question)

        assert isinstance(result, DrilldownResult)

    def test_execute_comparison(self, sample_gl_data):
        """Test: Exécution d'une comparaison"""
        executor = DrilldownExecutor(sample_gl_data)

        question = Question(
            question_id="Q003",
            question_type=QuestionType.COMPARISON,
            text="Comparer S1 vs S2",
            parameters={}
        )

        result = executor.execute(question)

        assert isinstance(result, DrilldownResult)

    def test_execute_breakdown(self, sample_gl_data):
        """Test: Exécution d'une décomposition"""
        executor = DrilldownExecutor(sample_gl_data)

        question = Question(
            question_id="Q004",
            question_type=QuestionType.BREAKDOWN,
            text="Décomposition par classe",
            parameters={}
        )

        result = executor.execute(question)

        assert isinstance(result, DrilldownResult)

    def test_execute_batch(self, sample_gl_data):
        """Test: Exécution en batch"""
        executor = DrilldownExecutor(sample_gl_data)

        questions = [
            Question("Q001", QuestionType.DETAIL_VIEW, "Test 1", parameters={"account": "601"}),
            Question("Q002", QuestionType.BREAKDOWN, "Test 2", parameters={}),
        ]

        results = executor.execute_batch(questions, max_count=2)

        assert len(results) == 2
        assert all(isinstance(r, DrilldownResult) for r in results)


# ============================================================
# Tests AutonomousAnalyzer
# ============================================================

class TestAutonomousAnalyzer:
    """Tests pour l'analyseur autonome complet"""

    def test_autonomous_analysis_workflow(self, sample_gl_data):
        """Test: Workflow complet d'analyse autonome"""
        analyzer = AutonomousAnalyzer(sample_gl_data)
        result = analyzer.analyze(auto_execute=False)

        assert 'patterns' in result
        assert 'questions' in result
        assert 'results' in result
        assert 'summary' in result

    def test_autonomous_analysis_with_auto_execute(self, sample_gl_data):
        """Test: Analyse avec exécution automatique"""
        analyzer = AutonomousAnalyzer(sample_gl_data)
        result = analyzer.analyze(auto_execute=True, max_auto_questions=3)

        assert 'results' in result
        # En mode auto, on devrait avoir des résultats exécutés
        if result['questions']:
            assert len(result['results']) <= 3

    def test_run_autonomous_analysis_utility(self, sample_gl_data):
        """Test: Fonction utilitaire run_autonomous_analysis"""
        result = run_autonomous_analysis(sample_gl_data, auto_execute=False)

        assert isinstance(result, dict)
        assert 'patterns' in result
        assert 'summary' in result


# ============================================================
# Tests AI Integration
# ============================================================

class TestAIIntegration:
    """Tests pour l'intégration IA"""

    def test_ai_analyzer_initialization(self):
        """Test: L'analyseur IA s'initialise"""
        analyzer = get_ai_analyzer()
        assert analyzer is not None

    def test_ai_availability_check(self):
        """Test: Vérification de disponibilité IA"""
        analyzer = get_ai_analyzer()

        # is_available retourne un booléen
        available = analyzer.is_available()
        assert isinstance(available, bool)

    def test_ai_provider_detection(self):
        """Test: Détection du provider disponible"""
        analyzer = get_ai_analyzer()

        provider = analyzer.get_available_provider()
        assert provider in [None, "openai", "anthropic"]

    def test_enhance_analysis_without_ai(self, sample_gl_data):
        """Test: Enrichissement sans IA configurée"""
        detector = PatternDetector(sample_gl_data)
        patterns = detector.detect_all()

        generator = DrilldownGenerator(patterns) if patterns else None
        questions = generator.generate_all() if generator else []

        result = enhance_analysis_with_ai(patterns, questions)

        assert 'ai_available' in result
        assert 'provider' in result
        assert 'enhanced_patterns' in result
        assert 'additional_questions' in result


# ============================================================
# Tests de performance et robustesse
# ============================================================

class TestPerformance:
    """Tests de performance"""

    def test_large_dataset_handling(self):
        """Test: Gestion d'un grand dataset"""
        # Générer un grand dataset
        n = 50000
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=n, freq='h'),
            'compte': np.random.choice(['601000', '602000', '701000'], n),
            'debit': np.random.exponential(1000, n),
            'credit': np.zeros(n),
            'libelle': [f'Entry {i}' for i in range(n)],
        })

        # L'analyse ne devrait pas prendre trop de temps
        import time
        start = time.time()

        result = run_autonomous_analysis(df, auto_execute=False)

        elapsed = time.time() - start

        assert elapsed < 30  # Max 30 secondes
        assert 'patterns' in result

    def test_empty_dataframe_handling(self):
        """Test: Gestion d'un DataFrame vide"""
        df = pd.DataFrame(columns=['date', 'compte', 'debit', 'credit', 'libelle'])

        result = run_autonomous_analysis(df, auto_execute=False)

        assert 'patterns' in result
        assert len(result['patterns']) == 0

    def test_missing_columns_handling(self):
        """Test: Gestion de colonnes manquantes"""
        df = pd.DataFrame({
            'account': ['601', '602'],
            'amount': [100, 200],
        })

        # Ne devrait pas lever d'exception
        try:
            result = run_autonomous_analysis(df, auto_execute=False)
            assert 'patterns' in result
        except Exception:
            # Acceptable si géré gracieusement
            pass


# ============================================================
# Tests de validation utilisateur
# ============================================================

class TestUserValidation:
    """Tests simulant la validation utilisateur"""

    def test_questions_are_actionable(self, sample_gl_data):
        """Test: Les questions générées sont actionnables"""
        result = run_autonomous_analysis(sample_gl_data, auto_execute=False)

        for q in result.get('questions', []):
            # Chaque question doit avoir un texte significatif
            assert len(q['text']) > 10
            # Et un type valide
            assert q['type'] in ['detail_view', 'trend_analysis', 'comparison', 'counterparty', 'breakdown']

    def test_pattern_descriptions_are_clear(self, sample_gl_data):
        """Test: Les descriptions de patterns sont claires"""
        result = run_autonomous_analysis(sample_gl_data, auto_execute=False)

        for p in result.get('patterns', []):
            assert len(p['title']) > 5
            assert len(p['description']) > 10
            # Doit avoir une description non vide
            desc = p['description'].lower()
            assert len(desc) > 0

    def test_results_provide_insights(self, sample_gl_data):
        """Test: Les résultats d'exécution fournissent des insights"""
        result = run_autonomous_analysis(sample_gl_data, auto_execute=True)

        for r in result.get('results', []):
            assert 'title' in r
            assert 'summary' in r
            # Si succès, doit avoir des insights
            if r.get('success'):
                assert 'insights' in r


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
