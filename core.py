"""Puquichu — núcleo: configuración, base de datos, géneros y descargas (sin interfaz)."""
import contextlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

APP_NAME = "Puquichu"
APP_ID = "puquichu"
APP_VERSION = "1.2.2"

# =====================================================================
# RUTAS: modo "código fuente" (portable) o modo "instalado"
# =====================================================================
FROZEN = bool(getattr(sys, "frozen", False))  # True cuando corre desde el instalador

if FROZEN and sys.platform.startswith("linux"):
    # El paquete instalado agrega sus librerías a LD_LIBRARY_PATH. Los programas externos
    # (ffmpeg, xdg-open, notify-send…) deben usar las del sistema, o fallan en distros más nuevas.
    _orig_ld = os.environ.get("LD_LIBRARY_PATH_ORIG")
    if _orig_ld:
        os.environ["LD_LIBRARY_PATH"] = _orig_ld
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)
SOURCE_DIR = Path(__file__).resolve().parent
# Recursos de solo lectura (ícono, etc.): dentro del paquete instalado o junto al código
APP_DIR = Path(getattr(sys, "_MEIPASS", SOURCE_DIR))
ASSETS_DIR = APP_DIR / "assets"


def _user_data_dir() -> Path:
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_ID


def _user_music_dir() -> Path:
    """Carpeta 'Música' del usuario (respeta el idioma del sistema en Linux: ~/Música)."""
    if sys.platform.startswith("linux"):
        try:
            out = subprocess.run(["xdg-user-dir", "MUSIC"], capture_output=True, text=True, timeout=3).stdout.strip()
            if out and Path(out) != Path.home():
                return Path(out) / APP_NAME
        except Exception:
            pass
    for name in ("Música", "Music"):
        if (Path.home() / name).is_dir():
            return Path.home() / name / APP_NAME
    return Path.home() / "Music" / APP_NAME


# Si ya hay datos junto al código (instalación de desarrollo), se siguen usando ahí.
PORTABLE = not FROZEN and any(
    (SOURCE_DIR / f).exists() for f in ("puquichu.db", "spotify_local.db", "settings.json")
)
DATA_DIR = SOURCE_DIR if PORTABLE else _user_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_MUSIC_DIR = SOURCE_DIR / "musicplay" if PORTABLE else _user_music_dir()

BASE_DIR = DATA_DIR  # compatibilidad con código anterior
CONFIG_PATH = DATA_DIR / "settings.json"
DB_PATH = DATA_DIR / "puquichu.db"
_LEGACY_DB_PATH = DATA_DIR / "spotify_local.db"  # nombre anterior de la base de datos
THUMB_DIR = (SOURCE_DIR / "musicplay" / ".thumbnails") if PORTABLE else (DATA_DIR / "thumbnails")
THUMB_DIR.mkdir(parents=True, exist_ok=True)
def _user_cache_dir() -> Path:
    if sys.platform.startswith("win"):
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME / "cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / APP_NAME
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / APP_ID


# Caché privada del usuario (no /tmp, que es compartido con otros usuarios del equipo)
CACHE_DIR = _user_cache_dir()
CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
SEARCH_CACHE_DIR = CACHE_DIR / "busquedas"

# Migración del nombre de la base de datos sin perder datos
if _LEGACY_DB_PATH.exists() and not DB_PATH.exists():
    shutil.move(str(_LEGACY_DB_PATH), str(DB_PATH))

# =====================================================================
# MOTOR DE DESCARGAS (yt-dlp) — se puede actualizar sin reinstalar la app
# =====================================================================
YTDLP_OVERRIDE = DATA_DIR / "yt-dlp-actualizado.zip"
if YTDLP_OVERRIDE.exists():
    sys.path.insert(0, str(YTDLP_OVERRIDE))
try:
    import yt_dlp
except Exception:
    # La copia actualizada estaba dañada: se descarta y se usa la incluida
    if str(YTDLP_OVERRIDE) in sys.path:
        sys.path.remove(str(YTDLP_OVERRIDE))
    YTDLP_OVERRIDE.unlink(missing_ok=True)
    for mod in [m for m in sys.modules if m == "yt_dlp" or m.startswith("yt_dlp.")]:
        del sys.modules[mod]
    import yt_dlp

YTDLP_LATEST_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"


def ytdlp_version() -> str:
    return yt_dlp.version.__version__


def download_latest_ytdlp() -> str:
    """Descarga la última versión de yt-dlp (archivo zipapp) y devuelve su número de versión."""
    tmp = YTDLP_OVERRIDE.with_suffix(".tmp")
    req = urllib.request.Request(YTDLP_LATEST_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    with zipfile.ZipFile(tmp) as z:
        text = z.read("yt_dlp/version.py").decode("utf-8", "replace")
    match = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", text)
    if not match:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("El archivo descargado no parece una versión válida de yt-dlp.")
    tmp.replace(YTDLP_OVERRIDE)
    return match.group(1)


DEFAULT_SETTINGS = {
    "download_dir": str(DEFAULT_MUSIC_DIR),
    "organize_by_genre": True,
    "clean_filenames": True,
    "audio_format": "best",  # "best" (Opus original) | "m4a" (AAC) | "mp3_320" (recodificado)
    "listen_mode": "save",   # "save" = escuchar y guardar a la vez | "stream" = solo en línea
    "audio_device": "",      # "" = salida del sistema, o el ID del parlante elegido en Puquichu
    "auto_next": True,
    "default_volume": 85,
    "season_theme": "auto",      # "auto" | "puquy" (lluvias, verde) | "ichu" (seca, dorado)
    "notifications": True,
    "equalizer": -1,             # -1 = desactivado, o índice de preset de VLC
    "shuffle": False,
    "loop": False,
    "last_song_id": None,
    "last_position_ms": 0,
}

GENRES_LIST = [
    "Reggaeton",
    "Urbano / Trap",
    "Pop",
    "Rock",
    "Electrónica",
    "Salsa / Tropical",
    "Andina / Folklore",
    "Regional / Cumbia",
    "Balada / Romántica",
    "Otros",
]

GENRE_COLORS = {
    "Reggaeton": ("#f97316", "#ea580c"),       # Naranja vibrante
    "Urbano / Trap": ("#a855f7", "#7e22ce"),   # Púrpura
    "Pop": ("#ec4899", "#be185d"),             # Rosa
    "Rock": ("#ef4444", "#b91c1c"),            # Rojo
    "Electrónica": ("#06b6d4", "#0e7490"),     # Cian
    "Salsa / Tropical": ("#eab308", "#a16207"),# Dorado
    "Andina / Folklore": ("#c8743f", "#7a3b18"),  # Terracota de adobe
    "Regional / Cumbia": ("#22c55e", "#15803d"),# Verde
    "Balada / Romántica": ("#6366f1", "#4338ca"),# Índigo
    "Otros": ("#10b981", "#047857"),           # Esmeralda
}


def load_settings() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = {**DEFAULT_SETTINGS, **data}
                Path(merged["download_dir"]).mkdir(parents=True, exist_ok=True)
                return merged
        except Exception:
            pass
    Path(DEFAULT_SETTINGS["download_dir"]).mkdir(parents=True, exist_ok=True)
    save_settings(DEFAULT_SETTINGS)
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


# =====================================================================
# CLASIFICADOR INTELIGENTE DE GÉNEROS MUSICALES
# =====================================================================
GENRE_KEYWORDS = {
    "Andina / Folklore": [
        "huayno", "huaino", "wayno", "huaylas", "huaylash", "sanjuanito", "morenada", "caporales",
        "saya caporal", "tinku", "diablada", "carnaval ayacuchano", "carnaval de", "yaravi", "yaraví", "muliza",
        "pumpin", "tunantada", "chonguinada", "andina", "andino", "folklore", "folclore", "zampoña",
        "charango", "quena", "kjarkas", "savia andina", "kalamarka", "bolivia manta", "los jaivas",
        "william luna", "max castro", "dina paucar", "dina páucar", "sonia morales", "pastorita huaracina",
        "flor pucarina", "amanda portales", "hermanos gaitan castro", "gaitán castro", "alborada",
        "manuelcha prado", "raul garcia zarate", "ranulfo fuentes", "chimbango", "yarita lizeth",
        "los hijos del sol", "sentimiento andino", "inti illimani", "illapu",
    ],
    "Reggaeton": [
        "reggaeton", "regeton", "perreo", "dembow", "daddy yankee", "bad bunny",
        "myke towers", "karol g", "feid", "ferxxo", "ozuna", "j balvin", "maluma",
        "rauw alejandro", "nicky jam", "wisin", "yandel", "don omar", "plan b",
        "chencho", "arcangel", "farruko", "sech", "ryan castro", "blessd",
        "jhayco", "jhay cortez", "zion", "lennox", "tegom", "tego calderon",
        "anuel", "young miko", "quevedo", "cris mj", " Mora ", "dalex", "justin quiles",
    ],
    "Urbano / Trap": [
        "trap", "hip hop", "rap", "drill", "freestyle", "bizarrap", "bzrp",
        "duki", "eladio carrion", "bryant myers", "almighty", "cazzu", "khea",
        "trueno", "wos", "Paulo Londra", "ele a el dominio", "eminem", "drake", "travis scott",
        "kendrick lamar", "50 cent", "snoop dogg",
    ],
    "Rock": [
        "rock", "metal", "punk", "grunge", "indie rock", "alternative",
        "queen", "bohemian rhapsody", "nirvana", "metallica", "guns n' roses",
        "ac/dc", "linkin park", "red hot chili", "coldplay", "soda stereo",
        "cerati", "caifanes", "mana", "heroes del silencio", "enanitos verdes",
        "rolling stones", "beatles", "pink floyd", "led zeppelin", "oasis",
    ],
    "Electrónica": [
        "electronic", "edm", "house", "techno", "trance", "dubstep", "remix",
        "tiesto", "david guetta", "calvin harris", "avicii", "martin garrix",
        "skrillex", "marshmello", "alan walker", "daft punk", "kygo", "alok",
    ],
    "Salsa / Tropical": [
        "salsa", "bachata", "merengue", "tropical", "romeo santos", "aventura",
        "marc anthony", "hector lavoe", "willie colon", "gilberto santa rosa",
        "grupo niche", "joe arroyo", "juan luis guerra", "prince royce", "eddie santiago",
    ],
    "Regional / Cumbia": [
        "cumbia", "regional", "banda", "corrido", "norteño", "ranchera", "mariachi",
        "vallenato", "peso pluma", "christian nodal", "grupo frontera", "carin leon",
        "fuerza regida", "natanael cano", "los angeles azules", "carlos vives",
    ],
    "Balada / Romántica": [
        "balada", "bolero", "romantica", "luis miguel", "ricardo arjona",
        "chayanne", "camila", "sin bandera", "reik", "jesse & joy", "pablo alboran",
        "alejandro sanz", "sebastian yatra", "morat", "adele", "ed sheeran",
    ],
    "Pop": [
        "pop", "shakira", "michael jackson", "dua lipa", "the weeknd", "bruno mars",
        "taylor swift", "ariana grande", "lady gaga", "justin bieber", "katy perry",
        "rihanna", "rosalia", "aitana", "tini", "camilo", "kali uchis",
    ],
}


def detect_genre(title: str, artist: str = "", tags: list | None = None, categories: list | None = None) -> str:
    haystack = " ".join(
        [
            title or "",
            artist or "",
            " ".join(tags or []),
            " ".join(categories or []),
        ]
    ).lower()

    for genre, keywords in GENRE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in haystack:
                return genre
    return "Otros"


def safe_id(value) -> str:
    """Solo letras, números, guion y guion bajo: para usar IDs de internet como nombre de archivo."""
    return re.sub(r"[^A-Za-z0-9_-]", "", str(value or ""))[:80] or "sin_id"


def download_file(url: str, dest: Path, timeout: int = 15, max_bytes: int = 15 * 1024 * 1024) -> bool:
    """Descarga con límite de tiempo y de tamaño; escribe a un temporal y luego lo mueve (nunca deja archivos a medias)."""
    if not url.startswith("https://"):
        return False
    tmp = dest.with_name(dest.name + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
            total = 0
            while chunk := r.read(64 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("archivo demasiado grande")
                f.write(chunk)
        tmp.replace(dest)
        return True
    except Exception:
        tmp.unlink(missing_ok=True)
        return False


def genre_folder(genre: str) -> str:
    """Nombre de carpeta seguro: 'Urbano / Trap' -> 'Urbano - Trap' (la '/' creaba carpetas anidadas)."""
    return sanitize_filename((genre or "Otros").replace("/", "-"))


def remove_empty_dirs(base: Path):
    """Borra carpetas vacías que quedaron tras mover canciones (no toca las ocultas)."""
    for d in sorted((p for p in base.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if any(part.startswith(".") for part in d.relative_to(base).parts):
            continue
        try:
            d.rmdir()  # solo funciona si está vacía
        except OSError:
            pass


def sanitize_filename(name: str) -> str:
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:110] or "Cancion_Local"


# =====================================================================
# GESTIÓN DE BASE DE DATOS Y ORGANIZACIÓN DE ARCHIVOS
# =====================================================================
_WAL_READY = False


@contextlib.contextmanager
def get_db():
    """Conexión a la base de datos: confirma los cambios al terminar y siempre se cierra.

    timeout=15 espera si otro hilo (p. ej. una descarga) está escribiendo, en vez de fallar con
    "database is locked"; el modo WAL permite leer mientras se escribe.
    """
    global _WAL_READY
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    if not _WAL_READY:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            _WAL_READY = True
        except sqlite3.DatabaseError:
            pass
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def clean_interrupted_downloads(settings: dict, max_age_hours: int = 6):
    """Borra restos de descargas interrumpidas (p. ej. si se cerró la app a mitad de una descarga)."""
    tmp = Path(settings.get("download_dir", "")) / ".tmp"
    if not tmp.is_dir():
        return
    limit = datetime.now().timestamp() - max_age_hours * 3600
    for f in tmp.iterdir():
        try:
            if f.is_file() and f.stat().st_mtime < limit:
                f.unlink()
        except OSError:
            pass


def init_and_migrate_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                artist TEXT DEFAULT 'Artista Desconocido',
                genre TEXT DEFAULT 'Otros',
                search_term TEXT,
                file_path TEXT NOT NULL,
                thumbnail_path TEXT DEFAULT '',
                duration INTEGER DEFAULT 0,
                play_count INTEGER DEFAULT 1,
                last_played DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Migración automática de columnas nuevas si la tabla ya existía
        existing_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(songs)").fetchall()
        }
        migrations = [
            ("artist", "TEXT DEFAULT 'Artista Desconocido'"),
            ("genre", "TEXT DEFAULT 'Otros'"),
            ("thumbnail_path", "TEXT DEFAULT ''"),
            ("duration", "INTEGER DEFAULT 0"),
            ("favorite", "INTEGER DEFAULT 0"),
            ("source_id", "TEXT DEFAULT ''"),
            ("added_at", "DATETIME"),
        ]
        for col_name, col_def in migrations:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE songs ADD COLUMN {col_name} {col_def}")
        # Recuperar el ID de YouTube de las miniaturas ya descargadas (nombre = <id>.jpg)
        conn.execute(
            "UPDATE songs SET source_id = REPLACE(REPLACE(thumbnail_path, RTRIM(thumbnail_path, REPLACE(thumbnail_path, '/', '')), ''), '.jpg', '') "
            "WHERE (source_id IS NULL OR source_id = '') AND thumbnail_path LIKE '%.jpg'"
        )
        conn.execute("UPDATE songs SET added_at = last_played WHERE added_at IS NULL")
        conn.commit()


def extract_artist_from_title(title: str, fallback: str = "YouTube Music") -> str:
    for sep in [" - ", " | ", " – "]:
        if sep in title:
            parts = title.split(sep, 1)
            if 1 < len(parts[0].strip()) < 40:
                return parts[0].strip().title()
    return fallback


def organize_and_classify_all_songs(settings: dict) -> int:
    """
    Clasifica automáticamente las canciones por género (Reggaeton, Rock, etc.)
    y si 'organize_by_genre' está activo, las mueve a subcarpetas por género
    con nombres de archivo limpios.
    """
    base_dl = Path(settings["download_dir"])
    base_dl.mkdir(parents=True, exist_ok=True)
    moved_count = 0

    with get_db() as conn:
        rows = conn.execute("SELECT * FROM songs").fetchall()
        for row in rows:
            song_id = row["id"]
            title = row["title"]
            artist = row["artist"] or "Artista Desconocido"
            if artist in ("Artista Desconocido", "YouTube Music"):
                artist = extract_artist_from_title(title, artist)

            genre = row["genre"]
            if not genre or genre == "Otros":
                genre = detect_genre(title, artist)

            current_path = Path(row["file_path"])
            new_path = current_path

            if current_path.exists():
                ext = current_path.suffix or ".m4a"
                target_dir = base_dl / genre_folder(genre) if settings.get("organize_by_genre", True) else base_dl
                target_dir.mkdir(parents=True, exist_ok=True)

                if settings.get("clean_filenames", True):
                    desired_name = f"{sanitize_filename(title)}{ext}"
                else:
                    desired_name = current_path.name

                candidate = target_dir / desired_name
                if candidate.resolve() != current_path.resolve() and not candidate.exists():
                    try:
                        shutil.move(str(current_path), str(candidate))
                        new_path = candidate
                        moved_count += 1
                    except Exception:
                        new_path = current_path

            conn.execute(
                """
                UPDATE songs
                SET artist = ?, genre = ?, file_path = ?
                WHERE id = ?
                """,
                (artist, genre, str(new_path), song_id),
            )
        conn.commit()
    remove_empty_dirs(base_dl)
    return moved_count


# =====================================================================
# HILO DE BÚSQUEDA Y DESCARGA (yt-dlp + Clasificación por Género)
# =====================================================================
def audio_format_options(audio_fmt: str, for_stream: bool = False) -> dict:
    """Opciones de yt-dlp según la calidad elegida.

    YouTube entrega como máximo Opus ~135-160 kbps (formato 251) o AAC ~128 kbps (formato 140).
    'best' guarda el Opus original sin recodificar (la mejor calidad real).
    'mp3_320' recodifica: más compatible con radios/USB, pero no suena mejor que el original.
    """
    has_ffmpeg = shutil.which("ffmpeg") is not None
    if audio_fmt == "m4a":
        return {"format": "bestaudio[ext=m4a]/bestaudio/best"}
    if audio_fmt == "mp3_320" and not for_stream and has_ffmpeg:
        return {
            "format": "bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"}],
        }
    opts = {"format": "bestaudio[acodec=opus]/bestaudio/best"}
    if not for_stream and has_ffmpeg:
        # Extrae el Opus del contenedor .webm a .opus sin perder calidad (copia directa)
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "opus"}]
    return opts


class SearchDownloadWorker(QThread):
    status_changed = pyqtSignal(str)
    completed = pyqtSignal(dict, bool)  # (song_dict, was_downloaded)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int)  # 0-100, -1 = indeterminado

    def __init__(self, query: str, settings: dict, url: str = "", video_id: str = ""):
        super().__init__()
        self.query = query.strip()
        self.settings = settings
        self.url = url
        self.video_id = video_id

    def run(self):
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if self.url:
                self._download(now)
                return
            self.status_changed.emit(f"Buscando «{self.query}» en tu biblioteca local...")

            # 1. Buscar coincidencia en SQLite local
            with get_db() as conn:
                row = conn.execute(
                    """
                    SELECT * FROM songs
                    WHERE LOWER(title) LIKE LOWER(?)
                       OR LOWER(search_term) = LOWER(?)
                       OR LOWER(artist) LIKE LOWER(?)
                    ORDER BY play_count DESC
                    LIMIT 1
                    """,
                    (f"%{self.query}%", self.query, f"%{self.query}%"),
                ).fetchone()

                if row and os.path.exists(row["file_path"]):
                    conn.execute(
                        "UPDATE songs SET play_count = play_count + 1, last_played = ? WHERE id = ?",
                        (now, row["id"]),
                    )
                    conn.commit()
                    updated = conn.execute(
                        "SELECT * FROM songs WHERE id = ?", (row["id"],)
                    ).fetchone()
                    self.completed.emit(dict(updated), False)
                    return

            self._download(now)
        except Exception as e:
            self.failed.emit(str(e))

    def _progress_hook(self, d: dict):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                self.progress.emit(int(d.get("downloaded_bytes", 0) * 100 / total))
        elif d.get("status") == "finished":
            self.progress.emit(-1)

    def _download(self, now: str):
        try:
            if self.video_id:
                with get_db() as conn:
                    row = conn.execute(
                        "SELECT * FROM songs WHERE source_id = ? ORDER BY id LIMIT 1", (self.video_id,)
                    ).fetchone()
                if row and os.path.exists(row["file_path"]):
                    self.completed.emit(dict(row), False)
                    return

            # 2. No existe localmente -> Extraer metadata y descargar de YouTube
            self.status_changed.emit(f"Descargando «{self.query}»…")
            base_dl = Path(self.settings["download_dir"])
            base_dl.mkdir(parents=True, exist_ok=True)
            temp_dir = base_dl / ".tmp"
            temp_dir.mkdir(parents=True, exist_ok=True)

            audio_fmt = self.settings.get("audio_format", "best")
            ydl_opts = {
                "outtmpl": str(temp_dir / "%(id)s.%(ext)s"),
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "noprogress": True,
                "socket_timeout": 20,
                "progress_hooks": [self._progress_hook],
            }

            ydl_opts.update(audio_format_options(audio_fmt))

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if self.url:
                    video = ydl.extract_info(self.url, download=True)
                else:
                    info = ydl.extract_info(f"ytsearch1:{self.query}", download=True)
                    if not info or "entries" not in info or not info["entries"]:
                        self.failed.emit("No se encontraron resultados en YouTube.")
                        return
                    video = info["entries"][0]
                if not video:
                    self.failed.emit("YouTube no devolvió información del video.")
                    return
                vid_id = video.get("id", "audio")
                title = video.get("title", self.query)
                uploader = video.get("artist") or video.get("creator") or video.get("uploader") or ""
                artist = extract_artist_from_title(title, uploader or "YouTube Music")
                tags = video.get("tags") or []
                categories = video.get("categories") or []
                duration = int(video.get("duration") or 0)
                thumb_url = video.get("thumbnail") or ""

                # Detectar el archivo descargado en temp_dir
                downloaded_file = None
                candidates = [c for c in temp_dir.glob(f"{vid_id}.*") if c.suffix not in (".part", ".ytdl", ".jpg", ".webp")]
                if candidates:
                    downloaded_file = max(candidates, key=lambda c: c.stat().st_mtime)
                if not downloaded_file:
                    prep = Path(ydl.prepare_filename(video))
                    if prep.exists():
                        downloaded_file = prep

                if not downloaded_file or not downloaded_file.exists():
                    self.failed.emit("Error al guardar el archivo de audio descargado.")
                    return

                # 3. Clasificar género automáticamente (Reggaeton, Rock, Pop, etc.)
                genre = detect_genre(title, artist, tags, categories)
                self.status_changed.emit(
                    f"Clasificado como [{genre}]. Organizando en tu biblioteca..."
                )

                target_folder = base_dl / genre_folder(genre) if self.settings.get("organize_by_genre", True) else base_dl
                target_folder.mkdir(parents=True, exist_ok=True)

                ext = downloaded_file.suffix
                if self.settings.get("clean_filenames", True):
                    final_filename = f"{sanitize_filename(title)}{ext}"
                else:
                    final_filename = downloaded_file.name

                final_path = target_folder / final_filename
                if final_path.exists():
                    final_path = target_folder / f"{Path(final_filename).stem} [{vid_id}]{ext}"
                shutil.move(str(downloaded_file), str(final_path))

                # 4. Descargar carátula / miniatura local
                thumb_local = ""
                if thumb_url:
                    try:
                        thumb_dest = THUMB_DIR / f"{safe_id(vid_id)}.jpg"
                        if download_file(thumb_url, thumb_dest):
                            thumb_local = str(thumb_dest)
                    except Exception:
                        thumb_local = ""

            # 5. Guardar en SQLite
            with get_db() as conn:
                existing = conn.execute(
                    "SELECT * FROM songs WHERE file_path = ?", (str(final_path),)
                ).fetchone()

                if existing:
                    conn.execute(
                        """
                        UPDATE songs
                        SET play_count = play_count + 1, last_played = ?, genre = ?, artist = ?, source_id = ?
                        WHERE id = ?
                        """,
                        (now, genre, artist, vid_id, existing["id"]),
                    )
                    conn.commit()
                    updated = conn.execute(
                        "SELECT * FROM songs WHERE id = ?", (existing["id"],)
                    ).fetchone()
                    self.completed.emit(dict(updated), False)
                else:
                    cursor = conn.execute(
                        """
                        INSERT INTO songs
                        (title, artist, genre, search_term, file_path, thumbnail_path, duration,
                         play_count, last_played, source_id, added_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                        """,
                        (
                            title,
                            artist,
                            genre,
                            self.query,
                            str(final_path),
                            thumb_local,
                            duration,
                            now,
                            vid_id,
                            now,
                        ),
                    )
                    conn.commit()
                    new_row = conn.execute(
                        "SELECT * FROM songs WHERE id = ?", (cursor.lastrowid,)
                    ).fetchone()
                    self.completed.emit(dict(new_row), True)

        except Exception as e:
            self.failed.emit(str(e))


# =====================================================================
# BÚSQUEDA CON VARIOS RESULTADOS (elige la versión correcta antes de descargar)
# =====================================================================
def search_local_songs(query: str, limit: int = 4) -> list[dict]:
    like = f"%{query.strip()}%"
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM songs
            WHERE title LIKE ? OR artist LIKE ? OR search_term LIKE ?
            ORDER BY play_count DESC LIMIT ?
            """,
            (like, like, like, limit),
        ).fetchall()
    return [dict(r) for r in rows if os.path.exists(r["file_path"])]


def _fetch_search_thumb(video_id: str) -> str:
    SEARCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    vid = safe_id(video_id)
    dest = SEARCH_CACHE_DIR / f"{vid}.jpg"
    if not dest.exists() and not download_file(f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg", dest):
        return ""
    return str(dest)


class YouTubeSearchWorker(QThread):
    """Busca varias opciones en YouTube (sin descargar audio) para que el usuario elija."""

    results_ready = pyqtSignal(str, list, list)  # (query, locales, youtube)
    failed = pyqtSignal(str, str)

    def __init__(self, query: str, max_results: int = 8):
        super().__init__()
        self.query = query.strip()
        self.max_results = max_results

    def run(self):
        local = search_local_songs(self.query)
        try:
            opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist", "skip_download": True, "socket_timeout": 20}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"ytsearch{self.max_results}:{self.query}", download=False)
            entries = [e for e in (info or {}).get("entries") or [] if e and e.get("id")]
        except Exception as e:
            self.failed.emit(self.query, str(e))
            if local:
                self.results_ready.emit(self.query, local, [])
            return

        with get_db() as conn:
            known = {
                r["source_id"]: dict(r)
                for r in conn.execute("SELECT * FROM songs WHERE source_id != ''").fetchall()
            }

        with ThreadPoolExecutor(max_workers=6) as pool:
            thumbs = list(pool.map(_fetch_search_thumb, [e["id"] for e in entries]))

        results = []
        for entry, thumb in zip(entries, thumbs):
            vid = entry["id"]
            local_song = known.get(vid)
            if local_song and not os.path.exists(local_song["file_path"]):
                local_song = None
            results.append(
                {
                    "id": vid,
                    "title": entry.get("title") or "Sin título",
                    "channel": entry.get("channel") or entry.get("uploader") or "",
                    "duration": int(entry.get("duration") or 0),
                    "views": int(entry.get("view_count") or 0),
                    "url": entry.get("url") or f"https://www.youtube.com/watch?v={vid}",
                    "thumb": thumb,
                    "local_song": local_song,
                }
            )
        self.results_ready.emit(self.query, local, results)


# =====================================================================
# ESCUCHAR AL INSTANTE (en línea mientras se guarda)
# =====================================================================
_UNWANTED_VERSIONS = ("live", "en vivo", "karaoke", "cover", "remix", "slowed", "sped up", "8d", "instrumental", "reaction")


def pick_best_video(entries: list[dict], query: str, target_duration: int = 0) -> dict | None:
    """Elige el video que mejor coincide (duración parecida y sin versiones raras)."""
    q = query.lower()
    best, best_score = None, None
    for rank, e in enumerate(entries):
        if not e or not e.get("id"):
            continue
        title = (e.get("title") or "").lower()
        score = rank * 2.0
        score += sum(8 for w in _UNWANTED_VERSIONS if w in title and w not in q)
        dur = int(e.get("duration") or 0)
        if target_duration and dur:
            score += min(abs(dur - target_duration) / 6.0, 20)
        elif dur > 900:
            score += 10  # mixes de más de 15 min
        if best_score is None or score < best_score:
            best, best_score = e, score
    return best


class OnlinePlayWorker(QThread):
    """Consigue el enlace de audio para reproducir en ~2 s, sin esperar a la descarga."""

    ready = pyqtSignal(int, dict, str)  # (token, item, stream_url)
    failed = pyqtSignal(int, str)

    def __init__(self, token: int, item: dict, audio_fmt: str):
        super().__init__()
        self.token = token
        self.item = dict(item)
        self.audio_fmt = audio_fmt

    def run(self):
        try:
            item = self.item
            base = {"quiet": True, "no_warnings": True, "noplaylist": True, "socket_timeout": 20}
            if not item.get("id"):
                query = item["query"]
                with yt_dlp.YoutubeDL({**base, "extract_flat": "in_playlist"}) as ydl:
                    info = ydl.extract_info(f"ytsearch6:{query}", download=False)
                chosen = pick_best_video(info.get("entries") or [], query, int(item.get("duration") or 0))
                if not chosen:
                    self.failed.emit(self.token, "No se encontró esa canción en YouTube.")
                    return
                item.update(
                    id=chosen["id"],
                    url=chosen.get("url") or f"https://www.youtube.com/watch?v={chosen['id']}",
                    yt_title=chosen.get("title") or "",
                    channel=chosen.get("channel") or chosen.get("uploader") or "",
                )
                if not item.get("duration"):
                    item["duration"] = int(chosen.get("duration") or 0)
            with yt_dlp.YoutubeDL({**base, **audio_format_options(self.audio_fmt, for_stream=True)}) as ydl:
                info = ydl.extract_info(item["url"], download=False)
            stream_url = info.get("url") or ""
            if not stream_url:
                self.failed.emit(self.token, "YouTube no entregó el audio.")
                return
            item.setdefault("title", info.get("title") or "")
            item["duration"] = int(info.get("duration") or item.get("duration") or 0)
            if not item.get("thumb"):
                item["thumb"] = _fetch_search_thumb(item["id"])
            self.ready.emit(self.token, item, stream_url)
        except Exception as e:
            self.failed.emit(self.token, str(e))


# =====================================================================
# EXPLORAR: rankings de Deezer (públicos, sin cuenta)
# =====================================================================
DEEZER_SOURCES = {
    "peru": ("Top Perú", "https://api.deezer.com/playlist/1362518525/tracks?limit=50"),
    "global": ("Top mundial", "https://api.deezer.com/chart/0/tracks?limit=50"),
}
CHART_CACHE_HOURS = 6


def _fetch_cover(url: str, key: str) -> str:
    if not url:
        return ""
    SEARCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = SEARCH_CACHE_DIR / f"dz_{safe_id(key)}.jpg"
    if not dest.exists() and not download_file(url, dest):
        return ""
    return str(dest)


def fetch_deezer_chart(kind: str) -> list[dict]:
    _title, url = DEEZER_SOURCES[kind]
    SEARCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = SEARCH_CACHE_DIR / f"chart_{kind}.json"
    if cache.exists() and (datetime.now().timestamp() - cache.stat().st_mtime) < CHART_CACHE_HOURS * 3600:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=12) as r:
        data = json.loads(r.read().decode("utf-8")).get("data") or []
    with ThreadPoolExecutor(max_workers=8) as pool:
        covers = list(
            pool.map(lambda t: _fetch_cover((t.get("album") or {}).get("cover_big", ""), str((t.get("album") or {}).get("id", t.get("id")))), data)
        )
    tracks = []
    for t, cover in zip(data, covers):
        artist = (t.get("artist") or {}).get("name", "")
        title = t.get("title_short") or t.get("title") or ""
        tracks.append(
            {
                "title": title,
                "artist": artist,
                "duration": int(t.get("duration") or 0),
                "cover": cover,
                "query": f"{artist} - {title}",
            }
        )
    cache.write_text(json.dumps(tracks, ensure_ascii=False), encoding="utf-8")
    return tracks


class ChartWorker(QThread):
    ready = pyqtSignal(str, list)
    failed = pyqtSignal(str, str)

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind

    def run(self):
        try:
            self.ready.emit(self.kind, fetch_deezer_chart(self.kind))
        except Exception as e:
            self.failed.emit(self.kind, str(e))


# =====================================================================
# TOP DE UN ARTISTA (Deezer: coincidencia exacta del nombre, el de más fans)
# =====================================================================
def _norm_name(text: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", (text or "").lower()) if unicodedata.category(c) != "Mn").strip()


def _deezer_get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_deezer_artist_top(artist: str, limit: int = 15) -> list[dict]:
    """Canciones más escuchadas del artista; [] si no hay coincidencia segura."""
    if not artist or _norm_name(artist) in ("artista desconocido", "youtube", "youtube music"):
        return []
    SEARCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = SEARCH_CACHE_DIR / f"artist_{safe_id(re.sub(r'[^a-z0-9]+', '_', _norm_name(artist)))}.json"
    if cache.exists() and (datetime.now().timestamp() - cache.stat().st_mtime) < 24 * 3600:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    found = _deezer_get("https://api.deezer.com/search/artist?limit=15&q=" + urllib.parse.quote(artist)).get("data") or []
    exact = [a for a in found if _norm_name(a.get("name", "")) == _norm_name(artist)]
    tracks: list[dict] = []
    if exact:
        best = max(exact, key=lambda a: a.get("nb_fan", 0))
        data = _deezer_get(f"https://api.deezer.com/artist/{best['id']}/top?limit={limit}").get("data") or []
        with ThreadPoolExecutor(max_workers=8) as pool:
            covers = list(pool.map(
                lambda t: _fetch_cover((t.get("album") or {}).get("cover_big", ""), str((t.get("album") or {}).get("id", t.get("id")))),
                data,
            ))
        for t, cover in zip(data, covers):
            title = t.get("title_short") or t.get("title") or ""
            name = (t.get("artist") or {}).get("name", best["name"])
            tracks.append({"title": title, "artist": name, "duration": int(t.get("duration") or 0), "cover": cover, "query": f"{name} - {title}"})
    cache.write_text(json.dumps(tracks, ensure_ascii=False), encoding="utf-8")
    return tracks


class ArtistTopWorker(QThread):
    ready = pyqtSignal(str, list)
    failed = pyqtSignal(str, str)

    def __init__(self, artist: str):
        super().__init__()
        self.artist = artist

    def run(self):
        try:
            self.ready.emit(self.artist, fetch_deezer_artist_top(self.artist))
        except Exception as e:
            self.failed.emit(self.artist, str(e))
