"""Producción (programa instalado). El launcher define ENV_FILE apuntando al
.env de C:\\ProgramData\\SistemaInventarios\\ y DATA_DIR en ese mismo lugar,
para que la base y los respaldos sobrevivan a actualizaciones y desinstalación."""
from .base import *  # noqa

DEBUG = False  # nunca activo en el programa instalado
