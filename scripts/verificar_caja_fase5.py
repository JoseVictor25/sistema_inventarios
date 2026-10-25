"""Fase 5 exclusivamente en SQLite temporal: --pruebas, --http o --abrir.

--abrir realiza primero el recorrido HTTP y deja cuentas y servidor TEMPORALES
para inspección visual. No acredita por sí mismo una revisión de navegador.
"""
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
    from html.parser import HTMLParser
    from http.cookiejar import CookieJar
    from urllib.error import HTTPError
    from urllib.parse import urlencode, urlparse
    from urllib.request import HTTPCookieProcessor, Request, build_opener
    from wsgiref.simple_server import make_server, WSGIRequestHandler
    from uuid import uuid4
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.core.wsgi import get_wsgi_application
    from django.db import connections
    from apps.caja.models import Caja, MovimientoCaja
    from apps.core.frontend import RECURSOS_FRONTEND
    from apps.usuarios.models import Usuario, Rol
    from verificar_interfaz_fase0 import TokenCSRF

    if Path(settings.DATABASES['default']['NAME']).resolve() != (temporal / 'aislada.sqlite3').resolve():
        raise RuntimeError('Se rechazó una base distinta de la temporal.')
    call_command('migrate', verbosity=0, interactive=False)
    call_command('cargar_datos_iniciales', verbosity=0)
    clave = secrets.token_urlsafe(24)
    for nombre, rol in (('dueno_fase5', 'Dueño'), ('vendedor_fase5', 'Vendedor')):
        Usuario.objects.create_user(nombre, password=clave, rol=Rol.objects.get(nombre=rol))
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
    informe = {'aprobado': False, 'inspeccion_visual': 'pendiente', 'peticiones': peticiones}

    def pedir(cliente, ruta, datos=None, htmx=False):
        solicitud = Request(origen + ruta, data=urlencode(datos).encode() if datos is not None else None,
                            headers={'HX-Request': 'true'} if htmx else {})
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
            attrs = dict(attrs)
            for atributo in ('src', 'href', 'action', 'hx-post', 'hx-get'):
                url = attrs.get(atributo, '')
                if url.startswith(('https://', 'http://', '//')):
                    self.externas.append(url)
                if url.startswith('/static/'):
                    self.recursos.add(url)

    def pagina(cliente, ruta, archivo):
        estado, contenido = pedir(cliente, ruta)
        assert estado == 200, (ruta, estado)
        html = contenido.decode()
        referencias = Referencias(html)
        assert not referencias.externas, referencias.externas
        for recurso in referencias.recursos:
            assert pedir(cliente, recurso)[0] == 200, recurso
        (temporal / archivo).write_text(html, encoding='utf-8')
        return TokenCSRF(html).token

    try:
        vendedor = sesion('vendedor_fase5')
        token = pagina(vendedor, '/caja/', 'apertura.html')
        datos = {'clave': uuid4(), 'monto_inicial': '100', 'turno': 'Prueba aislada', 'csrfmiddlewaretoken': token}
        for _ in range(2):
            assert pedir(vendedor, '/caja/abrir/', datos)[0] == 200
        assert Caja.objects.count() == 1
        caja = Caja.objects.get()
        token = pagina(vendedor, '/caja/', 'abierta.html')
        movimiento = {'clave': uuid4(), 'caja_id': caja.pk, 'tipo': 'INGRESO', 'monto': '10', 'concepto': 'Cambio temporal', 'csrfmiddlewaretoken': token}
        for _ in range(2):
            estado, cuerpo = pedir(vendedor, '/caja/movimientos/nuevo/', movimiento, htmx=True)
            assert estado == 200 and b'hx-swap-oob' in cuerpo
        assert MovimientoCaja.objects.count() == 1
        assert pedir(vendedor, '/caja/cerrar/', {'clave': uuid4()})[0] == 403  # CSRF
        cierre = {'clave': uuid4(), 'caja_id': caja.pk, 'monto_contado': '110', 'csrfmiddlewaretoken': token}
        for _ in range(2):
            estado, cuerpo = pedir(vendedor, '/caja/cerrar/', cierre)
            assert estado == 200 and b'CUADRA' in cuerpo
        pagina(vendedor, f'/caja/?caja_id={caja.pk}', 'cierre.html')
        movimiento['clave'] = uuid4()
        assert pedir(vendedor, '/caja/movimientos/nuevo/', movimiento, htmx=True)[0] == 422
        assert pedir(vendedor, '/caja/historial/')[0] == 403
        dueno = sesion('dueno_fase5')
        pagina(dueno, '/caja/historial/', 'historial.html')
        for recurso in (*RECURSOS_FRONTEND, 'css/app.css', 'js/app.js', 'img/favicon.svg'):
            assert pedir(dueno, '/static/' + recurso)[0] == 200, recurso
        assert not any(p['estado'] in (404, 500) for p in peticiones)
        informe['aprobado'] = True
        print('HTTP aislado aprobado: ciclo, reenvíos, HTMX, permisos, CSRF y recursos locales.', flush=True)
        if abrir:
            import webbrowser
            print(f'Revisión visual MANUAL: {origen}/login/', flush=True)
            print(f'Cuentas TEMPORALES: dueno_fase5 / vendedor_fase5. Contraseña temporal: {clave}', flush=True)
            print('Revisar a 1280x800 y 390x844. Ctrl+C detiene el servidor. Datos y HTML quedan en TEMP.', flush=True)
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
    temporal = Path(tempfile.mkdtemp(prefix='Inventarios_verificacion_fase5_'))
    env = preparar_entorno(temporal)
    env['NOMBRE_NEGOCIO'] = 'Caja · pruebas temporales'
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
                    resultado = subprocess.run([sys.executable, *comando], cwd=RAIZ / 'backend', env=env,
                                               stdout=salida, stderr=subprocess.STDOUT)
                resultados[nombre] = resultado.returncode
                if nombre == 'test' and 'Ran 0 tests' in (temporal / 'test.txt').read_text(encoding='utf-8'):
                    resultados[nombre] = 1
                print(f'{nombre}: código {resultados[nombre]}', flush=True)
        if args.http or args.abrir:
            os.environ.update(env)
            sys.path[:0] = [str(temporal), str(RAIZ / 'backend')]
            recorrido_http(temporal, args.abrir)
    finally:
        resultados['archivos_protegidos_intactos'] = all(
            Path(p).exists() and hashlib.sha256(Path(p).read_bytes()).hexdigest() == huella
            for p, huella in antes.items())
        (temporal / 'resultados.json').write_text(json.dumps(resultados, indent=2), encoding='utf-8')
        print('Base real, .env y reportes intactos:', resultados['archivos_protegidos_intactos'], flush=True)
    return int(not resultados.pop('archivos_protegidos_intactos') or any(resultados.values()))


if __name__ == '__main__':
    sys.exit(main())
