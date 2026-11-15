"""Puquichu — motor de audio basado en QtMultimedia (FFmpeg).

Reemplaza a VLC: VLC 3 corrige la sincronía audio/video y con parlantes Bluetooth
descarta audio y mete ~0,8 s de silencio al empezar o al adelantar. Un reproductor
de solo audio no necesita esa corrección; QtMultimedia reproduce limpio.

La interfaz imita la de python-vlc (play, pause, get_time, audio_set_volume…)
para que el resto de la app cambie lo mínimo.
"""
import os
import subprocess
import sys

if sys.platform.startswith("linux"):
    # El backend experimental PipeWire de Qt 6.10 marca el stream con node.dont-reconnect=true,
    # lo que impide mover la app de parlante desde el mezclador del sistema (KDE/GNOME).
    os.environ.setdefault("QT_AUDIO_BACKEND", "pulseaudio")

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudio, QAudioOutput, QMediaDevices, QMediaPlayer


class AudioEngine(QObject):
    ended = pyqtSignal()         # la canción terminó sola
    failed = pyqtSignal(str)     # no se pudo abrir o reproducir

    def __init__(self, parent=None, preferred_device: str = ""):
        super().__init__(parent)
        self._devices = QMediaDevices(self)
        self._preferred = preferred_device  # "" = seguir la salida del sistema
        self._output = QAudioOutput(self._pick_device(), self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._output)
        self._pending_start = 0
        self._autoplay = False
        self._volume = 85
        self._load_id = 0
        self._failed_id = -1
        self._last_pos = 0
        self._player.mediaStatusChanged.connect(self._on_status)
        self._player.errorOccurred.connect(self._on_error)
        self._player.positionChanged.connect(self._on_position)
        # Si el usuario cambia la salida del sistema (p. ej. conecta un parlante Bluetooth), seguirla
        self._devices.audioOutputsChanged.connect(self._follow_default_output)

    # ------------------------------------------------------------------ carga
    def load(self, source: str, start_ms: int = 0, autoplay: bool = True):
        """Carga un archivo local o una URL. Empieza directo en start_ms (sin sonar antes desde 0)."""
        self._load_id += 1
        self.sync_external_move()
        url = QUrl(source) if source.startswith(("http://", "https://")) else QUrl.fromLocalFile(source)
        self._pending_start = max(0, int(start_ms))
        self._last_pos = self._pending_start
        self._autoplay = autoplay
        self._player.setSource(url)
        if autoplay and not self._pending_start:
            self._player.play()

    def _on_position(self, pos: int):
        if pos > 0:
            self._last_pos = int(pos)

    def _emit_failed(self, lid: int, msg: str):
        if lid == self._load_id and self._failed_id != lid:
            self._failed_id = lid
            self.failed.emit(msg)

    def _on_status(self, status):
        Status = QMediaPlayer.MediaStatus
        lid = self._load_id
        if status in (Status.LoadedMedia, Status.BufferedMedia) and self._pending_start:
            start, self._pending_start = self._pending_start, 0
            if self._player.isSeekable():
                self._player.setPosition(start)
            if self._autoplay:
                self._player.play()
        elif status == Status.EndOfMedia:
            # Se avisa en el siguiente ciclo: cargar otra canción dentro de esta señal bloquea a Qt
            QTimer.singleShot(0, lambda: self.ended.emit() if lid == self._load_id else None)
        elif status == Status.InvalidMedia:
            msg = self._player.errorString() or "Formato de audio no válido"
            QTimer.singleShot(0, lambda: self._emit_failed(lid, msg))

    def _on_error(self, _error, message: str):
        if message:
            lid = self._load_id
            QTimer.singleShot(0, lambda: self._emit_failed(lid, message))

    # ---------------------------------------------------- salida de audio
    @staticmethod
    def device_id(device) -> str:
        return bytes(device.id()).decode("utf-8", "replace")

    @staticmethod
    def output_devices() -> list:
        return list(QMediaDevices.audioOutputs())

    def _pick_device(self):
        """El parlante elegido si está conectado; si no, la salida del sistema."""
        if self._preferred:
            for dev in QMediaDevices.audioOutputs():
                if self.device_id(dev) == self._preferred:
                    return dev
        return QMediaDevices.defaultAudioOutput()

    def set_preferred_device(self, device_id: str):
        self._preferred = device_id
        self._follow_default_output()

    def preferred_device(self) -> str:
        return self._preferred

    def current_device(self):
        return self._output.device()

    def preferred_available(self) -> bool:
        return not self._preferred or any(self.device_id(d) == self._preferred for d in QMediaDevices.audioOutputs())

    def _follow_default_output(self):
        """Al conectar/desconectar parlantes o cambiar la salida del sistema, se ajusta solo."""
        target = self._pick_device()
        if not target.isNull() and target.id() != self._output.device().id():
            self._output.setDevice(target)

    def sync_external_move(self):
        """Si el usuario movió Puquichu de parlante desde el mezclador del sistema, respetarlo."""
        if not sys.platform.startswith("linux") or not self.has_media():
            return
        sink = self._current_pulse_sink()
        if not sink or sink == self.device_id(self._output.device()):
            return
        for dev in QMediaDevices.audioOutputs():
            if self.device_id(dev) == sink:
                self._output.setDevice(dev)
                if self._preferred:
                    self._preferred = sink
                break

    @staticmethod
    def _current_pulse_sink() -> str:
        env = {**os.environ, "LC_ALL": "C"}
        try:
            si = subprocess.check_output(["pactl", "list", "sink-inputs"], env=env, text=True, timeout=0.4)
            pid_line = f'application.process.id = "{os.getpid()}"'
            sink_idx = None
            for block in si.split("Sink Input #")[1:]:
                if pid_line in block:
                    for line in block.splitlines():
                        line = line.strip()
                        if line.startswith("Sink:"):
                            sink_idx = line.split(":", 1)[1].strip()
                            break
            if not sink_idx:
                return ""
            sinks = subprocess.check_output(["pactl", "list", "sinks", "short"], env=env, text=True, timeout=0.4)
            for line in sinks.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2 and parts[0].strip() == sink_idx:
                    return parts[1].strip()
        except Exception:
            pass
        return ""

    # ---------------------------------------------------- interfaz tipo VLC
    def play(self):
        self._player.play()

    def pause(self):
        self._player.pause()

    def stop(self):
        self._load_id += 1
        self._pending_start = 0
        self._last_pos = 0
        self._player.stop()

    def is_remote(self) -> bool:
        return self._player.source().scheme() in ("http", "https")

    def last_position(self) -> int:
        return max(int(self._player.position()), self._last_pos)

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def is_ended(self) -> bool:
        return self._player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia

    def has_media(self) -> bool:
        return not self._player.source().isEmpty()

    def get_time(self) -> int:
        return int(self._player.position())

    def get_length(self) -> int:
        return int(self._player.duration())

    def set_time(self, ms: int):
        self._player.setPosition(max(0, int(ms)))

    def set_position(self, fraction: float):
        length = self._player.duration()
        if length > 0:
            self._player.setPosition(int(max(0.0, min(1.0, fraction)) * length))

    def audio_set_volume(self, volume: int):
        """Volumen 0-100 con curva perceptual (como un control de volumen real)."""
        self._volume = max(0, min(100, int(volume)))
        linear = QAudio.convertVolume(
            self._volume / 100.0, QAudio.VolumeScale.LogarithmicVolumeScale, QAudio.VolumeScale.LinearVolumeScale
        )
        self._output.setVolume(linear)

    def audio_get_volume(self) -> int:
        return self._volume

    def audio_set_mute(self, muted: bool):
        self._output.setMuted(bool(muted))
