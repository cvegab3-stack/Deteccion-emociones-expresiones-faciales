"""
Dibujo de resultados directamente sobre el video con OpenCV.

``cv2.putText`` solo admite caracteres ASCII, por eso los textos del video
no llevan tildes (la interfaz web sí las tiene).

Sobre el video se dibuja solo lo esencial: el recuadro con esquinas del
color de la expresión, su nombre (sin porcentaje), el emoji Noto, la franja
inferior de aviso y "Sin rostro visible". Los porcentajes están en el panel.
"""

from pathlib import Path

import cv2
import numpy as np

FUENTE = cv2.FONT_HERSHEY_SIMPLEX
BLANCO = (255, 255, 255)
OSCURO = (35, 30, 30)


def cargar_emojis(carpeta, nombres, tamano=72):
    """
    Carga los PNG de Noto Emoji con canal alfa. Si alguno falta se omite
    (el video sigue funcionando sin emoji).
    """
    emojis = {}
    for nombre in nombres:
        ruta = Path(carpeta) / nombre
        imagen = cv2.imread(str(ruta), cv2.IMREAD_UNCHANGED)
        if imagen is None or imagen.ndim != 3 or imagen.shape[2] != 4:
            continue
        emojis[nombre] = cv2.resize(imagen, (tamano, tamano), interpolation=cv2.INTER_AREA)
    return emojis


def superponer_png(fondo, png_bgra, x, y):
    """Mezcla un PNG con transparencia sobre ``fondo`` en (x, y)."""
    alto, ancho = png_bgra.shape[:2]
    alto_f, ancho_f = fondo.shape[:2]
    x, y = int(x), int(y)
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(ancho_f, x + ancho), min(alto_f, y + alto)
    if x1 >= x2 or y1 >= y2:
        return fondo
    recorte = png_bgra[y1 - y:y2 - y, x1 - x:x2 - x]
    alfa = recorte[:, :, 3:4].astype(np.float32) / 255.0
    zona = fondo[y1:y2, x1:x2].astype(np.float32)
    fondo[y1:y2, x1:x2] = (alfa * recorte[:, :, :3] + (1.0 - alfa) * zona).astype(np.uint8)
    return fondo


def texto_con_fondo(imagen, texto, x, y, color_fondo, escala=0.6, grosor=1,
                    color_texto=BLANCO, relleno=6):
    """Escribe ``texto`` con una etiqueta rellena detrás; (x, y) = esquina inferior izquierda."""
    (ancho, alto), base = cv2.getTextSize(texto, FUENTE, escala, grosor)
    x = max(0, min(int(x), imagen.shape[1] - ancho - 2 * relleno))
    y = max(alto + 2 * relleno, int(y))
    cv2.rectangle(imagen, (x, y - alto - 2 * relleno), (x + ancho + 2 * relleno, y + base),
                  color_fondo, cv2.FILLED)
    cv2.putText(imagen, texto, (x + relleno, y - relleno + 2), FUENTE, escala,
                color_texto, grosor, cv2.LINE_AA)


def recuadro_rostro(imagen, rect, color, grosor=2):
    """Recuadro con esquinas resaltadas alrededor del rostro."""
    x, y, w, h = rect
    cv2.rectangle(imagen, (x, y), (x + w, y + h), color, grosor, cv2.LINE_AA)
    largo = max(12, w // 6)
    for (cx, cy, dx, dy) in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
        cv2.line(imagen, (cx, cy), (cx + dx * largo, cy), color, grosor + 3, cv2.LINE_AA)
        cv2.line(imagen, (cx, cy), (cx, cy + dy * largo), color, grosor + 3, cv2.LINE_AA)


def resultado_rostro(imagen, rect, texto, color, emoji=None):
    """Recuadro + etiqueta de la expresión + emoji junto al rostro."""
    recuadro_rostro(imagen, rect, color)
    x, y, w, _ = rect
    texto_con_fondo(imagen, texto, x, y - 4, color, escala=0.65, grosor=2)
    if emoji is not None:
        lado = emoji.shape[1]
        ex = x + w + 8 if x + w + 8 + lado <= imagen.shape[1] else x - lado - 8
        superponer_png(imagen, emoji, ex, y)


def barra_inferior(imagen, texto):
    """Franja semitransparente con un aviso en la parte inferior del video."""
    alto, ancho = imagen.shape[:2]
    capa = imagen.copy()
    cv2.rectangle(capa, (0, alto - 28), (ancho, alto), OSCURO, cv2.FILLED)
    cv2.addWeighted(capa, 0.6, imagen, 0.4, 0, imagen)
    cv2.putText(imagen, texto, (10, alto - 9), FUENTE, 0.45, BLANCO, 1, cv2.LINE_AA)


def mensaje_central(imagen, texto, color=(60, 60, 225)):
    """Mensaje destacado en la parte superior central (sin rostro, sin modelo...)."""
    (ancho, _), _ = cv2.getTextSize(texto, FUENTE, 0.7, 2)
    x = max(10, (imagen.shape[1] - ancho) // 2 - 6)
    texto_con_fondo(imagen, texto, x, 40, color, escala=0.7, grosor=2)
