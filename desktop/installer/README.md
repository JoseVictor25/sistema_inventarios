# Instalador B3 y preparacion de B4

Nombre: **Sistema de Inventarios**, version **0.10.0**. AppId permanente:
`{E3488284-3044-4D29-AB90-33D28FD02467}`.

## Sistemas compatibles

El unico sistema operativo soportado es **Windows 11 x64 (compilacion 22000 o posterior)**.
Windows 10, Windows 7, Windows 8/8.1 y Windows ARM64 no son compatibles ni se probaran.
En Windows 10, Setup debe mostrar en espanol que el sistema requiere Windows 11.

## Estados del artefacto y bloqueo

- **Candidato:** onedir generado por `compilar_fase10.py`, con manifiesto sin firma.
  No puede iniciar modo instalado ni preparar datos; no se compila a instalador.
- **Autorizado:** payload inmutable cuyo manifiesto exacto tiene autorización Ed25519
  válida, política compatible y evidencia T1-B aprobada. La clave de release y la
  certificación T1-B aún no están provisionadas en este árbol.
- **Distribuible:** payload autorizado aceptado por `compilar_instalador.py`; Setup
  debe verificar el release aprobado. En el estado T1-A Setup sigue bloqueado.

La ruta de candidato solo inspecciona o empaqueta en TEMP; no inicia EXE ni Setup.
`--solo-pruebas-vm` está bloqueado. `InitializeSetup` retorna fallo antes de instalar.
No se generan claves, firmas ficticias ni instaladores ejecutables en T1-A.

## Compilacion

Generar un candidato onedir con `scripts/compilar_fase10.py`. No se ejecuta el EXE.
La autorización se firma después sobre el manifiesto de hashes del candidato; el
payload no se reconstruye. La clave privada permanece fuera del repositorio y del
paquete. La firma se rechaza mientras falten clave pública fijada o validación T1-B.

```powershell
.\venv\Scripts\python.exe scripts/compilar_instalador.py --paquete "RUTA\SistemaInventarios" --solo-verificar
```

`--solo-verificar` solo inspecciona archivos y comunica si el paquete sigue siendo
candidato; no autoriza distribución. La compilación final exige autorización válida,
copia el payload a TEMP y vuelve a verificar sus hashes. El instalador se compila
desde esa copia exacta; no se reconstruyen los binarios firmados. El compilador
rechaza `--solo-pruebas-vm` hasta cerrar T1-B/B4.

No hay secciones `[Run]`, `[UninstallRun]` ni `[UninstallDelete]`. ProgramData se
marca `uninsneveruninstall`. Los accesos directos de Inicio y escritorio apuntan
directamente a `SistemaInventarios.exe` y pasan `--operador-sid`; no pasan
`--inicializar`. En T1-A no se generan accesos directos instalables ni se permite
el arranque congelado: launcher y settings exigen autorización válida y T1-B.
`InitializeSetup` permanece bloqueado, incluso si se define la macro VM.

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

El instalador normal y la variante VM siguen bloqueados. El modo productivo no
puede considerarse preparado por una DACL correcta: requiere que T1-B valide el
procedimiento de propietario BA y que la autorización firmada coincida con el
manifiesto y el ejecutable exactos.

## Evidencia y pruebas

El plan manual esta en `docs/FASE_10_B4_PLAN_PRUEBAS.md`. Capturas, logs y otros
resultados de la VM se guardan fuera del repositorio.
