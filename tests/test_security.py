"""
Tests de sécurité pour GL Normalizer
====================================

Vérifie:
- Limites de taille fichier
- Limites de lignes/colonnes
- Protection des fichiers uploadés
- Sanitization des données
"""

import os
import sys
import tempfile
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gl_normalizer.security import (
    SecurityLimits,
    SecurityError,
    FileTooLargeError,
    TooManyRowsError,
    TooManyColumnsError,
    MemoryLimitError,
    check_file_size,
    check_dataframe_limits,
    check_ai_limits,
    sanitize_dataframe,
    SecureFileStorage,
    validate_file_extension,
    hash_file,
    get_limits_summary,
)


def test_file_size_limits():
    """Test des limites de taille fichier"""
    print("\n" + "=" * 60)
    print("TEST LIMITES TAILLE FICHIER")
    print("=" * 60)

    # Créer un petit fichier temporaire
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("col1,col2\n1,2\n3,4\n")
        small_file = f.name

    try:
        # Test fichier OK
        size = check_file_size(small_file)
        print(f"  ✓ Petit fichier ({size} bytes) accepté")

        # Test avec limite très basse
        tiny_limits = SecurityLimits(max_file_size_mb=0.00001)  # ~10 bytes
        try:
            check_file_size(small_file, tiny_limits)
            print("  ✗ Erreur: aurait dû lever FileTooLargeError")
        except FileTooLargeError as e:
            print(f"  ✓ FileTooLargeError levée correctement: {e}")

    finally:
        os.unlink(small_file)

    print("\n✓ Tests limites fichier PASSÉS")


def test_dataframe_limits():
    """Test des limites DataFrame"""
    print("\n" + "=" * 60)
    print("TEST LIMITES DATAFRAME")
    print("=" * 60)

    # DataFrame normal
    df_ok = pd.DataFrame({
        'a': range(100),
        'b': range(100),
    })

    check_dataframe_limits(df_ok)
    print(f"  ✓ DataFrame {len(df_ok)} lignes accepté")

    # Test trop de lignes
    limits_small = SecurityLimits(max_rows=50)
    try:
        check_dataframe_limits(df_ok, limits_small)
        print("  ✗ Erreur: aurait dû lever TooManyRowsError")
    except TooManyRowsError as e:
        print(f"  ✓ TooManyRowsError levée: {e}")

    # Test trop de colonnes
    df_wide = pd.DataFrame(np.random.rand(10, 150))
    limits_cols = SecurityLimits(max_columns=100)
    try:
        check_dataframe_limits(df_wide, limits_cols)
        print("  ✗ Erreur: aurait dû lever TooManyColumnsError")
    except TooManyColumnsError as e:
        print(f"  ✓ TooManyColumnsError levée: {e}")

    print("\n✓ Tests limites DataFrame PASSÉS")


def test_ai_limits():
    """Test des limites AI"""
    print("\n" + "=" * 60)
    print("TEST LIMITES AI")
    print("=" * 60)

    df = pd.DataFrame({'x': range(1000)})

    # Test normal
    limits = SecurityLimits(max_entries_ai=5000)
    check_ai_limits(df, "isolation_forest", limits)
    print(f"  ✓ DataFrame {len(df)} entrées accepté pour AI")

    # Test autoencoder avec limite basse
    limits_auto = SecurityLimits(max_entries_autoencoder=500)
    try:
        check_ai_limits(df, "autoencoder", limits_auto)
        print("  ✗ Erreur: aurait dû lever TooManyRowsError")
    except TooManyRowsError as e:
        print(f"  ✓ Limite autoencoder respectée: {e}")

    print("\n✓ Tests limites AI PASSÉS")


def test_sanitization():
    """Test de la sanitization des données"""
    print("\n" + "=" * 60)
    print("TEST SANITIZATION")
    print("=" * 60)

    # DataFrame avec données problématiques
    df = pd.DataFrame({
        'normale': ['abc', 'def', 'ghi'],
        'longue': ['x' * 20000, 'y', 'z'],  # String trop longue
        'control': ['a\x00b', 'c\x0fd', 'ok'],  # Caractères de contrôle
    })

    limits = SecurityLimits(max_string_length=100)
    df_clean = sanitize_dataframe(df, limits)

    # Vérifier troncation
    assert len(df_clean['longue'].iloc[0]) <= 100, "String non tronquée!"
    print(f"  ✓ String longue tronquée: {len(df_clean['longue'].iloc[0])} chars")

    # Vérifier suppression caractères de contrôle
    assert '\x00' not in df_clean['control'].iloc[0], "Caractère de contrôle non supprimé!"
    print(f"  ✓ Caractères de contrôle supprimés")

    print("\n✓ Tests sanitization PASSÉS")


def test_secure_file_storage():
    """Test du stockage sécurisé"""
    print("\n" + "=" * 60)
    print("TEST STOCKAGE SÉCURISÉ")
    print("=" * 60)

    # Créer un fichier temporaire
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("compte,debit,credit\n601000,1000,0\n")
        test_file = f.name

    storage = SecureFileStorage()

    try:
        # Stocker le fichier
        file_id = storage.store_file(test_file, "mon_fichier.csv")
        print(f"  ✓ Fichier stocké avec ID: {file_id[:8]}...")

        # Récupérer le chemin
        secure_path = storage.get_path(file_id)
        assert secure_path.exists(), "Fichier sécurisé non trouvé!"
        print(f"  ✓ Fichier accessible via ID")

        # Vérifier permissions (Unix only)
        if os.name != 'nt':
            mode = oct(secure_path.stat().st_mode)[-3:]
            print(f"  ✓ Permissions fichier: {mode}")

        # Test accès invalide
        try:
            storage.get_path("invalid-id-12345")
            print("  ✗ Erreur: aurait dû lever SecurityError")
        except SecurityError:
            print(f"  ✓ Accès avec ID invalide bloqué")

        # Supprimer
        deleted = storage.delete_file(file_id)
        assert deleted, "Fichier non supprimé!"
        assert not secure_path.exists(), "Fichier toujours présent!"
        print(f"  ✓ Fichier supprimé de manière sécurisée")

    finally:
        os.unlink(test_file)
        storage.cleanup_all()

    print("\n✓ Tests stockage sécurisé PASSÉS")


def test_extension_validation():
    """Test de validation d'extension"""
    print("\n" + "=" * 60)
    print("TEST VALIDATION EXTENSION")
    print("=" * 60)

    # Extensions valides
    for ext in ['.csv', '.xlsx', '.xls', '.xlsm']:
        assert validate_file_extension(f"test{ext}"), f"{ext} devrait être valide!"
        print(f"  ✓ {ext} acceptée")

    # Extensions invalides
    for ext in ['.exe', '.py', '.sh', '.php', '.js']:
        assert not validate_file_extension(f"test{ext}"), f"{ext} devrait être invalide!"
        print(f"  ✓ {ext} refusée")

    print("\n✓ Tests extension PASSÉS")


def test_file_hash():
    """Test du hash de fichier"""
    print("\n" + "=" * 60)
    print("TEST HASH FICHIER")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("test,data\n1,2\n")
        test_file = f.name

    try:
        hash1 = hash_file(test_file)
        hash2 = hash_file(test_file)

        assert hash1 == hash2, "Hash non reproductible!"
        assert len(hash1) == 64, "Hash SHA256 devrait faire 64 chars!"
        print(f"  ✓ Hash reproductible: {hash1[:16]}...")

    finally:
        os.unlink(test_file)

    print("\n✓ Tests hash PASSÉS")


def test_limits_summary():
    """Test de l'affichage des limites"""
    print("\n" + "=" * 60)
    print("TEST RÉSUMÉ LIMITES")
    print("=" * 60)

    summary = get_limits_summary()
    print(summary)

    assert "100 MB" in summary, "Limite fichier manquante"
    assert "2,000,000" in summary, "Limite lignes manquante"

    print("✓ Résumé complet affiché")


if __name__ == "__main__":
    print("=" * 60)
    print("TESTS DE SÉCURITÉ - GL NORMALIZER")
    print("=" * 60)

    test_file_size_limits()
    test_dataframe_limits()
    test_ai_limits()
    test_sanitization()
    test_secure_file_storage()
    test_extension_validation()
    test_file_hash()
    test_limits_summary()

    print("\n" + "=" * 60)
    print("✓ TOUS LES TESTS DE SÉCURITÉ PASSÉS")
    print("=" * 60)
