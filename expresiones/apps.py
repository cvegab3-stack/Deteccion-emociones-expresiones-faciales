"""Configuración de la aplicación Django ``expresiones``."""

from django.apps import AppConfig


class ExpresionesConfig(AppConfig):
    """Configuración de la aplicación (nombre visible en el administrador)."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "expresiones"
    verbose_name = "Detector de expresiones faciales"
