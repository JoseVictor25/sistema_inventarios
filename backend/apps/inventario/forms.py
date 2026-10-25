from uuid import uuid4

from django import forms



class FormularioInventario(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs['class'] = 'form-select' if isinstance(campo.widget, forms.Select) else 'form-control'

    def clean(self):
        datos = super().clean()
        permitidos = set(self.fields) | {'csrfmiddlewaretoken'}
        if set(self.data) - permitidos:
            raise forms.ValidationError('Se enviaron campos no permitidos.')
        return datos


class FiltroStockForm(FormularioInventario):
    q = forms.CharField(max_length=120, required=False, label='Código o nombre')
    solo_bajo = forms.ChoiceField(choices=[('', 'Todos'), ('1', 'Stock bajo (incluye cero)')], required=False, label='Existencias')
    page = forms.IntegerField(min_value=1, required=False, widget=forms.HiddenInput)


class FiltroLoteForm(FormularioInventario):
    q = forms.CharField(max_length=120, required=False, label='Producto o código de lote')
    producto = forms.IntegerField(min_value=1, required=False, widget=forms.HiddenInput)
    estado = forms.ChoiceField(required=False, label='Estado del lote', choices=[
        ('', 'Todos'), ('vigente', 'Vigentes con stock'), ('por_vencer', 'Por vencer'),
        ('vencido', 'Vencidos con stock'), ('sin_fecha', 'Sin vencimiento'), ('agotado', 'Agotados')])
    page = forms.IntegerField(min_value=1, required=False, widget=forms.HiddenInput)


class FiltroMovimientoForm(FormularioInventario):
    q = forms.CharField(max_length=120, required=False, label='Producto o código de lote')
    producto = forms.IntegerField(min_value=1, required=False, widget=forms.HiddenInput)
    lote = forms.IntegerField(min_value=1, required=False, label='Identificador de lote')
    tipo = forms.ChoiceField(required=False, choices=[('', 'Todos'), ('ENTRADA', 'Entrada'),
        ('SALIDA', 'Salida'), ('AJUSTE', 'Ajuste'), ('MERMA', 'Merma')])
    desde = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    hasta = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    page = forms.IntegerField(min_value=1, required=False, widget=forms.HiddenInput)

    def clean(self):
        datos = super().clean()
        if datos.get('desde') and datos.get('hasta') and datos['desde'] > datos['hasta']:
            raise forms.ValidationError('La fecha inicial no puede ser posterior a la final.')
        return datos


class FiltroAlertasForm(FormularioInventario):
    page_bajo = forms.IntegerField(min_value=1, required=False)
    page_por_vencer = forms.IntegerField(min_value=1, required=False)
    page_vencidos = forms.IntegerField(min_value=1, required=False)


class AjusteInventarioForm(FormularioInventario):
    clave = forms.UUIDField(widget=forms.HiddenInput, required=False, initial=uuid4)
    lote = forms.IntegerField(min_value=1, label='Lote a modificar')
    tipo = forms.ChoiceField(
        choices=[
            ('AJUSTE', 'Ajuste de inventario (corrección +/-)'),
            ('MERMA', 'Merma de producto (retiro por daño/pérdida -)'),
        ],
        label='Tipo de operación',
    )
    cantidad = forms.IntegerField(
        min_value=-2147483647,
        max_value=2147483647,
        label='Cantidad de unidades (con signo +/-)',
        help_text='Ingresa el número de unidades a modificar. Ejemplos: +2 suma dos unidades; -3 retira tres unidades. Para merma, ingresa siempre un valor negativo.',
    )
    motivo = forms.CharField(
        min_length=5,
        max_length=200,
        strip=True,
        label='Motivo o justificación',
        help_text='Describe detalladamente la razón de la modificación (entre 5 y 200 caracteres).',
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Ejemplo: Ajuste por conteo físico mensual / Merma por rotura de frasco durante manipulación...'}),
    )

    def clean(self):
        datos = super().clean()
        cantidad = datos.get('cantidad')
        if cantidad == 0:
            self.add_error('cantidad', 'La cantidad debe ser distinta de cero. Usa valores positivos (+) para sumar o negativos (-) para restar.')
        if datos.get('tipo') == 'MERMA' and cantidad is not None and cantidad >= 0:
            self.add_error('cantidad', 'Una merma debe retirar unidades: usa una cantidad negativa (ejemplo: -3).')
        return datos
