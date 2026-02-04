# GL Normalizer

## Overview
GL Normalizer is a web application for analyzing and normalizing P&L (Profit & Loss) statements. It helps identify and neutralize accounting artifacts like unjustified provisions and inflated/deflated budgets to calculate the true operational run rate.

## Running the Application
The web application runs on port 5000 using FastAPI + Uvicorn:
```bash
python main.py
```

## Project Structure
```
main.py                  # FastAPI web application
templates/               # Jinja2 HTML templates
  ├── base.html          # Base layout
  ├── upload.html        # File upload form
  └── results.html       # Analysis results dashboard
static/
  └── style.css          # Application styles

gl_normalizer/           # Core Python library
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
- fastapi, uvicorn, jinja2 - Web framework
- pandas, numpy - Data manipulation
- polars - High-performance data manipulation (Crystal analysis)
- numba - JIT compilation for numerical calculations
- openpyxl - Excel file handling
- scipy, scikit-learn - Statistical analysis
- xgboost - AI features

## Performance Optimizations (Feb 2026)
- **Polars**: Crystal analysis uses Polars for data transformation (x5-9 speedup)
- **Numba JIT**: Shannon entropy calculations use @njit compilation (x170 speedup)
- **itertuples**: GLEntry creation uses itertuples instead of iterrows (x13 speedup)
- **Graceful fallback**: Automatic fallback to pandas if Polars operations fail

## Web Application Features
1. Upload Excel files (GL data)
2. Single-year analysis or year-over-year comparison
3. Dashboard showing run rate, anomalies, and regularizations
4. Excel report download

## API Endpoints
- `GET /` - Upload form
- `POST /analyze` - Run analysis on uploaded files
- `GET /results/{job_id}` - View analysis results
- `GET /report/{job_id}` - Download Excel report

## Supported Formats
- Sage, Cegid, Quadratus, EBP
- Generic Excel exports

## Requirements
- Python 3.12+
- Monthly accounting data (required for pattern analysis)
