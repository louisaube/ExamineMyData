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

__version__ = "1.0.0"
__author__ = "GL Normalizer Team"

# API publique principale
from .loader import GLLoader, load_gl, load_multiple_gl
from .classifier import GLClassifier, classify_gl
from .pnl_normalizer import (
    PnLNormalizer,
    normalize_pnl,
    NormalizedPLResult,
    ProvisionAnalysis,
    AnomalyDetection,
)
from .comparator import GLComparator, compare_years, YearComparison
from .drilldown import VariationDrilldown, AccountDrilldown, VariationBridge
from .reporter import (
    ExcelReporter,
    TextReporter,
    generate_excel_report,
    generate_text_report,
)
from .config import NormalizerConfig, EntryType

# Exports publics
__all__ = [
    # Version
    "__version__",
    # Loader
    "GLLoader",
    "load_gl",
    "load_multiple_gl",
    # Classifier
    "GLClassifier",
    "classify_gl",
    # PnL Normalizer
    "PnLNormalizer",
    "normalize_pnl",
    "NormalizedPLResult",
    "ProvisionAnalysis",
    "AnomalyDetection",
    # Comparator
    "GLComparator",
    "compare_years",
    "YearComparison",
    # Drilldown
    "VariationDrilldown",
    "AccountDrilldown",
    "VariationBridge",
    # Reporter
    "ExcelReporter",
    "TextReporter",
    "generate_excel_report",
    "generate_text_report",
    # Config
    "NormalizerConfig",
    "EntryType",
]
