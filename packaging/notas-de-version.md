## 📥 Cómo instalar (Linux)

**Ubuntu 22.04 o más nuevo, Linux Mint 21+, Pop!_OS, Debian 12, Kubuntu, Zorin…**

1. Descarga el archivo **`puquichu_…_amd64.deb`** que está más abajo, en *Assets*.
2. Haz **doble clic** en el archivo descargado: se abre el Centro de software.
3. Pulsa **Instalar** y escribe tu contraseña. Se instala solo lo necesario (ffmpeg).
4. Busca **Puquichu** en tu menú de aplicaciones. ¡Listo! 🌱

<details>
<summary>¿Prefieres la terminal?</summary>

```bash
sudo apt install ./puquichu_*_amd64.deb
```
Para desinstalar: `sudo apt remove puquichu` (tu música y tu biblioteca no se borran).
</details>

Tu música se guarda en **~/Música/Puquichu** y tu biblioteca en **~/.local/share/puquichu**.

> 🪟 Windows y 🍎 macOS: en preparación.

---

## ✨ Novedades de la 1.2

- 🔈 **1.2.1 — Selector de salida de audio** (botón de parlante en el reproductor): elige en qué parlante suena
  (laptop, Bluetooth…) y Puquichu lo recuerda. Si el parlante se desconecta, usa la salida del sistema y vuelve
  solo cuando se reconecta. *Si con la 1.2.0 no escuchabas nada, era porque sonaba en otra salida.*

- 🔊 **Nuevo motor de audio**: se acabó la pausa y el "trabado" al empezar o al adelantar, sobre todo con parlantes **Bluetooth**.
  Además empieza a sonar más rápido (≈0,3 s en canciones en línea).
- ▶️ **Reproducción continua arreglada**: sigue en orden la lista donde elegiste la canción (biblioteca, Escuchado recientemente,
  Top Perú, búsqueda, top del artista…) y ya no salta ni repite canciones al reordenarse la biblioteca.
- Si una canción falla durante la reproducción continua, pasa a la siguiente en vez de detenerse.
- Al abrir la app, la última canción retoma **directo en el segundo donde quedó**.
- 🔒 Seguridad: los títulos que llegan de internet se muestran siempre como texto; caché privada en `~/.cache/puquichu`;
  descargas con límite de tiempo y tamaño; base de datos más robusta.
- Ya no necesita VLC (instalador más simple; base para Windows y Mac).
- Se quitó el ecualizador (dependía de VLC); volverá más adelante.
