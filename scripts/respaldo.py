"""Copia de seguridad de la base SQLite. Se puede programar con el
Programador de tareas de Windows (una vez al día).

Lee las rutas del archivo .env (DB_PATH, DATA_DIR, BACKUP_DIR, BACKUP_CONSERVAR).

Uso:  python scripts/respaldo.py [carpeta_destino] [cantidad_a_conservar]
"""
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(Path(os.environ.get("ENV_FILE", RAIZ / "backend" / ".env")))

DATA_DIR = Path(os.environ.get("DATA_DIR", RAIZ / "backend" / "datos"))
ORIGEN = Path(os.environ.get("DB_PATH", DATA_DIR / "db.sqlite3"))
DESTINO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    os.environ.get("BACKUP_DIR", DATA_DIR / "respaldos")
)
CONSERVAR = int(sys.argv[2]) if len(sys.argv) > 2 else int(
    os.environ.get("BACKUP_CONSERVAR", 30)
)


def main():
    if not ORIGEN.exists():
        sys.exit(f"No se encontró la base de datos: {ORIGEN}")
    DESTINO.mkdir(parents=True, exist_ok=True)
    nombre = DESTINO / f"respaldo_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"
    # API de respaldo de SQLite: segura aunque el sistema esté en uso
    origen = sqlite3.connect(ORIGEN)
    copia = sqlite3.connect(nombre)
    with copia:
        origen.backup(copia)
    origen.close()
    copia.close()
    print(f"Respaldo creado: {nombre}")
    viejos = sorted(DESTINO.glob("respaldo_*.sqlite3"))[:-CONSERVAR]
    for v in viejos:
        v.unlink()
        print(f"Eliminado respaldo antiguo: {v.name}")


if __name__ == "__main__":
    main()
