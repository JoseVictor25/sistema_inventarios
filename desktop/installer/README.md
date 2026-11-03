# Instalador preliminar B2

Nombre: **Sistema de Inventarios**. Versión: **0.10.0**.
AppId permanente: `{E3488284-3044-4D29-AB90-33D28FD02467}`.
No cambiar AppId al actualizar la versión.

## Estado y límite de seguridad

`setup.iss` define instalación por equipo, Program Files, Windows 11 x64 nativo,
Inicio y escritorio opcional. Conserva consola y paquete onedir del Bloque A.
Windows 10 y ARM64 no se anuncian como compatibles en este preliminar.

**InitializeSetup siempre devuelve False**, también en modo silencioso. No hay
interruptor de compilación para habilitarlo. Puede solicitar elevación por su
manifiesto, pero no instala el programa ni prepara datos. No ejecutar en el equipo
principal. No retirar el bloqueo antes de implementar, revisar y probar B3/B4.

Las rutas instaladas, SID del operador, ACL de ProgramData, primer inicio,
coordinación de actualización/procesos y desinstalación operativa son B3.
Los accesos directos previstos no reciben --datos-temporales ni --inicializar:
el launcher actual no funciona en modo instalado, y por eso se bloquea todo Setup.

No se crean archivos de datos mediante [Files]/[Dirs], no se definen borrados
adicionales ni ejecución al instalar/desinstalar. Inno registra únicamente archivos
del programa y accesos. ProgramData, SQLite, .env y respaldos no se incluyen ni
eliminan. No hay tareas Windows, migraciones o aplicación de ACL en B2.

No hay icono comercial aprobado ni términos legales. Se conserva el icono técnico
del ejecutable; no se genera un icono ni un documento legal ficticio. Estos recursos
deben aprobarse antes de distribuir una versión final.

## Compilación reproducible

Utilizar un onedir aprobado de `scripts/compilar_fase10.py`, nunca una carpeta de
datos. Desde la raíz:

```powershell
.\venv\Scripts\python.exe scripts/compilar_instalador.py --paquete "RUTA\SistemaInventarios" --solo-verificar
.\venv\Scripts\python.exe scripts/compilar_instalador.py --paquete "RUTA\SistemaInventarios"
```

El script copia el paquete inspeccionado a una carpeta nueva en TEMP y compara
SHA-256 antes/después. Genera `contenido.json`, una entrada por archivo en
`archivos.iss`, y, si está disponible ISCC, `compilacion.txt` y el instalador dentro
de `salida`. No ejecuta ningún EXE del paquete o instalador. Salida 2 significa
compilador ausente, no compilación exitosa. `--iscc RUTA` permite indicar un
compilador instalado y confiable. No se necesita Python en el equipo del cliente;
se usa el venv únicamente en construcción.

La inspección rechaza enlaces, hardlinks, bases/auxiliares SQLite, .env, logs,
respaldos, carpetas privadas y los dos informes protegidos. La lista explícita
evita incorporar archivos añadidos al directorio fuente después de inspeccionarlo.
Esto no es un detector universal de secretos dentro de binarios: el origen debe
ser el paquete aprobado construido desde el proyecto, sin datos reales.

## Inno Setup no instalado

Obtener Inno Setup 6 desde su sitio oficial:
https://jrsoftware.org/isdl.php

El operador debe verificar procedencia/firma y autorizar e instalar la herramienta
por separado. Este script no la descarga ni instala. Después proporcionar la ruta
ISCC.exe o usar una ubicación habitual/PATH. La sintaxis Pascal e ISPP solo queda
validada cuando ISCC compila correctamente; las pruebas estáticas no lo sustituyen.

## WebView2

Fuente oficial: https://developer.microsoft.com/microsoft-edge/webview2/
Contrato de distribución y detección:
https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution

Se prepara detección del Runtime por equipo mediante HKLM32 y valor `pv`,
descartando valor vacío/0.0.0.0. No se considera Edge navegador como Runtime.
El HKCU del instalador elevado puede pertenecer a otro administrador; la detección
por identidad autorizada y la comprobación funcional quedan para B3/B4.

`webview2.json` registra explícitamente la ausencia de un artefacto seleccionado.
No hay versión/hash reales todavía y no se incluye ni ejecuta el redistribuible.
Antes de incorporarlo, registrar URL oficial y URL final, versión del archivo,
SHA-256, fecha y firma Authenticode válida de Microsoft. Comprobar que sea el
Standalone x64, no el Bootstrapper dependiente de internet. El hash por sí solo
no acredita procedencia. Si falla la firma, procedencia, arquitectura o integridad,
no empaquetar. No desinstalar este Runtime compartido con la aplicación.

## Verificación y distribución

```powershell
.\venv\Scripts\python.exe -m unittest discover -s scripts/tests -p test_compilar_instalador.py -v
```

No distribuir a usuarios finales. Un futuro EXE B2 se identifica como
`Instalador_Sistema_Inventarios_0.10.0_B2_BLOQUEADO.exe`; compartirlo únicamente para
revisión técnica con su manifiesto y hash, nunca como instalador funcional.
Antes de distribución final: B3, B4 en VM limpia, términos/icono aprobados, política
de firma y pruebas de conservación de datos. No se garantiza atomicidad de una
actualización mediante las opciones de Inno presentes en este esqueleto.
