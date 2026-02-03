"""
Tests d'intégration GL Normalizer v2
====================================

Test rapide pour vérifier que l'implémentation fonctionne.
"""

import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gl_normalizer_v2.gl_loader import GLLoader, GLFormat
from gl_normalizer_v2.layer1_reading import (
    JournalClassifier,
    JournalType,
    PCGClassifier,
    ABTDetector,
    ProvisionMatcher,
)
from gl_normalizer_v2.layer2_passage import PassageTableBuilder
from gl_normalizer_v2.layer3_alerts import AlertGenerator


def create_test_gl() -> pd.DataFrame:
    """Crée un GL de test avec patterns réalistes."""
    np.random.seed(42)

    entries = []
    year = 2024

    # 1. Achats mensuels récurrents (601)
    for month in range(1, 13):
        for _ in range(20):
            entries.append({
                "compte": "601000",
                "date": datetime(year, month, 15),
                "libelle": "Achat matières premières",
                "journal": "ACH",
                "debit": np.random.uniform(5000, 15000),
                "credit": 0,
            })

    # 2. Salaires mensuels (641)
    for month in range(1, 13):
        # Moins en août (congés)
        base = 40000 if month != 8 else 25000
        entries.append({
            "compte": "641000",
            "date": datetime(year, month, 28),
            "libelle": "Salaires du mois",
            "journal": "SAL",
            "debit": base + np.random.uniform(-2000, 2000),
            "credit": 0,
        })

    # 3. Ventes mensuelles (706)
    for month in range(1, 13):
        for _ in range(15):
            entries.append({
                "compte": "706000",
                "date": datetime(year, month, 20),
                "libelle": "Vente produits finis",
                "journal": "VTE",
                "debit": 0,
                "credit": np.random.uniform(10000, 30000),
            })

    # 4. ABT CFE (488) - provision mensuelle + contrepassation décembre
    for month in range(1, 12):  # Jan-Nov: provisions
        entries.append({
            "compte": "488100",
            "date": datetime(year, month, 1),
            "libelle": "ABT CFE mensuel",
            "journal": "OD",
            "debit": 5000,
            "credit": 0,
        })
    # Décembre: contrepassation + charge réelle
    entries.append({
        "compte": "488100",
        "date": datetime(year, 12, 31),
        "libelle": "Contrepassation ABT CFE",
        "journal": "OD",
        "debit": 0,
        "credit": 55000,  # 5000 × 11
    })
    entries.append({
        "compte": "635000",
        "date": datetime(year, 12, 31),
        "libelle": "CFE 2024",
        "journal": "OD",
        "debit": 52000,  # Charge réelle
        "credit": 0,
    })

    # 5. IS en décembre uniquement (695)
    entries.append({
        "compte": "695000",
        "date": datetime(year, 12, 31),
        "libelle": "IS exercice 2024",
        "journal": "OD",
        "debit": 150000,
        "credit": 0,
    })

    # 6. Provision prud'hommes non budgétée (6815)
    entries.append({
        "compte": "6815000",
        "date": datetime(year, 12, 15),
        "libelle": "Provision prud'hommes Dupont",
        "journal": "OD",
        "debit": 25000,
        "credit": 0,
    })

    # 7. Amortissements mensuels (681)
    for month in range(1, 13):
        entries.append({
            "compte": "681100",
            "date": datetime(year, month, 28),
            "libelle": "Dotation amortissements",
            "journal": "OD",
            "debit": 8000,
            "credit": 0,
        })

    # Créer le DataFrame
    df = pd.DataFrame(entries)
    df["mois"] = df["date"].dt.month
    df["annee"] = df["date"].dt.year
    df["montant"] = df["debit"] - df["credit"]

    return df


def test_journal_classifier():
    """Test JournalClassifier."""
    print("\n" + "=" * 50)
    print("TEST: JournalClassifier")
    print("=" * 50)

    classifier = JournalClassifier()

    # Tests de classification
    assert classifier.classify("OD") == JournalType.OD
    assert classifier.classify("SAL") == JournalType.PAIE
    assert classifier.classify("VTE") == JournalType.VENTE
    assert classifier.classify("ACH") == JournalType.ACHAT
    print("✓ Classification des codes journaux OK")

    # Test sur GL
    df = create_test_gl()
    analysis = classifier.analyze(df)

    print(f"✓ {len(analysis.journals)} journaux analysés")
    print(f"✓ Journaux OD: {analysis.od_journals}")
    print(f"✓ Spike décembre OD: {analysis.od_december_spike}")


def test_pcg_classifier():
    """Test PCGClassifier."""
    print("\n" + "=" * 50)
    print("TEST: PCGClassifier")
    print("=" * 50)

    pcg = PCGClassifier()

    # Test comptes
    info_601 = pcg.classify("601000")
    assert info_601.classe == 6
    assert info_601.nature.value == "charge"
    print(f"✓ 601000: {info_601.libelle}")

    info_695 = pcg.classify("695000")
    assert info_695.is_is == True
    print(f"✓ 695000: IS={info_695.is_is}")

    info_6815 = pcg.classify("6815000")
    assert info_6815.is_provision == True
    print(f"✓ 6815000: Provision={info_6815.is_provision}")

    info_488 = pcg.classify("488100")
    assert info_488.is_abt_candidate == True
    print(f"✓ 488100: ABT candidate={info_488.is_abt_candidate}")


def test_abt_detector():
    """Test ABTDetector."""
    print("\n" + "=" * 50)
    print("TEST: ABTDetector")
    print("=" * 50)

    df = create_test_gl()
    detector = ABTDetector()

    abts = detector.detect(df)
    print(f"✓ {len(abts)} comptes 488 trouvés")

    valid_abts = detector.get_valid_abts(df)
    print(f"✓ {len(valid_abts)} ABT valides (soldent à ~0)")

    for abt in valid_abts:
        print(f"  - {abt.compte}: {abt.objet}, solde={abt.solde_annuel:,.0f}€")
        assert abs(abt.solde_annuel) < abt.mouvement_total * 0.1


def test_provision_matcher():
    """Test ProvisionMatcher."""
    print("\n" + "=" * 50)
    print("TEST: ProvisionMatcher")
    print("=" * 50)

    df = create_test_gl()
    matcher = ProvisionMatcher()

    couples = matcher.match(df)
    print(f"✓ {len(couples)} couples dotation/reprise trouvés")

    summary = matcher.get_summary(df)
    print(f"✓ Total dotations: {summary['total_dotations']:,.0f}€")
    print(f"✓ Total reprises: {summary['total_reprises']:,.0f}€")
    print(f"✓ Net: {summary['total_net']:,.0f}€")


def test_passage_table_builder():
    """Test PassageTableBuilder."""
    print("\n" + "=" * 50)
    print("TEST: PassageTableBuilder")
    print("=" * 50)

    df = create_test_gl()
    builder = PassageTableBuilder()

    # Build annual
    annual = builder.build_annual(df)
    print(f"✓ Résultat brut: {annual.resultat_brut:,.0f}€")
    print(f"✓ Résultat normalisé: {annual.resultat_normalise:,.0f}€")
    print(f"✓ Écart: {annual.ecart_resultat_pct:+.1f}%")

    # Run rate
    run_rate = builder.compute_run_rate(df)
    print(f"✓ Run rate charges brut: {run_rate.charges_brut_mensuel:,.0f}€/mois")
    print(f"✓ Run rate charges normalisé: {run_rate.charges_normalise_mensuel:,.0f}€/mois")

    # Afficher le tableau texte
    print("\n" + builder.get_passage_table_text(df))


def test_alert_generator():
    """Test AlertGenerator."""
    print("\n" + "=" * 50)
    print("TEST: AlertGenerator")
    print("=" * 50)

    df = create_test_gl()
    generator = AlertGenerator()

    alerts = generator.generate(df)
    print(f"✓ {len(alerts)} alertes générées")

    for alert in alerts:
        print(f"  [{alert.priorite}] {alert.type.value}: {alert.compte} - {alert.montant:,.0f}€")

    # Vérifier qu'il y a une alerte pour la provision prud'hommes
    prov_alerts = [a for a in alerts if "6815" in a.compte]
    print(f"✓ Alerte provision prud'hommes: {'OUI' if prov_alerts else 'NON'}")


def test_full_pipeline():
    """Test du pipeline complet."""
    print("\n" + "=" * 50)
    print("TEST: Pipeline complet")
    print("=" * 50)

    df = create_test_gl()

    # Pipeline
    from gl_normalizer_v2.output import ExcelReporter

    reporter = ExcelReporter()
    report = reporter.generate_text_report(df)

    print("\n" + "=" * 50)
    print("RAPPORT COMPLET")
    print("=" * 50)
    print(report)


if __name__ == "__main__":
    print("=" * 60)
    print("GL NORMALIZER v2 - TESTS D'INTÉGRATION")
    print("=" * 60)

    test_journal_classifier()
    test_pcg_classifier()
    test_abt_detector()
    test_provision_matcher()
    test_passage_table_builder()
    test_alert_generator()
    test_full_pipeline()

    print("\n" + "=" * 60)
    print("✓ TOUS LES TESTS PASSÉS")
    print("=" * 60)
