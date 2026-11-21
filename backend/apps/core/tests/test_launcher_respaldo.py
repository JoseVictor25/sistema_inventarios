"""La política de cierre se prueba con carpeta temporal y fechas controladas."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from desktop.launcher import _respaldo_cierre_vencido


class RespaldoCierreLauncherTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='launcher_respaldo_')
        self.addCleanup(self.temp.cleanup)
        self.settings = SimpleNamespace(BACKUP_DIR=Path(self.temp.name), BACKUP_HORAS_MIN_CIERRE=6)
        self.ahora = datetime(2026, 5, 20, 12, tzinfo=timezone.utc)

    @patch('apps.core.respaldos.listar_copias')
    def test_cierre_omite_respaldo_si_el_ultimo_tiene_menos_de_seis_horas(self, listar):
        listar.return_value = [{'verificado': True,
            'fecha': (self.ahora - timedelta(hours=5, minutes=59)).isoformat()}]
        self.assertFalse(_respaldo_cierre_vencido(self.settings, ahora=self.ahora))

    @patch('apps.core.respaldos.listar_copias')
    def test_cierre_crea_respaldo_si_el_ultimo_supera_seis_horas(self, listar):
        listar.return_value = [{'verificado': True,
            'fecha': (self.ahora - timedelta(hours=6, seconds=1)).isoformat()}]
        self.assertTrue(_respaldo_cierre_vencido(self.settings, ahora=self.ahora))
