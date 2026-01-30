"""
GL Normalizer - AI Module
========================

Advanced AI-powered anomaly detection and risk scoring.

Modules:
- benford: Benford's Law analysis
- isolation_forest: Isolation Forest anomaly detection
- autoencoder: Deep learning anomaly detection (requires PyTorch)
- nlp_analyzer: NLP-based label analysis
- xgboost_scorer: XGBoost risk classification (requires XGBoost)
- risk_scorer: Combined multi-model risk scoring
"""

import warnings

# Core modules (always available with scikit-learn)
from .benford import BenfordAnalyzer, analyze_benford
from .isolation_forest import IsolationForestDetector, detect_anomalies_iforest
from .nlp_analyzer import NLPAnalyzer, analyze_labels

__all__ = [
    # Benford
    "BenfordAnalyzer",
    "analyze_benford",
    # Isolation Forest
    "IsolationForestDetector",
    "detect_anomalies_iforest",
    # NLP
    "NLPAnalyzer",
    "analyze_labels",
]

# Optional: Autoencoder (requires PyTorch)
try:
    from .autoencoder import AutoencoderDetector, detect_anomalies_autoencoder
    __all__.extend(["AutoencoderDetector", "detect_anomalies_autoencoder"])
    AUTOENCODER_AVAILABLE = True
except ImportError:
    AutoencoderDetector = None
    detect_anomalies_autoencoder = None
    AUTOENCODER_AVAILABLE = False

# Optional: XGBoost
try:
    from .xgboost_scorer import XGBoostScorer, train_fraud_detector
    __all__.extend(["XGBoostScorer", "train_fraud_detector"])
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBoostScorer = None
    train_fraud_detector = None
    XGBOOST_AVAILABLE = False

# Risk Scorer (works with whatever is available)
from .risk_scorer import RiskScorer, calculate_risk_scores
__all__.extend(["RiskScorer", "calculate_risk_scores"])

# Export availability flags
__all__.extend(["AUTOENCODER_AVAILABLE", "XGBOOST_AVAILABLE"])
