"""
Sensibilidad respecto a la cara neutra de cada persona.

Con la cara relajada, FER+ suele dar "Neutral" con ~90 % y, aun con un
gesto claro, la otra expresión sube solo un poco (por ejemplo, Enojo pasa
de 3 % a 15 %), así que siempre ganaría Neutral. Por eso:

1. **Línea base.** Durante los primeros ``DURACION_CALIBRACION`` segundos
   con rostro visible se promedian las probabilidades crudas de FER+. Solo
   se guardan esos números en memoria; no se guardan imágenes. Mientras
   tanto se usa la decisión clásica: la expresión más probable si supera
   ``CONFIANZA_MINIMA``.
2. **Decisión por cambio.** Con línea base, para cada expresión distinta
   de neutral se calcula ``delta = p_actual - p_base``. Si el mayor delta
   llega a ``UMBRAL_CAMBIO``, esa es la expresión; si no, Neutral. La
   confianza que se muestra es la probabilidad actual de esa expresión.
3. **Ventana de votos.** La decisión de cada fotograma se cuenta en una
   ventana corta: una expresión se muestra solo si aparece en al menos
   ``VENTANA_MINIMO`` de los últimos ``VENTANA_FOTOGRAMAS`` fotogramas
   (3 de 5 por defecto), para que no parpadee.

La expresión depende **solo del modelo FER+**: la línea base no inventa
expresiones, solo compara las probabilidades con las de la cara relajada.
"""

from collections import Counter, deque
from dataclasses import dataclass, field

from . import expresiones as cat

NEUTRAL = "neutral"

# Estados de la calibración.
DESACTIVADA, CALIBRANDO, LISTA = "desactivada", "calibrando", "lista"


# =============================================================== ventana
class VentanaVotos:
    """
    Recuerda los últimos ``tamano`` valores. ``agregar`` devuelve el valor
    estable: el que aparece al menos ``minimo`` veces; si ninguno llega,
    se conserva el anterior.
    """

    def __init__(self, tamano=5, minimo=3):
        """``tamano``: fotogramas recordados; ``minimo``: votos para cambiar."""
        if not 1 <= minimo <= tamano:
            raise ValueError("Se requiere 1 <= minimo <= tamano")
        self.tamano, self.minimo = tamano, minimo
        self._valores = deque(maxlen=tamano)
        self.estable = None

    def reiniciar(self):
        """Olvida los votos y el valor estable."""
        self._valores.clear()
        self.estable = None

    def agregar(self, valor):
        """Agrega la decisión de un fotograma y devuelve el valor estable."""
        self._valores.append(valor)
        valor_mas_comun, veces = Counter(self._valores).most_common(1)[0]
        if veces >= self.minimo:
            self.estable = valor_mas_comun
        return self.estable


# ============================================================ línea base
class LineaBase:
    """Promedia las probabilidades de FER+ durante ``duracion`` segundos con rostro."""

    def __init__(self, duracion=3.0):
        """``duracion``: segundos con rostro que se promedian (0 = desactivada)."""
        self.duracion = float(duracion)
        self.reiniciar()

    @property
    def activa(self):
        """``False`` si ``DURACION_CALIBRACION`` es 0 (sin línea base)."""
        return self.duracion > 0

    def reiniciar(self):
        """Empieza una medición nueva."""
        self.segundos = 0.0
        self.lista = False
        self.probabilidades = None
        self._n = 0
        self._sumas = {clave: 0.0 for clave in cat.CLAVES}

    @property
    def progreso(self):
        """Avance de la medición, de 0 a 1."""
        if not self.activa:
            return 0.0
        return 1.0 if self.lista else min(1.0, self.segundos / self.duracion)

    @property
    def estado(self):
        """``desactivada``, ``calibrando`` o ``lista``."""
        if not self.activa:
            return DESACTIVADA
        return LISTA if self.lista else CALIBRANDO

    def agregar(self, dt, probabilidades):
        """Suma un fotograma con rostro. ``dt`` = segundos desde el anterior."""
        if not self.activa or self.lista:
            return
        self._n += 1
        for clave in cat.CLAVES:
            self._sumas[clave] += float(probabilidades[clave])
        self.segundos += max(0.0, float(dt))
        if self.segundos >= self.duracion:
            self.lista = True
            self.probabilidades = {c: s / self._n for c, s in self._sumas.items()}


# ============================================================== decisión
def decidir_por_cambio(actuales, base, umbral):
    """
    Devuelve ``(clave, deltas)``. ``deltas`` = {expresión no neutral:
    p_actual - p_base}. La clave es la del mayor delta si llega a ``umbral``;
    si no, ``"neutral"``.
    """
    deltas = {c: float(actuales[c]) - float(base[c]) for c in cat.CLAVES if c != NEUTRAL}
    clave = max(deltas, key=deltas.get)
    return (clave if deltas[clave] >= umbral else NEUTRAL), deltas


def decidir_clasico(probabilidades, confianza_minima):
    """Comportamiento sin línea base: la más probable si supera el mínimo; si no, ``None``."""
    clave = max(probabilidades, key=probabilidades.get)
    return clave if probabilidades[clave] >= confianza_minima else None


@dataclass
class ConfigDecision:
    """Parámetros de la decisión (vienen del archivo .env)."""
    confianza_minima: float = 0.40
    duracion_calibracion: float = 3.0   # 0 = sin línea base (comportamiento clásico)
    umbral_cambio: float = 0.08
    ventana: int = 5
    minimo_ventana: int = 3


@dataclass
class Decision:
    """Resultado de un fotograma: expresión, confianza y datos de la línea base."""
    clave: str | None                 # expresión mostrada (None = "no clara")
    confianza: float                  # 0-1
    calibracion: str                  # desactivada | calibrando | lista
    progreso: float                   # 0-1
    linea_base: dict | None           # probabilidades base (0-1)
    deltas: dict = field(default_factory=dict)


class MotorDecision:
    """Combina línea base, decisión por cambio y ventana de votos."""

    def __init__(self, config=None):
        """Crea la línea base y la ventana de votos."""
        self.config = config or ConfigDecision()
        c = self.config
        self.linea_base = LineaBase(c.duracion_calibracion)
        self._ventana = VentanaVotos(c.ventana, c.minimo_ventana)

    def nueva_linea_base(self):
        """Borra la línea base y empieza a medir de nuevo la cara neutra (al iniciar la cámara)."""
        self.linea_base.reiniciar()
        self.reiniciar_ventanas()

    def reiniciar_ventanas(self):
        """Se llama cuando se pierde el rostro: la línea base se conserva."""
        self._ventana.reiniciar()

    def actualizar(self, crudas, suavizadas, dt=0.0):
        """
        ``crudas``: probabilidades de FER+ de este fotograma (para la línea
        base). ``suavizadas``: promedio móvil (para decidir). ``dt``:
        segundos con rostro desde el fotograma anterior.
        """
        c, base = self.config, self.linea_base
        deltas = {}
        if not base.lista:
            base.agregar(dt, crudas)
        if base.lista:  # también el fotograma que completa la calibración
            candidata, deltas = decidir_por_cambio(suavizadas, base.probabilidades, c.umbral_cambio)
        else:
            candidata = decidir_clasico(suavizadas, c.confianza_minima)

        clave = self._ventana.agregar(candidata)
        confianza = suavizadas[clave] if clave else max(suavizadas.values())
        return Decision(
            clave=clave, confianza=float(confianza),
            calibracion=base.estado, progreso=base.progreso,
            linea_base=dict(base.probabilidades) if base.lista else None,
            deltas=deltas,
        )
