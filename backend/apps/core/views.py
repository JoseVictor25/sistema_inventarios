from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.shortcuts import redirect
from django.contrib import messages
from django.views.decorators.http import require_GET, require_POST
from .permissions import permiso_requerido
from . import services
from .respaldos import ErrorRespaldo


@login_required
@require_GET
def inicio(request):
    respuesta = render(request, 'inicio.html', services.datos_inicio(request.user))
    respuesta['Cache-Control'] = 'private, no-store'
    return respuesta


@permiso_requerido('respaldar')
@require_GET
def respaldos(request):
    try:
        filas = services.consultar_respaldos(request.user)
    except ErrorRespaldo as error:
        messages.error(request, str(error))
        filas = []
    respuesta = render(request, 'core/respaldos.html', {'respaldos': filas})
    respuesta['Cache-Control'] = 'private, no-store'
    return respuesta


@permiso_requerido('respaldar')
@require_POST
def respaldo_crear(request):
    if set(request.POST) - {'csrfmiddlewaretoken'} or request.GET:
        from django.http import HttpResponse
        return HttpResponse('No se aceptan rutas ni parámetros para crear el respaldo.', status=422)
    try:
        resultado = services.crear_respaldo(request.user)
    except ErrorRespaldo as error:
        messages.error(request, str(error))
    else:
        messages.success(request, 'Respaldo creado y verificado: ' + resultado['archivo'])
        if resultado['advertencia']:
            messages.warning(request, resultado['advertencia'])
    return redirect('core:respaldos')
