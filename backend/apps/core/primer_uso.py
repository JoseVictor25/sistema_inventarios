"""Alta local de un solo Dueño, sin privilegios técnicos."""
import secrets
import threading
from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from apps.usuarios.models import Usuario, Rol

_token = None
_cerrojo = threading.Lock()


def habilitar():
    global _token
    _token = secrets.token_urlsafe(32) if not Usuario.objects.exists() else None
    return _token


class PrimerDuenoForm(forms.Form):
    autorizacion = forms.CharField(widget=forms.PasswordInput)
    username = forms.CharField(max_length=150)
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        datos = super().clean()
        if datos.get('password1') != datos.get('password2'):
            raise forms.ValidationError('Las contraseñas no coinciden.')
        if datos.get('password1'):
            validate_password(datos['password1'], Usuario(username=datos.get('username', '')))
        return datos


def crear_dueno(datos):
    global _token
    form = PrimerDuenoForm(datos)
    if not form.is_valid():
        from django.core.exceptions import ValidationError
        raise ValidationError('Datos de configuración inicial inválidos.')
    datos = form.cleaned_data
    # El launcher mantiene exclusión entre procesos; este cerrojo serializa
    # peticiones del único servidor autorizado, incluida la invalidación.
    with _cerrojo:
        if not _token or not secrets.compare_digest(datos['autorizacion'], _token):
            raise PermissionDenied('Autorización local inválida.')
        with transaction.atomic():
            if Usuario.objects.exists():
                raise PermissionDenied('El primer usuario ya fue registrado.')
            usuario = Usuario(username=datos['username'], rol=Rol.objects.get(nombre='Dueño'))
            usuario.set_password(datos['password1'])
            usuario.full_clean()
            usuario.save()
        _token = None
        return usuario


@require_http_methods(['GET', 'POST'])
def primer_uso(request):
    if not _token or Usuario.objects.exists():
        raise PermissionDenied('La configuración inicial no está disponible.')
    form = PrimerDuenoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        from django.core.exceptions import ValidationError
        try:
            crear_dueno(form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return redirect('usuarios:login')
    respuesta = render(request, 'core/primer_uso.html', {'form': form}, status=422 if request.method == 'POST' else 200)
    respuesta['Cache-Control'] = 'no-store'
    return respuesta
