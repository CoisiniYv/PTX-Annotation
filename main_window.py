"""主窗口：组织核心状态与各混入模块。"""

import threading
from collections import OrderedDict

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

from actions_mixin import ActionsMixin
from canvas import Canvas
from data_mixin import DataMixin
from icons import IconFactory
from models import ImageEntry, ScanMode
from ui_mixin import UiMixin
from utils import apply_tech_theme


class MedicalLabelPro(QMainWindow, UiMixin, DataMixin, ActionsMixin):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("智能矫正终端CT\\X融合版")
        self.resize(1600, 1000)
        self.setWindowIcon(IconFactory.create_app_icon())

        self.entries: list[ImageEntry] = []
        self.current_idx = -1

        self.orig_root = ""
        self.mask_root = ""

        self.scan_mode = ScanMode.XRAY_SINGLE
        self.autosave_enabled = True
        self.task_json_path = ""
        self.task_entries: list[ImageEntry] = []
        self.task_mode = False
        self.task_case_entries = {}
        self.task_case_order = []
        self.task_key_map = {}
        self.single_pair_mode = False
        self._labels_cache = {}
        self._labels_json_path = ""
        self._labels_dirty = False
        self._labels_debounce_ms = 2000
        self._labels_timer = QTimer(self)
        self._labels_timer.setSingleShot(True)

        apply_tech_theme(QApplication.instance())

        self.canvas = Canvas()
        self.canvas.cursor_info_changed.connect(lambda s: self.status_label.setText(s))
        self.canvas.zoom_changed.connect(
            lambda z: self.statusBar().showMessage(f"缩放: {z:.2f}X", 2000)
        )
        self.canvas.content_modified.connect(self._update_status_ui)

        self._init_ui()
        self._init_toolbar()
        self._init_shortcuts()
        self._init_file_menu()
        self._init_tools_menu()
        self._init_window_menu()
        self._connect_canvas_signals()  # 连接 canvas.file_dropped → _on_mask_file_dropped

        self.status_label = QLabel("系统就绪")
        self.status_label.setStyleSheet(
            "color: #00f0ff; font-weight: bold; padding-right: 20px;"
        )
        self.statusBar().addPermanentWidget(self.status_label)
        self._image_cache = OrderedDict()
        self._cache_lock = threading.Lock()
        self._prefetch_inflight = set()
        self._prefetch_token = 0
        self._mask_pool_enabled = True
        self._mask_pool = []
        self._mask_pool_size = 0
        self._mask_pool_limit = 6
        self._mask_pool_max_shape = None
        self._mask_pool_refs = {}
        self.ct_prefetch_count = 8  # CT 序列内前后预取张数
        self.ct_cross_count = 2  # CT 跨病号预取数
        self.ct_cache_max = 40  # CT 帧缓存上限
        self.xray_prefetch_count = 5  # X光前后病例预取数
        self.xray_cache_max = 12  # X光缓存上限
        self.xray_default_mask_format = "png"  # X光项目级默认掩码格式
        self._settings = QSettings("CheXagent", "Penu")
        self._load_perf_settings()
        self._scan_process = None
        self._scan_queue = None
        self._scan_timer = None
        self._scan_progress = None
        self._scan_token = 0
        self.setAcceptDrops(True)

    def _coerce_int(self, value, default, min_val=None, max_val=None):
        try:
            v = int(value)
        except Exception:
            return default
        if min_val is not None and v < min_val:
            return default
        if max_val is not None and v > max_val:
            return default
        return v

    def _load_perf_settings(self):
        self.ct_prefetch_count = self._coerce_int(
            self._settings.value("ct_prefetch_count"),
            self.ct_prefetch_count,
            1,
            1000,
        )
        self.ct_cross_count = self._coerce_int(
            self._settings.value("ct_cross_count"),
            self.ct_cross_count,
            0,
            200,
        )
        self.ct_cache_max = self._coerce_int(
            self._settings.value("ct_cache_max"),
            self.ct_cache_max,
            1,
            1000,
        )
        self.xray_prefetch_count = self._coerce_int(
            self._settings.value("xray_prefetch_count"),
            self.xray_prefetch_count,
            0,
            200,
        )
        self.xray_cache_max = self._coerce_int(
            self._settings.value("xray_cache_max"),
            self.xray_cache_max,
            1,
            1000,
        )
        fmt = str(
            self._settings.value(
                "xray_default_mask_format",
                getattr(self, "xray_default_mask_format", "png"),
            )
        ).strip().lower()
        self.xray_default_mask_format = "nii" if fmt in ("nii", "nii.gz", "nifti") else "png"

    def _save_perf_settings(self):
        self._settings.setValue("ct_prefetch_count", int(self.ct_prefetch_count))
        self._settings.setValue("ct_cross_count", int(self.ct_cross_count))
        self._settings.setValue("ct_cache_max", int(self.ct_cache_max))
        self._settings.setValue("xray_prefetch_count", int(self.xray_prefetch_count))
        self._settings.setValue("xray_cache_max", int(self.xray_cache_max))
        self._settings.setValue(
            "xray_default_mask_format",
            str(getattr(self, "xray_default_mask_format", "png")),
        )

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        for url in urls:
            path = url.toLocalFile()
            if path:
                self.load_quick_preview(path)
                break
