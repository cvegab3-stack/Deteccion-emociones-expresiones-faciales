"""Registro de los modelos en el administrador de Django (solo lectura de registros)."""

from django.contrib import admin

from .models import RegistroExpresion, SesionAnalisis


class RegistroEnLinea(admin.TabularInline):
    """Registros de expresión de una sesión, en solo lectura."""
    model = RegistroExpresion
    extra = 0
    readonly_fields = ("expresion", "confianza", "registrado_en")
    can_delete = False
    max_num = 0


@admin.register(SesionAnalisis)
class SesionAnalisisAdmin(admin.ModelAdmin):
    """Listado y filtros de las sesiones de análisis."""
    list_display = ("id", "inicio", "estado", "expresion_predominante", "total_registros")
    list_filter = ("estado", "expresion_predominante")
    inlines = [RegistroEnLinea]


@admin.register(RegistroExpresion)
class RegistroExpresionAdmin(admin.ModelAdmin):
    """Listado y filtros de los registros por segundo."""
    list_display = ("sesion", "expresion", "confianza", "registrado_en")
    list_filter = ("expresion",)
