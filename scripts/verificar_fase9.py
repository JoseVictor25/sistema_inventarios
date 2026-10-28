"""Auditoría, respaldos y panel exclusivamente con SQLite y archivos temporales."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import tempfile
from verificar_catalogo_fase3 import preparar_entorno
from verificar_reportes_fase8 import huellas, RAIZ


def recuperar_temporal(temporal, usuario):
    from django.conf import settings
    from apps.core.services import crear_respaldo
    from apps.core.respaldos import verificar_copia, hash_archivo
    fuente = Path(settings.DATABASES['default']['NAME'])
    antes = hash_archivo(fuente)
    resultado = crear_respaldo(usuario)
    copia = Path(settings.BACKUP_DIR) / resultado['archivo']
    restaurada = temporal / 'recuperada.sqlite3'
    with restaurada.open('xb'):
        pass
    origen = sqlite3.connect(copia.as_uri() + '?mode=ro', uri=True)
    destino = sqlite3.connect(restaurada)
    real_temporal = sqlite3.connect(fuente.as_uri() + '?mode=ro', uri=True)
    try:
        origen.backup(destino)
        tablas = [f[0] for f in real_temporal.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        cantidades = {}
        for tabla in tablas:
            identificador = '"' + tabla.replace('"', '""') + '"'
            filas = real_temporal.execute('SELECT * FROM ' + identificador + ' ORDER BY rowid').fetchall()
            assert filas == destino.execute('SELECT * FROM ' + identificador + ' ORDER BY rowid').fetchall(), tabla
            cantidades[tabla] = len(filas)
        assert destino.execute('PRAGMA foreign_key_check').fetchall() == []
    finally:
        origen.close()
        destino.close()
        real_temporal.close()
    assert verificar_copia(restaurada)['sha256'] == resultado['sha256']
    assert hash_archivo(fuente) == antes
    informe = dict(respaldo=resultado, recuperada=str(restaurada), tablas=cantidades, fuente_temporal_intacta=True)
    (temporal / 'recuperacion.json').write_text(json.dumps(informe, indent=2), encoding='utf-8')
    print(f'Respaldo y recuperación aprobados: {len(tablas)} tablas comparadas íntegramente.', flush=True)


def recorrido_http(temporal, password, abrir):
    import threading
    from collections import Counter
    from html.parser import HTMLParser
    from http.cookiejar import CookieJar
    from urllib.error import HTTPError
    from urllib.parse import urlencode
    from urllib.request import HTTPCookieProcessor, Request, build_opener
    from wsgiref.simple_server import make_server, WSGIRequestHandler
    from django.core.wsgi import get_wsgi_application
    from django.db import connections
    from apps.core.frontend import RECURSOS_FRONTEND
    from verificar_interfaz_fase0 import TokenCSRF
    peticiones = []
    app = get_wsgi_application()
    def sitio(environ, start_response):
        def responder(status, headers, exc_info=None):
            peticiones.append(dict(ruta=environ['PATH_INFO'], estado=int(status[:3])))
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
    informe = dict(aprobado=False, visual='Pendiente de inspección manual', peticiones=peticiones)
    def pedir(cliente, ruta, post=None):
        try:
            respuesta = cliente.open(Request(origen + ruta, data=urlencode(post).encode() if post is not None else None), timeout=150)
        except HTTPError as error:
            respuesta = error
        with respuesta:
            return respuesta.status, respuesta.read()
    def sesion(nombre):
        cliente = build_opener(HTTPCookieProcessor(CookieJar()))
        estado, html = pedir(cliente, '/login/')
        assert estado == 200
        assert pedir(cliente, '/login/', dict(username=nombre, password=password, csrfmiddlewaretoken=TokenCSRF(html.decode()).token))[0] == 200
        return cliente
    class Recursos(HTMLParser):
        rutas = set()
        def handle_starttag(self, tag, attrs):
            if tag in ('script', 'link', 'img', 'iframe'):
                atributos = dict(attrs)
                ruta = atributos.get('src') or atributos.get('href')
                if ruta:
                    assert ruta.startswith('/static/'), ruta
                    self.rutas.add(ruta)
    try:
        dueno, vendedor = sesion('dueno_fase8'), sesion('vendedor_fase8')
        recursos = Recursos()
        for nombre, ruta in [('inicio', '/'), ('auditoria', '/auditoria/'), ('respaldos', '/sistema/respaldos/')]:
            estado, html = pedir(dueno, ruta)
            assert estado == 200, (ruta, estado)
            recursos.feed(html.decode())
            (temporal / (nombre + '.html')).write_bytes(html)
        estado, html = pedir(dueno, '/sistema/respaldos/')
        assert pedir(dueno, '/sistema/respaldos/crear/', {'csrfmiddlewaretoken': TokenCSRF(html.decode()).token})[0] == 200
        assert pedir(dueno, '/sistema/respaldos/crear/', {})[0] == 403
        assert pedir(dueno, '/sistema/respaldos/crear/', {'csrfmiddlewaretoken': TokenCSRF(html.decode()).token, 'ruta': 'no-permitida'})[0] == 422
        assert pedir(dueno, '/auditoria/?desde=invalida')[0] == 422
        assert pedir(dueno, '/auditoria/?entidad=Caja')[0] == 200
        assert pedir(dueno, '/auditoria/?page=2')[0] == 200
        for ruta in ('/auditoria/', '/sistema/respaldos/'):
            assert pedir(vendedor, ruta)[0] == 403
        estado, html = pedir(vendedor, '/')
        assert estado == 200 and b'Ventas del d' not in html and b'/auditoria/' not in html
        for ruta in recursos.rutas | {'/static/' + r for r in RECURSOS_FRONTEND}:
            assert pedir(dueno, ruta)[0] == 200, ruta
        assert not any(p['estado'] == 404 or p['estado'] >= 500 for p in peticiones)
        informe.update(aprobado=True, estados=dict(Counter(p['estado'] for p in peticiones)))
        print(f'HTTP aprobado: {len(peticiones)} solicitudes, sin 404 ni 500.', flush=True)
        if abrir:
            import webbrowser
            print(f'Revisión visual: {origen}/', flush=True)
            print(f'Usuarios ficticios: dueno_fase8 / vendedor_fase8. Contraseña: {password}', flush=True)
            print('Revisar inicio, /auditoria/ y /sistema/respaldos/ en 1280x800 y 390x844. Ctrl+C termina.', flush=True)
            webbrowser.open(origen + '/')
            try:
                threading.Event().wait()
            except KeyboardInterrupt:
                pass
    finally:
        servidor.shutdown()
        servidor.server_close()
        hilo.join(timeout=5)
        connections.close_all()
        (temporal / 'http.json').write_text(json.dumps(informe, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for opcion in ('pruebas', 'http', 'respaldos', 'abrir'):
        parser.add_argument('--' + opcion, action='store_true')
    args = parser.parse_args()
    if not any(vars(args).values()):
        parser.error('Elige --pruebas, --http, --respaldos o --abrir.')
    if Path(sys.executable).resolve() != (RAIZ / 'venv/Scripts/python.exe').resolve():
        parser.error('Utiliza exclusivamente venv/Scripts/python.exe.')
    antes = huellas()
    temporal = Path(tempfile.mkdtemp(prefix='Inventarios_verificacion_fase9_'))
    env = preparar_entorno(temporal)
    env.update(NOMBRE_NEGOCIO='Demostración temporal Fase 9', TIME_ZONE='America/La_Paz')
    resultados = {}
    print(f'Evidencia y SQLite aisladas: {temporal}', flush=True)
    try:
        if args.pruebas:
            comandos = {'check': ['manage.py', 'check'], 'makemigrations': ['manage.py', 'makemigrations', '--check', '--dry-run'],
                        'test': ['manage.py', 'test', '--noinput'], 'frontend': [str(RAIZ / 'scripts/preparar_frontend.py'), '--verificar']}
            for nombre, comando in comandos.items():
                with (temporal / f'{nombre}.txt').open('w', encoding='utf-8') as salida:
                    proceso = subprocess.run([sys.executable, *comando], cwd=RAIZ / 'backend', env=env, stdout=salida, stderr=subprocess.STDOUT)
                resultados[nombre] = proceso.returncode
                if nombre == 'test' and 'Ran 0 tests' in (temporal / 'test.txt').read_text(encoding='utf-8'):
                    resultados[nombre] = 1
                print(f'{nombre}: código {resultados[nombre]}', flush=True)
        if args.http or args.respaldos or args.abrir:
            os.environ.update(env)
            sys.path[:0] = [str(temporal), str(RAIZ / 'backend')]
            import django
            django.setup()
            from django.conf import settings
            from django.core.management import call_command
            from django.db import connections
            from apps.reportes.tests.datos import crear_datos
            assert Path(settings.DATABASES['default']['NAME']).resolve() == temporal / 'aislada.sqlite3'
            assert Path(settings.BACKUP_DIR).resolve().is_relative_to(temporal)
            call_command('migrate', verbosity=0, interactive=False)
            password = secrets.token_urlsafe(24)
            datos = crear_datos(password)
            from decimal import Decimal
            from apps.catalogo.services import cambiar_precio
            from apps.inventario.models import Lote
            from apps.inventario.services import ajustar_inventario
            cambiar_precio(datos['dueno'], datos['unidad'], Decimal('9'))
            lote = Lote.objects.filter(cantidad_actual__gt=0).first()
            ajustar_inventario(datos['dueno'], lote, 'MERMA', -1, 'Demostración ficticia de auditoría')
            try:
                if args.respaldos:
                    recuperar_temporal(temporal, datos['dueno'])
                    # También ejercitar el comando del operador sobre esta misma fuente ficticia.
                    resultado = subprocess.run([sys.executable, str(RAIZ / 'scripts/respaldo.py')], env=env, capture_output=True, text=True)
                    (temporal / 'respaldo_cli.txt').write_text(resultado.stdout + resultado.stderr, encoding='utf-8')
                    assert resultado.returncode == 0, 'Falló el comando de respaldo aislado.'
                    resultados['respaldos'] = 0
                if args.http or args.abrir:
                    recorrido_http(temporal, password, args.abrir)
                    resultados['http'] = 0
            finally:
                connections.close_all()
    except Exception as error:
        resultados['error'] = type(error).__name__
        raise
    finally:
        resultados['archivos_protegidos_intactos'] = antes == huellas()
        (temporal / 'resultados.json').write_text(json.dumps(resultados, indent=2), encoding='utf-8')
        print('Base real, .env y reportes intactos:', resultados['archivos_protegidos_intactos'], flush=True)
    return int(not resultados.pop('archivos_protegidos_intactos') or any(resultados.values()))


if __name__ == '__main__':
    sys.exit(main())
