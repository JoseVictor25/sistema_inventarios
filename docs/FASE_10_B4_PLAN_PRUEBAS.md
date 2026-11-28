# Fase 10 B4 — plan manual de pruebas del instalador

**Entorno:** una sola máquina virtual limpia con Windows 11 x64, compilación
22000 o posterior. Crear y anotar una instantánea limpia antes de empezar.
Windows 10, Windows 7, Windows 8/8.1 y Windows ARM64 quedan fuera de soporte y
no se probarán. Usar exclusivamente datos ficticios.

**Instalador:** generar la variante `--solo-pruebas-vm`, marcada `SOLO PRUEBAS
VM - NO ENTREGAR AL CLIENTE`. El instalador de entrega continúa bloqueado. No
usar credenciales ni datos de producción.

**Evidencia:** guardar capturas, logs, hashes y registros de prueba fuera del
repositorio. Completar el resultado real y observaciones de cada prueba.

## Preparación

- [ ] VM limpia Windows 11 x64, compilación: ______________________________
- [ ] Instantánea previa creada: __________ Fecha: __________ Responsable: __________
- [ ] Hash SHA-256 y ruta TEMP del instalador de pruebas: __________________________
- [ ] Cuenta administradora ficticia (`VMAdmin`): _________________________________
- [ ] Cuenta estándar distinta (`OperadorVM`): ___________________________________
- [ ] Destino externo (carpeta compartida o disco virtual): _________________________
- [ ] Evidencia fuera del repositorio en: _________________________________________
- [ ] Datos y credenciales ficticios verificados: _________________________________

## Pruebas

### B4-01 — Instalación nueva y permisos de ProgramData

**Flujo real de creación y permisos**

- Setup se ejecuta elevado como administrador y crea
  `C:\ProgramData\SistemaInventarios` mediante `[Dirs]`; `uninsneveruninstall`
  impide que la desinstalación elimine esa carpeta. Sin `/OPERATOR_SID`, hereda
  la ACL de `C:\ProgramData`. Con el parámetro, `CurStepChanged(ssPostInstall)`
  usa `icacls` para retirar herencia y conceder control a SYSTEM, Administradores
  y al SID indicado, con propagación a archivos y subdirectorios.
- `configurar()` crea `logs` y `respaldos`, luego `.env`, `db.sqlite3` y
  `operador.json` bajo la identidad del primer proceso. `.env`, base, logs,
  respaldos y los archivos SQLite `-wal`/`-shm` heredan la ACL de la carpeta.
  No hay ACL por archivo explícita. `registrar_operador()` solo escribe el SID;
  `configurar()` no llama a `aplicar_permisos_seguros()`.
- Sin `/OPERATOR_SID`, una cuenta estándar puede no tener permiso de escritura y
  `verificar_directorio_seguro()` rechaza ACL heredadas que incluyan Users,
  Authenticated Users o Everyone. Si se permite la inicialización, esas ACL
  heredadas también pueden conceder lectura de `.env` a otros usuarios locales.
- La variante de pruebas rechaza la instalación si falta `/OPERATOR_SID` o el
  SID no tiene formato válido. Setup aplica ACL al SID y lo pasa al launcher en
  los accesos directos. Si una cuenta administradora distinta hace el primer
  inicio, `configurar()` registra el SID indicado, no el SID del admin; el
  operador podrá usar los archivos porque la ACL ya le concede control. El token
  de un solo uso no elige ni cambia el SID.
- El primer inicio sin argumentos en el ejecutable congelado solo autoriza crear
  la instalación inicial. `backend/apps/core/primer_uso.py` genera el token si no
  existe ningún usuario, exige ese token para crear al Dueño y lo consume tras el
  alta. El cambio del launcher no añade una ruta de creación de Dueño sin token.

**Corrección aplicada**

La variante VM exige un `/OPERATOR_SID` con formato válido, aplica la ACL durante
Setup y lo entrega al launcher mediante los accesos directos. Así el primer
arranque puede hacerlo el operador o el administrador elevado sin cambiar al
operador registrado. El instalador normal permanece bloqueado. La prueba de VM
aún debe confirmar permisos efectivos de todos los archivos.

**Pasos**

1. Obtener el SID de `OperadorVM`. Desde `VMAdmin`, ejecutar la variante de
   pruebas pasando `/OPERATOR_SID=<SID de OperadorVM>` y completar la instalación.
2. Confirmar elevación y revisar permisos iniciales de
   `C:\ProgramData\SistemaInventarios`.
3. Cerrar sesión, iniciar como `OperadorVM` y abrir el acceso directo de Inicio.
   Observar si puede completar el primer inicio y crear archivos.
4. Restaurar la instantánea. Repetir instalando con `/OPERATOR_SID=<SID de VMAdmin>`
   y realizando el primer inicio con la misma cuenta administradora.
5. Verificar que la variante VM rechaza iniciar Setup si se omite `/OPERATOR_SID`
   o se proporciona un SID inválido.
6. Registrar propietario y permisos efectivos del directorio y archivos en cada caso.

**Resultado esperado:** Setup crea el directorio persistente bajo ProgramData.
Con `/OPERATOR_SID`, Setup aplica ACL al operador y el launcher registra ese SID
aunque el primer inicio lo haga un administrador distinto. Setup rechaza la
variante de pruebas si falta el SID. Si el operador no puede inicializar o el
SID registrado no coincide, anotar como bloqueo B4 y no relajar permisos
manualmente.

**Resultado real:** __________________________________________________________

**Observaciones / permisos observados:** _____________________________________

### B4-02 — Código de un solo uso, Dueño y persistencia

**Pasos**

1. En la identidad elegida para operar, abrir la aplicación instalada.
2. Anotar el código local de un solo uso de la consola e introducirlo en la
   configuración inicial.
3. Crear el Dueño con datos ficticios (nombre `Dueño VM`, usuario `dueno_vm`).
4. Completar el alta y comprobar que el código deja de servir.
5. Reiniciar la VM, iniciar sesión con la misma identidad y abrir la aplicación.

**Resultado esperado:** se crea un único Dueño, el código se consume y tras
reiniciar se conservan cuenta y configuración; no vuelve a aparecer el primer
uso. Registrar los permisos y SID persistidos.

**Resultado real:** __________________________________________________________

**Observaciones:** ___________________________________________________________

### B4-03 — Respaldos, destino externo y restauración

**Pasos**

1. Configurar un destino externo ficticio en una carpeta compartida o disco
   virtual disponible para la VM. Registrar espacio y permisos.
2. Abrir el sistema y comprobar el respaldo automático de inicio cuando corresponda.
3. Cerrar normalmente y comprobar el respaldo automático de cierre según intervalo.
4. Anotar nombres, hora, tamaño, SHA-256 y advertencias del destino externo.
5. Crear datos ficticios identificables, generar un respaldo y cerrar el sistema.
6. Ejecutar el launcher instalado con `--instalado --restaurar "RUTA_DEL_RESPALDO"`.
7. Volver a abrir, confirmar la restauración y el respaldo de seguridad previo.

**Resultado esperado:** copias verificadas en el destino configurado; errores del
destino externo se notifican. `--restaurar` requiere la instalación cerrada,
valida la copia y conserva un respaldo de seguridad antes de reemplazar la base.

**Resultado real:** __________________________________________________________

**Observaciones / hashes:** __________________________________________________

### B4-04 — Reinstalación encima y actualización con datos

**Pasos**

1. Con datos ficticios creados y respaldados, cerrar la aplicación.
2. Ejecutar la variante de pruebas sobre la instalación existente y aceptar la
   misma ruta de destino.
3. Abrir el sistema y verificar datos, Dueño, `.env`, logs y respaldos.

**Resultado esperado:** se actualizan archivos del programa; base y configuración
permanecen legibles. Si hay migraciones pendientes, el launcher informa que se
requiere actualización autorizada y no las aplica silenciosamente. No se pierde
información.

**Resultado real:** __________________________________________________________

**Observaciones:** ___________________________________________________________

### B4-05 — Desinstalación y conservación de datos

**Pasos**

1. Registrar contenido y hashes ficticios de `C:\ProgramData\SistemaInventarios`.
2. Desinstalar desde Aplicaciones instaladas.
3. Confirmar que se retiran programa y accesos; revisar ProgramData sin modificarlo.
4. Reinstalar la variante de pruebas e iniciar con la identidad autorizada.

**Resultado esperado:** se retiran binarios y accesos; SQLite, `.env`, logs,
respaldos y demás datos de ProgramData permanecen. La reinstalación reconoce los
datos existentes y valida el SID autorizado.

**Resultado real:** __________________________________________________________

**Observaciones / hashes antes y después:** ___________________________________

### B4-06 — Equipo sin WebView2 y navegador de respaldo

**Pasos**

1. Si es posible, usar una instantánea aislada sin Runtime WebView2; no quitar
   componentes compartidos del host.
2. Abrir el sistema y registrar el mensaje y el navegador abierto.
3. Probar acceso, configuración inicial y una operación ficticia desde el navegador.

**Resultado esperado:** mensaje en español que indique que WebView2 no está
disponible o no pudo abrirse y que se abrirá el navegador predeterminado. El
sistema permanece operativo mientras consola/servidor local siga abierto. No se
descarga ni instala WebView2.

**Resultado real:** __________________________________________________________

**Observaciones (o motivo por el que no se pudo simular):** ____________________

### B4-07 — SmartScreen con instalador sin firmar

**Pasos**

1. Ejecutar la variante sin firmar en la VM y capturar el texto exacto de
   SmartScreen, editor indicado y opciones disponibles.
2. Anotar si la advertencia aparece al descargar, abrir o iniciar Setup y cómo
   se resolvió en el laboratorio.

**Resultado esperado:** registrar el comportamiento exacto observado, sin asumir
que se repetirá idéntico en otra VM o versión de Windows. No se considera
validación de firma; el instalador sigue siendo de pruebas y no se entrega.

**Resultado real (texto y pasos exactos):** __________________________________

**Observaciones:** ___________________________________________________________

### B4-08 — Cierre inesperado y recuperación

**Pasos**

1. Crear datos ficticios y confirmar un respaldo válido.
2. Con la aplicación abierta, finalizar abruptamente el proceso dentro de la VM
   (por ejemplo, desde el Administrador de tareas). No hacerlo con datos reales.
3. Volver a abrir y observar recuperación, bloqueo de instancia, integridad y respaldo.

**Resultado esperado:** el cerrojo se libera al terminar el proceso; la aplicación
abre sin corromper la base. El último respaldo válido sigue disponible y se crea
el respaldo de inicio/cierre que corresponda por antigüedad.

**Resultado real:** __________________________________________________________

**Observaciones / logs:** ____________________________________________________

## Cierre de B4

- [ ] Se completaron los casos posibles y se anotaron los no ejecutables.
- [ ] Evidencia guardada fuera del repositorio en: _____________________________
- [ ] Bloqueos encontrados y severidad: _______________________________________
- [ ] Instantánea final / destino de descarte de la VM: _________________________
- [ ] B4 aprobado por: ______________________________ Fecha: _________________
