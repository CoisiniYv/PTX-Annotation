"""PTX Annotation 程序入口。"""

from __future__ import annotations

import multiprocessing as mp
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QStyleFactory

from app_config import (
    APP_NAME,
    APP_VERSION,
    QT_SETTINGS_ORGANIZATION,
)
from main_window import MedicalLabelPro


def _first_input_file(argv: list[str]) -> str | None:
    """从命令行参数中找到第一个存在的文件，供快速预览使用。"""

    for arg in argv:
        if not arg or arg.startswith("-"):
            continue
        path = os.path.abspath(os.path.expanduser(arg))
        if os.path.isfile(path):
            return path
    return None


def create_application(argv: list[str]) -> QApplication:
    """创建并配置 QApplication。"""

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(QT_SETTINGS_ORGANIZATION)

    fusion = QStyleFactory.create("Fusion")
    if fusion is not None:
        app.setStyle(fusion)
    return app


def main() -> int:
    mp.freeze_support()

    app = create_application(sys.argv)
    win = MedicalLabelPro()
    win.show()

    start_path = _first_input_file(sys.argv[1:])
    if start_path:
        QTimer.singleShot(0, lambda p=start_path: win.load_quick_preview(p))

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
