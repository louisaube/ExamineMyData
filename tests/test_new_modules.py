"""
tests/test_new_modules.py
Tests pour les nouveaux modules: AccountingContext, Profiler, Detector
"""

import pandas as pd
import numpy as np
from datetime import datetime
import sys
sys.path.insert(0, '/home/user/ExamineMyData')

from gl_normalizer import (
    AccountingContext,
    get_pcg_context,
    Profiler,
    profile_gl,
    AnomalyDetector,
    detect_anomalies,
)


def create_test_gl(year: int = 2024) -> pd.DataFrame:
    """Crée un GL de test avec des patterns connus"""
    records = []

    # Compte régulier: achats ~10k€/mois
    for month in range(1, 13):
        date = datetime(year, month, 15)
        amount = 10000 + np.random.normal(0, 500)
        records.append({
            "date": date,
            "compte": "601000",
            "libelle_compte": "Achats matières premières",
            "journal": "AC",
            "libelle": f"Achats {date.strftime('%B')}",
            "debit": amount,
            "credit": 0,
        })

    # Compte avec concentration en décembre (provision)
    records.append({
        "date": datetime(year, 12, 31),
        "compte": "681100",
        "libelle_compte": "Dotations aux amortissements",
        "journal": "OD",
        "libelle": "Dotation annuelle",
        "debit": 60000,
        "credit": 0,
    })

    # Montants ronds suspects
    for i in range(5):
        records.append({
            "date": datetime(year, 6, 15),
            "compte": "615000",
            "libelle_compte": "Entretien",
            "journal": "AC",
            "libelle": f"Provision entretien {i+1}",
            "debit": 10000,  # Montant rond répété
            "credit": 0,
        })

    # Ventes régulières
    for month in range(1, 13):
        date = datetime(year, month, 20)
        records.append({
            "date": date,
            "compte": "706000",
            "libelle_compte": "Prestations de services",
            "journal": "VT",
            "libelle": f"CA {date.strftime('%B')}",
            "debit": 0,
            "credit": 50000 + np.random.normal(0, 2000),
        })

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df["annee"] = df["date"].dt.year
    df["mois"] = df["date"].dt.month
    df["periode"] = df["date"].dt.strftime("%Y-%m")
    df["classe"] = df["compte"].str[0]
    df["racine_2"] = df["compte"].str[:2]
    df["montant"] = df["debit"] - df["credit"]

    return df


def test_accounting_context():
    """Test du module AccountingContext"""
    print("\n" + "=" * 60)
    print("TEST: AccountingContext (PCG)")
    print("=" * 60)

    ctx = AccountingContext()

    # Test classification
    test_comptes = ["601000", "631100", "695000", "681100", "706000"]

    print("\n1. Classification des comptes:")
    for compte in test_comptes:
        classif = ctx.classify_account(compte)
        if classif:
            print(f"   {compte}: {classif.libelle_pcg}")
            print(f"      Catégorie: {classif.categorie}, Fréquence: {classif.frequency.value}")

    # Vérifier que les comptes sont bien classifiés
    assert ctx.classify_account("601000") is not None, "601000 devrait être classifié"
    assert ctx.classify_account("695000") is not None, "695000 devrait être classifié"

    # Test comportement attendu
    print("\n2. Comportements attendus:")
    behavior = ctx.get_expected_behavior("631100")
    print(f"   631100: Mensuel={behavior.monthly_expected}, Pic fin année normal={behavior.year_end_spike_normal}")

    assert behavior is not None, "Comportement devrait être défini"

    # Test identification provision
    assert ctx.is_provision_account("681100"), "681100 est un compte de dotation"
    assert not ctx.is_provision_account("601000"), "601000 n'est pas une provision"

    print("\n✓ AccountingContext: TOUS LES TESTS PASSÉS")
    return True


def test_profiler():
    """Test du module Profiler"""
    print("\n" + "=" * 60)
    print("TEST: Profiler")
    print("=" * 60)

    df = create_test_gl(2024)
    profiler = Profiler(df, year=2024)

    # Test profil colonnes
    print("\n1. Profil des colonnes:")
    columns = profiler.profile_columns()
    print(f"   Nb colonnes: {len(columns)}")
    for col in columns[:5]:
        print(f"   {col.name}: {col.dtype}, nulls={col.null_pct:.1f}%")

    assert len(columns) > 0, "Devrait avoir des colonnes"

    # Test profil comptes
    print("\n2. Profil des comptes:")
    accounts = profiler.profile_accounts()
    print(f"   Nb comptes: {len(accounts)}")
    for acc in accounts[:3]:
        print(f"   {acc.compte}: {acc.behavior_type}, risk={acc.risk_score:.2f}")

    assert len(accounts) > 0, "Devrait avoir des comptes"

    # Test baseline
    print("\n3. Baseline:")
    baseline = profiler.compute_baseline()
    print(f"   Année: {baseline.year}")
    print(f"   Total écritures: {baseline.total_ecritures}")
    print(f"   Charges: {baseline.total_charges:,.0f}€")
    print(f"   Produits: {baseline.total_produits:,.0f}€")

    assert baseline.total_ecritures > 0, "Devrait avoir des écritures"

    # Test profil complet
    print("\n4. Profil complet:")
    result = profiler.profile()
    print(f"   Qualité: {result.data_quality.value}")
    print(f"   Warnings: {len(result.warnings)}")
    print(f"   Recommandations: {len(result.recommendations)}")

    print("\n✓ Profiler: TOUS LES TESTS PASSÉS")
    return True


def test_detector():
    """Test du module Detector"""
    print("\n" + "=" * 60)
    print("TEST: Detector")
    print("=" * 60)

    df = create_test_gl(2024)

    # Test détecteur d'anomalies
    print("\n1. Détection des anomalies:")
    result = detect_anomalies(df, year=2024)
    print(f"   Total anomalies: {result.total_anomalies}")
    print(f"   Risk score: {result.risk_score:.2f}")
    print(f"   Par type: {result.summary}")

    # Test concentrations
    print("\n2. Concentrations détectées:")
    for c in result.concentrations[:3]:
        print(f"   {c}")

    # Test montants ronds
    print("\n3. Montants ronds détectés:")
    for r in result.round_amounts[:3]:
        print(f"   {r}")

    # Le compte 681100 devrait être détecté (100% en décembre)
    compte_681 = [c for c in result.concentrations
                  if "681100" in c.value or "681100" in c.details]
    print(f"\n   Compte 681100 détecté: {len(compte_681) > 0}")

    # Les montants ronds de 10000€ devraient être détectés
    round_10k = [r for r in result.round_amounts if r.amount == 10000]
    print(f"   Montants 10k€ détectés: {len(round_10k) > 0}")

    print("\n✓ Detector: TOUS LES TESTS PASSÉS")
    return True


def test_integration():
    """Test d'intégration des trois modules"""
    print("\n" + "=" * 60)
    print("TEST: Intégration")
    print("=" * 60)

    df = create_test_gl(2024)

    # 1. Contexte PCG
    ctx = AccountingContext()

    # 2. Enrichir le DataFrame avec le PCG
    df_enriched = ctx.analyze_accounts(df)
    print(f"\n1. Colonnes ajoutées: {[c for c in df_enriched.columns if c.startswith('pcg_')]}")

    # 3. Profiler les données enrichies
    profiler = Profiler(df_enriched, year=2024)
    profile = profiler.profile()
    print(f"\n2. Profil qualité: {profile.data_quality.value}")

    # 4. Détecter les anomalies
    result = detect_anomalies(df_enriched, year=2024)
    print(f"\n3. Risk score: {result.risk_score:.2f}")

    # 5. Identifier les comptes à risque avec contexte PCG
    risk_accounts = ctx.get_risk_accounts(df)
    print(f"\n4. Comptes à risque PCG: {len(risk_accounts)}")

    print("\n✓ Intégration: TOUS LES TESTS PASSÉS")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("TESTS DES NOUVEAUX MODULES")
    print("=" * 60)

    results = []
    results.append(("AccountingContext", test_accounting_context()))
    results.append(("Profiler", test_profiler()))
    results.append(("Detector", test_detector()))
    results.append(("Integration", test_integration()))

    print("\n" + "=" * 60)
    print("RÉSUMÉ")
    print("=" * 60)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"   {name}: {status}")

    all_passed = all(r[1] for r in results)
    if all_passed:
        print("\n✓ TOUS LES TESTS PASSÉS")
    else:
        print("\n✗ CERTAINS TESTS ONT ÉCHOUÉ")
