"""Recorrido HTTP real de fase 2 con SQLite temporal y revisión manual opcional.

--abrir conserva el servidor hasta Ctrl+C y abre el navegador para revisión humana.
El resultado HTTP nunca acredita revisión visual ni ejecución de JavaScript.
"""
import argparse
import hashlib
from http.cookiejar import CookieJar
import json
import logging
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, HTTPCookieProcessor
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler
from socketserver import ThreadingMixIn

from verificar_interfaz_fase0 import TokenCSRF, preparar_base_temporal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--abrir", action="store_true")
    args = parser.parse_args()
    args.salida.mkdir(parents=True, exist_ok=True)
    archivo = args.salida / "resultado_http_fase2.json"
    if archivo.exists():
        parser.error("La salida ya contiene un resultado; usa otra carpeta para conservarlo.")
    raiz = Path(__file__).resolve().parent.parent
    protegidos = [raiz / p for p in (
        "backend/.env", "backend/datos/db.sqlite3",
        "backend/REPORTE_MIGRACIONES_FASE1.md", "backend/SOLUCION_ERROR_TERMINAL.md")]
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in protegidos if p.exists()}
    reporte = {"http": [], "comprobaciones": [], "errores": [], "recursos": [],
               "rutas": {}, "referencias_externas_html": [], "funcional_aprobado": False,
               "revision_visual": "No evaluada automáticamente", "javascript": "No evaluado por HTTP"}
    servidor = None
    with tempfile.TemporaryDirectory(prefix="inventarios_usuarios_fase2_", ignore_cleanup_errors=True) as temporal:
        os.environ.update({
            "DJANGO_SETTINGS_MODULE": "config.settings.desarrollo", "ENV_FILE": str(Path(temporal) / "sin_env"),
            "SECRET_KEY": secrets.token_urlsafe(48), "DATA_DIR": temporal,
            "DB_PATH": str(Path(temporal) / "datos_prueba.sqlite3"),
            "LOG_DIR": str(Path(temporal) / "logs"), "BACKUP_DIR": str(Path(temporal) / "respaldos"),
            "DEBUG": "False", "ALLOWED_HOSTS": "127.0.0.1,localhost", "NOMBRE_NEGOCIO": "Tienda de prueba fase 2",
        })
        sys.path.insert(0, str(raiz / "backend"))
        try:
            import django
            django.setup()
            from django.conf import settings
            from django.core.management import call_command
            from django.core.wsgi import get_wsgi_application
            from django.db import connections
            from django.urls import reverse, resolve
            from apps.usuarios.models import Usuario, Rol, Permiso
            from apps.core.frontend import RECURSOS_FRONTEND
            preparar_base_temporal(temporal)
            call_command("cargar_datos_iniciales", verbosity=0)
            clave = secrets.token_urlsafe(24)
            dueno = Usuario.objects.create_user(username="dueno_visual", password=clave, rol=Rol.objects.get(nombre="Dueño"))
            vendedor = Usuario.objects.create_user(username="vendedor_visual", password=clave, rol=Rol.objects.get(nombre="Vendedor"))
            connections.close_all()
            reporte["base"] = {"temporal": True, "tabla_usuario": "usuarios_usuario"}
            esperado = {"usuarios:lista": "/usuarios/", "usuarios:usuario_crear": "/usuarios/nuevo/",
                        "usuarios:usuario_editar": f"/usuarios/{vendedor.pk}/editar/", "usuarios:rol_lista": "/usuarios/roles/"}
            for nombre, ruta in esperado.items():
                assert reverse(nombre, args=[vendedor.pk] if nombre.endswith("editar") else None) == ruta
                assert resolve(ruta).view_name == nombre
                reporte["rutas"][nombre] = ruta
            app = get_wsgi_application()

            def sitio(environ, start_response):
                def inicio(status, headers, exc_info=None):
                    reporte["http"].append({"ruta": environ["PATH_INFO"], "metodo": environ["REQUEST_METHOD"], "estado": int(status[:3])})
                    return start_response(status, headers, exc_info)
                return app(environ, inicio)

            class Servidor(ThreadingMixIn, WSGIServer):
                daemon_threads = True

                def process_request_thread(self, request, address):
                    try:
                        super().process_request_thread(request, address)
                    finally:
                        connections.close_all()

            class Silencioso(WSGIRequestHandler):
                def setup(self):
                    self.request.settimeout(5)
                    super().setup()

                def log_message(self, *args):
                    pass

            servidor = make_server("127.0.0.1", 0, sitio, server_class=Servidor, handler_class=Silencioso)
            hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
            hilo.start()
            origen = f"http://127.0.0.1:{servidor.server_port}"

            def cliente():
                return build_opener(HTTPCookieProcessor(CookieJar()))

            def pedir(c, ruta, datos=None):
                req = Request(origen + ruta, data=urlencode(datos).encode() if datos is not None else None,
                              headers={"Referer": origen + ruta})
                try:
                    respuesta = c.open(req, timeout=15)
                except HTTPError as error:
                    respuesta = error
                with respuesta:
                    return respuesta.status, urlparse(respuesta.geturl()).path, respuesta.read()

            def post(c, ruta, datos):
                status, _, html = pedir(c, ruta)
                assert status == 200, (ruta, status)
                token = TokenCSRF(html.decode()).token
                assert token, "Falta CSRF"
                return pedir(c, ruta, {**datos, "csrfmiddlewaretoken": token})

            def login(nombre):
                c = cliente()
                status, ruta, _ = post(c, "/login/", {"username": nombre, "password": clave})
                assert status == 200 and ruta == "/", "Login falló"
                return c

            def ok(nombre):
                reporte["comprobaciones"].append(nombre)

            anonimo = cliente()
            for ruta in esperado.values():
                assert pedir(anonimo, ruta)[1] == "/login/"
            ok("Anónimo redirigido en las cuatro rutas")
            c = login(dueno.username)
            for ruta in esperado.values():
                status, final, html = pedir(c, ruta)
                assert status == 200 and final == ruta
                assert b' href="/usuarios/"' in html and b' href="/usuarios/roles/"' in html
                assert b"vendor/adminlte/css/adminlte.min.css" in html
                assert b"https://" not in html and b"http://" not in html
            ok("Dueño: listado, alta, edición, matriz y menú; HTML sin referencias externas")
            datos = dict(username="alta_visual", first_name="Ana", last_name="Prueba",
                         rol=vendedor.rol_id, is_active="on", password1=clave, password2=clave)
            status, ruta, _ = post(c, "/usuarios/nuevo/", datos)
            assert status == 200 and ruta == "/usuarios/"
            nuevo = Usuario.objects.get(username="alta_visual")
            assert nuevo.check_password(clave) and nuevo.rol_id == vendedor.rol_id and not nuevo.is_staff
            ok("Creación mediante POST real con CSRF y contraseña hash")
            ruta_editar = f"/usuarios/{nuevo.pk}/editar/"
            edit = dict(username=nuevo.username, first_name="Ana editada", last_name="Prueba", rol=dueno.rol_id)
            assert post(c, ruta_editar, edit)[1] == "/usuarios/"
            nuevo.refresh_from_db()
            assert not nuevo.is_active and nuevo.rol_id == dueno.rol_id and nuevo.first_name == "Ana editada"
            prueba = cliente()
            assert post(prueba, "/login/", {"username": nuevo.username, "password": clave})[1] == "/login/"
            ok("Edición, asignación de Dueño y desactivación; login inactivo rechazado")
            edit.update(is_active="on", rol=vendedor.rol_id)
            assert post(c, ruta_editar, edit)[1] == "/usuarios/"
            nuevo.refresh_from_db()
            assert nuevo.is_active and nuevo.rol_id == vendedor.rol_id
            login(nuevo.username)
            ok("Reactivación, asignación de Vendedor y login posterior")
            html = pedir(c, "/usuarios/roles/")[2].decode()
            assert Permiso.objects.count() == 12 and Rol.objects.count() == 2
            assert all(p in html for p in Permiso.objects.values_list("codigo", flat=True))
            ok("Matriz con los 12 permisos y los dos roles existentes")
            v = login(vendedor.username)
            inicio = pedir(v, "/")[2]
            assert b'href="/usuarios/"' not in inicio and b'href="/usuarios/roles/"' not in inicio
            token = TokenCSRF(inicio.decode()).token
            for ruta in esperado.values():
                assert pedir(v, ruta)[0] == 403
                assert pedir(v, ruta, {"csrfmiddlewaretoken": token})[0] == 403
            ok("Vendedor: menú oculto y 403 en GET/POST directo de las cuatro rutas con CSRF válido")
            recursos = (*RECURSOS_FRONTEND, "css/app.css", "js/app.js", "img/favicon.svg")
            for recurso in recursos:
                status, _, contenido = pedir(c, "/static/" + recurso)
                assert status == 200 and contenido == (settings.FRONTEND_DIR / "static" / recurso).read_bytes()
                reporte["recursos"].append(recurso)
            ok("Diez recursos locales disponibles, contenido idéntico al archivo de origen")
            assert not any(r["estado"] in (404, 500) for r in reporte["http"])
            reporte["funcional_aprobado"] = True
            print("Recorrido HTTP aprobado con SQLite temporal.", flush=True)
            if args.abrir:
                import webbrowser
                print(f"Revisión MANUAL: {origen}/login/", flush=True)
                print(f"Cuentas temporales: dueno_visual / vendedor_visual. Clave temporal: {clave}", flush=True)
                print("Revisar listado, alta, edición y matriz a 1280x800 y 390x844; F12 para errores/red. Ctrl+C termina.", flush=True)
                webbrowser.open(origen + "/login/")
                try:
                    threading.Event().wait()
                except KeyboardInterrupt:
                    pass
        except Exception as error:
            reporte["errores"].append(f"{type(error).__name__}: {error}")
        finally:
            if servidor:
                servidor.shutdown()
                servidor.server_close()
            if "django.db" in sys.modules:
                from django.db import connections
                connections.close_all()
            logging.shutdown()
            reporte["protegidos_sin_cambios"] = all(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in hashes.items())
            reporte["funcional_aprobado"] = (reporte["funcional_aprobado"] and reporte["protegidos_sin_cambios"]
                                              and not reporte["errores"] and not any(r["estado"] >= 500 for r in reporte["http"]))
            archivo.write_text(json.dumps(reporte, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: reporte[k] for k in ("funcional_aprobado", "protegidos_sin_cambios", "errores", "revision_visual")}, ensure_ascii=True))
    return 0 if reporte["funcional_aprobado"] else 1


if __name__ == "__main__":
    sys.exit(main())
