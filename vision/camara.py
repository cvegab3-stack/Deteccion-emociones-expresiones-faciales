"""
Gestor de la cámara: captura, procesa y publica fotogramas en un hilo.

Un único ``GestorCamara`` abre la cámara con ``cv2.VideoCapture``, procesa
cada fotograma (detección de rostro + clasificación de la expresión con el
modelo FER+ + dibujo) y guarda el último JPEG. Las vistas de Django leen
ese JPEG para transmitir el video (MJPEG) y consultan ``estado()`` para la
interfaz.

El gestor no conoce Django: avisa de los eventos (sesión iniciada,
expresión registrada, sesión finalizada) a un objeto ``oyente``. Así la
lógica de visión se prueba sin base de datos.
"""

import copy
import os
import threading
import time
from dataclasses import dataclass

import cv2

from . import dibujo
from . import expresiones as cat
from .clasificador import ErrorModelo
from .preprocesamiento import a_gris, recortar_rostro
from .sensibilidad import ConfigDecision, MotorDecision
from .suavizado import SuavizadorProbabilidades

DETENIDA, ACTIVA, ERROR = "detenida", "activa", "error"

AVISO_VIDEO = "Estimacion de expresion facial: no determina emociones reales"

# Tiempo máximo que cuenta un fotograma para la calibración (evita saltos si el video se congela).
DT_MAXIMO = 0.25


@dataclass
class ConfigCamara:
    """Opciones del gestor de cámara (se llenan desde el archivo .env)."""
    fuente: object = 0                 # CAMARA_FUENTE: índice de cámara (int) o ruta de un video (str)
    ancho: int = 640
    alto: int = 480
    backend: str = "auto"              # auto | dshow | msmf | any
    espejo: bool = True                # voltear como un espejo (solo cámaras)
    calidad_jpeg: int = 80
    confianza_minima: float = 0.40     # por debajo: "Expresión no clara" (antes de la línea base)
    alfa_suavizado: float = 0.5
    intervalo_registro: float = 1.0    # segundos entre registros en la base de datos
    fallos_maximos: int = 25           # lecturas fallidas seguidas antes de dar error
    fps_maximo: float = 25.0           # solo para archivos de video
    # Sensibilidad respecto a la cara neutra (ver sensibilidad.py).
    duracion_calibracion: float = 3.0  # segundos con rostro para la línea base (0 = desactivada)
    umbral_cambio: float = 0.08
    ventana_fotogramas: int = 5
    ventana_minimo: int = 3

    def config_decision(self):
        """Parámetros de la línea base y la decisión por cambio."""
        return ConfigDecision(
            confianza_minima=self.confianza_minima, duracion_calibracion=self.duracion_calibracion,
            umbral_cambio=self.umbral_cambio, ventana=self.ventana_fotogramas,
            minimo_ventana=self.ventana_minimo)


def _apis_para(backend):
    """Orden de backends de OpenCV a probar al abrir la cámara."""
    tabla = {"dshow": [cv2.CAP_DSHOW], "msmf": [cv2.CAP_MSMF], "any": [cv2.CAP_ANY]}
    if backend in tabla:
        return tabla[backend]
    if os.name == "nt":  # Windows: DirectShow abre más rápido que Media Foundation
        return [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    return [cv2.CAP_ANY]


def abrir_captura(config):
    """Abre la cámara o el archivo de video. Devuelve ``None`` si falla."""
    if isinstance(config.fuente, str):
        captura = cv2.VideoCapture(config.fuente)
        return captura if captura.isOpened() else None
    for api in _apis_para(config.backend):
        captura = cv2.VideoCapture(int(config.fuente), api)
        if captura.isOpened():
            captura.set(cv2.CAP_PROP_FRAME_WIDTH, config.ancho)
            captura.set(cv2.CAP_PROP_FRAME_HEIGHT, config.alto)
            return captura
        captura.release()
    return None


def mensaje_camara_no_disponible(fuente):
    """Mensaje en español con los pasos para resolver una cámara que no abre."""
    if isinstance(fuente, str):
        return f"No se pudo abrir el archivo de video '{fuente}'. Revise CAMARA_FUENTE en el archivo .env."
    return (
        f"No se pudo abrir la cámara {fuente}. Verifique que esté conectada, que no la use otra "
        "aplicación (Zoom, Teams, Cámara de Windows) y que Windows permita el acceso en "
        "Configuración > Privacidad y seguridad > Cámara > 'Permitir que las aplicaciones de "
        "escritorio accedan a la cámara'. Si tiene varias cámaras, pruebe CAMARA_FUENTE=1 en .env."
    )


class OyenteNulo:
    """Oyente por defecto: no hace nada. Django lo reemplaza por la base de datos."""

    def sesion_iniciada(self):
        """No guarda nada; devuelve ``None`` como id de sesión."""
        return None

    def expresion_registrada(self, sesion_id, clave, confianza):
        """No guarda nada."""
        pass

    def sesion_finalizada(self, sesion_id, resumen):
        """No guarda nada."""
        pass


class GestorCamara:
    """Hilo de captura y procesamiento de la cámara; publica el JPEG y el estado."""
    def __init__(self, config, detector, clasificador, carpeta_emojis,
                 oyente=None, fabrica_captura=abrir_captura, error_clasificador=None):
        """Prepara el gestor; la cámara no se abre hasta ``iniciar()``."""
        self.config = config
        self.detector = detector
        self.clasificador = clasificador        # puede ser None si falta el modelo
        self.error_clasificador = error_clasificador
        self.oyente = oyente or OyenteNulo()
        self._fabrica_captura = fabrica_captura
        nombres = [e.emoji for e in cat.EXPRESIONES] + [cat.EMOJI_DESCONOCIDA]
        self._emojis = dibujo.cargar_emojis(carpeta_emojis, nombres)
        self._suavizador = SuavizadorProbabilidades(config.alfa_suavizado, config.confianza_minima)
        # Línea base automática de la cara neutra (primeros segundos con rostro),
        # decisión por cambio y ventana de votos. No se muestra en la interfaz.
        self._motor = MotorDecision(config.config_decision())
        self._ultimo_rostro = None              # time.monotonic() del último fotograma con rostro

        self._control = threading.Lock()        # serializa iniciar/detener (no lo usa el hilo)
        self._bloqueo = threading.RLock()       # protege el estado compartido
        self._nuevo_fotograma = threading.Condition(self._bloqueo)
        self._detener = threading.Event()
        self._hilo = None
        self._captura = None
        self._jpeg = None
        self._id_fotograma = 0
        self._estado = self._estado_inicial()

    # ============================================================ estado
    def _estado_inicial(self):
        """Estado inicial que se envía a la interfaz."""
        return {
            "estado": DETENIDA,
            "mensaje": "Cámara detenida.",
            "advertencia": None,
            "rostro": False,
            "expresion": None,
            "confianza": 0.0,
            "probabilidades": {clave: 0.0 for clave in cat.CLAVES},
            "calibracion": {"estado": self._motor.linea_base.estado, "progreso": 0.0},
            "linea_base": None,            # % por expresión, cuando la calibración termina
            "deltas": {},                  # % por expresión no neutral (p_actual - p_base)
            "fps": 0.0,
            "sesion": None,
        }

    def estado(self):
        """Copia del estado actual (apta para JSON)."""
        with self._bloqueo:
            datos = copy.deepcopy(self._estado)
            datos["modelo"] = self.info_modelo()
            return datos

    def info_modelo(self):
        """Si el modelo FER+ está disponible y, si no, por qué."""
        return {"disponible": self.clasificador is not None, "error": self.error_clasificador}

    @property
    def activa(self):
        """``True`` mientras la cámara está transmitiendo."""
        with self._bloqueo:
            return self._estado["estado"] == ACTIVA

    def _actualizar(self, **cambios):
        """Cambia campos del estado de forma segura entre hilos."""
        with self._bloqueo:
            self._estado.update(cambios)

    # ================================================== iniciar / detener
    def iniciar(self):
        """Abre la cámara y arranca el hilo. Devuelve ``(ok, mensaje)``."""
        # _control evita que dos peticiones abran la cámara a la vez.
        with self._control, self._bloqueo:
            if self._hilo is not None and self._hilo.is_alive():
                return True, "La cámara ya está activa."
            captura = self._fabrica_captura(self.config)
            if captura is None:
                mensaje = mensaje_camara_no_disponible(self.config.fuente)
                self._actualizar(estado=ERROR, mensaje=mensaje)
                return False, mensaje
            if not self._primer_fotograma(captura):
                captura.release()
                mensaje = ("La cámara se abrió pero no entrega imagen. Puede que otra aplicación "
                           "la esté usando o que Windows haya bloqueado el permiso.")
                self._actualizar(estado=ERROR, mensaje=mensaje)
                return False, mensaje

            self._captura = captura
            self._detener.clear()
            self._suavizador.reiniciar()
            self._motor.nueva_linea_base()      # se mide de nuevo en cada inicio
            self._ultimo_rostro = None
            self._estado = self._estado_inicial()
            self._estado.update(estado=ACTIVA, mensaje="Cámara activa.")
            self._hilo = threading.Thread(target=self._bucle, name="camara", daemon=True)
            self._hilo.start()
            return True, "Cámara iniciada."

    @staticmethod
    def _primer_fotograma(captura, intentos=30):
        """Espera hasta que la cámara entregue un primer fotograma válido."""
        for _ in range(intentos):
            ok, fotograma = captura.read()
            if ok and fotograma is not None and fotograma.size:
                return True
            time.sleep(0.05)
        return False

    def detener(self):
        """Detiene la cámara (si está activa). Devuelve ``(ok, mensaje)``."""
        with self._control:
            hilo = self._hilo
            self._detener.set()
            if hilo is not None and hilo is not threading.current_thread():
                hilo.join(timeout=5)
            with self._bloqueo:
                self._hilo = None
                if self._estado["estado"] != ERROR:
                    self._estado.update(estado=DETENIDA, mensaje="Cámara detenida.")
                self._estado.update(rostro=False, expresion=None, confianza=0.0, fps=0.0, deltas={},
                                    probabilidades={clave: 0.0 for clave in cat.CLAVES})
                self._nuevo_fotograma.notify_all()
        return True, "Cámara detenida."

    # ======================================================= transmisión
    def generar_mjpeg(self, espera=2.0):
        """Generador de partes MJPEG para ``StreamingHttpResponse``."""
        ultimo = -1
        while True:
            with self._nuevo_fotograma:
                self._nuevo_fotograma.wait_for(
                    lambda visto=ultimo: self._id_fotograma != visto or self._estado["estado"] != ACTIVA,
                    timeout=espera,
                )
                if self._estado["estado"] != ACTIVA:
                    return
                ultimo, jpeg = self._id_fotograma, self._jpeg
            if jpeg is not None:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                       + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")

    # ============================================================ bucle
    def _bucle(self):
        """Bucle del hilo: lee, procesa, registra cada segundo y publica el JPEG."""
        captura = self._captura
        es_archivo = isinstance(self.config.fuente, str)
        fallos = 0
        ultimo_registro = 0.0
        anterior = time.perf_counter()
        sesion_id = None
        resumen = {"fotogramas": 0, "fotogramas_con_rostro": 0}
        try:
            if self.clasificador is not None:
                sesion_id = self._llamar_oyente("sesion_iniciada")
                with self._bloqueo:
                    self._estado["sesion"] = {"id": sesion_id, "inicio": time.time(), "conteo": {}}

            while not self._detener.is_set():
                ok, fotograma = captura.read()
                if not ok or fotograma is None:
                    if es_archivo:  # video de prueba: volver al inicio
                        captura.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    fallos += 1
                    if fallos >= self.config.fallos_maximos:
                        self._actualizar(
                            estado=ERROR,
                            mensaje="Se perdió la señal de la cámara (¿se desconectó o la tomó "
                                    "otra aplicación?). Pulse 'Iniciar cámara' para reintentar.")
                        break
                    time.sleep(0.04)
                    continue
                fallos = 0

                ahora = time.perf_counter()
                procesado, hay_rostro = self._procesar(fotograma, es_archivo)
                resumen["fotogramas"] += 1
                resumen["fotogramas_con_rostro"] += int(hay_rostro)

                # Una muestra por intervalo: al resumen en vivo y a PostgreSQL.
                if self._estado["sesion"] and time.time() - ultimo_registro >= self.config.intervalo_registro:
                    clave = self._estado["expresion"]
                    if clave:
                        ultimo_registro = time.time()
                        if sesion_id is not None:
                            self._llamar_oyente("expresion_registrada", sesion_id, clave,
                                                self._estado["confianza"])
                        with self._bloqueo:
                            conteo = self._estado["sesion"]["conteo"]
                            conteo[clave] = conteo.get(clave, 0) + 1

                ok_jpeg, buffer = cv2.imencode(".jpg", procesado,
                                               [cv2.IMWRITE_JPEG_QUALITY, self.config.calidad_jpeg])
                with self._nuevo_fotograma:
                    if ok_jpeg:
                        self._jpeg = buffer.tobytes()
                        self._id_fotograma += 1
                    dt = max(1e-6, ahora - anterior)
                    self._estado["fps"] = round(0.9 * self._estado["fps"] + 0.1 * (1.0 / dt), 1)
                    self._nuevo_fotograma.notify_all()
                anterior = ahora

                if es_archivo:  # no ir más rápido que un video real
                    espera = 1.0 / self.config.fps_maximo - (time.perf_counter() - ahora)
                    if espera > 0:
                        time.sleep(espera)
        except Exception as exc:  # un error inesperado no debe dejar la cámara colgada
            self._actualizar(estado=ERROR, mensaje=f"Error inesperado en el procesamiento: {exc}")
        finally:
            captura.release()
            with self._bloqueo:
                self._captura = None
                if self._estado["estado"] == ACTIVA:
                    self._estado.update(estado=DETENIDA, mensaje="Cámara detenida.")
                resumen["conteo"] = dict(self._estado["sesion"]["conteo"]) if self._estado["sesion"] else {}
                self._nuevo_fotograma.notify_all()
            if sesion_id is not None:
                self._llamar_oyente("sesion_finalizada", sesion_id, resumen)

    def _llamar_oyente(self, metodo, *args):
        """Llama al oyente sin permitir que un fallo (p. ej. de la base de datos) detenga el video."""
        try:
            resultado = getattr(self.oyente, metodo)(*args)
            with self._bloqueo:
                if self._estado["advertencia"] and self._estado["advertencia"].startswith("Base de datos"):
                    self._estado["advertencia"] = None
            return resultado
        except Exception as exc:
            self._actualizar(advertencia=f"Base de datos no disponible: los datos no se están "
                                         f"guardando ({exc.__class__.__name__}).")
            return None

    # ====================================================== procesamiento
    def _procesar(self, fotograma, es_archivo):
        """Detecta, clasifica y dibuja. Devuelve ``(imagen, hay_rostro)``."""
        if self.config.espejo and not es_archivo:
            fotograma = cv2.flip(fotograma, 1)
        if fotograma.shape[1] > self.config.ancho:
            escala = self.config.ancho / fotograma.shape[1]
            fotograma = cv2.resize(fotograma, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)

        gris = a_gris(fotograma)
        rect = self.detector.rostro_principal(gris)

        if self.clasificador is None:
            if rect is not None:
                dibujo.resultado_rostro(fotograma, rect, "Rostro detectado", (150, 150, 150))
            dibujo.mensaje_central(fotograma, "Modelo de emociones no disponible")
        elif rect is None:
            # La línea base se conserva (o la calibración se pausa) hasta que vuelva el rostro.
            self._suavizador.reiniciar()
            self._motor.reiniciar_ventanas()
            self._ultimo_rostro = None
            dibujo.mensaje_central(fotograma, "Sin rostro visible", color=(90, 90, 90))
            self._actualizar(expresion=None, confianza=0.0, deltas={},
                             probabilidades={clave: 0.0 for clave in cat.CLAVES})
        else:
            self._clasificar_y_dibujar(fotograma, gris, rect)

        dibujo.barra_inferior(fotograma, AVISO_VIDEO)
        self._actualizar(rostro=rect is not None)
        return fotograma, rect is not None

    def _clasificar_y_dibujar(self, imagen, gris, rect):
        """Clasifica el rostro, actualiza el estado y dibuja el resultado."""
        ahora = time.monotonic()
        dt = 0.0 if self._ultimo_rostro is None else min(DT_MAXIMO, ahora - self._ultimo_rostro)
        self._ultimo_rostro = ahora

        recorte = recortar_rostro(gris, rect)
        if recorte is None:
            return
        try:
            crudas = self.clasificador.predecir(recorte)
        except ErrorModelo as exc:
            self._actualizar(advertencia=str(exc))
            return
        self._suavizador.agregar(crudas)
        suavizadas = self._suavizador.probabilidades
        decision = self._motor.actualizar(crudas, suavizadas, dt)
        clave = decision.clave

        # Una sola fuente para los porcentajes: "confianza" es exactamente el valor
        # de "probabilidades" de la expresión estimada (el mismo número redondeado),
        # así el panel, la fila resaltada y PostgreSQL nunca difieren.
        probabilidades = {c: round(100 * p, 1) for c, p in suavizadas.items()}
        confianza = probabilidades[clave] if clave else max(probabilidades.values())
        self._actualizar(
            expresion=clave,
            confianza=confianza,
            probabilidades=probabilidades,
            calibracion={"estado": decision.calibracion, "progreso": round(100 * decision.progreso, 1)},
            linea_base={c: round(100 * p, 1) for c, p in decision.linea_base.items()}
            if decision.linea_base else None,
            deltas={c: round(100 * d, 1) for c, d in decision.deltas.items()},
        )

        # Sobre el video: solo el recuadro del color de la expresión, su nombre
        # (sin porcentaje) y el emoji. Los porcentajes se ven en el panel web.
        if clave:
            expresion = cat.obtener(clave)
            dibujo.resultado_rostro(imagen, rect, expresion.nombre_video, expresion.color_bgr,
                                    self._emojis.get(expresion.emoji))
        else:
            dibujo.resultado_rostro(imagen, rect, "Expresion no clara", (120, 120, 120),
                                    self._emojis.get(cat.EMOJI_DESCONOCIDA))
