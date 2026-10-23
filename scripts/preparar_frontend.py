"""Descarga de desarrollo; la aplicación nunca necesita conexión a internet.

Uso: python scripts/preparar_frontend.py [--verificar]
No sustituye archivos existentes distintos: revisar antes de actualizar versiones.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
from urllib.request import urlopen

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "frontend" / "static" / "vendor"
# Versiones fijadas, sin resolver "latest". Conservar licencias originales.
PAQUETES = (
    ("admin-lte", "4.0.2", "adminlte", {
        "dist/css/adminlte.min.css": "css/adminlte.min.css",
        "dist/js/adminlte.min.js": "js/adminlte.min.js", "LICENSE": "LICENSE"}),
    ("bootstrap", "5.3.8", "bootstrap", {
        "dist/js/bootstrap.bundle.min.js": "js/bootstrap.bundle.min.js", "LICENSE": "LICENSE"}),
    ("htmx.org", "2.0.8", "htmx", {"dist/htmx.min.js": "htmx.min.js", "LICENSE": "LICENSE"}),
    ("chart.js", "4.5.1", "chartjs", {"dist/chart.umd.min.js": "chart.umd.min.js", "LICENSE.md": "LICENSE.md"}),
    ("tom-select", "2.4.3", "tom-select", {
        "dist/css/tom-select.bootstrap5.min.css": "css/tom-select.bootstrap5.min.css",
        "dist/js/tom-select.complete.min.js": "js/tom-select.complete.min.js", "LICENSE": "LICENSE"}),
)


def descargar(url):
    """Descarga únicamente por HTTPS con tiempo de espera limitado."""
    if not url.startswith("https://"):
        raise ValueError("Se requiere HTTPS para descargar recursos.")
    with urlopen(url, timeout=30) as respuesta:
        return respuesta.read()


def preparar():
    """Valida todos los paquetes en memoria antes de escribir recursos nuevos."""
    pendientes = {}
    registro = []
    for nombre, version, carpeta, archivos in PAQUETES:
        url = f"https://registry.npmjs.org/{nombre}/{version}"
        datos = json.loads(descargar(url))
        if datos["version"] != version or datos.get("license") not in ("MIT", "0BSD", "Apache-2.0"):
            raise ValueError(f"Revisar versión/licencia de {nombre} antes de continuar.")
        contenido = descargar(datos["dist"]["tarball"])
        algoritmo, esperado = datos["dist"]["integrity"].split("-", 1)
        real = base64.b64encode(hashlib.new(algoritmo, contenido).digest()).decode()
        if real != esperado:
            raise ValueError(f"Integridad inválida: {nombre}")
        with tarfile.open(fileobj=io.BytesIO(contenido), mode="r:gz") as archivo:
            for origen, destino in archivos.items():
                miembro = archivo.getmember("package/" + origen)
                if not miembro.isfile():
                    raise ValueError(f"Recurso inválido: {origen}")
                recurso = archivo.extractfile(miembro).read()
                ruta = DESTINO / carpeta / destino
                if ruta.exists() and ruta.read_bytes() != recurso:
                    raise ValueError(f"No se sobrescribe un recurso existente distinto: {ruta}")
                pendientes[ruta] = recurso
        registro.append({"paquete": nombre, "version": version, "licencia": datos["license"],
                         "origen": url, "integridad": datos["dist"]["integrity"]})
    for ruta, contenido in pendientes.items():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)
    manifiesto = {"paquetes": registro, "archivos": {
        str(ruta.relative_to(DESTINO)).replace("\\", "/"): hashlib.sha256(contenido).hexdigest()
        for ruta, contenido in pendientes.items()}}
    (DESTINO / "manifest.json").write_text(json.dumps(manifiesto, indent=2), encoding="utf-8")
    print("Recursos y licencias guardados localmente.")


def verificar():
    """Comprueba presencia e integridad sin conexión."""
    manifiesto = DESTINO / "manifest.json"
    if not manifiesto.exists():
        raise ValueError("Faltan los recursos locales: ejecutar preparar_frontend.py con conexión.")
    datos = json.loads(manifiesto.read_text(encoding="utf-8"))
    esperados = {f"{carpeta}/{destino}" for _, _, carpeta, archivos in PAQUETES
                 for destino in archivos.values()}
    if set(datos["archivos"]) != esperados:
        raise ValueError("El manifiesto no contiene el conjunto exacto de recursos requeridos.")
    for ruta, esperado in datos["archivos"].items():
        archivo = DESTINO / ruta
        if not archivo.is_file() or hashlib.sha256(archivo.read_bytes()).hexdigest() != esperado:
            raise ValueError(f"Recurso ausente o alterado: {ruta}")
    print("Integridad de recursos locales correcta.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verificar", action="store_true")
    args = parser.parse_args()
    try:
        verificar() if args.verificar else preparar()
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        parser.exit(1, f"No se completó la preparación: {error}\n")
