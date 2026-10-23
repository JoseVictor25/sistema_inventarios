"""Verificación aislada de interfaz mediante las APIs públicas de pywebview.

No es el launcher. No usa objetos COM/WebView2 nativos ni genera capturas.
Los datos y sesiones se aíslan; CSP bloquea recursos externos de las páginas.
El código 0 acredita las comprobaciones automáticas, no la aprobación visual.
"""
import argparse
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from urllib.parse import urlparse, urlencode
from urllib.request import build_opener, HTTPCookieProcessor, Request
from http.cookiejar import CookieJar
from html.parser import HTMLParser
from uuid import uuid4
import secrets
import socket
from wsgiref.simple_server import make_server, WSGIRequestHandler, WSGIServer
from socketserver import ThreadingMixIn

CSP = (
    "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "font-src 'self' data:; connect-src 'self'; frame-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'"
)
INSTRUMENTACION = """<script>
window.documentoFase0 = "__DOCUMENTO__";
window.erroresFase0 = []; window.bloqueosFase0 = [];
addEventListener('error', function(e) {
  erroresFase0.push(e.message || ('Recurso: ' + (e.target.src || e.target.href || e.target.tagName)));
}, true);
addEventListener('unhandledrejection', e => erroresFase0.push(String(e.reason)));
addEventListener('securitypolicyviolation', e => bloqueosFase0.push({
  uri:e.blockedURI, directiva:e.effectiveDirective
}));
</script>"""
SONDEO = """JSON.stringify({
  documento:window.documentoFase0, ruta:location.pathname, titulo:document.title, ancho:innerWidth,
  usuario:document.querySelector(".menu .derecha")?.textContent || "",
  listo:document.readyState,
  desbordamiento:document.documentElement.scrollWidth > innerWidth,
  errores:window.erroresFase0, bloqueos:window.bloqueosFase0,
  bootstrap:typeof bootstrap, adminlte:typeof adminlte, htmx:typeof htmx,
  chart:typeof Chart, tomselect:typeof TomSelect,
  css:Array.from(document.styleSheets).filter(s=>s.href).map(s=>({
    url:s.href, reglas:s.cssRules.length
  })),
  scripts:Array.from(document.scripts).filter(s=>s.src).map(s=>s.src),
  recursos:performance.getEntriesByType('resource').map(r=>r.name)
})"""


def es_externa(url, origen):
    """Compara esquema, host y puerto; no confunde otro servidor local con este."""
    partes = urlparse(url)
    return partes.scheme in ("http", "https") and (partes.scheme, partes.netloc) != (
        urlparse(origen).scheme, urlparse(origen).netloc)


def validar_pagina(datos, ruta, requeridos, ancho=None):
    """Evalúa evidencia de carga; datos ausentes nunca se consideran éxito."""
    errores = []
    if datos.get("ruta") != ruta or datos.get("listo") != "complete":
        errores.append("La navegación no terminó en la página esperada.")
    for nombre in ("bootstrap", "adminlte", "htmx", "chart", "tomselect"):
        if datos.get(nombre, "undefined") == "undefined":
            errores.append(f"Biblioteca no ejecutada: {nombre}")
    if not isinstance(datos.get("errores"), list) or datos.get("errores"):
        errores.append("Falta instrumentación o hay errores JavaScript/recursos.")
    if not isinstance(datos.get("bloqueos"), list) or datos.get("bloqueos"):
        errores.append("Falta instrumentación CSP o hay solicitudes bloqueadas.")
    if datos.get("desbordamiento", True):
        errores.append("Desbordamiento horizontal.")
    if ancho is not None and not ancho * 0.75 <= datos.get("ancho", 0) <= ancho * 1.05:
        errores.append("El tamaño de ventana todavía no coincide con el solicitado.")
    css = datos.get("css", [])
    cargados = {urlparse(s["url"]).path for s in css if s.get("reglas", 0) > 0}
    cargados.update(urlparse(s).path for s in datos.get("scripts", []))
    if not set(requeridos) <= cargados:
        errores.append("Faltan hojas CSS aplicadas o scripts requeridos.")
    return errores


def preparar_base_temporal(carpeta):
    """Migra únicamente el archivo esperado dentro de la carpeta temporal propia."""
    from django.conf import settings
    from django.db import connection, connections
    from django.core.management import call_command
    from django.contrib.auth import get_user_model
    esperada = (Path(carpeta) / "datos_prueba.sqlite3").resolve()
    configurada = Path(settings.DATABASES["default"]["NAME"]).resolve()
    if configurada != esperada or settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
        raise RuntimeError("Se rechazó migrar: la base configurada no es el archivo temporal esperado.")
    if Path(connection.settings_dict["NAME"]).resolve() != esperada:
        raise RuntimeError("Se rechazó migrar: la conexión activa no apunta al archivo temporal.")
    call_command("migrate", interactive=False, verbosity=0)
    Usuario = get_user_model()
    if Usuario._meta.db_table not in connection.introspection.table_names():
        raise RuntimeError("La migración no creó usuarios_usuario en la base temporal.")
    clave = secrets.token_urlsafe(24)
    usuario = Usuario.objects.create_user(username="usuario_prueba", password=clave)
    evidencia = {"archivo_temporal": esperada.name, "tabla_usuario": Usuario._meta.db_table,
                 "tabla_verificada": True, "usuario": usuario.username}
    connections.close_all()
    return clave, evidencia


class TokenCSRF(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.token = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag == "input" and atributos.get("name") == "csrfmiddlewaretoken":
            self.token = atributos.get("value")


def comprobar_http(origen, clave, recursos, directorio_static):
    """Autenticación real sobre el servidor y su conexión SQLite, sin navegador."""
    cliente = build_opener(HTTPCookieProcessor(CookieJar()))
    def obtener(ruta, datos=None):
        peticion = Request(origen + ruta, data=urlencode(datos).encode() if datos is not None else None,
                           headers={"Referer": origen + ruta})
        with cliente.open(peticion, timeout=15) as respuesta:
            return respuesta.geturl(), respuesta.read(), respuesta.status
    direccion = urlparse(origen)
    # Reproduce una preconexión de Chromium: otra petición debe poder avanzar.
    with socket.create_connection((direccion.hostname, direccion.port), timeout=5):
        url, html, _ = obtener("/")
    if urlparse(url).path != "/login/":
        raise RuntimeError("Inicio permite acceso anónimo o no redirige a login.")
    token = TokenCSRF(html.decode()).token
    if not token:
        raise RuntimeError("Login no entregó token CSRF.")
    url, html, estado = obtener("/login/", {"username": "usuario_prueba", "password": clave,
                                           "csrfmiddlewaretoken": token})
    if estado != 200 or urlparse(url).path != "/" or b"usuario_prueba" not in html:
        raise RuntimeError("El login HTTP del usuario temporal no abrió inicio.")
    token = TokenCSRF(html.decode()).token
    verificados = []
    for recurso in recursos:
        _, contenido, estado = obtener("/static/" + recurso)
        if estado != 200 or contenido != (directorio_static / recurso).read_bytes():
            raise RuntimeError(f"Recurso ausente o desactualizado: {recurso}. Ejecuta collectstatic.")
        verificados.append(recurso)
    url, _, _ = obtener("/logout/", {"csrfmiddlewaretoken": token})
    if urlparse(url).path != "/login/" or urlparse(obtener("/")[0]).path != "/login/":
        raise RuntimeError("Logout no cerró la sesión temporal.")
    return {"aprobada": True, "conexion_anticipada": True, "login": True, "inicio": True, "logout": True,
            "recursos_verificados": verificados}


def esperar_documento(ventana, ruta, anterior, requeridos, ancho, espera, cancelado):
    """No acepta documentos anteriores ni toma loaded como garantía de recursos listos."""
    limite = time.monotonic() + espera
    ultimo = {}
    error_sondeo = None
    while not cancelado.is_set() and time.monotonic() < limite:
        if not ventana.events.loaded.wait(0.1):
            continue
        try:
            ultimo = json.loads(ventana.evaluate_js(SONDEO))
            nuevo = ultimo.get("documento") and ultimo["documento"] != anterior
            if nuevo and not validar_pagina(ultimo, ruta, requeridos, ancho):
                return ultimo
        except Exception as error:
            # El puente JS puede estar reiniciándose durante una navegación.
            error_sondeo = str(error)
        cancelado.wait(0.1)
    if not ultimo:
        raise RuntimeError(
            f"Tiempo de espera en {ruta} ({ancho}px): no se pudo obtener un documento "
            f"desde WebView2. No se evaluaron las bibliotecas ni el diseño. Sondeo: {error_sondeo}"
        )
    detalle = validar_pagina(ultimo, ruta, requeridos, ancho)
    if ultimo.get("documento") == anterior:
        detalle.append("No se recibió un documento nuevo.")
    raise RuntimeError(f"Tiempo de espera en {ruta} ({ancho}px): {detalle}; sondeo={error_sondeo}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", required=True, type=Path)
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--solo-http", action="store_true", help="Prueba sin GUI; no acredita interfaz ni JS.")
    parser.add_argument("--espera", type=int, default=30)
    parser.add_argument("--pausa", type=float, default=2)
    args = parser.parse_args()
    if not 1 <= args.espera <= 180 or not 0 <= args.pausa <= 60:
        parser.error("Usa espera entre 1 y 180, y pausa entre 0 y 60 segundos.")
    args.salida.mkdir(parents=True, exist_ok=True)
    raiz = Path(__file__).resolve().parent.parent
    temporal = tempfile.TemporaryDirectory(prefix="inventarios_webview_", ignore_cleanup_errors=True)
    os.environ.update({
        "DJANGO_SETTINGS_MODULE": "config.settings.desarrollo",
        "ENV_FILE": str(Path(temporal.name) / "sin_env"),
        "SECRET_KEY": secrets.token_urlsafe(48),
        "DATA_DIR": temporal.name, "DB_PATH": str(Path(temporal.name) / "datos_prueba.sqlite3"),
        "LOG_DIR": str(Path(temporal.name) / "logs"),
        "BACKUP_DIR": str(Path(temporal.name) / "respaldos"),
        "NOMBRE_NEGOCIO": "Tienda de prueba", "ALLOWED_HOSTS": "127.0.0.1,localhost",
        "DEBUG": "False",
    })
    sys.path.insert(0, str(raiz / "backend"))
    reporte = {"paginas": [], "solicitudes": [], "respuestas": [], "http_local": [],
               "externas_detectadas": [], "errores": [], "base_temporal": {}, "autenticacion_http": {},
               "autenticacion_navegador": False, "automatizacion_aprobada": False, "avisos_transporte": [],
               "revision_visual": "Pendiente de revisión humana; no se generan capturas."}
    bloqueo = threading.Lock()
    terminado, trabajo_terminado = threading.Event(), threading.Event()
    servidor, hilo_servidor = None, None
    try:
        import django
        django.setup()
        from django.conf import settings
        from django.core.wsgi import get_wsgi_application
        from django.db import connections
        from apps.core.frontend import RECURSOS_FRONTEND
        clave, reporte["base_temporal"] = preparar_base_temporal(temporal.name)
        aplicacion = get_wsgi_application()
        recursos = (*RECURSOS_FRONTEND, "css/app.css", "js/app.js", "img/favicon.svg")
        requeridos = ["/static/" + r for r in recursos if r.endswith((".css", ".js"))]

        def sitio(environ, start_response):
            cabecera = {}
            def capturar(estado, headers, exc_info=None):
                cabecera.update(estado=estado, headers=headers)
            iterable = aplicacion(environ, capturar)
            try:
                contenido = b"".join(iterable)
            finally:
                if hasattr(iterable, "close"):
                    iterable.close()
            headers = cabecera["headers"]
            if any(k.lower() == "content-type" and "text/html" in v for k, v in headers):
                script = INSTRUMENTACION.replace("__DOCUMENTO__", uuid4().hex).encode()
                contenido = contenido.replace(b"<head>", b"<head>" + script, 1)
                headers = [(k, v) for k, v in headers if k.lower() not in ("content-length", "content-security-policy")]
                headers += [("Content-Security-Policy", CSP), ("Content-Length", str(len(contenido))),
                            ("Cache-Control", "no-store")]
            with bloqueo:
                reporte["http_local"].append({"ruta": environ["PATH_INFO"], "metodo": environ["REQUEST_METHOD"],
                                             "estado": int(cabecera["estado"].split()[0])})
            start_response(cabecera["estado"], headers)
            return [contenido]

        class Silencioso(WSGIRequestHandler):
            def setup(self):
                self.request.settimeout(5)
                super().setup()

            def handle(self):
                try:
                    super().handle()
                except (ConnectionError, TimeoutError) as error:
                    with bloqueo:
                        reporte["avisos_transporte"].append(type(error).__name__)

            def log_message(self, *args):
                pass

        class ServidorPrueba(ThreadingMixIn, WSGIServer):
            # Chromium puede abrir conexiones anticipadas sin enviar aún una petición.
            # Cada conexión tiene su hilo y su conexión SQLite al mismo archivo temporal.
            def process_request_thread(self, request, client_address):
                try:
                    super().process_request_thread(request, client_address)
                finally:
                    connections.close_all()

        servidor = make_server("127.0.0.1", 0, sitio, server_class=ServidorPrueba, handler_class=Silencioso)
        def servir():
            try:
                servidor.serve_forever()
            finally:
                connections.close_all()
        hilo_servidor = threading.Thread(target=servir, daemon=True)
        hilo_servidor.start()
        origen = f"http://127.0.0.1:{servidor.server_port}"
        reporte["autenticacion_http"] = comprobar_http(origen, clave, recursos, settings.FRONTEND_DIR / "static")
        print("Base temporal migrada; login, inicio, logout y 10 recursos HTTP correctos.", flush=True)
        if not args.solo_http:
            import webview
            ventana = webview.create_window("Verificación fase 0 — no interactuar durante el recorrido",
                                            url=origen + "/login/", width=1280, height=800,
                                            hidden=not args.visible)
            def solicitud(request):
                with bloqueo:
                    reporte["solicitudes"].append(request.url)
                    if es_externa(request.url, origen):
                        reporte["externas_detectadas"].append(request.url)
            def respuesta(response):
                with bloqueo:
                    reporte["respuestas"].append({"url": response.url, "estado": response.status_code})
            ventana.events.request_sent += solicitud
            ventana.events.response_received += respuesta

            def comprobar():
                ultimo = None
                try:
                    # GET de cada escenario; POST real de login entre las dos páginas.
                    for pagina, ruta in (("login", "/login/"), ("inicio", "/")):
                        for ancho in (1280, 390):
                            ventana.restore()
                            ventana.resize(ancho, 800)
                            ventana.load_url(origen + ruta + "?verificacion=" + uuid4().hex)
                            datos = esperar_documento(ventana, ruta, ultimo, requeridos, ancho, args.espera, terminado)
                            ultimo = datos["documento"]
                            if pagina == "inicio" and "usuario_prueba" not in datos.get("usuario", ""):
                                raise RuntimeError("Inicio no muestra al usuario autenticado temporal.")
                            if terminado.wait(args.pausa):
                                raise RuntimeError("Ventana cerrada antes de terminar.")
                            # Volver a inspeccionar tras la pausa para detectar errores tardíos.
                            datos = json.loads(ventana.evaluate_js(SONDEO))
                            datos.update(pagina=pagina, ancho_solicitado=ancho)
                            datos["fallos"] = validar_pagina(datos, ruta, requeridos, ancho)
                            with bloqueo:
                                reporte["paginas"].append(datos)
                                reporte["externas_detectadas"].extend(u for u in datos.get("recursos", []) if es_externa(u, origen))
                            if datos["fallos"]:
                                raise RuntimeError(str(datos["fallos"]))
                            print(f"{pagina} {ancho}: comprobaciones automáticas correctas", flush=True)
                        if pagina == "login":
                            # Programar envío después de retornar al puente público de pywebview.
                            ventana.evaluate_js("document.querySelector('[name=username]').value='usuario_prueba';"
                                + "document.querySelector('[name=password]').value=" + json.dumps(clave) + ";"
                                + "setTimeout(()=>document.querySelector('form').requestSubmit(),0); true")
                            datos = esperar_documento(ventana, "/", ultimo, requeridos, 390, args.espera, terminado)
                            if "usuario_prueba" not in datos.get("usuario", ""):
                                raise RuntimeError("Login del navegador no autenticó al usuario temporal.")
                            ultimo = datos["documento"]
                    ventana.evaluate_js("setTimeout(()=>document.querySelector('form[action=\"/logout/\"]').requestSubmit(),0); true")
                    datos = esperar_documento(ventana, "/login/", ultimo, requeridos, 390, args.espera, terminado)
                    ultimo = datos["documento"]
                    ventana.load_url(origen + "/")
                    esperar_documento(ventana, "/login/", ultimo, requeridos, 390, args.espera, terminado)
                    reporte["autenticacion_navegador"] = True
                except Exception as error:
                    with bloqueo:
                        reporte["errores"].append(f"{type(error).__name__}: {error}")
                finally:
                    terminado.set()
                    try:
                        if not ventana.events.closed.is_set():
                            ventana.destroy()
                    except Exception as error:
                        reporte["errores"].append(f"Cierre: {error}")
                    trabajo_terminado.set()
            def al_cerrar():
                terminado.set()
            ventana.events.closed += al_cerrar
            webview.start(comprobar, gui="edgechromium", private_mode=False,
                          storage_path=str(Path(temporal.name) / "webview"))
            terminado.set()
            if not trabajo_terminado.wait(25):
                reporte["errores"].append("El hilo de verificación no terminó tras cerrar la ventana.")
    except Exception as error:
        reporte["errores"].append(f"Inicio: {type(error).__name__}: {error}")
    finally:
        if servidor:
            servidor.shutdown()
            servidor.server_close()
        if hilo_servidor:
            hilo_servidor.join(5)
        with bloqueo:
            http_ok = bool(reporte["autenticacion_http"].get("aprobada")) and not reporte["errores"]
            http_ok = http_ok and all(r["estado"] < 400 for r in reporte["http_local"])
            reporte["automatizacion_aprobada"] = (
                not args.solo_http and http_ok and reporte["autenticacion_navegador"]
                and len(reporte["paginas"]) == 4 and not reporte["externas_detectadas"]
                and all(not p["fallos"] for p in reporte["paginas"])
                and all(r["estado"] < 400 for r in reporte["respuestas"])
            )
            reporte["solo_http_aprobado"] = bool(args.solo_http and http_ok)
            (args.salida / "resultado.json").write_text(json.dumps(reporte, indent=2, ensure_ascii=False), encoding="utf-8")
        if "django.db" in sys.modules:
            from django.db import connections
            connections.close_all()
        logging.shutdown()
        temporal.cleanup()
    print(json.dumps({k: reporte[k] for k in ("automatizacion_aprobada", "solo_http_aprobado", "errores", "revision_visual")}, ensure_ascii=True))
    return 0 if reporte["automatizacion_aprobada"] or reporte["solo_http_aprobado"] else 1


if __name__ == "__main__":
    sys.exit(main())
