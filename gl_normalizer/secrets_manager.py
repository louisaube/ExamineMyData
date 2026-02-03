"""
gl_normalizer/secrets_manager.py
Gestion sécurisée des secrets et tokens API

Fournit:
- Stockage sécurisé des tokens API (OpenAI, Anthropic, etc.)
- Chiffrement des secrets au repos
- Variables d'environnement sécurisées
- Validation et masquage des tokens
"""

import os
import json
import base64
import hashlib
import getpass
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from enum import Enum
import warnings


class SecretType(Enum):
    """Types de secrets supportés"""
    OPENAI_API_KEY = "openai_api_key"
    ANTHROPIC_API_KEY = "anthropic_api_key"
    HUGGINGFACE_TOKEN = "huggingface_token"
    CUSTOM_API_KEY = "custom_api_key"


@dataclass
class SecretConfig:
    """Configuration d'un secret"""
    name: str
    secret_type: SecretType
    env_var: str                    # Variable d'environnement correspondante
    required_prefix: Optional[str] = None  # Préfixe requis (ex: "sk-" pour OpenAI)
    min_length: int = 20
    max_length: int = 200
    description: str = ""


# Configuration des secrets connus
KNOWN_SECRETS: Dict[SecretType, SecretConfig] = {
    SecretType.OPENAI_API_KEY: SecretConfig(
        name="OpenAI API Key",
        secret_type=SecretType.OPENAI_API_KEY,
        env_var="OPENAI_API_KEY",
        required_prefix="sk-",
        min_length=40,
        max_length=100,
        description="Clé API OpenAI pour GPT et embeddings",
    ),
    SecretType.ANTHROPIC_API_KEY: SecretConfig(
        name="Anthropic API Key",
        secret_type=SecretType.ANTHROPIC_API_KEY,
        env_var="ANTHROPIC_API_KEY",
        required_prefix="sk-ant-",
        min_length=40,
        max_length=150,
        description="Clé API Anthropic pour Claude",
    ),
    SecretType.HUGGINGFACE_TOKEN: SecretConfig(
        name="HuggingFace Token",
        secret_type=SecretType.HUGGINGFACE_TOKEN,
        env_var="HF_TOKEN",
        required_prefix="hf_",
        min_length=30,
        max_length=100,
        description="Token HuggingFace pour modèles et embeddings",
    ),
}


@dataclass
class SecretValidation:
    """Résultat de validation d'un secret"""
    is_valid: bool
    secret_type: SecretType
    masked_value: str               # Version masquée pour affichage
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class SecretsManager:
    """
    Gestionnaire sécurisé des secrets et tokens API.

    Fonctionnalités:
    - Stockage local chiffré (optionnel)
    - Lecture depuis variables d'environnement
    - Validation des formats de tokens
    - Masquage pour logs/affichage
    - Pas de stockage en clair dans le code
    """

    # Fichier de configuration des secrets (chiffré)
    SECRETS_FILE = ".gl_normalizer_secrets"

    # Clé de dérivation (basée sur machine ID)
    _encryption_key: Optional[bytes] = None

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Args:
            config_dir: Répertoire de configuration (défaut: ~/.config/gl_normalizer)
        """
        self.config_dir = config_dir or Path.home() / ".config" / "gl_normalizer"
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self._secrets_file = self.config_dir / self.SECRETS_FILE
        self._loaded_secrets: Dict[str, str] = {}

        # Charger les secrets existants
        self._load_secrets()

    def _get_encryption_key(self) -> bytes:
        """Génère une clé de chiffrement basée sur l'identifiant machine"""
        if self._encryption_key is None:
            # Utiliser une combinaison d'infos machine pour la clé
            machine_id = f"{os.getlogin()}:{Path.home()}"
            self._encryption_key = hashlib.sha256(machine_id.encode()).digest()
        return self._encryption_key

    def _encrypt(self, data: str) -> str:
        """Chiffre une chaîne (XOR simple avec clé dérivée)"""
        key = self._get_encryption_key()
        encrypted = bytes([
            ord(c) ^ key[i % len(key)]
            for i, c in enumerate(data)
        ])
        return base64.b64encode(encrypted).decode()

    def _decrypt(self, encrypted_data: str) -> str:
        """Déchiffre une chaîne"""
        key = self._get_encryption_key()
        decoded = base64.b64decode(encrypted_data.encode())
        decrypted = bytes([
            b ^ key[i % len(key)]
            for i, b in enumerate(decoded)
        ])
        return decrypted.decode()

    def _load_secrets(self):
        """Charge les secrets depuis le fichier chiffré"""
        if self._secrets_file.exists():
            try:
                with open(self._secrets_file, "r") as f:
                    encrypted_data = f.read()
                    if encrypted_data:
                        decrypted = self._decrypt(encrypted_data)
                        self._loaded_secrets = json.loads(decrypted)
            except Exception as e:
                warnings.warn(f"Impossible de charger les secrets: {e}")
                self._loaded_secrets = {}

    def _save_secrets(self):
        """Sauvegarde les secrets dans le fichier chiffré"""
        try:
            data = json.dumps(self._loaded_secrets)
            encrypted = self._encrypt(data)
            with open(self._secrets_file, "w") as f:
                f.write(encrypted)
            # Permissions restrictives
            os.chmod(self._secrets_file, 0o600)
        except Exception as e:
            warnings.warn(f"Impossible de sauvegarder les secrets: {e}")

    def get_secret(
        self,
        secret_type: SecretType,
        prompt_if_missing: bool = False,
    ) -> Optional[str]:
        """
        Récupère un secret de manière sécurisée.

        Ordre de priorité:
        1. Variable d'environnement
        2. Fichier de secrets local
        3. Prompt interactif (si activé)

        Args:
            secret_type: Type de secret à récupérer
            prompt_if_missing: Demander à l'utilisateur si manquant

        Returns:
            Le secret ou None si non trouvé
        """
        config = KNOWN_SECRETS.get(secret_type)
        if config is None:
            return None

        # 1. Variable d'environnement (priorité)
        env_value = os.environ.get(config.env_var)
        if env_value:
            return env_value

        # 2. Fichier de secrets local
        key = secret_type.value
        if key in self._loaded_secrets:
            return self._loaded_secrets[key]

        # 3. Prompt interactif
        if prompt_if_missing:
            return self._prompt_for_secret(secret_type)

        return None

    def _prompt_for_secret(self, secret_type: SecretType) -> Optional[str]:
        """Demande un secret à l'utilisateur de manière sécurisée"""
        config = KNOWN_SECRETS.get(secret_type)
        if config is None:
            return None

        print(f"\n{'='*60}")
        print(f"Configuration requise: {config.name}")
        print(f"{'='*60}")
        print(f"Description: {config.description}")
        print(f"Variable d'environnement: {config.env_var}")
        if config.required_prefix:
            print(f"Format attendu: {config.required_prefix}...")
        print()

        try:
            # Utiliser getpass pour masquer l'entrée
            secret = getpass.getpass(f"Entrez votre {config.name}: ")

            if not secret:
                print("Aucune valeur entrée.")
                return None

            # Valider
            validation = self.validate_secret(secret, secret_type)
            if not validation.is_valid:
                print(f"Erreur de validation: {', '.join(validation.errors)}")
                return None

            # Demander si sauvegarder
            save = input("Sauvegarder pour les prochaines utilisations? [o/N]: ")
            if save.lower() in ["o", "oui", "y", "yes"]:
                self.set_secret(secret_type, secret)
                print(f"Secret sauvegardé dans {self._secrets_file}")

            return secret

        except (EOFError, KeyboardInterrupt):
            print("\nAnnulé.")
            return None

    def set_secret(self, secret_type: SecretType, value: str) -> bool:
        """
        Enregistre un secret de manière sécurisée.

        Args:
            secret_type: Type de secret
            value: Valeur du secret

        Returns:
            True si succès
        """
        # Valider d'abord
        validation = self.validate_secret(value, secret_type)
        if not validation.is_valid:
            warnings.warn(f"Secret invalide: {', '.join(validation.errors)}")
            return False

        key = secret_type.value
        self._loaded_secrets[key] = value
        self._save_secrets()
        return True

    def delete_secret(self, secret_type: SecretType) -> bool:
        """Supprime un secret stocké"""
        key = secret_type.value
        if key in self._loaded_secrets:
            del self._loaded_secrets[key]
            self._save_secrets()
            return True
        return False

    def validate_secret(self, value: str, secret_type: SecretType) -> SecretValidation:
        """
        Valide un secret selon son type.

        Args:
            value: Valeur à valider
            secret_type: Type de secret

        Returns:
            SecretValidation avec résultat
        """
        config = KNOWN_SECRETS.get(secret_type)
        errors = []
        warnings_list = []

        if config is None:
            return SecretValidation(
                is_valid=False,
                secret_type=secret_type,
                masked_value=self.mask_secret(value),
                errors=["Type de secret inconnu"],
            )

        # Vérifier la longueur
        if len(value) < config.min_length:
            errors.append(f"Trop court (min {config.min_length} caractères)")
        if len(value) > config.max_length:
            errors.append(f"Trop long (max {config.max_length} caractères)")

        # Vérifier le préfixe
        if config.required_prefix and not value.startswith(config.required_prefix):
            errors.append(f"Doit commencer par '{config.required_prefix}'")

        # Vérifier les caractères suspects
        if any(c in value for c in [" ", "\n", "\t"]):
            errors.append("Contient des espaces ou caractères de contrôle")

        return SecretValidation(
            is_valid=len(errors) == 0,
            secret_type=secret_type,
            masked_value=self.mask_secret(value),
            errors=errors,
            warnings=warnings_list,
        )

    @staticmethod
    def mask_secret(value: str, visible_chars: int = 4) -> str:
        """
        Masque un secret pour affichage sécurisé.

        Args:
            value: Valeur à masquer
            visible_chars: Nombre de caractères visibles au début/fin

        Returns:
            Version masquée (ex: "sk-pr...xyz")
        """
        if len(value) <= visible_chars * 2:
            return "*" * len(value)

        return f"{value[:visible_chars]}...{value[-visible_chars:]}"

    def get_status(self) -> Dict[str, Any]:
        """
        Retourne le statut de tous les secrets configurés.

        Returns:
            Dict avec statut par type de secret
        """
        status = {}

        for secret_type, config in KNOWN_SECRETS.items():
            value = self.get_secret(secret_type, prompt_if_missing=False)

            if value:
                validation = self.validate_secret(value, secret_type)
                source = "env" if os.environ.get(config.env_var) else "file"
                status[secret_type.value] = {
                    "configured": True,
                    "valid": validation.is_valid,
                    "source": source,
                    "masked": validation.masked_value,
                    "errors": validation.errors,
                }
            else:
                status[secret_type.value] = {
                    "configured": False,
                    "valid": False,
                    "source": None,
                    "masked": None,
                    "errors": ["Non configuré"],
                }

        return status

    def print_status(self):
        """Affiche le statut des secrets de manière formatée"""
        print("\n" + "=" * 60)
        print("STATUT DES SECRETS GL NORMALIZER")
        print("=" * 60)

        status = self.get_status()

        for secret_type, info in status.items():
            config = KNOWN_SECRETS.get(SecretType(secret_type))
            name = config.name if config else secret_type

            if info["configured"]:
                valid_mark = "✓" if info["valid"] else "✗"
                source = f"({info['source']})"
                print(f"\n{valid_mark} {name} {source}")
                print(f"  Valeur: {info['masked']}")
                if info["errors"]:
                    print(f"  Erreurs: {', '.join(info['errors'])}")
            else:
                print(f"\n✗ {name}")
                print(f"  Non configuré")
                if config:
                    print(f"  Variable env: {config.env_var}")

        print("\n" + "=" * 60)

    def is_ai_ready(self) -> bool:
        """Vérifie si au moins un token IA est configuré et valide"""
        ai_types = [
            SecretType.OPENAI_API_KEY,
            SecretType.ANTHROPIC_API_KEY,
            SecretType.HUGGINGFACE_TOKEN,
        ]

        for secret_type in ai_types:
            value = self.get_secret(secret_type, prompt_if_missing=False)
            if value:
                validation = self.validate_secret(value, secret_type)
                if validation.is_valid:
                    return True

        return False

    def setup_interactive(self):
        """Configuration interactive des secrets"""
        print("\n" + "=" * 60)
        print("CONFIGURATION DES SECRETS GL NORMALIZER")
        print("=" * 60)
        print("\nCe wizard va vous aider à configurer les tokens API nécessaires.")
        print("Les secrets seront stockés de manière chiffrée localement.")
        print(f"Fichier: {self._secrets_file}")
        print()

        for secret_type, config in KNOWN_SECRETS.items():
            current = self.get_secret(secret_type, prompt_if_missing=False)

            if current:
                masked = self.mask_secret(current)
                print(f"\n{config.name}: Déjà configuré ({masked})")
                replace = input("Remplacer? [o/N]: ")
                if replace.lower() not in ["o", "oui", "y", "yes"]:
                    continue

            self._prompt_for_secret(secret_type)

        print("\n" + "=" * 60)
        print("Configuration terminée!")
        self.print_status()


# Singleton global
_secrets_manager: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    """Retourne l'instance singleton du gestionnaire de secrets"""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
    return _secrets_manager


def get_api_key(secret_type: SecretType, prompt_if_missing: bool = False) -> Optional[str]:
    """
    Fonction utilitaire pour récupérer une clé API.

    Args:
        secret_type: Type de secret (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)
        prompt_if_missing: Demander à l'utilisateur si manquant

    Returns:
        La clé API ou None
    """
    manager = get_secrets_manager()
    return manager.get_secret(secret_type, prompt_if_missing)


def setup_secrets():
    """Lance la configuration interactive des secrets"""
    manager = get_secrets_manager()
    manager.setup_interactive()


def check_ai_ready() -> bool:
    """Vérifie si l'IA est prête à être utilisée"""
    manager = get_secrets_manager()
    return manager.is_ai_ready()


if __name__ == "__main__":
    print("SecretsManager - Gestion sécurisée des tokens API")
    print("=" * 60)
    print("\nCommandes disponibles:")
    print("  python -m gl_normalizer.secrets_manager status")
    print("  python -m gl_normalizer.secrets_manager setup")
    print()

    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        manager = SecretsManager()

        if cmd == "status":
            manager.print_status()
        elif cmd == "setup":
            manager.setup_interactive()
        else:
            print(f"Commande inconnue: {cmd}")
    else:
        # Afficher le statut par défaut
        manager = SecretsManager()
        manager.print_status()
