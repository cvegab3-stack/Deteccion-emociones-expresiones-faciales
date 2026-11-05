"""Objetos simulados para probar sin cámara ni rostros reales."""

import numpy as np

from vision import expresiones as cat

RECT = (200, 120, 200, 200)  # posición fija del "rostro" simulado


def fotograma(brillo=90):
    """Fotograma BGR 640x480 uniforme (el contenido lo decide el clasificador simulado)."""
    return np.full((480, 640, 3), brillo, dtype=np.uint8)


def probabilidades(clave, valor=0.9):
    """Distribución donde ``clave`` tiene ``valor`` y el resto se reparte."""
    resto = (1.0 - valor) / (len(cat.CLAVES) - 1)
    return {c: (valor if c == clave else resto) for c in cat.CLAVES}


class CapturaSimulada:
    """Imita ``cv2.VideoCapture``. Puede fallar tras ``falla_despues`` lecturas."""

    def __init__(self, fotogramas, falla_despues=None):
        self.fotogramas = fotogramas
        self.indice = 0
        self.falla_despues = falla_despues
        self.liberada = False

    def isOpened(self):
        return not self.liberada

    def read(self):
        if self.falla_despues is not None and self.indice >= self.falla_despues:
            return False, None
        cuadro = self.fotogramas[self.indice % len(self.fotogramas)].copy()
        self.indice += 1
        return True, cuadro

    def set(self, *args):
        return True

    def release(self):
        self.liberada = True


class DetectorSimulado:
    """Devuelve siempre el mismo rectángulo (o ninguno)."""

    def __init__(self, rect=RECT):
        self.rect = rect

    def rostro_principal(self, gris):
        return self.rect


class ClasificadorSimulado:
    """Devuelve siempre la misma distribución de probabilidades."""

    def __init__(self, clave="felicidad", valor=0.9):
        self.resultado = probabilidades(clave, valor)
        self.llamadas = 0

    def predecir(self, gris_rostro):
        self.llamadas += 1
        return dict(self.resultado)


class OyenteMemoria:
    """Guarda en listas lo que el gestor reporta (en lugar de PostgreSQL)."""

    def __init__(self):
        self.sesiones, self.registros, self.finalizadas = [], [], []

    def sesion_iniciada(self):
        self.sesiones.append(len(self.sesiones) + 1)
        return self.sesiones[-1]

    def expresion_registrada(self, sesion_id, clave, confianza):
        self.registros.append((sesion_id, clave, confianza))

    def sesion_finalizada(self, sesion_id, resumen):
        self.finalizadas.append((sesion_id, resumen))
