# STORY-027: Configuration UI des tokens API

## Métadonnées
- **ID**: STORY-027
- **Sprint**: 6
- **Priorité**: High
- **Estimation**: 3 points
- **Dépendances**: STORY-022 (SecretsManager existant)

## User Story

**En tant que** utilisateur de GL Normalizer,
**Je veux** pouvoir configurer mes clés API directement dans l'interface web,
**Afin de** utiliser les fonctionnalités d'IA avancées (NLP, scoring, etc.) sans éditer de fichiers de configuration.

## Contexte

Le module `secrets_manager.py` existe déjà et gère :
- OpenAI API Key
- Anthropic API Key
- HuggingFace Token

Mais actuellement, aucune interface web ne permet de configurer ces tokens. L'utilisateur doit utiliser des variables d'environnement ou le wizard CLI.

## Critères d'acceptation

### AC-1: Page de configuration accessible
- [ ] Lien "Configuration" visible dans la navigation
- [ ] Page `/settings` accessible sans authentification (MVP)
- [ ] Affichage du statut de chaque provider (configuré/non configuré)

### AC-2: Formulaire de saisie des tokens
- [ ] Champ masqué (type password) pour chaque token
- [ ] Validation en temps réel du format (préfixe sk-, sk-ant-, hf_)
- [ ] Message d'erreur clair si format invalide
- [ ] Bouton "Tester" pour vérifier la validité avec l'API

### AC-3: Persistance sécurisée
- [ ] Tokens stockés via SecretsManager existant
- [ ] Chiffrement au repos (déjà implémenté)
- [ ] Jamais envoyés dans les logs ou réponses API
- [ ] Option pour supprimer un token configuré

### AC-4: Indicateur de disponibilité IA
- [ ] Badge sur la page d'accueil indiquant si l'IA est disponible
- [ ] Message informatif si aucun token configuré
- [ ] Liste des fonctionnalités disponibles selon les tokens configurés

## Design technique

### Nouveaux endpoints
```
GET  /settings                    # Page de configuration
POST /api/settings/token          # Sauvegarder un token
DELETE /api/settings/token/{type} # Supprimer un token
GET  /api/settings/status         # Statut des tokens (sans les valeurs)
POST /api/settings/test/{type}    # Tester un token
```

### Modifications
- `main.py`: Ajouter routes /settings
- `templates/settings.html`: Nouveau template
- `templates/base.html`: Ajouter lien navigation

### Sécurité
- Tokens jamais retournés dans les réponses (seulement statut)
- Validation CSRF sur les formulaires
- Rate limiting sur /api/settings/test (éviter brute force)

## Tâches

- [ ] Créer template `settings.html`
- [ ] Ajouter routes dans `main.py`
- [ ] Intégrer avec SecretsManager
- [ ] Ajouter tests de validation
- [ ] Ajouter indicateur IA sur page d'accueil

## Tests

### Tests unitaires
- Validation format tokens (préfixes, longueur)
- Masquage des valeurs dans les réponses
- Persistance et lecture

### Tests E2E
- Configuration d'un token OpenAI
- Suppression d'un token
- Affichage statut correct après config

## Notes

Le SecretsManager supporte déjà :
- `set_secret(type, value)` - Sauvegarder
- `get_secret(type)` - Récupérer
- `validate_secret(type, value)` - Valider format
- `mask_secret(value)` - Masquer pour affichage
- `has_valid_ai_token()` - Vérifier disponibilité IA
