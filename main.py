#!/usr/bin/env python3
"""Log-Viewer – interaktive Analyse von Rundfahrgeschäft-Logfiles."""
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from config import APP_ICON_PATH
from data.store import DataStore
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Log-Viewer")
    if APP_ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    store = DataStore()
    window = MainWindow(store)
    window.show()
    code = app.exec()
    store.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
