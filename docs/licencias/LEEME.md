# Licencias de componentes de terceros

| Componente | Dónde está | Licencia | Archivo |
|---|---|---|---|
| Modelo Emotion FER+ (Microsoft, ONNX Model Zoo) | `vision/modelos/emotion-ferplus-8.onnx` | MIT | `MIT-emotion-ferplus.txt` |
| Noto Emoji (Google) | `expresiones/static/expresiones/emojis/*.png` | Apache 2.0 (imágenes) / SIL OFL 1.1 (fuente) | `APACHE-2.0-noto-emoji.txt`, `OFL-1.1-noto-color-emoji.txt` |
| Haar Cascade frontal (OpenCV) | `vision/recursos/haarcascade_frontalface_default.xml` | Intel License Agreement (texto incluido dentro del XML) | `INTEL-haarcascade.txt` |
| Tutorial de Omes (OmesTutorials2020) | Idea inicial del proyecto | El repositorio original no declara licencia | Se cita como referencia; no se copió su código |

## Modelo FER+

- Descargado de la fuente oficial (Git LFS del repositorio `onnx/models`):
  <https://media.githubusercontent.com/media/onnx/models/main/validated/vision/body_analysis/emotion_ferplus/model/emotion-ferplus-8.onnx>
- SHA-256: `a2a2ba6a335a3b29c21acb6272f962bd3d47f84952aaffa03b60986e04efa61c`.
  Coincide con el puntero LFS publicado. También está en `vision/modelos/emotion-ferplus-8.onnx.sha256`.
- Se distribuye sin modificar.

## Cómo se obtuvieron los emojis

Los PNG (128 × 128 px, fondo transparente) se generaron desde la fuente
**Noto Color Emoji v2.047** de Google (proyecto `googlefonts/noto-emoji`). Ese
proyecto publica sus imágenes PNG/SVG bajo Apache 2.0 y la fuente bajo SIL OFL
1.1; se incluyen ambos textos. Solo se recortaron y escalaron, sin modificar
su diseño.

| Archivo | Emoji | Uso |
|---|---|---|
| `neutral.png` | 😐 U+1F610 | Neutral |
| `felicidad.png` | 😄 U+1F604 | Felicidad |
| `sorpresa.png` | 😮 U+1F62E | Sorpresa |
| `tristeza.png` | 😢 U+1F622 | Tristeza |
| `enojo.png` | 😠 U+1F620 | Enojo |
| `asco.png` | 🤢 U+1F922 | Asco |
| `desconocida.png` | 🤔 U+1F914 | Expresión no clara; "Otra" (registros antiguos de miedo o desprecio) |
| `sin_rostro.png` | 😶 U+1F636 | Cámara apagada / sin rostro |

Miedo y desprecio no se muestran (se excluyeron por baja fiabilidad), así
que sus emojis no se incluyen en el repositorio.
