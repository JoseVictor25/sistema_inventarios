"""Recorre pantallas con SQLite y DATA_DIR temporales; comprueba HTML y estados."""
from html.parser import HTMLParser
import re
import os
import logging
from pathlib import Path
import sys
import tempfile

from verificar_catalogo_fase3 import preparar_entorno


class BalanceHTML(HTMLParser):
    vacias = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pila = []
        self.errores = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.vacias:
            self.pila.append(tag)

    def handle_endtag(self, tag):
        if not self.pila or self.pila[-1] != tag:
            self.errores.append(f'Cierre inesperado: {tag}')
        else:
            self.pila.pop()


def main():
    raiz = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix='Inventarios_frontend_', ignore_cleanup_errors=True) as temporal:
        carpeta = Path(temporal)
        os.environ.update(preparar_entorno(carpeta))
        sys.path[:0] = [str(carpeta), str(raiz / 'backend')]
        import django
        django.setup()
        logging.disable(logging.CRITICAL)
        from django.conf import settings
        from django.core.management import call_command
        from django.test import Client
        from django.urls import reverse
        from apps.reportes.tests.datos import crear_datos

        if Path(settings.DATABASES['default']['NAME']).resolve() != (carpeta / 'aislada.sqlite3').resolve():
            raise RuntimeError('SQLite no temporal')
        call_command('migrate', verbosity=0, interactive=False)
        datos = crear_datos()
        nombres = [
            'core:inicio', 'core:qr_configurar', 'core:respaldos',
            'ventas:pos', 'ventas:lista', 'ventas:configurar_impresion',
            'caja:estado', 'caja:historial', 'inventario:stock_lista',
            'inventario:lote_lista', 'inventario:alertas', 'inventario:ajuste_crear',
            'inventario:movimiento_lista', 'compras:compra_lista', 'compras:compra_crear',
            'compras:proveedor_lista', 'compras:proveedor_crear',
            'catalogo:producto_lista', 'catalogo:producto_crear',
            'catalogo:categoria_lista', 'catalogo:categoria_crear',
            'usuarios:lista', 'usuarios:usuario_crear', 'usuarios:rol_lista',
            'auditoria:lista', 'reportes:inicio', 'reportes:ventas',
            'reportes:compras', 'reportes:ganancias', 'reportes:vencimientos',
            'reportes:inventario_valorizado', 'reportes:productos_mas_vendidos',
            'reportes:ventas_metodo_pago', 'reportes:cierres_caja',
        ]
        rutas = [reverse(nombre) for nombre in nombres]
        rutas += [reverse('ventas:detalle', args=[datos['venta'].pk]),
                  reverse('ventas:comprobante', args=[datos['venta'].pk]),
                  reverse('compras:compra_detalle', args=[datos['compra'].pk]),
                  reverse('catalogo:producto_detalle', args=[datos['producto'].pk])]
        for rol in ('dueno', 'vendedor'):
            cliente = Client()
            cliente.force_login(datos[rol])
            for ruta in rutas:
                respuesta = cliente.get(ruta)
                if respuesta.status_code not in (200, 403):
                    raise AssertionError(f'{rol} {ruta}: HTTP {respuesta.status_code}')
                if respuesta.status_code == 200 and respuesta.get('Content-Type', '').startswith('text/html'):
                    html = respuesta.content.decode('utf-8')
                    parser = BalanceHTML()
                    parser.feed(html)
                    if parser.errores or parser.pila:
                        raise AssertionError(f'{rol} {ruta}: {parser.errores}, abiertos: {parser.pila}')
                    if rol == 'dueno':
                        titulo = re.search(r'<title>(.*?)</title>', html, re.I | re.S)
                        if not titulo or not titulo.group(1).strip() or len(re.findall(r'<h1\b', html, re.I)) != 1:
                            raise AssertionError(f'{rol} {ruta}: título o h1 inválido')
            print(f'{rol}: {len(rutas)} pantallas, sin HTTP 500 ni etiquetas desequilibradas')
    return 0


if __name__ == '__main__':
    sys.exit(main())
