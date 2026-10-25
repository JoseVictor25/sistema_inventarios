"""Formularios explícitos de caja y validación administrativa heredada."""
from decimal import Decimal
from uuid import uuid4

from django import forms

from .models import Caja, MovimientoCaja
from apps.core.validators import validar_dinero


class OperacionCajaForm(forms.Form):
    """Clave persistente comprobada por el servicio dentro de su transacción SQL."""
    clave = forms.UUIDField(widget=forms.HiddenInput, initial=uuid4)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if not campo.widget.is_hidden:
                campo.widget.attrs["class"] = "form-select" if isinstance(campo.widget, forms.Select) else "form-control"

    def clean(self):
        datos = super().clean()
        # Ninguna fecha, propietario ni importe calculado procede del navegador.
        recibidos = set(self.data)
        permitidos = {self.add_prefix(c) for c in self.fields} | {"csrfmiddlewaretoken"}
        if recibidos - permitidos:
            raise forms.ValidationError("Se enviaron campos no permitidos para esta operación.")
        return datos


class AbrirCajaForm(OperacionCajaForm):
    monto_inicial = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"),
                                      validators=[validar_dinero], label="Monto inicial")
    turno = forms.CharField(max_length=30, required=False, strip=True, label="Turno (opcional)")


class MovimientoCajaForm(OperacionCajaForm):
    caja_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    tipo = forms.ChoiceField(choices=MovimientoCaja.TipoMovimientoCaja.choices)
    monto = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
                              validators=[validar_dinero])
    concepto = forms.CharField(max_length=120, strip=True)


class CerrarCajaForm(OperacionCajaForm):
    caja_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    monto_contado = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"),
                                      validators=[validar_dinero], label="Efectivo contado")


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
