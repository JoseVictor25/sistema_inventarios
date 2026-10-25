"""Formularios de compras y proveedores — Fase 4."""
import datetime

from django import forms
from django.core.exceptions import ValidationError

from apps.catalogo.forms import FormularioCatalogoMixin
from .models import Proveedor
from .services import CAMPOS_PROVEEDOR


class ProveedorForm(FormularioCatalogoMixin, forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = CAMPOS_PROVEEDOR


class FiltroComprasForm(forms.Form):
    """Filtro de compras por rango de fechas."""

    desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm", "id": "filtro-desde"}),
    )
    hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm", "id": "filtro-hasta"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        desde = cleaned_data.get("desde")
        hasta = cleaned_data.get("hasta")
        if desde and hasta and desde > hasta:
            raise ValidationError("La fecha 'Desde' no puede ser posterior a 'Hasta'.")
        return cleaned_data


class CompraCabeceraForm(forms.Form):
    """Formulario para la cabecera de registro de compra."""

    proveedor = forms.ModelChoiceField(
        queryset=Proveedor.objects.filter(activo=True).order_by("nombre"),
        empty_label="-- Seleccionar proveedor --",
        widget=forms.Select(attrs={"class": "form-select", "id": "id_proveedor", "required": "required"}),
    )
    fecha = forms.DateField(
        initial=datetime.date.today,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control", "id": "id_fecha", "required": "required"}),
    )
    observacion = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "id": "id_observacion",
            "placeholder": "Observación o nota adicional (opcional)",
        }),
    )


def extraer_lineas_post(post_data):
    """Extrae y estructura la lista de líneas enviadas en la petición POST."""
    productos = (
        post_data.getlist("linea_producto")
        or post_data.getlist("linea_producto[]")
        or post_data.getlist("producto_id")
    )
    cantidades = (
        post_data.getlist("linea_cantidad")
        or post_data.getlist("linea_cantidad[]")
        or post_data.getlist("cantidad")
    )
    costos = (
        post_data.getlist("linea_costo")
        or post_data.getlist("linea_costo[]")
        or post_data.getlist("costo_unitario")
    )
    vencimientos = (
        post_data.getlist("linea_vencimiento")
        or post_data.getlist("linea_vencimiento[]")
        or post_data.getlist("fecha_vencimiento")
    )

    lineas = []
    total_filas = max(len(productos), len(cantidades), len(costos))
    for i in range(total_filas):
        prod_val = productos[i].strip() if i < len(productos) else ""
        if not prod_val:
            continue
        cant_val = cantidades[i].strip() if i < len(cantidades) else "1"
        costo_val = costos[i].strip() if i < len(costos) else "0"
        venc_val = vencimientos[i].strip() if i < len(vencimientos) else ""
        lineas.append({
            "producto_id": prod_val,
            "cantidad": cant_val,
            "costo_unitario": costo_val,
            "fecha_vencimiento": venc_val or None,
        })
    return lineas
