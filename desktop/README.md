# desktop/

Empaquetado como programa de escritorio (se hace al final):

- launcher.py   -> aplica migraciones, inicia waitress y abre la ventana (pywebview)
- sistema.spec  -> configuración de PyInstaller (modo --onedir, incluir frontend/)
- installer/    -> setup.iss (Inno Setup), politicas.txt, icono.ico
