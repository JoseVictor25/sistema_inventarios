# Aplicacion de escritorio

El instalador y el modo instalado soportan exclusivamente **Windows 11 x64
(compilacion 22000 o posterior)**. Windows 10, Windows 7, Windows 8/8.1 y
Windows ARM64 quedan fuera de soporte y no se probaran.

## Launcher

Los accesos directos de Inicio y escritorio ejecutan `SistemaInventarios.exe`
con el SID de operador que Setup aplicó; no pasan `--inicializar`. En un paquete congelado, el launcher entra en modo instalado y
usa `C:\ProgramData\SistemaInventarios` para la base SQLite, `.env`, logs y
respaldos. El modo temporal con `--datos-temporales` es solo para desarrollo y
pruebas.

Al primer inicio de una instalacion nueva, el launcher del paquete instalado
autoriza la creacion inicial de forma controlada y el sistema presenta un codigo
local de un solo uso para crear al Dueño. En ejecuciones de desarrollo la
inicializacion sigue requiriendo `--inicializar`. El launcher valida la identidad
Windows y los permisos de la carpeta de datos.

Si WebView2 no esta disponible o no puede abrirse, muestra un mensaje en espanol
y abre el navegador predeterminado. La decision de distribuir Evergreen en linea,
Evergreen sin conexion o conservar solo este respaldo esta pendiente y se
documenta en `desktop/installer/README.md`. No se descarga ni incluye el Runtime.

## Comandos de desarrollo

```powershell
.\venv\Scripts\python.exe scripts/verificar_fase10.py --pruebas --http --escritorio
.\venv\Scripts\python.exe scripts/verificar_fase10.py --abrir
.\venv\Scripts\python.exe scripts/compilar_fase10.py
```

La salida de compilacion se escribe en TEMP. No incluir `.env`, datos, logs,
respaldos ni documentacion privada en el paquete.
