"""Puquichu — motor de audio basado en QtMultimedia (FFmpeg).

Reemplaza a VLC: VLC 3 corrige la sincronía audio/video y con parlantes Bluetooth
descarta audio y mete ~0,8 s de silencio al empezar o al adelantar. Un reproductor
de solo audio no necesita esa corrección; QtMultimedia reproduce limpio.

La interfaz imita la de python-vlc (play, pause, get_time, audio_set_volume…)
para que el resto de la app cambie lo mínimo.
"""
from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudio, QAudioOutput, QMediaDevices, QMediaPlayer


class AudioEngine(QObject):
    ended = pyqtSignal()         # la canción terminó sola
    failed = pyqtSignal(str)     # no se pudo abrir o reproducir

    def __init__(self, parent=None):
        super().__init__(parent)
        self._devices = QMediaDevices(self)
        self._output = QAudioOutput(QMediaDevices.defaultAudioOutput(), self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._output)
        self._pending_start = 0
        self._autoplay = False
        self._volume = 85
        self._player.mediaStatusChanged.connect(self._on_status)
        self._player.errorOccurred.connect(self._on_error)
        # Si el usuario cambia la salida del sistema (p. ej. conecta un parlante Bluetooth), seguirla
        self._devices.audioOutputsChanged.connect(self._follow_default_output)

    # ------------------------------------------------------------------ carga
    def load(self, source: str, start_ms: int = 0, autoplay: bool = True):
        """Carga un archivo local o una URL. Empieza directo en start_ms (sin sonar antes desde 0)."""
        url = QUrl(source) if source.startswith(("http://", "https://")) else QUrl.fromLocalFile(source)
        self._pending_start = max(0, int(start_ms))
        self._autoplay = autoplay
        self._player.setSource(url)
        if autoplay and not self._pending_start:
            self._player.play()

    def _on_status(self, status):
        Status = QMediaPlayer.MediaStatus
        if status in (Status.LoadedMedia, Status.BufferedMedia) and self._pending_start:
            start, self._pending_start = self._pending_start, 0
            if self._player.isSeekable():
                self._player.setPosition(start)
            if self._autoplay:
                self._player.play()
        elif status == Status.EndOfMedia:
            # Se avisa en el siguiente ciclo: cargar otra canción dentro de esta señal bloquea a Qt
            QTimer.singleShot(0, self.ended.emit)
        elif status == Status.InvalidMedia:
            msg = self._player.errorString() or "Formato de audio no válido"
            QTimer.singleShot(0, lambda: self.failed.emit(msg))

    def _on_error(self, _error, message: str):
        if message:
            QTimer.singleShot(0, lambda: self.failed.emit(message))

    def _follow_default_output(self):
        default = QMediaDevices.defaultAudioOutput()
        if not default.isNull() and default.id() != self._output.device().id():
            self._output.setDevice(default)

    # ---------------------------------------------------- interfaz tipo VLC
    def play(self):
        self._player.play()

    def pause(self):
        self._player.pause()

    def stop(self):
        self._pending_start = 0
        self._player.stop()

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
