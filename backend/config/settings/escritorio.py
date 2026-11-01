"""Producción empaquetada; el launcher fija rutas antes de importar Django."""
from .produccion import *

RECURSOS_ESCRITORIO = Path(os.environ['DESKTOP_RESOURCES'])
FRONTEND_DIR = RECURSOS_ESCRITORIO / 'frontend'
TEMPLATES[0]['DIRS'] = [FRONTEND_DIR / 'templates']
STATICFILES_DIRS = [FRONTEND_DIR / 'static']
STATIC_ROOT = Path(os.environ.get('DESKTOP_STATIC_ROOT', RECURSOS_ESCRITORIO / 'backend/staticfiles'))
WHITENOISE_USE_FINDERS = False
