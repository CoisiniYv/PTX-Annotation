"""
界面构建：负责主窗口的 UI 布局与工具栏配置

UI结构说明：
1. 左侧面板：病例列表
   - 已标注病例列表 (list_annotated)
   - 待标注病例列表 (list_todo)
   - 点击病例名称触发 load_case_sequence 加载

2. 中央工作区：
   - 画布 (canvas)：显示图片和掩码，支持标注操作
   - 缩略图栏 (thumbnail_strip)：显示序列中的所有图片
   - 进度滑块 (seek_slider)：快速跳转到序列中的任意位置

3. 右侧面板：
   - 信息面板 (info_panel)：显示DICOM元数据

4. 顶部工具栏：
   - 扫描模式切换 (combo_mode)：CT序列 / X光单张
   - 标注工具：画笔、橡皮、多边形
   - 智能锁定：锁定暗部/亮部区域
   - 可视化控制：反色、透明度、亮度、窗宽窗位

5. 菜单栏：
   - 文件菜单：加载原图/掩码目录、扫描、加载任务JSON、加载单对、保存、导出
   - 窗口菜单：显示/隐藏各个面板、性能设置
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QSlider,
    QSpinBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from icons import IconFactory
from models import ScanMode, ToolType
from widgets import DicomInfoPanel, VisualControlWidget


class UiMixin:
    def _init_ui(self):
        main_splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(main_splitter)

        self.files_widget = QWidget()
        files_layout = QVBoxLayout(self.files_widget)
        files_layout.setContentsMargins(5, 5, 5, 5)

        self.list_annotated = QListWidget()
        self.list_todo = QListWidget()

        def create_group(title, widget):
            grp = QGroupBox(title)
            l = QVBoxLayout(grp)
            l.setContentsMargins(5, 15, 5, 5)
            l.addWidget(widget)
            return grp

        files_layout.addWidget(
            create_group("已标注病例 (Completed)", self.list_annotated)
        )
        files_layout.addWidget(create_group("待标注病例 (Todo)", self.list_todo))

        self.list_annotated.itemClicked.connect(self.load_case_sequence)
        self.list_todo.itemClicked.connect(self.load_case_sequence)

        main_splitter.addWidget(self.files_widget)

        center_right_splitter = QSplitter(Qt.Horizontal)

        workspace_container = QWidget()
        workspace_layout = QVBoxLayout(workspace_container)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)

        v_splitter = QSplitter(Qt.Vertical)
        v_splitter.addWidget(self.canvas)

        self.sequence_container = QWidget()
        sequence_layout = QVBoxLayout(self.sequence_container)
        sequence_layout.setContentsMargins(0, 0, 0, 0)
        sequence_layout.setSpacing(2)

        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(False)

        self.thumbnail_strip = QListWidget()
        self.thumbnail_strip.setObjectName("ThumbnailStrip")
        self.thumbnail_strip.setFixedHeight(110)
        self.thumbnail_strip.setFlow(QListWidget.LeftToRight)
        self.thumbnail_strip.setIconSize(QSize(80, 80))
        self.thumbnail_strip.setSpacing(2)
        self.thumbnail_strip.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # [修复] 原本此处将其设置为了 False，导致缩略图整栏都看不见。已改为 True 显示出来！
        self.thumbnail_strip.setVisible(True)

        self.thumbnail_strip.itemClicked.connect(
            lambda item: self.load_image_at_index(self.thumbnail_strip.row(item))
        )
        self.seek_slider.valueChanged.connect(self.on_slider_change)

        sequence_layout.addWidget(self.seek_slider)
        sequence_layout.addWidget(self.thumbnail_strip)

        v_splitter.addWidget(self.sequence_container)
        v_splitter.setStretchFactor(0, 8)
        v_splitter.setStretchFactor(1, 2)

        workspace_layout.addWidget(v_splitter)

        self.info_panel = DicomInfoPanel()

        center_right_splitter.addWidget(workspace_container)
        center_right_splitter.addWidget(self.info_panel)
        center_right_splitter.setStretchFactor(0, 8)
        center_right_splitter.setStretchFactor(1, 2)

        main_splitter.addWidget(center_right_splitter)
        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 8)

    def _init_toolbar(self):
        tb = QToolBar("主控制台")
        tb.setIconSize(QSize(32, 32))
        tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.addToolBar(Qt.TopToolBarArea, tb)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["  MODE: CT SEQUENCE  ", "  MODE: X-RAY SINGLE  "])
        self.combo_mode.setToolTip("切换扫描模式")
        self.combo_mode.currentIndexChanged.connect(self._change_scan_mode)
        tb.addWidget(self.combo_mode)

        # [关键修复]：确保在界面初始化时，底层变量与下拉框的默认状态一致。
        # 修复“第一次启动加载原图没反应，必须切一下模式才能加载”的Bug。
        self.scan_mode = ScanMode.CT_SEQUENCE

        tb.addSeparator()

        grp = QActionGroup(self)
        self.act_brush = QAction(
            IconFactory.create_tool_icon("笔", "#00f0ff", "circle"), "画笔", self
        )
        self.act_brush.setCheckable(True)
        self.act_brush.setChecked(True)
        self.act_brush.triggered.connect(
            lambda: setattr(self.canvas, "tool", ToolType.BRUSH)
        )
        self.act_brush.setShortcut(QKeySequence("1"))
        tb.addAction(self.act_brush)
        grp.addAction(self.act_brush)

        self.act_eraser = QAction(
            IconFactory.create_tool_icon("擦", "#ff0055", "circle"), "橡皮", self
        )
        self.act_eraser.setCheckable(True)
        self.act_eraser.triggered.connect(
            lambda: setattr(self.canvas, "tool", ToolType.ERASER)
        )
        self.act_eraser.setShortcut(QKeySequence("2"))
        tb.addAction(self.act_eraser)
        grp.addAction(self.act_eraser)

        self.act_poly = QAction(
            IconFactory.create_tool_icon("多", "#00ff00", "circle"), "多边形", self
        )
        self.act_poly.setCheckable(True)
        self.act_poly.triggered.connect(
            lambda: setattr(self.canvas, "tool", ToolType.POLYGON)
        )
        self.act_poly.setShortcut(QKeySequence("3"))
        tb.addAction(self.act_poly)
        grp.addAction(self.act_poly)

        tb.addSeparator()

        self.act_smart = QAction(IconFactory.create_lock_icon(True), "智能锁定", self)
        self.act_smart.setCheckable(True)
        self.act_smart.toggled.connect(self._toggle_smart_lock)
        tb.addAction(self.act_smart)

        self.combo_smart = QComboBox()
        self.combo_smart.addItems(["锁定暗部(气)", "锁定亮部(骨)"])
        self.combo_smart.currentIndexChanged.connect(
            lambda i: setattr(
                self.canvas, "smart_lock_mode", "dark" if i == 0 else "light"
            )
        )
        tb.addWidget(self.combo_smart)

        w_thresh = QWidget()
        l_thresh = QHBoxLayout(w_thresh)
        l_thresh.setContentsMargins(5, 0, 5, 0)
        l_thresh.addWidget(QLabel("阈值:", w_thresh))
        self.spin_thresh = QSpinBox()
        self.spin_thresh.setRange(0, 255)
        self.spin_thresh.setValue(60)
        self.spin_thresh.setFixedWidth(50)
        self.spin_thresh.valueChanged.connect(
            lambda v: setattr(self.canvas, "smart_threshold", v)
        )
        l_thresh.addWidget(self.spin_thresh)
        tb.addWidget(w_thresh)

        tb.addSeparator()

        self.viz_ctrl = VisualControlWidget()
        self.viz_ctrl.valueChanged.connect(self._on_viz_change)
        tb.addWidget(self.viz_ctrl)

    def _init_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+S"), self, self.save_mask)
        QShortcut(QKeySequence("Ctrl+Z"), self, self.canvas.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, self.canvas.redo)
        QShortcut(QKeySequence("A"), self, self.prev_image)
        QShortcut(QKeySequence("D"), self, self.next_image)
        QShortcut(QKeySequence("W"), self, self.prev_case)
        QShortcut(QKeySequence("S"), self, self.next_case)

        sc_toggle = QShortcut(QKeySequence("Z"), self)
        sc_toggle.activated.connect(self.action_toggle_case_status)

        QShortcut(QKeySequence("T"), self, lambda: self._update_pneumo_label(1))
        QShortcut(QKeySequence("F"), self, lambda: self._update_pneumo_label(0))
        QShortcut(QKeySequence("Q"), self, lambda: self._adjust_alpha(-25))
        QShortcut(QKeySequence("E"), self, lambda: self._adjust_alpha(25))

    def _init_window_menu(self):
        menu = self.menuBar().addMenu("窗口")

        act_list = QAction("病例列表", self)
        act_list.setCheckable(True)
        act_list.setChecked(True)
        act_list.toggled.connect(lambda v: self.files_widget.setVisible(v))
        menu.addAction(act_list)

        act_thumb = QAction("缩略图栏", self)
        act_thumb.setCheckable(True)
        act_thumb.setChecked(True)
        act_thumb.toggled.connect(lambda v: self.sequence_container.setVisible(v))
        menu.addAction(act_thumb)

        act_info = QAction("信息面板", self)
        act_info.setCheckable(True)
        act_info.setChecked(True)
        act_info.toggled.connect(lambda v: self.info_panel.setVisible(v))
        menu.addAction(act_info)

        act_perf = QAction("性能设置", self)
        act_perf.triggered.connect(self.open_perf_settings)
        menu.addAction(act_perf)

        act_help = QAction("加载说明", self)
        act_help.triggered.connect(self._show_load_help)
        menu.addAction(act_help)

    def _show_load_help(self):
        text = """数据加载方式说明
一、CT 序列模式（默认）
1) 原图目录 + 掩码目录 + 扫描
   - 扫描规则：原图目录的一级子文件夹 = 1 个病例
   - 进入病例后：递归加载该病例文件夹内的整套序列
   - 支持格式：png / jpg / bmp / tif / dcm
   - 掩码规则：与原图保持相对层级一致，后缀统一为 .png
   - 界面表现：显示缩略图栏和序列滑块
   例：
     原图：D:/CT/images/case_001/0001.dcm
     掩码：D:/CT/masks/case_001/0001.png
2) 加载任务 JSON
   - JSON 的键可以是相对路径或绝对路径
   - CT 模式下会按路径第一层文件夹自动分组为病例
   例：D:/CT/task/ct_task.json
二、X 光单张模式
1) 原图目录 + 掩码目录 + 扫描
   - 扫描规则：每个原图文件 = 1 个病例
   - 为避免把掩码当原图，同名非 PNG 原图存在时，会自动跳过同名 PNG
   - 界面表现：不显示缩略图栏，不启用序列滑块
   例：
     原图：D:/XRAY/images/0001.dcm
     掩码：D:/XRAY/masks/0001.png
2) 加载单对
   - 适合直接打开 1 张原图 + 1 张对应掩码
3) 加载任务 JSON
   - X 光模式下通常按单张路径作为病例键
   例：D:/XRAY/task/xray_task.json

"""

        QMessageBox.information(self, "加载方式说明", text)

    def _init_file_menu(self):
        menu = self.menuBar().addMenu("文件")

        menu_load = menu.addMenu("加载")
        act_orig = QAction("原图目录", self)
        act_orig.triggered.connect(self.select_orig_dir)
        menu_load.addAction(act_orig)

        act_mask = QAction("掩码目录", self)
        act_mask.triggered.connect(self.select_mask_dir)
        menu_load.addAction(act_mask)

        act_refresh = QAction("扫描", self)
        act_refresh.triggered.connect(self.refresh_lists)
        menu_load.addAction(act_refresh)

        act_task = QAction("加载任务JSON", self)
        act_task.triggered.connect(self.select_task_json)
        menu_load.addAction(act_task)

        act_single = QAction("加载单对", self)
        act_single.triggered.connect(self.load_single_pair)
        menu_load.addAction(act_single)

        menu_save = menu.addMenu("保存")
        act_save = QAction("保存", self)
        act_save.triggered.connect(self.save_mask)
        menu_save.addAction(act_save)

        act_autosave = QAction("自动保存", self)
        act_autosave.setCheckable(True)
        act_autosave.setChecked(self.autosave_enabled)
        act_autosave.toggled.connect(lambda v: setattr(self, "autosave_enabled", v))
        menu_save.addAction(act_autosave)

        menu_export = menu.addMenu("导出")
        act_export = QAction("导出", self)
        act_export.triggered.connect(self.export_current)
        menu_export.addAction(act_export)
        menu_export.addSeparator()

        act_export_task = QAction("导出整体任务 JSON", self)
        act_export_task.setToolTip("将当前扫描到的所有影像打包为一个总任务清单")
        act_export_task.triggered.connect(self.export_task_json)
        menu_export.addAction(act_export_task)

    def _on_viz_change(self, type_, val):
        if type_ == "invert":
            setattr(self.canvas, "invert_view", val)
        elif type_ == "alpha":
            setattr(self.canvas, "overlay_alpha", val)
            self.canvas.update()
        elif type_ == "brightness":
            setattr(self.canvas, "brightness", val)
            self.canvas.update()
        elif type_ == "window_center":
            setattr(self.canvas, "window_center", val)
        elif type_ == "window_width":
            setattr(self.canvas, "window_width", val)
        elif type_ == "filter":
            # 映射索引到滤镜类型
            filters = ["None", "CLAHE", "Sharpen", "Smooth"]
            idx = int(val)
            if 0 <= idx < len(filters):
                setattr(self.canvas, "filter_type", filters[idx])
        elif type_ == "filter_strength":
            setattr(self.canvas, "filter_strength", val)

    def _toggle_smart_lock(self, checked):
        self.canvas.smart_lock_enabled = checked
        self.act_smart.setIcon(IconFactory.create_lock_icon(checked))

    def _change_scan_mode(self, idx):
        if self.autosave_enabled and self.current_idx >= 0 and self.canvas._is_dirty:
            self.save_mask()

        self.scan_mode = ScanMode.CT_SEQUENCE if idx == 0 else ScanMode.XRAY_SINGLE
        is_ct = self.scan_mode == ScanMode.CT_SEQUENCE
        self.sequence_container.setVisible(is_ct)

        # 切换模式时清空列表，不自动重新扫描，等待用户主动加载
        self.list_annotated.clear()
        self.list_todo.clear()
        self.entries.clear()
        self.thumbnail_strip.clear()
        self.current_idx = -1
        self.seek_slider.setEnabled(False)

        if hasattr(self, "_reset_cache"):
            self._reset_cache()

        if hasattr(self, "current_case_name"):
            self.current_case_name = ""

        # 清空画布，回到背景状态
        self.canvas.base_img = None
        self.canvas.mask = None
        self.canvas._cache_bg_pixmap = None
        self.canvas._is_dirty = False
        self.canvas.update()

        if hasattr(self.info_panel, "clear"):
            self.info_panel.clear()

        if hasattr(self.viz_ctrl, "set_window_controls"):
            # set_window_controls(center, width, min_val, max_val, enabled)
            self.viz_ctrl.set_window_controls(0, 0, 0, 0, False)
        # 同步 canvas 窗宽窗位状态，防止旧值被新图沿用
        self.canvas.window_center = 0
        self.canvas.window_width = 0

        mode_name = "CT 序列" if is_ct else "X 光单张"
        self.statusBar().showMessage(
            f"已切换至 {mode_name} 模式，请重新加载影像目录", 3000
        )

    def _adjust_alpha(self, delta):
        slider = self.viz_ctrl.slider_alpha
        if slider:
            new_val = max(0, min(255, slider.value() + delta))
            slider.setValue(new_val)
            self.statusBar().showMessage(f"透明度: {new_val}", 1000)
