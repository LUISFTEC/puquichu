# Puquichu 🌱

**Reproductor de música de escritorio para Linux** — busca una canción, suena al instante y queda guardada en tu equipo para escucharla sin internet.

> **puquy** (quechua): la temporada de lluvias, cuando brota el pasto verde en la sierra.
> **ichu** (quechua): el pasto de la puna, dorado en la temporada seca.
> Los colores de la app son esas dos estaciones del campo andino.

Hecho con **Python + PyQt6 + VLC + SQLite + yt-dlp**. Es una aplicación nativa de escritorio (no es una app web).

---

## ✨ Funciones

**Escuchar**
- **Local primero**: si ya tienes la canción, suena desde tu disco al instante y sin internet.
- **Escucha al instante** (~2 s) cualquier canción de internet; por defecto **se guarda a la vez** en segundo plano en la mejor calidad disponible (Opus original, sin recodificar).
- Modo **solo en línea** opcional, para no ocupar espacio.
- **Búsqueda con varios resultados** para elegir la versión correcta (oficial, en vivo, con letra…).

**Descubrir**
- **Explorar**: Top Perú, Top mundial y lo más escuchado por género (Huayno, Folklore andino, Cumbia peruana, Chicha, Salsa, Reggaetón…).
- **Página de cada canción** con detalles del archivo y el **top real del artista**.

**Organizar**
- Clasificación automática por género (incluye **Andina / Folklore**) y carpetas ordenadas.
- **Favoritas**, cola **"A continuación"**, historial, editar información y eliminar canciones.
- Importar música que ya tengas (MP3, M4A, FLAC, OGG…).

**Escritorio**
- Tema por estación: **Puquy** (verde), **Ichu** (dorado) o automático según el mes.
- Integración **MPRIS**: control desde el panel de KDE/GNOME y teclas multimedia.
- Ecualizador, temporizador para dormir, notificaciones y atajos de teclado.
- Retoma la última canción donde la dejaste.

---

## 📦 Instalación

Probado en **Ubuntu / Kubuntu (KDE Plasma, X11)** con Python 3.12+.

```bash
# 1. Dependencias del sistema
sudo apt install vlc ffmpeg libnotify-bin python3-venv

# 2. Clonar y crear el entorno
git clone <URL-del-repositorio> puquichu
cd puquichu
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# 3. Ejecutar
venv/bin/python3 app.py
```

### Acceso directo en el menú de aplicaciones (opcional)

Crea `~/.local/share/applications/puquichu.desktop` (cambia `RUTA` por la carpeta donde clonaste el proyecto):

```ini
[Desktop Entry]
Name=Puquichu
Comment=Busca, escucha y guarda tu música
Exec=RUTA/venv/bin/python3 RUTA/app.py
Path=RUTA
Icon=RUTA/assets/puquichu.png
Terminal=false
Type=Application
Categories=AudioVideo;Audio;Player;
StartupWMClass=puquichu
```

---

## ⌨️ Atajos

| Teclas | Acción |
|---|---|
| `Espacio` | Reproducir / pausar |
| `Ctrl + F` | Buscar |
| `Ctrl + → / ←` | Siguiente / anterior |
| `Shift + → / ←` | Adelantar / retroceder 10 s |
| `Ctrl + ↑ / ↓` | Volumen |
| `Ctrl + M` | Silenciar |
| `Ctrl + D` | Me gusta |
| `Ctrl + S / R` | Aleatorio / repetir |
| `Ctrl + 1 … 5` | Inicio, Explorar, Biblioteca, Favoritas, Ajustes |

---

## 🗂️ Estructura del proyecto

| Archivo | Contenido |
|---|---|
| `app.py` | Ventana principal (`PuquichuApp`): páginas, reproductor, cola, búsqueda, escuchar en línea, guardado, atajos, sesión. |
| `core.py` | Lógica sin interfaz: configuración, base de datos y migraciones, detección de género, organización de archivos y los hilos de trabajo (`SearchDownloadWorker`, `YouTubeSearchWorker`, `OnlinePlayWorker`, `ChartWorker`, `ArtistTopWorker`). |
| `theme.py` | Sistema de diseño: paleta de estaciones (`SEASONS`, `C`), iconos vectoriales (`draw_icon`), logo, carátulas y hoja de estilos (`build_qss`). |
| `widgets.py` | Componentes dibujados a mano: barra de título, tarjetas, filas de resultados, tabla de biblioteca, diálogos, avisos, interruptores, barra deslizante. |
| `mpris.py` | Integración MPRIS2 por D-Bus. |
| `assets/` | Ícono de la aplicación. |

Archivos que crea la app al usarla (no se suben a git): `settings.json` (preferencias), `puquichu.db` (biblioteca SQLite) y `musicplay/` (música guardada, en subcarpetas por género, y carátulas en `.thumbnails/`).

### Base de datos (`songs`)
`id`, `title`, `artist`, `genre`, `search_term`, `file_path`, `thumbnail_path`, `duration`, `play_count`, `last_played`, `favorite`, `source_id` (ID del video, evita duplicados), `added_at`.

---

## 🤝 Cómo colaborar

¡Las contribuciones son bienvenidas! Lee [CONTRIBUTING.md](CONTRIBUTING.md). Ideas pendientes:

- Listas de reproducción propias.
- Letras de canciones sincronizadas.
- Carátula incrustada en archivos importados.
- Normalización de volumen y transición suave (crossfade).
- Ícono en la bandeja del sistema y mini-reproductor.
- Arrastrar y soltar archivos para importarlos.
- Más rankings por país.

---

## 📄 Licencia

Puquichu es software libre bajo la licencia **GNU GPL v3** (ver [LICENSE](LICENSE)): puedes usarlo, estudiarlo, modificarlo y compartirlo, siempre que las versiones modificadas también se compartan bajo la misma licencia.

## ⚖️ Aviso legal

Puquichu es una herramienta para **uso personal**. Las búsquedas y la reproducción en línea usan [yt-dlp](https://github.com/yt-dlp/yt-dlp); los rankings provienen de la API pública de Deezer. El proyecto **no incluye ni distribuye música**.

Cada usuario es responsable de respetar los derechos de autor y los términos de servicio de las plataformas que use. Descargar contenido protegido sin permiso puede no estar permitido en tu país o por esos términos. Apoya a los artistas que escuchas.

---

## 🤖 Notas para asistentes de IA / agentes de código

1. Es una **app de escritorio nativa**: no convertirla en web ni levantar servidores salvo pedido explícito.
2. Usar el entorno virtual del proyecto: `venv/bin/python3`.
3. **No perder datos del usuario**: columnas nuevas solo con `ALTER TABLE` dentro de `init_and_migrate_db()` (`core.py`).
4. Colores: usar los tokens de `C` (`theme.py`), nunca hex sueltos para el acento, para que el cambio de estación funcione.
5. Iconos: agregarlos en `draw_icon()` (`theme.py`); no usar emojis en la interfaz.
6. Para probar la interfaz sin abrir ventana: `QT_QPA_PLATFORM=offscreen` y `widget.grab().save(...)`.

---

## 🙌 Créditos

Creado por **[LUISFTEC](https://github.com/LUISFTEC)**, con ayuda de **Claude** (asistente de inteligencia artificial de Anthropic) en el diseño y la programación.

Construido sobre [PyQt6](https://www.riverbankcomputing.com/software/pyqt/), [VLC / python-vlc](https://www.videolan.org/), [yt-dlp](https://github.com/yt-dlp/yt-dlp) y la API pública de [Deezer](https://developers.deezer.com/).
