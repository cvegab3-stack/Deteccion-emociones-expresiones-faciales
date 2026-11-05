#!/usr/bin/env python
"""Utilidad de línea de comandos de Django (migrate, runserver, test, diagnostico...)."""

import os
import sys


def main():
    """Punto de entrada de los comandos de Django."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. ¿Activó el entorno virtual (venv\\Scripts\\activate) "
            "e instaló las dependencias con 'pip install -r requirements.txt'?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
