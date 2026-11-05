"""
Pruebas de Django (vistas, API, modelos y manejo de errores) contra
PostgreSQL. Django crea y borra una base temporal ``test_<POSTGRES_DB>``.
"""

import time
from unittest import mock

from django.conf import settings
from django.db import OperationalError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from expresiones import servicios
from expresiones.models import RegistroExpresion, SesionAnalisis
from vision.camara import ConfigCamara, GestorCamara

from .utilidades import CapturaSimulada, ClasificadorSimulado, DetectorSimulado, fotograma


class GestorSimuladoMixin:
    """Inyecta un gestor con cámara simulada (no se usa una cámara real)."""

    def setUp(self):
        super().setUp()
        self.gestor = GestorCamara(
            ConfigCamara(fuente=0, intervalo_registro=0.05),
            DetectorSimulado(), ClasificadorSimulado("sorpresa", 0.8),
            settings.DETECTOR_EXPRESIONES["CARPETA_EMOJIS"],
            oyente=servicios.OyenteBaseDatos(),
            fabrica_captura=lambda config: CapturaSimulada([fotograma()]),
        )
        servicios.reemplazar_gestor(self.gestor)
        self.addCleanup(self.gestor.detener)
        self.addCleanup(servicios.reemplazar_gestor, None)

    def post(self, nombre):
        return self.client.post(reverse(f"expresiones:{nombre}"), {}, content_type="application/json")


class BaseWebTest(GestorSimuladoMixin, TestCase):
    pass


class PaginasTests(BaseWebTest):
    def test_paginas_responden(self):
        for nombre in ("panel", "historial", "acerca"):
            respuesta = self.client.get(reverse(f"expresiones:{nombre}"))
            self.assertEqual(respuesta.status_code, 200, nombre)
            self.assertContains(respuesta, "ExpresaVisión")

    def test_panel_muestra_las_seis_expresiones(self):
        respuesta = self.client.get(reverse("expresiones:panel"))
        for nombre in ("Neutral", "Felicidad", "Sorpresa", "Tristeza", "Enojo", "Asco"):
            self.assertContains(respuesta, nombre)
        for nombre in ("Miedo", "Desprecio", "miedo.png", "desprecio.png"):
            self.assertNotContains(respuesta, nombre)
        self.assertContains(respuesta, "emojis/asco.png")

    def test_historial_vacio(self):
        self.assertContains(self.client.get(reverse("expresiones:historial")), "Todavía no hay sesiones")

    def test_detalle_y_eliminacion_de_sesion(self):
        sesion = SesionAnalisis.objects.create()
        RegistroExpresion.objects.create(sesion=sesion, expresion="felicidad", confianza=80)
        RegistroExpresion.objects.create(sesion=sesion, expresion="felicidad", confianza=70)
        RegistroExpresion.objects.create(sesion=sesion, expresion="miedo", confianza=60)
        servicios.finalizar_sesion(sesion.pk, {"fotogramas": 100, "fotogramas_con_rostro": 90})
        sesion.refresh_from_db()
        self.assertEqual(sesion.expresion_predominante, "felicidad")
        self.assertEqual(sesion.total_registros, 3)
        self.assertEqual(sesion.porcentaje_rostro, 90)

        detalle = self.client.get(reverse("expresiones:detalle_sesion", args=[sesion.pk]))
        self.assertContains(detalle, "Felicidad")
        self.assertContains(detalle, "67 %")

        respuesta = self.client.post(reverse("expresiones:eliminar_sesion", args=[sesion.pk]))
        self.assertRedirects(respuesta, reverse("expresiones:historial"))
        self.assertFalse(RegistroExpresion.objects.exists())

    def test_registros_antiguos_de_miedo_y_desprecio_se_muestran_como_otra(self):
        sesion = SesionAnalisis.objects.create()
        for clave in ("miedo", "miedo", "desprecio", "asco"):
            RegistroExpresion.objects.create(sesion=sesion, expresion=clave, confianza=50)
        servicios.finalizar_sesion(sesion.pk)
        sesion.refresh_from_db()
        self.assertEqual(sesion.expresion_predominante, "miedo")   # dato antiguo, tal cual en la base

        historial = self.client.get(reverse("expresiones:historial"))
        self.assertContains(historial, "Otra")
        self.assertNotContains(historial, "Miedo")
        detalle = self.client.get(reverse("expresiones:detalle_sesion", args=[sesion.pk]))
        self.assertEqual(detalle.status_code, 200)
        self.assertContains(detalle, "Otra")
        self.assertContains(detalle, "75 %")                        # miedo + desprecio agrupados
        self.assertNotContains(detalle, "Desprecio")

    def test_sesion_inexistente_404(self):
        self.assertEqual(self.client.get(reverse("expresiones:detalle_sesion", args=[999])).status_code, 404)


class ApiTests(BaseWebTest):
    def test_estado_inicial(self):
        datos = self.client.get(reverse("expresiones:api_estado")).json()
        self.assertTrue(datos["ok"])
        self.assertEqual(datos["estado"]["estado"], "detenida")
        self.assertTrue(datos["estado"]["modelo"]["disponible"])
        self.assertEqual(len(datos["estado"]["probabilidades"]), 6)
        self.assertNotIn("miedo", datos["estado"]["probabilidades"])
        for campo in ("linea_base", "deltas", "calibracion"):
            self.assertIn(campo, datos["estado"])

    def test_get_no_permitido_en_acciones(self):
        self.assertEqual(self.client.get(reverse("expresiones:api_iniciar")).status_code, 405)

    def test_panel_js_usa_una_sola_fuente_para_los_porcentajes(self):
        """Cabecera y barras leen estado.probabilidades y redondean con Math.round."""
        from django.contrib.staticfiles import finders

        codigo = open(finders.find("expresiones/js/panel.js"), encoding="utf-8").read()
        self.assertIn("Math.round(probabilidades[clave] || 0)", codigo)
        self.assertIn("valor = porcentaje(estado, estado.expresion);", codigo)
        self.assertIn("pintarBarra(fila, porcentaje(estado, clave));", codigo)
        self.assertNotIn("estado.confianza", codigo)
        self.assertNotIn("toFixed", codigo)

    def test_panel_simplificado(self):
        respuesta = self.client.get(reverse("expresiones:panel"))
        for texto in ("Detector de expresiones faciales", "en vivo", "Video en tiempo real",
                      "Probabilidades en vivo", 'id="btn-camara"', 'id="info-fps"',
                      "Expresión estimada",
                      "Estimación de la expresión visible, no del estado emocional real",
                      "Detector de expresiones faciales en tiempo real", "Noto Emoji"):
            self.assertContains(respuesta, texto)
        # El panel es solo de detección en vivo: sin selector de cámara, sin resumen
        # (está en Historial) y sin avisos de calibración.
        for texto in ("<select", "Resumen de esta sesión", "Calibrando"):
            self.assertNotContains(respuesta, texto)
        self.assertContains(respuesta, '<svg class="icono-svg"')     # iconos en línea, sin CDN
        self.assertNotContains(respuesta, "cdn.")

    def test_video_con_camara_detenida(self):
        self.assertEqual(self.client.get(reverse("expresiones:video")).status_code, 409)


class FlujoCompletoTests(GestorSimuladoMixin, TransactionTestCase):
    """El hilo de la cámara escribe con su propia conexión: se usa TransactionTestCase."""

    def test_iniciar_reconocer_guardar_y_detener(self):
        datos = self.post("api_iniciar").json()
        self.assertTrue(datos["ok"])
        self.assertEqual(datos["estado"]["estado"], "activa")

        respuesta = self.client.get(reverse("expresiones:video"))
        self.assertTrue(respuesta["Content-Type"].startswith("multipart/x-mixed-replace"))
        self.assertTrue(next(iter(respuesta.streaming_content)).startswith(b"--frame"))

        for _ in range(100):
            if RegistroExpresion.objects.count() >= 2:
                break
            time.sleep(0.05)
        estado = self.client.get(reverse("expresiones:api_estado")).json()["estado"]
        self.assertEqual(estado["expresion"], "sorpresa")

        # Al iniciar la cámara se creó una SesionAnalisis abierta.
        sesion = SesionAnalisis.objects.get()
        self.assertEqual(sesion.estado, SesionAnalisis.ACTIVA)
        self.assertIsNone(sesion.fin)

        self.assertEqual(self.post("api_detener").json()["estado"]["estado"], "detenida")
        sesion.refresh_from_db()
        # Al detener: fin, expresión predominante, total de registros y % de rostro.
        self.assertEqual(sesion.estado, SesionAnalisis.FINALIZADA)
        self.assertIsNotNone(sesion.fin)
        self.assertGreaterEqual(sesion.fin, sesion.inicio)
        self.assertEqual(sesion.expresion_predominante, "sorpresa")
        self.assertGreaterEqual(sesion.total_registros, 2)
        self.assertEqual(sesion.total_registros, sesion.registros.count())
        self.assertGreater(sesion.fotogramas_procesados, 0)
        self.assertEqual(sesion.porcentaje_rostro, 100)   # el detector simulado siempre ve un rostro
        self.assertTrue(all(r.expresion == "sorpresa" for r in sesion.registros.all()))

        # /historial/ y /historial/<id>/ muestran los datos guardados.
        historial = self.client.get(reverse("expresiones:historial"))
        self.assertEqual(historial.status_code, 200)
        self.assertContains(historial, reverse("expresiones:detalle_sesion", args=[sesion.pk]))
        self.assertContains(historial, "Sorpresa")
        self.assertContains(historial, "Finalizada")
        self.assertContains(historial, "100 %")
        detalle = self.client.get(reverse("expresiones:detalle_sesion", args=[sesion.pk]))
        self.assertEqual(detalle.status_code, 200)
        self.assertContains(detalle, f"Sesión <span class=\"acento\">{sesion.pk}</span>", html=False)
        self.assertContains(detalle, "Sorpresa")
        self.assertContains(detalle, "100 %")                  # distribución: todo sorpresa
        self.assertContains(detalle, 'class="linea-tiempo"')
        self.assertContains(detalle, f"<strong>{sesion.total_registros}</strong>")

class OyenteBaseDatosTests(TestCase):
    def test_ciclo_de_sesion(self):
        oyente = servicios.OyenteBaseDatos()
        abierta = SesionAnalisis.objects.create()  # quedó abierta por un cierre inesperado
        sesion_id = oyente.sesion_iniciada()
        abierta.refresh_from_db()
        self.assertEqual(abierta.estado, SesionAnalisis.INTERRUMPIDA)

        oyente.expresion_registrada(sesion_id, "asco", 75.5)
        oyente.sesion_finalizada(sesion_id, {"fotogramas": 10, "fotogramas_con_rostro": 4})
        sesion = SesionAnalisis.objects.get(pk=sesion_id)
        self.assertEqual(sesion.estado, SesionAnalisis.FINALIZADA)
        self.assertEqual(sesion.expresion_predominante, "asco")
        self.assertIsNotNone(sesion.fin)


class ErroresTests(BaseWebTest):
    def test_pagina_amigable_si_postgresql_no_responde(self):
        with mock.patch("expresiones.views.SesionAnalisis.objects.all",
                        side_effect=OperationalError("connection refused")):
            respuesta = self.client.get(reverse("expresiones:historial"))
        self.assertEqual(respuesta.status_code, 503)
        self.assertContains(respuesta, "No se pudo conectar a PostgreSQL", status_code=503)

    def test_api_informa_detector_faltante(self):
        with mock.patch.object(servicios, "obtener_gestor", return_value=(None, "No se encontró el detector")):
            respuesta = self.client.get(reverse("expresiones:api_estado"))
        self.assertEqual(respuesta.status_code, 503)
        self.assertIn("detector", respuesta.json()["mensaje"])

    def test_aviso_si_falta_el_modelo(self):
        self.gestor.clasificador = None
        self.gestor.error_clasificador = "No se encontró el modelo de emociones"
        respuesta = self.client.get(reverse("expresiones:panel"))
        self.assertContains(respuesta, "Modelo de emociones no disponible")
