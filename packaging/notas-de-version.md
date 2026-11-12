## 📥 Cómo instalar (Linux)

**Ubuntu 22.04 o más nuevo, Linux Mint 21+, Pop!_OS, Debian 12, Kubuntu, Zorin…**

1. Descarga el archivo **`puquichu_…_amd64.deb`** que está más abajo, en *Assets*.
2. Haz **doble clic** en el archivo descargado: se abre el Centro de software.
3. Pulsa **Instalar** y escribe tu contraseña. Se instala solo lo necesario (VLC y ffmpeg).
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

## ✨ Novedades de la 1.1

- **Primer instalador para Linux** (.deb): ya no hace falta saber de Python ni de terminal.
- Página de cada canción con el **top real del artista**.
- La barra de progreso **salta a donde haces clic** y muestra el minuto.
- Arreglado: un doble clic ya no hace que la canción arranque dos veces.
- El motor de descargas se puede **actualizar desde Ajustes** sin reinstalar.
- Instalador probado en Ubuntu 22.04 y 24.04 (audio local y en línea en formato WebM/Opus).
