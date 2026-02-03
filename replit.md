# GL Normalizer

## Overview
GL Normalizer is a Python library for analyzing and normalizing P&L (Profit & Loss) statements. It helps identify and neutralize accounting artifacts like unjustified provisions and inflated/deflated budgets to calculate the true operational run rate.

## Project Structure
```
gl_normalizer/
├── __init__.py          # Public API exports
├── config.py            # Configuration classes
├── loader.py            # GL data loading (multi-format support)
├── classifier.py        # Entry classification
├── pnl_normalizer.py    # Run rate calculation
├── content_analyzer.py  # OD/pattern analysis
├── drilldown.py         # Account-level analysis
├── comparator.py        # Year-over-year comparison
├── reporter.py          # Excel/text report generation
├── questioner.py        # Non-conformity query generation
├── detector.py          # Anomaly detection
├── profiler.py          # Data profiling
├── regularization.py    # Regularization detection
├── analyzer.py          # Full GL analysis
├── security.py          # Security limits and validation
├── secrets_manager.py   # API key management
├── accounting_context.py # French accounting context (PCG)
├── advanced_stats.py    # Statistical analysis methods
└── ai/                  # AI/ML modules
    ├── benford.py       # Benford's Law analysis
    ├── isolation_forest.py
    ├── autoencoder.py   # Deep Learning
    ├── nlp_analyzer.py  # Label analysis
    ├── xgboost_scorer.py
    └── risk_scorer.py   # Combined risk scoring

tests/                   # Test suite
```

## Key Dependencies
- pandas, numpy - Data manipulation
- openpyxl - Excel file handling
- scipy, scikit-learn - Statistical analysis
- Optional: xgboost, torch, sentence-transformers - AI features

## Usage
This is a Python library. Import and use programmatically:

```python
from gl_normalizer import compare_years, generate_excel_report

# Compare two years
comparison = compare_years("GL_2024.xlsx", "GL_2025.xlsx")
print(f"Accounting variation: {comparison.variation_brute:,.0f}€")
print(f"Run rate variation: {comparison.variation_normalisee:,.0f}€")

# Generate Excel report
generate_excel_report(comparison, "analysis_report.xlsx")
```

## Running Tests
```bash
python -m pytest tests/ -v
```

## Supported Formats
- Sage, Cegid, Quadratus, EBP
- Generic Excel exports

## Requirements
- Python 3.9+
- Monthly accounting data (required for pattern analysis)
