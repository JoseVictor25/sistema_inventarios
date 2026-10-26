"""Filtros estrictos compartidos por pantalla, servicios y descargas."""
from datetime import date
from zoneinfo import ZoneInfo
from django import forms
from django.conf import settings
from django.utils import timezone
from apps.catalogo.models import Categoria
from apps.compras.models import Proveedor
from apps.usuarios.models import Usuario


class FiltrosReporteForm(forms.Form):
    """Valida solo los campos del reporte seleccionado, incluidos inactivos."""

    def __init__(self, nombre, data=None, **kwargs):
        super().__init__(data, **kwargs)
        if nombre not in ('inventario_valorizado', 'vencimientos'):
            for campo, etiqueta in [('desde', 'Desde'), ('hasta', 'Hasta')]:
                self.fields[campo] = forms.DateField(label=etiqueta, widget=forms.DateInput(attrs={'type': 'date'}))
        if nombre == 'ventas':
            self.fields['agrupar'] = forms.ChoiceField(choices=[('dia', 'Día'), ('semana', 'Semana (lunes)'), ('mes', 'Mes')])
        if nombre in ('productos_mas_vendidos', 'inventario_valorizado', 'ganancias'):
            self.fields['categoria'] = forms.ModelChoiceField(Categoria.objects.all(), required=False, label='Categoría exacta')
        if nombre == 'compras':
            self.fields['proveedor'] = forms.ModelChoiceField(Proveedor.objects.all(), required=False)
        if nombre == 'cierres_caja':
            self.fields['usuario'] = forms.ModelChoiceField(Usuario.objects.all(), required=False, label='Responsable del turno')
        if nombre == 'vencimientos':
            self.fields['dias'] = forms.IntegerField(min_value=0, initial=settings.DIAS_ALERTA_VENCIMIENTO, label='Días de anticipación')
        for campo in self.fields.values():
            campo.widget.attrs['class'] = 'form-select' if isinstance(campo.widget, forms.Select) else 'form-control'

    def clean(self):
        datos = super().clean()
        if set(self.data) - set(self.fields):
            raise forms.ValidationError('Se enviaron filtros no permitidos.')
        if hasattr(self.data, 'getlist') and any(len(self.data.getlist(k)) != 1 for k in self.data):
            raise forms.ValidationError('No repitas un mismo filtro.')
        desde, hasta = datos.get('desde'), datos.get('hasta')
        if desde and hasta:
            if desde > hasta:
                raise forms.ValidationError('Desde no puede ser posterior a Hasta.')
            if (hasta - desde).days + 1 > 366:
                raise forms.ValidationError('El intervalo admite como máximo 366 fechas calendario incluidas.')
            if hasta == date.max:
                raise forms.ValidationError('La fecha final está fuera del rango admitido.')
        if 'dias' in datos and datos['dias'] > (date.max - timezone.localdate(timezone=ZoneInfo('America/La_Paz'))).days:
            raise forms.ValidationError('La cantidad de días excede el calendario admitido.')
        return datos
