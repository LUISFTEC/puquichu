#!/usr/bin/env python3
"""Puquichu — reproductor de música de escritorio para Ubuntu/KDE.

puquy (quechua): la temporada de lluvias, cuando brota el pasto verde.
ichu  (quechua): el pasto de la puna, dorado en la temporada seca.
"""
import os
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import vlc
from PyQt6.QtCore import QPoint, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core import (
    APP_ID,
    APP_NAME,
    APP_VERSION,
    ASSETS_DIR,
    DATA_DIR,
    download_latest_ytdlp,
    ytdlp_version,
    BASE_DIR,
    DEEZER_SOURCES,
    GENRES_LIST,
    SEARCH_CACHE_DIR,
    ArtistTopWorker,
    ChartWorker,
    OnlinePlayWorker,
    SearchDownloadWorker,
    YouTubeSearchWorker,
    detect_genre,
    extract_artist_from_title,
    genre_folder,
    get_db,
    init_and_migrate_db,
    load_settings,
    organize_and_classify_all_songs,
    save_settings,
)
try:  # MPRIS solo existe en Linux (D-Bus)
    from mpris import MprisService, build_metadata
except Exception:  # pragma: no cover - Windows / macOS
    MprisService = None

    def build_metadata(*_args, **_kw):
        return {}
from theme import (
    SEASONS,
    C,
    UI_FONT,
    apply_season,
    brand_logo,
    build_qss,
    create_artwork_pixmap,
    display_title,
    dominant_color,
    fmt_seconds,
    humanize_dt,
    make_icon,
    make_icon_pixmap,
    resolve_season,
    save_brand_icon,
)
from widgets import (
    ROLE_PLAYING,
    ROLE_SONG,
    ChartCard,
    ClickSlider,
    EditSongDialog,
    ElidedLabel,
    GenreTile,
    HeroCard,
    LibraryDelegate,
    LibraryTable,
    ResultRow,
    RootWidget,
    SongCard,
    TitleBar,
    Toast,
    ToggleSwitch,
    TopSongDelegate,
    ask,
    show_message,
)

ICON_PATH = ASSETS_DIR / "puquichu.png" if (ASSETS_DIR / "puquichu.png").exists() else DATA_DIR / "puquichu.png"
FAV_FILTER = "__fav__"

EQ_NAMES_ES = {
    "Flat": "Plano",
    "Classical": "Clásica",
    "Club": "Club",
    "Dance": "Dance",
    "Full bass": "Graves potentes",
    "Full bass and treble": "Graves y agudos",
    "Full treble": "Agudos potentes",
    "Headphones": "Audífonos",
    "Large Hall": "Sala grande",
    "Live": "En vivo",
    "Party": "Fiesta",
    "Pop": "Pop",
    "Reggae": "Reggae",
    "Rock": "Rock",
    "Ska": "Ska",
    "Soft": "Suave",
    "Soft rock": "Rock suave",
    "Techno": "Techno",
}

EXPLORE_GENRES = [
    ("Huayno", "huaynos más escuchados"),
    ("Folklore andino", "música andina folklore éxitos"),
    ("Cumbia peruana", "cumbia peruana éxitos más escuchados"),
    ("Chicha", "chicha peruana clásicos"),
    ("Salsa", "salsa éxitos más escuchados"),
    ("Reggaetón", "reggaeton más escuchado"),
    ("Rock en español", "rock en español clásicos"),
    ("Baladas", "baladas románticas en español éxitos"),
    ("Trap latino", "trap latino más escuchado"),
    ("Electrónica", "música electrónica éxitos"),
]

SHORTCUTS_HELP = [
    ("Espacio", "Reproducir / pausar"),
    ("Ctrl + F", "Buscar una canción"),
    ("Ctrl + → / ←", "Siguiente / anterior"),
    ("Shift + → / ←", "Adelantar / retroceder 10 s"),
    ("Ctrl + ↑ / ↓", "Subir / bajar volumen"),
    ("Ctrl + M", "Silenciar"),
    ("Ctrl + D", "Me gusta (canción actual)"),
    ("Ctrl + S / R", "Aleatorio / repetir"),
    ("Ctrl + 1 … 5", "Inicio, Explorar, Biblioteca, Favoritas, Ajustes"),
    ("Esc", "Cerrar resultados de búsqueda"),
]


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


# =====================================================================
# VENTANA PRINCIPAL
# =====================================================================
class PuquichuApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        init_and_migrate_db()
        organize_and_classify_all_songs(self.settings)

        self.season = resolve_season(self.settings.get("season_theme", "auto"))
        apply_season(self.season)
        if not ICON_PATH.exists():
            try:
                save_brand_icon(ICON_PATH)
            except OSError:
                pass

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(1340, 840)
        self.setMinimumSize(1080, 700)
        self.setStyleSheet(build_qss())

        # Motor de audio VLC nativo
        self.vlc_instance = vlc.Instance("--no-xlib")
        self.player = self.vlc_instance.media_player_new()
        self.player.audio_set_volume(int(self.settings.get("default_volume", 85)))
        self._eq = None

        # Estado de reproducción
        self.current_song: dict | None = None
        self.playlist_queue: list[dict] = []
        self.up_next: list[int] = []
        self.history: list[int] = []
        self.selected_genre_filter = "Todos"
        self.is_seeking = False
        self.loop_enabled = bool(self.settings.get("loop", False))
        self.shuffle_enabled = bool(self.settings.get("shuffle", False))
        self.is_muted = False
        self.media_loaded = False
        self.resume_ms = 0
        self.sleep_deadline: datetime | None = None
        self.sleep_end_of_track = False
        self._last_status = "Stopped"

        # Descargas y búsqueda
        self.worker: SearchDownloadWorker | None = None
        self.current_job: dict | None = None
        self.download_queue: list[dict] = []
        self.search_worker: YouTubeSearchWorker | None = None
        self._old_search_workers: list = []
        self.result_rows: dict[str, ResultRow] = {}
        self.explore_rows: dict[str, ResultRow] = {}
        self.artist_rows: dict[str, ResultRow] = {}
        self.song_page_song: dict | None = None
        self._artist_query = ""
        self._last_query = ""
        self._explore_query = ""
        self._play_token = 0
        self._last_play_key = None
        self._last_play_time = 0.0
        self._online_done_cb = None
        self._workers: set = set()  # mantiene vivos los hilos hasta que terminen
        self.charts_loaded: set[str] = set()

        self._accent_labels: list[tuple[QLabel, str, int]] = []
        self.mpris = None

        self._build_ui()
        self.apply_equalizer(int(self.settings.get("equalizer", -1)))
        try:
            self.mpris = MprisService(self) if MprisService else None
            if self.mpris and not self.mpris.ok:
                self.mpris = None
        except Exception:
            self.mpris = None
        self._setup_shortcuts()

        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._update_playback_tick)
        self.timer.start()

        self.refresh_all_views()
        self._restore_session()

    # =================================================================
    # CONSTRUCCIÓN DE LA INTERFAZ
    # =================================================================
    def _build_ui(self):
        self.root = RootWidget()
        self.setCentralWidget(self.root)
        self.root_layout = QVBoxLayout(self.root)
        self.root_layout.setContentsMargins(RootWidget.EDGE, 0, RootWidget.EDGE, RootWidget.EDGE)
        self.root_layout.setSpacing(0)

        self.titlebar = TitleBar(self)
        self.root_layout.addWidget(self.titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)
        body.addWidget(self._create_sidebar())

        self.main_panel = QFrame()
        self.main_panel.setObjectName("MainPanel")
        mp = QVBoxLayout(self.main_panel)
        mp.setContentsMargins(0, 0, 0, 0)
        self.pages = QStackedWidget()
        self.page_home = self._create_home_page()
        self.page_library = self._create_library_page()
        self.page_settings = self._create_settings_page()
        self.page_explore = self._create_explore_page()
        self.page_song = self._create_song_page()
        for page in (self.page_home, self.page_library, self.page_settings, self.page_explore, self.page_song):
            self.pages.addWidget(page)
        mp.addWidget(self.pages)
        body.addWidget(self.main_panel, stretch=1)

        self.root_layout.addLayout(body, stretch=1)
        self.root_layout.addWidget(self._create_bottom_player())
        self.toast = Toast(self.main_panel)

    @staticmethod
    def _label(text: str, obj_name: str, cls=QLabel) -> QLabel:
        lbl = cls(text)
        lbl.setObjectName(obj_name)
        return lbl

    def _accent_icon_label(self, icon: str, size: int, tile: bool = False) -> QLabel:
        lbl = QLabel()
        if tile:
            lbl.setObjectName("IconTile")
            lbl.setFixedSize(40, 40)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setPixmap(make_icon_pixmap(icon, C["accent_hi"], size))
        self._accent_labels.append((lbl, icon, size))
        return lbl

    # ----------------------------- Barra lateral -----------------------------
    def _create_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(300)
        vbox = QVBoxLayout(sidebar)
        vbox.setContentsMargins(14, 18, 14, 14)
        vbox.setSpacing(4)

        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 0, 0)
        brand.setSpacing(12)
        self.brand_logo_lbl = QLabel()
        self.brand_logo_lbl.setPixmap(brand_logo(38))
        brand.addWidget(self.brand_logo_lbl)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(self._label(APP_NAME, "Brand"))
        self.brand_season_lbl = self._label("", "BrandSub")
        names.addWidget(self.brand_season_lbl)
        brand.addLayout(names)
        brand.addStretch()
        vbox.addLayout(brand)
        vbox.addSpacing(18)

        self.nav_buttons: dict[str, QPushButton] = {}
        self.nav_icons = {"home": "home", "explore": "compass", "library": "library", "favorites": "heart", "settings": "settings"}
        for key, label, action in (
            ("home", "Inicio", lambda: self.switch_page(0)),
            ("explore", "Explorar", self.open_explore),
            ("library", "Biblioteca", lambda: self.open_genre_in_library("Todos")),
            ("favorites", "Favoritas", lambda: self.open_genre_in_library(FAV_FILTER)),
            ("settings", "Ajustes", lambda: self.switch_page(2)),
        ):
            btn = QPushButton(f"  {label}")
            btn.setProperty("class", "NavBtn")
            btn.setIconSize(QSize(22, 22))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(action)
            vbox.addWidget(btn)
            self.nav_buttons[key] = btn

        vbox.addSpacing(16)
        div = QFrame()
        div.setProperty("class", "Divider")
        vbox.addWidget(div)
        vbox.addSpacing(14)

        top_hdr = QHBoxLayout()
        top_hdr.setContentsMargins(8, 0, 0, 0)
        top_hdr.setSpacing(8)
        top_hdr.addWidget(self._accent_icon_label("trend", 16))
        top_hdr.addWidget(self._label("MÁS ESCUCHADAS", "Kicker"))
        top_hdr.addStretch()
        vbox.addLayout(top_hdr)
        vbox.addSpacing(6)

        self.sidebar_top_list = QListWidget()
        self.sidebar_top_list.setObjectName("SidebarTopList")
        self.sidebar_top_list.setItemDelegate(TopSongDelegate(self.sidebar_top_list))
        self.sidebar_top_list.setMouseTracking(True)
        self.sidebar_top_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.sidebar_top_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sidebar_top_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.sidebar_top_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar_top_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sidebar_top_list.itemClicked.connect(lambda it: self.play_song_by_id(it.data(Qt.ItemDataRole.UserRole)))
        self.sidebar_top_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sidebar_top_list.customContextMenuRequested.connect(self._sidebar_context_menu)
        vbox.addWidget(self.sidebar_top_list, stretch=1)

        self.sidebar_empty_lbl = self._label("Tus canciones más escuchadas aparecerán aquí.", "Dim")
        self.sidebar_empty_lbl.setWordWrap(True)
        self.sidebar_empty_lbl.setContentsMargins(8, 0, 8, 0)
        vbox.addWidget(self.sidebar_empty_lbl)

        storage = QFrame()
        storage.setObjectName("StorageBox")
        st = QHBoxLayout(storage)
        st.setContentsMargins(12, 10, 12, 10)
        st.setSpacing(10)
        st_icon = QLabel()
        st_icon.setPixmap(make_icon_pixmap("folder", C["muted"], 18))
        st.addWidget(st_icon, alignment=Qt.AlignmentFlag.AlignTop)
        st_text = QVBoxLayout()
        st_text.setSpacing(1)
        self.sidebar_storage_lbl = self._label("", "Muted", ElidedLabel)
        self.sidebar_mode_lbl = self._label("", "Dim", ElidedLabel)
        st_text.addWidget(self.sidebar_storage_lbl)
        st_text.addWidget(self.sidebar_mode_lbl)
        st.addLayout(st_text, stretch=1)
        storage.setCursor(Qt.CursorShape.PointingHandCursor)
        storage.setToolTip("Abrir la carpeta de música")
        storage.mousePressEvent = lambda _e: self.open_path(self.settings["download_dir"])
        vbox.addSpacing(8)
        vbox.addWidget(storage)
        return sidebar

    # ----------------------------- Páginas -----------------------------
    def _scroll_page(self, margins=(32, 26, 32, 28), spacing=22):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(*margins)
        vbox.setSpacing(spacing)
        scroll.setWidget(page)
        return scroll, vbox

    def _section_header(self, title: str, action_text: str = "", action=None) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(self._label(title, "H2"))
        row.addStretch()
        if action_text:
            btn = QPushButton(action_text)
            btn.setProperty("class", "GhostBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(action)
            row.addWidget(btn)
        return row

    def _create_home_page(self) -> QWidget:
        scroll, vbox = self._scroll_page()
        self.home_scroll = scroll

        head = QVBoxLayout()
        head.setSpacing(4)
        self.greeting_lbl = self._label("", "H1")
        self.home_stats_lbl = self._label("", "Muted")
        head.addWidget(self.greeting_lbl)
        head.addWidget(self.home_stats_lbl)
        vbox.addLayout(head)

        # Buscador
        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("MainSearch")
        self.search_input.setPlaceholderText("¿Qué quieres escuchar? Busca una canción o artista y elige la versión correcta")
        self.search_input.addAction(make_icon("search", C["muted"], 18), QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.returnPressed.connect(self.start_search)
        search_row.addWidget(self.search_input, stretch=1)
        self.search_btn = QPushButton("Buscar")
        self.search_btn.setObjectName("PrimaryBtn")
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.search_btn.clicked.connect(self.start_search)
        search_row.addWidget(self.search_btn)
        vbox.addLayout(search_row)

        # Descargas en curso
        self.status_banner = QFrame()
        self.status_banner.setObjectName("StatusBanner")
        bl = QVBoxLayout(self.status_banner)
        bl.setContentsMargins(16, 12, 16, 12)
        bl.setSpacing(8)
        b_row = QHBoxLayout()
        b_row.setSpacing(10)
        b_row.addWidget(self._accent_icon_label("download", 18))
        self.status_label = ElidedLabel("")
        self.status_label.setStyleSheet("color: #ffffff; font-weight: 700;")
        b_row.addWidget(self.status_label, stretch=1)
        self.status_queue_lbl = self._label("", "Accent")
        b_row.addWidget(self.status_queue_lbl)
        bl.addLayout(b_row)
        self.status_progress = QProgressBar()
        self.status_progress.setRange(0, 0)
        self.status_progress.setTextVisible(False)
        self.status_progress.setFixedHeight(4)
        bl.addWidget(self.status_progress)
        self.status_banner.hide()
        vbox.addWidget(self.status_banner)

        # Resultados de búsqueda
        self.results_panel = QFrame()
        self.results_panel.setObjectName("ResultsPanel")
        rp = QVBoxLayout(self.results_panel)
        rp.setContentsMargins(18, 16, 18, 14)
        rp.setSpacing(6)
        rh = QHBoxLayout()
        self.results_title = self._label("", "H3")
        rh.addWidget(self.results_title, stretch=1)
        close_btn = QPushButton()
        close_btn.setProperty("class", "IconBtn")
        close_btn.setIcon(make_icon("close", C["muted"], 16))
        close_btn.setToolTip("Cerrar resultados (Esc)")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.clicked.connect(self.close_results)
        rh.addWidget(close_btn)
        rp.addLayout(rh)
        self.results_hint = self._label("", "Dim")
        self.results_hint.setWordWrap(True)
        rp.addWidget(self.results_hint)
        self.results_box = QVBoxLayout()
        self.results_box.setSpacing(2)
        rp.addLayout(self.results_box)
        self.results_panel.hide()
        vbox.addWidget(self.results_panel)

        # Tarjeta 'Sonando ahora'
        self.hero_card = HeroCard()
        self.hero_card.setMinimumHeight(250)
        hero = QHBoxLayout(self.hero_card)
        hero.setContentsMargins(28, 28, 28, 28)
        hero.setSpacing(28)
        self.hero_artwork = QLabel()
        self.hero_artwork.setFixedSize(196, 196)
        self.hero_artwork.setPixmap(create_artwork_pixmap("", "Otros", "", 196, 14))
        shadow = QGraphicsDropShadowEffect(self.hero_artwork)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 14)
        shadow.setColor(QColor(0, 0, 0, 170))
        self.hero_artwork.setGraphicsEffect(shadow)
        hero.addWidget(self.hero_artwork, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.hero_artwork.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hero_artwork.setToolTip("Ver la canción")
        self.hero_artwork.mousePressEvent = lambda _e: self.open_song_page()

        info = QVBoxLayout()
        info.setSpacing(6)
        info.addStretch()
        self.hero_kicker = self._label("BIENVENIDO", "HeroKicker")
        info.addWidget(self.hero_kicker)
        self.hero_title = self._label("Tu música, en tu escritorio", "HeroTitle")
        self.hero_title.setWordWrap(True)
        self.hero_title.setMaximumHeight(90)
        info.addWidget(self.hero_title)
        self.hero_artist = self._label("Busca una canción arriba o elige una de tu biblioteca", "HeroArtist")
        info.addWidget(self.hero_artist)
        badges = QHBoxLayout()
        badges.setSpacing(8)
        self.hero_genre_badge = self._label("Género automático", "GlassBadge")
        self.hero_source_badge = self._label("100% local", "GlassBadge")
        badges.addWidget(self.hero_genre_badge)
        badges.addWidget(self.hero_source_badge)
        badges.addStretch()
        info.addSpacing(6)
        info.addLayout(badges)
        self.hero_meta = self._label("", "HeroMeta", ElidedLabel)
        info.addWidget(self.hero_meta)
        info.addSpacing(8)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.hero_fav_btn = QPushButton()
        self.hero_fav_btn.setProperty("class", "GlassIcon")
        self.hero_fav_btn.setIconSize(QSize(18, 18))
        self.hero_fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hero_fav_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hero_fav_btn.clicked.connect(self.toggle_current_favorite)
        actions.addWidget(self.hero_fav_btn)
        self.hero_save_btn = QPushButton("Guardar")
        self.hero_save_btn.setProperty("class", "GlassBtn")
        self.hero_save_btn.setIcon(make_icon("download", "#ffffff", 16))
        self.hero_save_btn.setToolTip("Guardar esta canción en tu biblioteca para escucharla sin internet")
        self.hero_save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hero_save_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hero_save_btn.clicked.connect(lambda: self._save_current_stream())
        self.hero_save_btn.hide()
        actions.addWidget(self.hero_save_btn)
        self.open_folder_btn = QPushButton("Abrir carpeta")
        self.open_folder_btn.setProperty("class", "GlassBtn")
        self.open_folder_btn.setIcon(make_icon("folder", "#ffffff", 16))
        self.open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_folder_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.open_folder_btn.clicked.connect(self.open_current_song_folder)
        actions.addWidget(self.open_folder_btn)
        self.change_genre_combo = QComboBox()
        self.change_genre_combo.setObjectName("GlassCombo")
        self.change_genre_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.change_genre_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.change_genre_combo.addItem("Cambiar género…")
        self.change_genre_combo.addItems(GENRES_LIST)
        self.change_genre_combo.currentIndexChanged.connect(self.on_manual_genre_change)
        actions.addWidget(self.change_genre_combo)
        actions.addStretch()
        info.addLayout(actions)
        info.addStretch()
        hero.addLayout(info, stretch=1)
        vbox.addWidget(self.hero_card)

        # Escuchado recientemente
        vbox.addLayout(self._section_header("Escuchado recientemente", "Ver todo", lambda: self.open_genre_in_library("Todos")))
        recent_scroll = QScrollArea()
        recent_scroll.setWidgetResizable(True)
        recent_scroll.setFrameShape(QFrame.Shape.NoFrame)
        recent_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        recent_scroll.setFixedHeight(SongCard.ART + 82 + 14)
        host = QWidget()
        self.recent_row = QHBoxLayout(host)
        self.recent_row.setContentsMargins(0, 0, 0, 0)
        self.recent_row.setSpacing(6)
        recent_scroll.setWidget(host)
        vbox.addWidget(recent_scroll)

        # Géneros
        vbox.addLayout(self._section_header("Tus géneros", "Abrir biblioteca", lambda: self.open_genre_in_library("Todos")))
        self.genre_cards_grid = QGridLayout()
        self.genre_cards_grid.setHorizontalSpacing(14)
        self.genre_cards_grid.setVerticalSpacing(14)
        vbox.addLayout(self.genre_cards_grid)
        vbox.addStretch(1)
        return scroll

    def _create_library_page(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(32, 26, 32, 16)
        vbox.setSpacing(16)

        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.lib_title_lbl = self._label("Tu biblioteca", "H1")
        col.addWidget(self.lib_title_lbl)
        self.lib_count_lbl = self._label("", "Muted")
        col.addWidget(self.lib_count_lbl)
        hdr.addLayout(col)
        hdr.addStretch()

        self.lib_filter_input = QLineEdit()
        self.lib_filter_input.setProperty("class", "SettingsInput")
        self.lib_filter_input.setPlaceholderText("Filtrar por título, artista o género")
        self.lib_filter_input.addAction(make_icon("search", C["muted"], 16), QLineEdit.ActionPosition.LeadingPosition)
        self.lib_filter_input.setClearButtonEnabled(True)
        self.lib_filter_input.setFixedWidth(260)
        self.lib_filter_input.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.lib_filter_input.textChanged.connect(self.refresh_library_table)
        hdr.addWidget(self.lib_filter_input, alignment=Qt.AlignmentFlag.AlignBottom)
        self.lib_sort_combo = QComboBox()
        self.lib_sort_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lib_sort_combo.addItems(["Más escuchadas", "Escuchadas recientemente", "Agregadas recientemente", "Por género", "Título (A-Z)"])
        self.lib_sort_combo.setFixedWidth(220)
        self.lib_sort_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.lib_sort_combo.currentIndexChanged.connect(self.refresh_library_table)
        hdr.addWidget(self.lib_sort_combo, alignment=Qt.AlignmentFlag.AlignBottom)
        vbox.addLayout(hdr)

        # Fila de acciones: reproducir / aleatorio + chips de filtro
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.lib_play_btn = QPushButton()
        self.lib_play_btn.setObjectName("BigPlayBtn")
        self.lib_play_btn.setIconSize(QSize(20, 20))
        self.lib_play_btn.setToolTip("Reproducir esta lista")
        self.lib_play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lib_play_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.lib_play_btn.clicked.connect(lambda: self.play_current_list(shuffle=False))
        actions.addWidget(self.lib_play_btn)
        self.lib_shuffle_btn = QPushButton()
        self.lib_shuffle_btn.setProperty("class", "PlayerIconBtn")
        self.lib_shuffle_btn.setIconSize(QSize(22, 22))
        self.lib_shuffle_btn.setToolTip("Reproducir en orden aleatorio")
        self.lib_shuffle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lib_shuffle_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.lib_shuffle_btn.clicked.connect(lambda: self.play_current_list(shuffle=True))
        actions.addWidget(self.lib_shuffle_btn)
        actions.addSpacing(8)

        chips_scroll = QScrollArea()
        chips_scroll.setWidgetResizable(True)
        chips_scroll.setFrameShape(QFrame.Shape.NoFrame)
        chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        chips_scroll.setFixedHeight(46)
        chips_host = QWidget()
        chips = QHBoxLayout(chips_host)
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(8)
        self.genre_chip_buttons: dict[str, QPushButton] = {}
        for key in ["Todos", FAV_FILTER] + GENRES_LIST:
            chip = QPushButton("Favoritas" if key == FAV_FILTER else key)
            chip.setProperty("class", "GenreChip")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            chip.clicked.connect(lambda _c=False, g=key: self.set_library_genre_filter(g))
            chips.addWidget(chip)
            self.genre_chip_buttons[key] = chip
        chips.addStretch()
        chips_scroll.setWidget(chips_host)
        actions.addWidget(chips_scroll, stretch=1)
        vbox.addLayout(actions)

        t = self.library_table = LibraryTable()
        t.setHorizontalHeaderLabels(LibraryTable.COLS)
        t.setItemDelegate(LibraryDelegate(t))
        t.verticalHeader().setVisible(False)
        t.setShowGrid(False)
        t.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        t.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        t.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        t.setWordWrap(False)
        header = t.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c, w in {0: 52, 2: 170, 3: 96, 4: 130, 5: 48, 6: 96}.items():
            t.setColumnWidth(c, w)
        t.horizontalHeaderItem(6).setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        t.horizontalHeaderItem(0).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        t.cellDoubleClicked.connect(self.on_library_row_activated)
        t.cellClicked.connect(self.on_library_cell_clicked)
        t.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        t.customContextMenuRequested.connect(self._library_context_menu)
        vbox.addWidget(t, stretch=1)

        self.lib_empty_lbl = self._label("", "Muted")
        self.lib_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lib_empty_lbl.setWordWrap(True)
        self.lib_empty_lbl.hide()
        vbox.addWidget(self.lib_empty_lbl, stretch=1)
        vbox.addWidget(self._label("Doble clic para reproducir · ♥ para marcar favorita · Clic derecho para más opciones", "Dim"))
        return page

    def _settings_card(self, icon_name: str, title: str, desc: str):
        card = QFrame()
        card.setProperty("class", "Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)
        head = QHBoxLayout()
        head.setSpacing(14)
        head.addWidget(self._accent_icon_label(icon_name, 20, tile=True), alignment=Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self._label(title, "H3"))
        d = self._label(desc, "Muted")
        d.setWordWrap(True)
        text.addWidget(d)
        head.addLayout(text, stretch=1)
        layout.addLayout(head)
        div = QFrame()
        div.setProperty("class", "Divider")
        layout.addWidget(div)
        return card, layout

    def _settings_row(self, title: str, desc: str, control: QWidget | None) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(18)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self._label(title, "RowTitle"))
        if desc:
            d = self._label(desc, "Dim")
            d.setWordWrap(True)
            text.addWidget(d)
        row.addLayout(text, stretch=1)
        if control is not None:
            if isinstance(control, QPushButton):
                control.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            row.addWidget(control, alignment=Qt.AlignmentFlag.AlignVCenter)
        return row

    @staticmethod
    def _swatch_icon(colors: list[str]) -> QIcon:
        pm = QPixmap(44, 44)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        if len(colors) == 1:
            p.setBrush(QColor(colors[0]))
            p.drawEllipse(4, 4, 36, 36)
        else:
            p.setBrush(QColor(colors[0]))
            p.drawPie(4, 4, 36, 36, 90 * 16, 180 * 16)
            p.setBrush(QColor(colors[1]))
            p.drawPie(4, 4, 36, 36, 270 * 16, 180 * 16)
        p.end()
        pm.setDevicePixelRatio(2)
        return QIcon(pm)

    def _create_settings_page(self) -> QWidget:
        scroll, vbox = self._scroll_page(spacing=18)
        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(self._label("Ajustes", "H1"))
        head.addWidget(self._label("Apariencia, dónde se guarda tu música, cómo se organiza y cómo suena.", "Muted"))
        vbox.addLayout(head)
        vbox.addSpacing(4)

        # Apariencia: las dos estaciones del campo
        card, lay = self._settings_card(
            "sprout",
            "Estación del tema",
            "Los colores de Puquichu vienen del campo: el verde del pasto que brota con las lluvias (puquy) "
            "y el dorado del ichu en la temporada seca.",
        )
        seasons_row = QHBoxLayout()
        seasons_row.setSpacing(10)
        self.season_buttons: dict[str, QPushButton] = {}
        for key, label, colors in (
            ("auto", "Automático\nsegún el mes", [SEASONS["puquy"]["accent"], SEASONS["ichu"]["accent"]]),
            ("puquy", "Puquy\ntemporada de lluvias", [SEASONS["puquy"]["accent"]]),
            ("ichu", "Ichu\ntemporada seca", [SEASONS["ichu"]["accent"]]),
        ):
            b = QPushButton(f"  {label}")
            b.setProperty("class", "SeasonBtn")
            b.setIcon(self._swatch_icon(colors))
            b.setIconSize(QSize(22, 22))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _c=False, k=key: self.set_season_theme(k))
            seasons_row.addWidget(b, stretch=1)
            self.season_buttons[key] = b
        lay.addLayout(seasons_row)
        vbox.addWidget(card)

        # Almacenamiento
        card, lay = self._settings_card("folder", "Almacenamiento", "Carpeta donde se guardan las canciones descargadas.")
        path_row = QHBoxLayout()
        path_row.setSpacing(10)
        self.settings_dir_input = QLineEdit(self.settings["download_dir"])
        self.settings_dir_input.setProperty("class", "SettingsInput")
        self.settings_dir_input.setReadOnly(True)
        path_row.addWidget(self.settings_dir_input, stretch=1)
        for text, icon, slot in (
            ("Cambiar carpeta", "", self.choose_download_directory),
            ("Abrir", "folder", lambda: self.open_path(self.settings["download_dir"])),
        ):
            b = QPushButton(text)
            b.setProperty("class", "SecondaryBtn")
            if icon:
                b.setIcon(make_icon(icon, C["text"], 16))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(slot)
            path_row.addWidget(b)
        lay.addLayout(path_row)
        b = QPushButton("Importar carpeta")
        b.setProperty("class", "SecondaryBtn")
        b.setIcon(make_icon("download", C["text"], 16))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(self.import_external_music_folder)
        lay.addLayout(self._settings_row("Importar canciones existentes", "Añade los MP3, M4A, FLAC, OGG… que ya tengas en tu equipo.", b))
        vbox.addWidget(card)

        # Organización
        card, lay = self._settings_card("library", "Organización por género", "Clasifica automáticamente (Reggaeton, Rock, Pop…) y ordena los archivos.")
        self.chk_organize_genre = ToggleSwitch()
        self.chk_organize_genre.setChecked(bool(self.settings.get("organize_by_genre", True)))
        self.chk_organize_genre.toggled.connect(self.save_current_settings)
        lay.addLayout(self._settings_row("Subcarpetas por género", "Guarda cada canción en Reggaeton/, Rock/, Pop/, Urbano/…", self.chk_organize_genre))
        self.chk_clean_names = ToggleSwitch()
        self.chk_clean_names.setChecked(bool(self.settings.get("clean_filenames", True)))
        self.chk_clean_names.toggled.connect(self.save_current_settings)
        lay.addLayout(self._settings_row("Nombres de archivo limpios", "Usa el título real de la canción en vez del código de YouTube.", self.chk_clean_names))
        b = QPushButton("Ordenar ahora")
        b.setProperty("class", "PrimaryBtn")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(self.trigger_manual_reorganization)
        lay.addLayout(self._settings_row("Reclasificar toda la biblioteca", "Vuelve a detectar géneros y mueve los archivos a su carpeta.", b))
        vbox.addWidget(card)

        # Sonido y reproducción
        card, lay = self._settings_card("sliders_v", "Sonido y reproducción", "Cómo se escucha, con qué calidad se guarda y cómo suena.")
        lay.addLayout(self._settings_row("Modo de escucha", "Al tocar una canción de internet siempre suena al instante. Tú decides si además se guarda.", None))
        listen_row = QHBoxLayout()
        listen_row.setSpacing(10)
        self.listen_buttons: dict[str, QPushButton] = {}
        for key, label, icon in (
            ("save", "Escuchar y guardar (recomendado)\nSuena al instante y queda en tu equipo: la próxima vez sin internet", "download"),
            ("stream", "Solo en línea\nNo ocupa espacio; necesita internet cada vez", "cloud"),
        ):
            b = QPushButton(f"  {label}")
            b.setProperty("class", "SeasonBtn")
            b.setIcon(make_icon(icon, C["text"], 20))
            b.setIconSize(QSize(20, 20))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _c=False, k=key: self.set_listen_mode(k))
            listen_row.addWidget(b, stretch=1)
            self.listen_buttons[key] = b
        lay.addLayout(listen_row)

        self.combo_audio_fmt = QComboBox()
        self.combo_audio_fmt.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_audio_fmt.setMinimumWidth(340)
        self.combo_audio_fmt.addItem("Máxima calidad — Opus original (recomendado)", "best")
        self.combo_audio_fmt.addItem("Compatible — M4A / AAC 128 kbps", "m4a")
        self.combo_audio_fmt.addItem("MP3 320 kbps — para USB o radio del carro", "mp3_320")
        self.combo_audio_fmt.setCurrentIndex(max(0, self.combo_audio_fmt.findData(self.settings.get("audio_format", "best"))))
        self.combo_audio_fmt.currentIndexChanged.connect(self.save_current_settings)
        lay.addLayout(
            self._settings_row(
                "Calidad al guardar",
                "YouTube da como máximo Opus ~135-160 kbps; se guarda tal cual, sin perder calidad. "
                "El MP3 320 se recodifica: es más compatible pero no suena mejor.",
                self.combo_audio_fmt,
            )
        )

        self.combo_eq = QComboBox()
        self.combo_eq.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_eq.setMinimumWidth(300)
        self.combo_eq.addItem("Desactivado", -1)
        for i in range(vlc.libvlc_audio_equalizer_get_preset_count()):
            raw = vlc.libvlc_audio_equalizer_get_preset_name(i)
            name = raw.decode() if isinstance(raw, bytes) else str(raw)
            self.combo_eq.addItem(EQ_NAMES_ES.get(name, name), i)
        self.combo_eq.setCurrentIndex(max(0, self.combo_eq.findData(int(self.settings.get("equalizer", -1)))))
        self.combo_eq.currentIndexChanged.connect(self._on_eq_changed)
        lay.addLayout(self._settings_row("Ecualizador", "Ajusta graves y agudos con un preajuste; se aplica al instante.", self.combo_eq))

        self.chk_auto_next = ToggleSwitch()
        self.chk_auto_next.setChecked(bool(self.settings.get("auto_next", True)))
        self.chk_auto_next.toggled.connect(self.save_current_settings)
        lay.addLayout(self._settings_row("Reproducción continua", "Pasa a la siguiente canción al terminar.", self.chk_auto_next))
        self.chk_notifications = ToggleSwitch()
        self.chk_notifications.setChecked(bool(self.settings.get("notifications", True)))
        self.chk_notifications.toggled.connect(self.save_current_settings)
        lay.addLayout(
            self._settings_row(
                "Notificaciones de escritorio",
                "Avisa qué canción empieza y cuándo termina una descarga (solo si la ventana no está al frente).",
                self.chk_notifications,
            )
        )
        vbox.addWidget(card)

        # Mantenimiento
        card, lay = self._settings_card("refresh", "Mantenimiento", "Mantén al día el motor de descargas y limpia la biblioteca.")
        self.ytdlp_btn = QPushButton("Actualizar")
        self.ytdlp_btn.setProperty("class", "SecondaryBtn")
        self.ytdlp_btn.setIcon(make_icon("refresh", C["text"], 16))
        self.ytdlp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ytdlp_btn.clicked.connect(self.update_ytdlp)
        lay.addLayout(
            self._settings_row(
                f"Motor de descargas (yt-dlp {ytdlp_version()})",
                "YouTube cambia seguido; si las descargas empiezan a fallar, actualízalo.",
                self.ytdlp_btn,
            )
        )
        b = QPushButton("Revisar")
        b.setProperty("class", "SecondaryBtn")
        b.setIcon(make_icon("search", C["text"], 16))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(self.check_missing_files)
        lay.addLayout(self._settings_row("Canciones perdidas", "Busca canciones cuyo archivo ya no existe en el disco.", b))
        lay.addLayout(self._settings_row(f"Puquichu {APP_VERSION}", f"Tus datos se guardan en {str(DATA_DIR).replace(str(Path.home()), '~')}", None))
        vbox.addWidget(card)

        # Atajos
        card, lay = self._settings_card(
            "keyboard",
            "Atajos de teclado",
            "Funcionan con la ventana abierta. Las teclas multimedia (▶ ⏭ ⏮) y el control del panel de KDE funcionan siempre.",
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)
        for i, (keys, desc) in enumerate(SHORTCUTS_HELP):
            r, c = divmod(i, 2)
            cell = QHBoxLayout()
            cell.setSpacing(10)
            k = self._label(keys, "Kbd")
            k.setFixedWidth(118)
            k.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.addWidget(k)
            cell.addWidget(self._label(desc, "Muted"), stretch=1)
            grid.addLayout(cell, r, c)
        lay.addLayout(grid)
        vbox.addWidget(card)
        vbox.addStretch(1)
        return scroll

    # ----------------------------- Reproductor -----------------------------
    def _player_btn(self, icon: str, tip: str, slot) -> QPushButton:
        btn = QPushButton()
        btn.setProperty("class", "PlayerIconBtn")
        btn.setIcon(make_icon(icon, C["muted"], 20))
        btn.setIconSize(QSize(20, 20))
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.clicked.connect(slot)
        return btn

    def _create_bottom_player(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("BottomPlayer")
        bar.setFixedHeight(92)
        hbox = QHBoxLayout(bar)
        hbox.setContentsMargins(6, 10, 10, 4)
        hbox.setSpacing(16)

        left = QWidget()
        left.setFixedWidth(330)
        lr = QHBoxLayout(left)
        lr.setContentsMargins(0, 0, 0, 0)
        lr.setSpacing(14)
        self.footer_art = QLabel()
        self.footer_art.setFixedSize(58, 58)
        self.footer_art.setPixmap(create_artwork_pixmap("", "Otros", "", 58, 8))
        lr.addWidget(self.footer_art)
        meta = QVBoxLayout()
        meta.setSpacing(2)
        meta.addStretch()
        self.footer_title = self._label("Nada sonando", "PlayerTitle", ElidedLabel)
        self.footer_sub = self._label("Elige una canción para empezar", "PlayerSub", ElidedLabel)
        meta.addWidget(self.footer_title)
        meta.addWidget(self.footer_sub)
        meta.addStretch()
        lr.addLayout(meta, stretch=1)
        for wdg in (self.footer_art, self.footer_title, self.footer_sub):
            wdg.setCursor(Qt.CursorShape.PointingHandCursor)
            wdg.mousePressEvent = lambda _e: self.open_song_page()
        self.footer_art.setToolTip("Ver la canción")
        self.footer_fav_btn = self._player_btn("heart", "Me gusta", self.toggle_current_favorite)
        lr.addWidget(self.footer_fav_btn)
        hbox.addWidget(left)

        center = QWidget()
        center.setMaximumWidth(680)
        cc = QVBoxLayout(center)
        cc.setContentsMargins(0, 0, 0, 0)
        cc.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch()
        self.btn_shuffle = self._player_btn("shuffle", "Aleatorio (Ctrl+S)", self.toggle_shuffle)
        self.btn_prev = self._player_btn("prev", "Anterior (Ctrl+←)", self.play_previous_song)
        self.btn_back10 = self._player_btn("back10", "Retroceder 10 s (Shift+←)", lambda: self.seek_relative_ms(-10000))
        self.btn_play_pause = QPushButton()
        self.btn_play_pause.setObjectName("PlayCircleBtn")
        self.btn_play_pause.setIconSize(QSize(18, 18))
        self.btn_play_pause.setEnabled(False)
        self.btn_play_pause.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_play_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_play_pause.clicked.connect(self.toggle_play_pause)
        self.btn_fwd10 = self._player_btn("fwd10", "Adelantar 10 s (Shift+→)", lambda: self.seek_relative_ms(10000))
        self.btn_next = self._player_btn("next", "Siguiente (Ctrl+→)", lambda: self.play_next_song())
        self.btn_loop = self._player_btn("repeat", "Repetir canción (Ctrl+R)", self.toggle_loop)
        for b in (self.btn_shuffle, self.btn_prev, self.btn_back10, self.btn_play_pause, self.btn_fwd10, self.btn_next, self.btn_loop):
            row.addWidget(b)
        row.addStretch()
        cc.addLayout(row)
        seek = QHBoxLayout()
        seek.setSpacing(10)
        self.lbl_time_cur = self._label("0:00", "Time")
        self.lbl_time_cur.setFixedWidth(46)
        self.lbl_time_cur.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        seek.addWidget(self.lbl_time_cur)
        self.seek_slider = ClickSlider(Qt.Orientation.Horizontal)
        self.seek_slider.hover_text = self._seek_hover_text
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.seek_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.seek_slider.sliderPressed.connect(lambda: setattr(self, "is_seeking", True))
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        seek.addWidget(self.seek_slider, stretch=1)
        self.lbl_time_tot = self._label("0:00", "Time")
        self.lbl_time_tot.setFixedWidth(46)
        seek.addWidget(self.lbl_time_tot)
        cc.addLayout(seek)
        hbox.addWidget(center, stretch=1)

        right = QWidget()
        right.setFixedWidth(330)
        rr = QHBoxLayout(right)
        rr.setContentsMargins(0, 0, 0, 0)
        rr.setSpacing(6)
        rr.addStretch()
        self.btn_queue = self._player_btn("queue", "A continuación", self.show_queue_menu)
        self.btn_sleep = self._player_btn("moon", "Temporizador para dormir", self.show_sleep_menu)
        self.btn_mute = self._player_btn("volume", "Silenciar (Ctrl+M)", self.toggle_mute)
        rr.addWidget(self.btn_queue)
        rr.addWidget(self.btn_sleep)
        rr.addWidget(self.btn_mute)
        self.vol_slider = ClickSlider(Qt.Orientation.Horizontal)
        self.vol_slider.hover_text = lambda v: f"Volumen {v}%"
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(int(self.settings.get("default_volume", 85)))
        self.vol_slider.setFixedWidth(110)
        self.vol_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.vol_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vol_slider.valueChanged.connect(self.on_volume_changed)
        rr.addWidget(self.vol_slider)
        self.lbl_vol_pct = self._label(f"{self.vol_slider.value()}%", "Time")
        self.lbl_vol_pct.setFixedWidth(36)
        rr.addWidget(self.lbl_vol_pct)
        hbox.addWidget(right)
        return bar

    # =================================================================
    # TEMA Y ESTADO VISUAL
    # =================================================================
    def set_season_theme(self, key: str):
        self.settings["season_theme"] = key
        save_settings(self.settings)
        self.season = resolve_season(key)
        apply_season(self.season)
        self._apply_theme()
        self.toast.show_message(f"Tema: {SEASONS[self.season]['label']}")

    def _apply_theme(self):
        self.setStyleSheet(build_qss())
        for lbl, icon, size in self._accent_labels:
            lbl.setPixmap(make_icon_pixmap(icon, C["accent_hi"], size))
        self.brand_logo_lbl.setPixmap(brand_logo(38))
        self.titlebar.refresh_icons()
        if self.current_song:
            self._apply_now_playing_visuals(self.current_song)
        else:
            self.hero_card.set_color(QColor(C["accent_mid"]))
        self.refresh_all_views()
        self.update()

    def _refresh_visual_state(self):
        """Iconos que dependen del estado (activo/inactivo) o del color de la estación."""
        self.brand_season_lbl.setText("Temporada de lluvias" if self.season == "puquy" else "Temporada seca")
        accent, muted = C["accent"], C["muted"]
        self.btn_shuffle.setIcon(make_icon("shuffle", accent if self.shuffle_enabled else muted, 20))
        self.btn_loop.setIcon(make_icon("repeat", accent if self.loop_enabled else muted, 20))
        self.lib_shuffle_btn.setIcon(make_icon("shuffle", accent if self.shuffle_enabled else muted, 22))
        self.lib_play_btn.setIcon(make_icon("play", C["on_accent"], 20))
        self.btn_queue.setIcon(make_icon("queue", accent if self.up_next else muted, 20))
        self.btn_queue.setToolTip(f"A continuación ({len(self.up_next)})" if self.up_next else "A continuación")
        sleeping = self.sleep_deadline is not None or self.sleep_end_of_track
        self.btn_sleep.setIcon(make_icon("moon", accent if sleeping else muted, 20))
        self._set_play_icon(self.player.is_playing())
        self._set_mute_icon()
        self._refresh_fav_buttons()
        for key, btn in self.season_buttons.items():
            btn.setProperty("active", "true" if key == self.settings.get("season_theme", "auto") else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        for key, btn in self.listen_buttons.items():
            btn.setProperty("active", "true" if key == self.settings.get("listen_mode", "save") else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        cur = self.current_song
        self.hero_save_btn.setVisible(bool(cur and cur.get("stream") and not self._is_saving(cur.get("source_id"))))
        self._update_nav_active()

    def _set_play_icon(self, playing: bool):
        self.btn_play_pause.setIcon(make_icon("pause" if playing else "play", C["bg"], 18))
        self.btn_play_pause.setToolTip("Pausar (Espacio)" if playing else "Reproducir (Espacio)")

    def _set_mute_icon(self):
        v = self.vol_slider.value()
        name = "mute" if self.is_muted or v == 0 else "volume_low" if v < 45 else "volume"
        self.btn_mute.setIcon(make_icon(name, C["text"] if self.is_muted else C["muted"], 20))

    def _refresh_fav_buttons(self):
        fav = bool(self.current_song and self.current_song.get("favorite"))
        self.footer_fav_btn.setIcon(make_icon("heart_fill" if fav else "heart", C["accent"] if fav else C["muted"], 20))
        self.footer_fav_btn.setToolTip("Quitar de favoritas (Ctrl+D)" if fav else "Me gusta (Ctrl+D)")
        self.hero_fav_btn.setIcon(make_icon("heart_fill" if fav else "heart", C["accent"] if fav else "#ffffff", 18))
        self.hero_fav_btn.setToolTip(self.footer_fav_btn.toolTip())
        self.hero_fav_btn.setVisible(self.current_song is not None)
        self.footer_fav_btn.setVisible(self.current_song is not None)

    def _update_nav_active(self):
        page = self.pages.currentIndex()
        active = {0: "home", 2: "settings", 3: "explore", 4: ""}.get(page, "favorites" if self.selected_genre_filter == FAV_FILTER else "library")
        for key, btn in self.nav_buttons.items():
            btn.setProperty("active", "true" if key == active else "false")
            btn.setIcon(make_icon(self.nav_icons[key], C["text"] if key == active else C["muted"], 22))
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def changeEvent(self, e):
        if e.type() == e.Type.WindowStateChange and hasattr(self, "root_layout"):
            m = 0 if self.isMaximized() else RootWidget.EDGE
            self.root_layout.setContentsMargins(m, 0, m, m)
            self.titlebar.refresh_icons()
        super().changeEvent(e)

    # =================================================================
    # NAVEGACIÓN Y VISTAS
    # =================================================================
    def switch_page(self, idx: int):
        self.pages.setCurrentIndex(idx)
        self.refresh_all_views()

    def refresh_all_views(self):
        self.refresh_sidebar_top10()
        self.refresh_home_header()
        self.refresh_recent_row()
        self.refresh_genre_summary_cards()
        self.refresh_library_table()
        dl_dir = self.settings.get("download_dir", "")
        self.sidebar_storage_lbl.setText(dl_dir.replace(str(Path.home()), "~"))
        self.sidebar_mode_lbl.setText("Subcarpetas por género" if self.settings.get("organize_by_genre", True) else "Carpeta única")
        self._refresh_visual_state()

    def refresh_home_header(self):
        hour = datetime.now().hour
        self.greeting_lbl.setText("Buenos días" if hour < 12 else "Buenas tardes" if hour < 19 else "Buenas noches")
        with get_db() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN duration > 0 THEN duration END), 0) AS secs, "
                "COUNT(DISTINCT genre) AS g, COALESCE(SUM(play_count), 0) AS plays, "
                "COALESCE(SUM(favorite), 0) AS favs FROM songs"
            ).fetchone()
        n = row["n"]
        if not n:
            self.home_stats_lbl.setText("Tu biblioteca está vacía — busca tu primera canción para empezar.")
            return
        parts = [plural(n, "canción", "canciones"), plural(row["g"], "género", "géneros")]
        if row["secs"]:
            h, m = divmod(int(row["secs"]) // 60, 60)
            parts.append(f"{h} h {m} min de música" if h else f"{m} min de música")
        if row["favs"]:
            parts.append(plural(row["favs"], "favorita", "favoritas"))
        parts.append(plural(row["plays"], "reproducción", "reproducciones"))
        self.home_stats_lbl.setText("  ·  ".join(parts))

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def refresh_recent_row(self):
        self._clear_layout(self.recent_row)
        with get_db() as conn:
            rows = conn.execute("SELECT * FROM songs ORDER BY last_played DESC LIMIT 12").fetchall()
        if not rows:
            self.recent_row.addWidget(self._label("Aquí aparecerá lo último que escuches.", "Muted"))
        for row in rows:
            card = SongCard(dict(row))
            card.clicked.connect(self.play_song_by_id)
            card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            card.customContextMenuRequested.connect(lambda pos, c=card: self.show_song_menu(c.song["id"], c.mapToGlobal(pos)))
            self.recent_row.addWidget(card)
        self.recent_row.addStretch()

    def refresh_sidebar_top10(self):
        self.sidebar_top_list.clear()
        with get_db() as conn:
            rows = conn.execute("SELECT * FROM songs ORDER BY play_count DESC, last_played DESC LIMIT 10").fetchall()
        playing_id = self.current_song["id"] if self.current_song else None
        for row in rows:
            song = dict(row)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, song["id"])
            item.setData(ROLE_SONG, song)
            item.setData(ROLE_PLAYING, song["id"] == playing_id)
            item.setToolTip(song["title"])
            self.sidebar_top_list.addItem(item)
        self.sidebar_empty_lbl.setVisible(not rows)

    def refresh_genre_summary_cards(self):
        self._clear_layout(self.genre_cards_grid)
        with get_db() as conn:
            counts = {r["genre"]: r["cnt"] for r in conn.execute("SELECT genre, COUNT(*) AS cnt FROM songs GROUP BY genre")}
        ordered = sorted(GENRES_LIST, key=lambda g: (-counts.get(g, 0), GENRES_LIST.index(g)))
        for idx, g in enumerate(ordered[:8]):
            tile = GenreTile(g, counts.get(g, 0))
            tile.clicked.connect(lambda _c=False, genre=g: self.open_genre_in_library(genre))
            self.genre_cards_grid.addWidget(tile, idx // 4, idx % 4)

    def open_genre_in_library(self, genre: str):
        self.set_library_genre_filter(genre)
        self.switch_page(1)

    def set_library_genre_filter(self, genre: str):
        self.selected_genre_filter = genre
        for key, chip in self.genre_chip_buttons.items():
            chip.setProperty("active", "true" if key == genre else "false")
            chip.style().unpolish(chip)
            chip.style().polish(chip)
        self.refresh_library_table()
        self._update_nav_active()

    def refresh_library_table(self):
        search_txt = self.lib_filter_input.text().strip().lower()
        order = {
            0: "play_count DESC, last_played DESC",
            1: "last_played DESC",
            2: "COALESCE(added_at, last_played) DESC, id DESC",
            3: "genre ASC, play_count DESC",
            4: "title COLLATE NOCASE ASC",
        }[self.lib_sort_combo.currentIndex()]
        with get_db() as conn:
            rows = [dict(r) for r in conn.execute(f"SELECT * FROM songs ORDER BY {order}")]

        flt = self.selected_genre_filter
        filtered = []
        for s in rows:
            if flt == FAV_FILTER and not s.get("favorite"):
                continue
            if flt not in ("Todos", FAV_FILTER) and s.get("genre") != flt:
                continue
            if search_txt and search_txt not in f"{s['title']} {s.get('artist', '')} {s.get('genre', '')}".lower():
                continue
            filtered.append(s)

        self.playlist_queue = filtered
        t = self.library_table
        t.playing_id = self.current_song["id"] if self.current_song else None
        t.setRowCount(len(filtered))
        for i, song in enumerate(filtered):
            num = QTableWidgetItem()
            num.setData(Qt.ItemDataRole.UserRole, song["id"])
            num.setData(ROLE_SONG, song)
            t.setItem(i, 0, num)
            title = QTableWidgetItem()
            title.setToolTip(f"{song['title']}\n{song['file_path']}")
            t.setItem(i, 1, title)
            fav = QTableWidgetItem()
            fav.setToolTip("Quitar de favoritas" if song.get("favorite") else "Me gusta")
            t.setItem(i, LibraryTable.COL_FAV, fav)
            t.setRowHeight(i, 60)

        counts: dict[str, int] = {}
        for s in rows:
            counts[s.get("genre") or "Otros"] = counts.get(s.get("genre") or "Otros", 0) + 1
        for key, chip in self.genre_chip_buttons.items():
            chip.setVisible(key in ("Todos", FAV_FILTER) or key == flt or counts.get(key, 0) > 0)
        self.lib_play_btn.setIcon(make_icon("play", C["on_accent"], 20))
        self.lib_shuffle_btn.setIcon(make_icon("shuffle", C["accent"] if self.shuffle_enabled else C["muted"], 22))

        is_fav = flt == FAV_FILTER
        self.lib_title_lbl.setText("Favoritas" if is_fav else "Tu biblioteca" if flt == "Todos" else flt)
        total, shown = len(rows), len(filtered)
        if is_fav:
            label = plural(shown, "canción que te gusta", "canciones que te gustan")
        elif shown == total:
            label = f"{plural(total, 'canción guardada', 'canciones guardadas')} en tu equipo"
        else:
            label = f"Mostrando {shown} de {total} canciones"
        self.lib_count_lbl.setText(label)
        if shown == 0:
            self.lib_empty_lbl.setText(
                "Todavía no tienes favoritas.\nToca el ♥ junto a una canción para guardarla aquí."
                if is_fav and not search_txt
                else "No hay canciones que coincidan. Prueba otro filtro o busca una canción nueva en Inicio."
            )
        self.lib_empty_lbl.setVisible(shown == 0)
        t.setVisible(shown > 0)
        self.lib_play_btn.setEnabled(shown > 0)
        self.lib_shuffle_btn.setEnabled(shown > 1)
        t.viewport().update()

    # =================================================================
    # BÚSQUEDA CON RESULTADOS Y COLA DE DESCARGAS
    # =================================================================
    def focus_search(self):
        self.switch_page(0)
        self.home_scroll.verticalScrollBar().setValue(0)
        self.search_input.setFocus()
        self.search_input.selectAll()

    def start_search(self):
        query = self.search_input.text().strip()
        if not query:
            return
        self._last_query = query
        self._clear_layout(self.results_box)
        self.result_rows.clear()
        self.results_title.setText(f"Resultados para «{query}»")
        self.results_hint.setText("Buscando en tu biblioteca y en YouTube…")
        self.results_panel.show()
        if self.search_worker and self.search_worker.isRunning():
            self._old_search_workers.append(self.search_worker)
        self.search_worker = YouTubeSearchWorker(query)
        self.search_worker.results_ready.connect(self._on_search_results)
        self.search_worker.failed.connect(self._on_search_failed)
        self.search_worker.start()

    def close_results(self):
        self.results_panel.hide()
        self._clear_layout(self.results_box)
        self.result_rows.clear()

    def _results_section(self, text: str):
        lbl = self._label(text, "Kicker")
        lbl.setContentsMargins(8, 10, 0, 4)
        self.results_box.addWidget(lbl)

    def _on_search_results(self, query: str, local: list, youtube: list):
        self._old_search_workers = [w for w in self._old_search_workers if w.isRunning()]
        if query != self._last_query or self.results_panel.isHidden():
            return
        self._clear_layout(self.results_box)
        self.result_rows.clear()
        yt_local_ids = {r["local_song"]["id"] for r in youtube if r.get("local_song")}
        local = [s for s in local if s["id"] not in yt_local_ids]
        if not local and not youtube:
            self.results_hint.setText("No se encontraron resultados. Prueba con otras palabras.")
            return
        self.results_hint.setText("Elige la versión correcta (oficial, en vivo, con letra…). Haz clic para descargar o reproducir.")
        if local:
            self._results_section("EN TU BIBLIOTECA")
            for song in local:
                row = ResultRow(song, "local")
                row.activated.connect(self._on_result_activated)
                self.results_box.addWidget(row)
        if youtube:
            self._results_section("EN YOUTUBE")
            states = {j["id"]: "En cola para guardar" for j in self.download_queue}
            if self.current_job:
                states[self.current_job["id"]] = "Guardando…"
            for res in youtube:
                row = ResultRow(res, "yt")
                if res["id"] in states:
                    row.set_state(states[res["id"]])
                row.activated.connect(self._on_result_activated)
                self.results_box.addWidget(row)
                self.result_rows[res["id"]] = row

    def _on_search_failed(self, query: str, err: str):
        if query == self._last_query:
            self.results_hint.setText(f"No se pudo buscar en YouTube (¿sin internet?). {err[:160]}")

    def _on_result_activated(self, row: ResultRow):
        if row.kind == "local":
            self.play_song_by_id(row.data["id"])
            return
        local_song = row.data.get("local_song")
        if local_song and os.path.exists(local_song.get("file_path", "")):
            self.play_song_by_id(local_song["id"])
            return
        self.play_online(dict(row.data))

    def _rows_for(self, vid: str) -> list[ResultRow]:
        return [r for r in (self.result_rows.get(vid), self.explore_rows.get(vid), self.artist_rows.get(vid)) if r is not None]

    def _set_row_state(self, vid: str, text: str):
        for r in self._rows_for(vid):
            r.set_state(text)

    def _is_saving(self, vid) -> bool:
        if not vid:
            return False
        return bool((self.current_job and self.current_job["id"] == vid) or any(j["id"] == vid for j in self.download_queue))

    def enqueue_download(self, res: dict, quiet: bool = False, favorite: bool = False):
        vid = res["id"]
        if self._is_saving(vid):
            if favorite:
                for j in [self.current_job, *self.download_queue]:
                    if j and j["id"] == vid:
                        j["favorite"] = True
            return
        busy = self.worker is not None or bool(self.download_queue)
        self.download_queue.append({"id": vid, "title": res["title"], "url": res["url"], "favorite": favorite})
        self._set_row_state(vid, "En cola para guardar")
        if busy and not quiet:
            self.toast.show_message("Se guardará cuando terminen las otras descargas")
        self._start_next_download()
        self._refresh_visual_state()

    def _start_next_download(self):
        if self.worker is not None or not self.download_queue:
            self._update_download_banner()
            return
        job = self.download_queue.pop(0)
        self.current_job = job
        self.worker = SearchDownloadWorker(job["title"], self.settings, url=job["url"], video_id=job["id"])
        self.worker.progress.connect(self._on_download_progress)
        self.worker.completed.connect(lambda song, dl, j=job: self._on_download_completed(song, dl, j))
        self.worker.failed.connect(lambda err, j=job: self._on_download_failed(err, j))
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()
        self._set_row_state(job["id"], "Guardando…")
        self.status_progress.setRange(0, 0)
        self._update_download_banner()

    def _update_download_banner(self):
        if not self.current_job:
            self.status_banner.hide()
            return
        self.status_banner.show()
        self.status_label.setText(f"Guardando en tu biblioteca «{display_title(self.current_job['title'])}»")
        n = len(self.download_queue)
        self.status_queue_lbl.setText(f"+{n} en cola" if n else "")

    def _on_download_progress(self, pct: int):
        if pct < 0:
            self.status_progress.setRange(0, 0)
            text = "Procesando…"
        else:
            self.status_progress.setRange(0, 100)
            self.status_progress.setValue(pct)
            text = f"Guardando {pct}%"
        if self.current_job:
            self._set_row_state(self.current_job["id"], text)

    def _on_download_completed(self, song: dict, _was_downloaded: bool, job: dict):
        cur = self.current_song
        is_current = bool(cur and cur.get("stream") and cur.get("source_id") == job["id"])
        if job.get("favorite") or (is_current and cur.get("favorite")):
            with get_db() as conn:
                conn.execute("UPDATE songs SET favorite = 1 WHERE id = ?", (song["id"],))
                conn.commit()
        saved = self._song_by_id(song["id"]) or song
        for r in self._rows_for(job["id"]):
            r.data["local_song"] = saved
            r.set_state("En tu biblioteca")
        if self.pages.currentIndex() == 4 and self.song_page_song and self.song_page_song.get("source_id") == job["id"]:
            QTimer.singleShot(0, lambda sid=saved["id"]: self.open_song_page(sid))
        if is_current:
            # Sigue sonando sin cortes; desde ahora es una canción de tu biblioteca
            self.current_song = saved
            self._apply_now_playing_visuals(saved, None)
            self.hero_source_badge.setText("Guardada en tu biblioteca")
            self.settings["last_song_id"] = saved["id"]
            save_settings(self.settings)
            self.toast.show_message("Guardada en tu biblioteca ✓  La próxima vez sonará sin internet")
            if self.mpris:
                self.mpris.notify("Metadata")
        else:
            self.toast.show_message(f"Guardada: {display_title(saved['title'], saved.get('artist', ''))}")
            self.desktop_notify("Guardada en tu biblioteca", display_title(saved["title"], saved.get("artist", "")), saved.get("thumbnail_path", ""))
        self.refresh_all_views()

    def _on_download_failed(self, err: str, job: dict):
        self._set_row_state(job["id"], "")
        cur = self.current_song
        if cur and cur.get("stream") and cur.get("source_id") == job["id"]:
            self.toast.show_message("No se pudo guardar; sigue sonando en línea", 4000)
            return
        show_message(
            self,
            "No se pudo guardar",
            f"«{job['title']}»\n\n{err[:400]}\n\nSi pasa seguido, actualiza el motor de descargas en Ajustes → Mantenimiento.",
            "error",
        )

    def _on_worker_finished(self):
        self.worker = None
        self.current_job = None
        self._start_next_download()
        self._refresh_visual_state()

    # ----------------------------- Escuchar en línea -----------------------------
    def _local_by_source(self, vid: str) -> dict | None:
        if not vid:
            return None
        with get_db() as conn:
            row = conn.execute("SELECT * FROM songs WHERE source_id = ? ORDER BY id LIMIT 1", (vid,)).fetchone()
        return dict(row) if row and os.path.exists(row["file_path"]) else None

    def _start_worker(self, worker):
        self._workers.add(worker)
        worker.finished.connect(lambda w=worker: self._workers.discard(w))
        worker.start()

    def play_online(self, item: dict, done_cb=None):
        """Suena al instante desde internet; si el modo es 'guardar', se descarga en paralelo."""
        if self._is_repeat_click(("online", item.get("id") or item.get("query"))):
            if done_cb:
                done_cb()
            return
        local = self._local_by_source(item.get("id", ""))
        if local:
            if done_cb:
                done_cb()
            self.play_song_by_id(local["id"])
            return
        if self._online_done_cb:
            self._online_done_cb()
        self._play_token += 1
        self._online_done_cb = done_cb
        if item.get("id"):
            self._set_row_state(item["id"], "Cargando…")
        self.toast.show_message("Conectando…", 1800)
        worker = OnlinePlayWorker(self._play_token, item, self.settings.get("audio_format", "best"))
        worker.ready.connect(self._on_online_ready)
        worker.failed.connect(self._on_online_failed)
        self._start_worker(worker)

    def _finish_online_cb(self, token: int):
        if token == self._play_token and self._online_done_cb:
            self._online_done_cb()
            self._online_done_cb = None

    def _on_online_ready(self, token: int, item: dict, stream_url: str):
        if item.get("id") and not self._is_saving(item["id"]):
            self._set_row_state(item["id"], "")
        self._finish_online_cb(token)
        if token != self._play_token:
            return
        local = self._local_by_source(item["id"])
        if local:
            self.play_song_by_id(local["id"])
            return
        yt_title = item.get("yt_title") or item.get("title") or ""
        artist = item.get("artist") or extract_artist_from_title(yt_title, item.get("channel") or "YouTube")
        title = item.get("title") or yt_title
        song = {
            "id": None,
            "stream": True,
            "source_id": item["id"],
            "url": item["url"],
            "title": title,
            "artist": artist,
            "genre": detect_genre(f"{title} {yt_title}", artist),
            "thumbnail_path": item.get("cover") or item.get("thumb") or "",
            "duration": int(item.get("duration") or 0),
            "file_path": "",
            "play_count": 0,
            "favorite": 0,
        }
        self.play_song_dict(song, stream_url=stream_url)
        if self.settings.get("listen_mode", "save") == "save":
            self.enqueue_download({"id": item["id"], "title": yt_title or title, "url": item["url"]}, quiet=True)
        self._refresh_visual_state()

    def _on_online_failed(self, token: int, err: str):
        self._finish_online_cb(token)
        if token != self._play_token:
            return
        show_message(self, "No se pudo reproducir", f"{err[:400]}\n\n¿Hay internet? Si el problema sigue, actualiza el motor de descargas en Ajustes → Mantenimiento.", "error")

    def _save_current_stream(self, favorite: bool = False):
        cur = self.current_song
        if not cur or not cur.get("stream"):
            return
        self.enqueue_download({"id": cur["source_id"], "title": cur["title"], "url": cur["url"]}, quiet=True, favorite=favorite)
        self.toast.show_message("Guardando en tu biblioteca…")
        self._refresh_visual_state()

    def set_listen_mode(self, mode: str):
        self.settings["listen_mode"] = mode
        save_settings(self.settings)
        self._refresh_visual_state()
        self.toast.show_message("Modo: escuchar y guardar" if mode == "save" else "Modo: solo en línea")

    # ----------------------------- Página de la canción -----------------------------
    def _glass_icon_btn(self, icon: str, tip: str, slot) -> QPushButton:
        b = QPushButton()
        b.setProperty("class", "GlassIcon")
        b.setIcon(make_icon(icon, "#ffffff", 18))
        b.setIconSize(QSize(18, 18))
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.clicked.connect(slot)
        return b

    def _create_song_page(self) -> QWidget:
        scroll, vbox = self._scroll_page()
        self.song_scroll = scroll
        back = QPushButton("  Volver")
        back.setProperty("class", "GhostBtn")
        back.setIcon(make_icon("prev", C["muted"], 14))
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        back.clicked.connect(self._song_page_back)
        vbox.addWidget(back, alignment=Qt.AlignmentFlag.AlignLeft)

        self.sp_hero = HeroCard()
        self.sp_hero.setMinimumHeight(300)
        hero = QHBoxLayout(self.sp_hero)
        hero.setContentsMargins(32, 32, 32, 32)
        hero.setSpacing(32)
        self.sp_art = QLabel()
        self.sp_art.setFixedSize(236, 236)
        shadow = QGraphicsDropShadowEffect(self.sp_art)
        shadow.setBlurRadius(56)
        shadow.setOffset(0, 16)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.sp_art.setGraphicsEffect(shadow)
        hero.addWidget(self.sp_art, alignment=Qt.AlignmentFlag.AlignVCenter)
        info = QVBoxLayout()
        info.setSpacing(6)
        info.addStretch()
        self.sp_kicker = self._label("CANCIÓN", "HeroKicker")
        info.addWidget(self.sp_kicker)
        self.sp_title = self._label("", "HeroTitle")
        self.sp_title.setWordWrap(True)
        self.sp_title.setMaximumHeight(96)
        info.addWidget(self.sp_title)
        self.sp_artist = self._label("", "HeroArtist")
        self.sp_artist.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sp_artist.setToolTip("Ver todas sus canciones en tu biblioteca")
        self.sp_artist.mousePressEvent = lambda _e: self._open_artist_in_library()
        info.addWidget(self.sp_artist)
        badges = QHBoxLayout()
        badges.setSpacing(8)
        self.sp_badges = [self._label("", "GlassBadge") for _ in range(4)]
        for b in self.sp_badges:
            badges.addWidget(b)
        badges.addStretch()
        info.addSpacing(6)
        info.addLayout(badges)
        info.addSpacing(12)
        acts = QHBoxLayout()
        acts.setSpacing(10)
        self.sp_play = QPushButton()
        self.sp_play.setObjectName("BigPlayBtn")
        self.sp_play.setIconSize(QSize(20, 20))
        self.sp_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sp_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sp_play.clicked.connect(self._song_page_play)
        acts.addWidget(self.sp_play)
        self.sp_fav = self._glass_icon_btn("heart", "Me gusta", self._song_page_fav)
        self.sp_queue = self._glass_icon_btn("queue", "Añadir a la cola", lambda: self._song_page_action("queue"))
        self.sp_edit = self._glass_icon_btn("edit", "Editar información", lambda: self._song_page_action("edit"))
        self.sp_folder = self._glass_icon_btn("folder", "Mostrar en la carpeta", lambda: self._song_page_action("folder"))
        for b in (self.sp_fav, self.sp_queue, self.sp_edit, self.sp_folder):
            acts.addWidget(b)
        self.sp_save = QPushButton("Guardar")
        self.sp_save.setProperty("class", "GlassBtn")
        self.sp_save.setIcon(make_icon("download", "#ffffff", 16))
        self.sp_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sp_save.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sp_save.clicked.connect(lambda: (self._save_current_stream(), self.open_song_page()))
        acts.addWidget(self.sp_save)
        acts.addStretch()
        info.addLayout(acts)
        info.addStretch()
        hero.addLayout(info, stretch=1)
        vbox.addWidget(self.sp_hero)

        # Detalles
        card = QFrame()
        card.setProperty("class", "Card")
        grid = QGridLayout(card)
        grid.setContentsMargins(24, 20, 24, 20)
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(14)
        self.sp_details: dict[str, QLabel] = {}
        fields = [("Formato", "fmt"), ("Tamaño", "size"), ("Duración", "dur"), ("Escuchas", "plays"),
                  ("Agregada", "added"), ("Última vez", "last"), ("Género", "genre"), ("Ubicación", "path")]
        for i, (label, key) in enumerate(fields):
            r, c = divmod(i, 4)
            box = QVBoxLayout()
            box.setSpacing(3)
            box.addWidget(self._label(label.upper(), "Kicker"))
            val = self._label("", "RowTitle", ElidedLabel)
            self.sp_details[key] = val
            box.addWidget(val)
            grid.addLayout(box, r, c)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        vbox.addWidget(card)

        # Más del artista
        self.sp_more_title = self._label("", "H2")
        vbox.addWidget(self.sp_more_title)
        self.sp_more_hint = self._label("", "Dim")
        vbox.addWidget(self.sp_more_hint)
        sc, self.sp_more_row = self._hscroll(SongCard.ART + 82 + 14)
        self.sp_more_scroll = sc
        vbox.addWidget(sc)
        self.sp_online_title = self._label("", "H2")
        vbox.addWidget(self.sp_online_title)
        self.sp_online_hint = self._label("", "Dim")
        vbox.addWidget(self.sp_online_hint)
        sc, self.sp_top_row = self._hscroll(ChartCard.ART + 82 + 14)
        self.sp_top_scroll = sc
        sc.hide()
        vbox.addWidget(sc)
        self.sp_online_box = QVBoxLayout()
        self.sp_online_box.setSpacing(2)
        vbox.addLayout(self.sp_online_box)
        vbox.addStretch(1)
        return scroll

    def open_song_page(self, song_id: int | None = None):
        """Abre la ficha de una canción (por defecto, la que suena)."""
        if song_id is not None:
            song = self._song_by_id(song_id)
            if song:
                song["_follow"] = bool(self.current_song and self.current_song.get("id") == song_id)
        else:
            song = dict(self.current_song) if self.current_song else None
            if song:
                song["_follow"] = True
        if not song:
            self.toast.show_message("Elige una canción para ver sus detalles")
            return
        if self.pages.currentIndex() != 4:
            self._song_page_prev = self.pages.currentIndex()
        self.song_page_song = song
        self._fill_song_page(song)
        self.pages.setCurrentIndex(4)
        self.song_scroll.verticalScrollBar().setValue(0)
        self._update_nav_active()

    def _song_page_back(self):
        self.switch_page(getattr(self, "_song_page_prev", 0))

    def _fill_song_page(self, song: dict):
        genre = song.get("genre") or "Otros"
        thumb = song.get("thumbnail_path") or ""
        artist = song.get("artist") or "Artista desconocido"
        title = display_title(song["title"], artist)
        is_stream = bool(song.get("stream"))
        self.sp_hero.set_color(dominant_color(thumb, genre))
        self.sp_art.setPixmap(create_artwork_pixmap(title, genre, thumb, 236, 16))
        playing_this = self._is_current(song)
        self.sp_kicker.setText("SONANDO AHORA" if playing_this else "CANCIÓN")
        self.sp_title.setText(title)
        self.sp_title.setToolTip(song["title"])
        self.sp_artist.setText(artist)
        plays = int(song.get("play_count") or 0)
        dur = fmt_seconds(int(song.get("duration") or 0))
        badges = [genre, dur, "En línea" if is_stream else plural(plays, "escucha", "escuchas"),
                  "♥ Favorita" if song.get("favorite") else ""]
        for lbl, text in zip(self.sp_badges, badges):
            lbl.setText(text)
            lbl.setVisible(bool(text) and text != "—")
        self._refresh_song_page_buttons()

        # Detalles del archivo
        path = Path(song.get("file_path") or "")
        exists = bool(song.get("file_path")) and path.exists()
        ext = path.suffix.lower().lstrip(".") if exists else ""
        fmt_names = {"opus": "Opus · máxima calidad", "m4a": "M4A / AAC", "mp3": "MP3", "flac": "FLAC · sin pérdida", "webm": "WebM / Opus", "ogg": "OGG", "wav": "WAV · sin compresión"}
        size_mb = path.stat().st_size / 1_048_576 if exists else 0
        d = self.sp_details
        d["fmt"].setText(fmt_names.get(ext, ext.upper() or ("En línea (no guardada)" if is_stream else "—")))
        d["size"].setText(f"{size_mb:.1f} MB" if exists else "—")
        if exists and song.get("duration"):
            d["size"].setText(f"{size_mb:.1f} MB · {round(size_mb * 8388.6 / max(1, int(song['duration'])))} kbps")
        d["dur"].setText(dur)
        d["plays"].setText(str(plays) if not is_stream else "—")
        d["added"].setText(humanize_dt(song.get("added_at")) if song.get("added_at") else "—")
        d["last"].setText(humanize_dt(song.get("last_played")) if not is_stream else "Ahora")
        d["genre"].setText(genre)
        d["path"].setText(str(path).replace(str(Path.home()), "~") if exists else ("Se está guardando…" if self._is_saving(song.get("source_id")) else "—"))

        # Más del artista en tu biblioteca
        self._clear_layout(self.sp_more_row)
        with get_db() as conn:
            others = [dict(r) for r in conn.execute(
                "SELECT * FROM songs WHERE LOWER(artist) = LOWER(?) AND id != ? ORDER BY play_count DESC LIMIT 20",
                (artist, song.get("id") or -1),
            )]
        self.sp_more_title.setText(f"Más de {artist} en tu biblioteca")
        self.sp_more_hint.setText("" if others else "Todavía no tienes otras canciones de este artista. Mira abajo lo más escuchado.")
        self.sp_more_hint.setVisible(not others)
        self.sp_more_scroll.setVisible(bool(others))
        for o in others:
            c = SongCard(o)
            c.clicked.connect(self.play_song_by_id)
            c.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            c.customContextMenuRequested.connect(lambda pos, cc=c: self.show_song_menu(cc.song["id"], cc.mapToGlobal(pos)))
            self.sp_more_row.addWidget(c)
        self.sp_more_row.addStretch()

        # Lo más escuchado del artista en internet
        unknown = artist.lower() in ("artista desconocido", "youtube", "youtube music", "")
        self.sp_online_title.setText(f"Lo más escuchado de {artist}" if not unknown else "Canciones parecidas")
        key = f"artist:{artist}" if not unknown else f"{title} {genre}"
        if key != self._artist_query:
            self._artist_query = key
            self._clear_layout(self.sp_online_box)
            self._clear_layout(self.sp_top_row)
            self.sp_top_scroll.hide()
            self.artist_rows.clear()
            self.sp_online_hint.setText("Buscando…")
            self.sp_online_hint.show()
            if unknown:
                self._search_artist_youtube(key)
            else:
                worker = ArtistTopWorker(artist)
                worker.ready.connect(self._on_artist_top)
                worker.failed.connect(lambda a, e, k=key: self._search_artist_youtube(k, f"{a} canciones") if k == self._artist_query else None)
                self._start_worker(worker)
        else:
            self._mark_artist_cards()

    def _search_artist_youtube(self, key: str, query: str | None = None):
        self._artist_yt_query = query or key
        worker = YouTubeSearchWorker(self._artist_yt_query, max_results=8)
        worker.results_ready.connect(lambda q, loc, yt, k=key: self._on_artist_results(k, loc, yt) if q == self._artist_yt_query else None)
        worker.failed.connect(lambda q, e, k=key: self.sp_online_hint.setText("No se pudo buscar (¿sin internet?).") if k == self._artist_query else None)
        self._start_worker(worker)

    def _on_artist_top(self, artist: str, tracks: list):
        key = f"artist:{artist}"
        if key != self._artist_query:
            return
        if not tracks:
            self._search_artist_youtube(key, f"{artist} canciones")
            return
        self._clear_layout(self.sp_top_row)
        for i, t in enumerate(tracks, 1):
            card = ChartCard(t, i)
            card.clicked.connect(self.play_chart_card)
            self.sp_top_row.addWidget(card)
        self.sp_top_row.addStretch()
        self._mark_artist_cards()
        self.sp_top_scroll.show()
        self.sp_online_hint.setText("Su top real (Deezer). Toca para escuchar al instante; las que ya tienes llevan ✓.")

    def _mark_artist_cards(self):
        keys = self._library_keys()
        for i in range(self.sp_top_row.count()):
            card = self.sp_top_row.itemAt(i).widget()
            if isinstance(card, ChartCard):
                card.in_library = self._match_library(card.track, keys)
                card.update()

    def _on_artist_results(self, query: str, _local: list, youtube: list):
        if query != self._artist_query:
            return
        self._clear_layout(self.sp_online_box)
        self.artist_rows.clear()
        cur_src = (self.song_page_song or {}).get("source_id")
        youtube = [r for r in youtube if r["id"] != cur_src]
        self.sp_online_hint.setText("Toca para escuchar al instante." if youtube else "No se encontraron resultados.")
        for res in youtube:
            row = ResultRow(res, "yt")
            if self._is_saving(res["id"]):
                row.set_state("Guardando…")
            row.activated.connect(self._on_result_activated)
            self.sp_online_box.addWidget(row)
            self.artist_rows[res["id"]] = row

    def _is_current(self, song: dict | None) -> bool:
        cur = self.current_song
        if not cur or not song:
            return False
        if song.get("id") and cur.get("id") == song.get("id"):
            return True
        return bool(song.get("source_id") and cur.get("source_id") == song.get("source_id"))

    def _refresh_song_page_buttons(self):
        song = self.song_page_song
        if not song:
            return
        playing = self._is_current(song) and self.player.is_playing()
        self.sp_play.setIcon(make_icon("pause" if playing else "play", C["on_accent"], 20))
        self.sp_play.setToolTip("Pausar" if playing else "Reproducir")
        fav = bool(song.get("favorite"))
        self.sp_fav.setIcon(make_icon("heart_fill" if fav else "heart", C["accent"] if fav else "#ffffff", 18))
        self.sp_fav.setToolTip("Quitar de favoritas" if fav else "Me gusta")
        saved = bool(song.get("id"))
        for b in (self.sp_queue, self.sp_edit, self.sp_folder):
            b.setVisible(saved)
        self.sp_save.setVisible(bool(song.get("stream")) and not saved and not self._is_saving(song.get("source_id")))

    def _song_page_play(self):
        song = self.song_page_song
        if not song:
            return
        if self._is_current(song):
            self.toggle_play_pause()
        elif song.get("id"):
            self.play_song_by_id(song["id"])
        QTimer.singleShot(250, self._refresh_song_page_buttons)

    def _song_page_fav(self):
        song = self.song_page_song
        if not song:
            return
        if song.get("id"):
            self.toggle_favorite(song["id"])
            fresh = self._song_by_id(song["id"])
            if fresh:
                fresh["_follow"] = song.get("_follow")
                self.song_page_song = fresh
                self._fill_song_page(fresh)
        elif self._is_current(song):
            self.toggle_current_favorite()
            song["favorite"] = 1
            self._refresh_song_page_buttons()

    def _song_page_action(self, action: str):
        song = self.song_page_song
        if not song or not song.get("id"):
            return
        sid = song["id"]
        if action == "queue":
            self.add_to_queue(sid)
        elif action == "edit":
            self.edit_song(sid)
            self.open_song_page(sid)
        elif action == "folder":
            self.open_path(str(Path(song["file_path"]).parent))

    def _open_artist_in_library(self):
        song = self.song_page_song
        if not song or not song.get("artist"):
            return
        self.lib_filter_input.setText(song["artist"])
        self.open_genre_in_library("Todos")

    # ----------------------------- Explorar -----------------------------
    def _hscroll(self, height: int):
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sc.setFixedHeight(height)
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        sc.setWidget(host)
        return sc, row

    def _create_explore_page(self) -> QWidget:
        scroll, vbox = self._scroll_page()
        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(self._label("Explorar", "H1"))
        sub = self._label("Lo más escuchado ahora. Toca cualquier canción: suena al instante y se guarda sola en tu biblioteca.", "Muted")
        sub.setWordWrap(True)
        head.addWidget(sub)
        vbox.addLayout(head)

        self.chart_rows: dict[str, QHBoxLayout] = {}
        self.chart_status: dict[str, QLabel] = {}
        for kind in ("peru", "global"):
            title = DEEZER_SOURCES[kind][0]
            vbox.addLayout(self._section_header(title, "Actualizar", lambda _c=False, k=kind: self.load_chart(k, force=True)))
            status = self._label("Cargando…", "Dim")
            self.chart_status[kind] = status
            vbox.addWidget(status)
            sc, row = self._hscroll(ChartCard.ART + 82 + 14)
            self.chart_rows[kind] = row
            vbox.addWidget(sc)

        vbox.addLayout(self._section_header("Lo más escuchado por género"))
        chips_sc, chips = self._hscroll(46)
        chips.setSpacing(8)
        self.explore_chips: dict[str, QPushButton] = {}
        for label, _q in EXPLORE_GENRES:
            chip = QPushButton(label)
            chip.setProperty("class", "GenreChip")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            chip.clicked.connect(lambda _c=False, lb=label: self.load_explore_genre(lb))
            chips.addWidget(chip)
            self.explore_chips[label] = chip
        chips.addStretch()
        vbox.addWidget(chips_sc)
        self.explore_hint = self._label("", "Dim")
        vbox.addWidget(self.explore_hint)
        self.explore_box = QVBoxLayout()
        self.explore_box.setSpacing(2)
        vbox.addLayout(self.explore_box)
        vbox.addStretch(1)
        return scroll

    def open_explore(self):
        self.switch_page(3)
        for kind in ("peru", "global"):
            if kind not in self.charts_loaded:
                self.load_chart(kind)
        if not self._explore_query:
            self.load_explore_genre(EXPLORE_GENRES[0][0])

    def load_chart(self, kind: str, force: bool = False):
        if force:
            (SEARCH_CACHE_DIR / f"chart_{kind}.json").unlink(missing_ok=True)
        self.charts_loaded.add(kind)
        self.chart_status[kind].setText("Cargando…")
        self.chart_status[kind].show()
        worker = ChartWorker(kind)
        worker.ready.connect(self._on_chart_ready)
        worker.failed.connect(self._on_chart_failed)
        self._start_worker(worker)

    def _library_keys(self) -> list[tuple[str, str]]:
        with get_db() as conn:
            return [((r["title"] or "").lower(), (r["artist"] or "").lower()) for r in conn.execute("SELECT title, artist FROM songs")]

    def _match_library(self, track: dict, keys=None) -> bool:
        t = track["title"].lower().split(" (")[0].strip()
        a = track["artist"].lower().split(",")[0].strip()
        for title, artist in keys if keys is not None else self._library_keys():
            if t and t in title and (a in artist or a in title):
                return True
        return False

    def _on_chart_ready(self, kind: str, tracks: list):
        row = self.chart_rows[kind]
        self._clear_layout(row)
        keys = self._library_keys()
        for i, t in enumerate(tracks, 1):
            card = ChartCard(t, i)
            card.in_library = self._match_library(t, keys)
            card.clicked.connect(self.play_chart_card)
            row.addWidget(card)
        row.addStretch()
        self.chart_status[kind].setVisible(not tracks)
        self.chart_status[kind].setText("Sin datos por ahora.")

    def _on_chart_failed(self, kind: str, err: str):
        self.charts_loaded.discard(kind)
        self.chart_status[kind].setText(f"No se pudo cargar (¿sin internet?). {err[:120]}")

    def play_chart_card(self, card: ChartCard):
        t = card.track
        if card.in_library:
            with get_db() as conn:
                rows = [dict(r) for r in conn.execute("SELECT * FROM songs")]
            for song in rows:
                if self._match_library(t, [((song["title"] or "").lower(), (song["artist"] or "").lower())]) and os.path.exists(song["file_path"]):
                    self.play_song_by_id(song["id"])
                    return
        card.set_loading(True)
        item = {"query": t["query"], "title": t["title"], "artist": t["artist"], "duration": t["duration"], "cover": t.get("cover", "")}
        self.play_online(item, done_cb=lambda c=card: c.set_loading(False))

    def load_explore_genre(self, label: str):
        query = dict(EXPLORE_GENRES)[label]
        query = f"{query} {datetime.now().year}"
        self._explore_query = query
        for key, chip in self.explore_chips.items():
            chip.setProperty("active", "true" if key == label else "false")
            chip.style().unpolish(chip)
            chip.style().polish(chip)
        self._clear_layout(self.explore_box)
        self.explore_rows.clear()
        self.explore_hint.setText(f"Buscando lo más escuchado de {label}…")
        worker = YouTubeSearchWorker(query, max_results=12)
        worker.results_ready.connect(self._on_explore_results)
        worker.failed.connect(lambda q, e: self.explore_hint.setText(f"No se pudo buscar (¿sin internet?). {e[:120]}") if q == self._explore_query else None)
        self._start_worker(worker)

    def _on_explore_results(self, query: str, _local: list, youtube: list):
        if query != self._explore_query:
            return
        self._clear_layout(self.explore_box)
        self.explore_rows.clear()
        self.explore_hint.setText("Toca una canción para escucharla al instante." if youtube else "No se encontraron resultados.")
        for res in youtube:
            row = ResultRow(res, "yt")
            if self._is_saving(res["id"]):
                row.set_state("Guardando…")
            row.activated.connect(self._on_result_activated)
            self.explore_box.addWidget(row)
            self.explore_rows[res["id"]] = row

    # =================================================================
    # REPRODUCCIÓN
    # =================================================================
    def on_library_row_activated(self, row: int, _col: int):
        item = self.library_table.item(row, 0)
        if item:
            self.play_song_by_id(item.data(Qt.ItemDataRole.UserRole))

    def on_library_cell_clicked(self, row: int, col: int):
        if col == LibraryTable.COL_FAV:
            item = self.library_table.item(row, 0)
            if item:
                self.toggle_favorite(item.data(Qt.ItemDataRole.UserRole))

    def play_current_list(self, shuffle: bool):
        if not self.playlist_queue:
            return
        if self.shuffle_enabled != shuffle:
            self.toggle_shuffle()
        first = random.choice(self.playlist_queue) if shuffle else self.playlist_queue[0]
        self.up_next.clear()
        self.play_song_by_id(first["id"])

    def _is_repeat_click(self, key) -> bool:
        """Evita que un doble clic arranque la misma canción dos veces ('bun bun' al inicio)."""
        now = time.monotonic()
        if key == self._last_play_key and now - self._last_play_time < 1.0:
            return True
        self._last_play_key, self._last_play_time = key, now
        return False

    def play_song_by_id(self, song_id: int, record_history: bool = True):
        if self._is_repeat_click(("song", song_id)):
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_db() as conn:
            row = conn.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
            if not row:
                return
            if not os.path.exists(row["file_path"]):
                show_message(
                    self,
                    "Archivo no encontrado",
                    f"El archivo ya no está en:\n{row['file_path']}\n\nPuedes quitarlo en Ajustes → Mantenimiento.",
                    "warning",
                )
                return
            conn.execute("UPDATE songs SET play_count = play_count + 1, last_played = ? WHERE id = ?", (now, song_id))
            conn.commit()
            song = dict(conn.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone())
        self.play_song_dict(song, was_downloaded=False, record_history=record_history)
        self.refresh_all_views()

    def play_song_dict(self, song: dict, was_downloaded: bool = False, record_history: bool = True, stream_url: str = ""):
        prev = self.current_song
        if record_history and prev and prev.get("id") and prev["id"] != song.get("id"):
            self.history.append(prev["id"])
            del self.history[:-100]
        self.current_song = song
        self.resume_ms = 0
        self._apply_now_playing_visuals(song, None if stream_url else was_downloaded)
        self.player.set_media(self.vlc_instance.media_new(stream_url or song["file_path"]))
        self.player.play()
        self.media_loaded = True
        self.btn_play_pause.setEnabled(True)
        self._set_play_icon(True)
        self.seek_slider.setEnabled(True)
        if song.get("id"):
            self.settings["last_song_id"] = song["id"]
            self.settings["last_position_ms"] = 0
            save_settings(self.settings)
        if self.mpris:
            self.mpris.notify("Metadata", "PlaybackStatus", "CanPlay", "CanPause", "CanSeek")
        self.desktop_notify(display_title(song["title"], song.get("artist", "")), song.get("artist") or "", song.get("thumbnail_path", ""))

    def _apply_now_playing_visuals(self, song: dict, was_downloaded: bool | None = None, resumed: bool = False):
        genre = song.get("genre") or "Otros"
        thumb = song.get("thumbnail_path") or ""
        artist = song.get("artist") or "Artista desconocido"
        title = display_title(song["title"], artist)
        plays = song.get("play_count", 0)
        self.hero_card.set_color(dominant_color(thumb, genre))
        self.hero_artwork.setPixmap(create_artwork_pixmap(title, genre, thumb, 196, 14))
        self.hero_kicker.setText("CONTINUAR ESCUCHANDO" if resumed else "SONANDO AHORA")
        self.hero_title.setText(title)
        self.hero_title.setToolTip(song["title"])
        self.hero_artist.setText(artist)
        if was_downloaded is not None:
            self.hero_source_badge.setText("Recién descargada" if was_downloaded else "Desde tu biblioteca")
        if song.get("stream"):
            self.hero_genre_badge.setText(genre)
            self.hero_source_badge.setText("En línea")
            saving = self.settings.get("listen_mode", "save") == "save" or self._is_saving(song.get("source_id"))
            self.hero_meta.setText("Sonando desde internet · guardándose en tu biblioteca…" if saving else "Sonando desde internet · no se guarda (modo solo en línea)")
        else:
            self.hero_genre_badge.setText(f"{genre}  ·  {plural(plays, 'escucha', 'escuchas')}")
            self.hero_meta.setText(song["file_path"].replace(str(Path.home()), "~"))
        self.footer_art.setPixmap(create_artwork_pixmap(title, genre, thumb, 58, 8))
        self.footer_title.setText(title)
        self.footer_sub.setText(f"{artist}  ·  {genre}")
        self.titlebar.set_subtitle(f"{title} — {artist}")
        self.library_table.playing_id = song.get("id")
        self.library_table.viewport().update()
        self._refresh_fav_buttons()
        if self.pages.currentIndex() == 4 and (self.song_page_song is None or self.song_page_song.get("_follow")):
            QTimer.singleShot(0, lambda: self.open_song_page())

    def _reset_now_playing(self):
        self.player.stop()
        self.current_song = None
        self.media_loaded = False
        self.hero_card.set_color(QColor(C["accent_mid"]))
        self.hero_artwork.setPixmap(create_artwork_pixmap("", "Otros", "", 196, 14))
        self.hero_kicker.setText("BIENVENIDO")
        self.hero_title.setText("Tu música, en tu escritorio")
        self.hero_artist.setText("Busca una canción arriba o elige una de tu biblioteca")
        self.hero_genre_badge.setText("Género automático")
        self.hero_source_badge.setText("100% local")
        self.hero_meta.setText("")
        self.footer_art.setPixmap(create_artwork_pixmap("", "Otros", "", 58, 8))
        self.footer_title.setText("Nada sonando")
        self.footer_sub.setText("Elige una canción para empezar")
        self.titlebar.set_subtitle("")
        self.btn_play_pause.setEnabled(False)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setValue(0)
        self.lbl_time_cur.setText("0:00")
        self.lbl_time_tot.setText("0:00")
        self.settings["last_song_id"] = None
        save_settings(self.settings)
        if self.mpris:
            self.mpris.notify("Metadata", "PlaybackStatus", "CanPlay", "CanPause", "CanSeek")

    def toggle_play_pause(self):
        if not self.current_song:
            if self.playlist_queue:
                self.play_song_by_id(self.playlist_queue[0]["id"])
            return
        if not self.media_loaded:
            # Continuar la sesión anterior desde donde se quedó
            self.player.set_media(self.vlc_instance.media_new(self.current_song["file_path"]))
            self.player.play()
            self.media_loaded = True
            self._set_play_icon(True)
            self.hero_kicker.setText("SONANDO AHORA")
        elif self.player.is_playing():
            self.player.pause()
            self._set_play_icon(False)
        else:
            if self.player.get_state() == vlc.State.Ended:
                self.player.stop()
            self.player.play()
            self._set_play_icon(True)
        if self.mpris:
            QTimer.singleShot(150, lambda: self.mpris.notify("PlaybackStatus", "Metadata"))

    def seek_relative_ms(self, delta_ms: int):
        if not self.current_song or not self.media_loaded:
            return
        length = self.player.get_length()
        if length > 0:
            target = max(0, min(length - 500, self.player.get_time() + delta_ms))
            self.player.set_time(target)
            if self.mpris:
                self.mpris.seeked(target)

    def play_next_song(self, auto: bool = False):
        if self.up_next:
            self.play_song_by_id(self.up_next.pop(0))
            return
        if not self.playlist_queue:
            return
        ids = [s["id"] for s in self.playlist_queue]
        if not self.current_song:
            self.play_song_by_id(ids[0])
            return
        cur = self.current_song["id"]
        if self.shuffle_enabled and len(ids) > 1:
            # Aleatorio sin repetir lo que sonó hace poco
            recent = set(self.history[-min(len(ids) - 1, 15):]) | {cur}
            choices = [i for i in ids if i not in recent] or [i for i in ids if i != cur]
            self.play_song_by_id(random.choice(choices))
        elif cur in ids:
            self.play_song_by_id(ids[(ids.index(cur) + 1) % len(ids)])
        else:
            self.play_song_by_id(ids[0])

    def play_previous_song(self):
        if self.current_song and self.media_loaded and self.player.get_time() > 3000:
            self.player.set_time(0)
            return
        if self.history:
            self.play_song_by_id(self.history.pop(), record_history=False)
            return
        if not self.playlist_queue:
            return
        ids = [s["id"] for s in self.playlist_queue]
        if self.current_song and self.current_song["id"] in ids:
            self.play_song_by_id(ids[(ids.index(self.current_song["id"]) - 1) % len(ids)], record_history=False)
        else:
            self.play_song_by_id(ids[0])

    def toggle_loop(self):
        self.loop_enabled = not self.loop_enabled
        self.settings["loop"] = self.loop_enabled
        save_settings(self.settings)
        self._refresh_visual_state()
        self.toast.show_message("Repetir canción: activado" if self.loop_enabled else "Repetir canción: desactivado")
        if self.mpris:
            self.mpris.notify("LoopStatus")

    def toggle_shuffle(self):
        self.shuffle_enabled = not self.shuffle_enabled
        self.settings["shuffle"] = self.shuffle_enabled
        save_settings(self.settings)
        self._refresh_visual_state()
        if self.mpris:
            self.mpris.notify("Shuffle")

    def toggle_mute(self):
        self.is_muted = not self.is_muted
        self.player.audio_set_mute(self.is_muted)
        self._set_mute_icon()

    def change_volume(self, delta: int):
        self.vol_slider.setValue(max(0, min(100, self.vol_slider.value() + delta)))

    def on_volume_changed(self, val: int):
        self.player.audio_set_volume(val)
        self.lbl_vol_pct.setText(f"{val}%")
        if val > 0 and self.is_muted:
            self.is_muted = False
            self.player.audio_set_mute(False)
        self._set_mute_icon()
        if self.mpris:
            self.mpris.notify("Volume")

    def _seek_hover_text(self, value: int) -> str:
        if not self.current_song:
            return ""
        length = self.player.get_length() if self.media_loaded else 0
        length = length if length > 0 else int(self.current_song.get("duration") or 0) * 1000
        return self._fmt_ms(int(value / 1000 * length)) if length > 0 else ""

    def _on_seek_released(self):
        if self.current_song:
            if not self.media_loaded:
                length = int(self.current_song.get("duration") or 0) * 1000
                self.resume_ms = int(self.seek_slider.value() / 1000.0 * length)
                self.toggle_play_pause()
            else:
                self.player.set_position(self.seek_slider.value() / 1000.0)
                if self.mpris:
                    QTimer.singleShot(100, lambda: self.mpris.seeked(max(0, self.player.get_time())))
        self.is_seeking = False

    def _update_playback_tick(self):
        # Temporizador para dormir
        if self.sleep_deadline and datetime.now() >= self.sleep_deadline:
            self.sleep_deadline = None
            if self.player.is_playing():
                self.toggle_play_pause()
            self._refresh_visual_state()
            self.toast.show_message("Temporizador: música en pausa. ¡Buenas noches!", 4000)

        if not self.current_song or not self.media_loaded:
            return
        length_ms = self.player.get_length()
        cur_ms = self.player.get_time()
        if length_ms > 0:
            if self.resume_ms:
                self.player.set_time(min(self.resume_ms, length_ms - 1000))
                self.resume_ms = 0
            if not self.current_song.get("duration") and self.current_song.get("id"):
                secs = length_ms // 1000
                self.current_song["duration"] = secs
                with get_db() as conn:
                    conn.execute("UPDATE songs SET duration = ? WHERE id = ?", (secs, self.current_song["id"]))
                    conn.commit()
            self.lbl_time_cur.setText(self._fmt_ms(cur_ms))
            self.lbl_time_tot.setText(self._fmt_ms(length_ms))
            if not self.is_seeking:
                self.seek_slider.setValue(max(0, min(1000, int(cur_ms / length_ms * 1000))))

        if self.player.get_state() == vlc.State.Ended:
            if self.sleep_end_of_track:
                self.sleep_end_of_track = False
                self.player.stop()
                self._refresh_visual_state()
                self.toast.show_message("Temporizador: la canción terminó. ¡Buenas noches!", 4000)
            elif self.loop_enabled:
                if self.current_song.get("id"):
                    self.play_song_by_id(self.current_song["id"], record_history=False)
                else:
                    self.player.stop()
                    self.player.play()
            elif self.settings.get("auto_next", True) and (self.up_next or len(self.playlist_queue) > 1):
                self.play_next_song(auto=True)
            else:
                self.player.stop()
                self.seek_slider.setValue(0)

        status = self.mpris_status()
        if status != self._last_status:
            self._last_status = status
            self._set_play_icon(status == "Playing")
            if self.pages.currentIndex() == 4:
                self._refresh_song_page_buttons()
            if self.mpris:
                self.mpris.notify("PlaybackStatus")

    @staticmethod
    def _fmt_ms(ms: int) -> str:
        if ms < 0:
            return "0:00"
        s = ms // 1000
        h, rem = divmod(s, 3600)
        return f"{h}:{rem // 60:02d}:{rem % 60:02d}" if h else f"{s // 60}:{s % 60:02d}"

    # =================================================================
    # COLA, TEMPORIZADOR, FAVORITAS, EDICIÓN
    # =================================================================
    def _song_by_id(self, song_id: int) -> dict | None:
        with get_db() as conn:
            row = conn.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
        return dict(row) if row else None

    def add_to_queue(self, song_id: int, next_up: bool = False):
        if next_up:
            self.up_next.insert(0, song_id)
            self.toast.show_message("Sonará a continuación")
        else:
            self.up_next.append(song_id)
            self.toast.show_message(f"Añadida a la cola ({len(self.up_next)})")
        self._refresh_visual_state()

    def show_queue_menu(self):
        menu = QMenu(self)
        title = menu.addAction(f"A continuación · {plural(len(self.up_next), 'canción', 'canciones')}")
        title.setEnabled(False)
        menu.addSeparator()
        if not self.up_next:
            hint = menu.addAction("La cola está vacía — clic derecho en una canción → «Añadir a la cola»")
            hint.setEnabled(False)
        with get_db() as conn:
            for pos, sid in enumerate(self.up_next[:20]):
                r = conn.execute("SELECT title, artist FROM songs WHERE id = ?", (sid,)).fetchone()
                if not r:
                    continue
                act = menu.addAction(make_icon("play", C["muted"], 14), f"{pos + 1}.  {display_title(r['title'], r['artist'])} — {r['artist']}")
                act.triggered.connect(lambda _c=False, p=pos: self._play_from_queue(p))
        if self.up_next:
            menu.addSeparator()
            menu.addAction(make_icon("trash", C["muted"], 14), "Vaciar la cola").triggered.connect(self._clear_queue)
        self._popup_above(menu, self.btn_queue)

    def _play_from_queue(self, pos: int):
        if 0 <= pos < len(self.up_next):
            self.play_song_by_id(self.up_next.pop(pos))

    def _clear_queue(self):
        self.up_next.clear()
        self._refresh_visual_state()

    @staticmethod
    def _popup_above(menu: QMenu, anchor: QWidget):
        size = menu.sizeHint()
        menu.exec(anchor.mapToGlobal(QPoint(anchor.width() // 2 - size.width() // 2, -size.height() - 8)))

    def show_sleep_menu(self):
        menu = QMenu(self)
        if self.sleep_deadline:
            mins = max(1, int((self.sleep_deadline - datetime.now()).total_seconds() // 60) + 1)
            menu.addAction(f"Se pausará en {mins} min").setEnabled(False)
            menu.addSeparator()
        elif self.sleep_end_of_track:
            menu.addAction("Se detendrá al terminar esta canción").setEnabled(False)
            menu.addSeparator()
        for mins in (15, 30, 45, 60, 90):
            menu.addAction(make_icon("clock", C["muted"], 14), f"En {mins} minutos").triggered.connect(lambda _c=False, m=mins: self.set_sleep_timer(m))
        menu.addAction(make_icon("music", C["muted"], 14), "Al terminar esta canción").triggered.connect(lambda: self.set_sleep_timer(-1))
        if self.sleep_deadline or self.sleep_end_of_track:
            menu.addSeparator()
            menu.addAction(make_icon("close", C["muted"], 14), "Desactivar temporizador").triggered.connect(lambda: self.set_sleep_timer(0))
        self._popup_above(menu, self.btn_sleep)

    def set_sleep_timer(self, minutes: int):
        self.sleep_deadline = None
        self.sleep_end_of_track = False
        if minutes > 0:
            self.sleep_deadline = datetime.now() + timedelta(minutes=minutes)
            self.toast.show_message(f"La música se pausará en {minutes} minutos")
        elif minutes < 0:
            self.sleep_end_of_track = True
            self.toast.show_message("La música se detendrá al terminar esta canción")
        else:
            self.toast.show_message("Temporizador desactivado")
        self._refresh_visual_state()

    def toggle_current_favorite(self):
        cur = self.current_song
        if not cur:
            return
        if cur.get("id"):
            self.toggle_favorite(cur["id"])
            return
        # Canción en línea: se guarda en la biblioteca y queda como favorita
        cur["favorite"] = 1
        self._save_current_stream(favorite=True)
        self.toast.show_message("♥ Se guardará en tu biblioteca y en Favoritas")
        self._refresh_fav_buttons()

    def toggle_favorite(self, song_id: int):
        with get_db() as conn:
            conn.execute("UPDATE songs SET favorite = 1 - COALESCE(favorite, 0) WHERE id = ?", (song_id,))
            conn.commit()
            fav = conn.execute("SELECT favorite FROM songs WHERE id = ?", (song_id,)).fetchone()["favorite"]
        if self.current_song and self.current_song["id"] == song_id:
            self.current_song["favorite"] = fav
        self.toast.show_message("Añadida a Favoritas ♥" if fav else "Quitada de Favoritas")
        self.refresh_all_views()

    def on_manual_genre_change(self, idx: int):
        if idx <= 0 or not self.current_song:
            return
        if not self.current_song.get("id"):
            self.change_genre_combo.setCurrentIndex(0)
            self.toast.show_message("Podrás cambiar el género cuando la canción esté guardada")
            return
        new_genre = self.change_genre_combo.currentText()
        self.change_genre_combo.setCurrentIndex(0)
        self.update_song_genre(self.current_song["id"], new_genre)

    def update_song_genre(self, song_id: int, new_genre: str):
        base_dl = Path(self.settings["download_dir"])
        with get_db() as conn:
            row = conn.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
            if not row:
                return
            cur_path = Path(row["file_path"])
            new_path = cur_path
            if cur_path.exists() and self.settings.get("organize_by_genre", True):
                target_dir = base_dl / genre_folder(new_genre)
                target_dir.mkdir(parents=True, exist_ok=True)
                candidate = target_dir / cur_path.name
                if candidate.resolve() != cur_path.resolve() and not candidate.exists():
                    try:
                        shutil.move(str(cur_path), str(candidate))
                        new_path = candidate
                    except Exception:
                        new_path = cur_path
            conn.execute("UPDATE songs SET genre = ?, file_path = ? WHERE id = ?", (new_genre, str(new_path), song_id))
            conn.commit()
            updated = dict(conn.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone())
        if self.current_song and self.current_song["id"] == song_id:
            self.current_song = updated
            self._apply_now_playing_visuals(updated)
        self.toast.show_message(f"Género cambiado a {new_genre}")
        self.refresh_all_views()

    def edit_song(self, song_id: int):
        song = self._song_by_id(song_id)
        if not song:
            return
        dlg = EditSongDialog(self, song)
        dlg.exec()
        if dlg.result_key != "save":
            return
        vals = dlg.values()
        if not vals["title"]:
            return
        with get_db() as conn:
            conn.execute(
                "UPDATE songs SET title = ?, artist = ? WHERE id = ?",
                (vals["title"], vals["artist"] or "Artista desconocido", song_id),
            )
            conn.commit()
        if vals["genre"] != song.get("genre"):
            self.update_song_genre(song_id, vals["genre"])
        if self.current_song and self.current_song["id"] == song_id:
            self.current_song = self._song_by_id(song_id)
            self._apply_now_playing_visuals(self.current_song)
        self.toast.show_message("Información actualizada")
        self.refresh_all_views()

    def delete_song(self, song_id: int):
        song = self._song_by_id(song_id)
        if not song:
            return
        choice = ask(
            self,
            "¿Eliminar canción?",
            f"«{display_title(song['title'], song.get('artist', ''))}» — {song.get('artist')}\n\n"
            "Puedes quitarla solo de la biblioteca (el archivo se queda en tu carpeta) o borrar también el archivo de audio.",
            [
                ("cancel", "Cancelar", "SecondaryBtn"),
                ("remove", "Quitar de la biblioteca", "SecondaryBtn"),
                ("delete", "Borrar también el archivo", "DangerBtn"),
            ],
            icon="trash",
            color=C["danger"],
        )
        if choice not in ("remove", "delete"):
            return
        if self.current_song and self.current_song["id"] == song_id:
            self._reset_now_playing()
        with get_db() as conn:
            conn.execute("DELETE FROM songs WHERE id = ?", (song_id,))
            conn.commit()
        if choice == "delete":
            try:
                Path(song["file_path"]).unlink(missing_ok=True)
            except OSError as e:
                show_message(self, "No se pudo borrar el archivo", str(e), "warning")
        self.up_next = [i for i in self.up_next if i != song_id]
        self.history = [i for i in self.history if i != song_id]
        self.toast.show_message("Canción eliminada" if choice == "delete" else "Quitada de la biblioteca")
        self.refresh_all_views()

    # ----------------------------- Menú contextual -----------------------------
    def _library_context_menu(self, pos):
        item = self.library_table.itemAt(pos)
        if item:
            id_item = self.library_table.item(item.row(), 0)
            if id_item:
                self.show_song_menu(id_item.data(Qt.ItemDataRole.UserRole), self.library_table.viewport().mapToGlobal(pos))

    def _sidebar_context_menu(self, pos):
        item = self.sidebar_top_list.itemAt(pos)
        if item:
            self.show_song_menu(item.data(Qt.ItemDataRole.UserRole), self.sidebar_top_list.viewport().mapToGlobal(pos))

    def show_song_menu(self, song_id: int, global_pos):
        song = self._song_by_id(song_id)
        if not song:
            return
        m = QMenu(self)

        def ic(name):
            return make_icon(name, C["text"], 16)

        m.addAction(ic("play"), "Reproducir ahora").triggered.connect(lambda: self.play_song_by_id(song_id))
        m.addAction(ic("music"), "Ver canción").triggered.connect(lambda: self.open_song_page(song_id))
        m.addAction(ic("queue"), "Reproducir a continuación").triggered.connect(lambda: self.add_to_queue(song_id, next_up=True))
        m.addAction(ic("plus"), "Añadir a la cola").triggered.connect(lambda: self.add_to_queue(song_id))
        fav = bool(song.get("favorite"))
        m.addAction(
            make_icon("heart_fill" if fav else "heart", C["accent"] if fav else C["text"], 16),
            "Quitar de favoritas" if fav else "Me gusta",
        ).triggered.connect(lambda: self.toggle_favorite(song_id))
        m.addSeparator()
        m.addAction(ic("edit"), "Editar información…").triggered.connect(lambda: self.edit_song(song_id))
        genre_menu = m.addMenu(ic("library"), "Cambiar género y mover")
        for g in GENRES_LIST:
            act = genre_menu.addAction(g)
            act.setCheckable(True)
            act.setChecked(g == song.get("genre"))
            act.triggered.connect(lambda _c=False, genre=g: self.update_song_genre(song_id, genre))
        m.addAction(ic("folder"), "Mostrar en la carpeta").triggered.connect(lambda: self.open_path(str(Path(song["file_path"]).parent)))
        m.addSeparator()
        m.addAction(make_icon("trash", C["danger"], 16), "Eliminar…").triggered.connect(lambda: self.delete_song(song_id))
        m.exec(global_pos)

    # =================================================================
    # ATAJOS, ECUALIZADOR, NOTIFICACIONES, MPRIS, SESIÓN
    # =================================================================
    def _setup_shortcuts(self):
        def sc(keys, slot):
            s = QShortcut(QKeySequence(keys), self)
            s.setContext(Qt.ShortcutContext.WindowShortcut)
            s.activated.connect(slot)

        sc("Space", self.toggle_play_pause)
        sc("Ctrl+F", self.focus_search)
        sc("Ctrl+L", self.focus_search)
        sc("Ctrl+Right", lambda: self.play_next_song())
        sc("Ctrl+Left", self.play_previous_song)
        sc("Shift+Right", lambda: self.seek_relative_ms(10000))
        sc("Shift+Left", lambda: self.seek_relative_ms(-10000))
        sc("Ctrl+Up", lambda: self.change_volume(5))
        sc("Ctrl+Down", lambda: self.change_volume(-5))
        sc("Ctrl+M", self.toggle_mute)
        sc("Ctrl+D", self.toggle_current_favorite)
        sc("Ctrl+S", self.toggle_shuffle)
        sc("Ctrl+R", self.toggle_loop)
        sc("Ctrl+1", lambda: self.switch_page(0))
        sc("Ctrl+2", self.open_explore)
        sc("Ctrl+3", lambda: self.open_genre_in_library("Todos"))
        sc("Ctrl+4", lambda: self.open_genre_in_library(FAV_FILTER))
        sc("Ctrl+5", lambda: self.switch_page(2))
        sc("Escape", lambda: self.close_results() if self.results_panel.isVisible() else None)
        if self.mpris is None:
            # Sin MPRIS, al menos las teclas multimedia con la ventana enfocada
            sc(QKeySequence(Qt.Key.Key_MediaTogglePlayPause), self.toggle_play_pause)
            sc(QKeySequence(Qt.Key.Key_MediaPlay), self.toggle_play_pause)
            sc(QKeySequence(Qt.Key.Key_MediaNext), lambda: self.play_next_song())
            sc(QKeySequence(Qt.Key.Key_MediaPrevious), self.play_previous_song)

    def _on_eq_changed(self):
        idx = int(self.combo_eq.currentData())
        self.settings["equalizer"] = idx
        save_settings(self.settings)
        self.apply_equalizer(idx)
        self.toast.show_message(f"Ecualizador: {self.combo_eq.currentText()}")

    def apply_equalizer(self, idx: int):
        try:
            if idx < 0:
                self.player.set_equalizer(None)
                self._eq = None
            else:
                self._eq = vlc.libvlc_audio_equalizer_new_from_preset(idx)
                self.player.set_equalizer(self._eq)
        except Exception:
            pass

    def desktop_notify(self, title: str, body: str, icon: str = ""):
        if not self.settings.get("notifications", True) or self.isActiveWindow() or not shutil.which("notify-send"):
            return
        icon_path = icon if icon and os.path.exists(icon) else str(ICON_PATH)
        try:
            subprocess.Popen(
                ["notify-send", "-a", APP_NAME, "-i", icon_path, "-h", f"string:desktop-entry:{APP_ID}", "-t", "4000", title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass

    def mpris_status(self) -> str:
        if not self.current_song:
            return "Stopped"
        return "Playing" if self.player.is_playing() else "Paused"

    def mpris_metadata(self) -> dict:
        song = self.current_song
        length = self.player.get_length() if self.media_loaded else 0
        return build_metadata(song, length, (song or {}).get("thumbnail_path", "") or str(ICON_PATH))

    def mpris_raise(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _restore_session(self):
        sid = self.settings.get("last_song_id")
        song = self._song_by_id(sid) if sid else None
        if not song or not os.path.exists(song["file_path"]):
            return
        self.current_song = song
        self.media_loaded = False
        self.resume_ms = int(self.settings.get("last_position_ms") or 0)
        self._apply_now_playing_visuals(song, None, resumed=True)
        self.hero_source_badge.setText("Donde lo dejaste")
        self.btn_play_pause.setEnabled(True)
        self.seek_slider.setEnabled(True)
        length = int(song.get("duration") or 0) * 1000
        if length:
            self.seek_slider.setValue(int(self.resume_ms / length * 1000))
            self.lbl_time_tot.setText(self._fmt_ms(length))
        self.lbl_time_cur.setText(self._fmt_ms(self.resume_ms))
        self.refresh_all_views()

    def closeEvent(self, e):
        if self.current_song and self.current_song.get("id"):
            self.settings["last_song_id"] = self.current_song["id"]
            self.settings["last_position_ms"] = max(0, self.player.get_time()) if self.media_loaded else self.resume_ms
        self.settings["default_volume"] = self.vol_slider.value()
        save_settings(self.settings)
        self.player.stop()
        super().closeEvent(e)

    # =================================================================
    # AJUSTES
    # =================================================================
    def choose_download_directory(self):
        chosen = QFileDialog.getExistingDirectory(self, "Elegir carpeta para tu música", self.settings.get("download_dir", str(BASE_DIR / "musicplay")))
        if chosen:
            self.settings["download_dir"] = chosen
            self.settings_dir_input.setText(chosen)
            save_settings(self.settings)
            organize_and_classify_all_songs(self.settings)
            self.refresh_all_views()
            show_message(self, "Carpeta actualizada", f"Tus descargas se guardarán en:\n{chosen}")

    def save_current_settings(self):
        self.settings["organize_by_genre"] = self.chk_organize_genre.isChecked()
        self.settings["clean_filenames"] = self.chk_clean_names.isChecked()
        self.settings["audio_format"] = self.combo_audio_fmt.currentData()
        self.settings["auto_next"] = self.chk_auto_next.isChecked()
        self.settings["notifications"] = self.chk_notifications.isChecked()
        self.settings["default_volume"] = self.vol_slider.value()
        save_settings(self.settings)
        self.refresh_all_views()

    def trigger_manual_reorganization(self):
        self.save_current_settings()
        moved = organize_and_classify_all_songs(self.settings)
        self.refresh_all_views()
        show_message(self, "Biblioteca ordenada", f"Se clasificaron tus canciones por género.\nArchivos movidos a su carpeta: {moved}")

    def import_external_music_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Elegir una carpeta con música para importar")
        if not folder:
            return
        exts = {".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus", ".webm"}
        imported = 0
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_db() as conn:
            for root, _dirs, files in os.walk(folder):
                for file in files:
                    p = Path(root) / file
                    if p.suffix.lower() not in exts:
                        continue
                    if conn.execute("SELECT id FROM songs WHERE file_path = ?", (str(p),)).fetchone():
                        continue
                    title = p.stem.replace("_", " ")
                    artist = extract_artist_from_title(title, "Artista desconocido")
                    conn.execute(
                        "INSERT INTO songs (title, artist, genre, search_term, file_path, play_count, last_played, added_at) "
                        "VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                        (title, artist, detect_genre(title, artist), title, str(p), now, now),
                    )
                    imported += 1
            conn.commit()
        organize_and_classify_all_songs(self.settings)
        self.refresh_all_views()
        show_message(self, "Importación completada", f"Se importaron y clasificaron {plural(imported, 'canción nueva', 'canciones nuevas')}.")

    def update_ytdlp(self):
        """Descarga la última versión del motor de descargas (funciona también en la app instalada)."""
        self.ytdlp_btn.setEnabled(False)
        self.ytdlp_btn.setText("Actualizando…")
        current = ytdlp_version()

        class _Updater(QThread):
            done = pyqtSignal(str, str)

            def run(self):
                try:
                    self.done.emit(download_latest_ytdlp(), "")
                except Exception as e:  # sin internet, GitHub caído, etc.
                    self.done.emit("", str(e))

        worker = _Updater()
        worker.done.connect(lambda ver, err, cur=current: self._on_ytdlp_updated(ver, err, cur))
        self._start_worker(worker)

    def _on_ytdlp_updated(self, version: str, error: str, current: str):
        self.ytdlp_btn.setEnabled(True)
        self.ytdlp_btn.setText("Actualizar")
        if error:
            show_message(self, "No se pudo actualizar", f"{error[:400]}\n\nRevisa tu conexión a internet.", "error")
        elif version == current:
            show_message(self, "Ya estás al día", f"yt-dlp {current} es la versión más reciente.")
        else:
            show_message(self, "Motor actualizado", f"Se descargó yt-dlp {version}.\nCierra y vuelve a abrir Puquichu para usarlo.")

    def check_missing_files(self):
        with get_db() as conn:
            missing = [dict(r) for r in conn.execute("SELECT id, title, file_path FROM songs") if not os.path.exists(r["file_path"])]
        if not missing:
            show_message(self, "Todo en orden", "Todas las canciones de tu biblioteca tienen su archivo en el disco.")
            return
        names = "\n".join(f"• {display_title(m['title'])}" for m in missing[:8])
        more = f"\n…y {len(missing) - 8} más" if len(missing) > 8 else ""
        choice = ask(
            self,
            plural(len(missing), "canción perdida", "canciones perdidas"),
            f"Estos archivos ya no están en el disco:\n\n{names}{more}\n\n¿Quitarlas de la biblioteca?",
            [("cancel", "Ahora no", "SecondaryBtn"), ("remove", "Quitar de la biblioteca", "Primary")],
        )
        if choice == "remove":
            with get_db() as conn:
                conn.executemany("DELETE FROM songs WHERE id = ?", [(m["id"],) for m in missing])
                conn.commit()
            self.refresh_all_views()
            self.toast.show_message(f"Se quitaron {plural(len(missing), 'canción', 'canciones')}")

    def open_current_song_folder(self):
        if self.current_song and os.path.exists(self.current_song["file_path"]):
            self.open_path(str(Path(self.current_song["file_path"]).parent))
        else:
            self.open_path(self.settings["download_dir"])

    @staticmethod
    def open_path(path_str: str):
        if not os.path.exists(path_str):
            return
        if sys.platform.startswith("win"):
            os.startfile(path_str)  # type: ignore[attr-defined]
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, path_str], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    if os.environ.get("PUQUICHU_SMOKE_TEST"):
        import faulthandler

        faulthandler.dump_traceback_later(20, exit=True)  # si se cuelga, muestra dónde
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName(APP_ID)
    app.setFont(QFont(UI_FONT, 10))
    try:
        probe = vlc.Instance("--no-xlib")
        if probe is None:
            raise RuntimeError("libvlc sin módulos")
        probe.release()
    except Exception as e:
        print(f"PUQUICHU_VLC_ERROR {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        if os.environ.get("PUQUICHU_SMOKE_TEST"):
            sys.exit(3)
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.critical(
            None,
            "Falta VLC",
            "Puquichu usa VLC para reproducir la música, pero no está instalado.\n\n"
            "En Ubuntu / Linux Mint / Debian ábrelo desde el Centro de software o ejecuta:\n"
            "    sudo apt install vlc",
        )
        sys.exit(1)
    window = PuquichuApp()
    window.show()
    if os.environ.get("PUQUICHU_SMOKE_TEST"):
        # Usado por la integración continua: confirma que la app arranca y se cierra sola
        def _smoke():
            # Audio sin internet: genera un tono Opus con ffmpeg y lo reproduce con salida muda
            try:
                import tempfile

                tone = Path(tempfile.gettempdir()) / "puquichu_tono_prueba.opus"
                subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-c:a", "libopus", str(tone)],
                    check=True, timeout=30,
                )
                inst = vlc.Instance("--no-xlib", "--aout=dummy")
                local_player = inst.media_player_new()
                local_player.set_media(inst.media_new(str(tone)))
                local_player.play()
                deadline = time.time() + 10
                while time.time() < deadline and local_player.get_time() < 1000:
                    time.sleep(0.1)
                played = local_player.get_time()
                local_player.stop()
                print(f"PUQUICHU_AUDIO_LOCAL_{'OK' if played >= 1000 else 'FALLO'} {played} ms", flush=True)
            except Exception as e:
                print(f"PUQUICHU_AUDIO_LOCAL_FALLO {type(e).__name__}: {e}", flush=True)
            if os.environ["PUQUICHU_SMOKE_TEST"] == "red":
                try:
                    import yt_dlp

                    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": "in_playlist"}) as ydl:
                        hit = ydl.extract_info("ytsearch1:los kjarkas llorando se fue", download=False)["entries"][0]
                    print(f"PUQUICHU_RED_OK {hit.get('title')}", flush=True)
                    # Reproduce unos segundos (salida de audio muda) para comprobar códecs y streaming
                    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "format": "bestaudio[acodec=opus]/bestaudio"}) as ydl:
                        stream = ydl.extract_info(hit["url"], download=False)["url"]
                    inst = vlc.Instance("--no-xlib", "--aout=dummy")
                    test_player = inst.media_player_new()
                    test_player.set_media(inst.media_new(stream))
                    test_player.play()
                    deadline = time.time() + 15
                    while time.time() < deadline and test_player.get_time() < 1500:
                        time.sleep(0.2)
                    played = test_player.get_time()
                    test_player.stop()
                    print(f"PUQUICHU_AUDIO_{'OK' if played >= 1500 else 'FALLO'} {played} ms", flush=True)
                except Exception as e:  # YouTube puede bloquear servidores de centros de datos
                    print(f"PUQUICHU_RED_FALLO {type(e).__name__}: {str(e)[:200]}", flush=True)
            print(f"PUQUICHU_OK {APP_VERSION} yt-dlp {ytdlp_version()} mpris={'si' if window.mpris else 'no'}", flush=True)
            window.close()
            app.quit()

        QTimer.singleShot(2500, _smoke)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
