# Fase 10: opciones para la consola

La consola se mantiene visible en esta entrega. El primer arranque muestra allí
un código local de un solo uso; si el código se elimina de la consola, debe
seguir llegando al operador de forma autenticada y clara. También debe
informarse si WebView2 no está disponible y se abrirá el navegador.

## Opciones

| Opción | Ventajas | Riesgos |
| --- | --- | --- |
| Mostrar el código dentro de la ventana del sistema | Una sola interfaz y el operador puede copiarlo allí. | La ventana debe estar disponible antes del alta inicial; hay que evitar que el código quede en capturas, cachés o historial. |
| Guardar el código en un archivo legible solo por el operador | Fácil de implementar y permite recuperar el código si se pierde la ventana. | Debe crearse con ACL exclusiva desde el primer byte, borrarse al usarlo y evitar copias de seguridad o indexación; permisos mal aplicados exponen la autorización. |
| Asistente mínimo de primer arranque | Puede presentar el código, explicar WebView2 y guiar al operador en una interfaz coherente. | Añade otra superficie de interfaz que mantener y probar; debe proteger el código en memoria y comunicar errores de WebView2 aunque la vista principal no abra. |

## Recomendación

Implementar un asistente mínimo de primer arranque que muestre el código en la
propia ventana nativa, permita copiarlo y lo invalide al completar el registro.
El asistente debe presentar también el aviso de WebView2 y ofrecer abrir el
navegador cuando corresponda. Mantener la consola visible como alternativa de
diagnóstico hasta validar ese flujo en Windows 11 con cuentas de operador
estándar. No se modifica aquí la seguridad ni el ciclo de vida del código.
