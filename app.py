"""程序入口：初始化应用并启动主窗口。"""
import sys
import os
import multiprocessing as mp
from PySide6.QtWidgets import QApplication, QStyleFactory
from PySide6.QtCore import QTimer
from main_window import MedicalLabelPro


def main():
    mp.freeze_support()
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    win = MedicalLabelPro()
    win.show()
    start_path = None
    for arg in sys.argv[1:]:
        if not arg or arg.startswith("-"):
            continue
        if os.path.isfile(arg):
            start_path = arg
            break
    if start_path:
        QTimer.singleShot(0, lambda p=start_path: win.load_quick_preview(p))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
