"""Formularios ordinarios con campos explícitos, sin privilegios técnicos."""
from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Usuario


CAMPOS_USUARIO = ("username", "first_name", "last_name", "rol", "is_active")
CAMPOS_PROHIBIDOS = {
    "is_staff", "is_superuser", "groups", "user_permissions", "password",
    "last_login", "date_joined", "id", "pk",
}


class FormularioOrdinarioMixin:
    """Rechaza intentos explícitos de escribir campos protegidos."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-control"
            if isinstance(field.widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(field.widget, forms.Select):
                css = "form-select"
            field.widget.attrs["class"] = css

    def clean(self):
        datos = super().clean()
        prohibidos = CAMPOS_PROHIBIDOS | ({"password1", "password2"} - set(self.fields))
        if prohibidos.intersection(self.data):
            raise forms.ValidationError("No se permite modificar privilegios técnicos ni contraseñas desde este formulario.")
        return datos


class UsuarioCrearForm(FormularioOrdinarioMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = CAMPOS_USUARIO


class UsuarioEditarForm(FormularioOrdinarioMixin, forms.ModelForm):
    class Meta:
        model = Usuario
        fields = CAMPOS_USUARIO
