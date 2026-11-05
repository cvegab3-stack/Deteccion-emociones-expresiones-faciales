"""
Clasificación de expresiones faciales con un modelo ya entrenado (FER+).

Modelo: ``emotion-ferplus-8.onnx`` del ONNX Model Zoo (Microsoft, licencia
MIT). Se ejecuta con el módulo DNN de OpenCV (``cv2.dnn``), sin TensorFlow
ni otras librerías de deep learning.

* Entrada: rostro en escala de grises de 64x64 píxeles, valores 0-255
  (sin normalizar ni restar la media), forma ``1x1x64x64``.
* Salida: 8 puntuaciones en el orden de ``expresiones.CLASES_MODELO``; se
  convierten en probabilidades con softmax.
* Después del softmax se **descartan miedo y desprecio** (índices 6 y 7,
  ``expresiones.CLASES_DESCARTADAS``) y las 6 probabilidades restantes se
  vuelven a normalizar para que sumen 1 (``seleccionar_visibles``). El
  mapeo índice del modelo -> clave visible es ``expresiones.INDICES_MODELO``.
"""

import hashlib
import threading
from pathlib import Path

import cv2
import numpy as np

from . import expresiones as cat

RUTA_MODELO = Path(__file__).resolve().parent / "modelos" / "emotion-ferplus-8.onnx"
SHA256_MODELO = "a2a2ba6a335a3b29c21acb6272f962bd3d47f84952aaffa03b60986e04efa61c"
TAMANO_ENTRADA = 64


class ErrorModelo(RuntimeError):
    """El modelo no existe, está dañado o no se pudo ejecutar."""


def softmax(puntuaciones):
    """Convierte puntuaciones en probabilidades que suman 1."""
    valores = np.asarray(puntuaciones, dtype=np.float64).ravel()
    exponentes = np.exp(valores - valores.max())
    return exponentes / exponentes.sum()


def seleccionar_visibles(probabilidades_modelo):
    """
    Recibe las 8 probabilidades del modelo (orden ``CLASES_MODELO``) y
    devuelve ``{clave visible: probabilidad}`` con las 6 expresiones del
    catálogo, normalizadas para que sumen 1. Miedo y desprecio se descartan.
    """
    p = np.asarray(probabilidades_modelo, dtype=np.float64).ravel()
    if p.size != len(cat.CLASES_MODELO):
        raise ErrorModelo(f"El modelo devolvió {p.size} valores; se esperaban {len(cat.CLASES_MODELO)}.")
    visibles = np.array([p[cat.INDICES_MODELO[clave]] for clave in cat.CLAVES])
    total = visibles.sum()
    visibles = visibles / total if total > 0 else np.full(len(cat.CLAVES), 1.0 / len(cat.CLAVES))
    return {clave: float(v) for clave, v in zip(cat.CLAVES, visibles, strict=True)}


def sha256_archivo(ruta):
    """Huella SHA-256 de un archivo (para verificar el modelo)."""
    huella = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        for bloque in iter(lambda: archivo.read(1 << 20), b""):
            huella.update(bloque)
    return huella.hexdigest()


class ClasificadorEmociones:
    """Envoltura segura entre hilos de la red FER+ cargada con ``cv2.dnn``."""

    def __init__(self, ruta_modelo=RUTA_MODELO):
        """Carga la red ONNX; lanza ``ErrorModelo`` si falta o está dañada."""
        self.ruta = Path(ruta_modelo)
        if not self.ruta.is_file():
            raise ErrorModelo(
                f"No se encontró el modelo de emociones en '{self.ruta}'. Coloque el archivo "
                "emotion-ferplus-8.onnx en vision/modelos/ (ver README, sección Modelo)."
            )
        try:
            self._red = cv2.dnn.readNetFromONNX(str(self.ruta))
        except cv2.error as exc:
            raise ErrorModelo(f"El archivo del modelo está dañado o es incompatible: {exc}") from exc
        self._red.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self._red.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        self._bloqueo = threading.Lock()

    @staticmethod
    def preparar(gris_rostro):
        """Rostro en gris (cualquier tamaño) -> blob 1x1x64x64 para la red."""
        rostro = cv2.resize(gris_rostro, (TAMANO_ENTRADA, TAMANO_ENTRADA), interpolation=cv2.INTER_AREA)
        return cv2.dnn.blobFromImage(rostro, scalefactor=1.0, size=(TAMANO_ENTRADA, TAMANO_ENTRADA), mean=0)

    def predecir(self, gris_rostro):
        """Devuelve ``{clave: probabilidad}`` para las 6 expresiones visibles (suman 1)."""
        blob = self.preparar(gris_rostro)
        try:
            with self._bloqueo:
                self._red.setInput(blob)
                salida = self._red.forward()
        except cv2.error as exc:
            raise ErrorModelo(f"Error al ejecutar el modelo: {exc}") from exc
        return seleccionar_visibles(softmax(salida))
