"""Entrada del catálogo con campos explícitos y formsets sin borrado."""
from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import AtributoProducto, Categoria, Presentacion, Producto
from .services import CAMPOS_ATRIBUTO, CAMPOS_CATEGORIA, CAMPOS_PRESENTACION, CAMPOS_PRODUCTO


class FormularioCatalogoMixin:
    """Estilo local y rechazo explícito de campos protegidos."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs["class"] = (
                "form-check-input" if isinstance(campo.widget, forms.CheckboxInput)
                else "form-select" if isinstance(campo.widget, forms.Select) else "form-control")

    def clean(self):
        datos = super().clean()
        protegidos = {"creado_por", "modificado_por", "creado_en", "modificado_en",
                      "stock_actual", "producto", "producto_id", "is_superuser", "is_staff", "DELETE"}
        # El FK oculto del inline solo se acepta si coincide con la cabecera.
        if "producto" in self.fields:
            protegidos.discard("producto")
        if any(self.add_prefix(c) in self.data for c in protegidos):
            raise forms.ValidationError("Se enviaron campos protegidos o una eliminación no permitida.")
        return datos


class CategoriaForm(FormularioCatalogoMixin, forms.ModelForm):
    class Meta:
        model = Categoria
        fields = CAMPOS_CATEGORIA


class ProductoForm(FormularioCatalogoMixin, forms.ModelForm):
    class Meta:
        model = Producto
        fields = CAMPOS_PRODUCTO


class PresentacionForm(FormularioCatalogoMixin, forms.ModelForm):
    unidades_equivalentes = forms.IntegerField(min_value=1, label="Unidades equivalentes")

    class Meta:
        model = Presentacion
        fields = CAMPOS_PRESENTACION


class PresentacionesBaseFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        entradas = [f.cleaned_data for f in self.forms if f.cleaned_data]
        if not entradas:
            raise forms.ValidationError("Agrega al menos una presentación.")
        existentes = set(self.get_queryset().values_list("pk", flat=True))
        enviados = [d["id"].pk for d in entradas if d.get("id")]
        if set(enviados) != existentes or len(enviados) != len(set(enviados)):
            raise forms.ValidationError("Presentaciones omitidas, repetidas o ajenas. Recarga la página.")
        if self.initial_form_count() != len(existentes):
            raise forms.ValidationError("La cantidad de presentaciones existentes cambió. Recarga la página.")


PresentacionFormSet = inlineformset_factory(
    Producto, Presentacion, form=PresentacionForm, formset=PresentacionesBaseFormSet,
    extra=1, can_delete=False, min_num=1, validate_min=True,
)


class PrecioForm(FormularioCatalogoMixin, forms.Form):
    precio_venta = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0, label="Nuevo precio (Bs)")


class AtributoForm(FormularioCatalogoMixin, forms.ModelForm):
    class Meta:
        model = AtributoProducto
        fields = CAMPOS_ATRIBUTO


class FiltroProductoForm(FormularioCatalogoMixin, forms.Form):
    q = forms.CharField(required=False, max_length=120, label="Código o nombre")
    categoria = forms.ModelChoiceField(queryset=Categoria.objects.all(), required=False)
    atributo = forms.CharField(required=False, max_length=60)
    valor = forms.CharField(required=False, max_length=120)

    def clean(self):
        datos = super().clean()
        if bool(datos.get("atributo")) != bool(datos.get("valor")):
            raise forms.ValidationError("Para filtrar por atributo completa nombre y valor.")
        return datos
