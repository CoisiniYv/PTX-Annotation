"""主窗口：组合 UI、数据与交互模块，并持有共享运行状态。"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

from actions_mixin import ActionsMixin
from app_config import (
    APP_DISPLAY_NAME,
    PERFORMANCE_DEFAULTS,
    QT_SETTINGS_APPLICATION,
    QT_SETTINGS_ORGANIZATION,
)
from canvas import Canvas
from data_mixin import DataMixin
from models import ImageEntry, ScanMode
from ui_mixin import UiMixin
from utils import apply_tech_theme


class MedicalLabelPro(QMainWindow, UiMixin, DataMixin, ActionsMixin):
    """PTX Annotation 主窗口。

    ``UiMixin`` 负责界面构建，``DataMixin`` 负责扫描/加载/缓存，
    ``ActionsMixin`` 负责保存、导出和用户交互。主窗口仅组织这些能力并维护
    跨模块共享状态，避免把所有初始化逻辑继续堆在一个超长 ``__init__`` 中。
    """

    def __init__(self):
        super().__init__()

        self._init_domain_state()
        apply_tech_theme(QApplication.instance())

        self._init_canvas()
        self._init_status_widgets()
        self._init_ui()
        self._init_toolbar()
        self._init_shortcuts()
        self._init_file_menu()
        self._init_tools_menu()
        self._init_window_menu()
        self._connect_canvas_signals()

        self._init_performance_state()
        self._init_scan_state()

        self.setAcceptDrops(True)
        self._update_window_title()

    def _init_domain_state(self) -> None:
        """初始化病例、任务和标签等业务状态。"""

        self.entries: list[ImageEntry] = []
        self.current_idx = -1

        self.orig_root = ""
        self.mask_root = ""

        # 与工具栏首项保持一致，避免启动时 UI 显示 CT、内部却仍是 X 光模式。
        self.scan_mode = ScanMode.CT_SEQUENCE
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

    def _init_canvas(self) -> None:
        """创建标注画布并连接窗口级信号。"""

        self.canvas = Canvas()
        self.canvas.cursor_info_changed.connect(lambda s: self.status_label.setText(s))
        self.canvas.zoom_changed.connect(
            lambda z: self.statusBar().showMessage(f"缩放: {z:.2f}X", 2000)
        )
        self.canvas.content_modified.connect(self._update_status_ui)

    def _init_status_widgets(self) -> None:
        """初始化底部状态栏。"""

        self.status_label = QLabel("系统就绪")
        self.status_label.setStyleSheet(
            "color: #00f0ff; font-weight: bold; padding-right: 20px;"
        )

        self.task_status_label = QLabel("")
        self.task_status_label.setStyleSheet("color: #ffaa00; padding-right: 10px;")
        self.task_status_label.setVisible(False)

        self.statusBar().addPermanentWidget(self.task_status_label)
        self.statusBar().addPermanentWidget(self.status_label)

    def _init_performance_state(self) -> None:
        """初始化缓存、预取及持久化性能设置。"""

        defaults = PERFORMANCE_DEFAULTS

        self._image_cache = OrderedDict()
        self._cache_lock = threading.Lock()
        self._prefetch_inflight = set()
        self._prefetch_token = 0

        self._mask_pool_enabled = True
        self._mask_pool = []
        self._mask_pool_size = 0
        self._mask_pool_limit = defaults.mask_pool_limit
        self._mask_pool_max_shape = None
        self._mask_pool_refs = {}

        self.ct_prefetch_count = defaults.ct_prefetch_count
        self.ct_cross_count = defaults.ct_cross_count
        self.ct_cache_max = defaults.ct_cache_max
        self.xray_prefetch_count = defaults.xray_prefetch_count
        self.xray_cache_max = defaults.xray_cache_max
        self.xray_default_mask_format = defaults.xray_default_mask_format

        # 沿用旧命名空间，确保升级后仍能读取用户已有设置。
        self._settings = QSettings(
            QT_SETTINGS_ORGANIZATION,
            QT_SETTINGS_APPLICATION,
        )
        self._load_perf_settings()

    def _init_scan_state(self) -> None:
        """初始化后台扫描流程状态。"""

        self._scan_process = None
        self._scan_queue = None
        self._scan_timer = None
        self._scan_progress = None
        self._scan_token = 0

    def _update_task_status_bar(
        self,
        *,
        task_name,
        done,
        total,
        positive_cases=None,
    ):
        if not getattr(self, "task_mode", False) or total == 0:
            if hasattr(self, "task_status_label"):
                self.task_status_label.setVisible(False)
                self.task_status_label.clear()
            return

        if positive_cases is None:
            text = f"任务: {task_name} 进度: {done}/{total}"
        else:
            text = f"任务: {task_name} 进度: {done}/{total} (阳性病例: {positive_cases})"

        if hasattr(self, "task_status_label"):
            self.task_status_label.setText(text)
            self.task_status_label.setVisible(True)

    def _update_window_title(self):
        if not getattr(self, "task_mode", False):
            self.setWindowTitle(APP_DISPLAY_NAME)
            return

        done = self.list_annotated.count()
        pending = self.list_todo.count()
        total = done + pending

        if total <= 0 or not getattr(self, "task_json_path", ""):
            self.setWindowTitle(APP_DISPLAY_NAME)
            return

        task_name = Path(self.task_json_path).stem
        self.setWindowTitle(
            f"{APP_DISPLAY_NAME} - 任务: {task_name} ({done}/{total})"
        )

    @staticmethod
    def _coerce_int(value, default, min_val=None, max_val=None):
        try:
            result = int(value)
        except (TypeError, ValueError):
            return default
        if min_val is not None and result < min_val:
            return default
        if max_val is not None and result > max_val:
            return default
        return result

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
        self.xray_default_mask_format = (
            "nii" if fmt in ("nii", "nii.gz", "nifti") else "png"
        )

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
            event.ignore()
            return

        for url in urls:
            path = url.toLocalFile()
            if not path:
                continue
            self.load_quick_preview(path)
            event.acceptProposedAction()
            return

        event.ignore()
