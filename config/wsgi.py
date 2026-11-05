"""
Configuración WSGI del proyecto detector_expresiones.

Expone el objeto ``application`` que usan los servidores WSGI. Para el
desarrollo local basta con ``python manage.py runserver``.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
