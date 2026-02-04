"""
gl_normalizer/layer2/calibration.py
Fonctions de calibration des seuils pour Layer 2

Principe clé: Les seuils ne sont pas des constantes mais des fonctions
du comportement attendu de chaque famille (cv_montant, univers, volume).

Formules:
- dead_band(cv) = 1.5 + 2.0 * cv_attendu
  → CRISTALLIN (cv=0.05) : 1.6σ (sensible)
  → NOMINATIF (cv=1.20)  : 3.9σ (tolérant)
  → PONCTUEL (cv=2.00)   : 5.5σ (très tolérant)

- seuil_materialite = max(plancher, volume * pct_univers)
  → Jamais alerter sur des montants non significatifs
"""

from typing import Dict, Any, Optional
from .base import Univers


# =============================================================================
# CONSTANTES DE CALIBRATION
# =============================================================================

# Paramètres de la dead band (écart-type toléré)
DEAD_BAND_BASELINE = 1.5  # σ minimum tolérés
DEAD_BAND_SLOPE = 2.0     # Facteur multiplicatif du CV

# Plancher absolu de matérialité (€)
MATERIALITE_PLANCHER = 500.0

# Pourcentage de matérialité par univers
MATERIALITE_PCT_BY_UNIVERS: Dict[Univers, float] = {
    Univers.CRISTALLIN: 0.02,              # 2% - très stable, petite variation = signal
    Univers.NOMINATIF_TIERS: 0.05,         # 5% - plus volatile
    Univers.NOMINATIF_OPERATIONNEL: 0.05,  # 5% - multi-sites
    Univers.PROCESSUS: 0.03,               # 3% - cycles connus
    Univers.VENTILATION: 0.02,             # 2% - ABT doit solder
    Univers.CUT_OFF: 0.03,                 # 3% - réguls attendues
    Univers.TRESORERIE: 0.05,              # 5% - flux variables
    Univers.PONCTUEL: 0.10,                # 10% - événementiel par définition
    Univers.INVENTAIRE: 0.05,              # 5% - variation fin exercice
    Univers.COMPOSITE: 0.08,               # 8% - catch-all
}

# Seuils de variation M/M par univers (%)
VARIATION_SEUIL_BY_UNIVERS: Dict[Univers, float] = {
    Univers.CRISTALLIN: 0.05,              # 5% - loyers quasi-fixes
    Univers.NOMINATIF_TIERS: 0.30,         # 30% - transactionnel volatile
    Univers.NOMINATIF_OPERATIONNEL: 0.20,  # 20% - charges par site
    Univers.PROCESSUS: 0.15,               # 15% - cycles avec saisonnalité
    Univers.VENTILATION: 0.10,             # 10% - ABT mensuel
    Univers.CUT_OFF: 0.50,                 # 50% - réguls ponctuelles
    Univers.TRESORERIE: 0.50,              # 50% - flux irréguliers
    Univers.PONCTUEL: 1.00,                # 100% - pas de référence
    Univers.INVENTAIRE: 0.20,              # 20% - variations stock
    Univers.COMPOSITE: 0.30,               # 30% - défaut
}


# =============================================================================
# FONCTIONS DE CALIBRATION
# =============================================================================

def dead_band(cv_attendu: float) -> float:
    """
    Calcule la dead band (nombre d'écarts-types tolérés) en fonction du CV attendu.

    La dead band définit le seuil en σ au-delà duquel un écart est considéré
    comme significatif. Plus le CV attendu est élevé (compte volatile),
    plus on tolère d'écart.

    Formule: dead_band = 1.5 + 2.0 * cv_attendu

    Args:
        cv_attendu: Coefficient de variation attendu pour cette famille
                   (typiquement entre 0.05 et 2.0)

    Returns:
        Seuil en nombre d'écarts-types (σ)

    Examples:
        >>> dead_band(0.05)  # CRISTALLIN - loyers fixes
        1.6
        >>> dead_band(0.72)  # 613 loyers (cv réel)
        2.94
        >>> dead_band(1.20)  # NOMINATIF volatile
        3.9
        >>> dead_band(2.00)  # PONCTUEL
        5.5
    """
    return DEAD_BAND_BASELINE + DEAD_BAND_SLOPE * cv_attendu


def seuil_relatif(
    volume_annuel: float,
    pct: float,
    plancher: float = MATERIALITE_PLANCHER
) -> float:
    """
    Calcule un seuil relatif au volume avec plancher.

    Seuil = max(plancher, volume × pourcentage)

    Args:
        volume_annuel: Volume annuel de la famille en €
        pct: Pourcentage du volume (ex: 0.05 pour 5%)
        plancher: Seuil minimum absolu en €

    Returns:
        Seuil en €

    Examples:
        >>> seuil_relatif(100_000, 0.05)  # 5% de 100K€
        5000.0
        >>> seuil_relatif(5_000, 0.05)    # 5% de 5K€ < plancher
        500.0
    """
    return max(plancher, volume_annuel * pct)


def seuil_materialite(
    famille: str,
    referentiel: Dict[str, Any],
    plancher: float = MATERIALITE_PLANCHER
) -> float:
    """
    Calcule le seuil de matérialité pour une famille.

    Utilise le volume annuel médian du référentiel et le pourcentage
    selon l'univers de la famille.

    Args:
        famille: Code famille PCG (ex: "613")
        referentiel: Dictionnaire du référentiel sémantique
        plancher: Seuil minimum absolu en €

    Returns:
        Seuil de matérialité en €
    """
    ref_entry = referentiel.get(famille, {})

    # Volume annuel (utiliser médiane si disponible, sinon estimation)
    volume = ref_entry.get("volume_annuel_median", 100_000)

    # Univers pour déterminer le pourcentage
    univers_str = ref_entry.get("univers", "COMPOSITE")
    try:
        univers = Univers(univers_str)
    except ValueError:
        univers = Univers.COMPOSITE

    pct = MATERIALITE_PCT_BY_UNIVERS.get(univers, 0.05)

    return seuil_relatif(volume, pct, plancher)


def seuil_variation(
    univers: Univers,
    cv_historique: Optional[float] = None
) -> float:
    """
    Calcule le seuil de variation M/M acceptable pour un univers.

    Si cv_historique est fourni, utilise max(seuil_univers, cv_historique * 1.5)
    pour s'adapter aux familles plus volatiles que la moyenne.

    Args:
        univers: Univers sémantique
        cv_historique: CV historique observé pour cette famille (optionnel)

    Returns:
        Seuil de variation en proportion (ex: 0.05 pour 5%)

    Examples:
        >>> seuil_variation(Univers.CRISTALLIN)
        0.05
        >>> seuil_variation(Univers.CRISTALLIN, cv_historique=0.08)
        0.12  # 1.5 × 0.08 > 0.05
    """
    seuil_univers = VARIATION_SEUIL_BY_UNIVERS.get(univers, 0.30)

    if cv_historique is not None:
        # Adapter au CV historique observé
        seuil_adapte = cv_historique * 1.5
        return max(seuil_univers, seuil_adapte)

    return seuil_univers


def z_score_calibre(
    valeur: float,
    moyenne: float,
    ecart_type: float,
    cv_attendu: float
) -> tuple[float, bool]:
    """
    Calcule un z-score et détermine s'il dépasse la dead band calibrée.

    Args:
        valeur: Valeur observée
        moyenne: Moyenne de référence
        ecart_type: Écart-type de référence
        cv_attendu: CV attendu pour calibration de la dead band

    Returns:
        (z_score, is_signal): Le z-score et True si dépasse la dead band

    Examples:
        >>> z_score_calibre(1200, 1000, 100, cv_attendu=0.05)
        (2.0, True)   # 2σ > dead_band(0.05)=1.6
        >>> z_score_calibre(1200, 1000, 100, cv_attendu=1.0)
        (2.0, False)  # 2σ < dead_band(1.0)=3.5
    """
    if ecart_type == 0:
        return (0.0, False)

    z = abs(valeur - moyenne) / ecart_type
    seuil = dead_band(cv_attendu)

    return (z, z > seuil)


def est_montant_rond(montant: float, tolerance: float = 0.01) -> bool:
    """
    Vérifie si un montant est "rond" (multiple de 100, 500, 1000, etc.).

    Utilisé pour les exclusions métier (loyers = montants ronds normaux).

    Args:
        montant: Montant à vérifier
        tolerance: Tolérance relative (défaut 1%)

    Returns:
        True si le montant est considéré comme rond
    """
    abs_montant = abs(montant)
    if abs_montant < 100:
        return False

    # Multiples courants
    multiples = [100, 500, 1000, 5000, 10000, 25000, 50000, 100000]

    for m in multiples:
        if abs_montant >= m:
            reste = abs_montant % m
            if reste / m <= tolerance or (m - reste) / m <= tolerance:
                return True

    return False


def meme_montant_n_mois(montants: list[float], n: int = 12, tolerance: float = 0.01) -> bool:
    """
    Vérifie si le même montant se répète sur N mois.

    Utilisé pour exclusion CRISTALLIN (loyer identique = normal).

    Args:
        montants: Liste des montants mensuels
        n: Nombre de mois minimum pour considérer comme répétitif
        tolerance: Tolérance relative

    Returns:
        True si montant quasi-identique sur N mois ou plus
    """
    if len(montants) < n:
        return False

    # Prendre le montant médian comme référence
    import statistics
    median = statistics.median(montants)

    if median == 0:
        return False

    # Compter les montants dans la tolérance
    count_in_tolerance = sum(
        1 for m in montants
        if abs(m - median) / abs(median) <= tolerance
    )

    return count_in_tolerance >= n
