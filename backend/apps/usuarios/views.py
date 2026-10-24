"""Pantallas de usuarios y consulta de roles (§9.2)."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from apps.core.exceptions import ErrorDeNegocio
from apps.core.permissions import permiso_requerido
from . import services
from .forms import CAMPOS_USUARIO, UsuarioCrearForm, UsuarioEditarForm
from .models import Permiso, Rol, Usuario


@permiso_requerido("gestionar_usuarios")
@require_GET
def lista(request):
    return render(request, "usuarios/usuario_lista.html", {
        "usuarios": Usuario.objects.select_related("rol").all(),
    })


@permiso_requerido("gestionar_usuarios")
@require_http_methods(["GET", "POST"])
def usuario_crear(request):
    form = UsuarioCrearForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            services.crear_usuario(request.user, **{c: form.cleaned_data[c] for c in CAMPOS_USUARIO},
                                   password=form.cleaned_data["password1"])
        except ErrorDeNegocio as error:
            form.add_error(error.campo, error.mensaje)
        else:
            messages.success(request, "Usuario creado correctamente.")
            return redirect("usuarios:lista")
    return render(request, "usuarios/usuario_form.html", {
        "form": form, "roles": Rol.objects.all(), "creando": True,
    })


@permiso_requerido("gestionar_usuarios")
@require_http_methods(["GET", "POST"])
def usuario_editar(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    services.comprobar_usuario_editable(request.user, usuario)
    form = UsuarioEditarForm(request.POST if request.method == "POST" else None, instance=usuario)
    if request.method == "POST" and form.is_valid():
        try:
            services.editar_usuario(request.user, pk, **{c: form.cleaned_data[c] for c in CAMPOS_USUARIO})
        except ErrorDeNegocio as error:
            form.add_error(error.campo, error.mensaje)
        else:
            messages.success(request, "Usuario actualizado correctamente.")
            return redirect("usuarios:lista")
    return render(request, "usuarios/usuario_form.html", {
        "form": form, "roles": Rol.objects.all(), "creando": False,
    })


@permiso_requerido("gestionar_usuarios")
@require_GET
def rol_lista(request):
    roles = list(Rol.objects.prefetch_related("permisos"))
    catalogo = list(Permiso.objects.all())
    asignados = {rol.pk: {p.codigo for p in rol.permisos.all()} for rol in roles}
    filas = [{"permiso": p, "asignaciones": [p.codigo in asignados[r.pk] for r in roles]}
             for p in catalogo]
    return render(request, "usuarios/rol_lista.html", {
        "roles": roles, "catalogo_permisos": catalogo, "filas": filas,
    })
