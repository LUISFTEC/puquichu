"""Puquichu — integración MPRIS2 por D-Bus.

Permite controlar Puquichu desde el control multimedia del panel de KDE/GNOME,
la pantalla de bloqueo y las teclas multimedia del teclado (▶ ⏭ ⏮), aunque la
ventana no tenga el foco.
"""
from pathlib import Path

from PyQt6.QtCore import QMetaType, QObject, pyqtClassInfo, pyqtProperty, pyqtSlot
from PyQt6.QtDBus import (
    QDBusAbstractAdaptor,
    QDBusArgument,
    QDBusConnection,
    QDBusMessage,
    QDBusObjectPath,
)

from core import APP_ID, APP_NAME

OBJECT_PATH = "/org/mpris/MediaPlayer2"
ROOT_IFACE = "org.mpris.MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"


def _strlist(items) -> QDBusArgument:
    arg = QDBusArgument()
    arg.add([str(i) for i in items], QMetaType.Type.QStringList.value)
    return arg


def _int64(value: int) -> QDBusArgument:
    return QDBusArgument(int(value), QMetaType.Type.LongLong.value)


@pyqtClassInfo("D-Bus Interface", ROOT_IFACE)
class _RootAdaptor(QDBusAbstractAdaptor):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app

    @pyqtProperty(str)
    def Identity(self):
        return APP_NAME

    @pyqtProperty(str)
    def DesktopEntry(self):
        return APP_ID

    @pyqtProperty(bool)
    def CanQuit(self):
        return True

    @pyqtProperty(bool)
    def CanRaise(self):
        return True

    @pyqtProperty(bool)
    def HasTrackList(self):
        return False

    @pyqtProperty("QStringList")
    def SupportedUriSchemes(self):
        return ["file"]

    @pyqtProperty("QStringList")
    def SupportedMimeTypes(self):
        return ["audio/mpeg", "audio/mp4", "audio/ogg", "audio/flac", "audio/webm"]

    @pyqtSlot()
    def Raise(self):
        self.app.mpris_raise()

    @pyqtSlot()
    def Quit(self):
        self.app.close()


@pyqtClassInfo("D-Bus Interface", PLAYER_IFACE)
class _PlayerAdaptor(QDBusAbstractAdaptor):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app

    # --- Métodos ---
    @pyqtSlot()
    def PlayPause(self):
        self.app.toggle_play_pause()

    @pyqtSlot()
    def Play(self):
        if not self.app.player.is_playing():
            self.app.toggle_play_pause()

    @pyqtSlot()
    def Pause(self):
        if self.app.player.is_playing():
            self.app.toggle_play_pause()

    @pyqtSlot()
    def Stop(self):
        if self.app.player.is_playing():
            self.app.toggle_play_pause()

    @pyqtSlot()
    def Next(self):
        self.app.play_next_song()

    @pyqtSlot()
    def Previous(self):
        self.app.play_previous_song()

    @pyqtSlot("qlonglong")
    def Seek(self, offset_us):
        self.app.seek_relative_ms(int(offset_us) // 1000)

    @pyqtSlot(QDBusObjectPath, "qlonglong")
    def SetPosition(self, _track, position_us):
        if self.app.current_song:
            self.app.player.set_time(max(0, int(position_us) // 1000))

    @pyqtSlot(str)
    def OpenUri(self, _uri):
        pass

    # --- Propiedades ---
    @pyqtProperty(str)
    def PlaybackStatus(self):
        return self.app.mpris_status()

    @pyqtProperty(str)
    def LoopStatus(self):
        return "Track" if self.app.loop_enabled else "None"

    @pyqtProperty(bool)
    def Shuffle(self):
        return bool(self.app.shuffle_enabled)

    @pyqtProperty("QVariantMap")
    def Metadata(self):
        return self.app.mpris_metadata()

    @pyqtProperty(float)
    def Volume(self):
        return self.app.vol_slider.value() / 100.0

    @pyqtProperty("qlonglong")
    def Position(self):
        return max(0, self.app.player.get_time()) * 1000 if self.app.current_song else 0

    @pyqtProperty(float)
    def Rate(self):
        return 1.0

    @pyqtProperty(float)
    def MinimumRate(self):
        return 1.0

    @pyqtProperty(float)
    def MaximumRate(self):
        return 1.0

    @pyqtProperty(bool)
    def CanGoNext(self):
        return True

    @pyqtProperty(bool)
    def CanGoPrevious(self):
        return True

    @pyqtProperty(bool)
    def CanPlay(self):
        return self.app.current_song is not None

    @pyqtProperty(bool)
    def CanPause(self):
        return self.app.current_song is not None

    @pyqtProperty(bool)
    def CanSeek(self):
        return self.app.current_song is not None

    @pyqtProperty(bool)
    def CanControl(self):
        return True


class MprisService(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._root = _RootAdaptor(self, app)
        self._player = _PlayerAdaptor(self, app)
        self.bus = QDBusConnection.sessionBus()
        self.ok = (
            self.bus.isConnected()
            and self.bus.registerObject(OBJECT_PATH, self)
            and self.bus.registerService(f"org.mpris.MediaPlayer2.{APP_ID}")
        )

    def notify(self, *names: str):
        """Avisa al escritorio de que cambiaron propiedades del reproductor."""
        if not self.ok:
            return
        getters = {
            "PlaybackStatus": self.app.mpris_status,
            "Metadata": self.app.mpris_metadata,
            "LoopStatus": lambda: "Track" if self.app.loop_enabled else "None",
            "Shuffle": lambda: bool(self.app.shuffle_enabled),
            "Volume": lambda: self.app.vol_slider.value() / 100.0,
            "CanPlay": lambda: self.app.current_song is not None,
            "CanPause": lambda: self.app.current_song is not None,
            "CanSeek": lambda: self.app.current_song is not None,
        }
        changed = {n: getters[n]() for n in names if n in getters}
        msg = QDBusMessage.createSignal(OBJECT_PATH, "org.freedesktop.DBus.Properties", "PropertiesChanged")
        msg.setArguments([PLAYER_IFACE, changed, _strlist([])])
        self.bus.send(msg)

    def seeked(self, position_ms: int):
        if not self.ok:
            return
        msg = QDBusMessage.createSignal(OBJECT_PATH, PLAYER_IFACE, "Seeked")
        msg.setArguments([_int64(position_ms * 1000)])
        self.bus.send(msg)


def build_metadata(song: dict | None, length_ms: int, art_path: str = "") -> dict:
    if not song:
        return {"mpris:trackid": QDBusObjectPath("/org/mpris/MediaPlayer2/TrackList/NoTrack")}
    from theme import display_title

    meta = {
        "mpris:trackid": QDBusObjectPath(
            f"/org/{APP_ID}/track/{int(song['id'])}"
            if song.get("id")
            else f"/org/{APP_ID}/stream/" + "".join(ch if ch.isalnum() else "_" for ch in str(song.get("source_id") or "x"))
        ),
        "xesam:title": display_title(song["title"], song.get("artist", "")),
        "xesam:artist": _strlist([song.get("artist") or "Artista desconocido"]),
        "xesam:album": song.get("genre") or "",
        "xesam:genre": _strlist([song.get("genre") or "Otros"]),
        "xesam:useCount": int(song.get("play_count") or 0),
    }
    length = length_ms if length_ms > 0 else int(song.get("duration") or 0) * 1000
    if length > 0:
        meta["mpris:length"] = _int64(length * 1000)
    if art_path and Path(art_path).exists():
        meta["mpris:artUrl"] = Path(art_path).resolve().as_uri()
    if song.get("file_path"):
        meta["xesam:url"] = Path(song["file_path"]).as_uri()
    return meta
