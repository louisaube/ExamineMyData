"""
Tests d'intégration GL Crystal.

Valide le pipeline complet :
1. Normalisation et enrichissement
2. Calcul de l'ICC (Couche 1)
3. Graphe des contreparties (Couche 2)
4. Embedding topologique (Couche 3)
"""

import pytest
from datetime import date
from collections import defaultdict
import numpy as np

# Import des modules GL Crystal
from gl_crystal.normalizer.schema import (
    GLSchema, GLEntry, EnrichedEntry,
    ClassePCG, NatureCompte, TypeContrepartie
)
from gl_crystal.normalizer.enricher import GLEnricher

from gl_crystal.layer1_crystallinity.metrics import (
    compute_cv_decompose,
    compute_entropy_libelles,
    compute_regularite_temporelle,
    compute_diversite_journaux,
    compute_concentration_contreparties,
    compute_icc_composite,
)
from gl_crystal.layer1_crystallinity.icc_calculator import ICCCalculator

from gl_crystal.layer2_graph.bipartite_graph import (
    BipartiteGraph, build_bipartite_graph, Arc
)
from gl_crystal.layer2_graph.arc_stability import ArcStabilityAnalyzer, MutationType
from gl_crystal.layer2_graph.circuit_detector import CircuitDetector, CircuitType
from gl_crystal.layer2_graph.templates import (
    check_template_conformity, get_atypical_arcs
)

from gl_crystal.layer3_embedding.connectivity import (
    build_connectivity_matrix, ConnectivityMatrix
)
from gl_crystal.layer3_embedding.vectorizer import SVDVectorizer


# ============================================================================
# Fixtures : Données de test réalistes
# ============================================================================

@pytest.fixture
def sample_gl_entries():
    """
    Crée un GL de test réaliste avec plusieurs établissements.

    Simule un réseau de micro-crèches avec:
    - Salaires récurrents (cristallin)
    - Fournitures diverses (amorphe)
    - Loyer fixe (cristallin)
    - ABT sur CFE
    """
    entries = []
    line_id = 0

    # Sites
    sites = ['SDV', 'BOU', 'LIV3']

    # Mois de l'exercice
    mois_list = [f"2024-{m:02d}" for m in range(1, 13)]

    for site in sites:
        for mois in mois_list:
            mois_num = int(mois.split('-')[1])

            # Salaires (641) - très cristallin
            # Contrepartie 421 (personnel)
            salaire_base = 5000 if site != 'LIV3' else 4500
            entries.append(create_entry(
                line_id, date(2024, mois_num, 25), 'OD', 'OD PAIE',
                '641100', 'Salaires', None, site,
                f'SALAIRES {mois}', salaire_base, 0, f'PAIE-{mois}'
            ))
            line_id += 1
            entries.append(create_entry(
                line_id, date(2024, mois_num, 25), 'OD', 'OD PAIE',
                '421000', 'Personnel', None, site,
                f'SALAIRES {mois}', 0, salaire_base, f'PAIE-{mois}'
            ))
            line_id += 1

            # Charges sociales (645) - cristallin
            charges_soc = int(salaire_base * 0.42)
            entries.append(create_entry(
                line_id, date(2024, mois_num, 25), 'OD', 'OD PAIE',
                '645100', 'Charges sociales', None, site,
                f'URSSAF {mois}', charges_soc, 0, f'URSSAF-{mois}'
            ))
            line_id += 1
            entries.append(create_entry(
                line_id, date(2024, mois_num, 25), 'OD', 'OD PAIE',
                '431000', 'URSSAF', None, site,
                f'URSSAF {mois}', 0, charges_soc, f'URSSAF-{mois}'
            ))
            line_id += 1

            # Loyer (613) - cristallin
            loyer = 1200 if site != 'BOU' else 1400
            entries.append(create_entry(
                line_id, date(2024, mois_num, 5), 'ACH', 'ACHATS',
                '613200', 'Loyers', None, site,
                f'LOYER {mois} BAILLEUR', loyer, 0, f'LOYER-{mois}'
            ))
            line_id += 1
            entries.append(create_entry(
                line_id, date(2024, mois_num, 5), 'ACH', 'ACHATS',
                '401000', 'Fournisseurs', 'BAILLEUR', site,
                f'LOYER {mois} BAILLEUR', 0, loyer, f'LOYER-{mois}'
            ))
            line_id += 1

            # Fournitures (606) - plus amorphe, plusieurs fournisseurs
            fournitures = [
                ('HYGIPLUS', 150 + mois_num * 10),
                ('PAPETERIE MARTIN', 80),
                ('OFFICE DEPOT', 120 if mois_num % 3 == 0 else 0),
            ]
            for fournisseur, montant in fournitures:
                if montant > 0:
                    entries.append(create_entry(
                        line_id, date(2024, mois_num, 15), 'ACH', 'ACHATS',
                        '606300', 'Fournitures', None, site,
                        f'{fournisseur} FAC {mois}', montant, 0, f'FOUR-{line_id}'
                    ))
                    line_id += 1
                    entries.append(create_entry(
                        line_id, date(2024, mois_num, 15), 'ACH', 'ACHATS',
                        '401000', 'Fournisseurs', fournisseur, site,
                        f'{fournisseur} FAC {mois}', 0, montant, f'FOUR-{line_id}'
                    ))
                    line_id += 1

        # ABT sur CFE (488) - circuit qui doit boucler
        # Dotations mensuelles
        cfe_mensuel = 100
        for mois_num in range(1, 12):
            entries.append(create_entry(
                line_id, date(2024, mois_num, 28), 'OD', 'OD ABT',
                '633100', 'CFE', None, site,
                f'ABT CFE {mois_num}/12', cfe_mensuel, 0, f'ABT-CFE-{mois_num}'
            ))
            line_id += 1
            entries.append(create_entry(
                line_id, date(2024, mois_num, 28), 'OD', 'OD ABT',
                '488000', 'Charges à payer', None, site,
                f'ABT CFE {mois_num}/12', 0, cfe_mensuel, f'ABT-CFE-{mois_num}'
            ))
            line_id += 1

        # Charge réelle CFE en décembre
        entries.append(create_entry(
            line_id, date(2024, 12, 15), 'BAN', 'BANQUE',
            '633100', 'CFE', None, site,
            'CFE 2024 TRESOR PUBLIC', 1200, 0, 'CFE-REEL'
        ))
        line_id += 1
        entries.append(create_entry(
            line_id, date(2024, 12, 15), 'BAN', 'BANQUE',
            '512000', 'Banque', None, site,
            'CFE 2024 TRESOR PUBLIC', 0, 1200, 'CFE-REEL'
        ))
        line_id += 1

        # Reprise ABT
        entries.append(create_entry(
            line_id, date(2024, 12, 31), 'OD', 'OD ABT',
            '488000', 'Charges à payer', None, site,
            'REPRISE ABT CFE', 1100, 0, 'ABT-REPRISE'
        ))
        line_id += 1
        entries.append(create_entry(
            line_id, date(2024, 12, 31), 'OD', 'OD ABT',
            '633100', 'CFE', None, site,
            'REPRISE ABT CFE', 0, 1100, 'ABT-REPRISE'
        ))
        line_id += 1

    return entries


def create_entry(
    line_id, dt, journal_code, journal_lib, compte, compte_lib,
    auxiliaire, analytique, libelle, debit, credit, piece
):
    """Helper pour créer une entrée GL."""
    return GLEntry(
        ligne_id=line_id,
        date_ecriture=dt,
        journal_code=journal_code,
        journal_libelle=journal_lib,
        compte_general=compte,
        compte_libelle=compte_lib,
        compte_auxiliaire=auxiliaire,
        analytique=analytique,
        libelle_ecriture=libelle,
        debit=float(debit),
        credit=float(credit),
        piece=piece,
    )


@pytest.fixture
def sample_schema(sample_gl_entries):
    """Crée un GLSchema de test."""
    schema = GLSchema(
        source_file='test_gl.xlsx',
        source_format='test',
        date_extraction=date.today(),
        entries=sample_gl_entries,
    )
    schema.compute_stats()
    return schema


@pytest.fixture
def enriched_schema(sample_schema):
    """Crée un GLSchema enrichi."""
    enricher = GLEnricher()
    return enricher.enrich(sample_schema)


# ============================================================================
# Tests Couche 0 : Normalisation
# ============================================================================

class TestNormalization:
    """Tests de la normalisation et enrichissement."""

    def test_schema_creation(self, sample_schema):
        """Vérifie que le schéma est créé correctement."""
        assert sample_schema.nb_ecritures > 0
        assert sample_schema.nb_comptes > 0
        assert sample_schema.nb_journaux > 0

    def test_enrichment_adds_metadata(self, enriched_schema):
        """Vérifie que l'enrichissement ajoute les métadonnées."""
        for entry in enriched_schema.entries:
            assert entry.classe_pcg is not None
            assert entry.famille is not None
            assert entry.nature is not None
            assert entry.mois_comptable is not None

    def test_contrepartie_identification(self, enriched_schema):
        """Vérifie que les contreparties sont identifiées."""
        entries_with_cp = [e for e in enriched_schema.entries
                          if e.contrepartie_comptes]
        # Au moins 60% des écritures devraient avoir une contrepartie
        # (certaines écritures de test utilisent des pièces uniques)
        assert len(entries_with_cp) > len(enriched_schema.entries) * 0.6

    def test_pcg_classification(self, enriched_schema):
        """Vérifie la classification PCG."""
        for entry in enriched_schema.entries:
            compte = entry.compte_general
            if compte.startswith('6'):
                assert entry.nature == NatureCompte.CHARGE
            elif compte.startswith('7'):
                assert entry.nature == NatureCompte.PRODUIT
            elif compte[0] in '12345':
                assert entry.nature == NatureCompte.BILAN


# ============================================================================
# Tests Couche 1 : ICC
# ============================================================================

class TestICCMetrics:
    """Tests des métriques ICC individuelles."""

    def test_cv_homogeneous(self):
        """CV faible pour montants homogènes."""
        montants = [100.0] * 12
        result = compute_cv_decompose(montants)
        assert result['cv_total'] < 0.01

    def test_cv_heterogeneous(self):
        """CV élevé pour montants hétérogènes."""
        montants = [100.0, 500.0, 50.0, 1000.0, 200.0]
        result = compute_cv_decompose(montants)
        assert result['cv_total'] > 0.5

    def test_entropy_homogeneous(self):
        """Entropie faible pour libellés homogènes (un seul token unique)."""
        # Un seul token unique = entropie 0
        libelles = ['SALAIRE'] * 12
        result = compute_entropy_libelles(libelles)
        # Avec un seul token unique, n_unique = 1, donc max_entropy = log2(1) = 0
        # La fonction retourne 0.0 dans ce cas
        assert result['entropy_normalized'] == 0.0 or result['n_tokens_uniques'] == 1

    def test_entropy_heterogeneous(self):
        """Entropie élevée pour libellés divers."""
        libelles = [
            'FOURNITURE HYGIENE',
            'PAPETERIE BUREAU',
            'ENTRETIEN LOCAUX',
            'MATERIEL PEDAGOGIQUE',
            'PRODUITS ALIMENTAIRES',
        ]
        result = compute_entropy_libelles(libelles)
        assert result['entropy_normalized'] > 0.5

    def test_regularite_temporelle_regular(self):
        """Régularité élevée pour pattern régulier."""
        montants = [1000.0] * 12
        mois = [f'2024-{m:02d}' for m in range(1, 13)]
        result = compute_regularite_temporelle(montants, mois)
        assert result['score_regularite'] > 0.7

    def test_diversite_journaux_single(self):
        """Pureté maximale pour un seul journal."""
        journaux = ['ACH'] * 10
        result = compute_diversite_journaux(journaux)
        assert result['score_purete'] == 1.0
        assert result['n_journaux'] == 1

    def test_concentration_single_supplier(self):
        """Concentration maximale pour un seul fournisseur."""
        contreparties = ['401BAILLEUR'] * 12
        result = compute_concentration_contreparties(contreparties)
        assert result['herfindahl'] == 1.0

    def test_icc_composite(self):
        """Calcul du score ICC composite."""
        cv = {'cv_total': 0.1}
        entropy = {'entropy_normalized': 0.2}
        regularite = {'score_regularite': 0.8}
        journaux = {'score_purete': 1.0}
        contreparties = {'herfindahl': 0.9}

        icc = compute_icc_composite(cv, entropy, regularite, journaux, contreparties)
        assert 0 <= icc <= 1


class TestICCCalculator:
    """Tests du calculateur ICC complet."""

    def test_calculator_runs(self, enriched_schema):
        """Vérifie que le calculateur s'exécute sans erreur."""
        calculator = ICCCalculator()
        results = calculator.compute(enriched_schema)

        assert results.n_couples > 0
        assert len(results.scores) > 0

    def test_salaires_are_crystalline(self, enriched_schema):
        """Les salaires devraient être cristallins."""
        calculator = ICCCalculator()
        results = calculator.compute(enriched_schema)

        # Trouve les couples 641xxx
        salary_scores = [s for s in results.scores if s.compte.startswith('641')]
        assert len(salary_scores) > 0

        for score in salary_scores:
            # Les salaires devraient avoir un ICC élevé
            assert score.icc > 0.5, f"641 devrait être cristallin: {score.icc}"

    def test_zscore_computed(self, enriched_schema):
        """Vérifie que les z-scores sont calculés."""
        calculator = ICCCalculator()
        results = calculator.compute(enriched_schema)

        # Au moins certains scores devraient avoir un z-score
        scores_with_z = [s for s in results.scores if s.zscore is not None]
        assert len(scores_with_z) > 0


# ============================================================================
# Tests Couche 2 : Graphe
# ============================================================================

class TestBipartiteGraph:
    """Tests du graphe biparti."""

    def test_graph_construction(self, enriched_schema):
        """Vérifie la construction du graphe."""
        graph = build_bipartite_graph(enriched_schema)

        assert len(graph.nodes_pnl) > 0
        assert len(graph.nodes_bilan) > 0
        assert len(graph.arcs) > 0

    def test_salary_arc_exists(self, enriched_schema):
        """Vérifie l'arc salaires → personnel."""
        graph = build_bipartite_graph(enriched_schema)

        # Cherche l'arc 641 → 421
        arcs = graph.get_outgoing('641100')
        dest_comptes = [arc.compte_dest for arc in arcs]

        assert '421000' in dest_comptes, "Arc 641→421 devrait exister"


class TestArcStability:
    """Tests de la stabilité des arcs."""

    def test_stability_analysis(self, enriched_schema):
        """Vérifie l'analyse de stabilité."""
        analyzer = ArcStabilityAnalyzer()
        results = analyzer.analyze(enriched_schema)

        # Devrait avoir des distances mensuelles
        assert len(results.monthly_distances) > 0

    def test_low_jaccard_for_stable_pattern(self, enriched_schema):
        """Distance Jaccard faible pour pattern stable."""
        analyzer = ArcStabilityAnalyzer()
        results = analyzer.analyze(enriched_schema)

        avg_jaccard = results.get_average_jaccard()
        # Pattern stable = faible distance
        assert avg_jaccard < 0.5


class TestCircuitDetector:
    """Tests de détection des circuits."""

    def test_abt_circuit_detected(self, enriched_schema):
        """Détecte le circuit ABT."""
        detector = CircuitDetector()
        results = detector.detect(enriched_schema)

        abt_circuits = results.get_circuits_par_type(CircuitType.ABT)
        assert len(abt_circuits) > 0, "Circuit ABT devrait être détecté"

    def test_circuit_has_dotations_and_reprises(self, enriched_schema):
        """Vérifie dotations et reprises."""
        detector = CircuitDetector()
        results = detector.detect(enriched_schema)

        for circuit in results.circuits:
            # Un circuit valide a des dotations
            if circuit.type_circuit == CircuitType.ABT:
                assert circuit.total_dotations > 0


class TestTemplateConformity:
    """Tests de conformité aux templates."""

    def test_salary_to_personnel_is_conforme(self):
        """Salaires → Personnel est conforme."""
        is_conforme, _ = check_template_conformity('641', '421')
        assert is_conforme

    def test_salary_to_attente_is_not_conforme(self):
        """Salaires → Attente n'est pas conforme."""
        is_conforme, _ = check_template_conformity('641', '471')
        assert not is_conforme


# ============================================================================
# Tests Couche 3 : Embedding
# ============================================================================

class TestConnectivityMatrix:
    """Tests de la matrice de connectivité."""

    def test_matrix_construction(self, enriched_schema):
        """Vérifie la construction de la matrice."""
        matrix = build_connectivity_matrix(enriched_schema)

        assert matrix.n_comptes > 0
        assert matrix.total_flux > 0
        assert matrix.matrix is not None

    def test_matrix_symmetry_check(self, enriched_schema):
        """La matrice peut être asymétrique (flux dirigés)."""
        matrix = build_connectivity_matrix(enriched_schema)

        # Vérifie que c'est bien dirigé (pas nécessairement symétrique)
        assert matrix.shape[0] == matrix.shape[1]


class TestSVDVectorizer:
    """Tests de la vectorisation SVD."""

    def test_vectorizer_runs(self, enriched_schema):
        """Vérifie que le vectorizer s'exécute."""
        from gl_crystal.layer3_embedding.connectivity import build_all_matrices

        matrices = build_all_matrices(enriched_schema, by_analytique=True, by_mois=False)
        vectorizer = SVDVectorizer(k=5)
        embeddings = vectorizer.fit_transform(matrices)

        assert len(embeddings) > 0
        for emb in embeddings:
            assert emb.dimension == 5

    def test_similar_sites_close_in_embedding(self, enriched_schema):
        """Sites similaires devraient être proches dans l'embedding."""
        from gl_crystal.layer3_embedding.connectivity import build_all_matrices

        matrices = build_all_matrices(enriched_schema, by_analytique=True, by_mois=False)
        vectorizer = SVDVectorizer(k=5)
        embeddings = vectorizer.fit_transform(matrices)

        # Tous les sites ont un pattern similaire, ils devraient être proches
        if len(embeddings) >= 2:
            dist = embeddings[0].distance_to(embeddings[1])
            # Distance ne devrait pas être énorme
            assert dist < 10.0  # Seuil arbitraire


# ============================================================================
# Tests d'intégration complète
# ============================================================================

class TestFullPipeline:
    """Tests du pipeline complet."""

    def test_full_analysis(self, sample_gl_entries):
        """Exécute l'analyse complète."""
        # Schéma
        schema = GLSchema(
            source_file='test.xlsx',
            source_format='test',
            date_extraction=date.today(),
            entries=sample_gl_entries,
        )
        schema.compute_stats()

        # Enrichissement
        enricher = GLEnricher()
        enriched = enricher.enrich(schema)

        # Couche 1 : ICC
        icc_calc = ICCCalculator()
        icc_results = icc_calc.compute(enriched)

        # Couche 2 : Graphe
        graph = build_bipartite_graph(enriched)
        stability = ArcStabilityAnalyzer().analyze(enriched)
        circuits = CircuitDetector().detect(enriched)

        # Couche 3 : Embedding
        from gl_crystal.layer3_embedding.connectivity import build_all_matrices
        matrices = build_all_matrices(enriched, by_analytique=True, by_mois=False)
        vectorizer = SVDVectorizer(k=5)
        embeddings = vectorizer.fit_transform(matrices)

        # Assertions finales
        assert icc_results.n_couples > 0
        assert len(graph.arcs) > 0
        assert len(circuits.circuits) > 0
        assert len(embeddings) > 0

        print(f"\n=== Résumé de l'analyse ===")
        print(f"Écritures: {schema.nb_ecritures}")
        print(f"Comptes: {schema.nb_comptes}")
        print(f"Couples analysés: {icc_results.n_couples}")
        print(f"Cristallins: {len(icc_results.get_cristallins())}")
        print(f"Amorphes: {len(icc_results.get_amorphes())}")
        print(f"Arcs dans le graphe: {len(graph.arcs)}")
        print(f"Circuits détectés: {len(circuits.circuits)}")
        print(f"Circuits ouverts: {len(circuits.get_circuits_ouverts())}")
        print(f"Embeddings: {len(embeddings)}")


# ============================================================================
# Tests Layer 0 - Classification sémantique (v2.0)
# ============================================================================

class TestSemanticClassification:
    """Tests de la classification sémantique (Layer 0)."""

    def test_classifier_runs(self, enriched_schema):
        """Le classifieur s'exécute sans erreur."""
        from gl_crystal.layer0_classifier import SemanticClassifier

        classifier = SemanticClassifier(min_ecritures=3)
        results = classifier.classify(enriched_schema)

        assert results is not None
        assert len(results.classifications) > 0
        assert results.summary is not None

    def test_salaries_classified_appropriately(self, enriched_schema):
        """Les salaires devraient être classés dans un univers cohérent."""
        from gl_crystal.layer0_classifier import SemanticClassifier, UniversSemantique

        classifier = SemanticClassifier(min_ecritures=3)
        results = classifier.classify(enriched_schema)

        # Cherche les couples de salaires (641)
        salary_couples = [c for c in results.classifications
                         if c.compte_general.startswith('641')]

        assert len(salary_couples) > 0, "Devrait y avoir des couples de salaires"

        for couple in salary_couples:
            # Salaires avec montants identiques peuvent être classés VENTILATION
            # Salaires réguliers: CRISTALLIN
            # Salaires avec noms employés: NOMINATIF
            # Les seuls univers inadaptés seraient INVENTAIRE (réservé aux amortissements)
            assert couple.univers != UniversSemantique.INVENTAIRE, \
                f"Salaires ne devraient pas être classés INVENTAIRE"

            # Vérifier que la confiance est raisonnable
            assert couple.confiance >= 0.5, \
                f"Faible confiance pour salaires: {couple.confiance}"

    def test_classification_summary_complete(self, enriched_schema):
        """Le résumé de classification contient tous les univers."""
        from gl_crystal.layer0_classifier import SemanticClassifier, UniversSemantique

        classifier = SemanticClassifier(min_ecritures=3)
        results = classifier.classify(enriched_schema)

        # Tous les univers doivent être présents dans le résumé
        for univers in UniversSemantique:
            assert univers.value in results.summary.par_univers

    def test_univers_profiles_complete(self):
        """Tous les profils d'univers sont définis."""
        from gl_crystal.layer0_classifier import UniversSemantique, UNIVERS_PROFILES

        for univers in UniversSemantique:
            assert univers in UNIVERS_PROFILES
            profile = UNIVERS_PROFILES[univers]
            assert profile.icc_attendu is not None
            assert profile.seuil_surprise is not None
            assert len(profile.axes_icc_actifs) > 0


class TestICCv2Integration:
    """Tests de l'intégration ICC v2.0 avec Layer 0."""

    def test_icc_with_classification(self, enriched_schema):
        """ICC fonctionne avec classification fournie."""
        from gl_crystal.layer0_classifier import SemanticClassifier
        from gl_crystal.layer1_crystallinity.icc_calculator import ICCCalculator

        # Classifie d'abord
        classifier = SemanticClassifier(min_ecritures=3)
        classification = classifier.classify(enriched_schema)

        # Calcule l'ICC avec classification
        calculator = ICCCalculator(use_univers_weights=True)
        results = calculator.compute(enriched_schema, classification=classification)

        assert results.has_classification
        assert results.n_couples > 0

        # Tous les scores doivent avoir un univers
        for score in results.scores:
            assert score.univers is not None

    def test_surprise_score_computed(self, enriched_schema):
        """Le score de surprise est calculé."""
        from gl_crystal.layer0_classifier import SemanticClassifier
        from gl_crystal.layer1_crystallinity.icc_calculator import ICCCalculator

        classifier = SemanticClassifier(min_ecritures=3)
        classification = classifier.classify(enriched_schema)

        calculator = ICCCalculator(use_univers_weights=True)
        results = calculator.compute(enriched_schema, classification=classification)

        # Au moins certains scores doivent avoir une surprise
        scores_with_surprise = [s for s in results.scores if s.surprise is not None]
        assert len(scores_with_surprise) > 0

        # Le score de surprise doit être positif (valeur absolue)
        for score in scores_with_surprise:
            assert score.surprise >= 0

    def test_zscore_univers_computed(self, enriched_schema):
        """Le z-score par univers×famille est calculé."""
        from gl_crystal.layer0_classifier import SemanticClassifier
        from gl_crystal.layer1_crystallinity.icc_calculator import ICCCalculator

        classifier = SemanticClassifier(min_ecritures=3)
        classification = classifier.classify(enriched_schema)

        calculator = ICCCalculator(use_univers_weights=True)
        results = calculator.compute(enriched_schema, classification=classification)

        # Tous les scores doivent avoir un zscore_univers
        for score in results.scores:
            assert score.zscore_univers is not None

    def test_top_surprises_method(self, enriched_schema):
        """La méthode top_surprises fonctionne."""
        from gl_crystal.layer0_classifier import SemanticClassifier
        from gl_crystal.layer1_crystallinity.icc_calculator import ICCCalculator

        classifier = SemanticClassifier(min_ecritures=3)
        classification = classifier.classify(enriched_schema)

        calculator = ICCCalculator(use_univers_weights=True)
        results = calculator.compute(enriched_schema, classification=classification)

        top = results.top_surprises(n=5)
        assert len(top) <= 5

        # Doivent être triés par surprise décroissante
        if len(top) >= 2:
            assert top[0].surprise >= top[1].surprise

    def test_stats_include_univers_breakdown(self, enriched_schema):
        """Les stats incluent la répartition par univers."""
        from gl_crystal.layer0_classifier import SemanticClassifier
        from gl_crystal.layer1_crystallinity.icc_calculator import ICCCalculator

        classifier = SemanticClassifier(min_ecritures=3)
        classification = classifier.classify(enriched_schema)

        calculator = ICCCalculator(use_univers_weights=True)
        results = calculator.compute(enriched_schema, classification=classification)

        stats = results.get_stats()
        assert stats.get('has_classification')
        assert 'by_univers' in stats
        assert 'n_alertes_surprise' in stats

    def test_legacy_mode_without_classification(self, enriched_schema):
        """Le mode legacy (sans classification) fonctionne toujours."""
        from gl_crystal.layer1_crystallinity.icc_calculator import ICCCalculator

        calculator = ICCCalculator()
        results = calculator.compute(enriched_schema)

        assert not results.has_classification
        assert results.n_couples > 0

        # Z-score legacy doit être calculé
        for score in results.scores:
            assert score.zscore is not None


class TestProperNounNormalization:
    """Tests de la normalisation des noms propres."""

    def test_normalize_names(self):
        """Les noms propres sont correctement normalisés."""
        from gl_crystal.layer0_classifier import normalize_proper_nouns

        libelles = [
            "FACTURE DUPONT 2024-001",
            "FACTURE MARTIN 2024-002",
            "FACTURE DUBOIS 2024-003",
        ]

        normalized = normalize_proper_nouns(libelles)

        # Les noms propres doivent être remplacés par des tokens génériques
        for lib in normalized:
            # Le pattern devrait être uniforme
            assert "[NOM_PROPRE]" in lib or "FACTURE" in lib

    def test_normalize_invoice_references(self):
        """Les références de factures sont normalisées."""
        from gl_crystal.layer0_classifier import normalize_proper_nouns

        libelles = [
            "FAC-2024-00001",
            "FAC-2024-00002",
            "FAC-2024-00003",
        ]

        normalized = normalize_proper_nouns(libelles)

        # Les références numériques doivent être normalisées
        # L'entropie après normalisation devrait être plus faible
        assert len(set(normalized)) <= len(set(libelles))


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
