"""
Couche 3 : Alertes contextuelles
================================

Génère uniquement les alertes UTILES (pas de bruit).
"""

from .alert_generator import AlertGenerator, Alert, AlertType

__all__ = ["AlertGenerator", "Alert", "AlertType"]
