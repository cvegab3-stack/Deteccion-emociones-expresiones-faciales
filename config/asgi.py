"""
Configuración ASGI del proyecto detector_expresiones.

Expone el objeto ``application`` que usan los servidores ASGI. Para el
desarrollo local basta con ``python manage.py runserver``.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
