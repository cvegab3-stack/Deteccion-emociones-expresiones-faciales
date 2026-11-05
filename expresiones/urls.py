"""Rutas de la aplicación: páginas, video MJPEG y API JSON."""

from django.urls import path

from . import views

app_name = "expresiones"

urlpatterns = [
    # Páginas
    path("", views.panel, name="panel"),
    path("historial/", views.historial, name="historial"),
    path("historial/<int:sesion_id>/", views.detalle_sesion, name="detalle_sesion"),
    path("historial/<int:sesion_id>/eliminar/", views.eliminar_sesion, name="eliminar_sesion"),
    path("acerca/", views.acerca, name="acerca"),
    # Video en tiempo real (MJPEG)
    path("video/", views.video, name="video"),
    # API JSON
    path("api/estado/", views.api_estado, name="api_estado"),
    path("api/camara/iniciar/", views.api_iniciar, name="api_iniciar"),
    path("api/camara/detener/", views.api_detener, name="api_detener"),
]
