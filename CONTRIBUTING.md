# Cómo colaborar con Puquichu 🌱

¡Gracias por querer ayudar! Estas son las pautas para que todo sea ordenado.

## Antes de empezar
1. Revisa los *issues* abiertos o crea uno contando qué quieres cambiar o qué error encontraste.
2. Para cambios grandes, conversa la idea en el *issue* antes de programar.

## Preparar el entorno
```bash
sudo apt install vlc ffmpeg libnotify-bin python3-venv
git clone <URL-de-tu-fork> puquichu && cd puquichu
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python3 app.py
```

## Flujo de trabajo
1. Haz un *fork* y crea una rama descriptiva: `git checkout -b mejora/listas-de-reproduccion`.
2. Haz commits pequeños con mensajes claros en español (qué cambia y por qué).
3. Prueba que la app arranque y que lo que cambiaste funcione.
4. Abre un *Pull Request* explicando el cambio; si es visual, agrega una captura.

## Reglas del proyecto
- Es una **app de escritorio**: no agregar servidores web ni dependencias de navegador.
- **No perder datos del usuario**: columnas nuevas en la base de datos solo con `ALTER TABLE` dentro de `init_and_migrate_db()` (`core.py`).
- **Diseño**: usar los colores de `C` en `theme.py` (nada de colores sueltos para el acento) e iconos dibujados en `draw_icon()`; no usar emojis en la interfaz.
- **Dónde va cada cosa**: lógica sin interfaz en `core.py`, diseño en `theme.py`, componentes en `widgets.py`, ventana en `app.py`.
- No subir música, bases de datos, `settings.json` ni el `venv/` (ya están en `.gitignore`).
- Textos de la interfaz en **español**.

## Probar la interfaz sin abrir ventana
```bash
QT_QPA_PLATFORM=offscreen venv/bin/python3 -c "
import sys; sys.path.insert(0, '.')
import app
from PyQt6.QtWidgets import QApplication
qa = QApplication(sys.argv); w = app.PuquichuApp(); w.resize(1340, 840); w.show()
qa.processEvents(); w.grab().save('captura.png')"
```

## Respeto
Trata a todos con amabilidad. Este es un proyecto hecho con cariño por la música y el campo andino.
