# Fase 10 — Bloque B, etapa B2

Infraestructura preliminar; **no lista para usuarios finales**. B3/B4 pendientes.
Base: main, commit 7e848e8. Se conserva íntegro el código funcional del Bloque A.

## Implementado

- `desktop/installer/setup.iss`: AppId estable
  `{E3488284-3044-4D29-AB90-33D28FD02467}`, nombre Sistema de Inventarios,
  versión provisional 0.10.0, onedir completo, Program Files y privilegios de
  instalación por equipo. Destino de compatibilidad preliminar: Windows 11 x64,
  sin ARM64. Inicio y escritorio opcional.
- Bloqueo incondicional en InitializeSetup, también para modo silencioso, antes
  de instalar archivos. No se presenta como instalador funcional mientras faltan
  rutas instaladas, SID, ACL y mantenimiento. No existe opción para saltar el bloqueo.
- Detección WebView2 por equipo preparada; no confunde el HKCU del administrador
  elevado con el operador. No ejecuta ni descarga el Runtime.
- `scripts/compilar_instalador.py`: inspección, copia temporal de fuentes con
  hashes, lista explícita para Inno, manifiesto JSON, descubrimiento de ISCC,
  compilación sin ejecución y comprobación de los cuatro archivos protegidos.
- Sin escritura de datos en el script Inno ni borrado adicional al desinstalar.
  Sin [Run], tareas, ACL reales, creación de usuarios o migraciones.
- `desktop/installer/README.md`: comandos, límites, herramienta ausente,
  requisitos de procedencia del Runtime y distribución exclusivamente técnica.
- `desktop/installer/webview2.json`: registro de procedencia prevista, con versión,
  hash, firma y URL final explícitamente pendientes. No se inventaron valores.
- `scripts/tests/test_compilar_instalador.py`: seis pruebas independientes de Django.

## Verificaciones reales

Ejecutado con `venv/Scripts/python.exe`:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s scripts/tests -p test_compilar_instalador.py -v
```

**6 pruebas aprobadas**, con archivos ficticios exclusivamente en TEMP. Comprueban
copia íntegra, rechazo de configuraciones/datos/documentos privados, carpetas de
respaldo, paquete incompleto, caracteres inseguros y bloqueo/identidad del Setup.
No se ejecutó la suite Django: no se modificaron módulos de la aplicación y estas
comprobaciones no requieren conexión a ninguna SQLite.

Inno Setup no encontrado en PATH, ubicaciones habituales de Program Files y
LocalAppData comprobadas por el compilador, ni registros de desinstalación
HKLM/HKCU inspeccionados. No se instaló software. **No se acredita compilación
Inno, validez completa de Pascal/ISPP ni pruebas de instalación/desinstalación.**

No se ha adquirido un redistribuible WebView2. Es necesario seleccionar el
Standalone x64 oficial y verificar firma Microsoft, versión y SHA-256 antes de
incorporarlo. Este pendiente es explícito; el preliminar no intenta instalarlo.

Inspección real del onedir aprobado:
`%TEMP%/Inventarios_build_fase10_zk0de9fg/dist/SistemaInventarios`.
**4662 archivos inspeccionados y copiados con hashes coincidentes**, sin archivos
rechazados por las reglas de exclusión. Lista exacta y SHA-256 por archivo en:
`%TEMP%/Inventarios_instalador_B2_go_gtfoj/contenido.json`; entradas explícitas en
`archivos.iss` de la misma carpeta. La ejecución se detuvo por ausencia de ISCC;
no se generó ningún instalador EXE.

Los cuatro hashes protegidos coinciden con los registrados en el cierre del
Bloque A (`FASE_10_RESULTADOS.md`). `git diff --check` no reportó errores de
espacios; únicamente aviso de conversión LF/CRLF ya configurada en el repositorio.

## Pendientes

1. El operador instala una versión oficial de Inno Setup 6 tras autorizarlo;
   repetir compilación y corregir cualquier diagnóstico real de ISCC.
2. Seleccionar/verificar el redistribuible, registrar procedencia y hashes reales.
3. B3: modo instalado, SID/ACL, inicio persistente y mantenimiento/actualizaciones.
4. B4: instalación, reinstalación y desinstalación en VM con datos ficticios.
5. Icono, términos y firma definitiva aprobados antes de distribución final.

No se modificaron interfaz, modelos, servicios ni reglas de negocio. No se
ejecutaron binarios del paquete ni del instalador. Los dos informes privados
siguen sin seguimiento. Sin git add, commit o push. Se detiene el trabajo en B2.
