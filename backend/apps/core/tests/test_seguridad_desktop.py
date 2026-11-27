"""Pruebas de seguridad del módulo desktop.seguridad."""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

from django.test import SimpleTestCase
from unittest import skipUnless

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from desktop import seguridad


@skipUnless(os.name == 'nt', 'Prueba específica de permisos Windows')
class VerificarDirectorioSeguroTests(SimpleTestCase):

    def test_rechaza_directorio_si_falla_inspeccion_de_icacls(self):
        with tempfile.TemporaryDirectory(prefix='seguridad_desktop_') as temporal:
            resultado_inspeccion = {
                'seguro': False,
                'salida': '',
                'tiene_inseguros': False,
            }

            with patch.object(
                seguridad,
                'inspeccionar_permisos_icacls',
                return_value=resultado_inspeccion,
            ):
                with self.assertRaises(PermissionError):
                    seguridad.verificar_directorio_seguro(
                        Path(temporal)
                    )



class IdentidadOperadorTests(SimpleTestCase):

    SID_ORIGINAL = 'S-1-5-21-111-222-333-1001'
    SID_NUEVO = 'S-1-5-21-111-222-333-1002'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='identidad_operador_')
        self.addCleanup(self.temp.cleanup)
        self.directorio = Path(self.temp.name)

    def test_registrar_rechaza_un_segundo_sid_diferente(self):
        seguridad.registrar_operador(
            self.directorio, self.SID_ORIGINAL, cuenta='OperadorPrueba'
        )

        with self.assertRaises(ValueError):
            seguridad.registrar_operador(
                self.directorio, self.SID_NUEVO, cuenta='OtroOperador'
            )

        registro = seguridad.leer_registro_operador(self.directorio)
        self.assertEqual(registro['sid'], self.SID_ORIGINAL)

    def test_validar_rechaza_un_sid_no_autorizado(self):
        seguridad.registrar_operador(
            self.directorio, self.SID_ORIGINAL, cuenta='OperadorPrueba'
        )

        with self.assertRaises(PermissionError):
            seguridad.validar_operador(
                self.directorio, sid_actual=self.SID_NUEVO
            )

    def test_migrar_rechaza_sin_autorizacion_administrativa(self):
        seguridad.registrar_operador(
            self.directorio, self.SID_ORIGINAL, cuenta='OperadorPrueba'
        )

        with self.assertRaises(PermissionError):
            seguridad.migrar_operador(
                self.directorio,
                self.SID_NUEVO,
                nuevo_cuenta='NuevoOperador',
                autorizacion_admin=False,
            )

        registro = seguridad.leer_registro_operador(self.directorio)
        self.assertEqual(registro['sid'], self.SID_ORIGINAL)

    def test_migrar_autorizado_conserva_historial(self):
        seguridad.registrar_operador(
            self.directorio, self.SID_ORIGINAL, cuenta='OperadorPrueba'
        )

        resultado = seguridad.migrar_operador(
            self.directorio,
            self.SID_NUEVO,
            nuevo_cuenta='NuevoOperador',
            autorizacion_admin=True,
        )

        self.assertEqual(resultado['sid'], self.SID_NUEVO)
        self.assertEqual(len(resultado['historial_migraciones']), 1)
        evento = resultado['historial_migraciones'][0]
        self.assertEqual(evento['sid_anterior'], self.SID_ORIGINAL)
        self.assertEqual(evento['sid_nuevo'], self.SID_NUEVO)

        bitacora = self.directorio / 'logs' / 'migracion_operador.log'
        self.assertTrue(bitacora.is_file())


class GenerarComandosIcaclsTests(SimpleTestCase):

    def test_genera_secuencia_esperada_sin_ejecutar_icacls(self):
        sid_operador = 'S-1-5-21-111-222-333-1001'

        with tempfile.TemporaryDirectory(prefix='icacls_prueba_') as temporal:
            directorio = Path(temporal)
            comandos = seguridad.generar_comandos_icacls(
                directorio, sid_operador
            )

            ruta = str(directorio.resolve())

            self.assertEqual(len(comandos), 4)
            self.assertEqual(
                comandos[0],
                ['icacls', ruta, '/inheritance:r'],
            )
            self.assertEqual(
                comandos[1],
                [
                    'icacls', ruta, '/grant:r',
                    f'*{seguridad.SID_SYSTEM}:(OI)(CI)F',
                    f'*{seguridad.SID_ADMINISTRADORES}:(OI)(CI)F',
                ],
            )
            self.assertEqual(
                comandos[2],
                [
                    'icacls', ruta, '/grant:r',
                    f'*{sid_operador}:(OI)(CI)F',
                ],
            )
            self.assertEqual(
                comandos[3],
                [
                    'icacls', ruta, '/remove:g',
                    f'*{seguridad.SID_USERS}',
                    f'*{seguridad.SID_AUTHENTICATED_USERS}',
                    f'*{seguridad.SID_EVERYONE}',
                ],
            )


@skipUnless(os.name == 'nt', 'Prueba específica de permisos Windows')
class AplicarPermisosSegurosTests(SimpleTestCase):

    SID_OPERADOR = 'S-1-5-21-111-222-333-1001'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aplicar_acl_')
        self.addCleanup(self.temp.cleanup)
        self.directorio = Path(self.temp.name)
        seguridad.registrar_operador(
            self.directorio,
            self.SID_OPERADOR,
            cuenta='OperadorPrueba',
        )

    def resultado_icacls(self, codigo=0):
        return type(
            'ResultadoIcacls',
            (),
            {'returncode': codigo, 'stdout': '', 'stderr': 'error simulado'},
        )()

    def test_exito_registra_acl_aplicadas(self):
        with patch.object(
            seguridad.subprocess,
            'run',
            return_value=self.resultado_icacls(0),
        ) as ejecutar:
            resultado = seguridad.aplicar_permisos_seguros(
                self.directorio, self.SID_OPERADOR
            )

        self.assertTrue(resultado)
        self.assertEqual(ejecutar.call_count, 4)

        registro = seguridad.leer_registro_operador(self.directorio)
        self.assertTrue(registro['acl_aplicadas'])
        self.assertIn('acl_fecha', registro)

    def test_fallo_de_comando_principal_no_registra_acl(self):
        respuestas = [
            self.resultado_icacls(0),
            self.resultado_icacls(1),
            self.resultado_icacls(0),
            self.resultado_icacls(0),
        ]

        with patch.object(
            seguridad.subprocess,
            'run',
            side_effect=respuestas,
        ):
            resultado = seguridad.aplicar_permisos_seguros(
                self.directorio, self.SID_OPERADOR
            )

        self.assertFalse(resultado)
        registro = seguridad.leer_registro_operador(self.directorio)
        self.assertNotIn('acl_aplicadas', registro)

    ''' def test_fallo_de_remove_es_no_critico(self):
        respuestas = [
            self.resultado_icacls(0),
            self.resultado_icacls(0),
            self.resultado_icacls(0),
            self.resultado_icacls(1),
        ]

        with patch.object(
            seguridad.subprocess,
            'run',
            side_effect=respuestas,
        ):
            resultado = seguridad.aplicar_permisos_seguros(
                self.directorio, self.SID_OPERADOR
            )

        self.assertTrue(resultado)
        registro = seguridad.leer_registro_operador(self.directorio)
        self.assertTrue(registro['acl_aplicadas']) 
     '''
    def test_fallo_de_remove_no_registra_acl(self):
            respuestas = [
            self.resultado_icacls(0),
            self.resultado_icacls(0),
            self.resultado_icacls(0),
            self.resultado_icacls(1),
        ]

            with patch.object(
            seguridad.subprocess,
            'run',
            side_effect=respuestas,
            ) as ejecutar:
             resultado = seguridad.aplicar_permisos_seguros(
                self.directorio, self.SID_OPERADOR
            )

            self.assertFalse(resultado)
            self.assertEqual(ejecutar.call_count, 4)
            registro = seguridad.leer_registro_operador(self.directorio)
            self.assertNotIn('acl_aplicadas', registro)
     
     
    def test_solo_nuevo_omite_acl_ya_aplicadas_al_mismo_sid(self):
        archivo = self.directorio / 'operador.json'
        registro = seguridad.leer_registro_operador(self.directorio)
        registro['acl_aplicadas'] = True

        import json
        archivo.write_text(
            json.dumps(registro),
            encoding='utf-8',
        )

        with patch.object(seguridad.subprocess, 'run') as ejecutar:
            resultado = seguridad.aplicar_permisos_seguros(
                self.directorio,
                self.SID_OPERADOR,
                solo_nuevo=True,
            )

        self.assertTrue(resultado)
        ejecutar.assert_not_called()

class ConfigurarModoTests(SimpleTestCase):

    def test_modo_temporal_no_se_clasifica_como_instalado(self):
        from desktop import inicializacion

        with tempfile.TemporaryDirectory(prefix='modo_temporal_') as temporal:
            ruta = Path(temporal) / 'datos'

            with patch.object(
                inicializacion,
                '_validar_ruta',
                return_value=ruta,
            ), patch.object(
                inicializacion,
                'validar_datos_instalados',
            ) as validar_datos, patch.object(
                inicializacion,
                'verificar_directorio_seguro',
            ) as verificar, patch.object(
                inicializacion,
                'validar_operador',
            ) as validar:

                with self.assertRaisesRegex(
                    ValueError,
                    'Instalación nueva: requiere --inicializar.',
                ):
                    inicializacion.configurar(
                        ruta,
                        autorizar_nueva=False,
                        modo='temporal',
                    )

                validar_datos.assert_not_called()
                verificar.assert_not_called()
                validar.assert_not_called()

    def test_modo_instalado_activa_validaciones_de_seguridad(self):
        from desktop import inicializacion

        with tempfile.TemporaryDirectory(prefix='modo_instalado_') as temporal:
            ruta = Path(temporal) / 'datos'
            ruta.mkdir()

            (ruta / 'db.sqlite3').touch()
            (ruta / '.env').write_text(
                'SECRET_KEY=' + ('A' * 60) + '\n',
                encoding='utf-8',
            )

            with patch.object(
                inicializacion,
                '_validar_ruta',
                return_value=ruta,
            ), patch.object(
                inicializacion,
                'verificar_directorio_seguro',
                side_effect=ValueError(
                    'Validación de seguridad simulada.'
                ),
            ) as verificar:

                with self.assertRaisesRegex(
                    ValueError,
                    'Validación de seguridad simulada.',
                ):
                    inicializacion.configurar(
                        ruta,
                        modo='instalado',
                    )

                verificar.assert_called_once()
    def test_no_crea_directorios_si_instalacion_nueva_no_esta_autorizada(self):
        from desktop import inicializacion

        with tempfile.TemporaryDirectory(prefix='orden_validacion_') as temporal:
            ruta = Path(temporal) / 'datos'

            with patch.object(
                inicializacion,
                '_validar_ruta',
                return_value=ruta,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    'Instalación nueva: requiere --inicializar.',
                ):
                    inicializacion.configurar(
                        ruta,
                        autorizar_nueva=False,
                        modo='temporal',
                    )

            self.assertFalse(
                ruta.exists(),
                'No debe crear el directorio antes de autorizar la instalación.',
            )
