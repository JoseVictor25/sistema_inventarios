# Restaurar el sistema desde un respaldo

La restauración se hace desde el launcher del equipo donde está instalado el sistema. No se realiza desde una página web.

## Antes de empezar

1. Pide a todas las personas que cierren el sistema.
2. Comprueba que el archivo de respaldo `.sqlite3` y el archivo `.json` con el mismo nombre estén juntos. El manifiesto contiene la huella que permite comprobar que la copia no está dañada.
3. Conserva una copia de esos dos archivos en un lugar seguro. La restauración también crea automáticamente un respaldo de seguridad de la base actual.
4. Localiza `SistemaInventarios.exe` y abre una ventana de comandos en esa carpeta. Si el sistema sigue abierto, el launcher rechazará la operación.

## Restaurar

Ejecuta este comando, cambiando la ruta de ejemplo por la ubicación real del archivo:

```text
SistemaInventarios.exe --instalado --restaurar "E:\Respaldos\respaldo_20261120_120000_0123456789abcdef0123456789abcdef.sqlite3"
```

El launcher comprueba el manifiesto, el hash y la integridad SQLite. Si todo está correcto, guarda primero la base actual en la carpeta local de respaldos y luego reemplaza la base de forma atómica. Si el manifiesto contiene el QR bancario, también lo recupera.

Cuando aparezca «Restauración completada», abre el programa normalmente. Si aparece un mensaje de error, no borres archivos: la base anterior se conserva y el mensaje explica el problema. Si el programa indica que sigue en ejecución, ciérralo completamente y vuelve a ejecutar el comando.

## Importante

- No renombres ni separes el archivo `.json` de su respaldo `.sqlite3`.
- No edites la base ni el manifiesto.
- La restauración reemplaza los datos actuales por los que contiene la copia seleccionada.
- La base de seguridad anterior queda en la carpeta de respaldos configurada en el equipo.
- `BACKUP_CONSERVAR` indica los días naturales de cobertura: se guardan todas las copias verificadas de las últimas 24 horas (hasta ocho) y, para los días anteriores, solo la más reciente de cada día UTC hasta completar esa cobertura.
- `BACKUP_HORAS_MIN_CIERRE` controla cada cuántas horas se permite un respaldo al cerrar el programa. Su valor predeterminado es 6 y el mínimo es 1; el respaldo de inicio mantiene su límite de 24 horas.
