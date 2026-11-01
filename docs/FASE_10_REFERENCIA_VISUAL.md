# Adaptación a la referencia definitiva

Actualización 01/11/2026: el usuario aprobó la revisión visual de navegación,
Inicio, Bitácora y POS. Las limitaciones automatizadas descritas abajo son
evidencias históricas; el cierre técnico vigente está en `FASE_10_RESULTADOS.md`.

Referencia abierta y examinada: `docs/referencias/Panel de inventario Mi Tienda.png`.
Esta referencia sustituye la navegación horizontal descrita en informes anteriores.

## Implementación

- Barra lateral blanca de 250 px permanente desde 992 px. Por debajo utiliza
  Offcanvas de Bootstrap local, fondo oscurecido, foco controlado, cierre exterior,
  botón y Escape. Una sola lista de enlaces conserva los bloques de permisos.
- Encabezado compacto con nombre completo, usuario y formulario POST de salida
  con CSRF. No se trunca el nombre: los nombres largos pueden ocupar más altura.
- Fondo azul claro, iconos SVG locales decorativos, selección verde, tarjetas
  redondeadas y sombras suaves, siguiendo la composición de la referencia.
- Panel con los indicadores existentes: ventas autorizadas, turno propio y tres
  alertas. Degradados verde, naranja, amarillo y rojo. Accesos rápidos autorizados.
- No se agregaron clientes, porcentajes, buscador global, notificaciones ni
  gráficos ficticios de la ilustración. Los servicios y permisos no cambian.
- Bitácora en tabla con filtros y paginación existentes. Detalle de solo lectura
  en panel derecho desplazable, etiquetas legibles, comparación anterior/nuevo
  y escape de contenido. Se conserva el formateador y ocultamiento de secretos.

## Archivos de esta revisión

`frontend/templates/base.html`, `components/_menu.html`, `components/_icono.html`,
`inicio.html`, `auditoria/lista.html`; `frontend/static/css/app.css`,
`frontend/static/js/app.js`; `backend/apps/core/tests/test_navegacion_lateral.py`;
`scripts/verificar_interfaz_fase0.py`, `scripts/revisar_navegacion_fase10.py`;
este informe y `docs/FASE_10_RESULTADOS.md`.

## Revisión visual pendiente

Se intentó la automatización WebView2 con datos temporales. Login, inicio, logout
y 14 recursos superaron la comprobación HTTP, pero WebView2 agotó el tiempo al
leer `/login/` a 1920 px. No se inspeccionaron las interacciones ni los siete
tamaños y no hay capturas de la implementación. No se acredita equivalencia
visual perfecta ni cierre de fase.

Evidencia: `%TEMP%/Inventarios_visual_lateral_ajw51ysz/resultado.json`.

Desde la raíz, ejecutar:

```powershell
.\venv\Scripts\python.exe scripts/revisar_navegacion_fase10.py
```

El comando crea SQLite y credenciales ficticias en TEMP y abre el launcher desde
fuente, recopilando los recursos actuales. Revisar Inicio y Bitácora como Dueño
y Vendedor a 390, 768, 1024, 1280, 1366, 1600 y 1920 px; maximizar y restaurar.
Probar apertura, cierre exterior, Escape y teclado en ambos paneles, desplazamiento
vertical, nombre completo, selección activa y ausencia de módulos no autorizados.
Las vistas de datos no deben desbordar el documento; las tablas pueden desplazarse
dentro de su propio contenedor.

La aceptación visual depende de la revisión del usuario en Windows.

## Resultados técnicos ejecutados

- `verificar_fase10.py --pruebas --http --escritorio`: salida 0.
  Django check sin incidencias, sin cambios de modelos pendientes; suite completa
  de 356 pruebas aprobada en 255,600 segundos. Las tres pruebas nuevas de
  `test_navegacion_lateral` se ejecutaron después por separado: 3/3 aprobadas.
  Total: 359 pruebas aprobadas entre ambas ejecuciones, no una sola suite de 359.
- Launcher HTTP aislado: primera y segunda ejecución aprobadas.
- Reportes: 73 solicitudes HTTP, ocho reportes y dieciséis exportaciones.
- Auditoría/respaldos: 36 solicitudes HTTP sin 404 ni 500; recuperación temporal
  con comparación íntegra de 33 tablas. Los 403/422 deliberados verifican permisos,
  CSRF y validación, y no son fallos de regresión.
- `preparar_frontend.py --verificar`: integridad correcta. Recursos recopilados
  con configuración aislada y DEBUG=False. Bootstrap local incluye Offcanvas-lg.
- PyInstaller limpio: completado. Paquete experimental en
  `%TEMP%/Inventarios_build_fase10_6s3cvvv7/dist/SistemaInventarios`.
  Verificador del paquete: inicio nuevo, inicio existente, respaldo e inspección
  de archivos privados aprobados. 4662 archivos, 74184936 bytes. No instalado.
  Los hooks emitieron avisos de descubrimiento Django/Oracle opcional; las pruebas
  funcionales del paquete SQLite finalizaron con código 0.
- Ambas copias empaquetadas del CSS/JS coinciden byte por byte con el código fuente:
  CSS `ef9ab4448eaf68437f49dedd7716890767bd16eb94011b00efa2df3d88e00aac`;
  JS `a3160691a9369f3a66eb086842443a42b1498adb3444cdf94523677a0b16c2b2`.
- Git: main; sin staging, commits, push, ramas o etiquetas nuevas. Cambios locales
  previos y los dos informes privados conservados. Diff check sin errores de
  espacios; avisos LF/CRLF del repositorio, sin cambiar su configuración.

Evidencias técnicas: `%TEMP%/Inventarios_fase10_54r8svyu` y
`%TEMP%/Inventarios_fase10_tq_cu3ot`.

## Archivos protegidos

Hashes SHA-256 idénticos antes y después; sin conexiones de datos a la base real,
sin migraciones reales y sin cambios a los servicios, modelos o reglas de negocio:

| Archivo | SHA-256 |
|---|---|
| db.sqlite3 | `40D61B7947251655E3AF6055FAB58130D29A24586B103AA62FF4D5B847E37F50` |
| .env | `9BC65E53962E9CD7849EB41F2899DFA29D230DF7DCB217831793CA76BE8FC854` |
| REPORTE_MIGRACIONES_FASE1.md | `B5239FC7F134851BF32225F7363604D500449538690C2658A101105C7C257E53` |
| SOLUCION_ERROR_TERMINAL.md | `8D907AD4BD5AB07E2F3799033A21E83C9A77AA7095E4C6CF520709D5E1EFAE26` |
