# Práctica 4: Pruebas de calidad y documentación de ExpresaVisión

> Borrador del contenido para la plantilla UNEMI. Los textos entre corchetes
> `[...]` deben completarse o reemplazarse por capturas.

**Asignatura:** Construcción de Software · **Unidad 4:** Tecnologías y herramientas de la construcción de software
**Grupo:** [N.º] · **Integrantes:** [nombres] · **Fecha:** [fecha]
**Repositorio:** [https://github.com/USUARIO/REPOSITORIO]

---

## 1. Objetivo

Aplicar pruebas unitarias, de integración y funcionales al aplicativo web
desarrollado en la Unidad 3 (ExpresaVisión, detector de expresiones faciales
con Django, OpenCV y PostgreSQL), y elaborar su documentación técnica y de
usuario.

## 2. Estrategia de pruebas

| Nivel | Qué valida | Herramienta | Archivo | N.º |
|---|---|---|---|---|
| Unitarias | Funciones críticas de visión: modelo FER+ con `cv2.dnn`, softmax, suavizado, detector de rostros, recorte, dibujo, línea base, ventana de votos | `unittest` / `django.test.SimpleTestCase` | `test_vision.py`, `test_sensibilidad.py` | 57 |
| Integración | Rutas de Django, API JSON, flujo MJPEG, guardado en PostgreSQL, Historial, manejo de errores de BD | `django.test.TestCase`, `TransactionTestCase`, cliente de pruebas | `test_web.py` | 16 |
| Funcionales | Casos de uso completos en un navegador real | Selenium + Chrome/Edge, `StaticLiveServerTestCase` | `test_funcional.py` | 6 |
| **Total** | | | | **79** |

**Dobles de prueba.** Para no depender de una cámara física ni de rostros
reales, se usan objetos simulados (`expresiones/tests/utilidades.py`):
`CapturaSimulada` (imita `cv2.VideoCapture`), `DetectorSimulado`,
`ClasificadorSimulado` y `OyenteMemoria`. Las pruebas del modelo usan el
archivo ONNX real.

**Base de datos.** Django crea y elimina una base PostgreSQL temporal
(`test_detector_expresiones`) en cada ejecución.

## 3. Sesión 1: Pruebas unitarias y de integración

### 3.1 Pruebas unitarias (módulo de detección con OpenCV)

| Clase de prueba | Casos principales |
|---|---|
| `CatalogoTests` | 6 expresiones visibles, orden de las 8 clases del modelo, emojis disponibles |
| `ClasificadorTests` | Huella SHA-256 del modelo, 6 probabilidades que suman 1, determinismo, entrada 64×64, modelo inexistente o dañado |
| `SeleccionVisiblesTests` | Descarte de miedo/desprecio y renormalización |
| `SoftmaxYSuavizadoTests` | Softmax, estabilidad ante un parpadeo, "no clara" bajo el mínimo |
| `DetectorYPreprocesamientoTests` | Cascada Haar inexistente, imagen sin rostro, recorte |
| `DibujoTests` | Emoji en el borde, transparencia, recuadro y etiqueta |
| `GestorCamaraTests` | Cámara no disponible, pérdida de señal, sin rostro, 1 registro por segundo, fallo de BD sin detener el video |
| `DecisionPorCambioTests`, `VentanaVotosTests`, `LineaBaseTests`, `MotorDecisionTests` | Decisión por cambio respecto a la línea base, ventana 3 de 5 |

### 3.2 Pruebas de integración (rutas principales de Django)

| Clase de prueba | Casos principales |
|---|---|
| `PaginasTests` | `/`, `/historial/`, `/acerca/` responden 200; detalle y eliminación; 404 de sesión inexistente |
| `ApiTests` | `/api/estado/`, GET no permitido en acciones, `/video/` con cámara detenida |
| `FlujoCompletoTests` | Iniciar → MJPEG → registros en PostgreSQL → detener → Historial y detalle |
| `OyenteBaseDatosTests` | Ciclo de vida de la sesión en la BD |
| `ErroresTests` | Página de ayuda si PostgreSQL no responde; detector o modelo faltante |

### 3.3 Resultados

Comando: `.\ejecutar_pruebas.ps1` (logs en `evidencias/logs/`).

[Insertar captura de la consola con `1_unitarias` y `2_integracion` en OK]
[Pegar el final de `evidencias/logs/1_unitarias.log` y `2_integracion.log`: "Ran N tests ... OK"]

**Análisis:** [Ej.: Las 73 pruebas pasaron en X s. La línea "Error de base de
datos: connection refused" es esperada: corresponde a
`test_error_de_base_de_datos_no_detiene_el_video`, que simula la caída de
PostgreSQL para comprobar que el video sigue funcionando.]

## 4. Sesión 2: Pruebas funcionales

Se automatizaron con Selenium: un navegador real abre la aplicación servida
por Django, pulsa botones y comprueba lo que se ve en pantalla. Cada caso
guarda su captura en `evidencias/funcionales/`.

| ID | Caso de uso | Pasos | Resultado esperado | Resultado | Evidencia |
|---|---|---|---|---|---|
| CU-01 | Inicio | Abrir `/` | Título "En vivo", chip "Cámara detenida", botón "Iniciar cámara", 6 barras en 0 % | ✅ OK | `CU01_inicio_camara_detenida.png` |
| CU-02 | Detección en video | Pulsar "Iniciar cámara" | Chip "Cámara activa", video MJPEG con fotogramas, expresión "Sorpresa", barra resaltada, FPS, botón "Detener" | ✅ OK | `CU02_deteccion_en_video.png` |
| CU-03 | Sin rostro | Iniciar con una escena sin rostro | Mensaje "Sin rostro visible", ninguna expresión inventada | ✅ OK | `CU03_sin_rostro.png` |
| CU-04 | Detener y consultar | Detener → Historial → Ver detalle | Sesión "Finalizada", predominante "Sorpresa", 100 % de rostro, línea de tiempo | ✅ OK | `CU04a/b/c_*.png` |
| CU-05 | Eliminar sesión | Detalle → Eliminar → aceptar confirmación | Vuelve al Historial vacío; la sesión ya no existe en la BD | ✅ OK | `CU05_sesion_eliminada.png` |
| CU-06 | Navegación | Menú En vivo / Historial / Cómo funciona | Cada página abre y su enlace queda resaltado | ✅ OK | `CU06_como_funciona.png` |

[Insertar las capturas de `evidencias/funcionales/`]

**Prueba manual con cámara real** (complementa la automática):

| Paso | Esperado | Resultado |
|---|---|---|
| `python manage.py diagnostico --camara` | Todo en `[OK]` | [captura] |
| Iniciar cámara, cara relajada 3 s | "Neutral" | [captura] |
| Sonreír | "Felicidad" | [captura] |
| Boca abierta, cejas arriba | "Sorpresa" | [captura] |
| Salir del encuadre | "Sin rostro visible" | [captura] |
| Detener → Historial | Sesión nueva con su detalle | [captura] |

## 5. Sesión 3: Documentación técnica

### 5.1 Requisitos

- **Funcionales:** capturar video de la cámara; detectar el rostro; estimar
  6 expresiones (neutral, felicidad, sorpresa, tristeza, enojo, asco); mostrar
  resultado y probabilidades en vivo; guardar cada sesión en PostgreSQL;
  consultar y eliminar sesiones en el Historial.
- **No funcionales:** respuesta en tiempo real; el video no se guarda; la app
  sigue funcionando si falla la BD; mensajes de error claros.
- **Software:** Windows 11, Python 3.12, PostgreSQL 17, Chrome o Edge (solo
  para las pruebas funcionales), cámara web.

### 5.2 Tecnologías

Django 5.2 · OpenCV (contrib) 4.x con `cv2.dnn` · modelo FER+ ONNX ·
PostgreSQL + psycopg 3 · NumPy · python-dotenv · Selenium 4 (pruebas).

### 5.3 Instalación

```powershell
py -3.12 -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

En psql (usuario `postgres`):

```sql
CREATE USER expresiones_app WITH PASSWORD 'su_contrasena' CREATEDB;
CREATE DATABASE detector_expresiones OWNER expresiones_app;
```

```powershell
Copy-Item .env.example .env   # completar POSTGRES_PASSWORD y DJANGO_SECRET_KEY
python manage.py migrate
```

### 5.4 Ejecución

```powershell
python manage.py diagnostico --camara
python manage.py runserver        # abrir http://127.0.0.1:8000
```

Pruebas:

```powershell
python manage.py test             # las 79 pruebas
.\ejecutar_pruebas.ps1            # por grupos, con logs en evidencias\logs
```

### 5.5 Estructura de directorios

```
├── config/            settings, urls, wsgi/asgi
├── vision/            visión por computadora (sin Django)
│   ├── camara.py          GestorCamara: hilo de captura y MJPEG
│   ├── detector_rostros.py, preprocesamiento.py, clasificador.py
│   ├── sensibilidad.py, suavizado.py, dibujo.py, expresiones.py
│   ├── modelos/           emotion-ferplus-8.onnx
│   └── recursos/          haarcascade_frontalface_default.xml
├── expresiones/       aplicación Django
│   ├── models.py          SesionAnalisis, RegistroExpresion
│   ├── views.py, urls.py  páginas, API JSON y video
│   ├── servicios.py       puente visión → PostgreSQL
│   ├── templates/, static/
│   └── tests/             test_vision, test_sensibilidad, test_web, test_funcional, utilidades
├── evidencias/        logs y capturas generados por las pruebas
├── ejecutar_pruebas.ps1
├── manage.py, requirements.txt, .env.example, README.md
```

### 5.6 Arquitectura (resumen)

Navegador → Django (`views.py`) → `GestorCamara` (hilo) → OpenCV: captura →
detección Haar → recorte 64×64 → FER+ (`cv2.dnn`) → suavizado/línea base →
dibujo → MJPEG al navegador. El gestor avisa a `OyenteBaseDatos`, que guarda
sesiones y registros en PostgreSQL.

## 6. Sesión 3: Documentación de usuario

1. **Abrir la aplicación:** con el servidor en marcha, entrar a
   `http://127.0.0.1:8000`. [captura CU-01]
2. **Iniciar la cámara:** pulsar *Iniciar cámara*. Si Windows pide permiso,
   aceptarlo. Mantener la cara relajada 3 s para que el sistema tome la línea
   base. [captura]
3. **Leer el resultado:** sobre el video aparece un recuadro con la expresión.
   A la derecha se ve la *Expresión estimada* (emoji, nombre y probabilidad) y
   las *Probabilidades en vivo* de las 6 expresiones; la más alta queda
   resaltada. [captura CU-02]
4. **Mensajes posibles:** *Sin rostro visible* (no hay cara en el encuadre),
   *No clara* (ninguna expresión supera el mínimo), *Problema con la cámara*
   (cámara ocupada o desconectada).
5. **Detener:** pulsar *Detener*. La sesión se guarda. [captura CU-04a]
6. **Historial:** muestra cada sesión con duración, expresión predominante,
   registros y % de rostro visible. *Ver detalle* abre la línea de tiempo y la
   distribución. Desde el detalle se puede *Eliminar* la sesión. [capturas CU-04b, CU-04c, CU-05]
7. **Cómo funciona:** explica el proceso y sus límites. [captura CU-06]

**Explicación de resultados:** el porcentaje es la probabilidad que el modelo
asigna a la expresión visible. Es una **estimación de la expresión del
rostro**, no del estado emocional real de la persona.

## 7. Conclusiones

[Redactar 3-4 conclusiones propias del grupo. Ideas: los dobles de prueba
permitieron probar sin cámara; las pruebas de integración detectan errores en
el guardado en PostgreSQL; Selenium valida lo que el usuario ve realmente.]

## 8. Referencias

- Pressman, R. S. (2005). *Ingeniería del software: un enfoque práctico*. McGraw-Hill.
- Documentación de Django: Testing tools. https://docs.djangoproject.com/en/5.2/topics/testing/
- Documentación de Selenium. https://www.selenium.dev/documentation/
- Barsoum, E. et al. (2016). Training deep networks for facial expression recognition with crowd-sourced label distribution (FER+).

## Anexo A: Código de las pruebas

[Pegar el contenido de:]
- `expresiones/tests/utilidades.py`
- `expresiones/tests/test_vision.py`
- `expresiones/tests/test_sensibilidad.py`
- `expresiones/tests/test_web.py`
- `expresiones/tests/test_funcional.py`
- `ejecutar_pruebas.ps1`
