"""
Preprocesamiento del fotograma y del rostro antes de clasificarlo.

1. Escala de grises: el modelo FER+ trabaja con intensidades, no con color.
2. Recorte del rostro detectado por Haar Cascade, con un margen opcional.

No se ecualiza el histograma: FER+ se entrenó con imágenes en gris sin
ecualizar, y el redimensionado a 64x64 lo hace ``ClasificadorEmociones``.
"""

import cv2


def a_gris(fotograma_bgr):
    """Convierte un fotograma BGR a escala de grises."""
    return cv2.cvtColor(fotograma_bgr, cv2.COLOR_BGR2GRAY)


def recortar_rostro(gris, rectangulo, margen=0.0):
    """
    Recorta el rostro. ``margen`` > 0 amplía el recuadro y < 0 lo reduce
    (proporción del ancho y alto). Devuelve ``None`` si el recorte queda vacío.
    """
    x, y, w, h = rectangulo
    dx, dy = int(w * margen), int(h * margen)
    alto, ancho = gris.shape[:2]
    x1, y1 = max(0, x - dx), max(0, y - dy)
    x2, y2 = min(ancho, x + w + dx), min(alto, y + h + dy)
    if x2 <= x1 or y2 <= y1:
        return None
    return gris[y1:y2, x1:x2]
