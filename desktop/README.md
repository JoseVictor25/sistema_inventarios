# desktop/

Bloque A experimental: el launcher exige `--datos-temporales` con una ruta
absoluta dentro de TEMP. No utiliza ProgramData real. Una identidad Windows;
los datos heredan la protección del perfil temporal de esa identidad. Las ACL
de instalación definitiva corresponden al Bloque B, aún no autorizado.

Desde la raíz:

```powershell
.\venv\Scripts\python.exe scripts/verificar_fase10.py --pruebas --http --escritorio
.\venv\Scripts\python.exe scripts/verificar_fase10.py --abrir
.\venv\Scripts\python.exe scripts/compilar_fase10.py
```

`--abrir` crea una instalación ficticia. El launcher muestra en consola un código
de un solo uso: introdúcelo en la configuración inicial junto con las credenciales
que elijas. El Dueño no es staff ni superusuario. No cierres la consola mientras
usas la ventana. Si WebView2 falla, se abre el navegador; ENTER en la consola
termina el servidor. No existe endpoint HTTP de apagado.

El ejecutable conserva consola en este bloque para autorización y cierre local.
Ejecutar desde PowerShell con `--datos-temporales RUTA_ABSOLUTA` y `--inicializar`
solo la primera vez; `--diagnostico` comprueba HTTP/estáticos y termina;
`--respaldo` no abre servidor ni ventana. No acepta datos fuera de TEMP.

Recursos: rutas relativas al paquete. Datos: configuración generada por instalación,
SQLite, respaldos, logs y estáticos de desarrollo bajo la ruta temporal. Configuración
existente incompleta detiene el arranque. Las migraciones se aplican solo al crear
una instalación nueva autorizada; un esquema existente pendiente impide el arranque
funcional. El modo respaldo puede copiar un esquema pendiente sin migrarlo.

Construcción: collectstatic aislado, PyInstaller onedir con lista explícita de
recursos y módulos de aplicaciones. La salida está en TEMP, no se instala.
No incluir .env, datos, logs, respaldos ni documentación privada.

Pendientes de inspección: WebView2, descargas en ventana, navegaciones externas,
Windows limpio y pruebas visuales. No confundir HTTP con validación gráfica.

Empaquetado como programa de escritorio (se hace al final):

- launcher.py   -> aplica migraciones, inicia waitress y abre la ventana (pywebview)
- sistema.spec  -> configuración de PyInstaller (modo --onedir, incluir frontend/)
- installer/    -> setup.iss (Inno Setup), politicas.txt, icono.ico
