"""
gl_normalizer/security.py
Protections de sécurité pour éviter de surcharger le serveur

Limites par défaut:
- Fichier: 100 MB max
- Lignes: 2,000,000 max
- Colonnes: 100 max
- Mémoire: 2 GB max pour un DataFrame
"""

import os
import logging
from pathlib import Path
from typing import Optional, Union
from dataclasses import dataclass

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SecurityLimits:
    """Limites de sécurité configurables"""

    max_file_size_mb: int = 100          # Taille max fichier en MB
    max_rows: int = 2_000_000            # Nb max de lignes
    max_columns: int = 100               # Nb max de colonnes
    max_memory_mb: int = 2048            # Mémoire max DataFrame en MB
    max_string_length: int = 10000       # Longueur max d'une cellule string

    # Limites AI
    max_entries_ai: int = 500_000        # Max entrées pour modules AI
    max_entries_autoencoder: int = 100_000  # Max pour autoencoder (GPU intensive)


class SecurityError(Exception):
    """Exception levée en cas de violation de sécurité"""
    pass


class FileTooLargeError(SecurityError):
    """Fichier trop volumineux"""
    pass


class TooManyRowsError(SecurityError):
    """Trop de lignes dans le fichier"""
    pass


class TooManyColumnsError(SecurityError):
    """Trop de colonnes dans le fichier"""
    pass


class MemoryLimitError(SecurityError):
    """Limite mémoire dépassée"""
    pass


def check_file_size(
    file_path: Union[str, Path],
    limits: Optional[SecurityLimits] = None
) -> int:
    """
    Vérifie la taille du fichier avant chargement.

    Args:
        file_path: Chemin du fichier
        limits: Limites de sécurité (défaut: SecurityLimits())

    Returns:
        Taille du fichier en bytes

    Raises:
        FileTooLargeError: Si fichier trop gros
        FileNotFoundError: Si fichier n'existe pas
    """
    limits = limits or SecurityLimits()
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Fichier non trouvé: {file_path}")

    size_bytes = path.stat().st_size
    size_mb = size_bytes / (1024 * 1024)

    if size_mb > limits.max_file_size_mb:
        raise FileTooLargeError(
            f"Fichier trop volumineux: {size_mb:.1f} MB "
            f"(max: {limits.max_file_size_mb} MB)"
        )

    logger.info(f"Fichier {path.name}: {size_mb:.1f} MB (OK)")
    return size_bytes


def check_dataframe_limits(
    df: pd.DataFrame,
    limits: Optional[SecurityLimits] = None,
    context: str = "DataFrame"
) -> None:
    """
    Vérifie qu'un DataFrame respecte les limites.

    Args:
        df: DataFrame à vérifier
        limits: Limites de sécurité
        context: Contexte pour les messages d'erreur

    Raises:
        TooManyRowsError: Si trop de lignes
        TooManyColumnsError: Si trop de colonnes
        MemoryLimitError: Si mémoire excessive
    """
    limits = limits or SecurityLimits()

    # Vérifier nombre de lignes
    if len(df) > limits.max_rows:
        raise TooManyRowsError(
            f"{context}: {len(df):,} lignes "
            f"(max: {limits.max_rows:,})"
        )

    # Vérifier nombre de colonnes
    if len(df.columns) > limits.max_columns:
        raise TooManyColumnsError(
            f"{context}: {len(df.columns)} colonnes "
            f"(max: {limits.max_columns})"
        )

    # Vérifier mémoire
    memory_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)
    if memory_mb > limits.max_memory_mb:
        raise MemoryLimitError(
            f"{context}: {memory_mb:.0f} MB en mémoire "
            f"(max: {limits.max_memory_mb} MB)"
        )

    logger.info(
        f"{context}: {len(df):,} lignes, {len(df.columns)} colonnes, "
        f"{memory_mb:.1f} MB (OK)"
    )


def check_ai_limits(
    df: pd.DataFrame,
    module: str = "ai",
    limits: Optional[SecurityLimits] = None
) -> None:
    """
    Vérifie les limites spécifiques aux modules AI.

    Args:
        df: DataFrame pour analyse AI
        module: Nom du module AI (pour adapter les limites)
        limits: Limites de sécurité

    Raises:
        TooManyRowsError: Si trop d'entrées pour le module AI
    """
    limits = limits or SecurityLimits()

    if module == "autoencoder":
        max_entries = limits.max_entries_autoencoder
    else:
        max_entries = limits.max_entries_ai

    if len(df) > max_entries:
        raise TooManyRowsError(
            f"Module {module}: {len(df):,} entrées "
            f"(max: {max_entries:,}). "
            f"Conseil: échantillonner avec df.sample({max_entries})"
        )

    logger.info(f"Module {module}: {len(df):,} entrées (OK)")


def sanitize_dataframe(
    df: pd.DataFrame,
    limits: Optional[SecurityLimits] = None
) -> pd.DataFrame:
    """
    Nettoie un DataFrame pour éviter les injections.

    - Tronque les strings trop longues
    - Supprime les caractères de contrôle
    - Normalise les types

    Args:
        df: DataFrame à nettoyer
        limits: Limites de sécurité

    Returns:
        DataFrame nettoyé
    """
    limits = limits or SecurityLimits()
    df = df.copy()
    max_len = limits.max_string_length

    def truncate_string(x):
        if pd.isna(x):
            return x
        s = str(x)
        if len(s) > max_len:
            return s[:max_len]
        return x

    for col in df.columns:
        # Traiter colonnes string (object ou StringDtype)
        if df[col].dtype == "object" or pd.api.types.is_string_dtype(df[col]):
            # Tronquer les strings trop longues
            df[col] = df[col].apply(truncate_string)
            # Supprimer caractères de contrôle (sauf newline, tab)
            df[col] = df[col].astype(str).replace(
                r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]',
                '',
                regex=True
            )

    return df


def safe_read_csv(
    file_path: Union[str, Path],
    limits: Optional[SecurityLimits] = None,
    **kwargs
) -> pd.DataFrame:
    """
    Lecture CSV sécurisée avec vérifications.

    Args:
        file_path: Chemin du fichier
        limits: Limites de sécurité
        **kwargs: Arguments passés à pd.read_csv

    Returns:
        DataFrame chargé et vérifié
    """
    limits = limits or SecurityLimits()

    # Vérifier taille fichier
    check_file_size(file_path, limits)

    # Charger avec limite de lignes
    kwargs.setdefault("nrows", limits.max_rows)

    df = pd.read_csv(file_path, **kwargs)

    # Vérifier limites
    check_dataframe_limits(df, limits, f"CSV {Path(file_path).name}")

    # Nettoyer
    df = sanitize_dataframe(df, limits)

    return df


def safe_read_excel(
    file_path: Union[str, Path],
    limits: Optional[SecurityLimits] = None,
    **kwargs
) -> pd.DataFrame:
    """
    Lecture Excel sécurisée avec vérifications.

    Args:
        file_path: Chemin du fichier
        limits: Limites de sécurité
        **kwargs: Arguments passés à pd.read_excel

    Returns:
        DataFrame chargé et vérifié
    """
    limits = limits or SecurityLimits()

    # Vérifier taille fichier
    check_file_size(file_path, limits)

    # Charger avec limite de lignes
    kwargs.setdefault("nrows", limits.max_rows)

    df = pd.read_excel(file_path, **kwargs)

    # Vérifier limites
    check_dataframe_limits(df, limits, f"Excel {Path(file_path).name}")

    # Nettoyer
    df = sanitize_dataframe(df, limits)

    return df


# =============================================================================
# PROTECTION DES FICHIERS UPLOADÉS
# =============================================================================

import tempfile
import shutil
import hashlib
import uuid


class SecureFileStorage:
    """
    Stockage sécurisé des fichiers uploadés.

    - Fichiers stockés avec noms aléatoires (non devinables)
    - Permissions restrictives (lecture seule par le propriétaire)
    - Nettoyage automatique après utilisation
    - Pas d'accès direct par URL
    """

    def __init__(self, base_dir: Optional[Union[str, Path]] = None):
        """
        Args:
            base_dir: Répertoire de stockage (défaut: /tmp/gl_normalizer_secure)
        """
        if base_dir is None:
            base_dir = Path(tempfile.gettempdir()) / "gl_normalizer_secure"

        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

        # Mapping nom original -> nom sécurisé
        self._file_map: Dict[str, Path] = {}

    def store_file(
        self,
        source_path: Union[str, Path],
        original_name: Optional[str] = None
    ) -> str:
        """
        Stocke un fichier de manière sécurisée.

        Args:
            source_path: Chemin du fichier source
            original_name: Nom original (pour référence)

        Returns:
            ID unique du fichier stocké
        """
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Fichier non trouvé: {source_path}")

        # Générer un ID unique non devinable
        file_id = str(uuid.uuid4())

        # Garder l'extension originale
        suffix = source.suffix.lower()
        if suffix not in [".csv", ".xlsx", ".xls", ".xlsm"]:
            raise SecurityError(f"Extension non autorisée: {suffix}")

        # Chemin sécurisé
        secure_path = self.base_dir / f"{file_id}{suffix}"

        # Copier avec permissions restrictives
        shutil.copy2(source, secure_path)
        os.chmod(secure_path, 0o600)  # Lecture/écriture propriétaire uniquement

        # Enregistrer le mapping
        self._file_map[file_id] = secure_path

        logger.info(f"Fichier stocké: {original_name or source.name} -> {file_id}")

        return file_id

    def get_path(self, file_id: str) -> Path:
        """
        Récupère le chemin d'un fichier par son ID.

        Args:
            file_id: ID du fichier

        Returns:
            Chemin du fichier

        Raises:
            SecurityError: Si ID invalide
        """
        if file_id not in self._file_map:
            raise SecurityError(f"Fichier non trouvé ou accès refusé: {file_id}")

        path = self._file_map[file_id]
        if not path.exists():
            raise SecurityError(f"Fichier supprimé: {file_id}")

        return path

    def delete_file(self, file_id: str) -> bool:
        """
        Supprime un fichier de manière sécurisée.

        Args:
            file_id: ID du fichier

        Returns:
            True si supprimé
        """
        if file_id not in self._file_map:
            return False

        path = self._file_map[file_id]
        if path.exists():
            # Écraser avec des zéros avant suppression (sécurité)
            size = path.stat().st_size
            with open(path, "wb") as f:
                f.write(b"\x00" * min(size, 1024 * 1024))  # Max 1MB de zéros
            path.unlink()

        del self._file_map[file_id]
        logger.info(f"Fichier supprimé: {file_id}")

        return True

    def cleanup_all(self) -> int:
        """
        Supprime tous les fichiers stockés.

        Returns:
            Nombre de fichiers supprimés
        """
        count = 0
        for file_id in list(self._file_map.keys()):
            if self.delete_file(file_id):
                count += 1

        return count

    def __del__(self):
        """Nettoyage automatique à la destruction"""
        try:
            self.cleanup_all()
        except Exception:
            pass


def hash_file(file_path: Union[str, Path]) -> str:
    """
    Calcule le hash SHA256 d'un fichier (pour vérification d'intégrité).

    Args:
        file_path: Chemin du fichier

    Returns:
        Hash SHA256 en hexadécimal
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def validate_file_extension(file_path: Union[str, Path]) -> bool:
    """
    Vérifie que l'extension du fichier est autorisée.

    Args:
        file_path: Chemin du fichier

    Returns:
        True si extension valide
    """
    allowed = {".csv", ".xlsx", ".xls", ".xlsm"}
    suffix = Path(file_path).suffix.lower()
    return suffix in allowed


# Limites par défaut globales
DEFAULT_LIMITS = SecurityLimits()


def get_limits_summary() -> str:
    """Retourne un résumé des limites actives"""
    limits = DEFAULT_LIMITS
    return f"""
Limites de sécurité GL Normalizer:
- Fichier max: {limits.max_file_size_mb} MB
- Lignes max: {limits.max_rows:,}
- Colonnes max: {limits.max_columns}
- Mémoire max: {limits.max_memory_mb} MB
- Entrées AI max: {limits.max_entries_ai:,}
- Entrées Autoencoder max: {limits.max_entries_autoencoder:,}
"""
