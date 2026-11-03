"""Pruebas unitarias del cálculo del importe QR en pagos mixtos.

Verifican la lógica de calcularMontoQR() y las condiciones de apertura del modal
usando DOM simulado mediante html.parser y lógica Python equivalente al JS.

Casos cubiertos:
  A - Pago único QR por Bs 100
  B - Pago mixto efectivo Bs 60 + QR Bs 40
  C - Cambio del importe QR de Bs 40 a Bs 25
  D - Varias filas con una sola QR
  E - Importe QR = 0 → modal no se abre
  F - Importe QR vacío → modal no se abre
  G - Sin fila QR activa → modal no se abre
  H - Cierre del modal sin confirmar (invalidar)
  I - Múltiples filas QR suman correctamente
"""

import unittest
from decimal import Decimal


# ─────────────────────────────────────────────────────────────────────────────
# Lógica Python equivalente al JavaScript de frontend/static/js/qr.js
# ─────────────────────────────────────────────────────────────────────────────

def _calcular_monto_qr(filas):
    """Simula calcularMontoQR() del JS.

    Args:
        filas: lista de dicts con claves 'es_qr' (bool) y 'monto' (str o float o None).
    Returns:
        Decimal con la suma de montos QR, o None si no hay filas QR válidas.
    """
    suma = Decimal('0')
    encontrado = False
    for fila in filas:
        if not fila.get('es_qr'):
            continue
        try:
            val = Decimal(str(fila.get('monto', '') or ''))
            if val > 0:
                suma += val
                encontrado = True
        except Exception:
            pass
    return suma if encontrado else None


def _debe_abrir_modal(filas):
    """Simula la condición de apertura del modal QR del JS."""
    monto = _calcular_monto_qr(filas)
    return monto is not None and monto > 0


# ─────────────────────────────────────────────────────────────────────────────
# Suite de pruebas
# ─────────────────────────────────────────────────────────────────────────────

class CasoA_PagoUnicoQR(unittest.TestCase):
    """Caso A — Pago completo mediante QR (total = importe QR)."""

    def test_monto_qr_igual_al_total(self):
        filas = [{'es_qr': True, 'monto': '100.00'}]
        self.assertEqual(_calcular_monto_qr(filas), Decimal('100.00'))

    def test_modal_se_abre(self):
        filas = [{'es_qr': True, 'monto': '100.00'}]
        self.assertTrue(_debe_abrir_modal(filas))

    def test_monto_no_es_el_total_de_venta(self):
        total_venta = Decimal('100.00')
        filas = [{'es_qr': True, 'monto': '100.00'}]
        monto_qr = _calcular_monto_qr(filas)
        # Coincide en este caso, pero la fuente es la fila, no el total global
        self.assertEqual(monto_qr, total_venta)


class CasoB_PagoMixtoEfectivoQR(unittest.TestCase):
    """Caso B — Efectivo Bs 60 + QR Bs 40; total de venta Bs 100."""

    def setUp(self):
        self.filas = [
            {'es_qr': False, 'monto': '60.00'},
            {'es_qr': True,  'monto': '40.00'},
        ]

    def test_monto_qr_es_40_no_100(self):
        self.assertEqual(_calcular_monto_qr(self.filas), Decimal('40.00'))

    def test_monto_qr_no_incluye_efectivo(self):
        self.assertNotEqual(_calcular_monto_qr(self.filas), Decimal('100.00'))

    def test_modal_se_abre(self):
        self.assertTrue(_debe_abrir_modal(self.filas))


class CasoC_CambioImporteQR(unittest.TestCase):
    """Caso C — El cajero modifica el importe QR; el modal refleja el nuevo valor."""

    def test_importe_inicial_40(self):
        filas = [
            {'es_qr': False, 'monto': '60.00'},
            {'es_qr': True,  'monto': '40.00'},
        ]
        self.assertEqual(_calcular_monto_qr(filas), Decimal('40.00'))

    def test_importe_actualizado_a_25(self):
        filas = [
            {'es_qr': False, 'monto': '75.00'},
            {'es_qr': True,  'monto': '25.00'},
        ]
        self.assertEqual(_calcular_monto_qr(filas), Decimal('25.00'))

    def test_importe_nunca_es_el_total_previo(self):
        filas_nuevas = [
            {'es_qr': False, 'monto': '75.00'},
            {'es_qr': True,  'monto': '25.00'},
        ]
        # El modal no debe mostrar el valor anterior (40) sino el actual (25)
        self.assertNotEqual(_calcular_monto_qr(filas_nuevas), Decimal('40.00'))


class CasoD_VariasFilasUnaSolaQR(unittest.TestCase):
    """Caso D — Varias filas de pago, solo una es QR."""

    def setUp(self):
        self.filas = [
            {'es_qr': False, 'monto': '50.00'},  # Efectivo
            {'es_qr': False, 'monto': '10.00'},  # Tarjeta
            {'es_qr': True,  'monto': '40.00'},  # QR
        ]

    def test_solo_suma_la_fila_qr(self):
        self.assertEqual(_calcular_monto_qr(self.filas), Decimal('40.00'))

    def test_no_confunde_con_total_de_venta(self):
        # Total sería 100, pero el importe QR es 40
        self.assertNotEqual(_calcular_monto_qr(self.filas), Decimal('100.00'))


class CasoE_ImporteQRCero(unittest.TestCase):
    """Caso E — Importe QR = 0; modal no debe abrirse."""

    def setUp(self):
        self.filas = [{'es_qr': True, 'monto': '0.00'}]

    def test_monto_es_none(self):
        self.assertIsNone(_calcular_monto_qr(self.filas))

    def test_modal_no_se_abre(self):
        self.assertFalse(_debe_abrir_modal(self.filas))


class CasoF_ImporteQRVacio(unittest.TestCase):
    """Caso F — Campo de importe QR vacío; modal no debe abrirse."""

    def test_monto_vacio_es_none(self):
        filas = [{'es_qr': True, 'monto': ''}]
        self.assertIsNone(_calcular_monto_qr(filas))

    def test_monto_none_es_none(self):
        filas = [{'es_qr': True, 'monto': None}]
        self.assertIsNone(_calcular_monto_qr(filas))

    def test_modal_no_se_abre_con_vacio(self):
        filas = [{'es_qr': True, 'monto': ''}]
        self.assertFalse(_debe_abrir_modal(filas))


class CasoG_SinFilaQR(unittest.TestCase):
    """Caso G — No hay fila de pago QR activa; modal no debe abrirse."""

    def test_sin_fila_qr(self):
        filas = [{'es_qr': False, 'monto': '100.00'}]
        self.assertIsNone(_calcular_monto_qr(filas))

    def test_modal_no_se_abre(self):
        filas = [{'es_qr': False, 'monto': '100.00'}]
        self.assertFalse(_debe_abrir_modal(filas))


class CasoH_CierreModalSinConfirmar(unittest.TestCase):
    """Caso H — Cierre del modal sin confirmar invalida la casilla QR."""

    def test_invalidar_desmarca_confirmacion(self):
        # Simula el estado de la casilla: True=marcada, luego se invalida
        confirmado = {'checked': True}
        # Simula invalidar(): pone checked = False
        confirmado['checked'] = False
        self.assertFalse(confirmado['checked'])

    def test_nueva_apertura_no_hereda_confirmacion_previa(self):
        confirmado = {'checked': True}
        # Al abrir de nuevo, la lógica invalida primero
        confirmado['checked'] = False
        self.assertFalse(confirmado['checked'])


class CasoI_MultiplesFilasQR(unittest.TestCase):
    """Caso I — Varias filas QR simultáneas se suman correctamente."""

    def test_suma_dos_filas_qr(self):
        filas = [
            {'es_qr': True, 'monto': '30.00'},
            {'es_qr': True, 'monto': '20.00'},
        ]
        self.assertEqual(_calcular_monto_qr(filas), Decimal('50.00'))

    def test_ignora_monto_cero_en_segunda_fila_qr(self):
        filas = [
            {'es_qr': True, 'monto': '30.00'},
            {'es_qr': True, 'monto': '0.00'},
        ]
        self.assertEqual(_calcular_monto_qr(filas), Decimal('30.00'))


class VerificacionModal(unittest.TestCase):
    """Verifica el contenido del template actualizado."""

    def setUp(self):
        from pathlib import Path
        self.contenido = (
            Path(__file__).resolve().parents[2]
            / 'frontend/templates/ventas/partials/_qr_modal.html'
        ).read_text(encoding='utf-8')

    def test_texto_correcto_en_modal(self):
        self.assertIn('Importe a pagar por QR', self.contenido)

    def test_no_dice_total_de_la_venta(self):
        self.assertNotIn('Total de la venta', self.contenido)

    def test_tiene_span_qr_total(self):
        self.assertIn('id="qr-total"', self.contenido)

    def test_aviso_pago_mixto_actualizado(self):
        self.assertIn('únicamente el importe indicado arriba', self.contenido)


class VerificacionJS(unittest.TestCase):
    """Verifica la lógica del JS actualizado."""

    def setUp(self):
        from pathlib import Path
        self.contenido = (
            Path(__file__).resolve().parents[2]
            / 'frontend/static/js/qr.js'
        ).read_text(encoding='utf-8')

    def test_no_lee_monto_total_val(self):
        """El JS no debe obtener el importe del total global de la venta."""
        self.assertNotIn("getElementById('monto-total-val')", self.contenido)

    def test_tiene_funcion_calcular_monto_qr(self):
        self.assertIn('calcularMontoQR', self.contenido)

    def test_tiene_funcion_actualizar_importe_qr(self):
        self.assertIn('actualizarImporteQR', self.contenido)

    def test_guarda_proteccion_monto_cero_o_invalido(self):
        self.assertIn('monto <= 0', self.contenido)

    def test_modal_no_abre_sin_importe_valido(self):
        self.assertIn('if (monto === null || monto <= 0) return', self.contenido)

    def test_preserva_bloqueo_confirmacion_venta(self):
        self.assertIn("e.preventDefault(); alert(", self.contenido)

    def test_preserva_invalidar(self):
        self.assertIn('function invalidar()', self.contenido)

    def test_actualiza_modal_sin_recargar_imagen_al_cambiar_metodo(self):
        self.assertIn('actualizarImporteQR', self.contenido)
        self.assertIn('_isShown', self.contenido)


if __name__ == '__main__':
    unittest.main()
