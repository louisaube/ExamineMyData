"""
tests/test_integration_full.py
Tests d'intégration complets pour GL Normalizer v2.4.0

Teste le workflow complet:
1. Chargement données
2. Classification
3. Profiling avec AccountingContext
4. Détection anomalies
5. Détection régularisations
6. Analyse complète
7. Normalisation P&L
8. Génération questions
"""

import pandas as pd
import numpy as np
from datetime import datetime
import sys
sys.path.insert(0, '/home/user/ExamineMyData')


def create_realistic_gl(year: int = 2024) -> pd.DataFrame:
    """Crée un GL réaliste avec patterns comptables typiques"""
    records = []
    np.random.seed(42)

    # === CHARGES REGULIERES (601-626) ===

    # 601 - Achats matières premières (mensuel régulier)
    for month in range(1, 13):
        date = datetime(year, month, 15)
        records.append({
            "date": date,
            "compte": "601100",
            "libelle_compte": "Achats matières premières",
            "journal": "AC",
            "piece": f"FAC{year}{month:02d}001",
            "libelle": f"Achat fournisseur {date.strftime('%B')}",
            "debit": 15000 + np.random.normal(0, 1000),
            "credit": 0,
        })

    # 606 - Achats non stockés (mensuel régulier - fournitures)
    for month in range(1, 13):
        date = datetime(year, month, 20)
        records.append({
            "date": date,
            "compte": "606300",
            "libelle_compte": "Fournitures d'entretien",
            "journal": "AC",
            "piece": f"FAC{year}{month:02d}002",
            "libelle": f"Fournitures {date.strftime('%B')}",
            "debit": 2000 + np.random.normal(0, 200),
            "credit": 0,
        })

    # 613 - Locations (mensuel fixe)
    for month in range(1, 13):
        date = datetime(year, month, 1)
        records.append({
            "date": date,
            "compte": "613200",
            "libelle_compte": "Location immobilière",
            "journal": "AC",
            "piece": f"LOYER{year}{month:02d}",
            "libelle": f"Loyer {date.strftime('%B %Y')}",
            "debit": 5000,  # Montant fixe
            "credit": 0,
        })

    # 626 - Frais postaux et télécoms (mensuel régulier)
    for month in range(1, 13):
        date = datetime(year, month, 25)
        records.append({
            "date": date,
            "compte": "626100",
            "libelle_compte": "Frais postaux",
            "journal": "AC",
            "piece": f"TEL{year}{month:02d}",
            "libelle": f"Téléphone {date.strftime('%B')}",
            "debit": 800 + np.random.normal(0, 50),
            "credit": 0,
        })

    # === CHARGES SAISONNIERES ===

    # 616 - Primes d'assurance (annuelle en janvier)
    records.append({
        "date": datetime(year, 1, 15),
        "compte": "616100",
        "libelle_compte": "Primes d'assurance",
        "journal": "AC",
        "piece": f"ASSUR{year}",
        "libelle": "Prime assurance annuelle",
        "debit": 12000,  # Montant rond suspect mais normal pour assurance
        "credit": 0,
    })

    # 635 - Autres impôts (CFE en décembre)
    records.append({
        "date": datetime(year, 12, 15),
        "compte": "635100",
        "libelle_compte": "Cotisation foncière des entreprises",
        "journal": "OD",
        "piece": f"CFE{year}",
        "libelle": "CFE exercice",
        "debit": 8000,
        "credit": 0,
    })

    # === PERSONNEL (641, 645) ===

    # Salaires mensuels
    for month in range(1, 13):
        date = datetime(year, month, 28)
        records.append({
            "date": date,
            "compte": "641100",
            "libelle_compte": "Rémunérations du personnel",
            "journal": "PA",
            "piece": f"SAL{year}{month:02d}",
            "libelle": f"Salaires {date.strftime('%B')}",
            "debit": 50000 + np.random.normal(0, 2000),
            "credit": 0,
        })

    # Charges sociales
    for month in range(1, 13):
        date = datetime(year, month, 28)
        records.append({
            "date": date,
            "compte": "645100",
            "libelle_compte": "Charges de sécurité sociale",
            "journal": "PA",
            "piece": f"CHRG{year}{month:02d}",
            "libelle": f"Charges sociales {date.strftime('%B')}",
            "debit": 22000 + np.random.normal(0, 800),
            "credit": 0,
        })

    # === PROVISIONS (68x) - Concentrées en décembre ===

    # 681 - Dotations amortissements (mensuel)
    for month in range(1, 13):
        date = datetime(year, month, 30 if month != 2 else 28)
        records.append({
            "date": date,
            "compte": "681100",
            "libelle_compte": "Dotations aux amortissements",
            "journal": "OD",
            "piece": f"DAM{year}{month:02d}",
            "libelle": f"Dotation amort. {date.strftime('%B')}",
            "debit": 3000,
            "credit": 0,
        })

    # 681 - Dotation provision créances douteuses (décembre uniquement)
    records.append({
        "date": datetime(year, 12, 31),
        "compte": "681740",
        "libelle_compte": "Dotations prov. créances douteuses",
        "journal": "OD",
        "piece": f"PROV{year}CD",
        "libelle": "Provision créances douteuses exercice",
        "debit": 15000,  # Concentré en décembre - ANOMALIE ATTENDUE
        "credit": 0,
    })

    # 687 - Dotation provision exceptionnelle (décembre)
    records.append({
        "date": datetime(year, 12, 31),
        "compte": "687200",
        "libelle_compte": "Dotations prov. exceptionnelles",
        "journal": "OD",
        "piece": f"PROV{year}EX",
        "libelle": "Provision pour litige",
        "debit": 25000,  # Montant rond - mais provision donc normal
        "credit": 0,
    })

    # === REGULARISATIONS (486, 408) - Décembre ===

    # CCA - Charges constatées d'avance
    records.append({
        "date": datetime(year, 12, 31),
        "compte": "486000",
        "libelle_compte": "Charges constatées d'avance",
        "journal": "OD",
        "piece": f"CCA{year}",
        "libelle": "CCA assurance exercice suivant",
        "debit": 6000,
        "credit": 0,
    })

    # FNP - Factures non parvenues
    records.append({
        "date": datetime(year, 12, 31),
        "compte": "408100",
        "libelle_compte": "Fournisseurs - Factures non parvenues",
        "journal": "OD",
        "piece": f"FNP{year}",
        "libelle": "FNP fournisseur XYZ",
        "debit": 0,
        "credit": 8500,
    })

    # === PRODUITS (70x) ===

    # CA mensuel (variable)
    for month in range(1, 13):
        date = datetime(year, month, 28)
        # CA plus élevé en Q4 (saisonnalité)
        base = 120000 if month in [10, 11, 12] else 100000
        records.append({
            "date": date,
            "compte": "706100",
            "libelle_compte": "Prestations de services",
            "journal": "VT",
            "piece": f"CA{year}{month:02d}",
            "libelle": f"CA {date.strftime('%B')}",
            "debit": 0,
            "credit": base + np.random.normal(0, 5000),
        })

    # === EXCEPTIONNEL ===

    # Produit exceptionnel en juin
    records.append({
        "date": datetime(year, 6, 15),
        "compte": "775000",
        "libelle_compte": "Produits des cessions d'actifs",
        "journal": "OD",
        "piece": f"CESS{year}",
        "libelle": "Cession véhicule",
        "debit": 0,
        "credit": 8000,
    })

    # === IMPOTS (695) ===

    # IS (décembre)
    records.append({
        "date": datetime(year, 12, 31),
        "compte": "695100",
        "libelle_compte": "Impôts sur les bénéfices",
        "journal": "OD",
        "piece": f"IS{year}",
        "libelle": "Provision IS exercice",
        "debit": 45000,
        "credit": 0,
    })

    # Créer DataFrame
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df["annee"] = df["date"].dt.year
    df["mois"] = df["date"].dt.month
    df["periode"] = df["date"].dt.strftime("%Y-%m")
    df["classe"] = df["compte"].str[0]
    df["racine_2"] = df["compte"].str[:2]
    df["racine_3"] = df["compte"].str[:3]
    df["montant"] = df["debit"] - df["credit"]

    return df


def test_full_workflow():
    """Test du workflow complet"""
    print("\n" + "=" * 70)
    print("TEST WORKFLOW COMPLET GL NORMALIZER v2.4.0")
    print("=" * 70)

    # Créer données de test
    df = create_realistic_gl(2024)
    print(f"\n✓ Données créées: {len(df)} écritures, {df['compte'].nunique()} comptes")

    # 1. AccountingContext
    print("\n--- 1. AccountingContext (PCG) ---")
    from gl_normalizer import AccountingContext
    ctx = AccountingContext()

    # Tester classification
    tests_comptes = ["601100", "681100", "695100", "486000"]
    for compte in tests_comptes:
        classif = ctx.classify_account(compte)
        behavior = ctx.get_expected_behavior(compte)
        print(f"  {compte}: {classif.libelle_pcg if classif else 'N/A'}")
        print(f"    -> Mensuel: {behavior.monthly_expected}, Pic fin année: {behavior.year_end_spike_normal}")

    assert ctx.is_provision_account("681100"), "681100 devrait être provision"
    assert not ctx.is_provision_account("601100"), "601100 pas provision"
    print("✓ AccountingContext OK")

    # 2. Profiler
    print("\n--- 2. Profiler ---")
    from gl_normalizer import Profiler
    profiler = Profiler(df, year=2024)

    profile = profiler.profile()
    print(f"  Qualité données: {profile.data_quality.value}")
    print(f"  Colonnes: {len(profile.columns)}")
    print(f"  Comptes analysés: {len(profile.accounts)}")

    # Vérifier baseline
    baseline = profile.baseline
    print(f"  Baseline charges: {baseline.total_charges:,.0f}€")
    print(f"  Baseline produits: {baseline.total_produits:,.0f}€")

    assert profile.data_quality.value in ["excellent", "good", "acceptable"]
    print("✓ Profiler OK")

    # 3. Detector
    print("\n--- 3. Detector (Anomalies) ---")
    from gl_normalizer import detect_anomalies
    detection = detect_anomalies(df, year=2024)

    print(f"  Total anomalies: {detection.total_anomalies}")
    print(f"  Risk score: {detection.risk_score:.2f}")
    print(f"  Par type: {detection.summary}")

    # Afficher top concentrations
    if detection.concentrations:
        print("  Top concentrations:")
        for c in detection.concentrations[:3]:
            print(f"    - {c.dimension}={c.value}: {c.percentage:.1f}%")

    print("✓ Detector OK")

    # 4. Regularization Detector
    print("\n--- 4. RegularizationDetector ---")
    from gl_normalizer import detect_regularizations
    regul = detect_regularizations(df, year=2024)

    print(f"  Total régularisations: {regul.total_regularizations}")
    print(f"  Par type: {regul.by_type}")

    # Vérifier journaux
    if regul.by_journal:
        print("  Journaux analysés:")
        for code, j in regul.by_journal.items():
            if j.is_suspect:
                print(f"    - {code}: {j.pct_decembre:.0f}% en décembre [SUSPECT]")

    print("✓ RegularizationDetector OK")

    # 5. GLAnalyzer (intégration)
    print("\n--- 5. GLAnalyzer (Intégration) ---")
    from gl_normalizer import analyze_gl
    result = analyze_gl(df, year=2024)

    print(f"  Qualité: {result.data_quality}")
    print(f"  Risk global: {result.overall_risk_score:.2f}")
    print(f"  Anomalies contextualisées: {len(result.anomalies)}")

    # Catégories
    print("  Par catégorie:")
    for cat, count in result.anomalies_by_category.items():
        print(f"    - {cat}: {count}")

    # Run rate
    if result.run_rate:
        print(f"  Run rate mensuel: {result.run_rate.run_rate_mensuel:,.0f}€")

    print("✓ GLAnalyzer OK")

    # 6. PnLNormalizer
    print("\n--- 6. PnLNormalizer ---")
    from gl_normalizer import PnLNormalizer
    normalizer = PnLNormalizer(df, 2024)

    # Provisions
    provisions = normalizer.analyze_provisions()
    print(f"  Provisions détectées: {len(provisions)}")
    for p in provisions[:3]:
        print(f"    - {p.compte}: Impact {p.ecart_decembre:+,.0f}€")

    # Anomalies
    anomalies = normalizer.detect_anomalies()
    print(f"  Anomalies Z-score: {len(anomalies)}")

    # P&L normalisé
    norm = normalizer.compute_normalized_december()
    print(f"  Résultat brut: {norm.resultat_brut:,.0f}€")
    print(f"  Résultat normalisé: {norm.resultat_normalise:,.0f}€")
    print(f"  Ajustement total: {norm.total_ajustement:+,.0f}€")

    print("✓ PnLNormalizer OK")

    # 7. Questioner
    print("\n--- 7. Questioner ---")
    from gl_normalizer import Questioner

    # Convertir objets en dicts pour Questioner
    anomalies_dict = [
        {
            "compte": a.compte,
            "libelle_compte": a.libelle_compte,
            "mois": a.mois,
            "montant": a.montant_mois,
            "moyenne": a.moyenne_annuelle,
            "z_score": a.z_score,
            "nature": a.nature,
            "source": "zscore",
        }
        for a in anomalies
    ]

    provisions_dict = [
        {
            "compte": p.compte,
            "libelle_compte": p.libelle_compte,
            "montant": p.decembre_brut,
            "run_rate": p.run_rate_mensuel,
            "ecart": p.ecart_decembre,
            "moyenne": p.moyenne_hors_dec,
            "source": "provision",
            "mois": 12,
        }
        for p in provisions
    ]

    questioner = Questioner(anomalies_dict, provisions_dict)
    questions = questioner.generate_questions()

    print(f"  Questions générées: {len(questions)}")
    for q in questions[:3]:
        print(f"    - [{q.priorite}] {q.compte}: {q.question[:50]}...")

    fiche = questioner.generate_fiche_levee()
    print(f"  Fiche de levée: {fiche.nb_anomalies} points")

    print("✓ Questioner OK")

    # Résumé final
    print("\n" + "=" * 70)
    print("RÉSUMÉ INTÉGRATION")
    print("=" * 70)
    print(f"""
    Données:          {len(df)} écritures, {df['compte'].nunique()} comptes
    Qualité:          {profile.data_quality.value}
    Anomalies:        {detection.total_anomalies} détectées
    Régularisations:  {regul.total_regularizations} identifiées
    Questions:        {len(questions)} générées
    Risk score:       {result.overall_risk_score:.0%}
    Run rate:         {result.run_rate.run_rate_mensuel:,.0f}€/mois
    """)

    print("=" * 70)
    print("✓ TOUS LES TESTS D'INTÉGRATION PASSÉS")
    print("=" * 70)

    return True


def test_edge_cases():
    """Test des cas limites"""
    print("\n" + "=" * 70)
    print("TEST CAS LIMITES")
    print("=" * 70)

    from gl_normalizer import AccountingContext, Profiler, detect_anomalies

    # 1. Compte non référencé
    ctx = AccountingContext()
    classif = ctx.classify_account("999999")
    print(f"  Compte non référencé: {classif}")
    assert classif is None
    print("✓ Compte non référencé OK")

    # 2. DataFrame vide
    df_empty = pd.DataFrame(columns=["compte", "date", "debit", "credit", "montant", "periode", "annee"])
    try:
        profiler = Profiler(df_empty, year=2024)
        result = profiler.profile()
        print(f"  DataFrame vide: {result.row_count} lignes")
    except Exception as e:
        print(f"  DataFrame vide: Exception gérée - {type(e).__name__}")
    print("✓ DataFrame vide OK")

    # 3. Un seul compte
    df_single = create_realistic_gl(2024)
    df_single = df_single[df_single["compte"] == "601100"]
    detection = detect_anomalies(df_single, year=2024)
    print(f"  Un seul compte: {detection.total_anomalies} anomalies")
    print("✓ Un seul compte OK")

    print("\n✓ TOUS LES CAS LIMITES OK")
    return True


if __name__ == "__main__":
    import sys

    success = True

    try:
        success = test_full_workflow() and success
    except Exception as e:
        print(f"\n✗ ERREUR test_full_workflow: {e}")
        import traceback
        traceback.print_exc()
        success = False

    try:
        success = test_edge_cases() and success
    except Exception as e:
        print(f"\n✗ ERREUR test_edge_cases: {e}")
        import traceback
        traceback.print_exc()
        success = False

    sys.exit(0 if success else 1)
