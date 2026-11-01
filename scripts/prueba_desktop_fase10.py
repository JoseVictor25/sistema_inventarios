"""Proceso de prueba de producción, exclusivamente bajo TEMP."""
import hashlib
from http.cookiejar import CookieJar
import json
from pathlib import Path
import socket
import sys
from urllib.request import build_opener, HTTPCookieProcessor
from urllib.parse import urlencode

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from desktop.inicializacion import configurar
from desktop.rutas import validar_temporal
from verificar_interfaz_fase0 import TokenCSRF


def main():
    ruta = validar_temporal(sys.argv[1])
    configurar(ruta, autorizar_nueva=True)
    from django.conf import settings
    from django.core.management import call_command
    from django.core.wsgi import get_wsgi_application
    from django.db import connections
    from apps.core.primer_uso import habilitar
    from apps.core.respaldos import crear_copia, verificar_copia, _bloqueo, ErrorRespaldo
    from desktop.servidor import Servidor
    settings.STATIC_ROOT = ruta / 'staticfiles'
    call_command('collectstatic', interactive=False, verbosity=0)
    assert not settings.DEBUG
    huella = hashlib.sha256((ruta / '.env').read_bytes()).hexdigest()
    evidencia = ruta / 'prueba.json'
    segunda = evidencia.exists()
    if segunda:
        assert json.loads(evidencia.read_text())['configuracion'] == huella
    token = habilitar()
    assert bool(token) != segunda
    with _bloqueo(ruta):
        try:
            with _bloqueo(ruta):
                raise AssertionError('Se permitió otra instancia')
        except ErrorRespaldo:
            pass
    ocupado = socket.socket()
    ocupado.bind(('127.0.0.1', 0))
    ocupado.listen()
    puerto = ocupado.getsockname()[1]
    servidor = Servidor(get_wsgi_application(), puerto)
    try:
        assert int(servidor.servidor.effective_port) != puerto
        servidor.iniciar()
        cliente = build_opener(HTTPCookieProcessor(CookieJar()))
        def pedir(ruta_http, datos=None):
            with cliente.open(servidor.url + ruta_http, data=urlencode(datos).encode() if datos else None, timeout=15) as r:
                assert r.status == 200
                return r.read().decode()
        if token:
            html = pedir('/configuracion-inicial/')
            datos = dict(autorizacion=token, username='dueno_prueba',
                password1='Temporal-Desktop-2026!', password2='Temporal-Desktop-2026!', csrfmiddlewaretoken=TokenCSRF(html).token)
            from concurrent.futures import ThreadPoolExecutor
            from urllib.error import HTTPError
            def registrar(_):
                try:
                    pedir('/configuracion-inicial/', datos)
                    return 200
                except HTTPError as error:
                    estado = error.code
                    error.close()
                    return estado
            with ThreadPoolExecutor(max_workers=2) as ejecutor:
                assert sorted(ejecutor.map(registrar, range(2))) == [200, 403]
        html = pedir('/login/')
        pedir('/login/', dict(username='dueno_prueba', password='Temporal-Desktop-2026!', csrfmiddlewaretoken=TokenCSRF(html).token))
        for url in ('/', '/inventario/', '/compras/', '/ventas/', '/caja/', '/reportes/', '/auditoria/', '/sistema/respaldos/'):
            pedir(url)
        from apps.core.frontend import RECURSOS_FRONTEND
        for recurso in RECURSOS_FRONTEND:
            pedir('/static/' + recurso)
        resultado = crear_copia(settings.DB_PATH, settings.BACKUP_DIR, settings.BACKUP_CONSERVAR)
        verificar_copia(Path(settings.BACKUP_DIR) / resultado['archivo'])
    finally:
        servidor.cerrar()
        ocupado.close()
        connections.close_all()
    assert not servidor.hilo.is_alive(), 'El hilo de Waitress no terminó'
    comprobacion = socket.socket()
    try:
        assert comprobacion.connect_ex(('127.0.0.1', int(servidor.servidor.effective_port))) != 0
    finally:
        comprobacion.close()
    evidencia.write_text(json.dumps(dict(configuracion=huella, segunda_ejecucion=segunda, aprobado=True)), encoding='utf-8')
    print('Escritorio HTTP aislado aprobado; segunda ejecución:', segunda)


if __name__ == '__main__':
    main()
