from django.conf import settings
from django.db import models


class EntidadAuditable(models.Model):
    """Clase base abstracta: quién y cuándo creó/modificó cada registro."""

    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_en = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+", editable=False,
    )
    modificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+", editable=False,
    )

    class Meta:
        abstract = True
