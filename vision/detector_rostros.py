"""
Detección de rostros con el clasificador Haar Cascade de OpenCV.

Se usa el archivo ``haarcascade_frontalface_default.xml`` (Intel License,
incluido en OpenCV). Se copia dentro del proyecto para no depender de
``cv2.data``, que no está presente en todas las instalaciones.
"""

from pathlib import Path

import cv2

RUTA_CASCADA = Path(__file__).resolve().parent / "recursos" / "haarcascade_frontalface_default.xml"


class ErrorDetector(RuntimeError):
    """El clasificador no se pudo cargar (archivo ausente o dañado)."""


class DetectorRostros:
    """Encuentra rostros frontales en una imagen en escala de grises."""

    def __init__(self, ruta_cascada=RUTA_CASCADA, factor_escala=1.2,
                 vecinos_minimos=5, tamano_minimo=80, ancho_trabajo=320):
        """Carga el Haar Cascade; lanza ``ErrorDetector`` si falta o está dañado."""
        ruta = Path(ruta_cascada)
        if not ruta.is_file():
            raise ErrorDetector(f"No se encontró el detector de rostros: {ruta}")
        self._clasificador = cv2.CascadeClassifier(str(ruta))
        if self._clasificador.empty():
            raise ErrorDetector(f"El archivo del detector está dañado: {ruta}")
        self.factor_escala = factor_escala
        self.vecinos_minimos = vecinos_minimos
        self.tamano_minimo = tamano_minimo
        # Se detecta sobre una copia reducida para ganar velocidad.
        self.ancho_trabajo = ancho_trabajo

    def detectar(self, gris):
        """
        Devuelve una lista de rectángulos ``(x, y, ancho, alto)`` en
        coordenadas de la imagen original, ordenados del más grande al
        más pequeño.
        """
        alto, ancho = gris.shape[:2]
        escala = 1.0
        imagen = gris
        if ancho > self.ancho_trabajo:
            escala = self.ancho_trabajo / ancho
            imagen = cv2.resize(gris, (self.ancho_trabajo, int(alto * escala)),
                                interpolation=cv2.INTER_AREA)
        minimo = max(20, int(self.tamano_minimo * escala))
        rostros = self._clasificador.detectMultiScale(
            imagen,
            scaleFactor=self.factor_escala,
            minNeighbors=self.vecinos_minimos,
            minSize=(minimo, minimo),
        )
        resultado = [
            (int(x / escala), int(y / escala), int(w / escala), int(h / escala))
            for (x, y, w, h) in rostros
        ]
        resultado.sort(key=lambda r: r[2] * r[3], reverse=True)
        return resultado

    def rostro_principal(self, gris):
        """Devuelve el rostro más grande (el más cercano) o ``None``."""
        rostros = self.detectar(gris)
        return rostros[0] if rostros else None
