"""Application entry point."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from ezbooru.ui.main_window import MainWindow


def run() -> None:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    if getattr(sys, "frozen", False):
        icon_path = Path(sys._MEIPASS) / "assets" / "ezBooru.png"
    else:
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "ezBooru.png"
    app.setWindowIcon(QIcon(str(icon_path)))
    app.setApplicationName("ezBooru")
    app.setOrganizationName("ezBooru")
    app.setQuitOnLastWindowClosed(False)
    loop = QEventLoop(app)
    loop.set_default_executor(
        ThreadPoolExecutor(max_workers=4, thread_name_prefix="ezbooru")
    )
    asyncio.set_event_loop(loop)
    window = MainWindow()
    window.show()
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    run()
