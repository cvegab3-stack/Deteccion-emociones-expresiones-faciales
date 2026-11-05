"""
Suavizado temporal de las probabilidades.

Una predicción por fotograma "parpadea". Se usa un promedio móvil
exponencial: cada fotograma nuevo aporta un ``alfa`` (por defecto 35 %)
y el resto viene del historial. Así el resultado es estable, pero sigue
respondiendo rápido cuando la persona cambia de expresión.
"""

from . import expresiones as cat


class SuavizadorProbabilidades:
    """Promedio móvil exponencial de las probabilidades entre fotogramas."""
    def __init__(self, alfa=0.35, confianza_minima=0.40):
        """``alfa``: peso del fotograma nuevo (0-1]; ``confianza_minima``: umbral de «no clara»."""
        if not 0 < alfa <= 1:
            raise ValueError("alfa debe estar entre 0 y 1")
        self.alfa = alfa
        self.confianza_minima = confianza_minima
        self._promedio = None

    def reiniciar(self):
        """Olvida el historial (por ejemplo, cuando se pierde el rostro)."""
        self._promedio = None

    @property
    def probabilidades(self):
        """Probabilidades suavizadas actuales (todas en 0 si no hay datos)."""
        if self._promedio is None:
            return {clave: 0.0 for clave in cat.CLAVES}
        return dict(self._promedio)

    def agregar(self, probabilidades):
        """
        Incorpora las probabilidades de un fotograma y devuelve
        ``(clave_estimada, confianza)``. ``clave_estimada`` es ``None`` si la
        mayor probabilidad no alcanza ``confianza_minima``.
        """
        if self._promedio is None:
            self._promedio = dict(probabilidades)
        else:
            a = self.alfa
            self._promedio = {c: a * probabilidades[c] + (1 - a) * self._promedio[c] for c in cat.CLAVES}
        clave = max(self._promedio, key=self._promedio.get)
        confianza = self._promedio[clave]
        if confianza < self.confianza_minima:
            return None, confianza
        return clave, confianza
