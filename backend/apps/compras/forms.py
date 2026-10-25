"""Formularios ordinarios de proveedores de fase 3."""
from apps.catalogo.forms import FormularioCatalogoMixin
from django import forms

from .models import Proveedor
from .services import CAMPOS_PROVEEDOR


class ProveedorForm(FormularioCatalogoMixin, forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = CAMPOS_PROVEEDOR
