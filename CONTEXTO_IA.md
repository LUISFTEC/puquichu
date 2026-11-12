# CONTEXTO PARA AGENTES DE IA (AI HANDOVER)

Lee `README.md` en esta misma carpeta antes de realizar cualquier cambio (sección "Notas para asistentes de IA").

## Resumen
- **Nombre:** Puquichu. Nombre inventado: *puquy* (lluvias, pasto verde) + *ichu* (pasto seco dorado).
- **Tipo:** aplicación nativa de escritorio Linux (probada en KDE Plasma, X11) con PyQt6 + python-vlc + SQLite + yt-dlp + ffmpeg. **NO es web.**
- **Entrada:** `app.py` (ventana) → usa `core.py` (lógica), `theme.py` (diseño), `widgets.py` (componentes), `mpris.py` (D-Bus).
- **Python:** `venv/bin/python3` dentro de la carpeta del proyecto.
- **Datos (fuera de git):** `puquichu.db` (SQLite), `settings.json`, música en `musicplay/`.
- **Control de versiones:** git (rama `main`, etiquetas `vX.Y.Z`).

## Ejecutar (desde la carpeta del proyecto)
```bash
venv/bin/python3 app.py
```
