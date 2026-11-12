# CONTEXTO PARA AGENTES DE IA (AI HANDOVER)

Lee `README.md` en esta misma carpeta antes de realizar cualquier cambio (sección "Notas para asistentes de IA").

## Resumen
- **Nombre:** Puquichu. Nombre inventado: *puquy* (lluvias, pasto verde) + *ichu* (pasto seco dorado).
- **Tipo:** aplicación nativa de escritorio (PyQt6 + python-vlc + SQLite + yt-dlp + ffmpeg). **NO es web.** Hoy publicada para Linux.
- **Entrada:** `app.py` (ventana) → usa `core.py` (lógica), `theme.py` (diseño), `widgets.py` (componentes), `mpris.py` (D-Bus, solo Linux).
- **Python:** `venv/bin/python3` dentro de la carpeta del proyecto. El código debe seguir siendo compatible con **Python 3.10**.
- **Datos:** desde el código y con datos junto a `app.py` → modo portable (carpeta del proyecto). Instalada → `~/.local/share/puquichu` y `~/Música/Puquichu`.
- **Repositorio:** https://github.com/LUISFTEC/puquichu (público, GPL-3.0). Rama `main`, etiquetas `vX.Y.Z`.

## Ejecutar (desde la carpeta del proyecto)
```bash
venv/bin/python3 app.py
```

---

## Estado actual (versión 1.1.1)

- ✅ **Linux (.deb)** publicado en Releases. GitHub Actions (`.github/workflows/instaladores.yml`) lo arma en Ubuntu 22.04,
  lo instala y lo prueba en Ubuntu 22.04 y 24.04 limpios, y lo publica al subir una etiqueta `v*`.
- ✅ Prueba automática: `PUQUICHU_SMOKE_TEST=1` (arranque + tono WebM/Opus sin internet) o `=red` (además búsqueda y audio en línea).
- Lecciones del empaquetado (no repetir errores):
  - No incluir `libvlc*` en el paquete (pierde sus módulos): se usa el VLC del sistema.
  - No incluir `libstdc++` ni `libgcc_s`: en distros más nuevas rompen el lector WebM de VLC y ffmpeg.
  - Los programas externos (ffmpeg, xdg-open…) deben correr sin el `LD_LIBRARY_PATH` del paquete (ya lo hace `core.py`).
  - Nada de f-strings con comillas iguales anidadas (requiere Python 3.12; el paquete usa 3.10).

## Hoja de ruta (acordada con el autor, noviembre 2026)

1. **v1.2 — Windows** (`PuquichuSetup.exe` con Inno Setup), armado y probado por GitHub Actions en `windows-latest`.
   El autor preparará una máquina virtual con Windows para probarlo a mano. No hay que reescribir la app; falta:
   - Incluir **VLC (libvlc + plugins) y ffmpeg.exe** dentro del instalador (en Windows no hay dependencias automáticas).
   - Notificaciones con Qt (`QSystemTrayIcon`) en lugar de `notify-send`.
   - Teclas multimedia en Windows (MPRIS no existe ahí; ya es opcional).
   - Fuente: `Ubuntu Sans` no existe en Windows → *Segoe UI* o incluir la fuente.
   - Sin firma digital aparecerá "Windows protegió tu PC" (Más información → Ejecutar de todas formas);
     más adelante se puede pedir firma gratuita para código abierto (p. ej. SignPath).
2. **winget** (`winget install Puquichu`): registrar el `.exe` de Releases en `microsoft/winget-pkgs`. Gratis y rápido.
3. **Tiendas de Linux** (lo que el autor quiere: que aparezca en la tienda de Ubuntu/Debian):
   - **Snap Store** → aparece en el **App Center de Ubuntu** y en Discover. Requiere cuenta de Ubuntu One (gratis),
     reservar el nombre `puquichu`, un `snapcraft.yaml` (VLC y ffmpeg dentro del snap; interfaces `network`, `audio-playback`,
     `home`, `desktop`, `x11`/`wayland`, `mpris`) y publicar con `snapcraft upload` (puede automatizarse en Actions).
   - **Flathub** (Flatpak) → aparece en Discover, GNOME Software, Linux Mint, Fedora… Gratis; revisan la app.
   - Los repositorios oficiales de Debian/Ubuntu (`apt install puquichu` sin descargar nada) son un proceso largo
     de empaquetado y revisión; no es prioridad.
4. **macOS** (`.dmg` en `macos-latest`) y **Homebrew** (`brew install --cask puquichu`). Sin notarizar (99 USD/año),
   macOS pide abrirla con clic derecho → Abrir la primera vez.
5. **No recomendado:** Microsoft Store y App Store de Apple (suelen rechazar apps que descargan de YouTube).

## Ideas de funciones pendientes
Listas de reproducción propias, letras sincronizadas, carátula incrustada en archivos importados, normalización de volumen
y crossfade, ícono en la bandeja y mini-reproductor, arrastrar y soltar archivos, más rankings por país.
