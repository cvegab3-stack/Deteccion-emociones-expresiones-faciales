"""
Muestra un mensaje claro cuando PostgreSQL no está disponible o faltan
las migraciones, en lugar de la página de error genérica.
"""

import logging

from django.db import OperationalError, ProgrammingError
from django.http import JsonResponse
from django.shortcuts import render

registro_log = logging.getLogger("expresiones")


def describir_error_bd(exc):
    """Devuelve ``(mensaje, tipo)`` en español para un error de base de datos."""
    if isinstance(exc, ProgrammingError):
        return ("Las tablas no existen en PostgreSQL. Ejecute: python manage.py migrate", "migraciones")
    return ("No se pudo conectar a PostgreSQL. Verifique que el servicio esté iniciado y que los "
            "datos de POSTGRES_* en el archivo .env sean correctos.", "conexion")


class ErroresBaseDatosMiddleware:
    """Muestra una página de ayuda si PostgreSQL falla, en lugar de un error 500."""
    def __init__(self, get_response):
        """Guarda la siguiente capa de Django."""
        self.get_response = get_response

    def __call__(self, request):
        """Pasa la petición sin cambios."""
        return self.get_response(request)

    def process_exception(self, request, exception):
        """Convierte errores de PostgreSQL en la página ``error_bd.html`` (503)."""
        if not isinstance(exception, (OperationalError, ProgrammingError)):
            return None
        mensaje, tipo = describir_error_bd(exception)
        registro_log.error("Error de base de datos: %s", exception)
        if request.path.startswith("/api/"):
            return JsonResponse({"ok": False, "mensaje": mensaje}, status=503)
        return render(request, "expresiones/error_bd.html",
                      {"mensaje": mensaje, "tipo": tipo, "detalle": str(exception)}, status=503)
