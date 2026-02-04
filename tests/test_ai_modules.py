"""
Tests pour les modules IA du GL Normalizer
==========================================

Tests de:
- Benford's Law
- Isolation Forest
- Autoencoder
- NLP Analyzer
- XGBoost Scorer
- Risk Scorer combiné
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# Ajouter le chemin parent
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_test_data(n_entries: int = 1000) -> pd.DataFrame:
    """Crée des données de test réalistes"""
    np.random.seed(42)

    # Générer des dates sur une année
    start_date = datetime(2024, 1, 1)
    dates = [start_date + timedelta(days=np.random.randint(0, 365)) for _ in range(n_entries)]

    # Comptes comptables
    comptes = [
        "601000", "602000", "606000", "607000",  # Achats
        "611000", "613000", "615000", "616000",  # Services
        "621000", "622000", "623000", "625000",  # Autres charges
        "631000", "633000", "635000",            # Impôts
        "641000", "645000", "647000",            # Personnel
        "681000", "686000", "687000",            # Dotations
        "701000", "706000", "707000", "708000",  # Ventes
        "781000", "786000", "787000",            # Reprises
    ]

    # Journaux
    journaux = ["AC", "VE", "BQ", "OD", "AN", "SIT"]

    # Libellés
    libelles_normaux = [
        "Achat fournitures bureau",
        "Facture fournisseur",
        "Prestation de service",
        "Honoraires comptables",
        "Frais de déplacement",
        "Vente marchandises",
        "Facture client",
        "Remboursement frais",
    ]

    libelles_suspects = [
        "REGUL erreur saisie",
        "Correction manuel CEO",
        "Ajustement urgent fin année",
        "Override validation directeur",
        "Extourne provision client",
        "FNP facture non parvenue",
    ]

    records = []
    for i in range(n_entries):
        date = dates[i]
        compte = np.random.choice(comptes)

        # 5% d'écritures suspectes
        if np.random.random() < 0.05:
            libelle = np.random.choice(libelles_suspects)
            journal = np.random.choice(["OD", "AN"])
            # Montants ronds pour les suspects
            montant = np.random.choice([1000, 5000, 10000, 50000, 100000])
            if np.random.random() < 0.5:
                montant = -montant
        else:
            libelle = np.random.choice(libelles_normaux)
            journal = np.random.choice(journaux)
            # Montants naturels (suivent approximativement Benford)
            montant = np.random.lognormal(mean=7, sigma=1.5)
            if compte.startswith("7") or compte.startswith("78"):
                montant = -montant  # Produits en crédit

        records.append({
            "date": date,
            "compte": compte,
            "libelle_compte": f"Compte {compte}",
            "journal": journal,
            "piece": f"{journal}{date.strftime('%Y%m')}{i:04d}",
            "libelle": libelle,
            "debit": max(0, montant),
            "credit": max(0, -montant),
            "montant": montant,
        })

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df["mois"] = df["date"].dt.month
    df["annee"] = df["date"].dt.year

    return df


def test_benford():
    """Test de l'analyseur Benford"""
    print("\n" + "=" * 60)
    print("TEST BENFORD'S LAW")
    print("=" * 60)

    from gl_normalizer.ai.benford import BenfordAnalyzer

    df = create_test_data(500)

    analyzer = BenfordAnalyzer(df, amount_column="montant", min_entries=100)
    analysis = analyzer.analyze()

    print(f"\nRésultats:")
    print(f"  - Conformité 1er chiffre: {analysis.conformity_first}")
    print(f"  - MAD: {analysis.mad_first:.4f}")
    print(f"  - Chi² p-value: {analysis.p_value_first:.4f}")

    print(f"\nDistribution 1er chiffre:")
    for r in analysis.first_digit_results:
        flag = "⚠️" if r.is_suspicious else "✓"
        print(f"  {r.digit}: {r.observed_pct:.1f}% (attendu: {r.expected_pct:.1f}%) {flag}")

    # Détection montants ronds
    rounds = analyzer.detect_round_numbers()
    print(f"\nMontants ronds:")
    print(rounds.to_string(index=False))

    print(f"\n✓ Test Benford PASSÉ")
    return analyzer


def test_isolation_forest():
    """Test de l'Isolation Forest"""
    print("\n" + "=" * 60)
    print("TEST ISOLATION FOREST")
    print("=" * 60)

    from gl_normalizer.ai.isolation_forest import IsolationForestDetector

    df = create_test_data(500)

    detector = IsolationForestDetector(df, contamination=0.05)
    detector.fit()

    analysis = detector.analyze()

    print(f"\nRésultats:")
    print(f"  - Écritures totales: {analysis.total_entries}")
    print(f"  - Anomalies détectées: {analysis.nb_anomalies}")
    print(f"  - Taux d'anomalie: {analysis.anomaly_rate:.1%}")

    print(f"\nTop features:")
    for feat, imp in list(analysis.feature_importances.items())[:5]:
        print(f"  - {feat}: {imp:.3f}")

    # Top anomalies
    top = detector.get_top_anomalies(5)
    print(f"\nTop 5 anomalies:")
    for _, row in top.iterrows():
        print(f"  {row['compte']} | {row['journal']} | {row['montant']:+,.0f}€ | {row['libelle'][:30]}")

    print(f"\n✓ Test Isolation Forest PASSÉ")
    return detector


def test_isolation_forest_shap():
    """Test de l'Isolation Forest avec SHAP explainability (Sprint 8)"""
    print("\n" + "=" * 60)
    print("TEST ISOLATION FOREST - SHAP EXPLAINABILITY")
    print("=" * 60)

    from gl_normalizer.ai.isolation_forest import (
        IsolationForestDetector,
        AnomalyExplanation,
        SHAP_AVAILABLE,
    )

    print(f"  SHAP disponible: {SHAP_AVAILABLE}")

    df = create_test_data(300)

    detector = IsolationForestDetector(df, contamination=0.05)
    detector.fit()

    # Test explain_anomaly pour une anomalie spécifique
    anomalies = detector.get_anomalies()
    if len(anomalies) > 0:
        first_anomaly_idx = anomalies.index[0]
        print(f"\nTest explain_anomaly pour index {first_anomaly_idx}:")

        explanation = detector.explain_anomaly(first_anomaly_idx, top_n=3)

        assert explanation is not None, "L'explication ne devrait pas être None"
        assert isinstance(explanation, AnomalyExplanation), "Type incorrect"
        assert explanation.index == first_anomaly_idx, "Index incorrect"
        assert len(explanation.top_features) <= 3, "Trop de features"
        assert explanation.explanation_text, "Texte d'explication vide"
        assert explanation.confidence in ["High", "Medium", "Low"], "Confiance invalide"

        print(f"  Score: {explanation.anomaly_score:.3f}")
        print(f"  Confiance: {explanation.confidence}")
        print(f"  Explication: {explanation.explanation_text}")
        print(f"\n  Top features:")
        for feat, contrib, pct in explanation.top_features:
            print(f"    - {feat}: {contrib:.3f} ({pct:.1f}%)")

        # Test to_dict
        exp_dict = explanation.to_dict()
        assert "index" in exp_dict
        assert "top_features" in exp_dict
        print(f"\n  to_dict(): OK")

    # Test explain_anomalies (batch)
    print(f"\nTest explain_anomalies (batch):")
    explanations = detector.explain_anomalies(top_n=3, max_anomalies=10)
    print(f"  Anomalies expliquées: {len(explanations)}")
    assert len(explanations) <= 10, "Trop d'anomalies retournées"

    # Test get_anomalies_with_explanations
    print(f"\nTest get_anomalies_with_explanations:")
    anomalies_explained = detector.get_anomalies_with_explanations(
        top_n_features=3,
        max_anomalies=10
    )
    print(f"  Colonnes: {list(anomalies_explained.columns)}")
    assert "explanation_text" in anomalies_explained.columns
    assert "confidence" in anomalies_explained.columns
    assert "top_feature_1" in anomalies_explained.columns
    assert "top_feature_1_pct" in anomalies_explained.columns

    if len(anomalies_explained) > 0:
        print(f"\n  Exemple d'anomalie expliquée:")
        row = anomalies_explained.iloc[0]
        print(f"    Score: {row['anomaly_score']:.3f}")
        print(f"    Confiance: {row['confidence']}")
        print(f"    Feature 1: {row['top_feature_1']} ({row['top_feature_1_pct']:.1f}%)")
        print(f"    Explication: {row['explanation_text'][:80]}...")

    # Vérifier le summary inclut shap_available
    summary = detector.summary()
    assert "shap_available" in summary, "shap_available manquant dans summary"
    print(f"\n  summary.shap_available: {summary['shap_available']}")

    print(f"\n✓ Test Isolation Forest SHAP PASSÉ")
    return detector


def test_nlp_analyzer():
    """Test de l'analyseur NLP"""
    print("\n" + "=" * 60)
    print("TEST NLP ANALYZER")
    print("=" * 60)

    from gl_normalizer.ai.nlp_analyzer import NLPAnalyzer

    df = create_test_data(500)

    analyzer = NLPAnalyzer(df, use_embeddings=False)  # TF-IDF pour rapidité
    analyzer.fit(verbose=False)

    analysis = analyzer.analyze()

    print(f"\nRésultats:")
    print(f"  - Écritures totales: {analysis.total_entries}")
    print(f"  - Libellés suspects: {analysis.nb_suspicious}")
    print(f"  - Problèmes de cohérence: {analysis.coherence_issues}")

    print(f"\nMots-clés détectés:")
    stats = analyzer.get_keyword_statistics()
    if not stats.empty:
        for _, row in stats.head(5).iterrows():
            print(f"  - {row['category']}: {row['count']} ({row['percentage']:.1f}%)")

    # Top suspects
    suspects = analyzer.get_suspicious_labels(threshold=30, top_n=5)
    if not suspects.empty:
        print(f"\nTop libellés suspects:")
        for _, row in suspects.iterrows():
            print(f"  Score {row['nlp_risk_score']:.0f}: {row['libelle'][:50]}")

    print(f"\n✓ Test NLP PASSÉ")
    return analyzer


def test_xgboost_scorer():
    """Test du scorer XGBoost"""
    print("\n" + "=" * 60)
    print("TEST XGBOOST SCORER")
    print("=" * 60)

    try:
        from gl_normalizer.ai.xgboost_scorer import XGBoostScorer
    except ImportError as e:
        print(f"  ⚠️ XGBoost non disponible: {e}")
        return None

    df = create_test_data(500)

    scorer = XGBoostScorer(df)
    scorer.fit_auto(verbose=True)

    analysis = scorer.analyze()

    print(f"\nRésultats:")
    print(f"  - Écritures totales: {analysis.total_entries}")
    print(f"  - Haut risque: {analysis.nb_high_risk}")
    print(f"  - Risque moyen: {analysis.nb_medium_risk}")
    print(f"  - Faible risque: {analysis.nb_low_risk}")

    print(f"\nTop features:")
    for feat, imp in list(analysis.feature_importances.items())[:5]:
        print(f"  - {feat}: {imp:.3f}")

    # High risk
    high_risk = scorer.get_high_risk_entries()
    if not high_risk.empty:
        print(f"\nÉcritures à haut risque:")
        for _, row in high_risk.head(3).iterrows():
            print(f"  {row['compte']} | {row['risk_proba']:.2f} | {row['libelle'][:30]}")

    print(f"\n✓ Test XGBoost PASSÉ")
    return scorer


def test_risk_scorer():
    """Test du Risk Scorer combiné"""
    print("\n" + "=" * 60)
    print("TEST RISK SCORER COMBINÉ")
    print("=" * 60)

    from gl_normalizer.ai.risk_scorer import RiskScorer

    df = create_test_data(300)  # Plus petit pour rapidité

    # Test sans autoencoder ni XGBoost pour rapidité
    scorer = RiskScorer(
        df,
        use_autoencoder=False,
        use_xgboost=False,
        verbose=True,
    )
    scorer.fit()

    analysis = scorer.analyze()

    print(f"\nRésultats:")
    print(f"  - Écritures totales: {analysis.total_entries}")
    print(f"  - Score moyen: {analysis.mean_score:.1f}")
    print(f"  - Score médian: {analysis.median_score:.1f}")
    print(f"  - Modèles utilisés: {analysis.models_used}")

    print(f"\nDistribution des risques:")
    for level, count in analysis.risk_distribution.items():
        pct = count / analysis.total_entries * 100
        print(f"  - {level}: {count} ({pct:.1f}%)")

    # Top anomalies
    top = scorer.get_top_anomalies(5)
    print(f"\nTop 5 écritures à risque:")
    for _, row in top.iterrows():
        print(f"  Score {row['final_score']:.0f} | {row['risk_level']} | {row['compte']} | {row['libelle'][:25]}")

    # Explication
    if not top.empty:
        idx = top.index[0]
        explanation = scorer.explain_entry(idx)
        print(f"\nExplication pour l'écriture #{idx}:")
        print(f"  Score final: {explanation['final_score']:.1f}")
        print(f"  Niveau: {explanation['risk_level']}")
        print(f"  Facteur principal: {explanation['top_factor']}")
        if explanation['contributing_factors']:
            print(f"  Facteurs:")
            for f in explanation['contributing_factors']:
                print(f"    - {f}")

    print(f"\n✓ Test Risk Scorer PASSÉ")
    return scorer


def test_full_pipeline():
    """Test du pipeline complet avec tous les modules"""
    print("\n" + "=" * 60)
    print("TEST PIPELINE COMPLET")
    print("=" * 60)

    from gl_normalizer.ai.risk_scorer import RiskScorer, calculate_risk_scores

    df = create_test_data(200)

    print("\nTest fonction utilitaire calculate_risk_scores...")
    results = calculate_risk_scores(df, verbose=False)

    print(f"\nColonnes ajoutées: {[c for c in results.columns if 'score' in c or 'risk' in c]}")
    print(f"Score moyen: {results['final_score'].mean():.1f}")
    print(f"Écritures à risque (>60): {(results['final_score'] > 60).sum()}")

    print(f"\n✓ Test Pipeline PASSÉ")
    return results


if __name__ == "__main__":
    print("=" * 60)
    print("TESTS DES MODULES IA - GL NORMALIZER")
    print("=" * 60)

    # Tests individuels
    test_benford()
    test_isolation_forest()
    test_isolation_forest_shap()  # Sprint 8: SHAP explainability
    test_nlp_analyzer()
    test_xgboost_scorer()
    test_risk_scorer()
    test_full_pipeline()

    print("\n" + "=" * 60)
    print("✓ TOUS LES TESTS IA PASSÉS AVEC SUCCÈS")
    print("=" * 60)
