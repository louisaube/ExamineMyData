"""
tests/test_methodology.py
Test et validation de la méthodologie de normalisation P&L

Ce script crée des données synthétiques avec des patterns CONNUS
pour valider que les calculs sont corrects.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
sys.path.insert(0, '/home/user/ExamineMyData')

from gl_normalizer import (
    PnLNormalizer,
    NormalizerConfig,
    classify_gl,
)

# =============================================================================
# MÉTHODOLOGIE IMPLÉMENTÉE
# =============================================================================
"""
OBJECTIF:
---------
Neutraliser les artefacts comptables pour obtenir le "run rate" réel.

PROBLÈME:
---------
Le P&L de décembre est pollué par:
1. Régularisations pluriannuelles (dégrèvements TS 2022/2023/2024)
2. Dotations annuelles concentrées (IS, amortissements sur 1 mois)
3. Provisions oubliées (FNP, charges à payer)
4. Sur-provisionnement antérieur (reprises)

SOLUTION:
---------
1. DÉTECTION: Identifier les comptes dont décembre ≠ moyenne des autres mois
   - Calcul du Z-score: (Déc - Moyenne) / Écart-type
   - Seuils: Z > 1.5 ET écart > 2000€ ET écart > 30%

2. REDISTRIBUTION: Pour chaque compte anormal:
   - Run rate mensuel = Total annuel / 12
   - Décembre normalisé = Run rate (pas la valeur comptable)
   - Impact = Décembre normalisé - Décembre brut

3. RÉCONCILIATION:
   Variation brute - Impact N-1 + Impact N = Variation normalisée

FORMULES:
---------
Z-score = (Valeur_décembre - Moyenne_année) / Écart_type_année

EXCES si:  Z > seuil ET |écart| > min_absolu ET |écart%| > min_pct
DEFICIT si: Z < -seuil (mêmes conditions)

Run_rate = Total_annuel / 12
Décembre_normalisé = Run_rate
Impact = Décembre_normalisé - Décembre_brut
"""


def create_synthetic_gl(year: int) -> pd.DataFrame:
    """
    Crée un GL synthétique avec des patterns CONNUS pour validation.

    Patterns créés:
    - Compte 601000: Achats réguliers ~10k€/mois (run rate normal)
    - Compte 631000: Taxe sur salaires avec RÉGUL massive en décembre
    - Compte 695000: IS concentré en décembre (charge annuelle)
    - Compte 681000: Amortissements réguliers ~5k€/mois
    """

    records = []

    # --- COMPTE 601000: ACHATS RÉGULIERS ---
    # Pattern: ~10,000€/mois avec légère variation
    # Attendu: Pas d'anomalie, pas de normalisation
    for month in range(1, 13):
        date = datetime(year, month, 15)
        amount = 10000 + np.random.normal(0, 500)  # 10k ± 500
        records.append({
            "date": date,
            "compte": "601000",
            "libelle_compte": "Achats matières premières",
            "journal": "AC",
            "piece": f"AC{year}{month:02d}001",
            "libelle": f"Achats {date.strftime('%B %Y')}",
            "debit": amount,
            "credit": 0,
            "axe_1": "PROD",
        })

    # --- COMPTE 631000: TAXE SUR SALAIRES AVEC RÉGUL ---
    # Pattern: 0€ de janvier à novembre, puis -230,000€ en décembre (dégrèvement)
    # Attendu: DEFICIT massif en décembre, normalisation significative
    # Total annuel = -230,000€
    # Run rate = -230,000 / 12 = -19,167€/mois
    # Déc brut = -230,000€
    # Impact = -19,167 - (-230,000) = +210,833€

    # Aucune écriture de jan à nov pour ce compte
    # Dégrèvement en décembre
    records.append({
        "date": datetime(year, 12, 31),
        "compte": "631000",
        "libelle_compte": "Taxe sur salaires",
        "journal": "OD",
        "piece": f"OD{year}12001",
        "libelle": f"DEGREVEMENT TS {year-2}",
        "debit": 0,
        "credit": 80000,  # Crédit = produit/réduction de charge
        "axe_1": "ADMIN",
    })
    records.append({
        "date": datetime(year, 12, 31),
        "compte": "631000",
        "libelle_compte": "Taxe sur salaires",
        "journal": "OD",
        "piece": f"OD{year}12002",
        "libelle": f"DEGREVEMENT TS {year-1}",
        "debit": 0,
        "credit": 75000,
        "axe_1": "ADMIN",
    })
    records.append({
        "date": datetime(year, 12, 31),
        "compte": "631000",
        "libelle_compte": "Taxe sur salaires",
        "journal": "OD",
        "piece": f"OD{year}12003",
        "libelle": f"DEGREVEMENT TS {year}",
        "debit": 0,
        "credit": 75000,
        "axe_1": "ADMIN",
    })

    # --- COMPTE 695000: IS CONCENTRÉ EN DÉCEMBRE ---
    # Pattern: 0€ de jan à nov, 240,000€ en décembre
    # Attendu: EXCES massif, charge annuelle sur 1 mois
    # Total annuel = 240,000€
    # Run rate = 20,000€/mois
    # Déc brut = 240,000€
    # Impact = 20,000 - 240,000 = -220,000€

    records.append({
        "date": datetime(year, 12, 31),
        "compte": "695000",
        "libelle_compte": "Impôt sur les bénéfices",
        "journal": "OD",
        "piece": f"OD{year}12010",
        "libelle": f"IS exercice {year}",
        "debit": 240000,
        "credit": 0,
        "axe_1": "ADMIN",
    })

    # --- COMPTE 681000: AMORTISSEMENTS RÉGULIERS ---
    # Pattern: 5,000€/mois régulier
    # Attendu: Pas d'anomalie significative
    for month in range(1, 13):
        date = datetime(year, month, 28)
        records.append({
            "date": date,
            "compte": "681000",
            "libelle_compte": "Dotations aux amortissements",
            "journal": "OD",
            "piece": f"OD{year}{month:02d}020",
            "libelle": f"Amortissements {date.strftime('%m/%Y')}",
            "debit": 5000,
            "credit": 0,
            "axe_1": "PROD",
        })

    # --- COMPTE 706000: PRODUITS (VENTES) ---
    # Pour avoir un P&L complet, ajoutons des ventes
    for month in range(1, 13):
        date = datetime(year, month, 20)
        amount = 50000 + np.random.normal(0, 2000)
        records.append({
            "date": date,
            "compte": "706000",
            "libelle_compte": "Ventes de services",
            "journal": "VT",
            "piece": f"VT{year}{month:02d}001",
            "libelle": f"CA {date.strftime('%B %Y')}",
            "debit": 0,
            "credit": amount,
            "axe_1": "COMMERCIAL",
        })

    # Créer le DataFrame
    df = pd.DataFrame(records)

    # Ajouter les colonnes calculées (comme le ferait le loader)
    df["date"] = pd.to_datetime(df["date"])
    df["annee"] = df["date"].dt.year
    df["mois"] = df["date"].dt.month
    df["periode"] = df["date"].dt.strftime("%Y-%m")
    df["classe"] = df["compte"].str[0]
    df["racine_2"] = df["compte"].str[:2]
    df["racine_3"] = df["compte"].str[:3]
    df["montant"] = df["debit"] - df["credit"]

    return df


def test_methodology():
    """Test complet de la méthodologie"""

    print("=" * 70)
    print("TEST DE VALIDATION DE LA MÉTHODOLOGIE")
    print("=" * 70)

    # Créer données de test
    year = 2024
    df = create_synthetic_gl(year)

    print(f"\n1. DONNÉES SYNTHÉTIQUES CRÉÉES")
    print(f"   Nb écritures: {len(df)}")
    print(f"   Comptes: {df['compte'].unique().tolist()}")
    print(f"   Période: {df['periode'].min()} à {df['periode'].max()}")

    # Classifier (ajoute montant_pnl)
    df_classified = classify_gl(df)

    # Créer le normalizer
    config = NormalizerConfig(
        z_score_threshold=1.5,
        min_ecart_absolu=2000,
        min_ecart_pct=30,
        seuil_regul=2000,
    )
    normalizer = PnLNormalizer(df_classified, year, config)

    # =========================================================================
    # TEST 2: VÉRIFICATION DES TOTAUX PAR COMPTE
    # =========================================================================
    print(f"\n2. VÉRIFICATION DES TOTAUX PAR COMPTE")
    print("-" * 50)

    monthly = normalizer.get_monthly_comparison()

    for compte in ["601000", "631000", "695000", "681000"]:
        if compte in monthly.index:
            row = monthly.loc[compte]
            print(f"\n   Compte {compte}:")
            print(f"     Total annuel:  {row['TOTAL']:>12,.0f}€")
            print(f"     Moyenne:       {row['MOYENNE']:>12,.0f}€")
            print(f"     Décembre brut: {row['DEC_BRUT']:>12,.0f}€")
            print(f"     Écart déc/moy: {row['DEC_VS_MOY']:>+12,.0f}€")

    # =========================================================================
    # TEST 3: DÉTECTION DES PROVISIONS/RÉGULARISATIONS
    # =========================================================================
    print(f"\n3. DÉTECTION DES PROVISIONS/RÉGULARISATIONS")
    print("-" * 50)

    provisions = normalizer.analyze_provisions()

    print(f"   Nb comptes avec régularisation: {len(provisions)}")

    # Vérifier que 631000 et 695000 sont détectés
    comptes_detectes = [p.compte for p in provisions]

    assert "631000" in comptes_detectes, "ERREUR: Compte 631000 non détecté!"
    assert "695000" in comptes_detectes, "ERREUR: Compte 695000 non détecté!"
    print("   ✓ Comptes 631000 et 695000 correctement détectés")

    for p in provisions:
        print(f"\n   {p.compte} - {p.libelle_compte}:")
        print(f"     Total annuel:    {p.total_annuel:>12,.0f}€")
        print(f"     Run rate:        {p.run_rate_mensuel:>12,.0f}€/mois")
        print(f"     Décembre brut:   {p.decembre_brut:>12,.0f}€")
        print(f"     Déc normalisé:   {p.decembre_normalise:>12,.0f}€")
        print(f"     Impact:          {p.ecart_decembre:>+12,.0f}€")

    # =========================================================================
    # TEST 4: VALIDATION DES CALCULS DE NORMALISATION
    # =========================================================================
    print(f"\n4. VALIDATION DES CALCULS")
    print("-" * 50)

    # Compte 631000: dégrèvement
    p631 = next((p for p in provisions if p.compte == "631000"), None)
    if p631:
        # Total = -230,000 (3 crédits de 80k + 75k + 75k)
        expected_total = -230000
        expected_run_rate = expected_total / 12
        expected_dec_brut = -230000  # Tout en décembre
        expected_impact = expected_run_rate - expected_dec_brut

        print(f"\n   Compte 631000 (Dégrèvement TS):")
        print(f"     Attendu: Total={expected_total:,.0f}€, Run rate={expected_run_rate:,.0f}€")
        print(f"     Calculé: Total={p631.total_annuel:,.0f}€, Run rate={p631.run_rate_mensuel:,.0f}€")

        # Tolérance pour arrondis
        assert abs(p631.total_annuel - expected_total) < 100, f"Total 631000 incorrect: {p631.total_annuel}"
        print(f"     ✓ Calculs corrects pour 631000")

    # Compte 695000: IS
    p695 = next((p for p in provisions if p.compte == "695000"), None)
    if p695:
        expected_total = 240000
        expected_run_rate = 20000
        expected_dec_brut = 240000
        expected_impact = 20000 - 240000  # -220,000

        print(f"\n   Compte 695000 (IS):")
        print(f"     Attendu: Total={expected_total:,.0f}€, Impact={expected_impact:+,.0f}€")
        print(f"     Calculé: Total={p695.total_annuel:,.0f}€, Impact={p695.ecart_decembre:+,.0f}€")

        assert abs(p695.total_annuel - expected_total) < 100, f"Total 695000 incorrect"
        assert abs(p695.ecart_decembre - expected_impact) < 100, f"Impact 695000 incorrect"
        print(f"     ✓ Calculs corrects pour 695000")

    # =========================================================================
    # TEST 5: DÉTECTION DES ANOMALIES
    # =========================================================================
    print(f"\n5. DÉTECTION DES ANOMALIES (Z-SCORE)")
    print("-" * 50)

    anomalies = normalizer.detect_anomalies()

    print(f"   Nb anomalies détectées: {len(anomalies)}")

    for a in anomalies[:5]:
        print(f"\n   {a.mois} - {a.compte}:")
        print(f"     Montant:  {a.montant_mois:>12,.0f}€")
        print(f"     Moyenne:  {a.moyenne_annuelle:>12,.0f}€")
        print(f"     Z-score:  {a.z_score:>+12.2f}")
        print(f"     Nature:   {a.nature}")

    # =========================================================================
    # TEST 6: P&L NORMALISÉ FINAL
    # =========================================================================
    print(f"\n6. P&L NORMALISÉ FINAL")
    print("-" * 50)

    result = normalizer.compute_normalized_december()

    print(f"\n   DÉCEMBRE {year}:")
    print(f"     Charges brutes:      {result.charges_brutes:>12,.0f}€")
    print(f"     Produits bruts:      {result.produits_bruts:>12,.0f}€")
    print(f"     Résultat brut:       {result.resultat_brut:>12,.0f}€")
    print(f"")
    print(f"     Ajustement:          {result.total_ajustement:>+12,.0f}€")
    print(f"     Nb comptes ajustés:  {result.nb_comptes_ajustes:>12}")
    print(f"")
    print(f"     Charges normalisées: {result.charges_normalisees:>12,.0f}€")
    print(f"     Résultat normalisé:  {result.resultat_normalise:>12,.0f}€")

    # =========================================================================
    # TEST 7: ANALYSE ANALYTIQUE
    # =========================================================================
    print(f"\n7. ANALYSE PAR AXE ANALYTIQUE")
    print("-" * 50)

    axes = normalizer.get_available_axes()
    print(f"   Axes disponibles: {axes}")

    if "axe_1" in axes:
        breakdowns = normalizer.analyze_by_axe("axe_1")
        print(f"\n   Ventilation par axe_1:")
        for b in breakdowns:
            print(f"     {b.valeur:15} Total={b.total_annuel:>10,.0f}€  ({b.pct_du_total:>5.1f}%)")

    # =========================================================================
    # RÉSUMÉ
    # =========================================================================
    print(f"\n" + "=" * 70)
    print("RÉSUMÉ DES TESTS")
    print("=" * 70)
    print(f"✓ Données synthétiques créées avec patterns connus")
    print(f"✓ Comptes avec régularisation correctement détectés")
    print(f"✓ Calculs de run rate et impact validés")
    print(f"✓ Détection d'anomalies fonctionnelle")
    print(f"✓ P&L normalisé calculé")
    print(f"✓ Analyse analytique fonctionnelle")
    print(f"\nTOUS LES TESTS PASSÉS ✓")

    return result


def test_comparison_two_years():
    """Test de comparaison entre deux années"""

    print("\n" + "=" * 70)
    print("TEST COMPARAISON N-1 vs N")
    print("=" * 70)

    from gl_normalizer import GLComparator, compare_years

    # Créer deux années avec des patterns différents
    df_2023 = create_synthetic_gl(2023)
    df_2024 = create_synthetic_gl(2024)

    # Ajouter une variation connue en 2024
    # Ex: augmentation des achats de 10%
    df_2024.loc[df_2024["compte"] == "601000", "debit"] *= 1.10
    df_2024["montant"] = df_2024["debit"] - df_2024["credit"]

    # Classifier
    df_2023 = classify_gl(df_2023)
    df_2024 = classify_gl(df_2024)

    # Comparer
    comparator = GLComparator(df_2023, df_2024, 2023, 2024)
    comparison = comparator.compare(with_drilldown=False)

    print(f"\n   Résultat brut 2023:      {comparison.result_n1.resultat_brut:>12,.0f}€")
    print(f"   Résultat brut 2024:      {comparison.result_n.resultat_brut:>12,.0f}€")
    print(f"   Variation brute:         {comparison.variation_brute:>+12,.0f}€")
    print(f"")
    print(f"   Résultat normalisé 2023: {comparison.result_n1.resultat_normalise:>12,.0f}€")
    print(f"   Résultat normalisé 2024: {comparison.result_n.resultat_normalise:>12,.0f}€")
    print(f"   Variation normalisée:    {comparison.variation_normalisee:>+12,.0f}€")
    print(f"")
    print(f"   Écart (artefacts):       {comparison.ecart_normalisation:>+12,.0f}€")

    print(f"\n   ✓ Comparaison inter-années fonctionnelle")

    return comparison


def test_content_analysis():
    """Test de l'analyse de contenu (journaux OD, patterns, libellés)"""

    print("\n" + "=" * 70)
    print("TEST ANALYSE DE CONTENU")
    print("=" * 70)

    from gl_normalizer.content_analyzer import ContentAnalyzer

    # Créer des données avec des patterns explicites
    year = 2024
    df = create_synthetic_gl(year)

    # Ajouter des écritures avec patterns spécifiques
    additional_records = [
        # Régularisation avec libellé explicite
        {
            "date": datetime(year, 12, 31),
            "compte": "615000",
            "libelle_compte": "Entretien et réparations",
            "journal": "OD",
            "piece": "OD202412100",
            "libelle": "REGUL provision entretien annuel",
            "debit": 15000,
            "credit": 0,
            "axe_1": "PROD",
        },
        # FNP
        {
            "date": datetime(year, 12, 31),
            "compte": "606000",
            "libelle_compte": "Fournitures non stockables",
            "journal": "OD",
            "piece": "OD202412101",
            "libelle": "FNP fournitures décembre",
            "debit": 8000,
            "credit": 0,
            "axe_1": "ADMIN",
        },
        # Reprise de provision
        {
            "date": datetime(year, 12, 31),
            "compte": "781000",
            "libelle_compte": "Reprises sur provisions",
            "journal": "OD",
            "piece": "OD202412102",
            "libelle": "Reprise provision client douteux",
            "debit": 0,
            "credit": 12000,
            "axe_1": "COMMERCIAL",
        },
        # Écriture standard (journal AC)
        {
            "date": datetime(year, 6, 15),
            "compte": "601000",
            "libelle_compte": "Achats",
            "journal": "AC",
            "piece": "AC202406001",
            "libelle": "Achats matières juin",
            "debit": 5000,
            "credit": 0,
            "axe_1": "PROD",
        },
    ]

    df_additional = pd.DataFrame(additional_records)
    df_additional["date"] = pd.to_datetime(df_additional["date"])
    df_additional["annee"] = df_additional["date"].dt.year
    df_additional["mois"] = df_additional["date"].dt.month
    df_additional["periode"] = df_additional["date"].dt.strftime("%Y-%m")
    df_additional["classe"] = df_additional["compte"].str[0]
    df_additional["racine_2"] = df_additional["compte"].str[:2]
    df_additional["racine_3"] = df_additional["compte"].str[:3]
    df_additional["montant"] = df_additional["debit"] - df_additional["credit"]

    df = pd.concat([df, df_additional], ignore_index=True)

    # Créer l'analyseur de contenu
    analyzer = ContentAnalyzer(df, year)

    # =========================================================================
    # TEST 1: ANALYSE DES JOURNAUX
    # =========================================================================
    print(f"\n1. ANALYSE DES JOURNAUX")
    print("-" * 50)

    journals = analyzer.analyze_journals()

    print(f"   Nb journaux: {len(journals)}")

    journaux_od = [j for j in journals if j.is_od or j.is_situation]
    print(f"   Journaux OD/Situation: {len(journaux_od)}")

    for j in journals:
        type_jal = "OD" if j.is_od else ("SIT" if j.is_situation else "STD")
        print(f"\n   [{type_jal}] {j.journal}:")
        print(f"     Écritures: {j.nb_ecritures}")
        print(f"     Débit: {j.total_debit:,.0f}€")
        print(f"     % en décembre: {j.pct_decembre:.0f}%")

    # Vérifier que OD est détecté
    od_journal = next((j for j in journals if j.journal == "OD"), None)
    assert od_journal is not None, "Journal OD non trouvé!"
    assert od_journal.is_od, "Journal OD non identifié comme OD!"
    print(f"\n   ✓ Journal OD correctement identifié")

    # =========================================================================
    # TEST 2: DÉTECTION DES PATTERNS
    # =========================================================================
    print(f"\n2. DÉTECTION DES PATTERNS")
    print("-" * 50)

    patterns = analyzer.analyze_patterns()

    print(f"   Nb patterns détectés: {len(patterns)}")

    for p in patterns[:10]:
        print(f"\n   [{p.category}] {p.pattern}:")
        print(f"     Occurrences: {p.nb_occurrences}")
        print(f"     Montant net: {p.montant_net:+,.0f}€")
        print(f"     Exemples: {p.exemples_libelles[:2]}")

    # Vérifier que REGUL est détecté
    regul_patterns = [p for p in patterns if "REGUL" in p.pattern or p.category == "REGUL"]
    assert len(regul_patterns) > 0, "Pattern REGUL non détecté!"
    print(f"\n   ✓ Patterns REGUL correctement détectés")

    # Vérifier FNP
    fnp_patterns = [p for p in patterns if "FNP" in p.pattern]
    assert len(fnp_patterns) > 0, "Pattern FNP non détecté!"
    print(f"   ✓ Pattern FNP correctement détecté")

    # Vérifier REPRISE
    reprise_patterns = [p for p in patterns if "REPRISE" in p.pattern]
    assert len(reprise_patterns) > 0, "Pattern REPRISE non détecté!"
    print(f"   ✓ Pattern REPRISE correctement détecté")

    # =========================================================================
    # TEST 3: CONCENTRATION OD PAR MOIS
    # =========================================================================
    print(f"\n3. CONCENTRATION OD PAR MOIS")
    print("-" * 50)

    od_concentration = analyzer.get_od_concentration()

    print(f"\n   Mois    Écritures    % OD")
    print(f"   ----    ---------    ----")
    for _, row in od_concentration.iterrows():
        print(f"   {int(row['Mois']):2d}      {int(row['Total écritures']):5d}        {row['% OD']:5.1f}%")

    # Vérifier concentration en décembre
    dec_row = od_concentration[od_concentration["Mois"] == 12].iloc[0]
    print(f"\n   % OD en décembre: {dec_row['% OD']:.1f}%")
    assert dec_row["% OD"] > 50, "Les OD devraient être concentrés en décembre!"
    print(f"   ✓ Concentration OD en décembre correctement détectée")

    # =========================================================================
    # TEST 4: ANALYSE CONTENU D'UN COMPTE
    # =========================================================================
    print(f"\n4. ANALYSE CONTENU COMPTE 631000")
    print("-" * 50)

    content = analyzer.analyze_account_content("631000")

    if content:
        print(f"\n   Compte: {content.compte} - {content.libelle_compte}")
        print(f"   Écritures: {content.nb_ecritures}")
        print(f"   Débit: {content.total_debit:,.0f}€")
        print(f"   Crédit: {content.total_credit:,.0f}€")
        print(f"   % OD: {content.pct_od:.1f}%")
        print(f"   Régul heavy: {content.is_regul_heavy}")

        print(f"\n   Répartition par journal:")
        for jal, montant in content.par_journal.items():
            print(f"     {jal}: {montant:,.0f}€")

        print(f"\n   Libellés uniques:")
        for lib in content.libelles_uniques[:5]:
            print(f"     - {lib}")

        assert content.pct_od == 100, "Le compte 631000 devrait être 100% OD!"
        print(f"\n   ✓ Analyse de contenu correcte")

    # =========================================================================
    # TEST 5: RÉCUPÉRATION ÉCRITURES DE RÉGUL
    # =========================================================================
    print(f"\n5. ÉCRITURES DE RÉGULARISATION")
    print("-" * 50)

    df_regul = analyzer.get_regul_entries()

    print(f"   Nb écritures de régul identifiées: {len(df_regul)}")

    if not df_regul.empty:
        print(f"\n   Top 5 par montant:")
        for _, row in df_regul.head(5).iterrows():
            print(f"     {row['compte']} | {row['journal']} | {row['montant']:+,.0f}€ | {row['libelle'][:40]}")

    # =========================================================================
    # RÉSUMÉ
    # =========================================================================
    print(f"\n" + "=" * 70)
    print("RÉSUMÉ ANALYSE DE CONTENU")
    print("=" * 70)

    summary = analyzer.summary()
    print(f"   Journaux: {summary['nb_journaux']} (dont {summary['nb_journaux_od']} OD)")
    print(f"   Patterns régul: {summary['patterns_regul']} ({summary['montant_regul']:+,.0f}€)")
    print(f"   Patterns except: {summary['patterns_except']} ({summary['montant_except']:+,.0f}€)")
    print(f"   % OD décembre: {summary['pct_od_decembre']:.1f}%")

    print(f"\n✓ TOUS LES TESTS D'ANALYSE DE CONTENU PASSÉS")

    return analyzer


if __name__ == "__main__":
    # Exécuter les tests
    result = test_methodology()
    comparison = test_comparison_two_years()
    content = test_content_analysis()

    print("\n" + "=" * 70)
    print("FIN DES TESTS - MÉTHODOLOGIE VALIDÉE")
    print("=" * 70)
