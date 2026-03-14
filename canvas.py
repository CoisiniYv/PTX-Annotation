"""绘制画布：标注交互、缩放与绘制逻辑。"""

import cv2
import numpy as np
import SimpleITK as sitk
from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from models import ToolType


class Canvas(QWidget):
    request_next = Signal()
    request_prev = Signal()
    zoom_changed = Signal(float)
    cursor_info_changed = Signal(str)
    content_modified = Signal(bool)
    file_dropped = Signal(str)  # 拖入文件路径，由外部处理加载逻辑

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)

        self.base_img: np.ndarray | None = None
        self.base_gray: np.ndarray | None = None
        self.mask: np.ndarray | None = None
        self._is_dirty = False

        self._cache_bg_pixmap: QPixmap | None = None
        self._cache_color_table = []

        self.zoom = 1.0
        self.offset = QPoint(0, 0)
        self.fit_margin = 0.95

        self._overlay_color = (255, 50, 50)
        self._overlay_alpha = 100
        self.display_threshold = 127
        self._brightness = 1.0
        self._invert_view = False
        self._window_center = None
        self._window_width = None
        self.base_raw: np.ndarray | None = None
        self._filter_type = "None"
        self._filter_strength = 0.5
        self._raw_filtered: np.ndarray | None = None

        self._tool = ToolType.BRUSH
        self.brush_size = 20
        self.brush_shape = "circle"

        self.smart_lock_enabled = False
        self.smart_lock_mode = "dark"
        self.smart_threshold = 60
        self.edge_snap_enabled = False
        self.edge_snap_radius = 10

        self._is_drawing = False
        self._pan_active = False
        self._last_mouse_pos = QPoint()
        self._mouse_img_pos = (-1, -1)
        self._last_draw_point = None

        self.undo_stack = []
        self.redo_stack = []
        self.polygon_points = []

        self.grid_alpha = 24
        self.grid_step = 40
        self._cache_empty_bg_pixmap: QPixmap | None = None
        self._cache_empty_bg_size = None
        self.grid_timer = QTimer(self)
        self.grid_timer.timeout.connect(self._animate_grid)

        self._update_color_table()

    @property
    def filter_type(self):
        return self._filter_type

    @filter_type.setter
    def filter_type(self, value):
        if self._filter_type != value:
            self._filter_type = value
            self._raw_filtered = None
            self._update_bg_cache()
            self.update()

    @property
    def filter_strength(self):
        return self._filter_strength

    @filter_strength.setter
    def filter_strength(self, value):
        if self._filter_strength != value:
            self._filter_strength = value
            self._raw_filtered = None
            self._update_bg_cache()
            self.update()

    @property
    def brightness(self):
        return self._brightness

    @brightness.setter
    def brightness(self, value):
        if self._brightness != value:
            self._brightness = value
            self._update_bg_cache()
            self.update()

    @property
    def invert_view(self):
        return self._invert_view

    @invert_view.setter
    def invert_view(self, value: bool):
        if self._invert_view != value:
            self._invert_view = value
            self._update_bg_cache()
            self.update()

    @property
    def overlay_alpha(self):
        return self._overlay_alpha

    @overlay_alpha.setter
    def overlay_alpha(self, value):
        if self._overlay_alpha != value:
            self._overlay_alpha = value
            self._update_color_table()
            self.update()

    @property
    def window_center(self):
        return self._window_center

    @window_center.setter
    def window_center(self, value):
        if value is None:
            self._window_center = None
        elif self._window_center != value:
            self._window_center = value
        self._update_bg_cache()
        self.update()

    @property
    def window_width(self):
        return self._window_width

    @window_width.setter
    def window_width(self, value):
        if value is None:
            self._window_width = None
        elif self._window_width != value:
            self._window_width = value
        self._update_bg_cache()
        self.update()

    @property
    def tool(self) -> ToolType:
        return self._tool

    @tool.setter
    def tool(self, value: ToolType):
        if self._tool != value:
            self._tool = value
            self._update_cursor()
            self.update()
            if value != ToolType.POLYGON and self.polygon_points:
                self.polygon_points.clear()
                self.update()

    def _mark_dirty(self):
        if not self._is_dirty:
            self._is_dirty = True
            self.content_modified.emit(True)

    def _update_color_table(self):
        r, g, b = self._overlay_color
        alpha = self._overlay_alpha
        table = [0] * 256
        table[0] = QColor(0, 0, 0, 0).rgba()
        target_color = QColor(r, g, b, alpha).rgba()
        for i in range(1, 256):
            table[i] = target_color
        self._cache_color_table = table

    def _invalidate_empty_bg_cache(self):
        self._cache_empty_bg_pixmap = None
        self._cache_empty_bg_size = None

    def _ensure_empty_bg_cache(self):
        size = (self.width(), self.height())
        if size[0] <= 0 or size[1] <= 0:
            return
        if (
            self._cache_empty_bg_pixmap is not None
            and self._cache_empty_bg_size == size
        ):
            return

        pixmap = QPixmap(size[0], size[1])
        pixmap.fill(QColor("#000000"))

        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor(0, 240, 255, self.grid_alpha), 1))
        for x in range(0, size[0], self.grid_step):
            painter.drawLine(x, 0, x, size[1])
        for y in range(0, size[1], self.grid_step):
            painter.drawLine(0, y, size[0], y)
        painter.end()

        self._cache_empty_bg_pixmap = pixmap
        self._cache_empty_bg_size = size

    def _update_bg_cache(self):
        if self.base_img is None:
            self._cache_bg_pixmap = None
            self._ensure_empty_bg_cache()
            return

        # --- 1. 获取处理后的灰度图 (处理 Raw 数据优先) ---
        if (
            self.base_raw is not None
            and self._window_center is not None
            and self._window_width
        ):
            # 核心优化：只有缓存为空时才执行滤镜处理
            if self._raw_filtered is None:
                if self._filter_type == "None":
                    self._raw_filtered = self.base_raw.astype(np.float32)
                else:
                    s = self._filter_strength  # 0.0 ~ 1.0
                    
                    if self._filter_type == "CLAHE":
                        # [性能修复] SimpleITK 的 CLAHE 极慢，改用 OpenCV 的 16位 极速实现
                        raw_min = self.base_raw.min()
                        raw_max = self.base_raw.max()
                        if raw_max > raw_min:
                            # 映射到 0-65535 以使用 OpenCV 的 16位 支持
                            norm_raw = ((self.base_raw - raw_min) / (raw_max - raw_min) * 65535).astype(np.uint16)
                            # 强度映射：clipLimit 1.0 ~ 8.0
                            limit = 1.0 + s * 7.0
                            clahe = cv2.createCLAHE(clipLimit=limit, tileGridSize=(8, 8))
                            clahe_img = clahe.apply(norm_raw)
                            # 还原回原有的医学数值范围（如 CT 的 HU 值），保证调窗仍然准确
                            self._raw_filtered = (clahe_img.astype(np.float32) / 65535.0) * (raw_max - raw_min) + raw_min
                        else:
                            self._raw_filtered = self.base_raw.astype(np.float32)

                    elif self._filter_type == "Sharpen":
                        itk_img = sitk.GetImageFromArray(self.base_raw.astype(np.float32))
                        # 强度映射：Sigma 0.5 ~ 2.5
                        sigma = 0.5 + s * 2.0
                        sharpen = sitk.LaplacianRecursiveGaussianImageFilter()
                        sharpen.SetSigma(sigma)
                        laplacian = sharpen.Execute(itk_img)
                        itk_img = sitk.Subtract(itk_img, sitk.Multiply(laplacian, s))
                        self._raw_filtered = sitk.GetArrayFromImage(itk_img)
                        
                    elif self._filter_type == "Smooth":
                        itk_img = sitk.GetImageFromArray(self.base_raw.astype(np.float32))
                        # [性能修复] 降低最大迭代次数避免拖动滑块时卡死
                        iters = int(1 + s * 4) 
                        smooth = sitk.CurvatureFlowImageFilter()
                        smooth.SetTimeStep(0.05)
                        smooth.SetNumberOfIterations(iters)
                        itk_img = smooth.Execute(itk_img)
                        self._raw_filtered = sitk.GetArrayFromImage(itk_img)

            # 调窗映射：直接在缓存上操作，速度极快
            wc = float(self._window_center)
            ww = float(self._window_width)
            lower = wc - 0.5 - (ww - 1) / 2
            upper = wc - 0.5 + (ww - 1) / 2
            display = np.clip(self._raw_filtered, lower, upper)
            display = (display - lower) / (upper - lower) * 255.0
            display_img = cv2.cvtColor(display.astype(np.uint8), cv2.COLOR_GRAY2BGR)
        else:
            # 兼容非 DICOM 或无 Raw 数据的情况
            display_img = self.base_img.copy()
            if self._filter_type == "CLAHE":
                gray = cv2.cvtColor(display_img, cv2.COLOR_BGR2GRAY)
                limit = 1.0 + self._filter_strength * 4.0
                clahe = cv2.createCLAHE(clipLimit=limit, tileGridSize=(8, 8))
                gray = clahe.apply(gray)
                display_img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        # --- 2. 应用常规可视化设置 ---
        if self._brightness != 1.0:
            display_img = cv2.convertScaleAbs(display_img, alpha=self._brightness, beta=0)
        if self._invert_view:
            display_img = cv2.bitwise_not(display_img)

        h, w = display_img.shape[:2]
        img_rgb = cv2.cvtColor(display_img, cv2.COLOR_BGR2RGB)
        qimg = QImage(img_rgb.data, w, h, w * 3, QImage.Format_RGB888)
        self._cache_bg_pixmap = QPixmap.fromImage(qimg)

    def _update_cursor(self):
        if self.base_img is None:
            self.setCursor(Qt.ArrowCursor)
            return
        if self._tool == ToolType.POLYGON:
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.BlankCursor)

    def _animate_grid(self):
        # 空画布背景已改为静态缓存，不再进行 50ms 动画重绘。
        if self.grid_timer.isActive():
            self.grid_timer.stop()

    def fit_view(self):
        if self.base_img is None:
            return
        h, w = self.base_img.shape[:2]
        canvas_w = self.width()
        canvas_h = self.height()
        if canvas_w == 0 or canvas_h == 0:
            return
        scale_w = canvas_w / w
        scale_h = canvas_h / h
        self.zoom = min(scale_w, scale_h) * self.fit_margin

        disp_w, disp_h = w * self.zoom, h * self.zoom
        off_x = (canvas_w - disp_w) / 2
        off_y = (canvas_h - disp_h) / 2
        self.offset = QPoint(int(off_x), int(off_y))
        self.zoom_changed.emit(self.zoom)
        self.update()

    def load_image(
        self,
        img_bgr: np.ndarray,
        mask: np.ndarray | None,
        preserve_view: bool = False,
        raw: np.ndarray | None = None,
        window_center=None,
        window_width=None,
    ):
        if img_bgr is None:
            return
        if len(img_bgr.shape) == 2:
            img_bgr = cv2.cvtColor(img_bgr, cv2.COLOR_GRAY2BGR)

        self.base_img = img_bgr
        self.base_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        self.base_raw = raw
        if raw is None:
            self._window_center = None
            self._window_width = None
        else:
            self._window_center = window_center
            self._window_width = window_width

        if mask is None:
            self.mask = np.zeros(img_bgr.shape[:2], dtype=np.uint8)
        else:
            self.mask = np.ascontiguousarray(mask.copy())

        self.undo_stack.clear()
        self.redo_stack.clear()
        self.polygon_points.clear()
        self._raw_filtered = None

        self._update_bg_cache()
        self._is_dirty = False
        self.content_modified.emit(False)

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
        self._invalidate_empty_bg_cache()
        if self.base_img is not None:
            self.fit_view()
        else:
            self._ensure_empty_bg_cache()
            self.update()

    def _push_undo(self):
        if self.mask is not None:
            self.undo_stack.append(self.mask.copy())
            if len(self.undo_stack) > 20:
                self.undo_stack.pop(0)
            self.redo_stack.clear()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.mask.copy())
            self.mask = self.undo_stack.pop()
            self._mark_dirty()
            self.update()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.mask.copy())
            self.mask = self.redo_stack.pop()
            self._mark_dirty()
            self.update()

    def view_to_img(self, pos: QPoint) -> tuple[int, int]:
        x = int((pos.x() - self.offset.x()) / self.zoom)
        y = int((pos.y() - self.offset.y()) / self.zoom)
        return x, y

    def _snap_pos(self, x, y, r):
        if self.base_gray is None:
            return x, y
        h, w = self.base_gray.shape
        x0, y0 = max(0, x - r), max(0, y - r)
        x1, y1 = min(w, x + r + 1), min(h, y + r + 1)
        roi = self.base_gray[y0:y1, x0:x1]
        if roi.size == 0:
            return x, y
        if roi.shape[0] < 3 or roi.shape[1] < 3:
            return x, y
        gx = cv2.Sobel(roi, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(roi, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(mag)
        if max_val < 30:
            return x, y
        return x0 + max_loc[0], y0 + max_loc[1]

    def _apply_brush(self, x: int, y: int):
        if self.mask is None or self.base_gray is None:
            return
        h, w = self.mask.shape
        r = self.brush_size // 2
        if self.edge_snap_enabled:
            x, y = self._snap_pos(x, y, self.edge_snap_radius)
        x0, y0 = max(0, x - r), max(0, y - r)
        x1, y1 = min(w, x + r + 1), min(h, y + r + 1)
        if x0 >= x1 or y0 >= y1:
            return
        roi_mask = self.mask[y0:y1, x0:x1]

        if self.brush_shape == "circle":
            Y, X = np.ogrid[y0:y1, x0:x1]
            brush_area = ((X - x) ** 2 + (Y - y) ** 2) <= r**2
        else:
            brush_area = True

        valid_area = brush_area
        if self.smart_lock_enabled:
            roi_gray = self.base_gray[y0:y1, x0:x1]
            intensity_mask = (
                roi_gray < self.smart_threshold
                if self.smart_lock_mode == "dark"
                else roi_gray > self.smart_threshold
            )
            valid_area = brush_area & intensity_mask

        value = 255 if self.tool == ToolType.BRUSH else 0
        roi_mask[valid_area] = value
        self._mark_dirty()

    def _apply_brush_stroke(self, x: int, y: int):
        if self._last_draw_point is None:
            self._apply_brush(x, y)
            self._last_draw_point = (x, y)
            return
        last_x, last_y = self._last_draw_point
        dx = x - last_x
        dy = y - last_y
        dist = (dx * dx + dy * dy) ** 0.5
        step = max(1.0, self.brush_size * 0.5)
        steps = max(1, int(dist / step))
        for i in range(1, steps + 1):
            t = i / steps
            ix = int(round(last_x + dx * t))
            iy = int(round(last_y + dy * t))
            self._apply_brush(ix, iy)
        self._last_draw_point = (x, y)

    def _close_polygon(self):
        if not self.polygon_points or self.mask is None:
            return
        pts = np.array([[p.x(), p.y()] for p in self.polygon_points], dtype=np.int32)
        self._push_undo()
        cv2.fillPoly(self.mask, [pts], 255)
        self.polygon_points.clear()
        self._mark_dirty()
        self.update()

    _MASK_EXTS = {".nii", ".gz", ".png", ".jpg", ".jpeg", ".bmp"}

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                lower = path.lower()
                if lower.endswith(".nii.gz") or any(
                    lower.endswith(e) for e in self._MASK_EXTS
                ):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            return
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            lower = path.lower()
            if lower.endswith(".nii.gz") or any(
                lower.endswith(e) for e in self._MASK_EXTS
            ):
                self.file_dropped.emit(path)
                event.acceptProposedAction()
                return
        event.ignore()

    def paintEvent(self, event):
        painter = QPainter(self)

        if self._cache_bg_pixmap is None:
            self._ensure_empty_bg_cache()
            if self._cache_empty_bg_pixmap is not None:
                painter.drawPixmap(0, 0, self._cache_empty_bg_pixmap)
            else:
                painter.fillRect(self.rect(), QColor("#000000"))
            painter.setPen(QPen(QColor("#00f0ff"), 2))
            painter.setFont(QFont("Microsoft YaHei UI", 16))
            painter.drawText(self.rect(), Qt.AlignCenter, "请加载数据 (原图 + Mask)")
            return

        painter.fillRect(self.rect(), QColor("#000000"))

        painter.save()
        painter.translate(self.offset)
        painter.scale(self.zoom, self.zoom)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)

        painter.drawPixmap(0, 0, self._cache_bg_pixmap)

        # w/h 从 pixmap 先取好，保证后续画刷光标绘制时变量一定存在
        w = self._cache_bg_pixmap.width()
        h = self._cache_bg_pixmap.height()

        if self.mask is not None:
            h, w = self.mask.shape
            qmask = QImage(
                self.mask.data, w, h, self.mask.strides[0], QImage.Format_Indexed8
            )
            qmask.setColorTable(self._cache_color_table)
            painter.drawImage(0, 0, qmask)

        if self.tool == ToolType.POLYGON and self.polygon_points:
            painter.setPen(QPen(Qt.green, 2 / self.zoom))
            for i in range(1, len(self.polygon_points)):
                painter.drawLine(self.polygon_points[i - 1], self.polygon_points[i])
            if self._mouse_img_pos:
                mx, my = self._mouse_img_pos
                if mx != -1:
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
        self.setFocus()
        if self.base_img is None:
            return
        pos = event.position().toPoint()
        img_x, img_y = self.view_to_img(pos)

        if event.button() == Qt.RightButton:
            self._pan_active = True
            self._last_mouse_pos = pos
            self.setCursor(Qt.ClosedHandCursor)
            return

        if event.button() == Qt.LeftButton:
            if self.tool in (ToolType.BRUSH, ToolType.ERASER):
                self._is_drawing = True
                self._last_draw_point = None
                self._push_undo()
                self._apply_brush_stroke(img_x, img_y)
                self.update()
            elif self.tool == ToolType.POLYGON:
                self._is_drawing = True
                self.polygon_points.append(QPoint(img_x, img_y))
                self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            if self.tool == ToolType.POLYGON and len(self.polygon_points) > 1:
                self._close_polygon()
        else:
            super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        img_x, img_y = self.view_to_img(pos)
        self._mouse_img_pos = (img_x, img_y)

        if (
            self.base_gray is not None
            and 0 <= img_x < self.base_gray.shape[1]
            and 0 <= img_y < self.base_gray.shape[0]
        ):
            val = self.base_gray[img_y, img_x]
            self.cursor_info_changed.emit(
                f"POS: [{img_x:04d}, {img_y:04d}] | VAL: {val:03d}"
            )

        if self._pan_active:
            delta = pos - self._last_mouse_pos
            self.offset += delta
            self._last_mouse_pos = pos
            self.update()
            return

        if self._is_drawing and self.tool in (ToolType.BRUSH, ToolType.ERASER):
            self._apply_brush_stroke(img_x, img_y)
            self.update()

        elif self._is_drawing and self.tool == ToolType.POLYGON:
            if self.polygon_points:
                last_pt = self.polygon_points[-1]
                curr_pt = QPoint(img_x, img_y)
                dist_sq = (last_pt.x() - curr_pt.x()) ** 2 + (
                    last_pt.y() - curr_pt.y()
                ) ** 2
                if dist_sq > 25:
                    self.polygon_points.append(curr_pt)
                    self.update()
        else:
            # 修复：仅笔刷/橡皮工具需要跟随鼠标的光标圆圈时才重绘
            if (
                self.tool in (ToolType.BRUSH, ToolType.ERASER)
                and self.base_img is not None
            ):
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_drawing = False
            self._last_draw_point = None
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
            if delta > 0:
                self.brush_size += step
            else:
                self.brush_size = max(1, self.brush_size - step)
            self.update()
