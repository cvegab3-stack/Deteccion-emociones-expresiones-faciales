"""
Pruebas FUNCIONALES (de extremo a extremo) con Selenium.

Abren la aplicación en un navegador real (Chrome o Edge, sin ventana) contra
un servidor Django de pruebas y validan los casos de uso clave tal como los
vive el usuario:

    CU-01  Inicio: la página "En vivo" carga con la cámara detenida.
    CU-02  Detección en video: Iniciar cámara -> video MJPEG + expresión.
    CU-03  Sin rostro: el panel avisa "Sin rostro visible".
    CU-04  Detener y consultar la sesión en Historial y en su detalle.
    CU-05  Eliminar una sesión desde su detalle.
    CU-06  Navegación entre En vivo, Historial y Cómo funciona.

La cámara, el detector y el clasificador son simulados (no hace falta una
cámara real), pero todo lo demás es real: servidor HTTP, PostgreSQL,
plantillas, JavaScript, API y flujo MJPEG.

Cada prueba guarda capturas de pantalla en ``evidencias/funcionales/``.

Navegador: variable ``NAVEGADOR_PRUEBAS`` = ``chrome`` (defecto) o ``edge``.
Para ver el navegador en pantalla: ``NAVEGADOR_VISIBLE=1``.
Si no hay navegador disponible, las pruebas se omiten (skip) con un aviso.
"""

import os
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from expresiones import servicios
from expresiones.models import SesionAnalisis
from vision.camara import ConfigCamara, GestorCamara

from .utilidades import CapturaSimulada, ClasificadorSimulado, DetectorSimulado, fotograma

try:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except ImportError:  # selenium no instalado
    webdriver = None

CARPETA_EVIDENCIAS = Path(settings.BASE_DIR) / "evidencias" / "funcionales"
ESPERA = 10  # segundos máximos de espera por cada condición


def _crear_navegador():
    """Chrome o Edge en modo headless (o visible con NAVEGADOR_VISIBLE=1)."""
    preferido = os.getenv("NAVEGADOR_PRUEBAS", "chrome").strip().lower()
    orden = ["chrome", "edge"] if preferido != "edge" else ["edge", "chrome"]
    visible = os.getenv("NAVEGADOR_VISIBLE", "").strip() in {"1", "true", "si"}
    errores = []
    for nombre in orden:
        opciones = webdriver.ChromeOptions() if nombre == "chrome" else webdriver.EdgeOptions()
        if not visible:
            opciones.add_argument("--headless=new")
        opciones.add_argument("--window-size=1366,1100")
        opciones.add_argument("--lang=es")
        try:
            navegador = webdriver.Chrome(options=opciones) if nombre == "chrome" else webdriver.Edge(options=opciones)
            return navegador, nombre
        except WebDriverException as exc:
            errores.append(f"{nombre}: {exc.msg}")
    raise RuntimeError("; ".join(errores))


class BaseFuncional(StaticLiveServerTestCase):
    """Servidor real + navegador real + cámara simulada."""

    host = "127.0.0.1"
    navegador = None
    # Lo que "ve" la cámara simulada (cada clase puede cambiarlo).
    expresion_simulada = "sorpresa"
    hay_rostro = True

    @classmethod
    def setUpClass(cls):
        if webdriver is None:
            raise cls.skipException("Selenium no está instalado (pip install selenium).")
        try:
            cls.navegador, cls.nombre_navegador = _crear_navegador()
        except RuntimeError as exc:
            raise cls.skipException(f"No hay navegador para las pruebas funcionales: {exc}")
        super().setUpClass()
        cls.navegador.implicitly_wait(0)
        CARPETA_EVIDENCIAS.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if cls.navegador is not None:
            cls.navegador.quit()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        detector = DetectorSimulado() if self.hay_rostro else DetectorSimulado(rect=None)
        self.gestor = GestorCamara(
            ConfigCamara(fuente=0, intervalo_registro=0.1),
            detector, ClasificadorSimulado(self.expresion_simulada, 0.85),
            settings.DETECTOR_EXPRESIONES["CARPETA_EMOJIS"],
            oyente=servicios.OyenteBaseDatos(),
            fabrica_captura=lambda config: CapturaSimulada([fotograma()]),
        )
        servicios.reemplazar_gestor(self.gestor)
        # Orden inverso: primero se cierra la página (corta el MJPEG), luego la cámara.
        self.addCleanup(servicios.reemplazar_gestor, None)
        self.addCleanup(self.gestor.detener)
        self.addCleanup(self.navegador.get, "about:blank")

    # ------------------------------------------------------------ utilidades
    def abrir(self, ruta="/"):
        self.navegador.get(self.live_server_url + ruta)

    def esperar(self, condicion, mensaje=""):
        try:
            return WebDriverWait(self.navegador, ESPERA).until(condicion)
        except TimeoutException:
            self.captura("FALLO_" + self._testMethodName)
            self.fail(mensaje or "La condición no se cumplió a tiempo.")

    def esperar_texto(self, id_elemento, texto):
        self.esperar(EC.text_to_be_present_in_element((By.ID, id_elemento), texto),
                     f"#{id_elemento} no llegó a mostrar «{texto}».")

    def texto(self, id_elemento):
        return self.navegador.find_element(By.ID, id_elemento).text

    def captura(self, nombre):
        ruta = CARPETA_EVIDENCIAS / f"{nombre}.png"
        self.navegador.execute_script("window.scrollTo(0, 0);")
        self.navegador.save_screenshot(str(ruta))
        return ruta

    def iniciar_camara(self):
        boton = self.esperar(EC.element_to_be_clickable((By.ID, "btn-camara")), "El botón no está disponible.")
        self.assertEqual(boton.text, "Iniciar cámara")
        boton.click()
        self.esperar_texto("chip-camara", "Cámara activa")

    def video_tiene_imagen(self):
        """True cuando el <img id=video> ya pintó al menos un fotograma MJPEG."""
        return self.navegador.execute_script(
            "const v = document.getElementById('video');"
            "return !v.hidden && v.complete !== undefined && v.naturalWidth > 0;")


class CasosDeUsoTests(BaseFuncional):

    def test_cu01_inicio_pagina_en_vivo(self):
        """CU-01: al abrir la aplicación se ve el panel con la cámara detenida."""
        self.abrir("/")
        self.assertIn("En vivo", self.navegador.title)
        self.esperar_texto("chip-camara", "Cámara detenida")
        self.assertEqual(self.texto("btn-camara"), "Iniciar cámara")
        self.assertEqual(self.texto("marcador-titulo"), "La cámara está apagada")
        filas = self.navegador.find_elements(By.CSS_SELECTOR, "#barras-probabilidad .barra")
        self.assertEqual([f.get_attribute("data-clave") for f in filas],
                         ["neutral", "felicidad", "sorpresa", "tristeza", "enojo", "asco"])
        self.assertTrue(all(f.find_element(By.CLASS_NAME, "valor").text == "0 %" for f in filas))
        self.captura("CU01_inicio_camara_detenida")

    def test_cu02_deteccion_en_video(self):
        """CU-02: Iniciar cámara muestra el video y la expresión detectada."""
        self.abrir("/")
        self.iniciar_camara()
        self.esperar(lambda d: self.video_tiene_imagen(), "El video MJPEG no mostró ningún fotograma.")
        self.esperar_texto("nombre-actual", "Sorpresa")
        self.esperar_texto("detalle-actual", "Probabilidad actual del modelo")

        self.assertEqual(self.texto("btn-camara"), "Detener")
        self.assertTrue(self.navegador.find_element(By.ID, "video").get_attribute("src").startswith(
            self.live_server_url + "/video/"))
        self.assertTrue(self.navegador.find_element(By.ID, "marcador").get_attribute("hidden"))
        self.assertRegex(self.texto("info-fps"), r"^\d+\.\d FPS$")
        # La fila de "Sorpresa" queda resaltada y con el mayor porcentaje.
        fila = self.navegador.find_element(By.CSS_SELECTOR, '.barra[data-clave="sorpresa"]')
        self.esperar(lambda d: "destacada" in fila.get_attribute("class"), "La barra no se resaltó.")
        valores = {f.get_attribute("data-clave"): int(f.find_element(By.CLASS_NAME, "valor").text.split()[0])
                   for f in self.navegador.find_elements(By.CSS_SELECTOR, "#barras-probabilidad .barra")}
        self.assertEqual(max(valores, key=valores.get), "sorpresa")
        self.assertGreaterEqual(sum(valores.values()), 98)  # redondeos: ~100 %
        self.captura("CU02_deteccion_en_video")

    def test_cu04_detener_y_ver_en_historial(self):
        """CU-04: detener la cámara guarda la sesión y se ve en el Historial."""
        self.abrir("/")
        self.iniciar_camara()
        self.esperar_texto("nombre-actual", "Sorpresa")
        self.esperar(lambda d: SesionAnalisis.objects.exists()
                     and SesionAnalisis.objects.get().registros.count() >= 2,
                     "No se guardaron registros en la base de datos.")

        self.navegador.find_element(By.ID, "btn-camara").click()
        self.esperar_texto("chip-camara", "Cámara detenida")
        self.esperar_texto("btn-camara", "Iniciar cámara")
        self.esperar_texto("nombre-actual", "—")
        self.captura("CU04a_camara_detenida")

        sesion = SesionAnalisis.objects.get()
        self.assertEqual(sesion.estado, SesionAnalisis.FINALIZADA)
        self.assertEqual(sesion.expresion_predominante, "sorpresa")

        self.navegador.find_element(By.LINK_TEXT, "Historial").click()
        self.esperar(EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr")),
                     "El Historial no muestra la sesión.")
        fila = self.navegador.find_element(By.CSS_SELECTOR, "table tbody tr").text
        self.assertIn("Sorpresa", fila)
        self.assertIn("Finalizada", fila)
        self.assertIn("100 %", fila)
        self.captura("CU04b_historial")

        self.navegador.find_element(By.LINK_TEXT, "Ver detalle").click()
        self.esperar(EC.url_contains(f"/historial/{sesion.pk}/"), "No se abrió el detalle.")
        cuerpo = self.navegador.find_element(By.TAG_NAME, "body").text
        self.assertIn(f"Sesión {sesion.pk}", cuerpo)
        self.assertIn("Sorpresa", cuerpo)
        self.assertTrue(self.navegador.find_elements(By.CLASS_NAME, "linea-tiempo"))
        self.captura("CU04c_detalle_sesion")

    def test_cu05_eliminar_sesion(self):
        """CU-05: una sesión se puede eliminar desde su detalle (con confirmación)."""
        sesion = SesionAnalisis.objects.create(estado=SesionAnalisis.FINALIZADA)
        self.abrir(f"/historial/{sesion.pk}/")
        self.navegador.find_element(By.CSS_SELECTOR, "form[action$='/eliminar/'] button").click()
        alerta = self.esperar(EC.alert_is_present(), "No apareció la confirmación.")
        self.assertIn("Eliminar esta sesión", alerta.text)
        alerta.accept()
        self.esperar(EC.url_to_be(self.live_server_url + "/historial/"), "No volvió al Historial.")
        self.assertIn("Todavía no hay sesiones", self.navegador.find_element(By.TAG_NAME, "body").text)
        self.assertFalse(SesionAnalisis.objects.exists())
        self.captura("CU05_sesion_eliminada")

    def test_cu06_navegacion(self):
        """CU-06: el menú lleva a cada página y marca la sección activa."""
        self.abrir("/")
        for enlace, titulo in [("Historial", "Historial"), ("Cómo funciona", "Cómo funciona"), ("En vivo", "En vivo")]:
            self.navegador.find_element(By.LINK_TEXT, enlace).click()
            self.esperar(EC.title_contains(titulo), f"No se abrió «{enlace}».")
            activo = self.navegador.find_element(By.CSS_SELECTOR, "nav.navegacion a.activo")
            self.assertEqual(activo.text, enlace)
        self.navegador.find_element(By.LINK_TEXT, "Cómo funciona").click()
        self.esperar(EC.title_contains("Cómo funciona"))
        self.captura("CU06_como_funciona")


class SinRostroTests(BaseFuncional):
    hay_rostro = False

    def test_cu03_sin_rostro_visible(self):
        """CU-03: si no hay rostro, el panel lo indica y no inventa una expresión."""
        self.abrir("/")
        self.iniciar_camara()
        self.esperar(lambda d: self.video_tiene_imagen(), "El video MJPEG no mostró ningún fotograma.")
        self.esperar_texto("detalle-actual", "Sin rostro visible")
        self.assertEqual(self.texto("nombre-actual"), "—")
        self.assertFalse(self.navegador.find_elements(By.CSS_SELECTOR, ".barra.destacada"))
        self.captura("CU03_sin_rostro")
