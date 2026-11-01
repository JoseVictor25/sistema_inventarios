"""Inventario de recursos locales requeridos por la interfaz."""
from pathlib import Path

# Bibliotecas de terceros que se enlazan desde base.html.
RECURSOS_VENDOR = (
    "vendor/adminlte/css/adminlte.min.css",
    "vendor/adminlte/js/adminlte.min.js",
    "vendor/bootstrap/js/bootstrap.bundle.min.js",
    "vendor/htmx/htmx.min.js",
    "vendor/chartjs/chart.umd.min.js",
    "vendor/tom-select/css/tom-select.bootstrap5.min.css",
    "vendor/tom-select/js/tom-select.complete.min.js",
)

# Recursos propios que deben existir tanto en la fuente como en STATIC_ROOT.
RECURSOS_APP = (
    "css/app.css",
    "js/app.js",
    "js/catalogo.js",
    "js/compras.js",
    "js/pos.js",
    "js/reportes.js",
    "img/favicon.svg",
)

# Todos los recursos obligatorios para una instalación completa.
RECURSOS_FRONTEND = (*RECURSOS_VENDOR, *RECURSOS_APP)


def recursos_faltantes(directorio):
    """Devuelve los recursos obligatorios ausentes en un STATIC_ROOT dado."""
    base = Path(directorio)
    return tuple(ruta for ruta in RECURSOS_FRONTEND if not (base / ruta).is_file())
