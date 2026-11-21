from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('compras', '0002_integridad_fase1')]
    operations = [migrations.AddIndex(
        model_name='compra', index=models.Index(fields=['fecha'], name='compra_fecha_idx'))]
