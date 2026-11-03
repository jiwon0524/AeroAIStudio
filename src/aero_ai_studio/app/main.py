from __future__ import annotations
import argparse
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from aero_ai_studio.ui.window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="Aero AI Studio desktop")
    parser.add_argument("--workspace", type=Path, default=Path.cwd() / "workspace")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Aero AI Studio")
    window = MainWindow(args.workspace)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
