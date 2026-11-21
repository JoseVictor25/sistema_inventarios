from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ventas', '0003_operacion_venta')]
    operations = [migrations.AddIndex(
        model_name='venta', index=models.Index(fields=['fecha'], name='venta_fecha_idx'))]
