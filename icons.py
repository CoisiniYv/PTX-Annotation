"""图标工厂：集中创建应用与工具图标。"""
from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import (
    QPainter, QPixmap, QImage, QColor, QPen,
    QFont, QPainterPath, QRadialGradient, QIcon
)
import numpy as np


class IconFactory:
    @staticmethod
    def _base_icon(size=64):
        img = QImage(size, size, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        return img, p

    @staticmethod
    def create_app_icon():
        img, p = IconFactory._base_icon(128)
        size = 128
        cyan = QColor("#00f0ff")
        path = QPainterPath()
        center = QPoint(size // 2, size // 2)
        radius = size * 0.45
        path.addEllipse(center, radius, radius)
        pen = QPen(cyan, 4)
        p.setPen(pen)
        p.drawPath(path)
        p.setPen(QPen(QColor("#00f0ff"), 1))
        for i in range(10, size - 10, 15):
            p.drawLine(i, size // 2 - 20, i, size // 2 + 20)
        p.setBrush(QColor(0, 240, 255, 50))
        p.setPen(QPen(cyan, 2))
        center_rect = QRect(size // 2 - 20, size // 2 - 30, 40, 60)
        p.drawRoundedRect(center_rect, 10, 10)
        p.end()
        return QIcon(QPixmap.fromImage(img))

    @staticmethod
    def create_invert_icon():
        img, p = IconFactory._base_icon(64)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawEllipse(4, 4, 56, 56)
        p.setBrush(QColor("#ffffff"))
        p.drawPie(4, 4, 56, 56, 90 * 16, 180 * 16)
        p.end()
        return QIcon(QPixmap.fromImage(img))

    @staticmethod
    def create_tool_icon(text, color="#00f0ff", bg_shape="rect"):
        img, p = IconFactory._base_icon(64)
        size = 64
        c = QColor(color)
        p.setPen(QPen(c, 2))
        if bg_shape == "rect":
            p.drawRoundedRect(4, 4, size - 8, size - 8, 8, 8)
        elif bg_shape == "circle":
            p.drawEllipse(4, 4, size - 8, size - 8)
        grad = QRadialGradient(size // 2, size // 2, size // 2)
        grad.setColorAt(0, QColor(c.red(), c.green(), c.blue(), 50))
        grad.setColorAt(1, Qt.transparent)
        p.fillRect(0, 0, size, size, grad)
        p.setFont(QFont("Microsoft YaHei UI", 22, QFont.Bold))
        p.setPen(Qt.white)
        p.drawText(img.rect(), Qt.AlignCenter, text)
        p.end()
        return QIcon(QPixmap.fromImage(img))

    @staticmethod
    def create_lock_icon(locked=True):
        img, p = IconFactory._base_icon(64)
        color = QColor("#00f0ff") if locked else QColor("#888888")
        p.setPen(QPen(color, 3))
        p.drawRoundedRect(16, 26, 32, 24, 4, 4)
        if locked:
            p.drawArc(20, 10, 24, 30, 0, 180 * 16)
        else:
            p.drawArc(20, 10, 24, 30, 45 * 16, 135 * 16)
        p.setPen(QPen(color, 1))
        p.drawLine(32, 34, 32, 42)
        p.end()
        return QIcon(QPixmap.fromImage(img))

    @staticmethod
    def create_magnet_icon():
        img, p = IconFactory._base_icon(64)
        color = QColor("#ff00ff")
        p.setPen(QPen(color, 3))
        path = QPainterPath()
        path.moveTo(16, 16)
        path.lineTo(16, 40)
        path.arcTo(16, 24, 32, 32, 180, 180)
        path.lineTo(48, 16)
        p.drawPath(path)
        p.setPen(QPen(color, 1, Qt.DashLine))
        p.drawArc(10, 30, 44, 44, 200 * 16, 140 * 16)
        p.end()
        return QIcon(QPixmap.fromImage(img))

    @staticmethod
    def create_eye_icon():
        img, p = IconFactory._base_icon(64)
        color = QColor("#ffff00")
        p.setPen(QPen(color, 2))
        p.drawEllipse(10, 20, 44, 24)
        p.setBrush(QColor(color.red(), color.green(), color.blue(), 80))
        p.drawEllipse(26, 26, 12, 12)
        p.end()
        return QIcon(QPixmap.fromImage(img))

    @staticmethod
    def create_sun_icon():
        img, p = IconFactory._base_icon(64)
        color = QColor("#ffaa00")
        p.setPen(QPen(color, 2))
        p.setBrush(QColor(color.red(), color.green(), color.blue(), 100))
        p.drawEllipse(16, 16, 32, 32)
        center = QPoint(32, 32)
        for i in range(0, 360, 45):
            rad = np.radians(i)
            p1 = center + QPoint(int(20 * np.cos(rad)), int(20 * np.sin(rad)))
            p2 = center + QPoint(int(28 * np.cos(rad)), int(28 * np.sin(rad)))
            p.drawLine(p1, p2)
        p.end()
        return QIcon(QPixmap.fromImage(img))
