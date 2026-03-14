import os
import sys
import re
from dataclasses import dataclass
from enum import Enum, auto
import numpy as np
import cv2

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QSplitter, QToolBar, QLabel, QSlider,
    QCheckBox, QMessageBox, QComboBox, QSizePolicy, QGroupBox,
    QSpinBox, QStyleFactory, QAbstractItemView, 
    QToolButton
)
from PySide6.QtCore import Qt, QPoint, QRect, QSize, Signal,QTimer
from PySide6.QtGui import (
    QAction, QPainter, QPixmap, QImage, QColor, QKeySequence, 
    QShortcut, QActionGroup, QIcon, QPen, 
    QFont, QPainterPath, QRadialGradient
)

# ==========================================
# 0. Icon Generator (程序化生成图标 - 增强版)
# ==========================================
class IconFactory:
    """
    程序化生成高科技风格图标，无需外部素材文件。
    """
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
        
        # 配色
        cyan = QColor("#00f0ff")
        
        # 1. 外层六边形/圆环
        path = QPainterPath()
        center = QPoint(size//2, size//2)
        radius = size * 0.45
        path.addEllipse(center, radius, radius)
        
        pen = QPen(cyan, 4)
        p.setPen(pen)
        p.drawPath(path)
        
        # 2. 科技感扫描线
        p.setPen(QPen(QColor("#00f0ff"), 1))
        for i in range(10, size-10, 15):
            p.drawLine(i, size//2 - 20, i, size//2 + 20)
            
        # 3. 中间抽象形状
        p.setBrush(QColor(0, 240, 255, 50)) 
        p.setPen(QPen(cyan, 2))
        center_rect = QRect(size//2 - 20, size//2 - 30, 40, 60)
        p.drawRoundedRect(center_rect, 10, 10)
        
        p.end()
        return QIcon(QPixmap.fromImage(img))

    @staticmethod
    def create_tool_icon(text, color="#00f0ff", bg_shape="rect"):
        img, p = IconFactory._base_icon(64)
        size = 64
        
        c = QColor(color)
        p.setPen(QPen(c, 2))
        
        if bg_shape == "rect":
            p.drawRoundedRect(4, 4, size-8, size-8, 8, 8)
        elif bg_shape == "circle":
            p.drawEllipse(4, 4, size-8, size-8)
            
        # 内部发光感
        grad = QRadialGradient(size//2, size//2, size//2)
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
        
        # 锁体
        p.drawRoundedRect(16, 26, 32, 24, 4, 4)
        # 锁梁
        if locked:
            p.drawArc(20, 10, 24, 30, 0, 180*16)
        else:
            p.drawArc(20, 10, 24, 30, 45*16, 135*16)
            
        # 芯片纹路
        p.setPen(QPen(color, 1))
        p.drawLine(32, 34, 32, 42)
        p.drawLine(24, 38, 40, 38)
        
        p.end()
        return QIcon(QPixmap.fromImage(img))

    @staticmethod
    def create_magnet_icon():
        img, p = IconFactory._base_icon(64)
        color = QColor("#ff00ff")
        p.setPen(QPen(color, 3))
        
        # 马蹄磁铁 U形
        path = QPainterPath()
        path.moveTo(16, 16)
        path.lineTo(16, 40)
        path.arcTo(16, 24, 32, 32, 180, 180)
        path.lineTo(48, 16)
        p.drawPath(path)
        
        # 磁力线
        p.setPen(QPen(color, 1, Qt.DashLine))
        p.drawArc(10, 30, 44, 44, 200*16, 140*16)
        
        p.end()
        return QIcon(QPixmap.fromImage(img))
    
    @staticmethod
    def create_eye_icon():
        img, p = IconFactory._base_icon(64)
        color = QColor("#ffff00")
        p.setPen(QPen(color, 2))
        
        # 眼睛轮廓
        p.drawEllipse(10, 20, 44, 24)
        # 瞳孔
        p.setBrush(QColor(color.red(), color.green(), color.blue(), 80))
        p.drawEllipse(26, 26, 12, 12)
        
        p.end()
        return QIcon(QPixmap.fromImage(img))

# ==========================================
# 1. Utils & Helpers
# ==========================================

@dataclass
class ImageEntry:
    filename: str
    orig_path: str
    mask_path: str | None
    has_mask: bool

class ToolType(Enum):
    ERASER = auto()
    BRUSH = auto()
    POLYGON = auto()

def imread_unicode(path: str, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size == 0: return None
        return cv2.imdecode(data, flags)
    except Exception: return None

def imwrite_unicode(path: str, img: np.ndarray) -> bool:
    try:
        ext = os.path.splitext(path)[1]
        if not ext: ext = ".png"
        ok, buf = cv2.imencode(ext, img)
        if not ok: return False
        buf.tofile(path)
        return True
    except Exception: return False

def natural_sort_key(s: str):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def apply_tech_theme(app):

    bg_color = "#1e1e2e"
    panel_color = "#252535"
    text_color = "#e0e0e0"
    accent_color = "#00f0ff" # 赛博青
    border_color = "#3e3e4e"
    
    style_sheet = f"""
    QMainWindow {{ background-color: {bg_color}; }}
    QWidget {{ color: {text_color}; font-family: "Microsoft YaHei UI", "Segoe UI", "SimHei"; font-size: 10pt; }}
    
    /* --- 工具栏 --- */
    QToolBar {{
        background-color: {panel_color};
        border-bottom: 2px solid {accent_color};
        spacing: 8px;
        padding: 4px;
    }}
    QToolButton {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 4px;
        padding: 4px;
        color: {text_color};
    }}
    QToolButton:hover {{
        background-color: rgba(0, 240, 255, 30);
        border: 1px solid {accent_color};
    }}
    QToolButton:checked {{
        background-color: rgba(0, 240, 255, 60);
        border: 1px solid {accent_color};
        color: #fff;
    }}

    /* --- 停靠窗口 --- */
    QDockWidget::title {{
        background: {panel_color};
        padding: 6px;
        border-left: 4px solid {accent_color};
        font-weight: bold;
    }}
    QWidget#DockContent {{ background-color: {panel_color}; }}

    /* --- 列表与缩略图 --- */
    QListWidget {{
        background-color: #181825;
        border: 1px solid {border_color};
        border-radius: 4px;
    }}
    QListWidget::item:selected {{
        background-color: rgba(0, 240, 255, 40);
        border: 1px solid {accent_color};
    }}

    /* --- 胶片缩略图条 (底部) --- */
    QListWidget#ThumbnailStrip {{
        background-color: #121212;
        border-top: 2px solid {accent_color};
        padding: 5px;
    }}
    QListWidget#ThumbnailStrip::item {{
        border: 1px solid #333;
        margin-right: 2px;
        background-color: #000;
    }}
    QListWidget#ThumbnailStrip::item:selected {{
        border: 2px solid {accent_color};
        background-color: #222;
    }}

    /* --- 进度条滑块 --- */
    QSlider::groove:horizontal {{
        border: 1px solid {border_color};
        height: 4px;
        background: #181825;
        margin: 2px 0;
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {accent_color};
        width: 14px;
        height: 14px;
        margin: -5px 0;
        border-radius: 7px;
    }}
    
    /* --- 顶栏控件微调 --- */
    QComboBox {{
        background-color: #333;
        border: 1px solid #555;
        border-radius: 3px;
        padding: 3px;
        min-width: 80px;
    }}
    QSpinBox {{
        background-color: #333;
        border: 1px solid #555;
        border-radius: 3px;
        padding: 3px;
    }}
    QLabel#ToolLabel {{
        color: {accent_color};
        font-weight: bold;
    }}
    
    QSplitter::handle {{
        background-color: {border_color};
    }}
    """
    app.setStyleSheet(style_sheet)

# ==========================================
# 2. Custom Painting Canvas
# ==========================================

class Canvas(QWidget):
    request_next = Signal()
    request_prev = Signal()
    zoom_changed = Signal(float)
    cursor_info_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        
        self.base_img: np.ndarray | None = None
        self.base_gray: np.ndarray | None = None
        self.mask: np.ndarray | None = None
        
        self.zoom = 1.0
        self.offset = QPoint(0, 0)
        self.overlay_color = (255, 50, 50) 
        self.overlay_alpha = 100
        self.display_threshold = 127
        self.fit_margin = 0.95
        
        self._tool = ToolType.BRUSH
        self.brush_size = 20
        self.brush_shape = 'circle'
        
        self.smart_lock_enabled = False
        self.smart_lock_mode = 'dark'
        self.smart_threshold = 60
        self.edge_snap_enabled = False
        self.edge_snap_radius = 10
        
        self._is_drawing = False
        self._pan_active = False
        self._last_mouse_pos = QPoint()
        self._mouse_img_pos = (-1, -1)
        
        self.undo_stack = []
        self.redo_stack = []
        self.polygon_points = []
        
        self.grid_alpha = 0
        self.grid_timer = QTimer(self)
        self.grid_timer.timeout.connect(self._animate_grid)
        self.grid_timer.start(50)
        self.grid_direction = 1

    @property
    def tool(self) -> ToolType: return self._tool

    @tool.setter
    def tool(self, value: ToolType):
        if self._tool != value:
            self._tool = value
            self._update_cursor()
            self.update()

    def _update_cursor(self):
        if self.base_img is None:
            self.setCursor(Qt.ArrowCursor)
            return
        if self._tool == ToolType.POLYGON:
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.BlankCursor)

    def _animate_grid(self):
        self.grid_alpha += self.grid_direction * 2
        if self.grid_alpha >= 40: self.grid_direction = -1
        if self.grid_alpha <= 10: self.grid_direction = 1
        self.update()

    def fit_view(self):
        if self.base_img is None: return
        h, w = self.base_img.shape[:2]
        canvas_w = self.width()
        canvas_h = self.height()
        if canvas_w == 0 or canvas_h == 0: return
        scale_w = canvas_w / w
        scale_h = canvas_h / h
        self.zoom = min(scale_w, scale_h) * self.fit_margin
        
        disp_w, disp_h = w * self.zoom, h * self.zoom
        off_x = (canvas_w - disp_w) / 2
        off_y = (canvas_h - disp_h) / 2
        self.offset = QPoint(int(off_x), int(off_y))
        self.zoom_changed.emit(self.zoom)
        self.update()

    def load_image(self, img_bgr: np.ndarray, mask: np.ndarray | None, preserve_view: bool = False):
        if img_bgr is None: return
        if len(img_bgr.shape) == 2 or (len(img_bgr.shape) == 3 and img_bgr.shape[2] == 1):
            img_bgr = cv2.cvtColor(img_bgr, cv2.COLOR_GRAY2BGR)
        self.base_img = img_bgr
        self.base_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        if mask is None:
            self.mask = np.zeros(img_bgr.shape[:2], dtype=np.uint8)
        else:
            self.mask = mask.copy()
            
        self.undo_stack.clear(); self.redo_stack.clear(); self.polygon_points.clear()
        if preserve_view:
            self._update_cursor()
            self.zoom_changed.emit(self.zoom)
            self.update()
        else:
            QTimer.singleShot(0, self.fit_view)
            self._update_cursor()
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.base_img is not None: self.fit_view()

    def _push_undo(self):
        if self.mask is not None:
            self.undo_stack.append(self.mask.copy())
            if len(self.undo_stack) > 20: self.undo_stack.pop(0)
            self.redo_stack.clear()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.mask.copy())
            self.mask = self.undo_stack.pop()
            self.update()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.mask.copy())
            self.mask = self.redo_stack.pop()
            self.update()

    def view_to_img(self, pos: QPoint) -> tuple[int, int]:
        x = int((pos.x() - self.offset.x()) / self.zoom)
        y = int((pos.y() - self.offset.y()) / self.zoom)
        return x, y

    def _snap_pos(self, x, y, r):
        if self.base_gray is None: return x, y
        h, w = self.base_gray.shape
        x0, y0 = max(0, x - r), max(0, y - r)
        x1, y1 = min(w, x + r + 1), min(h, y + r + 1)
        roi = self.base_gray[y0:y1, x0:x1]
        if roi.size == 0: return x, y
        gx = cv2.Sobel(roi, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(roi, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(mag)
        if max_val < 30: return x, y
        return x0 + max_loc[0], y0 + max_loc[1]

    def _apply_brush(self, x: int, y: int):
        if self.mask is None or self.base_gray is None: return
        h, w = self.mask.shape
        r = self.brush_size // 2
        if self.edge_snap_enabled: x, y = self._snap_pos(x, y, self.edge_snap_radius)
        x0, y0 = max(0, x - r), max(0, y - r)
        x1, y1 = min(w, x + r + 1), min(h, y + r + 1)
        if x0 >= x1 or y0 >= y1: return
        roi_mask = self.mask[y0:y1, x0:x1]
        roi_gray = self.base_gray[y0:y1, x0:x1]
        
        if self.brush_shape == 'circle':
            Y, X = np.ogrid[y0:y1, x0:x1]
            brush_area = ((X - x)**2 + (Y - y)**2) <= r**2
        else:
            brush_area = np.ones_like(roi_mask, dtype=bool)
            
        valid_area = brush_area
        if self.smart_lock_enabled:
            intensity_mask = roi_gray < self.smart_threshold if self.smart_lock_mode == 'dark' else roi_gray > self.smart_threshold
            valid_area = brush_area & intensity_mask
            
        value = 255 if self.tool == ToolType.BRUSH else 0
        roi_mask[valid_area] = value

    def _close_polygon(self):
        if not self.polygon_points or self.mask is None: return
        pts = np.array([[p.x(), p.y()] for p in self.polygon_points], dtype=np.int32)
        self._push_undo()
        cv2.fillPoly(self.mask, [pts], 255)
        self.polygon_points.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        
        # 网格背景
        painter.setPen(QPen(QColor(0, 240, 255, self.grid_alpha), 1))
        for x in range(0, self.width(), 40): painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 40): painter.drawLine(0, y, self.width(), y)

        if self.base_img is None:
            painter.setPen(QPen(QColor("#00f0ff"), 2))
            painter.setFont(QFont("Microsoft YaHei UI", 16))
            painter.drawText(self.rect(), Qt.AlignCenter, "等待数据加载...")
            self.setCursor(Qt.ArrowCursor) 
            return

        h, w = self.base_img.shape[:2]
        img_rgb = cv2.cvtColor(self.base_img, cv2.COLOR_BGR2RGB)
        qimg = QImage(img_rgb.data, w, h, w * 3, QImage.Format_RGB888)
        
        painter.save()
        painter.translate(self.offset)
        painter.scale(self.zoom, self.zoom)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        painter.drawImage(0, 0, qimg)

        if self.mask is not None:
            bin_mask = (self.mask >= self.display_threshold).astype(np.uint8)
            overlay_rgba = np.zeros((h, w, 4), dtype=np.uint8)
            r, g, b = self.overlay_color
            overlay_rgba[..., 0] = r; overlay_rgba[..., 1] = g; overlay_rgba[..., 2] = b
            overlay_rgba[..., 3] = bin_mask * self.overlay_alpha
            qoverlay = QImage(overlay_rgba.data, w, h, w * 4, QImage.Format_RGBA8888)
            painter.drawImage(0, 0, qoverlay)

        if self.tool == ToolType.POLYGON and self.polygon_points:
            painter.setPen(QPen(Qt.green, 2 / self.zoom))
            for i in range(1, len(self.polygon_points)):
                painter.drawLine(self.polygon_points[i-1], self.polygon_points[i])
            if self._mouse_img_pos:
                mx, my = self._mouse_img_pos
                painter.setPen(QPen(Qt.yellow, 1 / self.zoom, Qt.DashLine))
                painter.drawLine(self.polygon_points[-1], QPoint(mx, my))

        if self.tool in (ToolType.BRUSH, ToolType.ERASER) and not self._pan_active:
            mx, my = self._mouse_img_pos
            if 0 <= mx < w and 0 <= my < h:
                color = Qt.cyan if self.tool == ToolType.BRUSH else Qt.magenta
                painter.setPen(QPen(color, 1.5 / self.zoom))
                painter.setBrush(Qt.NoBrush)
                r_size = self.brush_size / 2
                painter.drawEllipse(QPoint(mx, my), r_size, r_size)
                
        painter.restore()

    def mousePressEvent(self, event):
        if self.base_img is None: return
        pos = event.position().toPoint()
        img_x, img_y = self.view_to_img(pos)
        if event.button() == Qt.RightButton:
            if self.tool == ToolType.POLYGON: self._close_polygon()
            else:
                self._pan_active = True
                self._last_mouse_pos = pos
                self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() == Qt.LeftButton:
            if self.tool in (ToolType.BRUSH, ToolType.ERASER):
                self._is_drawing = True
                self._push_undo()
                self._apply_brush(img_x, img_y)
                self.update()
            elif self.tool == ToolType.POLYGON:
                self.polygon_points.append(QPoint(img_x, img_y))
                self.update()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        img_x, img_y = self.view_to_img(pos)
        self._mouse_img_pos = (img_x, img_y)
        
        val_str = "N/A"
        if self.base_gray is not None and 0 <= img_x < self.base_gray.shape[1] and 0 <= img_y < self.base_gray.shape[0]:
            val = self.base_gray[img_y, img_x]
            val_str = f"{val:03d}"
        
        self.cursor_info_changed.emit(f"POS: [{img_x:04d}, {img_y:04d}] | VAL: {val_str}")

        if self._pan_active:
            delta = pos - self._last_mouse_pos
            self.offset += delta
            self._last_mouse_pos = pos
            self.update()
            return

        if self._is_drawing and self.tool in (ToolType.BRUSH, ToolType.ERASER):
            self._apply_brush(img_x, img_y)
            self.update()
        else:
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton: self._is_drawing = False
        if event.button() == Qt.RightButton:
            self._pan_active = False
            self._update_cursor()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        modifiers = event.modifiers()
        if modifiers & Qt.ControlModifier:
            scale_factor = 1.1 if delta > 0 else 0.9
            old_zoom = self.zoom
            new_zoom = self.zoom * scale_factor
            self.zoom = max(0.1, min(new_zoom, 20.0))
            pos = event.position().toPoint()
            img_x = (pos.x() - self.offset.x()) / old_zoom
            img_y = (pos.y() - self.offset.y()) / old_zoom
            new_off_x = pos.x() - img_x * self.zoom
            new_off_y = pos.y() - img_y * self.zoom
            self.offset = QPoint(int(new_off_x), int(new_off_y))
            self.zoom_changed.emit(self.zoom)
            self.update()
        else:
            step = 2 if self.brush_size < 30 else 5
            if delta > 0: self.brush_size += step
            else: self.brush_size = max(1, self.brush_size - step)
            self.update()

# ==========================================
# 3. Main Window (Layout Revised)
# ==========================================

class MaskCorrectorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CT气胸智能标注终端")
        self.resize(1600, 1000)
        self.setWindowIcon(IconFactory.create_app_icon())
        
        self.entries: list[ImageEntry] = []
        self.current_idx = -1
        self.orig_root = ""
        self.mask_root = ""
        self.autosave_enabled = True
        
        apply_tech_theme(QApplication.instance())
        
        self.canvas = Canvas() # Init canvas early
        self.canvas.cursor_info_changed.connect(lambda s: self.status_label.setText(s))
        self.canvas.zoom_changed.connect(lambda z: self.statusBar().showMessage(f"缩放: {z:.2f}X", 2000))
        
        self._init_ui()
        self._init_toolbar() # Now includes right panel params
        self._init_shortcuts()
        
        self.status_label = QLabel("系统就绪")
        self.status_label.setStyleSheet("color: #00f0ff; font-weight: bold; padding-right: 20px;")
        self.statusBar().addPermanentWidget(self.status_label)

    def _init_ui(self):
        # 核心布局：左侧资源栏 + 右侧主工作区 (Splitter)
        main_splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(main_splitter)
        
        # --- 1. 左侧资源栏 (简化) ---
        files_widget = QWidget()
        files_layout = QVBoxLayout(files_widget)
        files_layout.setContentsMargins(5, 5, 5, 5)
        
        self.list_patients_annotated = QListWidget()
        self.list_patients_no_mask = QListWidget()
        
        def create_group(title, widget):
            grp = QGroupBox(title)
            l = QVBoxLayout(grp)
            l.setContentsMargins(5,15,5,5)
            l.addWidget(widget)
            return grp

        files_layout.addWidget(create_group("已标注患者", self.list_patients_annotated))
        files_layout.addWidget(create_group("待标注患者", self.list_patients_no_mask))
        
        self.list_patients_annotated.itemClicked.connect(self.load_patient_images)
        self.list_patients_no_mask.itemClicked.connect(self.load_patient_images)
        
        main_splitter.addWidget(files_widget)
        
        # --- 2. 右侧工作区 (包含画布和底部的胶卷栏) ---
        workspace_container = QWidget()
        workspace_layout = QVBoxLayout(workspace_container)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        
        # 使用垂直分割器，允许用户上下调整胶卷栏大小
        v_splitter = QSplitter(Qt.Vertical)
        
        # A. 上部：画布
        v_splitter.addWidget(self.canvas)
        
        # B. 下部：序列容器 (胶卷 + 进度条)
        sequence_container = QWidget()
        sequence_layout = QVBoxLayout(sequence_container)
        sequence_layout.setContentsMargins(0, 0, 0, 0)
        sequence_layout.setSpacing(2)
        
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0); self.seek_slider.setEnabled(False)
        
        self.thumbnail_strip = QListWidget()
        self.thumbnail_strip.setObjectName("ThumbnailStrip")
        self.thumbnail_strip.setFixedHeight(110) # 稍微加高一点
        self.thumbnail_strip.setFlow(QListWidget.LeftToRight)
        self.thumbnail_strip.setIconSize(QSize(80, 80)) # 图标变大
        self.thumbnail_strip.setSpacing(2)
        self.thumbnail_strip.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.thumbnail_strip.itemClicked.connect(lambda item: self.load_image_at_index(self.thumbnail_strip.row(item)))
        self.seek_slider.valueChanged.connect(self.on_slider_change)
        
        sequence_layout.addWidget(self.seek_slider)
        sequence_layout.addWidget(self.thumbnail_strip)
        
        v_splitter.addWidget(sequence_container)
        
        # 设置分割器初始比例 (画布占大部分)
        v_splitter.setStretchFactor(0, 8)
        v_splitter.setStretchFactor(1, 2)
        
        workspace_layout.addWidget(v_splitter)
        main_splitter.addWidget(workspace_container)
        
        # 设置主分割器比例 (资源栏窄，工作区宽)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 5)

    def _init_toolbar(self):
        tb = QToolBar("主控制台")
        tb.setIconSize(QSize(36, 36))
        tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.addToolBar(Qt.TopToolBarArea, tb)
        
        # === 基础文件操作 ===
        act_orig = QAction(IconFactory.create_tool_icon("图", "#ffffff", "rect"), "加载原图", self)
        act_orig.triggered.connect(self.select_orig_dir)
        tb.addAction(act_orig)
        
        act_mask = QAction(IconFactory.create_tool_icon("掩", "#ffffff", "rect"), "加载掩码", self)
        act_mask.triggered.connect(self.select_mask_dir)
        tb.addAction(act_mask)
        
        tb.addSeparator()
        
        # === 绘图工具 ===
        grp = QActionGroup(self)
        self.act_brush = QAction(IconFactory.create_tool_icon("笔", "#00f0ff", "circle"), "画笔工具", self)
        self.act_brush.setCheckable(True); self.act_brush.setChecked(True)
        self.act_brush.triggered.connect(lambda: setattr(self.canvas, 'tool', ToolType.BRUSH))
        tb.addAction(self.act_brush); grp.addAction(self.act_brush)
        
        self.act_eraser = QAction(IconFactory.create_tool_icon("擦", "#ff0055", "circle"), "橡皮擦", self)
        self.act_eraser.setCheckable(True)
        self.act_eraser.triggered.connect(lambda: setattr(self.canvas, 'tool', ToolType.ERASER))
        tb.addAction(self.act_eraser); grp.addAction(self.act_eraser)
        
        self.act_poly = QAction(IconFactory.create_tool_icon("多", "#00ff00", "circle"), "多边形绘制", self)
        self.act_poly.setCheckable(True)
        self.act_poly.triggered.connect(lambda: setattr(self.canvas, 'tool', ToolType.POLYGON))
        tb.addAction(self.act_poly); grp.addAction(self.act_poly)
        
        tb.addSeparator()

        # === 保存 ===
        act_save = QAction(IconFactory.create_tool_icon("存", "#ffff00", "rect"), "保存标注", self)
        act_save.triggered.connect(self.save_mask)
        tb.addAction(act_save)
        
        # 自动保存复选框
        self.chk_autosave = QCheckBox("自动保存")
        self.chk_autosave.setChecked(self.autosave_enabled)
        self.chk_autosave.toggled.connect(lambda v: setattr(self, 'autosave_enabled', v))
        tb.addWidget(self.chk_autosave)
        
        tb.addSeparator()
        
        # === 参数区 (原右侧面板) ===
        # 1. 智能锁定模块
        self.act_smart = QAction(IconFactory.create_lock_icon(True), "智能分割锁定", self)
        self.act_smart.setCheckable(True)
        self.act_smart.setToolTip("启用基于灰度的智能锁定")
        self.act_smart.toggled.connect(self._toggle_smart_lock)
        tb.addAction(self.act_smart)
        
        # 模式选择 (放在 Action 旁边)
        self.combo_smart = QComboBox()
        self.combo_smart.addItems(["锁定目标：暗部(气体)", "锁定目标：亮部(组织)"])
        self.combo_smart.setToolTip("选择锁定的目标区域类型")
        self.combo_smart.currentIndexChanged.connect(lambda i: setattr(self.canvas, 'smart_lock_mode', 'dark' if i==0 else 'light'))
        tb.addWidget(self.combo_smart)
        
        # 阈值滑块 (紧凑型)
        w_thresh = QWidget()
        l_thresh = QHBoxLayout(w_thresh); l_thresh.setContentsMargins(5,0,5,0)
        l_thresh.addWidget(QLabel("阈值:", w_thresh))
        self.spin_thresh = QSpinBox()
        self.spin_thresh.setRange(0, 255); self.spin_thresh.setValue(60)
        self.spin_thresh.setFixedWidth(50)
        self.spin_thresh.valueChanged.connect(lambda v: setattr(self.canvas, 'smart_threshold', v))
        l_thresh.addWidget(self.spin_thresh)
        tb.addWidget(w_thresh)
        
        tb.addSeparator()
        
        # 2. 可视化模块 (整合在一个 Widget 里以减少间距)
        w_viz = QWidget()
        l_viz = QHBoxLayout(w_viz)
        l_viz.setContentsMargins(0, 0, 0, 0)
        l_viz.setSpacing(3) # 更紧凑的水平间距
        w_viz.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        
        # 透明度图标
        icon_eye = QLabel()
        icon_eye.setPixmap(IconFactory.create_eye_icon().pixmap(28, 28)) # 稍微大一点
        icon_eye.setContentsMargins(0, 0, 0, 0)
        icon_eye.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        l_viz.addWidget(icon_eye)
        
        # 透明度滑块
        slider_alpha = QSlider(Qt.Horizontal)
        slider_alpha.setRange(0, 255); slider_alpha.setValue(100); slider_alpha.setFixedWidth(80)
        slider_alpha.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        slider_alpha.setToolTip("调整掩码显示透明度")
        slider_alpha.valueChanged.connect(lambda v: (setattr(self.canvas, 'overlay_alpha', v), self.canvas.update()))
        l_viz.addWidget(slider_alpha)
        
        # 边缘吸附按钮 (手动创建 ToolButton 以便放入同一布局)
        self.act_snap = QAction(IconFactory.create_magnet_icon(), "边缘吸附", self)
        self.act_snap.setCheckable(True)
        self.act_snap.toggled.connect(lambda v: setattr(self.canvas, 'edge_snap_enabled', v))
        
        btn_snap = QToolButton()
        btn_snap.setDefaultAction(self.act_snap)
        btn_snap.setToolButtonStyle(Qt.ToolButtonIconOnly) # 仅图标，减少水平占用
        btn_snap.setAutoRaise(True)
        btn_snap.setIconSize(QSize(28, 28))
        btn_snap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn_snap.setToolTip("边缘吸附")
        l_viz.addWidget(btn_snap)
        
        tb.addWidget(w_viz)

    def _toggle_smart_lock(self, checked):
        self.canvas.smart_lock_enabled = checked
        # 切换图标状态
        self.act_smart.setIcon(IconFactory.create_lock_icon(checked))

    def _init_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+S"), self, self.save_mask)
        QShortcut(QKeySequence("Ctrl+Z"), self, self.canvas.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, self.canvas.redo)
        QShortcut(QKeySequence("A"), self, self.prev_image)
        QShortcut(QKeySequence("D"), self, self.next_image)
        QShortcut(QKeySequence("1"), self, self.act_brush.trigger)
        QShortcut(QKeySequence("2"), self, self.act_eraser.trigger)
        QShortcut(QKeySequence("3"), self, self.act_poly.trigger)

    # --- 业务逻辑 ---

    def select_orig_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择原图目录")
        if d:
            self.orig_root = d
            if self.mask_root: self.refresh_lists()

    def select_mask_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择掩码目录")
        if d:
            self.mask_root = d
            if self.orig_root: self.refresh_lists()

    def refresh_lists(self):
        if not self.orig_root or not self.mask_root: return
        self.list_patients_annotated.clear()
        self.list_patients_no_mask.clear()
        try:
            patients = [d for d in os.listdir(self.orig_root) if os.path.isdir(os.path.join(self.orig_root, d))]
            patients.sort(key=natural_sort_key)
            for p in patients:
                if os.path.exists(os.path.join(self.mask_root, p)):
                    self.list_patients_annotated.addItem(p)
                else:
                    self.list_patients_no_mask.addItem(p)
        except Exception as e:
            QMessageBox.critical(self, "系统错误", str(e))

    def load_patient_images(self, item):
        if not item: return
        patient_name = item.text()
        p_orig = os.path.join(self.orig_root, patient_name)
        p_mask = os.path.join(self.mask_root, patient_name)
        
        self.entries.clear()
        self.thumbnail_strip.clear() 
        self.current_idx = -1
        
        exts = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'}
        files = []
        for root, _, fs in os.walk(p_orig):
            for f in fs:
                if os.path.splitext(f)[1].lower() in exts:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, p_orig)
                    files.append((rel, full))
        files.sort(key=lambda x: natural_sort_key(x[0]))
        
        self.statusBar().showMessage(f"正在读取 {len(files)} 张序列图像...")
        QApplication.processEvents()

        for i, (rel, full) in enumerate(files):
            mask_name = os.path.splitext(rel)[0] + ".png"
            mask_full = os.path.join(p_mask, mask_name)
            has_mask = os.path.exists(mask_full)
            self.entries.append(ImageEntry(rel, full, mask_full, has_mask))
            
            # 缩略图生成
            thumb_icon = QIcon()
            img_thumb = imread_unicode(full, cv2.IMREAD_GRAYSCALE)
            if img_thumb is not None:
                # 稍微增大缩略图渲染尺寸以适应新UI
                img_thumb = cv2.resize(img_thumb, (80, 80), interpolation=cv2.INTER_AREA)
                thumb_rgb = cv2.cvtColor(img_thumb, cv2.COLOR_GRAY2RGB)
                
                if has_mask:
                    mask_img = imread_unicode(mask_full, cv2.IMREAD_GRAYSCALE)
                    if mask_img is not None:
                        mask_thumb = cv2.resize(mask_img, (80, 80), interpolation=cv2.INTER_NEAREST)
                        bin_mask = (mask_thumb >= 127).astype(np.uint8)
                        r, g, b = (255, 50, 50)
                        alpha = 0.5
                        overlay = np.zeros_like(thumb_rgb)
                        overlay[..., 0] = r; overlay[..., 1] = g; overlay[..., 2] = b
                        mask3 = bin_mask[..., None].astype(np.float32)
                        thumb_rgb = (thumb_rgb.astype(np.float32) * (1.0 - alpha * mask3) + overlay.astype(np.float32) * (alpha * mask3)).astype(np.uint8)
                
                qimg = QImage(thumb_rgb.data, 80, 80, thumb_rgb.strides[0], QImage.Format_RGB888)
                pix = QPixmap.fromImage(qimg)
                if has_mask:
                    p = QPainter(pix)
                    p.setPen(QPen(Qt.green, 4))
                    p.drawRect(0, 0, 79, 79)
                    p.end()
                thumb_icon = QIcon(pix)
            
            l_item = QListWidgetItem(thumb_icon, "")
            l_item.setToolTip(f"{i+1}: {rel}")
            self.thumbnail_strip.addItem(l_item)
            
            if i % 10 == 0: QApplication.processEvents()
        
        if self.entries:
            self.seek_slider.setRange(0, len(self.entries) - 1)
            self.seek_slider.setEnabled(True)
            self.load_image_at_index(0)
        else:
            self.seek_slider.setEnabled(False)

        self.statusBar().showMessage(f"序列加载完成: {patient_name} ({len(files)} 张)")

    def on_slider_change(self, value):
        if value != self.current_idx:
            self.load_image_at_index(value)

    def load_image_at_index(self, row):
        if row < 0 or row >= len(self.entries): return
        
        if self.autosave_enabled and self.current_idx >= 0 and self.current_idx != row:
            self.save_mask()
        
        preserve = self.current_idx != -1
        self.current_idx = row
        
        if self.seek_slider.value() != row:
            self.seek_slider.blockSignals(True)
            self.seek_slider.setValue(row)
            self.seek_slider.blockSignals(False)
            
        self.thumbnail_strip.blockSignals(True)
        self.thumbnail_strip.setCurrentRow(row)
        self.thumbnail_strip.scrollToItem(self.thumbnail_strip.item(row), QAbstractItemView.PositionAtCenter)
        self.thumbnail_strip.blockSignals(False)
        
        entry = self.entries[row]
        img = imread_unicode(entry.orig_path)
        if img is None: return
            
        mask = None
        if entry.has_mask and entry.mask_path:
            mask = imread_unicode(entry.mask_path, cv2.IMREAD_GRAYSCALE)
            
        self.canvas.load_image(img, mask, preserve_view=preserve)
        self.status_label.setText(f"INDEX: {row+1} / {len(self.entries)} | {entry.filename}")

    def save_mask(self):
        if self.current_idx < 0 or self.canvas.mask is None: return
        entry = self.entries[self.current_idx]
        if not entry.mask_path: return
        os.makedirs(os.path.dirname(entry.mask_path), exist_ok=True)
        save_mask = (self.canvas.mask >= self.canvas.display_threshold).astype(np.uint8) * 255
        if imwrite_unicode(entry.mask_path, save_mask):
            self.statusBar().showMessage(f"SAVED: {entry.mask_path}", 1000)
            entry.has_mask = True
            
            item = self.thumbnail_strip.item(self.current_idx)
            if item:
                icon = item.icon()
                pix = icon.pixmap(80, 80)
                p = QPainter(pix)
                p.setPen(QPen(Qt.green, 6))
                p.drawRect(0, 0, 79, 79)
                p.end()
                item.setIcon(QIcon(pix))
        else:
            QMessageBox.warning(self, "Error", "Failed to write mask.")

    def prev_image(self):
        if self.current_idx > 0: self.load_image_at_index(self.current_idx - 1)

    def next_image(self):
        if self.current_idx < len(self.entries) - 1: self.load_image_at_index(self.current_idx + 1)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    win = MaskCorrectorWindow()
    win.show()
    sys.exit(app.exec())
