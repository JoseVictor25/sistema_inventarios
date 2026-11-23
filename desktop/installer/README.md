# Instalador B3 y preparacion de B4

Nombre: **Sistema de Inventarios**, version **0.10.0**. AppId permanente:
`{E3488284-3044-4D29-AB90-33D28FD02467}`.

## Sistemas compatibles

El unico sistema operativo soportado es **Windows 11 x64 (compilacion 22000 o posterior)**.
Windows 10, Windows 7, Windows 8/8.1 y Windows ARM64 no son compatibles ni se probaran.
En Windows 10, Setup debe mostrar en espanol que el sistema requiere Windows 11.

## Estado de seguridad

La compilacion predeterminada conserva el bloqueo incondicional de
`InitializeSetup`: muestra que el instalador esta bloqueado y termina sin instalar.
Su nombre sigue siendo `Instalador_Sistema_Inventarios_0.10.0_B3_BLOQUEADO.exe`.
No se debe retirar este bloqueo para una entrega real.

Para preparar exclusivamente la prueba manual en una VM limpia de Windows 11,
agrega `--solo-pruebas-vm` al comando de compilacion. Esta variante solo continua
tras mostrar un aviso, y se identifica con `SOLO_PRUEBAS_VM` en el nombre,
`AppVerName` y el propio asistente. **No entregar al cliente.** Ambas variantes
aplican la misma inspeccion estricta del paquete. La salida se crea en TEMP, nunca
en el repositorio, y se imprime la ruta y SHA-256. Este script compila; no ejecuta
el instalador ni ningun EXE del paquete.

## Compilacion

Usar un onedir aprobado de `scripts/compilar_fase10.py`. Desde la raiz:

```powershell
.\venv\Scripts\python.exe scripts/compilar_instalador.py --paquete "RUTA\SistemaInventarios" --solo-verificar
.\venv\Scripts\python.exe scripts/compilar_instalador.py --paquete "RUTA\SistemaInventarios"
.\venv\Scripts\python.exe scripts/compilar_instalador.py --paquete "RUTA\SistemaInventarios" --solo-pruebas-vm
```

El script copia el paquete inspeccionado a TEMP, conserva `contenido.json`, la
lista explicita `archivos.iss`, el log del compilador y el instalador. Rechaza
enlaces, hardlinks, bases/auxiliares SQLite, `.env`, logs, respaldos, carpetas
privadas y archivos protegidos. La inspeccion es identica en ambas variantes.

No hay secciones `[Run]`, `[UninstallRun]` ni `[UninstallDelete]`. ProgramData se
marca `uninsneveruninstall`. Los accesos directos de Inicio y escritorio apuntan
directamente a `SistemaInventarios.exe` y pasan `--operador-sid`; no pasan
`--inicializar`. La variante VM exige `/OPERATOR_SID=<SID>` y Setup valida/aplica
ACL a ese SID. El launcher
congelado entra en modo instalado, autoriza el primer inicio y usa
`C:\ProgramData\SistemaInventarios`. Para que Setup aplique ACL al operador
estándar antes de su primer inicio, proporcionar `/OPERATOR_SID=<SID>` al
instalador. Sin ese parámetro, la carpeta conserva ACL heredadas y la validación
de seguridad puede rechazar el acceso; probar y registrar ambos escenarios B4.

Inno Setup no se descarga ni instala mediante este script. `--iscc RUTA` permite
indicar un compilador ya instalado.

## WebView2: decision pendiente

No se descarga ni incluye instalador de WebView2. El instalador registra si el
Runtime por equipo aparece en HKLM32, pero no lo instala ni bloquea la instalacion.
Si WebView2 falta o no puede abrirse, el launcher informa en espanol que abrira
el navegador predeterminado y lo usa como respaldo.

Opciones para equipos sin Runtime, pendientes de decision antes de distribucion:

| Opcion | Ventajas | Desventajas |
| --- | --- | --- |
| Evergreen Bootstrapper en linea | Descarga el Runtime vigente y reduce el tamano inicial. | Requiere internet durante instalacion; la disponibilidad y el tiempo dependen de la red. |
| Evergreen Standalone sin conexion | Se puede instalar en redes aisladas; se controla el artefacto y su verificacion. | Aumenta el paquete; requiere mantener version, procedencia, firma y hash, y decidir actualizaciones. |
| Solo respaldo del navegador | No incorpora ni instala componentes compartidos; el launcher ya abre el navegador predeterminado. | La experiencia y descargas dependen del navegador y del perfil del usuario; requiere validar el flujo en B4. |

No se eligio ni descargo ningun redistribuible. Para cualquier futura inclusion
se requiere verificar procedencia oficial, firma Authenticode Microsoft, version,
arquitectura y SHA-256. Si se elige distribuirlo, usar el paquete oficial
Standalone x64 y registrar URL de origen/final, version, fecha y firma Microsoft;
el hash por si solo no prueba procedencia. El Runtime compartido no se desinstala.

La inspeccion no detecta secretos embebidos en binarios: el origen debe ser un
onedir aprobado, construido sin datos reales. ISCC ausente produce salida 2 y no
cuenta como compilacion; las pruebas estaticas no sustituyen compilar con Inno.
Inno Setup no se descarga ni instala por este script. Verificar procedencia y
firma antes de instalar ISCC. No hay icono comercial ni terminos legales
aprobados para una version final.

La variante de pruebas rechaza instalaciones sin `/OPERATOR_SID=<SID>` válido,
aplica ACL al SID en Setup y lo transmite por los accesos directos. El instalador
normal sigue bloqueado. `configurar()` no llama a `aplicar_permisos_seguros()`;
el escenario sin SID no aplica a la variante VM porque Setup lo impide.

## Evidencia y pruebas

El plan manual esta en `docs/FASE_10_B4_PLAN_PRUEBAS.md`. Capturas, logs y otros
resultados de la VM se guardan fuera del repositorio.
