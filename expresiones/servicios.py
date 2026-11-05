"""
Conexión entre el módulo de visión (``vision``) y Django.

* ``OyenteBaseDatos`` recibe los eventos del ``GestorCamara`` y los guarda
  en PostgreSQL con el ORM de Django.
* ``obtener_gestor()`` crea una única instancia del gestor de cámara para
  todo el servidor (la cámara solo se puede abrir una vez).
"""

import logging
import threading

from django.conf import settings
from django.db import close_old_connections, connection, transaction
from django.db.models import Count
from django.utils import timezone

from vision.camara import ConfigCamara, GestorCamara
from vision.clasificador import ClasificadorEmociones, ErrorModelo
from vision.detector_rostros import DetectorRostros, ErrorDetector

from .models import RegistroExpresion, SesionAnalisis

registro_log = logging.getLogger("expresiones")


class OyenteBaseDatos:
    """Guarda en PostgreSQL lo que ocurre en la cámara (se ejecuta en el hilo de la cámara)."""

    def _con_conexion(self, funcion, *args):
        # El hilo de la cámara abre y cierra su propia conexión a PostgreSQL
        # para no dejar conexiones colgadas ni reutilizar una que se cortó.
        """Ejecuta ``funcion`` con una conexión propia si se llama desde el hilo de la cámara."""
        en_hilo_camara = threading.current_thread() is not threading.main_thread()
        if en_hilo_camara:
            close_old_connections()
        try:
            return funcion(*args)
        finally:
            if en_hilo_camara:
                connection.close()

    def sesion_iniciada(self):
        """Crea la sesión (y cierra las que quedaron abiertas). Devuelve su id."""
        def crear():
            # Sesiones que quedaron abiertas por un cierre inesperado del servidor.
            """Cierra sesiones huérfanas y crea una nueva."""
            SesionAnalisis.objects.filter(estado=SesionAnalisis.ACTIVA).update(
                estado=SesionAnalisis.INTERRUMPIDA, fin=timezone.now())
            return SesionAnalisis.objects.create().pk
        return self._con_conexion(crear)

    def expresion_registrada(self, sesion_id, clave, confianza):
        """Guarda la muestra de este segundo."""
        self._con_conexion(lambda: RegistroExpresion.objects.create(
            sesion_id=sesion_id, expresion=clave, confianza=confianza))

    def sesion_finalizada(self, sesion_id, resumen):
        """Cierra la sesión con su resumen."""
        self._con_conexion(finalizar_sesion, sesion_id, resumen)


def distribucion_sesion(sesion_id):
    """Lista ``[(clave, cantidad), ...]`` ordenada de mayor a menor."""
    filas = (RegistroExpresion.objects.filter(sesion_id=sesion_id)
             .values("expresion").annotate(cantidad=Count("id")).order_by("-cantidad", "expresion"))
    return [(f["expresion"], f["cantidad"]) for f in filas]


def finalizar_sesion(sesion_id, resumen=None, estado=SesionAnalisis.FINALIZADA):
    """Cierra la sesión y calcula la expresión predominante con una consulta agregada."""
    resumen = resumen or {}
    distribucion = distribucion_sesion(sesion_id)
    with transaction.atomic():
        SesionAnalisis.objects.filter(pk=sesion_id).update(
            fin=timezone.now(),
            estado=estado,
            expresion_predominante=distribucion[0][0] if distribucion else "",
            total_registros=sum(c for _, c in distribucion),
            fotogramas_procesados=resumen.get("fotogramas", 0),
            fotogramas_con_rostro=resumen.get("fotogramas_con_rostro", 0),
        )


# ------------------------------------------------------------- singleton
_gestor = None
_error_gestor = None
_bloqueo = threading.Lock()


def config_camara():
    """``ConfigCamara`` con los valores de ``settings.DETECTOR_EXPRESIONES`` (archivo .env)."""
    opciones = settings.DETECTOR_EXPRESIONES
    return ConfigCamara(
        fuente=opciones["CAMARA_FUENTE"],
        ancho=opciones["CAMARA_ANCHO"],
        alto=opciones["CAMARA_ALTO"],
        backend=opciones["CAMARA_BACKEND"],
        espejo=opciones["CAMARA_ESPEJO"],
        confianza_minima=opciones["CONFIANZA_MINIMA"],
        alfa_suavizado=opciones["ALFA_SUAVIZADO"],
        intervalo_registro=opciones["INTERVALO_REGISTRO"],
        duracion_calibracion=opciones["DURACION_CALIBRACION"],
        umbral_cambio=opciones["UMBRAL_CAMBIO"],
        ventana_fotogramas=opciones["VENTANA_FOTOGRAMAS"],
        ventana_minimo=opciones["VENTANA_MINIMO"],
    )


def _crear_gestor():
    """Crea el único ``GestorCamara`` del servidor con la configuración del .env."""
    opciones = settings.DETECTOR_EXPRESIONES
    config = config_camara()
    detector = DetectorRostros()  # puede lanzar ErrorDetector
    clasificador, error_clasificador = None, None
    try:
        clasificador = ClasificadorEmociones(opciones["MODELO_EMOCIONES"])
    except ErrorModelo as exc:
        error_clasificador = str(exc)
        registro_log.error(error_clasificador)
    return GestorCamara(config, detector, clasificador, opciones["CARPETA_EMOJIS"],
                        oyente=OyenteBaseDatos(), error_clasificador=error_clasificador)


def obtener_gestor():
    """Devuelve ``(gestor, error)``. Si el detector no carga, ``gestor`` es ``None``."""
    global _gestor, _error_gestor
    with _bloqueo:
        if _gestor is None and _error_gestor is None:
            try:
                _gestor = _crear_gestor()
            except ErrorDetector as exc:
                _error_gestor = str(exc)
                registro_log.error(_error_gestor)
        return _gestor, _error_gestor


def reemplazar_gestor(gestor):
    """Solo para pruebas: inyecta un gestor con una cámara simulada."""
    global _gestor, _error_gestor
    with _bloqueo:
        _gestor, _error_gestor = gestor, None
