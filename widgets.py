"""Puquichu — widgets personalizados dibujados a mano."""
from PyQt6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPalette, QPen
from PyQt6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QToolTip,
    QStyledItemDelegate,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from core import APP_NAME, GENRE_COLORS, GENRES_LIST
from theme import (
    C,
    UI_FONT,
    brand_logo,
    cached_artwork,
    create_wide_thumb,
    display_title,
    fmt_seconds,
    fmt_views,
    humanize_dt,
    make_icon,
    make_icon_pixmap,
)

ROLE_SONG = Qt.ItemDataRole.UserRole + 1
ROLE_PLAYING = Qt.ItemDataRole.UserRole + 2

ALIGN_LEFT = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
ALIGN_CENTER = int(Qt.AlignmentFlag.AlignCenter)


def ui_font(px: int, weight=QFont.Weight.Normal) -> QFont:
    f = QFont(UI_FONT)
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


def elide(text: str, font: QFont, width: int) -> str:
    return QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, max(0, int(width)))


# =====================================================================
# VENTANA SIN BORDES: raíz con bordes redimensionables + barra de título
# =====================================================================
class RootWidget(QWidget):
    """Widget raíz. Su margen exterior funciona como borde para redimensionar la ventana."""

    EDGE = 6
    _CURSORS = {
        Qt.Edge.LeftEdge: Qt.CursorShape.SizeHorCursor,
        Qt.Edge.RightEdge: Qt.CursorShape.SizeHorCursor,
        Qt.Edge.TopEdge: Qt.CursorShape.SizeVerCursor,
        Qt.Edge.BottomEdge: Qt.CursorShape.SizeVerCursor,
        Qt.Edge.LeftEdge | Qt.Edge.TopEdge: Qt.CursorShape.SizeFDiagCursor,
        Qt.Edge.RightEdge | Qt.Edge.BottomEdge: Qt.CursorShape.SizeFDiagCursor,
        Qt.Edge.RightEdge | Qt.Edge.TopEdge: Qt.CursorShape.SizeBDiagCursor,
        Qt.Edge.LeftEdge | Qt.Edge.BottomEdge: Qt.CursorShape.SizeBDiagCursor,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMouseTracking(True)

    def _edges(self, pos: QPoint):
        win = self.window()
        edges = Qt.Edge(0)
        if win.isMaximized() or win.isFullScreen():
            return edges
        g = self.EDGE + 4  # zona un poco más generosa en las esquinas
        if pos.x() <= g:
            edges |= Qt.Edge.LeftEdge
        elif pos.x() >= self.width() - g:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= g:
            edges |= Qt.Edge.TopEdge
        elif pos.y() >= self.height() - g:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mouseMoveEvent(self, e):
        edges = self._edges(e.position().toPoint())
        cursor = self._CURSORS.get(edges)
        if cursor:
            self.setCursor(cursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            edges = self._edges(e.position().toPoint())
            handle = self.window().windowHandle()
            if edges != Qt.Edge(0) and handle:
                handle.startSystemResize(edges)
                return
        super().mousePressEvent(e)


class TitleBar(QWidget):
    """Barra de título propia: arrastrar, doble clic para maximizar y botones de ventana."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.win = window
        self.setObjectName("TitleBar")
        self.setFixedHeight(40)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 2, 0)
        lay.setSpacing(4)

        self.logo = QLabel()
        self.logo.setPixmap(brand_logo(18))
        lay.addWidget(self.logo)
        lay.addSpacing(6)
        self.title = QLabel(APP_NAME)
        self.title.setObjectName("TitleText")
        lay.addWidget(self.title)
        lay.addStretch()

        self.btn_min = self._win_btn("win_min", "Minimizar", self.win.showMinimized)
        self.btn_max = self._win_btn("win_max", "Maximizar", self.toggle_max)
        self.btn_close = self._win_btn("win_close", "Cerrar", self.win.close)
        self.btn_close.setObjectName("WinClose")
        for b in (self.btn_min, self.btn_max, self.btn_close):
            lay.addWidget(b)

    def _win_btn(self, icon: str, tip: str, slot) -> QPushButton:
        b = QPushButton()
        b.setProperty("class", "WinBtn")
        b.setIcon(make_icon(icon, C["muted"], 18))
        b.setIconSize(QSize(18, 18))
        b.setToolTip(tip)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.clicked.connect(slot)
        return b

    def set_subtitle(self, text: str):
        self.title.setText(f"{APP_NAME}  ·  {text}" if text else APP_NAME)

    def toggle_max(self):
        if self.win.isMaximized():
            self.win.showNormal()
        else:
            self.win.showMaximized()

    def refresh_icons(self):
        maxed = self.win.isMaximized()
        self.btn_max.setIcon(make_icon("win_restore" if maxed else "win_max", C["muted"], 18))
        self.btn_max.setToolTip("Restaurar" if maxed else "Maximizar")
        self.btn_min.setIcon(make_icon("win_min", C["muted"], 18))
        self.btn_close.setIcon(make_icon("win_close", C["muted"], 18))
        self.logo.setPixmap(brand_logo(18))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.win.windowHandle():
            self.win.windowHandle().startSystemMove()
            return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.toggle_max()


# =====================================================================
# ELEMENTOS BÁSICOS
# =====================================================================
class ElidedLabel(QLabel):
    """Etiqueta de una línea que recorta con '…' y muestra el texto completo como tooltip."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(20)
        self.setToolTip(text)

    def setText(self, text: str):
        super().setText(text)
        self.setToolTip(text)

    def paintEvent(self, _event):
        p = QPainter(self)
        rect = self.contentsRect()
        txt = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, rect.width())
        self.style().drawItemText(p, rect, ALIGN_LEFT, self.palette(), self.isEnabled(), txt, QPalette.ColorRole.WindowText)


class ToggleSwitch(QCheckBox):
    """Interruptor tipo GNOME/KDE dibujado a mano."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(46, 26)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        track = QRectF(1, 1, self.width() - 2, self.height() - 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C["accent"] if on else "#3a3f34"))
        p.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        d = track.height() - 6
        x = track.right() - d - 3 if on else track.left() + 3
        p.setBrush(QColor(C["on_accent"] if on else "#f2f1e9"))
        p.drawEllipse(QRectF(x, track.top() + 3, d, d))


class ClickSlider(QSlider):
    """Barra que salta justo donde haces clic (Qt por defecto avanza a saltos) y muestra el tiempo al pasar el ratón."""

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.hover_text = None  # función valor -> texto del tooltip
        self.setMouseTracking(True)

    def _value_at(self, x: float) -> int:
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        handle = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)
        span = max(1, self.width() - handle.width())
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), int(x - handle.width() / 2), span)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.setValue(self._value_at(e.position().x()))
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.hover_text and self.isEnabled():
            text = self.hover_text(self._value_at(e.position().x()))
            if text:
                QToolTip.showText(e.globalPosition().toPoint() + QPoint(0, -36), text, self)
        super().mouseMoveEvent(e)


class Toast(QLabel):
    """Aviso breve que aparece abajo y desaparece solo."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, ms: int = 2400):
        self.setStyleSheet(
            f"background-color: {C['text']}; color: {C['bg']}; font-weight: 700; font-size: 13px;"
            "padding: 10px 18px; border-radius: 18px;"
        )
        self.setText(text)
        self.adjustSize()
        parent = self.parentWidget()
        self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 24)
        self.raise_()
        self.show()
        self._timer.start(ms)


# =====================================================================
# DIÁLOGOS PROPIOS (sin la barra antigua del sistema)
# =====================================================================
class PuquiDialog(QDialog):
    def __init__(self, parent, title: str, icon_name: str = "", icon_color: str = ""):
        super().__init__(parent)
        self.setObjectName("PuquiDialog")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(440)
        self.result_key = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 24, 26, 22)
        outer.setSpacing(14)
        head = QHBoxLayout()
        head.setSpacing(12)
        if icon_name:
            ic = QLabel()
            ic.setObjectName("IconTile")
            ic.setFixedSize(38, 38)
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ic.setPixmap(make_icon_pixmap(icon_name, icon_color or C["accent_hi"], 20))
            head.addWidget(ic)
        t = QLabel(title)
        t.setObjectName("H2")
        head.addWidget(t, stretch=1)
        outer.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body)
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(8)
        self.buttons.addStretch()
        outer.addSpacing(6)
        outer.addLayout(self.buttons)

    def add_text(self, text: str):
        lbl = QLabel(text)
        lbl.setObjectName("Muted")
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.addWidget(lbl)
        return lbl

    def add_button(self, key: str, label: str, style: str = "SecondaryBtn", default: bool = False):
        b = QPushButton(label)
        if style == "Primary":
            b.setObjectName("DialogOk")
        else:
            b.setProperty("class", style)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda: self._finish(key))
        if default:
            b.setDefault(True)
        self.buttons.addWidget(b)
        return b

    def _finish(self, key):
        self.result_key = key
        self.accept()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setPen(QPen(QColor(C["border"]), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))


def show_message(parent, title: str, text: str, kind: str = "info"):
    icon, color = {"info": ("check", C["accent_hi"]), "warning": ("warning", "#f0b44c"), "error": ("warning", C["danger"])}.get(
        kind, ("check", C["accent_hi"])
    )
    dlg = PuquiDialog(parent, title, icon, color)
    dlg.add_text(text)
    dlg.add_button("ok", "Entendido", "Primary", default=True)
    dlg.exec()


def ask(parent, title: str, text: str, buttons: list[tuple[str, str, str]], icon: str = "warning", color: str = "") -> str | None:
    dlg = PuquiDialog(parent, title, icon, color or "#f0b44c")
    dlg.add_text(text)
    for key, label, style in buttons:
        dlg.add_button(key, label, style, default=(style == "Primary"))
    dlg.exec()
    return dlg.result_key


class EditSongDialog(PuquiDialog):
    def __init__(self, parent, song: dict):
        super().__init__(parent, "Editar información", "edit")
        self.title_input = QLineEdit(song.get("title") or "")
        self.artist_input = QLineEdit(song.get("artist") or "")
        self.genre_combo = QComboBox()
        self.genre_combo.addItems(GENRES_LIST)
        self.genre_combo.setCurrentText(song.get("genre") or "Otros")
        for label, w in (("Título", self.title_input), ("Artista", self.artist_input), ("Género", self.genre_combo)):
            lbl = QLabel(label)
            lbl.setObjectName("Kicker")
            self.body.addWidget(lbl)
            if isinstance(w, QLineEdit):
                w.setProperty("class", "SettingsInput")
            self.body.addWidget(w)
        self.add_button("cancel", "Cancelar")
        self.add_button("save", "Guardar", "Primary", default=True)

    def values(self) -> dict:
        return {
            "title": self.title_input.text().strip(),
            "artist": self.artist_input.text().strip(),
            "genre": self.genre_combo.currentText(),
        }


# =====================================================================
# TARJETAS
# =====================================================================
class HeroCard(QFrame):
    """Tarjeta 'Sonando ahora' con degradado tomado del color dominante de la carátula."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor(C["accent_mid"])

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, 20, 20)
        base = QColor(C["panel_alt"])
        grad = diagonal_gradient(rect)
        grad.setColorAt(0.0, self._color)
        mid = QColor(
            (self._color.red() + base.red() * 2) // 3,
            (self._color.green() + base.green() * 2) // 3,
            (self._color.blue() + base.blue() * 2) // 3,
        )
        grad.setColorAt(0.55, mid)
        grad.setColorAt(1.0, base)
        p.fillPath(path, grad)
        shade = diagonal_gradient(QRectF(0, 0, 0, rect.height()))
        shade.setColorAt(0.0, QColor(0, 0, 0, 0))
        shade.setColorAt(1.0, QColor(0, 0, 0, 110))
        p.fillPath(path, shade)
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.drawPath(path)


def diagonal_gradient(rect: QRectF) -> QLinearGradient:
    return QLinearGradient(rect.left(), rect.top(), rect.left() + rect.width(), rect.top() + rect.height())


class GenreTile(QAbstractButton):
    """Tarjeta de colección por género."""

    def __init__(self, genre: str, count: int, parent=None):
        super().__init__(parent)
        self.genre = genre
        self.count = count
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(98)
        self.setMinimumWidth(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        c1, c2 = GENRE_COLORS.get(self.genre, (C["accent"], C["accent_press"]))
        hover = self.underMouse()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), 16, 16)
        grad = diagonal_gradient(QRectF(0, 0, w, h))
        grad.setColorAt(0.0, QColor(c1).lighter(112) if hover else QColor(c1))
        grad.setColorAt(1.0, QColor(c2).darker(135))
        p.fillPath(path, grad)
        p.setClipPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 34))
        p.drawEllipse(QRectF(w - 78, h - 52, 104, 104))
        p.setBrush(QColor(0, 0, 0, 38))
        p.drawEllipse(QRectF(w - 40, -34, 70, 70))
        p.drawPixmap(w - 50, h - 48, make_icon_pixmap("music", QColor(255, 255, 255, 215), 30))
        if self.count == 0 and not hover:
            p.fillPath(path, QColor(12, 14, 10, 130))  # géneros vacíos más apagados
        p.setClipping(False)
        p.setPen(QColor("#ffffff"))
        p.setFont(ui_font(15, QFont.Weight.Bold))
        p.drawText(QRectF(16, 14, w - 60, 24), ALIGN_LEFT, self.genre)
        p.setFont(ui_font(12, QFont.Weight.Medium))
        p.setPen(QColor(255, 255, 255, 200))
        p.drawText(QRectF(16, h - 34, w - 60, 20), ALIGN_LEFT, "1 canción" if self.count == 1 else f"{self.count} canciones")


class SongCard(QWidget):
    """Tarjeta tipo álbum para 'Escuchado recientemente'."""

    clicked = pyqtSignal(int)
    ART = 140

    def __init__(self, song: dict, parent=None):
        super().__init__(parent)
        self.song = song
        self.setFixedSize(self.ART + 24, self.ART + 82)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setToolTip(song["title"])

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(int(self.song["id"]))
        super().mouseReleaseEvent(e)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        hover = self.underMouse()
        if hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C["hover"]))
            p.drawRoundedRect(QRectF(self.rect()), 14, 14)
        genre = self.song.get("genre") or "Otros"
        p.drawPixmap(12, 12, cached_artwork(genre, self.song.get("thumbnail_path", ""), self.ART, 10))
        if self.song.get("favorite"):
            p.drawPixmap(20, 20, make_icon_pixmap("heart_fill", C["accent"], 18))
        if hover:
            cx, cy, d = 12 + self.ART - 52, 12 + self.ART - 52, 44
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 90))
            p.drawEllipse(QRectF(cx - 1, cy + 2, d + 2, d + 2))
            p.setBrush(QColor(C["accent"]))
            p.drawEllipse(QRectF(cx, cy, d, d))
            p.drawPixmap(cx + 12, cy + 12, make_icon_pixmap("play", C["on_accent"], 20))
        tw = self.width() - 24
        f = ui_font(13, QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(QColor(C["text"]))
        p.drawText(12, self.ART + 34, elide(display_title(self.song["title"], self.song.get("artist", "")), f, tw))
        f = ui_font(12)
        p.setFont(f)
        p.setPen(QColor(C["muted"]))
        p.drawText(12, self.ART + 54, elide(self.song.get("artist") or "Artista desconocido", f, tw))


class ChartCard(QWidget):
    """Tarjeta de ranking (Top Perú / Top mundial) con número de puesto."""

    clicked = pyqtSignal(object)
    ART = 140

    def __init__(self, track: dict, rank: int, parent=None):
        super().__init__(parent)
        self.track = track
        self.rank = rank
        self.in_library = False
        self.loading = False
        self.setFixedSize(self.ART + 24, self.ART + 82)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setToolTip(f"{track['title']} — {track['artist']}")

    def set_loading(self, value: bool):
        self.loading = value
        self.update()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self)
        super().mouseReleaseEvent(e)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        hover = self.underMouse()
        if hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C["hover"]))
            p.drawRoundedRect(QRectF(self.rect()), 14, 14)
        p.drawPixmap(12, 12, cached_artwork("Otros", self.track.get("cover", ""), self.ART, 10))

        # Puesto en el ranking
        f = ui_font(13, QFont.Weight.Black)
        p.setFont(f)
        badge = QRectF(18, 18, max(28, QFontMetrics(f).horizontalAdvance(str(self.rank)) + 14), 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(badge, 12, 12)
        p.setPen(QColor(C["gold"] if self.rank <= 3 else "#ffffff"))
        p.drawText(badge, ALIGN_CENTER, str(self.rank))

        if self.in_library:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C["accent"]))
            p.drawEllipse(QRectF(12 + self.ART - 32, 18, 24, 24))
            p.drawPixmap(12 + self.ART - 28, 22, make_icon_pixmap("check", C["on_accent"], 16))

        if hover or self.loading:
            cx, cy, d = 12 + self.ART - 52, 12 + self.ART - 52, 44
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 90))
            p.drawEllipse(QRectF(cx - 1, cy + 2, d + 2, d + 2))
            p.setBrush(QColor(C["accent"]))
            p.drawEllipse(QRectF(cx, cy, d, d))
            if self.loading:
                p.setPen(QPen(QColor(C["on_accent"]), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawArc(QRectF(cx + 12, cy + 12, 20, 20), 90 * 16, 270 * 16)
            else:
                p.drawPixmap(cx + 12, cy + 12, make_icon_pixmap("play", C["on_accent"], 20))

        tw = self.width() - 24
        f = ui_font(13, QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(QColor(C["text"]))
        p.drawText(12, self.ART + 34, elide(self.track["title"], f, tw))
        f = ui_font(12)
        p.setFont(f)
        p.setPen(QColor(C["muted"]))
        p.drawText(12, self.ART + 54, elide(self.track["artist"], f, tw))


class ResultRow(QWidget):
    """Fila de resultado de búsqueda (de tu biblioteca o de YouTube)."""

    activated = pyqtSignal(object)
    THUMB_W, THUMB_H = 112, 63

    def __init__(self, data: dict, kind: str, parent=None):
        super().__init__(parent)
        self.data = data
        self.kind = kind  # "local" | "yt"
        self.state = ""
        self.setFixedHeight(self.THUMB_H + 16)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        if kind == "local":
            self._thumb = cached_artwork(data.get("genre") or "Otros", data.get("thumbnail_path", ""), self.THUMB_H, 8)
        else:
            self._thumb = create_wide_thumb(data.get("thumb", ""), self.THUMB_W, self.THUMB_H, 8)
            if data.get("local_song"):
                self.state = "En tu biblioteca"
        self.setToolTip(data.get("title", ""))

    def set_state(self, text: str):
        self.state = text
        self.update()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.activated.emit(self)
        super().mouseReleaseEvent(e)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        hover = self.underMouse()
        if hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C["hover"]))
            p.drawRoundedRect(QRectF(0, 0, w, h), 12, 12)

        p.drawPixmap(8, 8, self._thumb)
        thumb_w = self.THUMB_H if self.kind == "local" else self.THUMB_W
        if self.kind == "yt" and self.data.get("duration"):
            dur = fmt_seconds(self.data["duration"])
            f = ui_font(10, QFont.Weight.Bold)
            p.setFont(f)
            tw = QFontMetrics(f).horizontalAdvance(dur) + 10
            r = QRectF(8 + thumb_w - tw - 4, 8 + self.THUMB_H - 20, tw, 16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 190))
            p.drawRoundedRect(r, 4, 4)
            p.setPen(QColor("#ffffff"))
            p.drawText(r, ALIGN_CENTER, dur)

        # Botón/estado a la derecha
        if self.state and self.state != "En tu biblioteca":
            pill_text, pill_bg, pill_fg, icon = self.state, C["accent_lo"], C["accent_hi"], "download"
        elif self.kind == "local" or self.data.get("local_song"):
            pill_text, pill_bg, pill_fg, icon = "Reproducir", C["accent"], C["on_accent"], "play"
        else:
            pill_text, icon = "Escuchar", "play"
            pill_bg, pill_fg = (C["accent"], C["on_accent"]) if hover else (C["elev"], C["text"])
        f = ui_font(12, QFont.Weight.Bold)
        pw = QFontMetrics(f).horizontalAdvance(pill_text) + 44
        pill = QRectF(w - pw - 14, (h - 32) / 2, pw, 32)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(pill_bg))
        p.drawRoundedRect(pill, 16, 16)
        p.drawPixmap(int(pill.left()) + 12, int(pill.top()) + 8, make_icon_pixmap(icon, pill_fg, 16))
        p.setFont(f)
        p.setPen(QColor(pill_fg))
        p.drawText(pill.adjusted(32, 0, -12, 0), ALIGN_LEFT, pill_text)

        # Texto
        tx = 8 + thumb_w + 16
        tw = int(pill.left()) - tx - 16
        if self.kind == "local":
            title = display_title(self.data["title"], self.data.get("artist", ""))
            sub = f"{self.data.get('artist') or 'Artista desconocido'}  ·  {self.data.get('genre') or 'Otros'}  ·  {fmt_seconds(self.data.get('duration') or 0)}"
        else:
            title = self.data["title"]
            parts = [self.data.get("channel", ""), fmt_views(self.data.get("views", 0))]
            sub = "  ·  ".join(x for x in parts if x)
        f = ui_font(14, QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(C["text"]))
        p.drawText(QRect(tx, 14, tw, 22), ALIGN_LEFT, elide(title, f, tw))
        f = ui_font(12)
        p.setFont(f)
        p.setPen(QColor(C["muted"]))
        p.drawText(QRect(tx, 38, tw, 18), ALIGN_LEFT, elide(sub, f, tw))
        if self.state == "En tu biblioteca":
            f = ui_font(11, QFont.Weight.Bold)
            p.setFont(f)
            p.setPen(QColor(C["accent_hi"]))
            p.drawText(QRect(tx, 56, tw, 16), ALIGN_LEFT, "✓ Ya está en tu biblioteca")


# =====================================================================
# LISTAS Y TABLAS
# =====================================================================
class TopSongDelegate(QStyledItemDelegate):
    """Fila del ranking 'Más escuchadas' en la barra lateral."""

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 58)

    def paint(self, p: QPainter, option, index):
        song = index.data(ROLE_SONG)
        if not song:
            return
        playing = bool(index.data(ROLE_PLAYING))
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        r = option.rect.adjusted(0, 2, 0, -2)
        rank = index.row() + 1
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if hover or playing:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C["hover"] if hover else C["elev"]))
            p.drawRoundedRect(QRectF(r), 10, 10)
        p.setFont(ui_font(13, QFont.Weight.Bold))
        p.setPen(QColor(C["gold"] if rank <= 3 else C["dim"]))
        p.drawText(QRect(r.left() + 4, r.top(), 24, r.height()), ALIGN_CENTER, str(rank))
        genre = song.get("genre") or "Otros"
        p.drawPixmap(r.left() + 34, r.top() + (r.height() - 42) // 2, cached_artwork(genre, song.get("thumbnail_path", ""), 42, 7))
        tx = r.left() + 88
        tw = r.right() - tx - 8
        f = ui_font(13, QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(C["accent_hi"] if playing else C["text"]))
        p.drawText(QRect(tx, r.top() + 9, tw, 20), ALIGN_LEFT, elide(display_title(song["title"], song.get("artist", "")), f, tw))
        f = ui_font(11)
        p.setFont(f)
        p.setPen(QColor(C["muted"]))
        plays = song.get("play_count", 0)
        sub = f"{song.get('artist') or genre} · {plays} {'escucha' if plays == 1 else 'escuchas'}"
        p.drawText(QRect(tx, r.top() + 29, tw, 18), ALIGN_LEFT, elide(sub, f, tw))
        p.restore()


class LibraryTable(QTableWidget):
    """Tabla de biblioteca con resaltado de fila completa al pasar el ratón."""

    COLS = ["#", "TÍTULO", "GÉNERO", "ESCUCHAS", "ÚLTIMA VEZ", "", "DURACIÓN"]
    COL_FAV = 5

    def __init__(self, parent=None):
        super().__init__(0, len(self.COLS), parent)
        self.hover_row = -1
        self.playing_id = None
        self.setMouseTracking(True)

    def mouseMoveEvent(self, e):
        row = self.rowAt(int(e.position().y()))
        if row != self.hover_row:
            self.hover_row = row
            self.viewport().update()
        col = self.columnAt(int(e.position().x()))
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if col == self.COL_FAV and row >= 0 else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self.hover_row = -1
        self.viewport().update()
        super().leaveEvent(e)

    def resizeEvent(self, e):
        # En ventanas angostas se ocultan columnas secundarias para que el título respire
        w = self.viewport().width()
        self.setColumnHidden(4, w < 900)  # ÚLTIMA VEZ
        self.setColumnHidden(3, w < 780)  # ESCUCHAS
        super().resizeEvent(e)


class LibraryDelegate(QStyledItemDelegate):
    def __init__(self, table: LibraryTable):
        super().__init__(table)
        self.table = table

    def paint(self, p: QPainter, option, index):
        song = index.sibling(index.row(), 0).data(ROLE_SONG)
        if not song:
            return
        r = option.rect
        col = index.column()
        last_col = self.table.columnCount() - 1
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = index.row() == self.table.hover_row
        playing = song["id"] == self.table.playing_id

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        bg = QColor(C["accent_lo"]) if selected else QColor(C["hover"]) if hover else None
        if bg is not None:
            p.setClipRect(r)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            rr = QRectF(r).adjusted(0, 2, 0, -2)
            if col == 0:
                rr.adjust(0, 0, 20, 0)
            if col == last_col:
                rr.adjust(-20, 0, 0, 0)
            p.drawRoundedRect(rr, 10, 10)
            p.setClipping(False)

        if col == 0:
            cx = r.left() + (r.width() - 18) // 2
            cy = r.top() + (r.height() - 18) // 2
            if playing:
                p.drawPixmap(cx, cy, make_icon_pixmap("eq", C["accent"], 18))
            elif hover:
                p.drawPixmap(cx, cy, make_icon_pixmap("play", C["text"], 18))
            else:
                p.setFont(ui_font(13))
                p.setPen(QColor(C["dim"]))
                p.drawText(r, ALIGN_CENTER, str(index.row() + 1))
        elif col == 1:
            genre = song.get("genre") or "Otros"
            art = 40
            p.drawPixmap(r.left() + 6, r.top() + (r.height() - art) // 2, cached_artwork(genre, song.get("thumbnail_path", ""), art, 7))
            tx = r.left() + art + 20
            tw = r.right() - tx - 10
            f = ui_font(14, QFont.Weight.DemiBold)
            p.setFont(f)
            p.setPen(QColor(C["accent_hi"] if playing else C["text"]))
            p.drawText(QRect(tx, r.top() + 8, tw, 22), ALIGN_LEFT, elide(display_title(song["title"], song.get("artist", "")), f, tw))
            f = ui_font(12)
            p.setFont(f)
            p.setPen(QColor(C["muted"]))
            p.drawText(QRect(tx, r.top() + 30, tw, 18), ALIGN_LEFT, elide(song.get("artist") or "Artista desconocido", f, tw))
        elif col == 2:
            genre = song.get("genre") or "Otros"
            c1, _ = GENRE_COLORS.get(genre, (C["accent"], C["accent_press"]))
            f = ui_font(11, QFont.Weight.Bold)
            p.setFont(f)
            fm = QFontMetrics(f)
            pw = min(fm.horizontalAdvance(genre) + 22, r.width() - 8)
            pill = QRectF(r.left() + 4, r.top() + (r.height() - 24) / 2, pw, 24)
            fill = QColor(c1)
            fill.setAlpha(46)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(pill, 12, 12)
            p.setPen(QColor(c1).lighter(135))
            p.drawText(pill, ALIGN_CENTER, fm.elidedText(genre, Qt.TextElideMode.ElideRight, int(pw - 12)))
        elif col == LibraryTable.COL_FAV:
            fav = bool(song.get("favorite"))
            if fav or hover:
                cx = r.left() + (r.width() - 18) // 2
                cy = r.top() + (r.height() - 18) // 2
                p.drawPixmap(cx, cy, make_icon_pixmap("heart_fill" if fav else "heart", C["accent"] if fav else C["muted"], 18))
        else:
            if col == 3:
                text = str(song.get("play_count", 0))
            elif col == 4:
                text = humanize_dt(song.get("last_played"))
            else:
                text = fmt_seconds(song.get("duration") or 0)
            p.setFont(ui_font(13))
            p.setPen(QColor(C["muted"]))
            align = Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignRight if col == last_col else Qt.AlignmentFlag.AlignLeft)
            p.drawText(r.adjusted(8, 0, -16, 0), int(align), text)
        p.restore()
