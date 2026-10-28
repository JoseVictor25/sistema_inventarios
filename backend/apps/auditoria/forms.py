"""Filtros de consulta de bitácora, sin operaciones de escritura."""
from datetime import date
from django import forms
from apps.usuarios.models import Usuario


class FiltrosAuditoriaForm(forms.Form):
    usuario = forms.ModelChoiceField(Usuario.objects.all(), required=False)
    entidad = forms.CharField(max_length=60, required=False)
    desde = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    hasta = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    page = forms.IntegerField(min_value=1, required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs['class'] = 'form-control'

    def clean(self):
        datos = super().clean()
        if set(self.data) - set(self.fields):
            raise forms.ValidationError('Se enviaron filtros no permitidos.')
        if hasattr(self.data, 'getlist') and any(len(self.data.getlist(k)) != 1 for k in self.data):
            raise forms.ValidationError('No repitas un mismo filtro.')
        if datos.get('desde') and datos.get('hasta') and datos['desde'] > datos['hasta']:
            raise forms.ValidationError('Desde no puede ser posterior a Hasta.')
        if datos.get('hasta') == date.max:
            raise forms.ValidationError('La fecha final está fuera del rango admitido.')
        return datos
