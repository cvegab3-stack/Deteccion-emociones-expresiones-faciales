"""
Configuración de Django para el Detector de Expresiones Faciales.

Las credenciales y opciones se leen de variables de entorno (archivo
``.env`` en la raíz del proyecto). Copie ``.env.example`` a ``.env`` y
complete sus datos; ``.env`` no se sube a GitHub.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Oculta las advertencias internas de OpenCV al buscar cámaras; la aplicación
# muestra sus propios mensajes en español.
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")


def _bool(nombre, defecto=False):
    """Lee una variable de entorno como booleano (1, true, si, sí, yes)."""
    return os.getenv(nombre, str(defecto)).strip().lower() in {"1", "true", "si", "sí", "yes"}


def _numero(nombre, defecto, tipo=float):
    """Lee una variable de entorno numérica; si no es válida, lanza ImproperlyConfigured."""
    valor = os.getenv(nombre, "").strip()
    if not valor:
        return defecto
    try:
        return tipo(valor)
    except ValueError as exc:
        raise ImproperlyConfigured(f"La variable {nombre}='{valor}' debe ser numérica.") from exc


# --------------------------------------------------------------- seguridad
DEBUG = _bool("DJANGO_DEBUG", True)
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Defina DJANGO_SECRET_KEY en el archivo .env.")
    SECRET_KEY = "solo-para-desarrollo-cambie-esta-clave-en-env"

ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()]

# -------------------------------------------------------------- aplicaciones
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "expresiones",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "expresiones.middleware.ErroresBaseDatosMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ------------------------------------------------------------ PostgreSQL
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "detector_expresiones"),
        "USER": os.getenv("POSTGRES_USER", "postgres"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 5},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ------------------------------------------------- idioma y zona horaria
LANGUAGE_CODE = "es-ec"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "America/Guayaquil")
USE_I18N = True
USE_TZ = True

# ------------------------------------------------------ archivos estáticos
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------- visión por computadora
_fuente = os.getenv("CAMARA_FUENTE", "0").strip() or "0"

DETECTOR_EXPRESIONES = {
    # Índice de la cámara (0, 1, ...) o ruta de un archivo de video para pruebas.
    "CAMARA_FUENTE": int(_fuente) if _fuente.isdigit() else _fuente,
    "CAMARA_BACKEND": os.getenv("CAMARA_BACKEND", "auto").strip().lower(),
    "CAMARA_ANCHO": _numero("CAMARA_ANCHO", 640, int),
    "CAMARA_ALTO": _numero("CAMARA_ALTO", 480, int),
    "CAMARA_ESPEJO": _bool("CAMARA_ESPEJO", True),
    # Probabilidad mínima (0-1) para mostrar una expresión; si no, "no clara".
    # (Solo se usa mientras no hay línea base de la cara neutra.)
    "CONFIANZA_MINIMA": _numero("CONFIANZA_MINIMA", 0.40),
    # Peso del fotograma nuevo en el promedio móvil (0-1]: más alto = responde más rápido.
    "ALFA_SUAVIZADO": _numero("ALFA_SUAVIZADO", 0.5),
    "INTERVALO_REGISTRO": _numero("INTERVALO_REGISTRO", 1.0),
    # Modelo FER+ ya entrenado (ONNX), ejecutado con cv2.dnn.
    "MODELO_EMOCIONES": BASE_DIR / "vision" / "modelos" / "emotion-ferplus-8.onnx",
    "CARPETA_EMOJIS": BASE_DIR / "expresiones" / "static" / "expresiones" / "emojis",
    # Sensibilidad respecto a la cara neutra (README, sección "Sensibilidad respecto a su cara neutra").
    "DURACION_CALIBRACION": _numero("DURACION_CALIBRACION", 3.0),   # 0 = sin línea base
    "UMBRAL_CAMBIO": _numero("UMBRAL_CAMBIO", 0.08),
    "VENTANA_FOTOGRAMAS": _numero("VENTANA_FOTOGRAMAS", 5, int),
    "VENTANA_MINIMO": _numero("VENTANA_MINIMO", 3, int),
}

for _nombre, _minimo, _maximo in (
    ("CONFIANZA_MINIMA", 0.0, 1.0),
    ("ALFA_SUAVIZADO", 0.01, 1.0),
    ("DURACION_CALIBRACION", 0.0, 60.0),
    ("UMBRAL_CAMBIO", 0.0, 1.0),
    ("VENTANA_FOTOGRAMAS", 1, 30),
):
    if not _minimo <= DETECTOR_EXPRESIONES[_nombre] <= _maximo:
        raise ImproperlyConfigured(
            f"La variable {_nombre}={DETECTOR_EXPRESIONES[_nombre]} del archivo .env debe estar "
            f"entre {_minimo} y {_maximo}.")
if not 1 <= DETECTOR_EXPRESIONES["VENTANA_MINIMO"] <= DETECTOR_EXPRESIONES["VENTANA_FOTOGRAMAS"]:
    raise ImproperlyConfigured("VENTANA_MINIMO debe estar entre 1 y VENTANA_FOTOGRAMAS (por defecto 3 de 5).")

# ----------------------------------------------------------------- logs
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"consola": {"class": "logging.StreamHandler"}},
    "loggers": {"expresiones": {"handlers": ["consola"], "level": "INFO"}},
}
