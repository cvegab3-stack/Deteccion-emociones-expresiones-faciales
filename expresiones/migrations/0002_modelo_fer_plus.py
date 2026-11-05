"""
Cambio al modelo ya entrenado FER+:

* se elimina el entrenamiento LBPH (tabla CapturaEntrenamiento);
* se elimina el "Reto de expresiones" (campo retos_superados);
* 'coincidencia' pasa a llamarse 'confianza' (probabilidad del modelo, %);
* las expresiones pasan de 5 a las 8 clases de FER+.
"""

from django.db import migrations, models

OPCIONES = [
    ("neutral", "Neutral"), ("felicidad", "Felicidad"), ("sorpresa", "Sorpresa"),
    ("tristeza", "Tristeza"), ("enojo", "Enojo"), ("asco", "Asco"), ("miedo", "Miedo"),
    ("desprecio", "Desprecio"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("expresiones", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(name="CapturaEntrenamiento"),
        migrations.RemoveField(model_name="sesionanalisis", name="retos_superados"),
        migrations.RenameField(model_name="registroexpresion", old_name="coincidencia", new_name="confianza"),
        migrations.AlterField(
            model_name="registroexpresion",
            name="confianza",
            field=models.FloatField(verbose_name="confianza (%)"),
        ),
        migrations.AlterField(
            model_name="registroexpresion",
            name="expresion",
            field=models.CharField(choices=OPCIONES, max_length=20, verbose_name="expresión estimada"),
        ),
        migrations.AlterField(
            model_name="sesionanalisis",
            name="expresion_predominante",
            field=models.CharField(blank=True, choices=OPCIONES, max_length=20,
                                   verbose_name="expresión predominante"),
        ),
    ]
