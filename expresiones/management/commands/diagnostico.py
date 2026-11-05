"""
python manage.py diagnostico [--camara]

Revisa paso a paso que el entorno esté listo: versiones, detector Haar,
modelo FER+ (existencia, huella SHA-256 e inferencia de prueba), emojis,
PostgreSQL, migraciones y, opcionalmente, la cámara.
"""

import platform
import sys
import time

import cv2
import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from vision import expresiones as cat
from vision.camara import ConfigCamara, abrir_captura, mensaje_camara_no_disponible
from vision.clasificador import SHA256_MODELO, ClasificadorEmociones, ErrorModelo, sha256_archivo
from vision.detector_rostros import DetectorRostros, ErrorDetector


class Command(BaseCommand):
    """Comando ``diagnostico``: muestra [OK], [!] o [X] para cada requisito."""
    help = "Verifica la instalación (OpenCV, modelo FER+, PostgreSQL, migraciones y cámara)."

    def add_arguments(self, parser):
        """Opción ``--camara`` para probar también la cámara."""
        parser.add_argument("--camara", action="store_true", help="Intenta abrir la cámara y leer un fotograma.")

    def _ok(self, texto):
        """Escribe una línea correcta."""
        self.stdout.write(self.style.SUCCESS("  [OK]  ") + texto)

    def _mal(self, texto):
        """Escribe un problema y lo cuenta (el comando termina con código 1)."""
        self.errores += 1
        self.stdout.write(self.style.ERROR("  [X]   ") + texto)

    def _aviso(self, texto):
        """Escribe una advertencia que no impide usar la aplicación."""
        self.stdout.write(self.style.WARNING("  [!]   ") + texto)

    def handle(self, *args, **opciones):
        """Ejecuta todas las revisiones en orden y resume el resultado."""
        self.errores = 0
        conf = settings.DETECTOR_EXPRESIONES
        self.stdout.write(self.style.MIGRATE_HEADING("Diagnóstico de ExpresaVisión"))
        self._ok(f"Python {platform.python_version()} ({sys.executable})")
        self._ok(f"OpenCV {cv2.__version__}")

        try:
            DetectorRostros()
            self._ok("Detector de rostros Haar Cascade cargado")
        except ErrorDetector as exc:
            self._mal(str(exc))

        self._revisar_modelo(conf["MODELO_EMOCIONES"])

        faltantes = [e.emoji for e in cat.EXPRESIONES if not (conf["CARPETA_EMOJIS"] / e.emoji).exists()]
        if faltantes:
            self._aviso(f"Faltan emojis: {', '.join(faltantes)} (el video funciona sin ellos)")
        else:
            self._ok("Emojis Noto disponibles")

        self._revisar_sensibilidad(conf)
        self._revisar_postgresql()

        if opciones["camara"]:
            self._revisar_camara(conf)
        else:
            self._aviso("Cámara no probada (agregue --camara para probarla).")

        if self.errores:
            self.stdout.write(self.style.ERROR(f"\n{self.errores} problema(s) encontrado(s)."))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS("\nTodo listo. Ejecute: python manage.py runserver"))

    def _revisar_modelo(self, ruta):
        """Comprueba que el modelo FER+ exista, tenga la huella correcta y se ejecute."""
        if not ruta.is_file():
            self._mal(f"No existe el modelo {ruta}. Vea la sección 'Modelo' del README.")
            return
        huella = sha256_archivo(ruta)
        if huella == SHA256_MODELO:
            self._ok("Modelo FER+ presente y con la huella SHA-256 correcta")
        else:
            self._mal(f"El archivo del modelo no coincide (SHA-256 {huella[:12]}…). Descárguelo de nuevo.")
            return
        try:
            clasificador = ClasificadorEmociones(ruta)
            inicio = time.perf_counter()
            probabilidades = clasificador.predecir(np.full((96, 96), 128, np.uint8))
            ms = (time.perf_counter() - inicio) * 1000
            self._ok(f"Modelo cargado en cv2.dnn: {len(probabilidades)} expresiones, inferencia de prueba {ms:.0f} ms")
        except ErrorModelo as exc:
            self._mal(str(exc))

    def _revisar_sensibilidad(self, conf):
        """Muestra la configuración de la línea base automática."""
        if conf["DURACION_CALIBRACION"] > 0:
            self._ok(f"Línea base: {conf['DURACION_CALIBRACION']:g} s de cara relajada; "
                     f"UMBRAL_CAMBIO {conf['UMBRAL_CAMBIO']:g}; ventana {conf['VENTANA_MINIMO']} de "
                     f"{conf['VENTANA_FOTOGRAMAS']} fotogramas; ALFA_SUAVIZADO {conf['ALFA_SUAVIZADO']:g}")
        else:
            self._aviso("Línea base desactivada (DURACION_CALIBRACION=0): se usa CONFIANZA_MINIMA.")

    def _revisar_postgresql(self):
        """Comprueba la conexión a PostgreSQL y las migraciones pendientes."""
        try:
            connection.ensure_connection()
            datos = connection.settings_dict
            self._ok(f"PostgreSQL conectado: base '{datos['NAME']}' en {datos['HOST']}:{datos['PORT']}")
            ejecutor = MigrationExecutor(connection)
            pendientes = ejecutor.migration_plan(ejecutor.loader.graph.leaf_nodes())
            if pendientes:
                self._mal(f"Hay {len(pendientes)} migraciones pendientes: python manage.py migrate")
            else:
                self._ok("Migraciones aplicadas")
        except Exception as exc:  # noqa: BLE001 - se informa cualquier problema de conexión
            self._mal(f"No se pudo conectar a PostgreSQL: {exc}".strip())

    def _revisar_camara(self, conf):
        """Abre la cámara de ``CAMARA_FUENTE`` y lee un fotograma."""
        config = ConfigCamara(fuente=conf["CAMARA_FUENTE"], backend=conf["CAMARA_BACKEND"],
                              ancho=conf["CAMARA_ANCHO"], alto=conf["CAMARA_ALTO"])
        captura = abrir_captura(config)
        if captura is None:
            self._mal(mensaje_camara_no_disponible(config.fuente))
            return
        leido, fotograma = False, None
        for _ in range(30):
            leido, fotograma = captura.read()
            if leido:
                break
        captura.release()
        if leido:
            self._ok(f"Cámara {config.fuente} entrega imagen de {fotograma.shape[1]}x{fotograma.shape[0]}")
        else:
            self._mal("La cámara se abrió pero no entregó imagen.")
