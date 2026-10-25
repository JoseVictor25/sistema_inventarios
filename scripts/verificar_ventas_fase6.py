"""Fase 6 exclusivamente en SQLite temporal: --pruebas, --http o --abrir.

--abrir realiza primero el recorrido HTTP y deja cuentas y servidor TEMPORALES
para inspección visual. No acredita por sí mismo una revisión de navegador.
"""
import argparse
from decimal import Decimal
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
    from urllib.parse import urlencode
    from urllib.request import HTTPCookieProcessor, Request, build_opener
    from wsgiref.simple_server import make_server, WSGIRequestHandler
    from uuid import uuid4
    from datetime import timedelta
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.core.wsgi import get_wsgi_application
    from django.db import connections
    from django.utils import timezone
    from apps.caja import services as caja_s
    from apps.caja.models import Caja
    from apps.catalogo.models import Categoria, Presentacion, Producto
    from apps.core.frontend import RECURSOS_FRONTEND
    from apps.inventario.models import Lote
    from apps.usuarios.models import Usuario, Rol
    from apps.ventas.models import MetodoPago, Venta
    from verificar_interfaz_fase0 import TokenCSRF

    if Path(settings.DATABASES['default']['NAME']).resolve() != (temporal / 'aislada.sqlite3').resolve():
        raise RuntimeError('Se rechazó una base distinta de la temporal.')
    call_command('migrate', verbosity=0, interactive=False)
    call_command('cargar_datos_iniciales', verbosity=0)

    clave = secrets.token_urlsafe(24)
    dueno = Usuario.objects.create_user('dueno_fase6', password=clave, rol=Rol.objects.get(nombre='Dueño'))
    vendedor = Usuario.objects.create_user('vendedor_fase6', password=clave, rol=Rol.objects.get(nombre='Vendedor'))
    cajero_sin_caja = Usuario.objects.create_user('cajero_sin_caja', password=clave, rol=Rol.objects.get(nombre='Vendedor'))
    sin_permiso = Usuario.objects.create_user('sin_permiso_fase6', password=clave)

    # Catálogo inicial para pruebas de POS
    cat = Categoria.objects.create(nombre="Suplementos")
    p1 = Producto.objects.create(codigo="COL-300", nombre="Colágeno hidrolizado 300g", categoria=cat, stock_minimo=5)
    pres_u = Presentacion.objects.create(producto=p1, nombre="Unidad", unidades_equivalentes=1, precio_venta=Decimal("50.00"))
    pres_c = Presentacion.objects.create(producto=p1, nombre="Cuarta", unidades_equivalentes=3, precio_venta=Decimal("135.00"))

    hoy = timezone.localdate()
    Lote.objects.create(producto=p1, codigo_lote="L-2026-001", cantidad_inicial=30, cantidad_actual=30, costo_unitario=Decimal("25.00"), fecha_vencimiento=hoy + timedelta(days=60))

    # Abrir caja para vendedor
    caja_s.abrir_caja(vendedor, "100.00", "Turno Mañana", clave=uuid4())

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
        vendedor_cl = sesion('vendedor_fase6')
        token = pagina(vendedor_cl, '/ventas/nueva/', 'pos.html')

        # Buscar producto
        estado_busq, cuerpo_busq = pedir(vendedor_cl, '/ventas/buscar/?q=Col%C3%A1geno', htmx=True)
        assert estado_busq == 200 and b'Col\xc3\xa1geno' in cuerpo_busq

        # Agregar al carrito
        estado_add, cuerpo_add = pedir(vendedor_cl, '/ventas/carrito/agregar/',
                                       {'presentacion_id': pres_u.pk, 'cantidad': 2, 'csrfmiddlewaretoken': token}, htmx=True)
        assert estado_add == 200 and b'100' in cuerpo_add

        # Actualizar cantidad
        estado_upd, cuerpo_upd = pedir(vendedor_cl, '/ventas/carrito/actualizar/',
                                       {'indice': 0, 'cantidad': 3, 'csrfmiddlewaretoken': token}, htmx=True)
        assert estado_upd == 200 and b'150' in cuerpo_upd

        # Confirmar venta
        clave_venta = str(uuid4())
        efectivo = MetodoPago.objects.get(nombre="Efectivo")
        datos_conf = {
            'clave': clave_venta,
            'metodo_id': efectivo.pk,
            'monto': '150.00',
            'monto_recibido': '200.00',
            'csrfmiddlewaretoken': token,
        }
        estado_conf, cuerpo_conf = pedir(vendedor_cl, '/ventas/confirmar/', datos_conf, htmx=True)
        assert estado_conf == 200 and b'Venta registrada con' in cuerpo_conf
        assert Venta.objects.count() == 1
        venta = Venta.objects.get()

        # Idempotencia: reenvío con la misma clave devuelve el resultado sin duplicar
        estado_conf2, cuerpo_conf2 = pedir(vendedor_cl, '/ventas/confirmar/', datos_conf, htmx=True)
        assert estado_conf2 == 200 and b'Venta registrada con' in cuerpo_conf2
        assert Venta.objects.count() == 1

        # Listado de ventas del día
        pagina(vendedor_cl, '/ventas/', 'venta_lista.html')

        # Detalle de venta (vendedor sin ver_costos no ve costo del lote)
        estado_det, cuerpo_det = pedir(vendedor_cl, f'/ventas/{venta.pk}/')
        assert estado_det == 200 and b'costo:' not in cuerpo_det
        (temporal / 'venta_detalle_vendedor.html').write_text(cuerpo_det.decode(), encoding='utf-8')

        # Dueño consulta detalle y sí ve costos
        dueno_cl = sesion('dueno_fase6')
        estado_det_d, cuerpo_det_d = pedir(dueno_cl, f'/ventas/{venta.pk}/')
        assert estado_det_d == 200 and b'costo:' in cuerpo_det_d
        (temporal / 'venta_detalle_dueno.html').write_text(cuerpo_det_d.decode(), encoding='utf-8')

        # Comprobación de aislamiento de Caja: cajero_sin_caja no tiene turno abierto
        cajero_cl = sesion('cajero_sin_caja')
        token_cajero = pagina(cajero_cl, '/ventas/nueva/', 'pos_cajero_sin_caja.html')
        assert 'Sin turno de caja abierto' in (temporal / 'pos_cajero_sin_caja.html').read_text(encoding='utf-8')
        # Agrega un producto al carrito para tener líneas activas
        pedir(cajero_cl, '/ventas/carrito/agregar/', {
            'presentacion_id': pres_u.pk,
            'cantidad': 1,
            'csrfmiddlewaretoken': token_cajero,
        }, htmx=True)
        # Intentar confirmar venta debe fallar con 422 y mensaje descriptivo
        estado_sc, cuerpo_sc = pedir(cajero_cl, '/ventas/confirmar/', {
            'clave': str(uuid4()),
            'metodo_id': efectivo.pk,
            'monto': '50.00',
            'csrfmiddlewaretoken': token_cajero,
        }, htmx=True)
        assert estado_sc == 422 and b'Abre tu turno de caja antes de vender' in cuerpo_sc

        # Usuario sin permiso es rechazado con 403
        sin_perm_cl = sesion('sin_permiso_fase6')
        assert pedir(sin_perm_cl, '/ventas/nueva/')[0] == 403
        assert pedir(sin_perm_cl, '/ventas/')[0] == 403

        # Verificar todos los recursos estáticos requeridos
        for recurso in (*RECURSOS_FRONTEND, 'css/app.css', 'js/app.js', 'js/pos.js', 'img/favicon.svg'):
            assert pedir(dueno_cl, '/static/' + recurso)[0] == 200, recurso

        assert not any(p['estado'] in (404, 500) for p in peticiones)
        informe['aprobado'] = True
        print('HTTP aislado aprobado: ciclo POS, carrito, confirmación, idempotencia, permisos y recursos locales.', flush=True)

        if abrir:
            import webbrowser
            print(f'Revisión visual MANUAL: {origen}/login/', flush=True)
            print('Cuentas TEMPORALES disponibles:', flush=True)
            print('  1. dueno_fase6 (Rol Dueño — puede abrir su turno de caja, consultar todas las cajas y ver costos)', flush=True)
            print('  2. vendedor_fase6 (Rol Vendedor — tiene caja abierta para probar ventas inmediatamente)', flush=True)
            print('  3. cajero_sin_caja (Rol Vendedor — SIN caja abierta, para verificar aviso y bloqueo)', flush=True)
            print(f'Contraseña común: {clave}', flush=True)
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
    temporal = Path(tempfile.mkdtemp(prefix='Inventarios_verificacion_fase6_'))
    env = preparar_entorno(temporal)
    env['NOMBRE_NEGOCIO'] = 'Ventas · pruebas temporales'
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
