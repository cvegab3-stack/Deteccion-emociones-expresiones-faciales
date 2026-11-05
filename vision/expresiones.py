"""
Catálogo único de las expresiones faciales que muestra la aplicación.

El modelo ``emotion-ferplus-8.onnx`` devuelve SIEMPRE 8 valores, en el orden
de ``CLASES_MODELO`` (no se debe cambiar). La aplicación muestra solo 6:
**miedo y desprecio se excluyeron** porque no se detectan de forma fiable
con una cámara web. ``ClasificadorEmociones`` descarta esas dos salidas y
vuelve a normalizar las 6 restantes para que sumen 1.

Mapeo índice del modelo -> clave visible::

    0 neutral    -> neutral
    1 happiness  -> felicidad
    2 surprise   -> sorpresa
    3 sadness    -> tristeza
    4 anger      -> enojo
    5 disgust    -> asco
    6 fear       -> (miedo, descartada)
    7 contempt   -> (desprecio, descartada)

Lo usan el módulo de visión (nombres y colores del dibujo) y Django
(opciones de los modelos y la interfaz), así que la interfaz nunca muestra
una clase que no esté aquí. Los registros antiguos de la base de datos con
"miedo" o "desprecio" se muestran como **"Otra"** (``obtener_o_otra``).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Expresion:
    """Datos de una expresión del catálogo (nombre, emoji y colores)."""
    clave: str            # identificador interno (se guarda en la base de datos)
    nombre: str           # nombre visible en la interfaz (español)
    nombre_video: str     # nombre sin tildes para cv2.putText (solo admite ASCII)
    emoji: str            # PNG de Noto Emoji en static/expresiones/emojis/
    color_bgr: tuple      # color del recuadro en el video (formato BGR de OpenCV)
    color_hex: str        # mismo color para la interfaz web


# Las 8 salidas del modelo FER+, en su orden (neutral, happiness, surprise,
# sadness, anger, disgust, fear, contempt), con la clave en español.
CLASES_MODELO = ("neutral", "felicidad", "sorpresa", "tristeza", "enojo", "asco", "miedo", "desprecio")

# Clases del modelo que la aplicación descarta por baja fiabilidad.
CLASES_DESCARTADAS = ("miedo", "desprecio")

# Expresiones visibles (6), en el mismo orden relativo que el modelo.
EXPRESIONES = (
    Expresion("neutral", "Neutral", "Neutral", "neutral.png", (176, 160, 140), "#8ca0b0"),
    Expresion("felicidad", "Felicidad", "Felicidad", "felicidad.png", (40, 190, 250), "#fabe28"),
    Expresion("sorpresa", "Sorpresa", "Sorpresa", "sorpresa.png", (200, 90, 160), "#a05ac8"),
    Expresion("tristeza", "Tristeza", "Tristeza", "tristeza.png", (220, 140, 50), "#328cdc"),
    Expresion("enojo", "Enojo", "Enojo", "enojo.png", (60, 60, 225), "#e13c3c"),
    Expresion("asco", "Asco", "Asco", "asco.png", (80, 170, 90), "#5aaa50"),
)

CLAVES = tuple(e.clave for e in EXPRESIONES)
POR_CLAVE = {e.clave: e for e in EXPRESIONES}

# Índice de la salida del modelo para cada clave visible: {"neutral": 0, ..., "asco": 5}.
INDICES_MODELO = {clave: CLASES_MODELO.index(clave) for clave in CLAVES}

# Emojis para estados especiales (no son clases del modelo).
EMOJI_DESCONOCIDA = "desconocida.png"   # hay rostro, pero ninguna expresión es clara
EMOJI_SIN_ROSTRO = "sin_rostro.png"     # cámara apagada o sin rostro visible

# Registros antiguos con una clave que ya no está en el catálogo (miedo, desprecio).
OTRA = Expresion("otra", "Otra", "Otra", EMOJI_DESCONOCIDA, (180, 180, 180), "#b4b4b4")


def obtener(clave):
    """Devuelve la expresión por su clave o ``None`` si no existe."""
    return POR_CLAVE.get(clave)


def obtener_o_otra(clave):
    """
    Para datos guardados: la expresión del catálogo, ``OTRA`` si la clave
    ya no existe (p. ej. "miedo" de una versión anterior) o ``None`` si está vacía.
    """
    if not clave:
        return None
    return POR_CLAVE.get(clave, OTRA)


def opciones_django():
    """Lista ``(clave, nombre)`` para el parámetro ``choices`` de Django."""
    return [(e.clave, e.nombre) for e in EXPRESIONES]
