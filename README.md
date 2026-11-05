# ExpresaVisión: detector de expresiones faciales en tiempo real

Aplicación web en **Django** que captura la cámara de la computadora, la
procesa con **OpenCV**, **detecta el rostro** y **estima su expresión facial**
con un **modelo ya entrenado (FER+)**. El resultado se dibuja sobre el video y
cada sesión se guarda en **PostgreSQL** para consultarla en el *Historial*.

Basta con abrir la página y pulsar **Iniciar cámara**: no hay que entrenar
nada.

> La aplicación muestra una **estimación de la expresión visible del rostro**.
> No determina cómo se siente realmente la persona.

Proyecto de la práctica G003-S12 de Construcción de Software. Enfoque:
*Detección de emociones mediante expresiones faciales*.

---

## Contenido

1. [Qué hace](#1-qué-hace)
2. [Las 6 expresiones](#2-las-6-expresiones)
3. [Cómo funciona](#3-cómo-funciona)
4. [Qué se guarda y cómo funciona el Historial](#4-qué-se-guarda-y-cómo-funciona-el-historial)
5. [Tecnologías y versiones](#5-tecnologías-y-versiones)
6. [Instalación en Windows 11](#6-instalación-en-windows-11)
7. [Uso](#7-uso)
8. [Configuración (.env)](#8-configuración-env)
9. [Pruebas](#9-pruebas)
10. [Solución de errores frecuentes](#10-solución-de-errores-frecuentes)
11. [Estructura del proyecto](#11-estructura-del-proyecto)
12. [Créditos y licencias](#12-créditos-y-licencias)
13. [Limitaciones](#13-limitaciones)

---

## 1. Qué hace

| Página | Contenido |
|---|---|
| **En vivo** | Video en tiempo real con el resultado dibujado por OpenCV, botón **Iniciar cámara / Detener**, indicador de FPS, la **expresión estimada** (emoji, nombre y porcentaje) y las **probabilidades en vivo** de las 6 expresiones. |
| **Historial** | Lista de sesiones guardadas en PostgreSQL. Cada una tiene su detalle: duración, expresión predominante, % de rostro visible, línea de tiempo y distribución. Se pueden eliminar. |
| **Cómo funciona** | Explicación del proceso, de los datos que se guardan y de los límites. |

Mensajes claros cuando la cámara no está disponible (o Windows bloqueó el
permiso), se pierde la señal, no hay rostro visible, ninguna expresión es
clara, falta el modelo o PostgreSQL no responde.

## 2. Las 6 expresiones

| Expresión | Emoji | Cómo provocarla |
|---|---|---|
| Neutral | 😐 | Cara relajada |
| Felicidad | 😄 | Sonrisa amplia |
| Sorpresa | 😮 | Boca abierta y cejas arriba |
| Tristeza | 😢 | Comisuras hacia abajo |
| Enojo | 😠 | Ceño fruncido |
| Asco | 🤢 | Arrugar la nariz y levantar el labio superior |

El modelo FER+ también estima **miedo** y **desprecio**, pero **se
excluyeron** porque con una cámara web casi nunca se detectaban o aparecían
por error. `ClasificadorEmociones` descarta esas dos salidas y vuelve a
normalizar las 6 restantes para que sumen 100 %. El mapeo está documentado en
`vision/expresiones.py`:

| Índice del modelo | Clase FER+ | Clave en la aplicación |
|---|---|---|
| 0 | neutral | `neutral` |
| 1 | happiness | `felicidad` |
| 2 | surprise | `sorpresa` |
| 3 | sadness | `tristeza` |
| 4 | anger | `enojo` |
| 5 | disgust | `asco` |
| 6 | fear | descartada |
| 7 | contempt | descartada |

## 3. Cómo funciona

Cada fotograma pasa por estas etapas (todas con OpenCV):

```
cámara (cv2.VideoCapture)
  → procesamiento: espejo (cv2.flip), escala de grises (cv2.cvtColor)
  → detección del rostro: Haar Cascade (cv2.CascadeClassifier)
  → reconocimiento: recorte 64×64 + modelo FER+ ONNX (cv2.dnn), softmax, 6 clases
  → suavizado entre fotogramas y decisión (línea base automática)
  → dibujo sobre el video (cv2.rectangle, cv2.line, cv2.putText, emoji PNG)
  → JPEG (cv2.imencode) → navegador como MJPEG
```

1. **Captura.** Un hilo lee la cámara de `CAMARA_FUENTE` (por defecto `0`, la
   integrada). Hay una sola cámara: la interfaz no tiene selector.
2. **Procesamiento.** El fotograma se voltea como espejo y se pasa a escala de
   grises.
3. **Detección.** El clasificador Haar Cascade frontal busca rostros; se
   analiza el más grande (el más cercano).
4. **Reconocimiento.** El rostro se recorta, se redimensiona a 64 × 64 y se
   pasa por el modelo **FER+** con `cv2.dnn`. El softmax da 8
   probabilidades; se descartan miedo y desprecio y las 6 restantes se
   normalizan.
5. **Suavizado.** Las probabilidades se promedian entre fotogramas (promedio
   móvil con `ALFA_SUAVIZADO`). Una expresión solo se muestra si se mantiene
   en 3 de los últimos 5 fotogramas, para que no parpadee.
6. **Línea base automática.** Con la cara relajada, FER+ suele dar "Neutral"
   con ~88 %, y aun con un gesto claro la otra expresión sube poco (por
   ejemplo, Enojo de 4 % a 15 %). Por eso:
   - durante los primeros **3 s con rostro visible** después de pulsar
     *Iniciar cámara*, la aplicación promedia las probabilidades de su cara
     (la **línea base**). Es **automático y no se muestra**: no hay botón ni
     aviso. Mientras tanto se usa el comportamiento normal del modelo (la
     expresión más probable si supera `CONFIANZA_MINIMA`);
   - después, para cada expresión distinta de neutral se calcula
     `delta = p_actual − p_base`. Si el mayor delta llega a `UMBRAL_CAMBIO`
     (8 puntos), esa es la expresión estimada; si no, "Neutral";
   - la línea base se vuelve a medir cada vez que inicia la cámara. Solo se
     guardan esos promedios en memoria: no se guardan imágenes.
7. **Dibujo sobre el video.** OpenCV dibuja el **recuadro** del rostro con
   esquinas del color de la expresión, su **nombre** encima (sin porcentaje,
   o "Expresion no clara") y el **emoji** Noto al lado. Abajo hay una franja
   fija: "Estimacion de expresion facial: no determina emociones reales". Si
   no hay rostro, aparece "Sin rostro visible". Los porcentajes se ven en el
   panel web.
8. **Panel web.** Consulta `/api/estado/` varias veces por segundo. La
   cabecera "Expresión estimada" y la fila resaltada de "Probabilidades en
   vivo" muestran **el mismo porcentaje**: ambos salen de
   `estado.probabilidades[estado.expresion]` redondeado con `Math.round`.

**Modelo FER+**

| Aspecto | Detalle |
|---|---|
| Archivo | `vision/modelos/emotion-ferplus-8.onnx` (34 MB, incluido en el repositorio) |
| Autor y fuente | Microsoft, [ONNX Model Zoo](https://github.com/onnx/models/tree/main/validated/vision/body_analysis/emotion_ferplus). Artículo: Barsoum et al., 2016 ([arXiv:1608.01041](https://arxiv.org/abs/1608.01041)) |
| Licencia | MIT |
| Entrenamiento | Imágenes de FER-2013 con las etiquetas FER+ |
| Entrada / salida | Rostro gris 64×64 (`1x1x64x64`) → 8 puntuaciones |
| Ejecución | `cv2.dnn.readNetFromONNX`, en CPU (sin TensorFlow ni GPU) |
| SHA-256 | `a2a2ba6a335a3b29c21acb6272f962bd3d47f84952aaffa03b60986e04efa61c` |

## 4. Qué se guarda y cómo funciona el Historial

| Tabla en PostgreSQL | Contenido |
|---|---|
| `expresiones_sesionanalisis` | Inicio, fin, estado, expresión predominante, número de registros, fotogramas procesados y fotogramas con rostro |
| `expresiones_registroexpresion` | Una fila por segundo: expresión estimada, confianza (%) y hora |

- **Al pulsar *Iniciar cámara*** se crea una sesión. Si una sesión anterior
  quedó abierta por un cierre inesperado, se marca como *Interrumpida*.
- **Cada segundo** (`INTERVALO_REGISTRO`) se guarda la expresión estimada en
  ese momento y su porcentaje (el mismo que muestra el panel).
- **Al pulsar *Detener*** se calculan el fin, la expresión predominante (la
  más registrada), el total de registros y el % de fotogramas con rostro.
- En **Historial** se listan las sesiones; *Ver detalle* muestra los
  indicadores, la **línea de tiempo** (un bloque por segundo, del color de la
  expresión) y la **distribución**. Las sesiones se pueden eliminar.
- Los registros de versiones anteriores con miedo o desprecio no se borran:
  aparecen agrupados como **"Otra"**.

**No se guardan fotos ni video.** Cada fotograma se procesa en memoria y se
descarta.

## 5. Tecnologías y versiones

| Componente | Requerido | Versión probada |
|---|---|---|
| Windows | 11 | Windows 11 |
| Python | 3.11 a 3.13 (**recomendado 3.12**) | 3.12.10 |
| Django | 5.2 LTS | 5.2.19 |
| OpenCV | `opencv-contrib-python` 4.10 o superior | 5.0.0 |
| NumPy | 1.26 o superior | 2.5.4 |
| PostgreSQL | 14 o superior | 17.11 |
| psycopg | 3.2 o superior | 3.3.8 |
| python-dotenv | 1.0 o superior | 1.2.4 |

La interfaz no usa CDN (iconos SVG en línea) y funciona sin internet.

## 6. Instalación en Windows 11

Use **PowerShell** (en VS Code: `Ctrl + ñ`) dentro de la carpeta del
proyecto, donde está `manage.py`.

### 6.1 Requisitos previos

1. **Python 3.12** desde <https://www.python.org/downloads/windows/>. Marque
   *"Add python.exe to PATH"* al instalar.
2. **PostgreSQL 17** desde <https://www.postgresql.org/download/windows/>.
   Anote la contraseña del usuario `postgres` y deje el puerto 5432 (no hace
   falta Stack Builder).
3. Una cámara web.

### 6.2 Entorno virtual y dependencias

```powershell
py -3.12 -m venv venv
venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Si PowerShell bloquea la activación, ejecute una vez
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### 6.3 Base de datos

Abra psql como `postgres` (cambie `17` por su versión si es distinta):

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres
```

Dentro de psql, con una contraseña suya:

```sql
CREATE USER expresiones_app WITH PASSWORD 'su_contrasena' CREATEDB;
CREATE DATABASE detector_expresiones OWNER expresiones_app;
\q
```

(`CREATEDB` permite que `python manage.py test` cree su base temporal.)

### 6.4 Variables de entorno

```powershell
Copy-Item .env.example .env
notepad .env
```

En `.env`, escriba la misma contraseña en `POSTGRES_PASSWORD` y una clave
larga en `DJANGO_SECRET_KEY`. El archivo `.env` no se sube a GitHub.

### 6.5 Modelo

**Ya viene incluido** en `vision/modelos/emotion-ferplus-8.onnx`. Solo si
falta:

1. Descárguelo de
   <https://media.githubusercontent.com/media/onnx/models/main/validated/vision/body_analysis/emotion_ferplus/model/emotion-ferplus-8.onnx>
2. Guárdelo en `vision/modelos/emotion-ferplus-8.onnx`.
3. Compruebe la huella:
   `Get-FileHash vision\modelos\emotion-ferplus-8.onnx -Algorithm SHA256`.

### 6.6 Ejecutar

```powershell
python manage.py migrate
python manage.py diagnostico --camara
python manage.py runserver
```

- `diagnostico` revisa OpenCV, el modelo (huella e inferencia de prueba), los
  emojis, la línea base, PostgreSQL, las migraciones y la cámara.
- Con todo en `[OK]`, abra **<http://127.0.0.1:8000>**.
- Para detener el servidor: `Ctrl + C`.

## 7. Uso

1. En **En vivo**, pulse **Iniciar cámara**. Mantenga la **cara relajada**
   los primeros 3 s: la línea base se mide sola, sin avisos.
2. Sobre el video verá el recuadro del color de la expresión, su nombre y el
   emoji.
3. A la derecha se actualizan la **expresión estimada** y las **6 barras de
   probabilidad**; la fila de la expresión estimada se resalta.
4. Bajo el video están solo el botón **Iniciar cámara / Detener** y el
   indicador de **FPS**.
5. Pulse **Detener** para terminar. El resumen de la sesión está en
   **Historial** → *Ver detalle*.

**Para una buena demostración:** rostro de frente, buena luz, a unos 50 cm y
gestos claros (ver la tabla de la [sección 2](#2-las-6-expresiones)).

**Probar sin cámara:** en `.env` ponga `CAMARA_FUENTE=C:/ruta/video.mp4`. El
video se repite en bucle.

## 8. Configuración (.env)

Todas las variables están explicadas en `.env.example`.

| Variable | Defecto | Para qué sirve |
|---|---|---|
| `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_TIME_ZONE` | | Django |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` | | Conexión a PostgreSQL |
| `CAMARA_FUENTE` | `0` | Cámara a usar (0 = integrada) o ruta de un video. Reinicie el servidor tras cambiarla |
| `CAMARA_BACKEND` | `auto` | `auto`, `dshow`, `msmf` o `any` |
| `CAMARA_ANCHO`, `CAMARA_ALTO` | `640`, `480` | Resolución pedida a la cámara |
| `CAMARA_ESPEJO` | `True` | Voltear la imagen como un espejo |
| `CONFIANZA_MINIMA` | `0.40` | Mínimo para mostrar una expresión mientras no hay línea base |
| `ALFA_SUAVIZADO` | `0.5` | Peso del fotograma nuevo en el promedio móvil |
| `INTERVALO_REGISTRO` | `1` | Segundos entre registros en PostgreSQL |
| `DURACION_CALIBRACION` | `3` | Segundos con rostro para la línea base (0 = sin línea base) |
| `UMBRAL_CAMBIO` | `0.08` | Cuánto debe subir una expresión sobre la línea base |
| `VENTANA_FOTOGRAMAS`, `VENTANA_MINIMO` | `5`, `3` | Una expresión se muestra si aparece en 3 de los últimos 5 fotogramas |

Para ver la línea base y los deltas en vivo, abra
<http://127.0.0.1:8000/api/estado/> con la cámara encendida.

## 9. Pruebas

```powershell
python manage.py test
```

**73 pruebas automáticas** (sin cámara real; usan una cámara, un detector y un
clasificador simulados, y una base PostgreSQL temporal):

- **Modelo real con `cv2.dnn`** (`test_vision.py`): huella, 6 probabilidades
  que suman 1 (miedo y desprecio descartados y renormalizados), mapeo del
  modelo, determinismo, error claro si falta o está dañado.
- **Lógica de visión:** softmax, suavizado y "no clara", detector, recorte,
  dibujo (sin porcentajes sobre el video).
- **GestorCamara:** cámara no disponible o sin imagen, pérdida de señal, sin
  rostro, modelo faltante, fallo de base de datos sin detener el video,
  `confianza` idéntica a la probabilidad de la expresión, un registro por
  segundo con el intervalo por defecto.
- **Línea base** (`test_sensibilidad.py`): decisión por cambio, ventana 3 de
  5, línea base automática, siempre la cámara de la configuración.
- **Django con PostgreSQL** (`test_web.py`): páginas, API, MJPEG, flujo
  completo (sesión creada al iniciar, registros, fin, predominante, % de
  rostro, Historial y detalle), registros antiguos como "Otra", eliminación,
  página de ayuda si PostgreSQL no responde.

**Prueba manual con la cámara:**

1. `python manage.py diagnostico --camara` debe mostrar todo `[OK]`.
2. En vivo → Iniciar cámara → cara relajada 3 s. Luego: sonrisa → Felicidad;
   boca abierta y cejas arriba → Sorpresa; ceño fruncido → Enojo.
3. Salga del encuadre: debe aparecer "Sin rostro visible".
4. Detener → Historial → Ver detalle.
5. Detenga el servicio de PostgreSQL y abra Historial: debe aparecer la
   página de ayuda.

## 10. Solución de errores frecuentes

| Problema | Solución |
|---|---|
| *"No se pudo abrir la cámara 0"* | Cierre Zoom, Teams o la app Cámara. Active *Configuración > Privacidad y seguridad > Cámara* (incluida "Permitir que las aplicaciones de escritorio accedan"). Con varias cámaras, pruebe `CAMARA_FUENTE=1` y reinicie el servidor. |
| Video lento o negro | Pruebe `CAMARA_BACKEND=msmf` (o `dshow`) en `.env` y reinicie el servidor. |
| *"No se encontró el modelo de emociones"* | Falta `vision/modelos/emotion-ferplus-8.onnx` (ver [6.5](#65-modelo)). |
| Casi siempre "Expresión no clara" al empezar | Mejore la luz y marque más los gestos, o baje `CONFIANZA_MINIMA` a 0.30. |
| Siempre "Neutral" aunque haga gestos | Detenga e inicie la cámara con la cara relajada (se vuelve a medir la línea base). Si sigue, baje `UMBRAL_CAMBIO` (0.05). |
| Aparecen expresiones sin hacer gestos | Suba `UMBRAL_CAMBIO` (0.12) o reinicie la cámara con la cara relajada: quizá empezó sonriendo. |
| Cambia de expresión con facilidad | Baje `ALFA_SUAVIZADO` (0.35) o use `VENTANA_MINIMO=4`. |
| *"No se pudo conectar a PostgreSQL"* | En *Servicios* de Windows, verifique que `postgresql-x64-17` esté *En ejecución*. Revise `POSTGRES_*` en `.env`. |
| `password authentication failed` | La contraseña de `.env` no coincide. Cámbiela en psql: `ALTER USER expresiones_app WITH PASSWORD '...';` |
| *"Las tablas no existen"* | `python manage.py migrate` |
| `permission denied to create database` al ejecutar `test` | En psql, como `postgres`: `ALTER USER expresiones_app CREATEDB;` |
| `'psql' no se reconoce` | Use la ruta completa: `& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres` |
| Puerto 8000 ocupado | `python manage.py runserver 8080` |
| "Otra" en el historial | Son registros de versiones anteriores con miedo o desprecio. |

## 11. Estructura del proyecto

```
detector_expresiones/
├── manage.py · requirements.txt · .env.example · .gitignore · README.md
├── config/                    # configuración de Django (settings, urls, asgi, wsgi)
├── vision/                    # módulo OpenCV, independiente de Django
│   ├── camara.py              # GestorCamara: hilo de captura, procesamiento, registro y MJPEG
│   ├── detector_rostros.py    # detección Haar Cascade
│   ├── preprocesamiento.py    # escala de grises y recorte del rostro
│   ├── clasificador.py        # modelo FER+ con cv2.dnn (softmax, 8 clases → 6 visibles)
│   ├── suavizado.py           # promedio móvil de probabilidades
│   ├── sensibilidad.py        # línea base automática, decisión por cambio, ventana 3 de 5
│   ├── dibujo.py              # recuadro, nombre, emoji y avisos sobre el video
│   ├── expresiones.py         # catálogo de las 6 expresiones y mapeo del modelo
│   ├── modelos/               # emotion-ferplus-8.onnx (+ .sha256)
│   └── recursos/              # haarcascade_frontalface_default.xml
├── expresiones/               # aplicación Django
│   ├── models.py              # SesionAnalisis, RegistroExpresion
│   ├── views.py · urls.py     # páginas, API JSON y video MJPEG
│   ├── servicios.py           # puente visión → PostgreSQL y gestor único de la cámara
│   ├── middleware.py          # página de ayuda si falla PostgreSQL
│   ├── admin.py · apps.py
│   ├── management/commands/diagnostico.py
│   ├── migrations/            # 0001 a 0003
│   ├── templates/expresiones/ # base, panel, _video, _icono, historial, detalle, acerca, error_bd
│   ├── static/expresiones/    # css/estilos.css, js/comun.js, js/panel.js, emojis/ (Noto)
│   └── tests/                 # test_vision.py, test_sensibilidad.py, test_web.py, utilidades.py
└── docs/licencias/            # licencias del modelo, Noto Emoji y Haar Cascade
```

El paquete `vision` no importa Django. Avisa de los eventos (sesión iniciada,
expresión registrada, sesión finalizada) a un *oyente*, y
`expresiones/servicios.py` los guarda en PostgreSQL. Gracias a esto la visión
se prueba con una cámara simulada.

## 12. Créditos y licencias

- **Modelo FER+** (Microsoft, ONNX Model Zoo, MIT): se usa sin modificar.
- **Noto Emoji** (Google, Apache 2.0 / SIL OFL 1.1).
- **Haar Cascade frontal** (OpenCV, Intel License Agreement).
- **OpenCV** (Apache 2.0), **Django** (BSD-3), **psycopg** (LGPL-3.0),
  **NumPy** (BSD-3), **python-dotenv** (BSD-3).
- **Idea inicial:** tutorial de reconocimiento de emociones de **Omes**
  (<https://omes-va.com/reconocimiento-de-emociones-opencv-python/>). No se
  copió su código.
- Se descartaron repositorios que dependen de TensorFlow/Keras, dlib o
  MediaPipe (la guía exige OpenCV y esas librerías son pesadas o difíciles de
  instalar en Windows) y los que no tienen una licencia clara.

Los textos de las licencias y el origen de cada archivo están en
`docs/licencias/`.

## 13. Limitaciones

- **Es una estimación de la expresión visible**, no del estado emocional ni
  del ánimo real de la persona.
- Con gestos sutiles, FER+ tiende a responder **"Neutral"**. La línea base lo
  compensa en parte, pero tristeza, enojo y asco necesitan gestos marcados.
- **Miedo y desprecio no se estiman** (se excluyeron por baja fiabilidad).
  Un rostro con esas expresiones se mostrará como la expresión visible más
  parecida.
- Si empieza la sesión con un gesto (por ejemplo, sonriendo), esa expresión
  queda como "neutra": detenga e inicie la cámara con la cara relajada.
- **El detector Haar solo encuentra rostros de frente.** Le afectan la mala
  iluminación, los lentes oscuros, el cubrebocas y la cabeza muy inclinada.
- Se analiza **un rostro a la vez**: el más grande.
- FER-2013 son fotos de internet en baja resolución: **el modelo puede tener
  sesgos** según la edad, el tono de piel o la cultura.
- Pensado para un usuario y una cámara local, con el servidor de desarrollo
  de Django. **No está preparado para publicarse en internet**: el servidor
  abre la cámara del propio equipo.
