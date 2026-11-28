from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('catalogo', '0002_integridad_fase1')]
    operations = [migrations.AddIndex(
        model_name='producto', index=models.Index(fields=['nombre'], name='producto_nombre_idx'))]
