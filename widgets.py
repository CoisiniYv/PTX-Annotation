"""界面组件：信息面板与可视化控制条。"""

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from icons import IconFactory
from utils import get_dicom_metadata


class DicomInfoPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)
        l = QVBoxLayout(self)
        l.setContentsMargins(5, 5, 5, 5)

        title = QLabel("DICOM METADATA")
        title.setStyleSheet(
            "color: #00f0ff; font-weight: bold; border-bottom: 2px solid #00f0ff; padding-bottom: 5px;"
        )
        l.addWidget(title)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Tag", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        l.addWidget(self.table)

    def clear(self):
        """清空表格内容（供模式切换时调用）。"""
        self.table.setRowCount(0)

    def update_info(self, path):
        self.table.setRowCount(0)
        info = get_dicom_metadata(path)
        self.table.setRowCount(len(info))
        for i, (k, v) in enumerate(info.items()):
            self.table.setItem(i, 0, QTableWidgetItem(k))
            self.table.setItem(i, 1, QTableWidgetItem(v))


class VisualControlWidget(QWidget):
    valueChanged = Signal(str, float)

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        l = QHBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(2)

        self.btn_invert = QToolButton()
        self.btn_invert.setIcon(IconFactory.create_invert_icon())
        self.btn_invert.setToolTip("反色显示")
        self.btn_invert.setAutoRaise(True)
        self.btn_invert.setCheckable(True)
        self.btn_invert.clicked.connect(
            lambda: self.valueChanged.emit("invert", self.btn_invert.isChecked())
        )
        l.addWidget(self.btn_invert)

        w_alpha = QWidget()
        l_alpha = QHBoxLayout(w_alpha)
        l_alpha.setContentsMargins(0, 0, 0, 0)
        l_alpha.setSpacing(2)
        lab_a = QLabel()
        lab_a.setPixmap(IconFactory.create_eye_icon().pixmap(20, 20))
        self.slider_alpha = QSlider(Qt.Horizontal)
        self.slider_alpha.setRange(0, 255)
        self.slider_alpha.setValue(100)
        self.slider_alpha.setFixedWidth(60)
        self.slider_alpha.valueChanged.connect(
            lambda v: self.valueChanged.emit("alpha", v)
        )
        l_alpha.addWidget(lab_a)
        l_alpha.addWidget(self.slider_alpha)
        l.addWidget(w_alpha)

        w_bright = QWidget()
        l_bright = QHBoxLayout(w_bright)
        l_bright.setContentsMargins(0, 0, 0, 0)
        l_bright.setSpacing(2)
        lab_b = QLabel()
        lab_b.setPixmap(IconFactory.create_sun_icon().pixmap(20, 20))
        self.slider_bright = QSlider(Qt.Horizontal)
        self.slider_bright.setRange(50, 300)
        self.slider_bright.setValue(100)
        self.slider_bright.setFixedWidth(60)
        self.slider_bright.valueChanged.connect(
            lambda v: self.valueChanged.emit("brightness", v / 100.0)
        )
        l_bright.addWidget(lab_b)
        l_bright.addWidget(self.slider_bright)
        l.addWidget(w_bright)

        # --- 滤镜选择 ---
        w_filter = QWidget()
        l_filter = QHBoxLayout(w_filter)
        l_filter.setContentsMargins(0, 0, 0, 0)
        l_filter.setSpacing(2)
        
        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["正常", "CLAHE", "锐化", "平滑"])
        self.combo_filter.setFixedWidth(65)
        self.combo_filter.setToolTip("医学影像增强滤镜")
        self.combo_filter.currentIndexChanged.connect(
            lambda i: self.valueChanged.emit("filter", float(i))
        )
        
        self.slider_filter_strength = QSlider(Qt.Horizontal)
        self.slider_filter_strength.setRange(0, 100)
        self.slider_filter_strength.setValue(50)
        self.slider_filter_strength.setFixedWidth(50)
        self.slider_filter_strength.setToolTip("滤镜增强强度")
        self.slider_filter_strength.valueChanged.connect(
            lambda v: self.valueChanged.emit("filter_strength", v / 100.0)
        )
        
        l_filter.addWidget(self.combo_filter)
        l_filter.addWidget(self.slider_filter_strength)
        l.addWidget(w_filter)

        w_window = QWidget()
        l_window = QVBoxLayout(w_window)
        l_window.setContentsMargins(0, 0, 0, 0)
        l_window.setSpacing(2)
        row_w = QHBoxLayout()
        row_w.setContentsMargins(0, 0, 0, 0)
        row_w.setSpacing(2)
        lab_w = QLabel("W")
        self.slider_window_width = QSlider(Qt.Horizontal)
        self.slider_window_width.setRange(1, 4096)
        self.slider_window_width.setValue(400)
        self.slider_window_width.setFixedWidth(70)
        self.slider_window_width.valueChanged.connect(
            lambda v: self.valueChanged.emit("window_width", float(v))
        )
        row_w.addWidget(lab_w)
        row_w.addWidget(self.slider_window_width)

        row_c = QHBoxLayout()
        row_c.setContentsMargins(0, 0, 0, 0)
        row_c.setSpacing(2)
        lab_c = QLabel("C")
        self.slider_window_center = QSlider(Qt.Horizontal)
        self.slider_window_center.setRange(-1024, 3072)
        self.slider_window_center.setValue(40)
        self.slider_window_center.setFixedWidth(70)
        self.slider_window_center.valueChanged.connect(
            lambda v: self.valueChanged.emit("window_center", float(v))
        )
        row_c.addWidget(lab_c)
        row_c.addWidget(self.slider_window_center)

        l_window.addLayout(row_w)
        l_window.addLayout(row_c)
        l.addWidget(w_window)

        l.addStretch()

    def set_window_controls(self, center, width, min_val, max_val, enabled: bool):
        self.slider_window_center.blockSignals(True)
        self.slider_window_width.blockSignals(True)
        if enabled:
            min_c = int(np.floor(min_val))
            max_c = int(np.ceil(max_val))
            self.slider_window_center.setRange(min_c, max_c)
            self.slider_window_width.setRange(1, int(max(2, max_val - min_val)))
            self.slider_window_center.setValue(int(round(center)))
            self.slider_window_width.setValue(int(round(width)))
        self.slider_window_center.setEnabled(enabled)
        self.slider_window_width.setEnabled(enabled)
        self.slider_window_center.blockSignals(False)
        self.slider_window_width.blockSignals(False)


class PrefetchSettingsDialog(QDialog):
    def __init__(
        self,
        parent=None,
        ct_prefetch_count=8,
        ct_cross_count=2,
        ct_cache_max=40,
        xray_prefetch_count=5,
        xray_cache_max=12,
        xray_default_mask_format="png",
    ):
        super().__init__(parent)
        self.setWindowTitle("性能设置")
        from PySide6.QtWidgets import QGroupBox, QTabWidget

        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        # ── CT 标签页 ──────────────────────────────────────────
        ct_widget = QWidget()
        ct_layout = QVBoxLayout(ct_widget)
        ct_layout.setSpacing(12)

        grp_seq = QGroupBox("序列内预取（帧）")
        form_seq = QFormLayout(grp_seq)
        self.spin_ct_prefetch = QSpinBox()
        self.spin_ct_prefetch.setRange(0, 80)
        self.spin_ct_prefetch.setValue(ct_prefetch_count)
        self.spin_ct_prefetch.setSuffix(" 张")
        self.spin_ct_prefetch.setToolTip("当前帧前后各预读 N 张，0 = 关闭")
        form_seq.addRow("前后预取张数", self.spin_ct_prefetch)

        grp_cross = QGroupBox("跨病号预取")
        form_cross = QFormLayout(grp_cross)
        self.spin_ct_cross = QSpinBox()
        self.spin_ct_cross.setRange(0, 10)
        self.spin_ct_cross.setValue(ct_cross_count)
        self.spin_ct_cross.setSuffix(" 个病号")
        self.spin_ct_cross.setToolTip(
            "切换病号时，提前预读后续 N 个病号的序列，0 = 关闭"
        )
        form_cross.addRow("预读后续病号数", self.spin_ct_cross)

        grp_cache_ct = QGroupBox("内存缓存")
        form_cache_ct = QFormLayout(grp_cache_ct)
        self.spin_ct_cache = QSpinBox()
        self.spin_ct_cache.setRange(5, 50)
        self.spin_ct_cache.setValue(ct_cache_max)
        self.spin_ct_cache.setSuffix(" 帧")
        self.spin_ct_cache.setToolTip(
            "LRU 缓存最多保留多少帧图像，超出后自动淘汰最旧的"
        )
        form_cache_ct.addRow("缓存上限", self.spin_ct_cache)

        ct_layout.addWidget(grp_seq)
        ct_layout.addWidget(grp_cross)
        ct_layout.addWidget(grp_cache_ct)
        ct_layout.addStretch()
        tabs.addTab(ct_widget, "CT 序列")

        # ── X光标签页 ──────────────────────────────────────────
        xray_widget = QWidget()
        xray_layout = QVBoxLayout(xray_widget)
        xray_layout.setSpacing(12)

        grp_xray_pre = QGroupBox("病例预取")
        form_xray_pre = QFormLayout(grp_xray_pre)
        self.spin_xray_prefetch = QSpinBox()
        self.spin_xray_prefetch.setRange(0, 30)
        self.spin_xray_prefetch.setValue(xray_prefetch_count)
        self.spin_xray_prefetch.setSuffix(" 个病例")
        self.spin_xray_prefetch.setToolTip("当前病例前后各预读 N 个病例，0 = 关闭")
        form_xray_pre.addRow("前后预取病例数", self.spin_xray_prefetch)

        grp_cache_xray = QGroupBox("内存缓存")
        form_cache_xray = QFormLayout(grp_cache_xray)
        self.spin_xray_cache = QSpinBox()
        self.spin_xray_cache.setRange(2, 100)
        self.spin_xray_cache.setValue(xray_cache_max)
        self.spin_xray_cache.setSuffix(" 张")
        self.spin_xray_cache.setToolTip(
            "LRU 缓存最多保留多少张 X 光图像，X 光单图通常较大，建议不超过 20"
        )
        form_cache_xray.addRow("缓存上限", self.spin_xray_cache)

        grp_mask_fmt = QGroupBox("项目默认掩码格式")
        form_mask_fmt = QFormLayout(grp_mask_fmt)
        self.combo_xray_mask_format = QComboBox()
        self.combo_xray_mask_format.addItem("PNG（位图掩码）", "png")
        self.combo_xray_mask_format.addItem("NIfTI（.nii.gz）", "nii")
        fmt_value = str(xray_default_mask_format or "png").strip().lower()
        idx = 1 if fmt_value in ("nii", "nii.gz", "nifti") else 0
        self.combo_xray_mask_format.setCurrentIndex(idx)
        self.combo_xray_mask_format.setToolTip("X 光模式下新建掩码、尚未存在掩码文件时默认使用的保存格式。")
        form_mask_fmt.addRow("新建掩码默认格式", self.combo_xray_mask_format)

        xray_layout.addWidget(grp_xray_pre)
        xray_layout.addWidget(grp_cache_xray)
        xray_layout.addWidget(grp_mask_fmt)
        xray_layout.addStretch()
        tabs.addTab(xray_widget, "X 光单张")

        layout.addWidget(tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setMinimumWidth(360)

    def get_values(self):
        return {
            "ct_prefetch_count": self.spin_ct_prefetch.value(),
            "ct_cross_count": self.spin_ct_cross.value(),
            "ct_cache_max": self.spin_ct_cache.value(),
            "xray_prefetch_count": self.spin_xray_prefetch.value(),
            "xray_cache_max": self.spin_xray_cache.value(),
            "xray_default_mask_format": self.combo_xray_mask_format.currentData(),
        }


class ExportSettingsDialog(QDialog):
    def __init__(self, parent=None, width=512, height=512, quality=95, default_path=""):
        super().__init__(parent)
        self.setWindowTitle("导出设置")
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.spin_width = QSpinBox()
        self.spin_width.setRange(1, 10000)
        self.spin_width.setValue(width)
        form.addRow("宽度", self.spin_width)

        self.spin_height = QSpinBox()
        self.spin_height.setRange(1, 10000)
        self.spin_height.setValue(height)
        form.addRow("高度", self.spin_height)

        self.spin_quality = QSpinBox()
        self.spin_quality.setRange(1, 100)
        self.spin_quality.setValue(quality)
        form.addRow("质量", self.spin_quality)

        self.combo_format = QComboBox()
        self.combo_format.addItems(["png", "jpg", "nii"])
        form.addRow("格式", self.combo_format)

        self.check_invert = QCheckBox("反色导出")
        form.addRow("显示模式", self.check_invert)

        self.edit_path = QLineEdit()
        self.edit_path.setText(default_path)

        btn_browse = QPushButton("浏览")
        btn_browse.clicked.connect(self._browse_path)

        path_row = QHBoxLayout()
        path_row.addWidget(self.edit_path)
        path_row.addWidget(btn_browse)
        form.addRow("导出路径", path_row)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_with_normalized_path)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.combo_format.currentTextChanged.connect(self._on_format_changed)

        self._normalize_initial_format(default_path)

    def _split_known_ext(self, path: str):
        path = path or ""
        lower = path.lower()
        for ext in (".nii.gz", ".nii", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"):
            if lower.endswith(ext):
                return path[: -len(ext)], ext
        return path, ""

    def _ensure_path_ext(self, path: str, fmt: str) -> str:
        stem, _ = self._split_known_ext(path)
        fmt = (fmt or "png").lower()
        if fmt == "jpg":
            return stem + ".jpg"
        if fmt == "nii":
            return stem + ".nii.gz"
        return stem + ".png"

    def _filter_for_format(self, fmt: str) -> str:
        fmt = (fmt or "png").lower()
        if fmt == "jpg":
            return "JPG Files (*.jpg *.jpeg);;PNG Files (*.png);;NIfTI Files (*.nii.gz *.nii);;All Files (*)"
        if fmt == "nii":
            return "NIfTI Files (*.nii.gz *.nii);;PNG Files (*.png);;JPG Files (*.jpg *.jpeg);;All Files (*)"
        return "PNG Files (*.png);;JPG Files (*.jpg *.jpeg);;NIfTI Files (*.nii.gz *.nii);;All Files (*)"

    def _normalize_initial_format(self, default_path: str):
        lower = (default_path or "").lower()
        if lower.endswith((".nii.gz", ".nii")):
            self.combo_format.setCurrentText("nii")
        elif lower.endswith((".jpg", ".jpeg")):
            self.combo_format.setCurrentText("jpg")
        else:
            self.combo_format.setCurrentText("png")
        self.edit_path.setText(self._ensure_path_ext(default_path or "export.png", self.combo_format.currentText()))

    def _on_format_changed(self, fmt: str):
        current = self.edit_path.text().strip()
        if not current:
            current = "export"
        self.edit_path.setText(self._ensure_path_ext(current, fmt))

    def _accept_with_normalized_path(self):
        current = self.edit_path.text().strip()
        if current:
            self.edit_path.setText(self._ensure_path_ext(current, self.combo_format.currentText()))
        self.accept()

    def get_values(self):
        return (
            self.spin_width.value(),
            self.spin_height.value(),
            self.spin_quality.value(),
            self.combo_format.currentText(),
            self.edit_path.text().strip(),
            self.check_invert.isChecked(),
        )

    def _browse_path(self):
        fmt = self.combo_format.currentText()
        current = self.edit_path.text().strip()
        start_path = self._ensure_path_ext(current or "export", fmt)

        path, _ = QFileDialog.getSaveFileName(
            self,
            "选择导出路径",
            start_path,
            self._filter_for_format(fmt),
        )
        if path:
            self.edit_path.setText(self._ensure_path_ext(path, fmt))
