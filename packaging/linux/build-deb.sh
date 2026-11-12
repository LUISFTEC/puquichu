#!/usr/bin/env bash
# Arma el instalador .deb de Puquichu (Ubuntu, Linux Mint, Debian, Pop!_OS…).
# Uso (desde la raíz del proyecto):  PYTHON=venv/bin/python packaging/linux/build-deb.sh
# Requiere: pip install -r requirements.txt pyinstaller   y   dpkg-deb
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' core.py)"
ARCH="$(dpkg --print-architecture)"
PKG="build/deb/puquichu_${VERSION}_${ARCH}"

echo "==> Empaquetando Puquichu ${VERSION} (${ARCH}) con PyInstaller"
"$PYTHON" -m PyInstaller --noconfirm --clean \
    --distpath build/dist --workpath build/work packaging/puquichu.spec

echo "==> Armando la estructura del paquete"
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/opt/puquichu" "$PKG/usr/bin" \
         "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/256x256/apps" \
         "$PKG/usr/share/doc/puquichu"
cp -a build/dist/puquichu/. "$PKG/opt/puquichu/"
ln -s /opt/puquichu/puquichu "$PKG/usr/bin/puquichu"
cp packaging/linux/puquichu.desktop "$PKG/usr/share/applications/puquichu.desktop"
cp assets/puquichu.png "$PKG/usr/share/icons/hicolor/256x256/apps/puquichu.png"
cp LICENSE "$PKG/usr/share/doc/puquichu/copyright"

INSTALLED_KB="$(du -sk "$PKG" | cut -f1)"
cat > "$PKG/DEBIAN/control" <<EOF
Package: puquichu
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: ${ARCH}
Maintainer: LUISFTEC <74120641+LUISFTEC@users.noreply.github.com>
Installed-Size: ${INSTALLED_KB}
Depends: vlc, ffmpeg, libxcb-cursor0, libxkbcommon-x11-0, libegl1, libfontconfig1, libdbus-1-3
Recommends: libnotify-bin, xdg-user-dirs
Homepage: https://github.com/LUISFTEC/-puquichu
Description: Reproductor de música de escritorio con los colores de la sierra
 Busca una canción, suena al instante y queda guardada en tu equipo para
 escucharla sin internet, en la mejor calidad disponible. Incluye Top Perú,
 Top mundial, lo más escuchado por género, favoritas, cola, ecualizador,
 temporizador y control desde el panel del escritorio (MPRIS).
EOF

cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
exit 0
EOF
cp "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm"
chmod 755 "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm"

echo "==> Construyendo el .deb"
dpkg-deb --build --root-owner-group "$PKG" "build/puquichu_${VERSION}_${ARCH}.deb"
ls -lh "build/puquichu_${VERSION}_${ARCH}.deb"
