# Sistema de inventarios y ventas

Django (backend/) + HTML con plantilla (frontend/), empaquetable como programa de escritorio.

## Estructura
- backend/   proyecto Django (config/, apps/)
- frontend/  templates/ y static/ (Django los lee desde aquí)
- desktop/   empaquetado (PyInstaller + Inno Setup)
- scripts/   respaldo.py
- docs/      especificación completa, diagrama de clases (Mermaid) y mockups HTML de las pantallas

## Primeros pasos (Windows)
    python -m venv venv
    venv\Scripts\activate
    pip install -r backend\requirements.txt
    cd backend
    copy .env.example .env        (y completa SECRET_KEY dentro de .env)
    python manage.py migrate
    python manage.py createsuperuser
    python manage.py runserver

Abre http://127.0.0.1:8000/ e ingresa con el superusuario.

## Para trabajar con un agente de IA
Entrégale este proyecto y pídele que lea primero ESPECIFICACION_SISTEMA.md (empieza por la sección
"Cómo usar este documento", que incluye un primer mensaje sugerido).

## Siguiente paso
Escribir los models.py de cada app según docs/diagrama_clases_inventario_v4.mermaid.

## Estado de la fase 0

Preparación parcial: consultar [resultados y verificación](docs/FASE_0_RESULTADOS.md).
Los recursos locales y dependencias del venv están verificados. Queda validar
la interfaz en navegador y la apertura de WebView2; consultar el informe actualizado.
No hay commits ni modelos de la fase 1.
