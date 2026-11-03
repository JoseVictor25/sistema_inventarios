"""Imagen bancaria local, sin rutas proporcionadas por el navegador."""
from io import BytesIO
import os
from pathlib import Path
import tempfile
import warnings
from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpResponse, Http404
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods, require_GET
from .permissions import permiso_requerido


def ruta_qr():
    raiz = Path(settings.DATA_DIR).absolute()
    destino = raiz / 'qr_bancario.png'
    for p in (destino, *destino.parents):
        if p.is_symlink() or p.is_junction():
            raise ValidationError('Ruta de QR insegura.')
    for base in [Path(settings.BASE_DIR).parent, *[Path(os.environ[v]) for v in
                 ('ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432') if os.environ.get(v)]]:
        if raiz.resolve().is_relative_to(base.resolve()):
            raise ValidationError('El QR requiere un directorio de datos separado del programa.')
    if destino.exists() and destino.stat().st_nlink > 1:
        raise ValidationError('Archivo de QR inseguro.')
    return destino


def normalizar(archivo):
    if Path(archivo.name).suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}:
        raise ValidationError('Utiliza PNG, JPG, JPEG o WEBP.')
    contenido = archivo.read(5 * 1024 * 1024 + 1)
    if len(contenido) > 5 * 1024 * 1024:
        raise ValidationError('La imagen no debe superar 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(contenido)) as img:
                if img.format not in {'PNG', 'JPEG', 'WEBP'} or getattr(img, 'is_animated', False):
                    raise ValidationError('Formato no permitido o imagen animada.')
                if not all(128 <= n <= 4096 for n in img.size) or img.width * img.height > 8_000_000:
                    raise ValidationError('Dimensiones: 128 a 4096 píxeles por lado, máximo 8 megapíxeles.')
                img.verify()
            with Image.open(BytesIO(contenido)) as img:
                salida = BytesIO()
                img.convert('RGB').save(salida, format='PNG')
                return salida.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError('El archivo no contiene una imagen válida.') from None


@permiso_requerido('gestionar_usuarios')
@require_http_methods(['GET', 'POST'])
def configurar(request):
    error = None
    try:
        ruta = ruta_qr()
        if request.method == 'POST':
            if request.POST.get('accion') == 'eliminar':
                ruta.unlink(missing_ok=True)
            elif request.POST.get('accion') == 'guardar' and 'imagen' in request.FILES:
                datos = normalizar(request.FILES['imagen'])
                nombre = None
                try:
                    with tempfile.NamedTemporaryFile(dir=ruta.parent, prefix='.qr_', delete=False) as f:
                        nombre = f.name
                        f.write(datos)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(nombre, ruta)
                finally:
                    if nombre:
                        Path(nombre).unlink(missing_ok=True)
            else:
                raise ValidationError('Selecciona una imagen y una operación válida.')
            return redirect('core:qr_configurar')
    except ValidationError as exc:
        error = '; '.join(exc.messages)
    except OSError:
        error = 'No se pudo actualizar el QR. Revisa los permisos del directorio de datos.'
    respuesta = render(request, 'core/qr.html', {'error': error}, status=422 if error else 200)
    respuesta['Cache-Control'] = 'no-store'
    return respuesta


@require_GET
def imagen(request):
    from .permissions import tiene_permiso
    from django.core.exceptions import PermissionDenied
    if not (tiene_permiso(request.user, 'vender') or tiene_permiso(request.user, 'gestionar_usuarios')):
        raise PermissionDenied
    try:
        datos = ruta_qr().read_bytes()
    except (FileNotFoundError, ValidationError):
        raise Http404('No hay QR configurado.')
    respuesta = HttpResponse(datos, content_type='image/png')
    respuesta['Cache-Control'] = 'private, no-store'
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta
