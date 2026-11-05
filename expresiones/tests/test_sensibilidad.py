"""
Pruebas de la sensibilidad respecto a la cara neutra (línea base, decisión
por cambio y ventana de votos), sin cámara. La expresión depende solo del
modelo FER+.
"""

import time

from django.conf import settings
from django.test import SimpleTestCase

from vision import expresiones as cat
from vision.camara import ConfigCamara, GestorCamara
from vision.sensibilidad import (CALIBRANDO, DESACTIVADA, LISTA, ConfigDecision, LineaBase, MotorDecision,
                                 VentanaVotos, decidir_por_cambio)

from .utilidades import CapturaSimulada, DetectorSimulado, OyenteMemoria, fotograma

EMOJIS = settings.DETECTOR_EXPRESIONES["CARPETA_EMOJIS"]


def distribucion(**valores):
    """Probabilidades con los valores dados; el resto se reparte en partes iguales."""
    resto = (1.0 - sum(valores.values())) / (len(cat.CLAVES) - len(valores))
    return {c: valores.get(c, resto) for c in cat.CLAVES}


BASE_NEUTRAL = distribucion(neutral=0.86, enojo=0.04)


def esperar(condicion, limite=5.0):
    fin = time.time() + limite
    while time.time() < fin:
        if condicion():
            return True
        time.sleep(0.02)
    return False


class DecisionPorCambioTests(SimpleTestCase):
    def test_enojo_que_sube_diez_puntos_gana(self):
        actual = distribucion(neutral=0.76, enojo=0.14)
        clave, deltas = decidir_por_cambio(actual, BASE_NEUTRAL, 0.08)
        self.assertEqual(clave, "enojo")
        self.assertAlmostEqual(deltas["enojo"], 0.10)
        self.assertNotIn("neutral", deltas)

    def test_cambio_de_tres_puntos_sigue_neutral(self):
        actual = distribucion(neutral=0.83, enojo=0.07)
        clave, deltas = decidir_por_cambio(actual, BASE_NEUTRAL, 0.08)
        self.assertEqual(clave, "neutral")
        self.assertAlmostEqual(deltas["enojo"], 0.03)

    def test_gana_el_mayor_delta(self):
        actual = distribucion(neutral=0.60, enojo=0.14, tristeza=0.20)
        self.assertEqual(decidir_por_cambio(actual, BASE_NEUTRAL, 0.08)[0], "tristeza")

    def test_deltas_solo_de_las_cinco_expresiones_no_neutrales(self):
        _, deltas = decidir_por_cambio(BASE_NEUTRAL, BASE_NEUTRAL, 0.08)
        self.assertEqual(set(deltas), {"felicidad", "sorpresa", "tristeza", "enojo", "asco"})


class VentanaVotosTests(SimpleTestCase):
    def test_tres_de_cinco(self):
        v = VentanaVotos(5, 3)
        self.assertIsNone(v.agregar("enojo"))
        self.assertIsNone(v.agregar("enojo"))
        self.assertEqual(v.agregar("enojo"), "enojo")      # 3 de 3

    def test_un_parpadeo_no_cambia_la_decision(self):
        v = VentanaVotos(5, 3)
        for _ in range(5):
            v.agregar("neutral")
        self.assertEqual(v.agregar("enojo"), "neutral")
        self.assertEqual(v.agregar("enojo"), "neutral")    # 2 de 5: aún no
        self.assertEqual(v.agregar("enojo"), "enojo")      # 3 de 5

    def test_alternancia_conserva_el_ultimo_estable(self):
        v = VentanaVotos(5, 3)
        for valor in ("a", "a", "a", "b", "c", "b", "c"):
            resultado = v.agregar(valor)
        self.assertEqual(resultado, "a")

    def test_parametros_invalidos(self):
        with self.assertRaises(ValueError):
            VentanaVotos(5, 6)


class LineaBaseTests(SimpleTestCase):
    def test_promedia_durante_la_duracion(self):
        base = LineaBase(duracion=1.0)
        self.assertEqual(base.estado, CALIBRANDO)
        base.agregar(0.0, distribucion(neutral=0.8))
        base.agregar(0.5, distribucion(neutral=0.9))
        self.assertAlmostEqual(base.progreso, 0.5)
        self.assertFalse(base.lista)
        base.agregar(0.5, distribucion(neutral=0.7))
        self.assertEqual(base.estado, LISTA)
        self.assertAlmostEqual(base.probabilidades["neutral"], 0.8)
        self.assertAlmostEqual(sum(base.probabilidades.values()), 1.0)
        self.assertEqual(set(base.probabilidades), set(cat.CLAVES))

    def test_desactivada(self):
        base = LineaBase(duracion=0)
        base.agregar(1.0, distribucion(neutral=0.8))
        self.assertEqual(base.estado, DESACTIVADA)
        self.assertFalse(base.lista)


class MotorDecisionTests(SimpleTestCase):
    def calibrado(self, **cambios):
        motor = MotorDecision(ConfigDecision(duracion_calibracion=0.3, **cambios))
        for _ in range(4):
            motor.actualizar(BASE_NEUTRAL, BASE_NEUTRAL, dt=0.1)
        self.assertTrue(motor.linea_base.lista)
        return motor

    def test_antes_de_la_linea_base_usa_el_comportamiento_clasico(self):
        motor = MotorDecision(ConfigDecision(duracion_calibracion=3, confianza_minima=0.4))
        for _ in range(3):
            d = motor.actualizar(BASE_NEUTRAL, BASE_NEUTRAL, dt=0.1)
        self.assertEqual((d.clave, d.calibracion), ("neutral", CALIBRANDO))
        self.assertAlmostEqual(d.progreso, 0.1)
        self.assertIsNone(d.linea_base)

    def test_despues_de_la_linea_base_decide_por_cambio(self):
        motor = self.calibrado()
        enojo = distribucion(neutral=0.76, enojo=0.14)
        for _ in range(3):
            d = motor.actualizar(enojo, enojo, dt=0.1)
        self.assertEqual((d.clave, d.calibracion), ("enojo", LISTA))
        self.assertAlmostEqual(d.confianza, 0.14)               # probabilidad actual de la clase
        self.assertAlmostEqual(d.deltas["enojo"], 0.10)
        self.assertAlmostEqual(d.linea_base["neutral"], 0.86)

    def test_cambio_pequeno_es_neutral(self):
        motor = self.calibrado()
        poco = distribucion(neutral=0.83, enojo=0.07)
        for _ in range(3):
            d = motor.actualizar(poco, poco, dt=0.1)
        self.assertEqual(d.clave, "neutral")

    def test_solo_decide_el_modelo(self):
        """Si el modelo da Felicidad 99 %, la expresión estimada es Felicidad."""
        motor = self.calibrado()
        feliz = distribucion(neutral=0.005, felicidad=0.99)
        for _ in range(3):
            d = motor.actualizar(feliz, feliz, dt=0.1)
        self.assertEqual(d.clave, "felicidad")

    def test_nueva_linea_base(self):
        motor = self.calibrado()
        motor.nueva_linea_base()
        self.assertEqual(motor.linea_base.estado, CALIBRANDO)
        self.assertEqual(motor.linea_base.progreso, 0.0)


class ClasificadorCambiante:
    """Devuelve ``inicial`` hasta que la prueba cambia ``actual``."""

    def __init__(self, inicial):
        self.actual = inicial

    def predecir(self, gris_rostro):
        return dict(self.actual)


class GestorConLineaBaseTests(SimpleTestCase):
    def crear(self, clasificador, duracion=0.3):
        config = ConfigCamara(fuente=0, intervalo_registro=0.05, duracion_calibracion=duracion)
        gestor = GestorCamara(config, DetectorSimulado(), clasificador, EMOJIS, oyente=OyenteMemoria(),
                              fabrica_captura=lambda c: CapturaSimulada([fotograma()]))
        self.addCleanup(gestor.detener)
        return gestor

    def test_calibra_y_luego_detecta_el_cambio(self):
        clasificador = ClasificadorCambiante(BASE_NEUTRAL)
        gestor = self.crear(clasificador)
        self.assertTrue(gestor.iniciar()[0])
        self.assertTrue(esperar(lambda: gestor.estado()["calibracion"]["estado"] == LISTA))
        estado = gestor.estado()
        self.assertEqual(estado["expresion"], "neutral")
        self.assertAlmostEqual(estado["linea_base"]["neutral"], 86.0, delta=0.5)
        self.assertEqual(set(estado["deltas"]), set(cat.CLAVES) - {"neutral"})

        clasificador.actual = distribucion(neutral=0.74, enojo=0.16)
        self.assertTrue(esperar(lambda: gestor.estado()["expresion"] == "enojo"))
        self.assertGreaterEqual(gestor.estado()["deltas"]["enojo"], 8.0)

    def test_linea_base_automatica(self):
        """La línea base se mide sola al iniciar; mientras tanto el modelo funciona normal."""
        gestor = self.crear(ClasificadorCambiante(BASE_NEUTRAL), duracion=0.5)
        gestor.iniciar()
        self.assertTrue(esperar(lambda: gestor.estado()["calibracion"]["estado"] == CALIBRANDO
                                and gestor.estado()["rostro"]))
        self.assertTrue(esperar(lambda: gestor.estado()["expresion"] == "neutral"))
        self.assertTrue(esperar(lambda: gestor.estado()["calibracion"]["estado"] == LISTA))

    def test_la_camara_es_siempre_la_de_la_configuracion(self):
        abiertas = []

        def fabrica(config):
            abiertas.append(config.fuente)
            return CapturaSimulada([fotograma()])

        config = ConfigCamara(fuente=0, intervalo_registro=0.05)
        gestor = GestorCamara(config, DetectorSimulado(), ClasificadorCambiante(BASE_NEUTRAL), EMOJIS,
                              oyente=OyenteMemoria(), fabrica_captura=fabrica)
        self.addCleanup(gestor.detener)
        for _ in range(2):
            self.assertTrue(gestor.iniciar()[0])
            gestor.detener()
        self.assertEqual(abiertas, [0, 0])
