from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('inventario', '0004_lote_vencimiento_index')]
    operations = [migrations.AddIndex(
        model_name='movimientoinventario', index=models.Index(fields=['fecha'], name='movimiento_fecha_idx'))]
