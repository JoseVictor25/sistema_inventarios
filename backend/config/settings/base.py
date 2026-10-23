"""Configuración común a desarrollo y producción.

Todos los valores que cambian según el equipo o el entorno (clave secreta,
rutas, puertos, reglas del negocio) se leen del archivo .env. Ver
backend/.env.example para la lista completa.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# backend/config/settings/base.py -> BASE_DIR = backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BASE_DIR.parent
FRONTEND_DIR = ROOT_DIR / "frontend"

# --- Lectura del archivo .env ------------------------------------------------
# En desarrollo: backend/.env. En el programa instalado, el launcher define
# ENV_FILE apuntando a C:\ProgramData\SistemaInventarios\.env
ENV_FILE = Path(os.environ.get("ENV_FILE", BASE_DIR / ".env"))
load_dotenv(ENV_FILE)


def env_str(nombre, por_defecto=None):
    """Lee una variable de texto. Si no existe y no hay valor por defecto, falla."""
    valor = os.environ.get(nombre, por_defecto)
    if valor is None or not str(valor).strip():
        raise RuntimeError(
            f"Falta la variable de entorno {nombre}. Revisa tu archivo {ENV_FILE}."
        )
    return valor


def env_bool(nombre, por_defecto=False):
    """Lee una variable booleana: acepta true/1/si/yes (sin importar mayúsculas)."""
    valor = os.environ.get(nombre)
    if valor is None:
        return por_defecto
    normalizado = valor.strip().lower()
    if normalizado in {"true", "1", "si", "sí", "yes"}:
        return True
    if normalizado in {"false", "0", "no"}:
        return False
    raise RuntimeError(f"La variable {nombre} debe ser booleana. Revisa {ENV_FILE}.")


def env_int(nombre, por_defecto, minimo=None, maximo=None):
    """Lee una variable entera y avisa con un mensaje claro si no lo es."""
    valor = os.environ.get(nombre, str(por_defecto))
    try:
        numero = int(valor)
    except ValueError:
        raise RuntimeError(f"La variable {nombre} debe ser un número entero. Revisa {ENV_FILE}.") from None
    if (minimo is not None and numero < minimo) or (maximo is not None and numero > maximo):
        raise RuntimeError(f"La variable {nombre} está fuera del rango permitido ({minimo}, {maximo}). Revisa {ENV_FILE}.")
    return numero


def env_lista(nombre, por_defecto=""):
    """Lee una lista separada por comas: 'a,b,c' -> ['a', 'b', 'c']."""
    return [x.strip() for x in os.environ.get(nombre, por_defecto).split(",") if x.strip()]


# --- Seguridad ---------------------------------------------------------------
SECRET_KEY = env_str("SECRET_KEY")  # obligatoria: no hay valor por defecto
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_lista("ALLOWED_HOSTS", "localhost,127.0.0.1")

# --- Rutas de datos ----------------------------------------------------------
DATA_DIR = Path(env_str("DATA_DIR", BASE_DIR / "datos"))
DB_PATH = Path(env_str("DB_PATH", DATA_DIR / "db.sqlite3"))
BACKUP_DIR = Path(env_str("BACKUP_DIR", DATA_DIR / "respaldos"))
LOG_DIR = Path(env_str("LOG_DIR", DATA_DIR / "logs"))
for carpeta in (DATA_DIR, BACKUP_DIR, LOG_DIR):
    carpeta.mkdir(parents=True, exist_ok=True)

# --- Reglas del negocio configurables ----------------------------------------
NOMBRE_NEGOCIO = env_str("NOMBRE_NEGOCIO", "Mi tienda")
MONEDA_SIMBOLO = env_str("MONEDA_SIMBOLO", "Bs")
DIAS_ALERTA_VENCIMIENTO = env_int("DIAS_ALERTA_VENCIMIENTO", 30, minimo=0)
STOCK_MINIMO_DEFECTO = env_int("STOCK_MINIMO_DEFECTO", 5, minimo=0)
BACKUP_CONSERVAR = env_int("BACKUP_CONSERVAR", 30, minimo=1)

# --- Aplicaciones ------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Apps del negocio (una por área)
    "apps.core",
    "apps.usuarios",
    "apps.catalogo",
    "apps.compras",
    "apps.inventario",
    "apps.ventas",
    "apps.caja",
    "apps.reportes",
    "apps.auditoria",
]

AUTH_USER_MODEL = "usuarios.Usuario"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # El HTML vive en la carpeta frontend/, fuera de backend/
        "DIRS": [FRONTEND_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Variables disponibles en TODAS las plantillas (nombre del
                # negocio, símbolo de moneda). Se crea en apps/core/context_processors.py
                "apps.core.context_processors.datos_del_negocio",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DB_PATH,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# --- Idioma y hora -----------------------------------------------------------
LANGUAGE_CODE = env_str("LANGUAGE_CODE", "es")
TIME_ZONE = env_str("TIME_ZONE", "America/La_Paz")
USE_I18N = True
USE_TZ = True

# --- Archivos estáticos (frontend/static) -------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [FRONTEND_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Sesión y acceso ---------------------------------------------------------
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 60 * 60 * 8, minimo=1)  # 8 horas
LOGIN_URL = "usuarios:login"
LOGIN_REDIRECT_URL = "core:inicio"
LOGOUT_REDIRECT_URL = "usuarios:login"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Registro de eventos (logs) ----------------------------------------------
LOG_LEVEL = env_str("LOG_LEVEL", "INFO").strip().upper()
if LOG_LEVEL not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
    raise RuntimeError(f"La variable LOG_LEVEL no es válida. Revisa {ENV_FILE}.")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{asctime} [{levelname}] {name}: {message}", "style": "{"},
    },
    "handlers": {
        "consola": {"class": "logging.StreamHandler", "formatter": "simple"},
        "archivo": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "sistema.log",
            "maxBytes": 1_000_000,
            "backupCount": 4,  # archivo activo + cuatro históricos = cinco archivos
            "encoding": "utf-8",
            "formatter": "simple",
        },
    },
    "root": {"handlers": ["consola", "archivo"], "level": LOG_LEVEL},
}
