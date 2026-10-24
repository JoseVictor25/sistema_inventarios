"""Validación de entradas administrativas sobre turnos abiertos (RN-13)."""
from django import forms

from .models import Caja, MovimientoCaja


class MovimientoCajaAdminForm(forms.ModelForm):
    """No permite agregar ni trasladar movimientos a un turno cerrado."""

    class Meta:
        model = MovimientoCaja
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "caja" in self.fields:
            self.fields["caja"].queryset = Caja.objects.filter(
                estado=Caja.EstadoCaja.ABIERTA
            )

    def clean(self):
        """Comprueba el turno original y el destino, también en los inlines."""
        datos = super().clean()
        caja = datos.get("caja") or getattr(self.instance, "caja", None)
        ids = [caja.pk] if caja else []
        if self.instance.pk:
            ids.extend(MovimientoCaja.objects.filter(pk=self.instance.pk)
                       .values_list("caja_id", flat=True))
        if Caja.objects.filter(pk__in=ids, estado=Caja.EstadoCaja.CERRADA).exists():
            raise forms.ValidationError("No se pueden modificar movimientos de un turno cerrado.")
        return datos
