"""Capturas aisladas de pantallas representativas con Chrome headless."""
import base64
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import urlopen
from urllib.parse import urlparse
from wsgiref.simple_server import make_server, WSGIRequestHandler

from verificar_catalogo_fase3 import preparar_entorno


class Silencioso(WSGIRequestHandler):
    def log_message(self, *_args):
        pass


class CDP:
    """Intercambio WebSocket mínimo con Chrome, sin dependencias nuevas."""

    def __init__(self, url):
        destino = urlparse(url)
        self.conexion = socket.create_connection((destino.hostname, destino.port), timeout=15)
        llave = base64.b64encode(secrets.token_bytes(16)).decode()
        solicitud = (f'GET {destino.path} HTTP/1.1\r\nHost: {destino.netloc}\r\n'
                     f'Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {llave}\r\n'
                     'Sec-WebSocket-Version: 13\r\nOrigin: http://localhost\r\n\r\n')
        self.conexion.sendall(solicitud.encode('ascii'))
        respuesta = b''
        while b'\r\n\r\n' not in respuesta:
            respuesta += self.conexion.recv(4096)
        if not respuesta.startswith(b'HTTP/1.1 101 '):
            raise RuntimeError('Chrome rechazó WebSocket: ' + respuesta.split(b'\r\n', 1)[0].decode('ascii', errors='replace'))
        self.pendiente = respuesta.split(b'\r\n\r\n', 1)[1]
        self.identificador = 0

    def leer(self, cantidad):
        while len(self.pendiente) < cantidad:
            self.pendiente += self.conexion.recv(max(4096, cantidad - len(self.pendiente)))
        bloque, self.pendiente = self.pendiente[:cantidad], self.pendiente[cantidad:]
        return bloque

    def enviar(self, datos):
        cuerpo = json.dumps(datos).encode('utf-8')
        mascara = secrets.token_bytes(4)
        longitud = len(cuerpo)
        encabezado = bytes([0x81, 0x80 | (longitud if longitud < 126 else 126)])
        if longitud >= 126:
            encabezado += longitud.to_bytes(2, 'big')
        self.conexion.sendall(encabezado + mascara + bytes(b ^ mascara[i % 4] for i, b in enumerate(cuerpo)))

    def recibir(self):
        primero, segundo = self.leer(2)
        longitud = segundo & 0x7f
        if longitud == 126:
            longitud = int.from_bytes(self.leer(2), 'big')
        elif longitud == 127:
            longitud = int.from_bytes(self.leer(8), 'big')
        mascara = self.leer(4) if segundo & 0x80 else None
        cuerpo = self.leer(longitud)
        if mascara:
            cuerpo = bytes(b ^ mascara[i % 4] for i, b in enumerate(cuerpo))
        if primero & 0x0f != 1:
            return None
        return json.loads(cuerpo)

    def comando(self, metodo, parametros=None):
        self.identificador += 1
        actual = self.identificador
        self.enviar({'id': actual, 'method': metodo, 'params': parametros or {}})
        while True:
            respuesta = self.recibir()
            if respuesta and respuesta.get('id') == actual:
                if 'error' in respuesta:
                    raise RuntimeError(respuesta['error'])
                return respuesta.get('result', {})


def main():
    raiz = Path(__file__).resolve().parent.parent
    chrome = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    if not chrome.is_file():
        raise RuntimeError('Chrome headless no disponible')
    salida = raiz / 'docs/evidencias_frontend/capturas'
    salida.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='Inventarios_capturas_', ignore_cleanup_errors=True) as temporal:
        carpeta = Path(temporal)
        os.environ.update(preparar_entorno(carpeta))
        sys.path[:0] = [str(carpeta), str(raiz / 'backend')]
        import django
        django.setup()
        logging.disable(logging.CRITICAL)
        from django.conf import settings
        from django.core.management import call_command
        from django.core.wsgi import get_wsgi_application
        from django.test import Client
        from apps.reportes.tests.datos import crear_datos

        if Path(settings.DATABASES['default']['NAME']).resolve() != (carpeta / 'aislada.sqlite3').resolve():
            raise RuntimeError('SQLite no temporal')
        call_command('migrate', verbosity=0, interactive=False)
        datos = crear_datos()
        cliente = Client()
        cliente.force_login(datos['dueno'])
        sesion = cliente.cookies['sessionid'].value
        django_app = get_wsgi_application()

        def app(environ, start_response):
            if environ['PATH_INFO'] == '/login/':
                environ.pop('HTTP_COOKIE', None)
            else:
                environ['HTTP_COOKIE'] = 'sessionid=' + sesion
            if environ['PATH_INFO'].startswith('/static/'):
                return django_app(environ, start_response)
            estado = []
            encabezados = []

            def capturar(status, headers, _exc_info=None):
                estado.append(status)
                encabezados.extend(headers)

            respuesta = django_app(environ, capturar)
            cuerpo = b''.join(respuesta)
            if hasattr(respuesta, 'close'):
                respuesta.close()
            tipo = next((v for k, v in encabezados if k.lower() == 'content-type'), '')
            if estado[0].startswith('200') and tipo.startswith('text/html'):
                observador = (b'<script>window.addEventListener("error",function(){document.documentElement.dataset.errores='
                             b'String(1+Number(document.documentElement.dataset.errores||0))});'
                             b'window.addEventListener("load",function(){document.documentElement.dataset.ancho=String(innerWidth);document.documentElement.dataset.desbordamiento='
                             b'document.documentElement.scrollWidth>innerWidth?"si":"no"})</script>')
                cuerpo = cuerpo.replace(b'</head>', observador + b'</head>', 1)
                encabezados = [(k, v) for k, v in encabezados if k.lower() != 'content-length']
                encabezados.append(('Content-Length', str(len(cuerpo))))
            start_response(estado[0], encabezados)
            return [cuerpo]

        servidor = make_server('127.0.0.1', 0, app, handler_class=Silencioso)
        servidor.handle_error = lambda *_args: None
        hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
        hilo.start()
        try:
            rutas = {
                'login': '/login/', 'inicio': '/', 'pos': '/ventas/nueva/', 'historial': '/ventas/',
                'impresion': '/ventas/impresion/', 'qr': '/sistema/qr/',
                'compras': '/compras/', 'productos': '/catalogo/productos/',
                'venta_detalle': f"/ventas/{datos['venta'].pk}/",
                'comprobante': f"/ventas/{datos['venta'].pk}/comprobante/",
                'caja': '/caja/', 'historial_caja': '/caja/historial/',
                'proveedores': '/compras/proveedores/',
                'proveedor_nuevo': '/compras/proveedores/nuevo/',
                'compra_nueva': '/compras/nueva/',
                'compra_detalle': f"/compras/{datos['compra'].pk}/",
                'producto_nuevo': '/catalogo/productos/nuevo/',
                'producto_detalle': f"/catalogo/productos/{datos['producto'].pk}/",
                'categorias': '/catalogo/categorias/',
                'categoria_nueva': '/catalogo/categorias/nueva/',
                'inventario': '/inventario/', 'lotes': '/inventario/lotes/',
                'alertas': '/inventario/alertas/', 'ajuste': '/inventario/ajuste/',
                'movimientos': '/inventario/movimientos/',
                'usuarios': '/usuarios/', 'usuario_nuevo': '/usuarios/nuevo/',
                'roles': '/usuarios/roles/', 'auditoria': '/auditoria/',
                'respaldos': '/sistema/respaldos/',
                'reportes': '/reportes/', 'reporte_ventas': '/reportes/ventas/',
                'reporte_compras': '/reportes/compras/',
                'reporte_ganancias': '/reportes/ganancias/',
                'reporte_vencimientos': '/reportes/vencimientos/',
                'reporte_inventario': '/reportes/inventario_valorizado/',
                'reporte_productos': '/reportes/productos_mas_vendidos/',
                'reporte_metodos': '/reportes/ventas_metodo_pago/',
                'reporte_cierres': '/reportes/cierres_caja/',
            }
            perfil = carpeta / 'chrome_perfil'
            proceso = subprocess.Popen([str(chrome), '--headless=new', '--disable-gpu',
                                        '--no-first-run', '--no-default-browser-check',
                                        '--remote-debugging-port=0', '--remote-allow-origins=*',
                                        f'--user-data-dir={perfil}', 'about:blank'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                puerto_archivo = perfil / 'DevToolsActivePort'
                for _ in range(100):
                    if puerto_archivo.is_file():
                        break
                    time.sleep(.1)
                puerto = int(puerto_archivo.read_text().splitlines()[0])
                objetivos = json.load(urlopen(f'http://127.0.0.1:{puerto}/json', timeout=10))
                pagina = next(o for o in objetivos if o['type'] == 'page')
                cdp = CDP(pagina['webSocketDebuggerUrl'])
                cdp.comando('Page.enable')
                cdp.comando('Runtime.enable')
                for ancho, alto in ((1366, 768), (375, 812)):
                    cdp.comando('Emulation.setDeviceMetricsOverride', {
                        'width': ancho, 'height': alto, 'deviceScaleFactor': 1, 'mobile': ancho == 375})
                    for nombre, ruta in rutas.items():
                        cdp.comando('Page.navigate', {'url': f'http://127.0.0.1:{servidor.server_port}{ruta}'})
                        time.sleep(1.2)
                        cdp.comando('Runtime.evaluate', {'expression': 'window.scrollTo(0,0)'})
                        medido = cdp.comando('Runtime.evaluate', {
                            'expression': '({ancho:innerWidth,alto:innerHeight,scroll:document.documentElement.scrollWidth,errores:Number(document.documentElement.dataset.errores||0)})',
                            'returnByValue': True})['result']['value']
                        if medido['ancho'] != ancho or medido['alto'] != alto:
                            raise AssertionError(f'{nombre}: viewport {medido}, solicitado {ancho}x{alto}')
                        if medido['scroll'] > medido['ancho'] or medido['errores']:
                            raise AssertionError(f'{nombre} {ancho}x{alto}: desbordamiento o error JavaScript: {medido}')
                        captura = cdp.comando('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False})
                        (salida / f'{nombre}_{ancho}x{alto}.png').write_bytes(base64.b64decode(captura['data']))
                        print(f'{nombre} {ancho}x{alto}: viewport real, sin desbordamiento ni errores JavaScript', flush=True)
                        if nombre == 'pos' and ancho == 1366:
                            flujo = cdp.comando('Runtime.evaluate', {'expression': '''(() => {
                              const total = document.getElementById('monto-total-val');
                              total.dataset.total = '50.00';
                              const primera = document.querySelector('#lista-pagos .fila-pago');
                              const monto = primera.querySelector('.input-monto-pago');
                              monto.value = '20.00'; monto.dispatchEvent(new Event('input', {bubbles:true}));
                              document.getElementById('btn-agregar-metodo').click();
                              const filas = [...document.querySelectorAll('#lista-pagos .fila-pago')];
                              const referencia = filas[1].querySelector('.fila-referencia');
                              const segundo = filas[1].querySelector('.select-metodo');
                              const qr = [...segundo.options].find(o => o.dataset.esQr === '1');
                              segundo.value = qr.value; segundo.dispatchEvent(new Event('change', {bubbles:true}));
                              const referenciaVisible = !referencia.classList.contains('d-none');
                              const efectivoVisible = !document.getElementById('seccion-efectivo').classList.contains('d-none');
                              const recibido = document.getElementById('recv');
                              recibido.value = '25.00'; recibido.dispatchEvent(new Event('input', {bubbles:true}));
                              const vuelto = document.getElementById('chg').textContent;
                              recibido.value = '15.00'; recibido.dispatchEvent(new Event('input', {bubbles:true}));
                              const aviso = !document.getElementById('aviso-efectivo-insuficiente').classList.contains('d-none');
                              return {filas:filas.length, referenciaVisible, efectivoVisible, vuelto, aviso};
                            })()''', 'returnByValue': True})['result']['value']
                            if flujo != {'filas': 2, 'referenciaVisible': True, 'efectivoVisible': True,
                                         'vuelto': 'Bs 5.00', 'aviso': True}:
                                raise AssertionError(f'Flujo POS mixto, referencia, efectivo y vuelto: {flujo}')
                            print('POS: pagos mixtos, referencia, efectivo y vuelto correctos', flush=True)
                cdp.conexion.close()
            finally:
                proceso.terminate()
                proceso.wait(timeout=10)
        finally:
            servidor.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
