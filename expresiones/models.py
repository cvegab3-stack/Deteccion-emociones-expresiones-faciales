"""
Modelos guardados en PostgreSQL.

Qué se guarda (y qué NO):

* ``SesionAnalisis``: cada uso del panel en vivo (inicio, fin, expresión
  predominante y número de fotogramas procesados y con rostro).
* ``RegistroExpresion``: una muestra por segundo con la expresión estimada
  y su confianza (%).

NO se guardan fotos ni video en la base de datos ni en disco.
"""

from django.db import models
from django.utils import timezone

from vision import expresiones as catalogo

OPCIONES_EXPRESION = catalogo.opciones_django()


class SesionAnalisis(models.Model):
    """Una sesión del Panel en vivo: desde que se inicia la cámara hasta que se detiene."""
    ACTIVA, FINALIZADA, INTERRUMPIDA = "activa", "finalizada", "interrumpida"
    ESTADOS = [
        (ACTIVA, "Activa"),
        (FINALIZADA, "Finalizada"),
        (INTERRUMPIDA, "Interrumpida"),
    ]

    inicio = models.DateTimeField("inicio", default=timezone.now, db_index=True)
    fin = models.DateTimeField("fin", null=True, blank=True)
    estado = models.CharField("estado", max_length=15, choices=ESTADOS, default=ACTIVA)
    expresion_predominante = models.CharField(
        "expresión predominante", max_length=20, choices=OPCIONES_EXPRESION, blank=True)
    total_registros = models.PositiveIntegerField("registros", default=0)
    fotogramas_procesados = models.PositiveIntegerField("fotogramas procesados", default=0)
    fotogramas_con_rostro = models.PositiveIntegerField("fotogramas con rostro", default=0)

    class Meta:
        ordering = ["-inicio"]
        verbose_name = "sesión de análisis"
        verbose_name_plural = "sesiones de análisis"

    def __str__(self):
        return f"Sesión {self.pk} - {timezone.localtime(self.inicio):%d/%m/%Y %H:%M}"

    @property
    def duracion(self):
        """Duración de la sesión (hasta ahora si sigue activa)."""
        fin = self.fin or timezone.now()
        return fin - self.inicio

    @property
    def duracion_texto(self):
        """Duración legible, por ejemplo «2 min 05 s»."""
        segundos = int(self.duracion.total_seconds())
        minutos, segundos = divmod(segundos, 60)
        return f"{minutos} min {segundos:02d} s" if minutos else f"{segundos} s"

    @property
    def porcentaje_rostro(self):
        """Porcentaje de fotogramas en los que se detectó un rostro."""
        if not self.fotogramas_procesados:
            return 0
        return round(100 * self.fotogramas_con_rostro / self.fotogramas_procesados)

    @property
    def expresion(self):
        """
        Objeto del catálogo de la expresión predominante, ``catalogo.OTRA``
        si es una clave antigua (miedo, desprecio) o ``None`` si está vacía.
        """
        return catalogo.obtener_o_otra(self.expresion_predominante)


class RegistroExpresion(models.Model):
    """Una muestra por segundo con la expresión estimada y su confianza (%)."""
    sesion = models.ForeignKey(SesionAnalisis, on_delete=models.CASCADE,
                               related_name="registros", verbose_name="sesión")
    expresion = models.CharField("expresión estimada", max_length=20, choices=OPCIONES_EXPRESION)
    confianza = models.FloatField("confianza (%)")
    registrado_en = models.DateTimeField("registrado en", default=timezone.now)

    class Meta:
        ordering = ["registrado_en"]
        indexes = [models.Index(fields=["sesion", "registrado_en"], name="registro_sesion_fecha_idx")]
        verbose_name = "registro de expresión"
        verbose_name_plural = "registros de expresión"

    def __str__(self):
        return f"{self.get_expresion_display()} ({self.confianza:.0f}%)"
