# Recursos locales del frontend

Estado: recursos instalados y hashes verificados con el manifiesto local.
Django sirve los nueve CSS/JS de la base con HTTP 200 y contenido correcto.
La revisión visual y ejecución JavaScript en navegador siguen pendientes.

Desde la raíz, en un entorno con conexión:

```powershell
python scripts/preparar_frontend.py
python scripts/preparar_frontend.py --verificar
```

Versiones objetivo: AdminLTE 4.0.2 (incluye CSS Bootstrap), Bootstrap 5.3.8
(bundle JS con Popper), HTMX 2.0.8, Chart.js 4.5.1 y Tom Select 2.4.3.
No se añade una segunda hoja CSS de Bootstrap.

El script consulta metadatos oficiales de npm, verifica la integridad del paquete,
conserva las licencias y registra hashes SHA-256 en manifest.json. Se detiene
si encuentra un archivo existente distinto. No descarga demos ni fuentes externas.
La descarga fue realizada por el usuario; en esta revisión se verificaron
archivos, hashes y licencias locales. Conservar todas las licencias. Verificar
consola y solicitudes de red antes de dar por finalizada la fase 0.
Los recursos originales no se editan; ajustes propios en css/app.css.

La ejecución del sistema utiliza solo rutas locales, sin CDN. Después de descargar,
ejecutar collectstatic y verificar en navegador con internet desconectado.

Licencias: AdminLTE, Bootstrap y Chart.js (MIT); HTMX (0BSD);
Tom Select (Apache-2.0). Se conserva la corrección del usuario que admite Apache-2.0.

Los bundles referencian seis archivos `.map` que no forman parte de esta descarga.
Son mapas de depuración, no dependencias de ejecución; DevTools puede intentar
solicitarlos y mostrar avisos de ausencia. Los archivos originales no se modificaron.
Las dos hojas CSS no tienen @import ni URL externas (solo imágenes data:).
