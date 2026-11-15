"""Puquichu — sistema de diseño: paleta de estaciones, iconos vectoriales, carátulas y hoja de estilos.

La paleta nace del campo de la sierra:
  * Puquy  (temporada de lluvias): verde del pasto cuando brota.
  * Ichu   (temporada seca):       dorado del pasto seco de la puna.
"""
import os
import re
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)

from core import CACHE_DIR, GENRE_COLORS

UI_FONT = "Ubuntu Sans"

# Colores fijos de las dos estaciones (se usan en el logo y en detalles)
GREEN_PUQUY = "#86cf4a"
GOLD_ICHU = "#d8ad55"

SEASONS = {
    "puquy": {
        "label": "Puquy · temporada de lluvias",
        "accent": GREEN_PUQUY,
        "accent_hover": "#9cdc66",
        "accent_press": "#6fb236",
        "accent_hi": "#b8ec85",
        "accent_mid": "#3c6524",
        "accent_lo": "#1c3011",
        "on_accent": "#0b1706",
    },
    "ichu": {
        "label": "Ichu · temporada seca",
        "accent": GOLD_ICHU,
        "accent_hover": "#e5c075",
        "accent_press": "#bf963f",
        "accent_hi": "#f2d796",
        "accent_mid": "#6b5326",
        "accent_lo": "#33270f",
        "on_accent": "#1c1406",
    },
}

# Neutros cálidos con un leve tono de tierra y oliva
C = {
    "bg": "#080907",
    "panel": "#10120e",
    "panel_alt": "#151812",
    "elev": "#1c2018",
    "hover": "#252a20",
    "border": "#272c22",
    "text": "#f2f1e9",
    "muted": "#a8a999",
    "dim": "#727464",
    "danger": "#e5534b",
    "green": GREEN_PUQUY,
    "gold": GOLD_ICHU,
}
C.update(SEASONS["puquy"])


def season_for_month(month: int | None = None) -> str:
    """En la sierra llueve aprox. de diciembre a abril; el resto del año es temporada seca."""
    month = month or datetime.now().month
    return "puquy" if month in (12, 1, 2, 3, 4) else "ichu"


def resolve_season(setting: str) -> str:
    return setting if setting in SEASONS else season_for_month()


def apply_season(season: str):
    C.update({k: v for k, v in SEASONS[season].items() if k != "label"})
    _ART_CACHE.clear()


# =====================================================================
# UTILIDADES DE TEXTO
# =====================================================================
_TITLE_NOISE = re.compile(
    r"\s*[\(\[][^\)\]]*(official|oficial|video|audio|lyric|letra|visualizer|hd|4k|remaster)[^\)\]]*[\)\]]",
    re.IGNORECASE,
)


def display_title(title: str, artist: str = "") -> str:
    """Título limpio solo para mostrar (no modifica la base de datos)."""
    t = _TITLE_NOISE.sub("", title or "").strip()
    for sep in (" - ", " | ", " – "):
        if sep in t:
            left, right = t.split(sep, 1)
            if artist and left.strip().lower() == artist.strip().lower() and right.strip():
                t = right.strip()
            break
    return t or (title or "")


def fmt_seconds(sec: int) -> str:
    if not sec or sec <= 0:
        return "—"
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_views(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f} mil M vistas".replace(".0 ", " ")
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} M vistas".replace(".0 ", " ")
    if n >= 1_000:
        return f"{n // 1_000} mil vistas"
    return f"{n} vistas" if n else ""


def humanize_dt(value) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return str(value)
    secs = (datetime.now() - dt).total_seconds()
    if secs < 90:
        return "Ahora mismo"
    if secs < 3600:
        return f"Hace {int(secs // 60)} min"
    if secs < 86400:
        return f"Hace {int(secs // 3600)} h"
    if secs < 172800:
        return "Ayer"
    if secs < 7 * 86400:
        return f"Hace {int(secs // 86400)} días"
    return dt.strftime("%d/%m/%Y")


# =====================================================================
# ICONOS VECTORIALES (cuadrícula de 24x24)
# =====================================================================
def draw_icon(p: QPainter, name: str, color: QColor):
    thin = name in ("win_min", "win_max", "win_restore", "win_close")
    pen = QPen(color, 1.3 if thin else 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    def poly(*pts, close=False):
        path = QPainterPath()
        path.moveTo(*pts[0])
        for pt in pts[1:]:
            path.lineTo(*pt)
        if close:
            path.closeSubpath()
        p.drawPath(path)

    def filled(*pts):
        path = QPainterPath()
        path.moveTo(*pts[0])
        for pt in pts[1:]:
            path.lineTo(*pt)
        path.closeSubpath()
        p.save()
        p.setPen(QPen(color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(color)
        p.drawPath(path)
        p.restore()

    def fill_path(path):
        p.save()
        p.setBrush(color)
        p.drawPath(path)
        p.restore()

    def speaker():
        filled((3.5, 9.5), (7, 9.5), (11.5, 5.5), (11.5, 18.5), (7, 14.5), (3.5, 14.5))

    def heart_path():
        path = QPainterPath()
        path.moveTo(12, 20)
        path.cubicTo(6, 16, 2.5, 12.5, 3.2, 8.6)
        path.cubicTo(3.8, 5.2, 8.6, 3.8, 12, 7.6)
        path.cubicTo(15.4, 3.8, 20.2, 5.2, 20.8, 8.6)
        path.cubicTo(21.5, 12.5, 18, 16, 12, 20)
        path.closeSubpath()
        return path

    if name == "home":
        poly((3.5, 10.5), (12, 3.5), (20.5, 10.5))
        poly((5.5, 9), (5.5, 20), (18.5, 20), (18.5, 9))
        poly((10, 20), (10, 14.5), (14, 14.5), (14, 20))
    elif name == "library":
        poly((5, 4), (5, 20))
        poly((10, 4), (10, 20))
        poly((14.5, 4.8), (19.5, 19.2))
    elif name == "settings":
        poly((4, 7), (11.5, 7))
        poly((17.5, 7), (20, 7))
        p.drawEllipse(QRectF(11.5, 4.5, 5, 5))
        poly((4, 17), (6.5, 17))
        poly((12.5, 17), (20, 17))
        p.drawEllipse(QRectF(6.5, 14.5, 5, 5))
    elif name == "search":
        p.drawEllipse(QRectF(4, 4, 13, 13))
        poly((15.5, 15.5), (20.5, 20.5))
    elif name == "play":
        filled((7.5, 4.5), (19.5, 12), (7.5, 19.5))
    elif name == "pause":
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(6, 4.5, 4.2, 15), 1.2, 1.2)
        p.drawRoundedRect(QRectF(13.8, 4.5, 4.2, 15), 1.2, 1.2)
        p.restore()
    elif name == "next":
        filled((5, 5), (15, 12), (5, 19))
        poly((18.5, 5), (18.5, 19))
    elif name == "prev":
        filled((19, 5), (9, 12), (19, 19))
        poly((5.5, 5), (5.5, 19))
    elif name == "shuffle":
        path = QPainterPath()
        path.moveTo(3, 17)
        path.lineTo(6.5, 17)
        path.cubicTo(11, 17, 12, 7, 16.5, 7)
        path.lineTo(20, 7)
        path.moveTo(3, 7)
        path.lineTo(6.5, 7)
        path.cubicTo(11, 7, 12, 17, 16.5, 17)
        path.lineTo(20, 17)
        p.drawPath(path)
        poly((17.5, 4.5), (20, 7), (17.5, 9.5))
        poly((17.5, 14.5), (20, 17), (17.5, 19.5))
    elif name == "repeat":
        path = QPainterPath()
        path.moveTo(4, 11.5)
        path.lineTo(4, 9.5)
        path.quadTo(4, 6.5, 7, 6.5)
        path.lineTo(19, 6.5)
        path.moveTo(20, 12.5)
        path.lineTo(20, 14.5)
        path.quadTo(20, 17.5, 17, 17.5)
        path.lineTo(5, 17.5)
        p.drawPath(path)
        poly((16.5, 4), (19, 6.5), (16.5, 9))
        poly((7.5, 15), (5, 17.5), (7.5, 20))
    elif name in ("volume", "volume_low"):
        speaker()
        path = QPainterPath()
        r1 = QRectF(9.5, 8.5, 7, 7)
        path.arcMoveTo(r1, -50)
        path.arcTo(r1, -50, 100)
        if name == "volume":
            r2 = QRectF(8, 5, 13, 14)
            path.arcMoveTo(r2, -50)
            path.arcTo(r2, -50, 100)
        p.drawPath(path)
    elif name == "mute":
        speaker()
        poly((15.5, 9.5), (20.5, 14.5))
        poly((20.5, 9.5), (15.5, 14.5))
    elif name == "folder":
        path = QPainterPath()
        path.moveTo(3, 7)
        path.quadTo(3, 5, 5, 5)
        path.lineTo(9.5, 5)
        path.lineTo(11.5, 7.5)
        path.lineTo(19, 7.5)
        path.quadTo(21, 7.5, 21, 9.5)
        path.lineTo(21, 17)
        path.quadTo(21, 19, 19, 19)
        path.lineTo(5, 19)
        path.quadTo(3, 19, 3, 17)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "trend":
        poly((3, 17), (9, 11), (13, 15), (21, 7))
        poly((15.5, 7), (21, 7), (21, 12.5))
    elif name == "download":
        poly((12, 4), (12, 15))
        poly((7.5, 10.5), (12, 15), (16.5, 10.5))
        poly((5, 19.5), (19, 19.5))
    elif name == "music":
        p.save()
        p.setBrush(color)
        p.drawEllipse(QRectF(4.5, 14.5, 6, 5))
        p.drawEllipse(QRectF(13.5, 12.5, 6, 5))
        p.restore()
        poly((10.5, 17), (10.5, 5.5), (19.5, 3.5), (19.5, 15))
    elif name == "clock":
        p.drawEllipse(QRectF(3.5, 3.5, 17, 17))
        poly((12, 7.5), (12, 12), (15, 14))
    elif name == "eq":
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(4, 9, 3.4, 11), 1, 1)
        p.drawRoundedRect(QRectF(10.3, 4, 3.4, 16), 1, 1)
        p.drawRoundedRect(QRectF(16.6, 12, 3.4, 8), 1, 1)
        p.restore()
    elif name == "sliders_v":
        for x, knob in ((6, 15), (12, 8), (18, 13)):
            poly((x, 4), (x, 20))
            p.save()
            p.setBrush(color)
            p.drawEllipse(QRectF(x - 2.2, knob - 2.2, 4.4, 4.4))
            p.restore()
    elif name == "sparkle":
        path = QPainterPath()
        path.moveTo(12, 3)
        path.quadTo(13, 11, 21, 12)
        path.quadTo(13, 13, 12, 21)
        path.quadTo(11, 13, 3, 12)
        path.quadTo(11, 11, 12, 3)
        fill_path(path)
    elif name == "chevron_down":
        poly((6, 9), (12, 15), (18, 9))
    elif name == "chevron_right":
        poly((9, 6), (15, 12), (9, 18))
    elif name in ("back10", "fwd10"):
        rect = QRectF(4, 4, 16, 16)
        path = QPainterPath()
        path.arcMoveTo(rect, 90)
        path.arcTo(rect, 90, 270 if name == "back10" else -270)
        p.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
        if name == "back10":
            poly((14.2, 1.8), (11.8, 4), (14.2, 6.2))
        else:
            poly((9.8, 1.8), (12.2, 4), (9.8, 6.2))
        f = QFont(UI_FONT)
        f.setPixelSize(7)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(4, 6.5, 16, 12), Qt.AlignmentFlag.AlignCenter, "10")
    elif name == "heart":
        p.drawPath(heart_path())
    elif name == "heart_fill":
        fill_path(heart_path())
    elif name == "queue":
        poly((4, 6), (17, 6))
        poly((4, 11), (17, 11))
        poly((4, 16), (11, 16))
        filled((14.5, 13.8), (20, 16.8), (14.5, 19.8))
    elif name == "moon":
        outer = QPainterPath()
        outer.addEllipse(QRectF(3.5, 3.5, 17, 17))
        cut = QPainterPath()
        cut.addEllipse(QRectF(9, 0.5, 15, 15))
        p.drawPath(outer.subtracted(cut))
    elif name == "edit":
        poly((4, 20), (4.6, 16), (15.5, 5.1), (18.9, 8.5), (8, 19.4), close=True)
        poly((13.3, 7.3), (16.7, 10.7))
    elif name == "trash":
        poly((4, 6.5), (20, 6.5))
        poly((9, 6.5), (9.6, 4), (14.4, 4), (15, 6.5))
        poly((6, 6.5), (7, 20), (17, 20), (18, 6.5))
        poly((10, 10.5), (10, 16.5))
        poly((14, 10.5), (14, 16.5))
    elif name == "plus":
        poly((12, 5), (12, 19))
        poly((5, 12), (19, 12))
    elif name == "check":
        poly((5, 12.5), (10, 17), (19, 7.5))
    elif name == "close":
        poly((6.5, 6.5), (17.5, 17.5))
        poly((17.5, 6.5), (6.5, 17.5))
    elif name == "refresh":
        rect = QRectF(4.5, 4.5, 15, 15)
        path = QPainterPath()
        path.arcMoveTo(rect, 60)
        path.arcTo(rect, 60, 290)
        p.drawPath(path)
        poly((15.5, 2.5), (16, 6.5), (12, 7))
    elif name == "warning":
        poly((12, 3.5), (21, 19.5), (3, 19.5), close=True)
        poly((12, 9.5), (12, 13.5))
        p.save()
        p.setBrush(color)
        p.drawEllipse(QRectF(11.2, 16, 1.6, 1.6))
        p.restore()
    elif name == "keyboard":
        p.drawRoundedRect(QRectF(2.5, 6, 19, 12), 2.5, 2.5)
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        for x in (6, 9.5, 13, 16.5):
            p.drawEllipse(QRectF(x - 0.9, 9, 1.8, 1.8))
        p.restore()
        poly((7.5, 14.5), (16.5, 14.5))
    elif name == "bell":
        path = QPainterPath()
        path.moveTo(5, 17)
        path.lineTo(6.5, 15)
        path.lineTo(6.5, 10.5)
        path.cubicTo(6.5, 7, 9, 4.5, 12, 4.5)
        path.cubicTo(15, 4.5, 17.5, 7, 17.5, 10.5)
        path.lineTo(17.5, 15)
        path.lineTo(19, 17)
        path.closeSubpath()
        p.drawPath(path)
        poly((10, 20), (14, 20))
    elif name == "sprout":
        # Tres hojas de pasto brotando de la tierra
        path = QPainterPath()
        path.moveTo(12, 21)
        path.quadTo(11.2, 12, 13.2, 3.5)
        path.moveTo(11.2, 21)
        path.quadTo(9, 13.5, 3.8, 8.5)
        path.moveTo(12.8, 21)
        path.quadTo(15.2, 14.5, 20.5, 10.5)
        p.save()
        p.setPen(QPen(color, 2.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
        p.restore()
        poly((7, 21), (17, 21))
    elif name == "compass":
        p.drawEllipse(QRectF(3, 3, 18, 18))
        filled((15.6, 8.4), (13.2, 13.2), (8.4, 15.6), (10.8, 10.8))
    elif name == "cloud":
        path = QPainterPath()
        path.moveTo(7, 18.5)
        path.cubicTo(3.5, 18.5, 2.5, 13.5, 6, 12.5)
        path.cubicTo(6, 8, 11, 6, 13.5, 9)
        path.cubicTo(15, 7.5, 18.5, 8.5, 18, 11.5)
        path.cubicTo(21.5, 12, 21.5, 18.5, 17.5, 18.5)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "speaker":
        p.drawRoundedRect(QRectF(6, 2.5, 12, 19), 2.5, 2.5)
        p.drawEllipse(QRectF(8.5, 10, 7, 7))
        p.save()
        p.setBrush(color)
        p.drawEllipse(QRectF(11, 5, 2, 2))
        p.restore()
    elif name == "win_min":
        poly((6.5, 12.5), (17.5, 12.5))
    elif name == "win_max":
        p.drawRoundedRect(QRectF(6.5, 6.5, 11, 11), 1.5, 1.5)
    elif name == "win_restore":
        p.drawRoundedRect(QRectF(6.5, 9, 8.5, 8.5), 1.2, 1.2)
        poly((9, 9), (9, 6.5), (17.5, 6.5), (17.5, 15), (15, 15))
    elif name == "win_close":
        poly((7, 7), (17, 17))
        poly((17, 7), (7, 17))


def make_icon_pixmap(name: str, color, size: int = 20) -> QPixmap:
    dpr = 2
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.scale(size * dpr / 24.0, size * dpr / 24.0)
    draw_icon(p, name, QColor(color))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def make_icon(name: str, color=None, size: int = 20) -> QIcon:
    return QIcon(make_icon_pixmap(name, color or C["text"], size))


# =====================================================================
# LOGO DE PUQUICHU (brote verde + pasto dorado: las dos estaciones)
# =====================================================================
def brand_logo(size: int) -> QPixmap:
    dpr = 2
    px = size * dpr
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, px, px)
    grad.setColorAt(0.0, QColor(GREEN_PUQUY))
    grad.setColorAt(1.0, QColor(GOLD_ICHU))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(0, 0, px, px), px * 0.28, px * 0.28)
    icon = make_icon_pixmap("sprout", "#10170a", int(size * 0.66))
    icon.setDevicePixelRatio(1)
    p.drawPixmap((px - icon.width()) // 2, (px - icon.height()) // 2 + int(px * 0.02), icon)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def save_brand_icon(path: Path, size: int = 256):
    path.parent.mkdir(parents=True, exist_ok=True)
    pm = brand_logo(size // 2)
    pm.setDevicePixelRatio(1)
    pm.save(str(path))


# =====================================================================
# CARÁTULAS
# =====================================================================
def create_artwork_pixmap(title: str, genre: str, thumb_path: str = "", size: int = 120, radius: int = 14) -> QPixmap:
    dpr = 2
    px = size * dpr
    pixmap = QPixmap(px, px)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, px, px), radius * dpr, radius * dpr)
    painter.setClipPath(path)

    loaded = False
    if thumb_path and os.path.exists(thumb_path):
        src = QPixmap(thumb_path)
        if not src.isNull():
            # Las miniaturas de YouTube son 16:9 -> recorte cuadrado centrado
            scaled = src.scaled(px, px, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(0, 0, scaled, (scaled.width() - px) // 2, (scaled.height() - px) // 2, px, px)
            loaded = True

    if not loaded:
        c1, c2 = GENRE_COLORS.get(genre, (C["accent"], C["accent_press"]))
        grad = QLinearGradient(0, 0, px, px)
        grad.setColorAt(0.0, QColor(c1))
        grad.setColorAt(1.0, QColor(c2).darker(140))
        painter.fillRect(0, 0, px, px, grad)
        glow = QRadialGradient(px * 0.25, px * 0.2, px * 0.8)
        glow.setColorAt(0.0, QColor(255, 255, 255, 60))
        glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(0, 0, px, px, glow)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i, frac in enumerate((0.78, 0.6, 0.42)):
            painter.setPen(QPen(QColor(255, 255, 255, 26 + i * 8), max(1.0, px * 0.008)))
            d = px * frac
            painter.drawEllipse(QRectF((px - d) / 2, (px - d) / 2, d, d))
        note = make_icon_pixmap("music", QColor(255, 255, 255, 235), max(10, int(size * 0.32)))
        note.setDevicePixelRatio(1)
        painter.drawPixmap((px - note.width()) // 2, (px - note.height()) // 2, note)

    painter.end()
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def create_wide_thumb(thumb_path: str, w: int, h: int, radius: int = 8) -> QPixmap:
    """Miniatura 16:9 redondeada (resultados de búsqueda)."""
    dpr = 2
    pm = QPixmap(w * dpr, h * dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w * dpr, h * dpr), radius * dpr, radius * dpr)
    p.setClipPath(path)
    src = QPixmap(thumb_path) if thumb_path and os.path.exists(thumb_path) else QPixmap()
    if not src.isNull():
        scaled = src.scaled(w * dpr, h * dpr, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(0, 0, scaled, (scaled.width() - w * dpr) // 2, (scaled.height() - h * dpr) // 2, w * dpr, h * dpr)
    else:
        p.fillRect(0, 0, w * dpr, h * dpr, QColor(C["elev"]))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


_ART_CACHE: dict = {}
_COLOR_CACHE: dict = {}


def cached_artwork(genre: str, thumb: str, size: int, radius: int) -> QPixmap:
    key = (genre or "Otros", thumb or "", size, radius)
    if key not in _ART_CACHE:
        _ART_CACHE[key] = create_artwork_pixmap("", genre, thumb or "", size, radius)
    return _ART_CACHE[key]


def dominant_color(thumb_path: str, genre: str) -> QColor:
    key = (thumb_path or "", genre or "")
    if key in _COLOR_CACHE:
        return QColor(_COLOR_CACHE[key])
    color = QColor(GENRE_COLORS.get(genre, (C["accent"], C["accent_press"]))[0])
    if thumb_path and os.path.exists(thumb_path):
        img = QImage(thumb_path)
        if not img.isNull():
            small = img.scaled(24, 24, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            r = g = b = w = 0.0
            for x in range(small.width()):
                for y in range(small.height()):
                    c = QColor(small.pixel(x, y))
                    _h, s, v, _a = c.getHsvF()
                    weight = 0.05 + (s * v) ** 2
                    r += c.redF() * weight
                    g += c.greenF() * weight
                    b += c.blueF() * weight
                    w += weight
            if w > 0:
                avg = QColor.fromRgbF(r / w, g / w, b / w)
                h, s, v, _a = avg.getHsvF()
                color = QColor.fromHsvF(max(h, 0.0), min(1.0, s * 1.15 + 0.05), min(0.72, max(0.42, v)))
    _COLOR_CACHE[key] = QColor(color)
    return color


def _ui_asset(name: str, icon_name: str, color: str, size: int = 16) -> str:
    """PNG temporal para la hoja de estilos (flechas de los combos)."""
    folder = CACHE_DIR / "ui"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{name}.png"
    pm = make_icon_pixmap(icon_name, color, size)
    pm.setDevicePixelRatio(1)
    pm.save(str(target))
    return target.as_posix()


# =====================================================================
# HOJA DE ESTILOS (QSS)
# =====================================================================
_QSS_TEMPLATE = """
QMainWindow { background-color: @bg; }
QWidget {
    color: @text;
    font-family: '__FONT__', 'Ubuntu', 'Noto Sans', sans-serif;
    font-size: 13px;
}
QWidget#Root { background-color: @bg; }
QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QLabel { background: transparent; }

QToolTip {
    background-color: @elev; color: @text; border: 1px solid @border;
    border-radius: 6px; padding: 6px 8px;
}

/* BARRA DE TÍTULO PROPIA */
QWidget#TitleBar { background: transparent; }
QLabel#TitleText { color: @dim; font-size: 12px; font-weight: 600; }
QPushButton.WinBtn {
    background: transparent; border: none; border-radius: 8px;
    min-width: 40px; max-width: 40px; min-height: 30px; max-height: 30px;
}
QPushButton.WinBtn:hover { background-color: @elev; }
QPushButton#WinClose:hover { background-color: #c42b1c; }

/* PANELES */
QFrame#Sidebar, QFrame#MainPanel { background-color: @panel; border-radius: 16px; }
QFrame#BottomPlayer { background-color: @bg; }

/* TIPOGRAFÍA */
QLabel#Brand { font-size: 19px; font-weight: 800; color: @text; }
QLabel#BrandSub { font-size: 11px; font-weight: 600; color: @dim; }
QLabel#H1 { font-size: 30px; font-weight: 800; color: @text; }
QLabel#H2 { font-size: 19px; font-weight: 800; color: @text; }
QLabel#H3 { font-size: 15px; font-weight: 700; color: @text; }
QLabel#RowTitle { font-size: 14px; font-weight: 600; color: @text; }
QLabel#Kicker { font-size: 11px; font-weight: 700; color: @dim; letter-spacing: 1.2px; }
QLabel#Muted { color: @muted; font-size: 13px; }
QLabel#Dim { color: @dim; font-size: 12px; }
QLabel#Accent { color: @accent_hi; font-size: 12px; font-weight: 700; }
QLabel#HeroKicker { color: rgba(255,255,255,0.75); font-size: 11px; font-weight: 800; letter-spacing: 1.6px; }
QLabel#HeroTitle { color: #ffffff; font-size: 32px; font-weight: 800; }
QLabel#HeroArtist { color: rgba(255,255,255,0.88); font-size: 15px; font-weight: 600; }
QLabel#HeroMeta { color: rgba(255,255,255,0.55); font-size: 12px; }
QLabel#GlassBadge {
    background-color: rgba(255,255,255,0.12); color: #ffffff;
    font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 11px;
}
QLabel#PlayerTitle { font-size: 14px; font-weight: 700; color: @text; }
QLabel#PlayerSub { font-size: 12px; color: @muted; }
QLabel#Time { font-size: 11px; color: @muted; font-family: 'Ubuntu Sans Mono', 'Ubuntu Mono', monospace; }
QLabel#IconTile { background-color: @accent_lo; border-radius: 10px; }
QLabel#Kbd {
    background-color: @elev; border: 1px solid @border; border-bottom: 2px solid @border;
    border-radius: 6px; padding: 2px 8px; font-size: 12px; font-weight: 700; color: @text;
}

/* NAVEGACIÓN */
QPushButton.NavBtn {
    background-color: transparent; color: @muted; text-align: left;
    padding: 10px 14px; border-radius: 10px; font-size: 14px; font-weight: 700; border: none;
}
QPushButton.NavBtn:hover { background-color: @elev; color: @text; }
QPushButton.NavBtn[active="true"] { background-color: @elev; color: @text; }

QListWidget#SidebarTopList { background: transparent; border: none; outline: none; }
QFrame#StorageBox { background-color: @panel_alt; border: 1px solid @border; border-radius: 12px; }
QFrame#SeasonPill { background-color: @accent_lo; border-radius: 12px; }

/* TARJETAS */
QFrame.Card { background-color: @panel_alt; border: 1px solid @border; border-radius: 16px; }
QFrame.Divider { background-color: @border; max-height: 1px; min-height: 1px; border: none; }
QFrame#ResultsPanel { background-color: @panel_alt; border: 1px solid @border; border-radius: 18px; }

/* BUSCADOR */
QLineEdit#MainSearch {
    background-color: @elev; border: 1px solid @border; border-radius: 19px;
    padding: 10px 16px; font-size: 14px; color: @text;
    selection-background-color: @accent; selection-color: @on_accent;
}
QLineEdit#MainSearch:hover { border-color: #3a4032; }
QLineEdit#MainSearch:focus { border: 1px solid @accent; background-color: @hover; }

/* BOTONES */
QPushButton#PrimaryBtn, QPushButton.PrimaryBtn {
    background-color: @accent; color: @on_accent; font-weight: 800; font-size: 14px;
    border-radius: 17px; padding: 10px 22px; border: none;
}
QPushButton#PrimaryBtn:hover, QPushButton.PrimaryBtn:hover { background-color: @accent_hover; }
QPushButton#PrimaryBtn:pressed, QPushButton.PrimaryBtn:pressed { background-color: @accent_press; }
QPushButton#PrimaryBtn:disabled, QPushButton.PrimaryBtn:disabled { background-color: @accent_lo; color: @muted; }

QPushButton.SecondaryBtn {
    background-color: @elev; color: @text; font-weight: 700; font-size: 13px;
    border-radius: 15px; padding: 8px 16px; border: 1px solid @border;
}
QPushButton.SecondaryBtn:hover { background-color: @hover; border-color: #3a4032; }
QPushButton.SecondaryBtn:disabled { color: @dim; }

QPushButton.DangerBtn {
    background-color: transparent; color: @danger; font-weight: 700; font-size: 13px;
    border-radius: 15px; padding: 8px 16px; border: 1px solid #5a2723;
}
QPushButton.DangerBtn:hover { background-color: #2a1311; }

QPushButton.GhostBtn {
    background: transparent; color: @muted; font-weight: 700; font-size: 13px;
    border: none; padding: 6px 4px;
}
QPushButton.GhostBtn:hover { color: @text; }

QPushButton.IconBtn {
    background: transparent; border: none; border-radius: 15px;
    min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
}
QPushButton.IconBtn:hover { background-color: @hover; }

QPushButton.GlassBtn {
    background-color: rgba(255,255,255,0.12); color: #ffffff; font-weight: 700;
    font-size: 13px; border-radius: 16px; padding: 8px 16px; border: 1px solid rgba(255,255,255,0.14);
}
QPushButton.GlassBtn:hover { background-color: rgba(255,255,255,0.2); }
QPushButton.GlassIcon {
    background-color: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.14); border-radius: 17px;
    min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px;
}
QPushButton.GlassIcon:hover { background-color: rgba(255,255,255,0.2); }

/* CHIPS */
QPushButton.GenreChip {
    background-color: @elev; color: @text; border: none;
    border-radius: 15px; padding: 7px 14px; font-size: 13px; font-weight: 600;
}
QPushButton.GenreChip:hover { background-color: @hover; }
QPushButton.GenreChip[active="true"] { background-color: @accent; color: @on_accent; font-weight: 800; }

QPushButton.SeasonBtn {
    background-color: @elev; color: @muted; border: 1px solid @border;
    border-radius: 14px; padding: 10px 14px; font-size: 13px; font-weight: 700; text-align: left;
}
QPushButton.SeasonBtn:hover { background-color: @hover; color: @text; }
QPushButton.SeasonBtn[active="true"] { border: 2px solid @accent; color: @text; background-color: @accent_lo; }

/* TABLA */
QTableWidget {
    background: transparent; border: none; gridline-color: transparent; outline: none;
    selection-background-color: transparent;
}
QHeaderView { background: transparent; border: none; }
QHeaderView::section {
    background: transparent; color: @dim; font-weight: 700; font-size: 11px;
    letter-spacing: 1px; padding: 8px 10px; border: none; border-bottom: 1px solid @border;
}

/* FORMULARIOS */
QComboBox, QLineEdit.SettingsInput {
    background-color: @elev; border: 1px solid @border; border-radius: 10px;
    padding: 8px 12px; color: @text; font-size: 13px;
    selection-background-color: @accent; selection-color: @on_accent;
}
QComboBox:hover, QLineEdit.SettingsInput:hover { border-color: #3a4032; }
QLineEdit.SettingsInput:focus { border-color: @accent; }
QComboBox { padding-right: 30px; }
QComboBox::drop-down { border: none; width: 28px; subcontrol-origin: padding; subcontrol-position: center right; }
QComboBox::down-arrow { image: url(__CHEVRON__); width: 14px; height: 14px; }
QComboBox QAbstractItemView {
    background-color: @elev; border: 1px solid @border; border-radius: 10px;
    padding: 4px; outline: none; selection-background-color: @accent_lo; selection-color: @text;
}
QComboBox#GlassCombo {
    background-color: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.14);
    border-radius: 16px; color: #ffffff; font-weight: 700; padding: 8px 32px 8px 16px;
}
QComboBox#GlassCombo:hover { background-color: rgba(255,255,255,0.2); }

/* MENÚS Y DIÁLOGOS */
QMenu {
    background-color: @elev; border: 1px solid @border; border-radius: 10px; padding: 6px;
}
QMenu::item { padding: 8px 24px 8px 12px; border-radius: 6px; color: @text; }
QMenu::item:selected { background-color: @hover; }
QMenu::item:disabled { color: @dim; }
QMenu::icon { padding-left: 8px; }
QMenu::separator { height: 1px; background: @border; margin: 4px 8px; }
QMenu::right-arrow { image: url(__CHEVRON_R__); width: 12px; height: 12px; }
QMessageBox, QDialog { background-color: @panel_alt; }
QMessageBox QLabel { font-size: 13px; }
QMessageBox QPushButton, QDialog QPushButton#DialogOk {
    background-color: @accent; color: @on_accent; border: none; border-radius: 14px;
    padding: 7px 18px; font-weight: 800; min-width: 80px;
}
QMessageBox QPushButton:hover, QDialog QPushButton#DialogOk:hover { background-color: @accent_hover; }

/* BARRAS DE DESPLAZAMIENTO */
QScrollBar:vertical { background: transparent; width: 10px; margin: 4px 2px; }
QScrollBar::handle:vertical { background: #2e3428; border-radius: 3px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #4b5342; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px 4px; }
QScrollBar::handle:horizontal { background: #2e3428; border-radius: 3px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #4b5342; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* DESCARGAS */
QFrame#StatusBanner { background-color: @accent_lo; border: 1px solid @accent_mid; border-radius: 14px; }
QProgressBar { background-color: rgba(255,255,255,0.1); border: none; border-radius: 2px; }
QProgressBar::chunk { background-color: @accent; border-radius: 2px; }

/* REPRODUCTOR */
QPushButton#PlayCircleBtn {
    background-color: @text; border-radius: 20px; border: none;
    min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px;
}
QPushButton#PlayCircleBtn:hover { background-color: @accent_hi; }
QPushButton#PlayCircleBtn:disabled { background-color: #3a3f34; }
QPushButton#BigPlayBtn {
    background-color: @accent; border-radius: 22px; border: none;
    min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px;
}
QPushButton#BigPlayBtn:hover { background-color: @accent_hover; }
QPushButton#BigPlayBtn:disabled { background-color: @accent_lo; }
QPushButton.PlayerIconBtn {
    background-color: transparent; border-radius: 17px; border: none;
    min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px;
}
QPushButton.PlayerIconBtn:hover { background-color: @elev; }

QSlider { background: transparent; }
QSlider::groove:horizontal { border-radius: 2px; height: 4px; background: #363c30; }
QSlider::sub-page:horizontal { background: @text; border-radius: 2px; }
QSlider::sub-page:horizontal:hover { background: @accent; }
QSlider::handle:horizontal {
    background: #ffffff; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px;
}
QSlider::sub-page:horizontal:disabled { background: #363c30; }
QSlider::handle:horizontal:disabled { background: transparent; }
"""


def build_qss() -> str:
    qss = _QSS_TEMPLATE
    for key in sorted(C, key=len, reverse=True):
        qss = qss.replace(f"@{key}", C[key])
    qss = qss.replace("__FONT__", UI_FONT)
    qss = qss.replace("__CHEVRON_R__", _ui_asset("chevron_r", "chevron_right", C["muted"], 14))
    qss = qss.replace("__CHEVRON__", _ui_asset("chevron", "chevron_down", C["muted"], 16))
    return qss
