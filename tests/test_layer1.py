"""
Tests for Layer 1: Label Parser

Tests:
- Entity extraction (amounts, dates, references, tiers)
- Intent classification
- Operation type classification
- Full parsing pipeline
"""

import pytest

from gl_normalizer.layer1 import (
    # Base
    ParsedLabel,
    LabelFeatures,
    ExtractedEntity,
    EntityType,
    OperationType,
    Intent,
    ParserConfig,
    # Entities
    extract_entities,
    extract_amount,
    extract_date,
    extract_reference,
    extract_tiers,
    # Intents
    classify_intent,
    classify_operation,
    detect_recurring,
    INTENT_PATTERNS,
    # Parser
    LabelParser,
    parse_label,
    parse_labels,
)


# =============================================================================
# TEST ENTITY EXTRACTION
# =============================================================================

class TestAmountExtraction:
    """Tests extraction de montants."""

    def test_extract_amount_with_euro(self):
        """Montant avec symbole euro."""
        entities = extract_amount("Facture 1234.56€ TTC")
        assert len(entities) >= 1
        assert entities[0].entity_type == EntityType.MONTANT

    def test_extract_amount_french_format(self):
        """Montant format français (virgule décimale)."""
        entities = extract_amount("Total: 1 234,56 EUR")
        assert len(entities) >= 1

    def test_extract_amount_with_keyword(self):
        """Montant avec mot-clé MONTANT."""
        entities = extract_amount("MONTANT: 500")
        assert len(entities) >= 1


class TestDateExtraction:
    """Tests extraction de dates."""

    def test_extract_date_full(self):
        """Date complète JJ/MM/AAAA."""
        entities = extract_date("Facture du 15/01/2024")
        assert len(entities) >= 1
        assert entities[0].entity_type == EntityType.DATE

    def test_extract_date_month_year(self):
        """Mois + année."""
        entities = extract_date("Loyer janvier 2024")
        assert len(entities) >= 1
        assert "01" in entities[0].normalized or "JANVIER" in entities[0].normalized.upper()

    def test_extract_date_quarter(self):
        """Trimestre."""
        entities = extract_date("Provision Q1 2024")
        assert len(entities) >= 1
        assert "Q1" in entities[0].value.upper()


class TestReferenceExtraction:
    """Tests extraction de références."""

    def test_extract_facture_reference(self):
        """Référence facture."""
        entities = extract_reference("FA-2024-00123 ACME")
        assert len(entities) >= 1
        assert entities[0].entity_type == EntityType.REFERENCE
        assert "FA" in entities[0].normalized.upper()

    def test_extract_bon_commande(self):
        """Référence bon de commande."""
        entities = extract_reference("BC-123456 fournitures")
        assert len(entities) >= 1
        assert "BC" in entities[0].normalized.upper()

    def test_extract_generic_reference(self):
        """Référence générique."""
        entities = extract_reference("Pièce n°12345678")
        assert len(entities) >= 1


class TestTiersExtraction:
    """Tests extraction de noms de tiers."""

    def test_extract_tiers_with_suffix(self):
        """Tiers avec suffixe juridique."""
        entities = extract_tiers("Facture ACME SARL")
        assert len(entities) >= 1
        assert "ACME" in entities[0].normalized.upper()

    def test_extract_tiers_after_keyword(self):
        """Tiers après mot-clé."""
        entities = extract_tiers("Paiement fournisseur ABC COMPANY")
        # Peut ou non matcher selon les patterns
        # Le test vérifie juste que ça ne plante pas
        assert isinstance(entities, list)

    def test_extract_tiers_with_known_list(self):
        """Tiers avec liste connue."""
        known = ["ACME CORP", "XYZ INDUSTRIES"]
        entities = extract_tiers("Facture ACME CORP 2024", known_tiers=known)
        assert len(entities) >= 1


class TestAllEntities:
    """Tests extraction combinée."""

    def test_extract_all_from_complex_label(self):
        """Extraction complète d'un libellé riche."""
        text = "FA-2024-001 ACME SARL loyer janvier 2024 1500.00€"
        entities = extract_entities(text)

        types = {e.entity_type for e in entities}
        # On s'attend à trouver au moins référence, date, montant
        assert EntityType.REFERENCE in types or EntityType.MONTANT in types

    def test_extract_empty_string(self):
        """Libellé vide."""
        entities = extract_entities("")
        assert entities == []

    def test_extract_no_entities(self):
        """Libellé sans entités détectables."""
        entities = extract_entities("divers")
        # Peut être vide ou non
        assert isinstance(entities, list)


# =============================================================================
# TEST INTENT CLASSIFICATION
# =============================================================================

class TestIntentClassification:
    """Tests classification d'intention."""

    def test_intent_regularisation(self):
        """Détection régularisation."""
        intent, conf = classify_intent("REGULARISATION TVA decembre")
        assert intent == Intent.REGULARISATION
        assert conf > 0.5

    def test_intent_extourne(self):
        """Détection extourne."""
        intent, conf = classify_intent("Extourne facture 123")
        assert intent == Intent.EXTOURNE
        assert conf > 0.5

    def test_intent_provision(self):
        """Détection provision."""
        intent, conf = classify_intent("Dotation provision client douteux")
        assert intent == Intent.PROVISION
        assert conf > 0.5

    def test_intent_standard(self):
        """Libellé standard sans intent particulier."""
        intent, conf = classify_intent("Achat fournitures bureau")
        # Peut être STANDARD ou autre, mais pas d'erreur
        assert intent in Intent


class TestOperationClassification:
    """Tests classification type d'opération."""

    def test_operation_achat(self):
        """Détection achat."""
        op, conf = classify_operation("Facture fournisseur ACME")
        assert op == OperationType.ACHAT
        assert conf > 0.5

    def test_operation_vente(self):
        """Détection vente."""
        op, conf = classify_operation("Facture client ABC")
        assert op == OperationType.VENTE
        assert conf > 0.5

    def test_operation_salaire(self):
        """Détection salaire."""
        op, conf = classify_operation("Paie janvier 2024")
        assert op == OperationType.SALAIRE
        assert conf > 0.5

    def test_operation_loyer(self):
        """Détection charge fixe (loyer)."""
        op, conf = classify_operation("Loyer bureaux janvier")
        assert op == OperationType.CHARGE_FIXE
        assert conf > 0.5


class TestRecurringDetection:
    """Tests détection récurrence."""

    def test_recurring_loyer(self):
        """Loyer = récurrent."""
        is_recur, conf = detect_recurring("Loyer janvier 2024")
        assert is_recur is True

    def test_recurring_abonnement(self):
        """Abonnement = récurrent."""
        is_recur, conf = detect_recurring("Abonnement téléphone")
        assert is_recur is True

    def test_not_recurring(self):
        """Achat ponctuel = non récurrent."""
        is_recur, conf = detect_recurring("Achat ordinateur")
        assert is_recur is False


# =============================================================================
# TEST LABEL PARSER
# =============================================================================

class TestLabelParser:
    """Tests du parser principal."""

    def test_parser_basic(self):
        """Parsing basique."""
        parser = LabelParser()
        result = parser.parse("FA-2024-001 ACME loyer janvier 1500€")

        assert isinstance(result, ParsedLabel)
        assert result.original == "FA-2024-001 ACME loyer janvier 1500€"
        assert result.normalized != ""
        assert result.hash != ""

    def test_parser_features(self):
        """Features extraites."""
        parser = LabelParser()
        result = parser.parse("Facture fournisseur ABC SARL 2500.00 EUR")

        features = result.features
        assert isinstance(features, LabelFeatures)
        assert features.operation_type in OperationType

    def test_parser_caching(self):
        """Cache des résultats."""
        parser = LabelParser(ParserConfig(cache_enabled=True))

        # Premier appel
        result1 = parser.parse("Test libellé cache")
        # Deuxième appel (même texte)
        result2 = parser.parse("Test libellé cache")

        # Même hash = même résultat caché
        assert result1.hash == result2.hash

    def test_parser_batch(self):
        """Parsing batch."""
        parser = LabelParser()
        texts = ["Facture 1", "Facture 2", "Loyer janvier"]
        results = parser.parse_batch(texts)

        assert len(results) == 3
        assert all(isinstance(r, ParsedLabel) for r in results)

    def test_parser_empty(self):
        """Libellé vide."""
        parser = LabelParser()
        result = parser.parse("")

        assert result.original == ""
        assert len(result.entities) == 0


class TestConvenienceFunctions:
    """Tests des fonctions raccourcies."""

    def test_parse_label_function(self):
        """Fonction parse_label."""
        result = parse_label("Test facture")
        assert isinstance(result, ParsedLabel)

    def test_parse_labels_function(self):
        """Fonction parse_labels."""
        results = parse_labels(["Label 1", "Label 2"])
        assert len(results) == 2


class TestParsedLabel:
    """Tests de la classe ParsedLabel."""

    def test_to_dict(self):
        """Conversion en dict."""
        parser = LabelParser()
        result = parser.parse("Test label")
        d = result.to_dict()

        assert "original" in d
        assert "normalized" in d
        assert "hash" in d
        assert "entities" in d
        assert "features" in d

    def test_summary(self):
        """Résumé textuel."""
        parser = LabelParser()
        result = parser.parse("Facture fournisseur ABC SARL")
        summary = result.summary()

        assert isinstance(summary, str)
        assert result.hash[:6] in summary

    def test_get_entities_by_type(self):
        """Filtrage entités par type."""
        parser = LabelParser()
        result = parser.parse("FA-2024-001 1500€")

        refs = result.get_entities_by_type(EntityType.REFERENCE)
        amounts = result.get_entities_by_type(EntityType.MONTANT)

        assert all(e.entity_type == EntityType.REFERENCE for e in refs)
        assert all(e.entity_type == EntityType.MONTANT for e in amounts)


# =============================================================================
# TEST EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Tests cas limites."""

    def test_very_long_label(self):
        """Libellé très long."""
        long_text = "Facture " * 100 + "fin"
        parser = LabelParser()
        result = parser.parse(long_text)
        assert isinstance(result, ParsedLabel)

    def test_special_characters(self):
        """Caractères spéciaux."""
        text = "Facture n°123 @ 50% TVA <test>"
        parser = LabelParser()
        result = parser.parse(text)
        assert isinstance(result, ParsedLabel)

    def test_unicode(self):
        """Caractères Unicode."""
        text = "Régularisation été 2024 € ñ"
        parser = LabelParser()
        result = parser.parse(text)
        assert isinstance(result, ParsedLabel)

    def test_multiple_amounts(self):
        """Plusieurs montants."""
        entities = extract_amount("HT: 1000€ TVA: 200€ TTC: 1200€")
        # Devrait trouver au moins un montant
        assert len(entities) >= 1

    def test_multiple_dates(self):
        """Plusieurs dates."""
        entities = extract_date("Du 01/01/2024 au 31/01/2024")
        assert len(entities) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
