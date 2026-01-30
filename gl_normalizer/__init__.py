"""
GL Normalizer - Analyse et normalisation du P&L

Package pour comparer deux périodes comptables en neutralisant les artefacts
comptables (régularisations, provisions) pour obtenir le run rate opérationnel réel.

Usage simple:
    from gl_normalizer import compare_years, generate_excel_report

    comparison = compare_years("GL_2024.xlsx", "GL_2025.xlsx")
    print(f"Variation brute: {comparison.variation_brute:,.0f}€")
    print(f"Variation réelle: {comparison.variation_normalisee:,.0f}€")

    generate_excel_report(comparison, "rapport_normalisation.xlsx")

Validation des headers:
    from gl_normalizer import validate_gl_headers

    validation = validate_gl_headers("mon_gl.xlsx")
    print(validation.summary())  # Affiche le mapping détecté et suggestions

    if not validation.is_valid:
        print(f"Colonnes manquantes: {validation.missing_required}")
        print(f"Suggestions: {validation.suggestions}")

Analyse analytique:
    from gl_normalizer import GLLoader, PnLNormalizer

    loader = GLLoader("GL_2025.xlsx")
    df = loader.load()

    # Voir les axes analytiques disponibles
    print(loader.get_analytical_axes())

    # Analyser par axe
    normalizer = PnLNormalizer(df, 2025)
    for axe in normalizer.get_available_axes():
        breakdowns = normalizer.analyze_by_axe(axe)
        for b in breakdowns[:5]:
            print(f"{b.valeur}: {b.total_annuel:,.0f}€")

Usage avancé:
    from gl_normalizer import GLComparator, GLLoader, PnLNormalizer

    # Charger et comparer
    comparator = GLComparator("GL_2024.xlsx", "GL_2025.xlsx")
    comparison = comparator.compare()

    # Analyser les provisions
    provisions = comparator.normalizer_n.analyze_provisions()
    for p in provisions:
        print(f"{p.compte}: Impact {p.ecart_decembre:+,.0f}€")

    # Drill-down sur un compte
    from gl_normalizer.drilldown import VariationDrilldown
    drilldown = VariationDrilldown(df_2024, df_2025, 2024, 2025)
    analysis = drilldown.analyze_account("631111000")
    print(drilldown.format_drilldown_report(analysis))
"""

__version__ = "2.1.0"
__author__ = "GL Normalizer Team"

# API publique principale
from .loader import (
    GLLoader,
    load_gl,
    load_multiple_gl,
    validate_gl_headers,
    HeaderValidator,
)
from .classifier import GLClassifier, classify_gl
from .pnl_normalizer import (
    PnLNormalizer,
    normalize_pnl,
    NormalizedPLResult,
    ProvisionAnalysis,
    AnomalyDetection,
    AnalyticalBreakdown,
)
from .comparator import GLComparator, compare_years, YearComparison
from .drilldown import VariationDrilldown, AccountDrilldown, VariationBridge
from .content_analyzer import (
    ContentAnalyzer,
    analyze_content,
    JournalAnalysis,
    ContentPattern,
    AccountContent,
)
from .reporter import (
    ExcelReporter,
    TextReporter,
    generate_excel_report,
    generate_text_report,
)
from .questioner import (
    Questioner,
    Question,
    PointLevee,
    FicheLevee,
    AnomalyType,
    ResolutionStatus,
    generate_questions,
    generate_fiche_levee,
)
from .config import (
    NormalizerConfig,
    EntryType,
    HeaderValidation,
    ColumnMapping,
    REQUIRED_COLUMNS,
    OPTIONAL_COLUMNS,
    STANDARD_ANALYTICAL_COLUMNS,
)

# Exports publics
__all__ = [
    # Version
    "__version__",
    # Loader
    "GLLoader",
    "load_gl",
    "load_multiple_gl",
    "validate_gl_headers",
    "HeaderValidator",
    # Classifier
    "GLClassifier",
    "classify_gl",
    # PnL Normalizer
    "PnLNormalizer",
    "normalize_pnl",
    "NormalizedPLResult",
    "ProvisionAnalysis",
    "AnomalyDetection",
    "AnalyticalBreakdown",
    # Comparator
    "GLComparator",
    "compare_years",
    "YearComparison",
    # Drilldown
    "VariationDrilldown",
    "AccountDrilldown",
    "VariationBridge",
    # Content Analyzer
    "ContentAnalyzer",
    "analyze_content",
    "JournalAnalysis",
    "ContentPattern",
    "AccountContent",
    # Reporter
    "ExcelReporter",
    "TextReporter",
    "generate_excel_report",
    "generate_text_report",
    # Questioner (Levée de non-conformité)
    "Questioner",
    "Question",
    "PointLevee",
    "FicheLevee",
    "AnomalyType",
    "ResolutionStatus",
    "generate_questions",
    "generate_fiche_levee",
    # Config
    "NormalizerConfig",
    "EntryType",
    "HeaderValidation",
    "ColumnMapping",
    "REQUIRED_COLUMNS",
    "OPTIONAL_COLUMNS",
    "STANDARD_ANALYTICAL_COLUMNS",
    # AI Module
    "ai",
]

# AI Module - Import conditionnel pour ne pas bloquer si dépendances manquantes
try:
    from . import ai
except ImportError as e:
    import warnings
    warnings.warn(
        f"Module AI non disponible (dépendances manquantes): {e}. "
        "Installez avec: pip install scikit-learn xgboost torch sentence-transformers"
    )
