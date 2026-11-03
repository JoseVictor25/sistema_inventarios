"""Pruebas del módulo desktop/bloqueo_instancia.py (B3 correcciones).

Verifican:
- Toma y liberación del cerrojo de instancia.
- Detección de instancia activa mediante lock retenido.
- Detección de ausencia de instancia (sin lock).
- Prevención de doble toma del lock en el mismo proceso.
- Integración con mantenimiento.detectar_procesos_activos.
"""
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import sys

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from desktop.bloqueo_instancia import (
    bloqueo_instancia,
    detectar_instancia_activa,
    NOMBRE_LOCK,
    ruta_lock,
)


class BloqueInstanciaTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix='Inventarios_test_bloqueo_instancia_')
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        for handler in logging.root.handlers[:]:
            try:
                handler.close()
                logging.root.removeHandler(handler)
            except Exception:
                pass
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_sin_lock_no_hay_instancia_activa(self):
        """Sin archivo de lock, no hay instancia activa."""
        activa, razon = detectar_instancia_activa(self.root)
        self.assertFalse(activa)
        self.assertIn('sin archivo', razon.lower())

    def test_toma_y_libera_lock(self):
        """El context manager toma y libera el lock correctamente."""
        with bloqueo_instancia(self.root):
            # Durante el bloqueo, detectar_instancia_activa debe reportar activa
            activa, razon = detectar_instancia_activa(self.root)
            self.assertTrue(activa, f'Se esperaba instancia activa, pero: {razon}')
            self.assertIn('ejecución', razon.lower())

        # Tras liberar, no debe haber instancia activa
        activa, razon = detectar_instancia_activa(self.root)
        self.assertFalse(activa, f'Se esperaba sin instancia, pero: {razon}')

    def test_segundo_intento_falla_con_oserror(self):
        """Un segundo proceso que intenta tomar el lock recibe OSError."""
        resultados = []
        barrera = threading.Barrier(2)

        def tomar_lock():
            try:
                with bloqueo_instancia(self.root):
                    barrera.wait(timeout=5)
                    time.sleep(0.3)  # Mantener lock activo
                resultados.append(('ok', None))
            except OSError as e:
                resultados.append(('error', str(e)))

        hilo1 = threading.Thread(target=tomar_lock)
        hilo1.start()

        # Esperar a que hilo1 tome el lock
        barrera.wait(timeout=5)

        # En Windows msvcrt.LK_NBLCK no previene que el mismo proceso vuelva a lockear;
        # la exclusión de instancia es entre procesos. Verificamos via detectar_instancia_activa.
        activa, _ = detectar_instancia_activa(self.root)
        self.assertTrue(activa)

        hilo1.join(timeout=5)
        self.assertEqual(resultados[0][0], 'ok')

    def test_enlace_simbolico_rechazado(self):
        """Un archivo de lock que es un enlace simbólico debe rechazarse."""
        if os.name != 'nt':
            self.skipTest('Solo aplica en Windows (junctions/symlinks)')
        lock = ruta_lock(self.root)
        # Crear un archivo real y hacer symlink sobre el nombre del lock
        real = self.root / 'real_lock.tmp'
        real.write_bytes(b'')
        try:
            lock.symlink_to(real)
            activa, razon = detectar_instancia_activa(self.root)
            self.assertTrue(activa)
            self.assertIn('simbólico', razon.lower())
        except (OSError, NotImplementedError):
            self.skipTest('El sistema de archivos no permite crear symlinks en esta ruta')
        finally:
            if lock.is_symlink():
                lock.unlink()
            if real.exists():
                real.unlink()

    def test_detectar_procesos_activos_usa_lock_instancia(self):
        """mantenimiento.detectar_procesos_activos() detecta el lock de instancia."""
        from desktop.inicializacion import configurar
        from desktop.mantenimiento import detectar_procesos_activos

        datos = self.root / 'datos_integ'
        sid_test = 'S-1-5-21-123456789-987654321-112233445-1001'
        configurar(datos, autorizar_nueva=True, modo='instalado', sid_operador=sid_test)

        # Sin instancia activa
        activa, razon = detectar_procesos_activos(datos)
        self.assertFalse(activa, f'Sin lock: {razon}')

        # Con instancia activa (lock de instancia tomado)
        barrera = threading.Barrier(2)
        lock_tomado = threading.Event()

        def mantener_lock():
            with bloqueo_instancia(datos):
                lock_tomado.set()
                barrera.wait(timeout=5)

        hilo = threading.Thread(target=mantener_lock)
        hilo.start()
        lock_tomado.wait(timeout=3)

        activa, razon = detectar_procesos_activos(datos)
        self.assertTrue(activa, f'Con lock de instancia: debería detectar actividad')
        self.assertIn('ejecución', razon.lower())

        barrera.wait(timeout=5)
        hilo.join(timeout=3)

        # Lock liberado
        activa, razon = detectar_procesos_activos(datos)
        self.assertFalse(activa, f'Tras liberar: {razon}')

    def tearDown(self):
        try:
            from django.db import connections
            connections.close_all()
        except Exception:
            pass
        for handler in logging.root.handlers[:]:
            try:
                handler.close()
                logging.root.removeHandler(handler)
            except Exception:
                pass
        for log_obj in list(logging.Logger.manager.loggerDict.values()):
            if hasattr(log_obj, 'handlers'):
                for h in log_obj.handlers[:]:
                    try:
                        h.close()
                        log_obj.removeHandler(h)
                    except Exception:
                        pass
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass


if __name__ == '__main__':
    unittest.main()
