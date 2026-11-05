"""
Vistas web (páginas HTML) y API JSON que usa la interfaz.

Páginas: panel en vivo, historial, detalle de sesión y "cómo funciona".
API: iniciar/detener cámara y estado. El video se transmite como MJPEG en
``/video/``. La aplicación es solo de detección en vivo: no captura ni
guarda fotos. La cámara es siempre la de ``CAMARA_FUENTE`` (archivo .env).
"""

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.views.decorators.http import require_GET, require_POST

from vision import expresiones as cat

from . import servicios
from .models import SesionAnalisis


# ================================================================ apoyo
def catalogo_interfaz():
    """Datos de cada expresión para las plantillas y JavaScript."""
    return [
        {"clave": e.clave, "nombre": e.nombre, "emoji": static(f"expresiones/emojis/{e.emoji}"),
         "color": e.color_hex}
        for e in cat.EXPRESIONES
    ]


def _emojis_especiales():
    """Rutas de los emojis de estados especiales (no clara, sin rostro)."""
    return {
        "desconocida": static(f"expresiones/emojis/{cat.EMOJI_DESCONOCIDA}"),
        "sin_rostro": static(f"expresiones/emojis/{cat.EMOJI_SIN_ROSTRO}"),
    }


def _contexto_base(**extra):
    """Contexto común de todas las páginas (catálogo, emojis y errores)."""
    gestor, error = servicios.obtener_gestor()
    contexto = {
        "catalogo": catalogo_interfaz(),
        "emojis_especiales": _emojis_especiales(),
        "error_gestor": error,
        "modelo": gestor.info_modelo() if gestor else None,
    }
    contexto.update(extra)
    return contexto


def _respuesta(ok, mensaje, gestor=None, estado_http=None):
    """Respuesta JSON estándar de la API: ``ok``, ``mensaje`` y, si hay, ``estado``."""
    datos = {"ok": ok, "mensaje": mensaje}
    if gestor is not None:
        datos["estado"] = gestor.estado()
    return JsonResponse(datos, status=estado_http or (200 if ok else 400))


def _gestor_o_error():
    """Devuelve ``(gestor, None)`` o ``(None, respuesta 503)`` si la visión no cargó."""
    gestor, error = servicios.obtener_gestor()
    if gestor is None:
        return None, _respuesta(False, error or "El módulo de visión no está disponible.", estado_http=503)
    return gestor, None


# ============================================================== páginas
@require_GET
def panel(request):
    """Página «En vivo»: video, expresión estimada y probabilidades."""
    return render(request, "expresiones/panel.html", _contexto_base(seccion="panel"))


@require_GET
def historial(request):
    """Lista paginada de sesiones guardadas."""
    pagina = Paginator(SesionAnalisis.objects.all(), 15).get_page(request.GET.get("pagina"))
    return render(request, "expresiones/historial.html", _contexto_base(seccion="historial", pagina=pagina))


@require_GET
def detalle_sesion(request, sesion_id):
    """Detalle de una sesión: indicadores, línea de tiempo y distribución."""
    sesion = get_object_or_404(SesionAnalisis, pk=sesion_id)
    distribucion = servicios.distribucion_sesion(sesion.pk)
    total_registros = sum(c for _, c in distribucion)
    total = total_registros or 1
    # Las claves que ya no están en el catálogo (miedo, desprecio de versiones
    # anteriores) se agrupan en una sola barra "Otra".
    cantidades = {}
    for clave, cantidad in distribucion:
        expresion = cat.obtener_o_otra(clave) or cat.OTRA
        cantidades[expresion] = cantidades.get(expresion, 0) + cantidad
    barras = [
        {"expresion": expresion, "cantidad": cantidad, "porcentaje": round(100 * cantidad / total, 1)}
        for expresion, cantidad in sorted(cantidades.items(), key=lambda par: -par[1])
    ]
    linea = []
    for r in sesion.registros.all()[:900]:
        expresion = cat.obtener_o_otra(r.expresion) or cat.OTRA
        linea.append({"color": expresion.color_hex, "nombre": expresion.nombre,
                      "hora": r.registrado_en, "confianza": r.confianza})
    hay_otra = cat.OTRA in cantidades
    return render(request, "expresiones/detalle_sesion.html", _contexto_base(
        seccion="historial", sesion=sesion, barras=barras, linea=linea, total_registros=total_registros,
        otra=cat.OTRA if hay_otra else None))


@require_POST
def eliminar_sesion(request, sesion_id):
    """Elimina una sesión y sus registros (no la sesión en curso)."""
    gestor, _ = servicios.obtener_gestor()
    activa = gestor.estado()["sesion"] if gestor else None
    if activa and activa.get("id") == sesion_id:
        messages.error(request, "No se puede eliminar la sesión mientras la cámara está activa.")
        return redirect("expresiones:detalle_sesion", sesion_id=sesion_id)
    get_object_or_404(SesionAnalisis, pk=sesion_id).delete()
    messages.success(request, f"Sesión {sesion_id} eliminada junto con sus registros.")
    return redirect("expresiones:historial")


@require_GET
def acerca(request):
    """Página «Cómo funciona»."""
    opciones = settings.DETECTOR_EXPRESIONES
    return render(request, "expresiones/acerca.html", _contexto_base(
        seccion="acerca", confianza_minima=round(100 * opciones["CONFIANZA_MINIMA"]),
        intervalo=opciones["INTERVALO_REGISTRO"],
        duracion_calibracion=f"{opciones['DURACION_CALIBRACION']:g}",
        umbral_cambio=round(100 * opciones["UMBRAL_CAMBIO"]),
        ventana=opciones["VENTANA_FOTOGRAMAS"], ventana_minimo=opciones["VENTANA_MINIMO"]))


# ===================================================================== API
@require_GET
def api_estado(request):
    """Estado actual de la cámara y de la estimación (lo consulta el panel)."""
    gestor, error = _gestor_o_error()
    if error:
        return error
    return JsonResponse({"ok": True, "estado": gestor.estado()})


@require_POST
def api_iniciar(request):
    """Abre la cámara de ``CAMARA_FUENTE`` e inicia una sesión."""
    gestor, error = _gestor_o_error()
    if error:
        return error
    ok, mensaje = gestor.iniciar()
    return _respuesta(ok, mensaje, gestor, estado_http=200 if ok else 409)


@require_POST
def api_detener(request):
    """Detiene la cámara y cierra la sesión."""
    gestor, error = _gestor_o_error()
    if error:
        return error
    ok, mensaje = gestor.detener()
    return _respuesta(ok, mensaje, gestor)


# ================================================================== video
@require_GET
def video(request):
    """Transmisión MJPEG: el navegador la muestra en una etiqueta <img>."""
    gestor, error = servicios.obtener_gestor()
    if gestor is None:
        return HttpResponse(error or "Módulo de visión no disponible.", status=503, content_type="text/plain")
    if not gestor.activa:
        return HttpResponse("La cámara está detenida.", status=409, content_type="text/plain")
    respuesta = StreamingHttpResponse(gestor.generar_mjpeg(),
                                      content_type="multipart/x-mixed-replace; boundary=frame")
    respuesta["Cache-Control"] = "no-cache, no-store, must-revalidate"
    respuesta["X-Accel-Buffering"] = "no"
    return respuesta
