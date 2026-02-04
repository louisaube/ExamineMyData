"""
GL Crystal - Règles de Classification Sémantique

Règles heuristiques ordonnées par spécificité décroissante.
Les seuils sont calibrés sur le GL MicroStars 2024.
"""

from typing import Tuple
from .univers import UniversSemantique


def classify_couple(features: dict) -> Tuple[UniversSemantique, float, str]:
    """
    Classifie un couple dans un univers sémantique.

    Args:
        features: Dict de features extrait par extract_classification_features

    Returns:
        (univers, confiance, raison)
        - univers: UniversSemantique
        - confiance: float 0-1
        - raison: str explicatif pour l'utilisateur
    """
    # Règles ordonnées par spécificité décroissante

    # =========================================================================
    # INVENTAIRE : comptes d'amortissement/provision + réf immobilisations
    # =========================================================================
    if (features.get('famille', '') in ('681', '686', '687', '281', '291', '391')
        and features.get('pct_ref_immo', 0) > 0.3):
        return (
            UniversSemantique.INVENTAIRE,
            min(0.95, 0.7 + features['pct_ref_immo']),
            f"{features['pct_ref_immo']:.0%} des libellés contiennent "
            f"des références d'immobilisation (comptes {features['famille']})"
        )

    # Dotations avec régularité parfaite = inventaire
    if (features.get('famille', '') in ('681', '686', '687')
        and features.get('regularite_temporelle', 0) > 0.85
        and features.get('cv_montants', 1) < 0.1):
        return (
            UniversSemantique.INVENTAIRE,
            0.90,
            f"Dotations régulières : CV={features['cv_montants']:.2f}, "
            f"régularité={features['regularite_temporelle']:.2f}"
        )

    # =========================================================================
    # VENTILATION : forte proportion d'écritures miroirs
    # =========================================================================
    if features.get('ratio_miroirs', 0) > 0.3:
        return (
            UniversSemantique.VENTILATION,
            min(0.95, 0.6 + features['ratio_miroirs']),
            f"{features['ratio_miroirs']:.0%} d'écritures miroirs "
            f"(répartition inter-sites probable)"
        )

    # Compte 791 (transferts de charges) = ventilation par nature
    if features.get('famille', '') == '791':
        return (
            UniversSemantique.VENTILATION,
            0.85,
            "Compte 791 = transfert de charges (ventilation par nature)"
        )

    # =========================================================================
    # CRISTALLIN : très faible entropie brute + régularité temporelle
    # =========================================================================
    shannon_brut = features.get('shannon_brut', 10)
    cv_montants = features.get('cv_montants', 1)
    regularite = features.get('regularite_temporelle', 0)

    if (shannon_brut < 2.0
        and cv_montants < 0.15
        and regularite > 0.75):
        return (
            UniversSemantique.CRISTALLIN,
            0.95,
            f"Montants stables (CV={cv_montants:.2f}), "
            f"libellés homogènes (Shannon={shannon_brut:.1f}), "
            f"régularité temporelle {regularite:.0%}"
        )

    # Loyers (613) avec faible variabilité = cristallin
    if (features.get('famille', '') == '613'
        and cv_montants < 0.2
        and regularite > 0.7):
        return (
            UniversSemantique.CRISTALLIN,
            0.90,
            f"Loyer régulier : CV={cv_montants:.2f}, régularité={regularite:.0%}"
        )

    # Abonnements (626) réguliers = cristallin
    if (features.get('famille', '') == '626'
        and cv_montants < 0.25
        and features.get('nb_journaux', 10) <= 2):
        return (
            UniversSemantique.CRISTALLIN,
            0.85,
            f"Abonnement télécom régulier : CV={cv_montants:.2f}"
        )

    # =========================================================================
    # NOMINATIF : entropie qui chute après normalisation des noms propres
    # =========================================================================
    delta_shannon = features.get('delta_shannon', 0)
    pct_noms_propres = features.get('pct_noms_propres', 0)
    shannon_normalise = features.get('shannon_normalise', 10)

    # Fort delta = nominatif évident
    if delta_shannon > 2.0:
        return (
            UniversSemantique.NOMINATIF,
            min(0.95, 0.5 + delta_shannon / 5),
            f"Entropie brute={shannon_brut:.1f} mais normalisée={shannon_normalise:.1f} "
            f"(delta={delta_shannon:.1f}, noms propres détectés)"
        )

    # Beaucoup de noms propres détectés
    if pct_noms_propres > 0.35:
        return (
            UniversSemantique.NOMINATIF,
            min(0.90, 0.5 + pct_noms_propres),
            f"{pct_noms_propres:.0%} de noms propres dans les libellés"
        )

    # Facturation (706/707) avec beaucoup de libellés distincts mais pattern régulier
    if (features.get('famille', '') in ('706', '707')
        and features.get('nb_libelles_uniques', 0) > 20
        and regularite > 0.5):
        return (
            UniversSemantique.NOMINATIF,
            0.85,
            f"Facturation avec {features['nb_libelles_uniques']} libellés distincts "
            f"(noms de clients probable)"
        )

    # Paie (641) = nominatif par nature
    if (features.get('famille', '') == '641'
        and features.get('nb_libelles_uniques', 0) > 5):
        return (
            UniversSemantique.NOMINATIF,
            0.90,
            f"Paie avec {features['nb_libelles_uniques']} libellés distincts "
            f"(noms des salariés)"
        )

    # =========================================================================
    # COMPOSITE : multi-source, multi-nature, pas de pattern dominant
    # =========================================================================
    nb_journaux = features.get('nb_journaux', 0)
    nb_contreparties = features.get('nb_contreparties', 0)

    # Critère fort : multi-source ET entropie normalisée reste haute
    if (nb_journaux >= 3
        and nb_contreparties >= 4
        and shannon_normalise > 3.0):
        return (
            UniversSemantique.COMPOSITE,
            0.85,
            f"{nb_journaux} journaux, {nb_contreparties} contreparties, "
            f"Shannon normalisé={shannon_normalise:.1f} (vrai fourre-tout)"
        )

    # Entropie normalisée reste haute + CV montants élevé
    if (shannon_normalise > 3.5
        and cv_montants > 0.5
        and nb_journaux >= 2):
        return (
            UniversSemantique.COMPOSITE,
            0.75,
            f"Entropie résiduelle élevée après normalisation ({shannon_normalise:.1f}), "
            f"montants dispersés (CV={cv_montants:.2f}), multi-journaux"
        )

    # Comptes d'attente (471) ou divers (618) = composite probable
    if features.get('famille', '') in ('471', '618'):
        if shannon_normalise > 2.5 or nb_contreparties > 3:
            return (
                UniversSemantique.COMPOSITE,
                0.70,
                f"Compte {features['famille']} (attente/divers) avec diversité "
                f"(Shannon={shannon_normalise:.1f}, {nb_contreparties} contreparties)"
            )

    # =========================================================================
    # NON_CLASSE : les règles ne sont pas assez discriminantes
    # =========================================================================
    return (
        UniversSemantique.NON_CLASSE,
        0.30,
        f"Profil intermédiaire : Shannon brut={shannon_brut:.1f}, "
        f"normalisé={shannon_normalise:.1f}, CV={cv_montants:.2f}, "
        f"{nb_journaux} journaux, {nb_contreparties} contreparties"
    )


def get_classification_thresholds() -> dict:
    """
    Retourne les seuils de classification (pour config/tuning).

    Ces seuils sont calibrés sur le GL MicroStars 2024.
    """
    return {
        'cristallin': {
            'shannon_max': 2.0,
            'cv_montants_max': 0.15,
            'regularite_min': 0.75,
        },
        'nominatif': {
            'delta_shannon_min': 2.0,
            'pct_noms_propres_min': 0.35,
        },
        'inventaire': {
            'pct_ref_immo_min': 0.3,
            'familles': ['681', '686', '687', '281', '291', '391'],
        },
        'ventilation': {
            'ratio_miroirs_min': 0.3,
            'familles': ['791'],
        },
        'composite': {
            'nb_journaux_min': 3,
            'nb_contreparties_min': 4,
            'shannon_normalise_min': 3.0,
        },
    }
