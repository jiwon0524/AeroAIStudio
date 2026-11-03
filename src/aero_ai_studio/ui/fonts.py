"""Qt offscreen on Windows may not discover system fonts automatically."""
import os
import sys
from pathlib import Path
from PySide6.QtGui import QFontDatabase


def ensure_fonts() -> None:
    if sys.platform == "win32" and not QFontDatabase.families():
        root = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for filename in ("segoeui.ttf", "consola.ttf", "malgun.ttf"):
            path = root / filename
            if path.exists():
                QFontDatabase.addApplicationFont(str(path))
