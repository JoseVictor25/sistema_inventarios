"""Inventario con SQLite temporal: --pruebas, --http, --abrir (revisión manual)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from verificar_catalogo_fase3 import preparar_entorno

RAIZ = Path(__file__).resolve().parent.parent


def recorrido_http(temporal, abrir):
    import threading
    from datetime import timedelta
    from decimal import Decimal
    from html.parser import HTMLParser
    from http.cookiejar import CookieJar
    from urllib.error import HTTPError
    from urllib.parse import urlencode
    from urllib.request import HTTPCookieProcessor, Request, build_opener
    from wsgiref.simple_server import make_server, WSGIRequestHandler
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.core.wsgi import get_wsgi_application
    from django.db import connections
    from django.utils import timezone
    import uuid
    from apps.catalogo.models import Producto, Categoria
    from apps.inventario.models import Lote, MovimientoInventario, OperacionAjusteInventario
    from apps.auditoria.models import LogAuditoria
    from apps.usuarios.models import Usuario, Rol
    from apps.core.frontend import RECURSOS_FRONTEND
    from verificar_interfaz_fase0 import TokenCSRF

    if Path(settings.DATABASES['default']['NAME']).resolve() != (temporal / 'aislada.sqlite3').resolve():
        raise RuntimeError('Se rechazó una base distinta de la temporal.')
    call_command('migrate', verbosity=0, interactive=False)
    call_command('cargar_datos_iniciales', verbosity=0)
    clave = secrets.token_urlsafe(24)
    dueno = Usuario.objects.create_user('dueno_fase7', password=clave, rol=Rol.objects.get(nombre='Dueño'))
    Usuario.objects.create_user('vendedor_fase7', password=clave, rol=Rol.objects.get(nombre='Vendedor'))
    categoria = Categoria.objects.create(nombre='Productos de demostración')
    objetivo = None
    for numero, (nombre, cantidad, dias, activo) in enumerate([
            ('Sin lotes', None, None, True), ('Stock cero', 0, 0, True),
            ('Stock bajo', 3, 10, True), ('Vence hoy', 10, 0, True),
            ('Solo vencidos', 10, -1, True), ('Sin vencimiento', 12, None, True),
            ('Inactivo con existencias', 4, 5, False), ('Límite de alerta', 8, settings.DIAS_ALERTA_VENCIMIENTO, True)]):
        producto = Producto.objects.create(codigo=f'F7-{numero}', nombre=nombre, categoria=categoria, activo=activo)
        if cantidad is not None:
            registro = Lote.objects.create(producto=producto, codigo_lote=f'L-F7-{numero}',
                cantidad_inicial=max(cantidad, 1), cantidad_actual=cantidad,
                fecha_vencimiento=timezone.localdate() + timedelta(days=dias) if dias is not None else None,
                costo_unitario=Decimal('9876.54'))
            if cantidad:
                MovimientoInventario.objects.create(lote=registro, usuario=dueno, tipo='ENTRADA', cantidad=cantidad, motivo='Existencias de demostración temporal')
            if nombre == 'Sin vencimiento':
                objetivo = registro
    # Más de 20 registros para verificar paginación real.
    for numero in range(23):
        Producto.objects.create(codigo=f'PAG-{numero}', nombre=f'Producto de paginación {numero:02}', categoria=categoria)

    app = get_wsgi_application()
    peticiones = []
    def sitio(environ, start_response):
        def responder(status, headers, exc_info=None):
            peticiones.append({'ruta': environ['PATH_INFO'], 'metodo': environ['REQUEST_METHOD'], 'estado': int(status[:3])})
            return start_response(status, headers, exc_info)
        return app(environ, responder)
    class Silencioso(WSGIRequestHandler):
        def log_message(self, *args):
            pass
    servidor = make_server('127.0.0.1', 0, sitio, handler_class=Silencioso)
    def atender():
        try:
            servidor.serve_forever()
        finally:
            connections.close_all()
    hilo = threading.Thread(target=atender, daemon=True)
    hilo.start()
    origen = f'http://127.0.0.1:{servidor.server_port}'
    informe = {'aprobado': False, 'visual': 'pendiente de inspección manual', 'peticiones': peticiones}

    def pedir(cliente, ruta, datos=None, headers=None):
        solicitud = Request(origen + ruta, data=urlencode(datos).encode() if datos is not None else None, headers=headers or {})
        try:
            respuesta = cliente.open(solicitud, timeout=20)
        except HTTPError as error:
            respuesta = error
        with respuesta:
            return respuesta.status, respuesta.read()

    def sesion(nombre):
        cliente = build_opener(HTTPCookieProcessor(CookieJar()))
        token = TokenCSRF(pedir(cliente, '/login/')[1].decode()).token
        assert pedir(cliente, '/login/', {'username': nombre, 'password': clave, 'csrfmiddlewaretoken': token})[0] == 200
        return cliente

    class Referencias(HTMLParser):
        def __init__(self, html):
            super().__init__()
            self.externas = []
            self.recursos = set()
            self.feed(html)
        def handle_starttag(self, tag, attrs):
            for atributo, url in attrs:
                if atributo not in ('src', 'href', 'action', 'hx-get', 'hx-post') or not url:
                    continue
                if url.startswith(('http://', 'https://', '//')):
                    self.externas.append(url)
                if url.startswith('/static/'):
                    self.recursos.add(url)

    try:
        dueno_http, vendedor_http = sesion('dueno_fase7'), sesion('vendedor_fase7')
        rutas = ['', 'lotes/', 'alertas/', 'movimientos/', f'ajuste/?lote={objetivo.pk}']
        token = None
        for numero, ruta in enumerate(rutas):
            estado, cuerpo = pedir(dueno_http, '/inventario/' + ruta)
            assert estado == 200, (ruta, estado)
            html = cuerpo.decode()
            referencias = Referencias(html)
            assert not referencias.externas
            for recurso in referencias.recursos:
                assert pedir(dueno_http, recurso)[0] == 200
            (temporal / f'pantalla_{numero}.html').write_text(html, encoding='utf-8')
            token = TokenCSRF(html).token
        for ruta in rutas[:4]:
            for headers in ({}, {'HX-Request': 'true'}, {'Accept': 'application/json'}):
                estado, cuerpo = pedir(vendedor_http, '/inventario/' + ruta, headers=headers)
                assert estado == 200 and b'9876' not in cuerpo and b'costo_unitario' not in cuerpo
        token_vendedor = TokenCSRF(pedir(vendedor_http, '/inventario/')[1].decode()).token
        assert pedir(vendedor_http, '/inventario/ajuste/')[0] == 403
        assert pedir(vendedor_http, '/inventario/ajuste/', {'csrfmiddlewaretoken': token_vendedor})[0] == 403
        assert pedir(dueno_http, '/inventario/ajuste/', {})[0] == 403
        datos = {'lote': objetivo.pk, 'tipo': 'MERMA', 'cantidad': '-2', 'motivo': 'Rotura de prueba', 'csrfmiddlewaretoken': token}
        assert pedir(dueno_http, '/inventario/ajuste/', datos)[0] == 200
        objetivo.refresh_from_db()
        assert objetivo.cantidad_actual == 10
        assert LogAuditoria.objects.filter(accion='AJUSTE_INVENTARIO').count() == 1
        assert pedir(dueno_http, '/inventario/ajuste/', {**datos, 'cantidad': '-999'})[0] == 422

        # Idempotencia persistente en HTTP: misma clave recupera resultado y deduplica
        clave_idemp = str(uuid.uuid4())
        datos_idemp = {'lote': objetivo.pk, 'tipo': 'MERMA', 'cantidad': '-1', 'motivo': 'Merma con clave idempotente', 'csrfmiddlewaretoken': token, 'clave': clave_idemp}
        assert pedir(dueno_http, '/inventario/ajuste/', datos_idemp)[0] == 200
        objetivo.refresh_from_db()
        assert objetivo.cantidad_actual == 9
        assert OperacionAjusteInventario.objects.filter(clave=clave_idemp).count() == 1

        # Reenvío idéntico con la misma clave: stock no se reduce nuevamente
        assert pedir(dueno_http, '/inventario/ajuste/', datos_idemp)[0] == 200
        objetivo.refresh_from_db()
        assert objetivo.cantidad_actual == 9
        assert OperacionAjusteInventario.objects.filter(clave=clave_idemp).count() == 1

        # Reenvío con misma clave pero datos alterados -> 422
        assert pedir(dueno_http, '/inventario/ajuste/', {**datos_idemp, 'cantidad': '-2'})[0] == 422
        objetivo.refresh_from_db()
        assert objetivo.cantidad_actual == 9
        assert pedir(dueno_http, '/inventario/?page=2')[0] == 200
        assert pedir(dueno_http, '/inventario/alertas/?page_bajo=2')[0] == 200
        assert pedir(dueno_http, '/inventario/lotes/?estado=vencido')[0] == 200
        assert pedir(dueno_http, '/inventario/?page=no')[0] == 422
        for recurso in RECURSOS_FRONTEND:
            assert pedir(dueno_http, '/static/' + recurso)[0] == 200
        assert not any(p['estado'] >= 500 or p['estado'] == 404 for p in peticiones)
        informe['aprobado'] = True
        print('HTTP aprobado: cinco pantallas, permisos, costos, ajuste, auditoría, filtros, CSRF y recursos locales.', flush=True)
        if abrir:
            import webbrowser
            print(f'Revisión visual: {origen}/login/', flush=True)
            print(f'Usuarios TEMPORALES: dueno_fase7 / vendedor_fase7. Contraseña temporal: {clave}', flush=True)
            print('Revisar a 1280x800 y 390x844; Ctrl+C finaliza. No acredita inspección visual automática.', flush=True)
            webbrowser.open(origen + '/login/')
            try:
                threading.Event().wait()
            except KeyboardInterrupt:
                pass
    finally:
        servidor.shutdown()
        servidor.server_close()
        hilo.join(timeout=5)
        connections.close_all()
        (temporal / 'http.json').write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for opcion in ('pruebas', 'http', 'abrir'):
        parser.add_argument('--' + opcion, action='store_true')
    args = parser.parse_args()
    if not any(vars(args).values()):
        parser.error('Elige --pruebas, --http o --abrir.')
    if Path(sys.executable).resolve() != (RAIZ / 'venv/Scripts/python.exe').resolve():
        parser.error('Utiliza exclusivamente venv/Scripts/python.exe.')
    temporal = Path(tempfile.mkdtemp(prefix='Inventarios_verificacion_fase7_'))
    env = preparar_entorno(temporal)
    env['NOMBRE_NEGOCIO'] = 'Inventario de prueba temporal'
    protegidos = [RAIZ / p for p in ('backend/.env', 'backend/datos/db.sqlite3',
                  'backend/REPORTE_MIGRACIONES_FASE1.md', 'backend/SOLUCION_ERROR_TERMINAL.md')]
    antes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protegidos if p.exists()}
    print(f'Evidencia y SQLite aisladas: {temporal}', flush=True)
    resultados = {}
    try:
        if args.pruebas:
            comandos = {
                'check': ['manage.py', 'check'],
                'makemigrations': ['manage.py', 'makemigrations', '--check', '--dry-run'],
                'test': ['manage.py', 'test', '--noinput'],
                'frontend': [str(RAIZ / 'scripts/preparar_frontend.py'), '--verificar'],
            }
            for nombre, comando in comandos.items():
                with (temporal / f'{nombre}.txt').open('w', encoding='utf-8') as salida:
                    resultado = subprocess.run([sys.executable, *comando], cwd=RAIZ / 'backend', env=env, stdout=salida, stderr=subprocess.STDOUT)
                resultados[nombre] = resultado.returncode
                if nombre == 'test' and 'Ran 0 tests' in (temporal / 'test.txt').read_text(encoding='utf-8'):
                    resultados[nombre] = 1
                print(f'{nombre}: código {resultados[nombre]}', flush=True)
        if args.http or args.abrir:
            os.environ.update(env)
            sys.path[:0] = [str(temporal), str(RAIZ / 'backend')]
            recorrido_http(temporal, args.abrir)
    finally:
        resultados['archivos_protegidos_intactos'] = all(Path(p).exists() and hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in antes.items())
        (temporal / 'resultados.json').write_text(json.dumps(resultados, indent=2), encoding='utf-8')
        print('Base real, .env y reportes intactos:', resultados['archivos_protegidos_intactos'], flush=True)
    return int(not resultados.pop('archivos_protegidos_intactos') or any(resultados.values()))


if __name__ == '__main__':
    sys.exit(main())
