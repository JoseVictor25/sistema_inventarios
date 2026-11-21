from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('inventario', '0003_operacion_ajuste_inventario')]
    operations = [migrations.AddIndex(
        model_name='lote', index=models.Index(fields=['fecha_vencimiento'], name='lote_vencimiento_idx'))]
