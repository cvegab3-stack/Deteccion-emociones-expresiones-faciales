"""
Pruebas del módulo de visión (OpenCV) sin cámara ni base de datos.

El modelo FER+ real se carga y ejecuta con cv2.dnn. El resto del flujo se
prueba con una cámara, un detector y un clasificador simulados, para que
las pruebas sean repetibles y no requieran fotos de personas.
"""

import tempfile
import time
from pathlib import Path
from unittest import mock

import numpy as np
from django.conf import settings
from django.test import SimpleTestCase

from vision import dibujo
from vision import expresiones as cat
from vision.camara import ACTIVA, DETENIDA, ERROR, ConfigCamara, GestorCamara
from vision.clasificador import (RUTA_MODELO, SHA256_MODELO, ClasificadorEmociones, ErrorModelo,
                                 seleccionar_visibles, sha256_archivo, softmax)
from vision.detector_rostros import DetectorRostros, ErrorDetector
from vision.preprocesamiento import recortar_rostro
from vision.suavizado import SuavizadorProbabilidades

from .utilidades import (RECT, CapturaSimulada, ClasificadorSimulado, DetectorSimulado, OyenteMemoria,
                         fotograma, probabilidades)

EMOJIS = settings.DETECTOR_EXPRESIONES["CARPETA_EMOJIS"]


def esperar(condicion, limite=5.0):
    fin = time.time() + limite
    while time.time() < fin:
        if condicion():
            return True
        time.sleep(0.02)
    return False


class CatalogoTests(SimpleTestCase):
    def test_seis_expresiones_visibles(self):
        self.assertEqual(cat.CLAVES, ("neutral", "felicidad", "sorpresa", "tristeza", "enojo", "asco"))
        self.assertNotIn("miedo", cat.CLAVES)
        self.assertNotIn("desprecio", cat.CLAVES)

    def test_ocho_clases_en_el_orden_del_modelo_y_mapeo(self):
        self.assertEqual(cat.CLASES_MODELO, ("neutral", "felicidad", "sorpresa", "tristeza",
                                             "enojo", "asco", "miedo", "desprecio"))
        self.assertEqual(cat.INDICES_MODELO, {"neutral": 0, "felicidad": 1, "sorpresa": 2,
                                              "tristeza": 3, "enojo": 4, "asco": 5})
        self.assertEqual(cat.CLASES_DESCARTADAS, ("miedo", "desprecio"))

    def test_claves_antiguas_se_muestran_como_otra(self):
        self.assertIs(cat.obtener_o_otra("miedo"), cat.OTRA)
        self.assertIs(cat.obtener_o_otra("desprecio"), cat.OTRA)
        self.assertEqual(cat.obtener_o_otra("asco").nombre, "Asco")
        self.assertIsNone(cat.obtener_o_otra(""))
        self.assertIsNone(cat.obtener("miedo"))

    def test_cada_expresion_tiene_su_emoji_noto(self):
        for e in cat.EXPRESIONES:
            self.assertTrue((EMOJIS / e.emoji).is_file(), e.emoji)

    def test_textos_del_video_son_ascii(self):
        for e in cat.EXPRESIONES:
            e.nombre_video.encode("ascii")


class ClasificadorTests(SimpleTestCase):
    """Usa el modelo real vision/modelos/emotion-ferplus-8.onnx."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clasificador = ClasificadorEmociones()

    def test_huella_del_modelo(self):
        self.assertEqual(sha256_archivo(RUTA_MODELO), SHA256_MODELO)

    def test_devuelve_seis_probabilidades_que_suman_uno(self):
        rng = np.random.default_rng(0)
        resultado = self.clasificador.predecir(rng.integers(0, 255, (120, 100), dtype=np.uint8))
        self.assertEqual(list(resultado), list(cat.CLAVES))
        self.assertAlmostEqual(sum(resultado.values()), 1.0, places=5)
        self.assertTrue(all(0.0 <= p <= 1.0 for p in resultado.values()))
        self.assertEqual(len(resultado), 6)

    def test_es_determinista(self):
        imagen = np.full((64, 64), 100, np.uint8)
        self.assertEqual(self.clasificador.predecir(imagen), self.clasificador.predecir(imagen))

    def test_entrada_de_64x64(self):
        blob = ClasificadorEmociones.preparar(np.zeros((200, 150), np.uint8))
        self.assertEqual(blob.shape, (1, 1, 64, 64))

    def test_modelo_inexistente(self):
        with self.assertRaisesRegex(ErrorModelo, "No se encontró el modelo"):
            ClasificadorEmociones("no_existe.onnx")

    def test_modelo_danado(self):
        ruta = Path(tempfile.mkdtemp()) / "danado.onnx"
        ruta.write_bytes(b"esto no es un modelo onnx")
        with self.assertRaises(ErrorModelo):
            ClasificadorEmociones(ruta)


class SeleccionVisiblesTests(SimpleTestCase):
    def test_descarta_miedo_y_desprecio_y_normaliza(self):
        modelo = [0.30, 0.10, 0.10, 0.10, 0.10, 0.10, 0.15, 0.05]   # miedo + desprecio = 0.20
        visibles = seleccionar_visibles(modelo)
        self.assertEqual(list(visibles), list(cat.CLAVES))
        self.assertAlmostEqual(sum(visibles.values()), 1.0)
        self.assertAlmostEqual(visibles["neutral"], 0.30 / 0.80)
        self.assertAlmostEqual(visibles["asco"], 0.10 / 0.80)

    def test_numero_de_valores_incorrecto(self):
        with self.assertRaises(ErrorModelo):
            seleccionar_visibles([0.5, 0.5])

    def test_si_todo_era_miedo_reparte_por_igual(self):
        visibles = seleccionar_visibles([0, 0, 0, 0, 0, 0, 1.0, 0])
        self.assertAlmostEqual(visibles["neutral"], 1 / 6)


class SoftmaxYSuavizadoTests(SimpleTestCase):
    def test_softmax(self):
        p = softmax([1.0, 2.0, 3.0])
        self.assertAlmostEqual(p.sum(), 1.0)
        self.assertEqual(int(p.argmax()), 2)
        self.assertTrue(np.isfinite(softmax([1000.0, 0.0])).all())  # estable con valores grandes

    def test_suavizado_estable_ante_un_parpadeo(self):
        s = SuavizadorProbabilidades(alfa=0.35, confianza_minima=0.4)
        for _ in range(6):
            s.agregar(probabilidades("felicidad", 0.9))
        clave, _ = s.agregar(probabilidades("enojo", 0.9))  # un fotograma aislado
        self.assertEqual(clave, "felicidad")

    def test_cambia_cuando_la_expresion_se_mantiene(self):
        s = SuavizadorProbabilidades(alfa=0.35)
        s.agregar(probabilidades("felicidad", 0.9))
        for _ in range(6):
            clave, _ = s.agregar(probabilidades("sorpresa", 0.9))
        self.assertEqual(clave, "sorpresa")

    def test_no_clara_bajo_el_minimo(self):
        s = SuavizadorProbabilidades(confianza_minima=0.5)
        clave, confianza = s.agregar(probabilidades("tristeza", 0.3))
        self.assertIsNone(clave)
        self.assertAlmostEqual(confianza, 0.3)

    def test_alfa_invalido(self):
        with self.assertRaises(ValueError):
            SuavizadorProbabilidades(alfa=0)


class DetectorYPreprocesamientoTests(SimpleTestCase):
    def test_archivo_inexistente_da_error_claro(self):
        with self.assertRaises(ErrorDetector):
            DetectorRostros("no_existe.xml")

    def test_imagen_sin_rostro(self):
        self.assertIsNone(DetectorRostros().rostro_principal(np.full((480, 640), 128, np.uint8)))

    def test_recorte(self):
        gris = np.zeros((480, 640), np.uint8)
        self.assertEqual(recortar_rostro(gris, (100, 100, 50, 60)).shape, (60, 50))
        self.assertEqual(recortar_rostro(gris, (100, 100, 50, 50), margen=0.2).shape, (70, 70))
        self.assertIsNone(recortar_rostro(gris, (700, 500, 10, 10)))


class DibujoTests(SimpleTestCase):
    def test_emoji_en_el_borde_no_falla(self):
        fondo = np.zeros((100, 100, 3), np.uint8)
        png = np.full((40, 40, 4), 255, np.uint8)
        dibujo.superponer_png(fondo, png, 80, -10)
        dibujo.superponer_png(fondo, png, 500, 500)
        self.assertEqual(fondo[0, 99].tolist(), [255, 255, 255])

    def test_carga_emojis_con_transparencia(self):
        emojis = dibujo.cargar_emojis(EMOJIS, ["felicidad.png", "no_existe.png"], tamano=48)
        self.assertEqual(list(emojis), ["felicidad.png"])
        self.assertEqual(emojis["felicidad.png"].shape, (48, 48, 4))

    def test_ya_no_hay_panel_de_probabilidades_en_el_video(self):
        self.assertFalse(hasattr(dibujo, "top_probabilidades"))

    def test_resultado_rostro_dibuja_recuadro_y_etiqueta(self):
        imagen = np.zeros((480, 640, 3), np.uint8)
        dibujo.resultado_rostro(imagen, RECT, "Tristeza", (220, 140, 50))
        self.assertGreater(imagen.sum(), 0)


class GestorCamaraTests(SimpleTestCase):
    """Ciclo completo con cámara, detector y clasificador simulados."""

    def crear(self, clasificador=None, rect=RECT, falla_despues=None, abre=True, error_clasificador=None):
        self.oyente = OyenteMemoria()
        self.capturas = []

        def fabrica(config):
            if not abre:
                return None
            captura = CapturaSimulada([fotograma()], falla_despues)
            self.capturas.append(captura)
            return captura

        config = ConfigCamara(fuente=0, intervalo_registro=0.05, fallos_maximos=5)
        gestor = GestorCamara(config, DetectorSimulado(rect), clasificador, EMOJIS, oyente=self.oyente,
                              fabrica_captura=fabrica, error_clasificador=error_clasificador)
        self.addCleanup(gestor.detener)
        return gestor

    def test_camara_no_disponible(self):
        gestor = self.crear(ClasificadorSimulado(), abre=False)
        ok, mensaje = gestor.iniciar()
        self.assertFalse(ok)
        self.assertIn("No se pudo abrir la cámara", mensaje)
        self.assertEqual(gestor.estado()["estado"], ERROR)

    def test_camara_abierta_pero_sin_imagen(self):
        ok, mensaje = self.crear(ClasificadorSimulado(), falla_despues=0).iniciar()
        self.assertFalse(ok)
        self.assertIn("no entrega imagen", mensaje)

    def test_reconoce_registra_y_transmite(self):
        gestor = self.crear(ClasificadorSimulado("felicidad", 0.9))
        self.assertTrue(gestor.iniciar()[0])
        self.assertTrue(esperar(lambda: gestor.estado()["expresion"] == "felicidad"))
        estado = gestor.estado()
        self.assertEqual(estado["estado"], ACTIVA)
        self.assertAlmostEqual(estado["probabilidades"]["felicidad"], 90.0, delta=0.5)
        self.assertTrue(esperar(lambda: len(self.oyente.registros) >= 2))
        self.assertEqual(self.oyente.registros[0][1], "felicidad")
        parte = next(gestor.generar_mjpeg())
        self.assertTrue(parte.startswith(b"--frame") and b"\xff\xd8" in parte)
        gestor.detener()
        self.assertEqual(gestor.estado()["estado"], DETENIDA)
        self.assertTrue(self.capturas[0].liberada)
        self.assertEqual(len(self.oyente.finalizadas), 1)
        self.assertGreater(self.oyente.finalizadas[0][1]["conteo"]["felicidad"], 0)

    def test_un_registro_por_segundo_con_el_intervalo_por_defecto(self):
        """Con INTERVALO_REGISTRO=1 se guarda una muestra por segundo, no una por fotograma."""
        self.oyente = OyenteMemoria()
        config = ConfigCamara(fuente=0)                    # intervalo_registro = 1.0 por defecto
        self.assertEqual(config.intervalo_registro, 1.0)
        gestor = GestorCamara(config, DetectorSimulado(RECT), ClasificadorSimulado("felicidad", 0.9), EMOJIS,
                              oyente=self.oyente, fabrica_captura=lambda c: CapturaSimulada([fotograma()]))
        self.addCleanup(gestor.detener)
        gestor.iniciar()
        time.sleep(2.5)
        gestor.detener()
        fotogramas = self.oyente.finalizadas[0][1]["fotogramas"]
        self.assertIn(len(self.oyente.registros), (2, 3))  # ~1 por segundo en 2,5 s
        self.assertGreater(fotogramas, len(self.oyente.registros))

    def test_confianza_es_identica_a_la_probabilidad_de_la_expresion(self):
        gestor = self.crear(ClasificadorSimulado("tristeza", 0.6789))
        gestor.iniciar()
        self.assertTrue(esperar(lambda: gestor.estado()["expresion"] == "tristeza"))
        for _ in range(10):
            estado = gestor.estado()
            self.assertEqual(estado["confianza"], estado["probabilidades"][estado["expresion"]])
        self.assertTrue(esperar(lambda: len(self.oyente.registros) >= 1))
        _, clave, confianza = self.oyente.registros[-1]
        self.assertEqual(confianza, gestor.estado()["probabilidades"][clave])   # lo mismo en PostgreSQL

    def test_etiqueta_del_video_sin_porcentaje(self):
        etiquetas = []
        original = dibujo.resultado_rostro

        def espia(imagen, rect, texto, *args, **kwargs):
            etiquetas.append(texto)
            return original(imagen, rect, texto, *args, **kwargs)

        with mock.patch("vision.camara.dibujo.resultado_rostro", side_effect=espia):
            gestor = self.crear(ClasificadorSimulado("tristeza", 0.68))
            gestor.iniciar()
            self.assertTrue(esperar(lambda: "Tristeza" in etiquetas))
            gestor.detener()
            no_clara = self.crear(ClasificadorSimulado("tristeza", 0.2))   # nada supera el mínimo
            no_clara.iniciar()
            self.assertTrue(esperar(lambda: "Expresion no clara" in etiquetas))
            no_clara.detener()
        self.assertTrue(all("%" not in texto for texto in etiquetas), etiquetas)
        self.assertLessEqual(set(etiquetas), {"Tristeza", "Expresion no clara"})

    def test_expresion_no_clara_no_se_registra(self):
        gestor = self.crear(ClasificadorSimulado("tristeza", 0.2))
        gestor.iniciar()
        self.assertTrue(esperar(lambda: gestor.estado()["rostro"]))
        time.sleep(0.3)
        self.assertIsNone(gestor.estado()["expresion"])
        self.assertEqual(self.oyente.registros, [])

    def test_sin_rostro(self):
        clasificador = ClasificadorSimulado()
        gestor = self.crear(clasificador, rect=None)
        gestor.iniciar()
        time.sleep(0.3)
        self.assertFalse(gestor.estado()["rostro"])
        self.assertIsNone(gestor.estado()["expresion"])
        self.assertEqual(clasificador.llamadas, 0)

    def test_perdida_de_senal(self):
        gestor = self.crear(ClasificadorSimulado(), falla_despues=40)
        gestor.iniciar()
        self.assertTrue(esperar(lambda: gestor.estado()["estado"] == ERROR))
        self.assertIn("Se perdió la señal", gestor.estado()["mensaje"])
        self.assertTrue(self.capturas[0].liberada)

    def test_sin_modelo_el_video_sigue_y_no_crea_sesion(self):
        gestor = self.crear(None, error_clasificador="No se encontró el modelo")
        self.assertTrue(gestor.iniciar()[0])
        self.assertTrue(next(gestor.generar_mjpeg()).startswith(b"--frame"))  # el video sigue
        self.assertFalse(gestor.estado()["modelo"]["disponible"])
        self.assertEqual(self.oyente.sesiones, [])

    def test_error_de_base_de_datos_no_detiene_el_video(self):
        gestor = self.crear(ClasificadorSimulado())

        def falla(*args):
            raise ConnectionError("PostgreSQL apagado")

        self.oyente.expresion_registrada = falla
        gestor.iniciar()
        self.assertTrue(esperar(lambda: gestor.estado()["advertencia"] is not None))
        self.assertEqual(gestor.estado()["estado"], ACTIVA)
        self.assertIn("Base de datos", gestor.estado()["advertencia"])

    def test_iniciar_dos_veces_no_abre_otra_camara(self):
        gestor = self.crear(ClasificadorSimulado())
        gestor.iniciar()
        ok, mensaje = gestor.iniciar()
        self.assertTrue(ok)
        self.assertIn("ya está activa", mensaje)
        self.assertEqual(len(self.capturas), 1)

    def test_con_el_modelo_real(self):
        gestor = self.crear(ClasificadorEmociones())
        gestor.iniciar()
        self.assertTrue(esperar(lambda: sum(gestor.estado()["probabilidades"].values()) > 99))
