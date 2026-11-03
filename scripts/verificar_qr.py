"""Recorrido QR en WebView2 con instalación, imagen y productos ficticios."""
import json
import argparse
from pathlib import Path
import secrets
import sys
import tempfile
import time

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from verificar_reportes_fase8 import huellas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--http', action='store_true')
    parser.add_argument('--abrir', action='store_true')
    args = parser.parse_args()
    if Path(sys.executable).resolve() != RAIZ / 'venv/Scripts/python.exe':
        raise RuntimeError('Utiliza el Python del venv.')
    antes = huellas()
    temporal = Path(tempfile.mkdtemp(prefix='Inventarios_QR_visual_'))
    print('Evidencias:', temporal, flush=True)
    from desktop.inicializacion import configurar
    configurar(temporal, autorizar_nueva=True)
    from django.conf import settings
    from django.core.management import call_command
    from django.core.wsgi import get_wsgi_application
    from django.db import connections
    from apps.reportes.tests.datos import crear_datos
    from apps.ventas.models import Venta
    from apps.caja.models import Caja, MovimientoCaja
    from apps.inventario.models import Lote
    from PIL import Image, ImageDraw
    clave = secrets.token_urlsafe(20)
    datos = crear_datos(clave)
    imagen = Image.new('RGB', (768, 768), 'white')
    dibujo = ImageDraw.Draw(imagen)
    dibujo.rectangle((5, 5, 762, 762), outline='black', width=8)
    for y in range(32, 730, 24):
        for x in range(32, 730, 24):
            if (x // 24 + y // 24) % 3:
                dibujo.rectangle((x, y, x + 15, y + 15), fill='black')
    dibujo.rectangle((200, 340, 560, 400), fill='white')
    dibujo.text((220, 360), 'PRUEBA - NO ES UN QR BANCARIO', fill='black')
    imagen.save(temporal / 'qr_bancario.png')
    settings.STATIC_ROOT = temporal / 'staticfiles'
    call_command('collectstatic', interactive=False, verbosity=0)
    def estado():
        return [list(m.objects.order_by('pk').values()) for m in (Venta, Caja, MovimientoCaja, Lote)]
    inicial = estado()
    connections.close_all()
    from desktop.servidor import Servidor
    servidor = Servidor(get_wsgi_application(), 0)
    servidor.iniciar()
    informe = {'pantallas': [], 'errores': []}
    try:
        from django.test import Client
        cliente = Client(HTTP_HOST='127.0.0.1')
        cliente.force_login(datos['dueno'])
        pagina = cliente.get('/ventas/nueva/')
        assert pagina.status_code == 200
        assert b'width:100%;height:55vh;object-fit:contain' in pagina.content
        assert cliente.get('/sistema/qr/imagen/').content == (temporal / 'qr_bancario.png').read_bytes()
        for cantidad in (1, 2):
            ruta = '/ventas/carrito/agregar/' if cantidad == 1 else '/ventas/carrito/actualizar/'
            respuesta = cliente.post(ruta, {'presentacion_id': datos['unidad'].pk, 'indice': 0, 'cantidad': cantidad})
            assert respuesta.status_code == 200
            from apps.ventas.carrito import enriquecer_carrito
            assert enriquecer_carrito(cliente.session)['total'] == cantidad * 8
        respuesta = cliente.post('/ventas/confirmar/', {'metodo_id': datos['qr'].pk, 'monto': '16'})
        assert respuesta.status_code == 422
        assert estado() == inicial
        cliente.force_login(datos['vendedor'])
        assert cliente.get('/sistema/qr/').status_code == 403
        assert cliente.get('/sistema/qr/imagen/').status_code == 200
        informe['http_y_permisos'] = True
        informe['sin_operaciones_comerciales_http'] = True
        from apps.core.services import crear_respaldo
        from apps.core.respaldos import recuperar_temporal
        respaldo = crear_respaldo(datos['dueno'])
        recuperado = recuperar_temporal(settings.BACKUP_DIR / respaldo['archivo'], temporal / 'recuperada')
        assert recuperado['qr_restaurado']
        assert (temporal / 'recuperada/qr_bancario.png').read_bytes() == (temporal / 'qr_bancario.png').read_bytes()
        informe['respaldo_y_recuperacion_qr'] = True
        from urllib.request import urlopen
        with urlopen(servidor.url + '/static/js/qr.js') as respuesta:
            assert respuesta.status == 200
            assert respuesta.read() == (RAIZ / 'frontend/static/js/qr.js').read_bytes()
        informe['js_debug_false'] = not settings.DEBUG
        if args.http:
            return 0
        import webview
        ventana = webview.create_window('Validación QR ficticio', servidor.url + '/login/', width=1280, height=800)
        if args.abrir:
            print('Usuario ficticio: dueno_fase8. Clave temporal:', clave, flush=True)
            print('Abra caja, agregue productos y seleccione QR. Cierre la ventana para terminar.', flush=True)
            webview.start(gui='edgechromium', private_mode=False, storage_path=str(temporal / 'webview'))
            return 0
        def esperar(js):
            limite = time.monotonic() + 30
            while time.monotonic() < limite:
                if ventana.evaluate_js(js):
                    return
                time.sleep(.2)
            raise RuntimeError('Tiempo de espera de interfaz: ' + js)
        def recorrido():
            try:
                esperar("!!document.querySelector('[name=username]')")
                ventana.evaluate_js("document.querySelector('[name=username]').value='dueno_fase8'; document.querySelector('[name=password]').value=" + json.dumps(clave) + ";setTimeout(()=>document.querySelector('form').requestSubmit(),0);true")
                esperar("location.pathname === '/'")
                ventana.load_url(servidor.url + '/ventas/nueva/')
                esperar("!!document.querySelector('#lista-pagos .select-metodo') && !!window.bootstrap && !!window.htmx")
                ventana.evaluate_js("setTimeout(()=>htmx.ajax('POST','/ventas/carrito/agregar/',{target:'#carrito',swap:'outerHTML',values:{presentacion_id:" + str(datos['unidad'].pk) + ",cantidad:1}}),0);true")
                esperar("!!document.querySelector('.input-cantidad-linea')")
                for ancho in (1280, 768, 390):
                    ventana.resize(ancho, 800)
                    ventana.evaluate_js("let s=document.querySelector('.select-metodo'); s.value=Array.from(s.options).find(o=>o.dataset.esQr==='1').value;s.dispatchEvent(new Event('change',{bubbles:true}));true")
                    esperar("document.querySelector('#modal-qr').classList.contains('show') && !document.querySelector('#qr-imagen').hidden")
                    time.sleep(.5)
                    prueba = ventana.evaluate_js("(()=>{let i=document.querySelector('#qr-imagen'),r=i.getBoundingClientRect();return {ancho:innerWidth,imagenAncho:r.width,imagenAlto:r.height,natural:i.naturalWidth,completa:getComputedStyle(i).objectFit==='contain',total:document.querySelector('#qr-total').textContent,totalCarrito:document.querySelector('#monto-total-val').textContent,dentro:r.left>=0&&r.right<=innerWidth};})()")
                    assert prueba['completa'] and prueba['dentro'] and prueba['natural'] == 768
                    assert prueba['total'] == prueba['totalCarrito']
                    informe['pantallas'].append(prueba)
                    ventana.evaluate_js("document.querySelector('#modal-qr .btn-close').click();true")
                    esperar("!document.querySelector('#modal-qr').classList.contains('show')")
                ventana.evaluate_js("let c=document.querySelector('.input-cantidad-linea');c.value=2;c.dispatchEvent(new Event('change',{bubbles:true}));true")
                esperar("document.querySelector('#monto-total-val').textContent.trim().startsWith('16')")
                esperar("document.querySelector('#qr-total').textContent === document.querySelector('#monto-total-val').textContent")
                informe['total_actualizado'] = True
                ventana.evaluate_js("let s=document.querySelector('.select-metodo');s.value=Array.from(s.options).find(o=>o.dataset.esQr!=='1').value;s.dispatchEvent(new Event('change',{bubbles:true}));true")
                informe['sin_operaciones_comerciales'] = estado() == inicial
                assert informe['sin_operaciones_comerciales']
            except Exception as exc:
                informe['errores'].append(str(exc))
            finally:
                connections.close_all()
                ventana.destroy()
        webview.start(recorrido, gui='edgechromium', private_mode=False, storage_path=str(temporal / 'webview'))
    except Exception as exc:
        informe['errores'].append(str(exc))
    finally:
        servidor.cerrar()
        informe['protegidos_intactos'] = huellas() == antes
        (temporal / 'resultado.json').write_text(json.dumps(informe, indent=2), encoding='utf-8')
        print(json.dumps(informe, indent=2), flush=True)
        assert informe['protegidos_intactos'], 'Cambió un archivo protegido.'
    return int(bool(informe['errores']) or not informe['protegidos_intactos'] or not informe['pantallas'])


if __name__ == '__main__':
    sys.exit(main())
