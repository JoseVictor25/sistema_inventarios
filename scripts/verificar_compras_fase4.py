"""Verifica la Fase 4 (Compras y Lotes) con SQLite temporal: --pruebas, --http o --abrir.

No lee .env ni conecta a la base del negocio. Conserva evidencia en una carpeta
nueva de TEMP. --abrir mantiene el servidor hasta Ctrl+C.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

RAIZ = Path(__file__).resolve().parent.parent


def preparar_entorno(temporal):
    env = os.environ.copy()
    env.update({
        "ENV_FILE": str(temporal / "sin_env"),
        "SECRET_KEY": secrets.token_urlsafe(48),
        "DATA_DIR": str(temporal / "datos"),
        "DB_PATH": str(temporal / "aislada.sqlite3"),
        "LOG_DIR": str(temporal / "logs"),
        "BACKUP_DIR": str(temporal / "respaldos"),
        "DEBUG": "False",
        "ALLOWED_HOSTS": "127.0.0.1,localhost,testserver",
        "NOMBRE_NEGOCIO": "Pruebas de compras (Fase 4)",
        "PYTHONIOENCODING": "utf-8",
        "DJANGO_SETTINGS_MODULE": "settings_fase4",
        "PYTHONPATH": os.pathsep.join([str(temporal), str(RAIZ / "backend"), str(RAIZ / "scripts")]),
    })
    (temporal / "settings_fase4.py").write_text(
        "from config.settings.desarrollo import *\n"
        f"DATABASES['default']['TEST'] = {{'NAME': {str(temporal / 'tests.sqlite3')!r}}}\n"
        "WHITENOISE_USE_FINDERS = True\n",
        encoding="utf-8",
    )
    return env


def recorrido_http(temporal, abrir):
    from decimal import Decimal
    from http.cookiejar import CookieJar
    import threading
    from urllib.error import HTTPError
    from urllib.parse import urlencode, urlparse
    from urllib.request import HTTPCookieProcessor, Request, build_opener
    from wsgiref.simple_server import WSGIRequestHandler, make_server

    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.core.wsgi import get_wsgi_application
    from django.db import connections

    from apps.catalogo import services as cat_services
    from apps.compras import services as compras_services
    from apps.core.frontend import RECURSOS_FRONTEND
    from apps.usuarios.models import Rol, Usuario
    from verificar_interfaz_fase0 import TokenCSRF

    esperado = (temporal / "aislada.sqlite3").resolve()
    if Path(settings.DATABASES["default"]["NAME"]).resolve() != esperado:
        raise RuntimeError("Se rechazó una base distinta de la temporal.")

    call_command("migrate", verbosity=0, interactive=False)
    call_command("cargar_datos_iniciales", verbosity=0)

    clave = secrets.token_urlsafe(24)
    dueno = Usuario.objects.create_user("dueno_fase4", password=clave, rol=Rol.objects.get(nombre="Dueño"))
    Usuario.objects.create_user("vendedor_fase4", password=clave, rol=Rol.objects.get(nombre="Vendedor"))

    # Datos sintéticos en la base temporal
    categoria = cat_services.guardar_categoria(dueno, {"nombre": "Insumos Temporales"})
    producto = cat_services.crear_producto(dueno, {
        "codigo": "INS-F4",
        "nombre": "Materia Prima F4",
        "categoria": categoria,
        "descripcion": "Datos exclusivos de prueba temporal.",
        "stock_minimo": 5,
    }, [{"nombre": "Unidad", "unidades_equivalentes": 1, "precio_venta": Decimal("15.00")}])

    proveedor = compras_services.guardar_proveedor(dueno, {
        "nombre": "Proveedor Temporal F4",
        "tipo": "EMPRESA",
    })

    compra = compras_services.registrar_compra(dueno, proveedor, [{
        "producto": producto,
        "cantidad": 10,
        "costo_unitario": Decimal("8.50"),
        "fecha_vencimiento": None,
    }], observacion="Compra sintética inicial")

    conexiones = []
    app = get_wsgi_application()

    def sitio(environ, start_response):
        def responder(status, headers, exc_info=None):
            conexiones.append({
                "ruta": environ["PATH_INFO"],
                "metodo": environ["REQUEST_METHOD"],
                "estado": int(status[:3]),
            })
            return start_response(status, headers, exc_info)
        return app(environ, responder)

    class Silencioso(WSGIRequestHandler):
        def log_message(self, *args):
            pass

    servidor = make_server("127.0.0.1", 0, sitio, handler_class=Silencioso)

    def atender():
        try:
            servidor.serve_forever()
        finally:
            connections.close_all()

    hilo = threading.Thread(target=atender, daemon=True)
    hilo.start()
    origen = f"http://127.0.0.1:{servidor.server_port}"

    paginas = [
        "/compras/",
        "/compras/nueva/",
        "/compras/nueva/linea/",
        f"/compras/{compra.pk}/",
        "/compras/proveedores/",
        "/compras/proveedores/nuevo/",
        f"/compras/proveedores/{proveedor.pk}/editar/",
    ]

    def pedir(cliente, ruta, datos=None):
        solicitud = Request(origen + ruta, data=urlencode(datos).encode() if datos is not None else None)
        try:
            respuesta = cliente.open(solicitud, timeout=15)
        except HTTPError as error:
            respuesta = error
        with respuesta:
            return respuesta.status, urlparse(respuesta.geturl()).path, respuesta.read()

    def login(nombre):
        cliente = build_opener(HTTPCookieProcessor(CookieJar()))
        token = TokenCSRF(pedir(cliente, "/login/")[2].decode()).token
        estado, ruta, _ = pedir(cliente, "/login/", {"username": nombre, "password": clave, "csrfmiddlewaretoken": token})
        if estado != 200 or ruta != "/":
            raise RuntimeError("Falló el login temporal.")
        return cliente

    informe = {"visual": "Pendiente de inspección humana", "javascript": "No evaluado por HTTP", "http": conexiones}
    try:
        cliente = login("dueno_fase4")
        for ruta in paginas:
            estado, final, html = pedir(cliente, ruta)
            if estado != 200 or (final != ruta and not final.startswith(ruta)) or b"https://" in html or b"http://" in html:
                raise RuntimeError(f"Página inválida: {ruta}, HTTP {estado}")

        recursos_fase4 = (*RECURSOS_FRONTEND, "css/app.css", "js/app.js", "js/catalogo.js", "js/compras.js", "img/favicon.svg")
        for recurso in recursos_fase4:
            estado, _, datos = pedir(cliente, "/static/" + recurso)
            if estado != 200 or datos != (RAIZ / "frontend/static" / recurso).read_bytes():
                raise RuntimeError(f"Recurso incorrecto: {recurso}")

        vendedor = login("vendedor_fase4")
        for ruta in paginas:
            if pedir(vendedor, ruta)[0] != 403:
                raise RuntimeError(f"Vendedor obtuvo acceso a {ruta}")

        informe["aprobado_http"] = True
        print(f"HTTP: {len(paginas)} pantallas, {len(recursos_fase4)} recursos locales y denegación al Vendedor verificados exitosamente.", flush=True)

        if abrir:
            import webbrowser
            print(f"Revisión manual: {origen}/login/", flush=True)
            print(f"Usuarios TEMPORALES: dueno_fase4 / vendedor_fase4. Clave: {clave}", flush=True)
            print("Revisa compras y proveedores a 1280x800 y 390x844. Ctrl+C finaliza.", flush=True)
            webbrowser.open(origen + "/login/")
            try:
                threading.Event().wait()
            except KeyboardInterrupt:
                pass
    finally:
        servidor.shutdown()
        servidor.server_close()
        hilo.join(timeout=5)
        connections.close_all()
        (temporal / "http.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pruebas", action="store_true")
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--abrir", action="store_true")
    args = parser.parse_args()
    if not any((args.pruebas, args.http, args.abrir)):
        parser.error("Elige --pruebas, --http o --abrir.")
    if Path(sys.executable).resolve() != (RAIZ / "venv/Scripts/python.exe").resolve():
        parser.error("Utiliza exclusivamente venv/Scripts/python.exe.")

    temporal = Path(tempfile.mkdtemp(prefix="Inventarios_verificacion_fase4_"))
    env = preparar_entorno(temporal)
    print(f"Evidencia y datos aislados: {temporal}", flush=True)
    resultados = {}

    if args.pruebas:
        comandos = {
            "check": ["manage.py", "check"],
            "makemigrations": ["manage.py", "makemigrations", "--check", "--dry-run"],
            "test": ["manage.py", "test", "--noinput"],
            "frontend": [str(RAIZ / "scripts/preparar_frontend.py"), "--verificar"],
        }
        for nombre, comando in comandos.items():
            with (temporal / f"{nombre}.txt").open("w", encoding="utf-8") as salida:
                resultado = subprocess.run(
                    [sys.executable, *comando],
                    cwd=RAIZ / "backend",
                    env=env,
                    stdout=salida,
                    stderr=subprocess.STDOUT,
                )
            resultados[nombre] = resultado.returncode
            if nombre == "test" and "Ran 0 tests" in (temporal / "test.txt").read_text(encoding="utf-8"):
                resultados[nombre] = 1
            print(f"{nombre}: código {resultados[nombre]}", flush=True)

    if args.http or args.abrir:
        os.environ.update(env)
        sys.path[:0] = [str(temporal), str(RAIZ / "backend"), str(RAIZ / "scripts")]
        recorrido_http(temporal, args.abrir)

    (temporal / "resultados.json").write_text(json.dumps(resultados, indent=2), encoding="utf-8")
    return int(any(resultados.values()))


if __name__ == "__main__":
    sys.exit(main())
