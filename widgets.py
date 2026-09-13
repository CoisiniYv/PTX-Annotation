"""界面组件：信息面板与可视化控制条。"""

import numpy as np
from pathlib import Path
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
    QTabWidget,
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
        self.combo_filter.addItems(["正常", "增强", "锐化", "平滑"])
        self.combo_filter.setFixedWidth(50)
        self.combo_filter.setToolTip("医学影像增强滤镜")
        self.combo_filter.currentIndexChanged.connect(
            lambda i: self.valueChanged.emit("filter", float(i))
        )

        # 关键：隐藏下拉箭头，缩掉右侧区域
        self.combo_filter.setStyleSheet("""
            QComboBox::drop-down {
                width: 0px;
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                width: 0px;
                height: 0px;
            }
            QComboBox {
                padding-right: 0px;
            }
        """)
        
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


class PaFilterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PA 位筛选")
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.edit_source = QLineEdit()
        btn_source = QPushButton("浏览")
        btn_source.clicked.connect(lambda: self._browse_dir(self.edit_source))
        row_source = QHBoxLayout()
        row_source.addWidget(self.edit_source)
        row_source.addWidget(btn_source)
        form.addRow("源 DICOM 目录", row_source)

        self.edit_target = QLineEdit()
        btn_target = QPushButton("浏览")
        btn_target.clicked.connect(lambda: self._browse_dir(self.edit_target))
        row_target = QHBoxLayout()
        row_target.addWidget(self.edit_target)
        row_target.addWidget(btn_target)
        form.addRow("PA 文件输出目录(可选)", row_target)

        self.edit_excluded = QLineEdit()
        btn_excluded = QPushButton("浏览")
        btn_excluded.clicked.connect(lambda: self._browse_dir(self.edit_excluded))
        row_excluded = QHBoxLayout()
        row_excluded.addWidget(self.edit_excluded)
        row_excluded.addWidget(btn_excluded)
        form.addRow("非 PA 文件移动目录(可选)", row_excluded)

        self.check_report = QCheckBox("生成筛选报告")
        self.check_report.setChecked(True)
        form.addRow("报告", self.check_report)

        self.check_dry_run = QCheckBox("仅扫描不复制/移动")
        self.check_dry_run.setChecked(True)
        form.addRow("dry-run", self.check_dry_run)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setMinimumWidth(480)

    def _browse_dir(self, edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "选择目录")
        if path:
            edit.setText(path)

    def get_values(self):
        return {
            "source_dir": self.edit_source.text().strip(),
            "target_dir": self.edit_target.text().strip(),
            "move_excluded_dir": self.edit_excluded.text().strip(),
            "report": self.check_report.isChecked(),
            "dry_run": self.check_dry_run.isChecked(),
        }


class MaskAuditDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("掩码/JSON 审计")
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tab_audit = QWidget()
        self.tab_restore = QWidget()

        self._build_audit_tab()
        self._build_restore_tab()

        self.tabs.addTab(self.tab_audit, "审计")
        self.tabs.addTab(self.tab_restore, "恢复")
        layout.addWidget(self.tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setMinimumWidth(520)

    def _build_audit_tab(self):
        form = QFormLayout(self.tab_audit)

        self.edit_root = QLineEdit()
        btn_root = QPushButton("浏览")
        btn_root.clicked.connect(self._browse_root)
        row_root = QHBoxLayout()
        row_root.addWidget(self.edit_root)
        row_root.addWidget(btn_root)
        form.addRow("root 目录", row_root)

        self.edit_json = QLineEdit()
        btn_json = QPushButton("浏览")
        btn_json.clicked.connect(self._browse_json)
        row_json = QHBoxLayout()
        row_json.addWidget(self.edit_json)
        row_json.addWidget(btn_json)
        form.addRow("标注 JSON", row_json)

        self.edit_report = QLineEdit()
        btn_report = QPushButton("浏览")
        btn_report.clicked.connect(self._browse_report)
        row_report = QHBoxLayout()
        row_report.addWidget(self.edit_report)
        row_report.addWidget(btn_report)
        form.addRow("报告输出", row_report)

        self.combo_quarantine = QComboBox()
        self.combo_quarantine.addItem("仅报告", "none")
        self.combo_quarantine.addItem("复制到隔离区", "copy")
        self.combo_quarantine.addItem("移动到隔离区", "move")
        form.addRow("错误掩码处理", self.combo_quarantine)

        self.edit_quarantine_dir = QLineEdit()
        btn_quarantine = QPushButton("浏览")
        btn_quarantine.clicked.connect(self._browse_quarantine)
        row_quarantine = QHBoxLayout()
        row_quarantine.addWidget(self.edit_quarantine_dir)
        row_quarantine.addWidget(btn_quarantine)
        form.addRow("隔离目录", row_quarantine)

        self.check_corrected = QCheckBox("生成纠正后 JSON")
        self.check_corrected.toggled.connect(self._toggle_corrected)
        form.addRow("纠正 JSON", self.check_corrected)

        self.edit_corrected = QLineEdit()
        btn_corrected = QPushButton("浏览")
        btn_corrected.clicked.connect(self._browse_corrected)
        row_corrected = QHBoxLayout()
        row_corrected.addWidget(self.edit_corrected)
        row_corrected.addWidget(btn_corrected)
        form.addRow("纠正输出", row_corrected)

        self.check_sync_both = QCheckBox("双向同步(有掩码->1, 无掩码->0)")
        form.addRow("同步策略", self.check_sync_both)

        self._toggle_corrected(False)

    def _build_restore_tab(self):
        form = QFormLayout(self.tab_restore)

        self.edit_manifest = QLineEdit()
        btn_manifest = QPushButton("浏览")
        btn_manifest.clicked.connect(self._browse_manifest)
        row_manifest = QHBoxLayout()
        row_manifest.addWidget(self.edit_manifest)
        row_manifest.addWidget(btn_manifest)
        form.addRow("manifest", row_manifest)

        self.check_overwrite = QCheckBox("覆盖已存在文件")
        form.addRow("覆盖", self.check_overwrite)

    def _browse_root(self):
        path = QFileDialog.getExistingDirectory(self, "选择 root 目录")
        if path:
            self.edit_root.setText(path)
            self._fill_default_paths(Path(path))

    def _browse_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 JSON 文件", "", "JSON Files (*.json)")
        if path:
            self.edit_json.setText(path)

    def _browse_report(self):
        start = self.edit_report.text().strip() or "mask_audit_report.json"
        path, _ = QFileDialog.getSaveFileName(self, "输出报告", start, "JSON Files (*.json)")
        if path:
            self.edit_report.setText(path)

    def _browse_quarantine(self):
        path = QFileDialog.getExistingDirectory(self, "选择隔离目录")
        if path:
            self.edit_quarantine_dir.setText(path)

    def _browse_corrected(self):
        start = self.edit_corrected.text().strip() or "labels_corrected.json"
        path, _ = QFileDialog.getSaveFileName(self, "输出纠正 JSON", start, "JSON Files (*.json)")
        if path:
            self.edit_corrected.setText(path)

    def _browse_manifest(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 manifest", "", "JSON Files (*.json)")
        if path:
            self.edit_manifest.setText(path)

    def _fill_default_paths(self, root: Path):
        if not self.edit_report.text().strip():
            self.edit_report.setText(str(root / "mask_audit_report.json"))
        if not self.edit_quarantine_dir.text().strip():
            self.edit_quarantine_dir.setText(str(root / "mask_quarantine"))
        if not self.edit_corrected.text().strip():
            self.edit_corrected.setText(str(root / "labels_corrected.json"))

    def _toggle_corrected(self, checked: bool):
        self.edit_corrected.setEnabled(checked)
        self.check_sync_both.setEnabled(checked)

    def get_values(self):
        mode = "audit" if self.tabs.currentWidget() == self.tab_audit else "restore"
        return {
            "mode": mode,
            "root": self.edit_root.text().strip(),
            "json_path": self.edit_json.text().strip(),
            "report_out": self.edit_report.text().strip(),
            "quarantine_mode": self.combo_quarantine.currentData(),
            "quarantine_dir": self.edit_quarantine_dir.text().strip(),
            "write_corrected": self.check_corrected.isChecked(),
            "corrected_path": self.edit_corrected.text().strip(),
            "sync_both_ways": self.check_sync_both.isChecked(),
            "manifest_path": self.edit_manifest.text().strip(),
            "overwrite": self.check_overwrite.isChecked(),
        }
