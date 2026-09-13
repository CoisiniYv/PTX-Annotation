"""
界面构建：负责主窗口的 UI 布局与工具栏配置

UI结构说明：
1. 左侧面板：病例列表
   - 已标注病例列表 (list_annotated)
   - 待标注病例列表 (list_todo)
   - 点击病例名称触发 load_case_sequence 加载
   - 新增病例搜索框：支持 Ctrl+F 聚焦，支持中英文/Windows 路径模糊搜索

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

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QMenu,
    QSlider,
    QSpinBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from icons import IconFactory
from models import ScanMode, ToolType
from tools.case_search import CaseSearchEngine, build_case_search_candidates
from widgets import DicomInfoPanel, VisualControlWidget


class UiMixin:
    def _init_ui(self):
        main_splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(main_splitter)

        self.files_widget = QWidget()
        files_layout = QVBoxLayout(self.files_widget)
        files_layout.setContentsMargins(5, 5, 5, 5)
        files_layout.setSpacing(6)

        self.case_search_text = ""
        self._case_search_refresh_timer = QTimer(self)
        self._case_search_refresh_timer.setSingleShot(True)
        self._case_search_refresh_timer.timeout.connect(self._apply_case_filter_now)

        search_row = QWidget()
        search_layout = QHBoxLayout(search_row)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(6)

        self.lbl_case_search = QLabel("病例搜索")
        self.edit_case_search = QLineEdit()
        self.edit_case_search.setObjectName("CaseSearchEdit")
        self.edit_case_search.setPlaceholderText("Ctrl+F 搜索病例名 / 路径（支持模糊匹配）")
        self.edit_case_search.setClearButtonEnabled(True)
        self.edit_case_search.textChanged.connect(self._on_case_search_text_changed)
        self.edit_case_search.returnPressed.connect(self.activate_first_visible_case)

        self.lbl_case_search_hits = QLabel("")
        self.lbl_case_search_hits.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_case_search_hits.setMinimumWidth(72)

        search_layout.addWidget(self.lbl_case_search)
        search_layout.addWidget(self.edit_case_search, 1)
        search_layout.addWidget(self.lbl_case_search_hits)
        files_layout.addWidget(search_row)

        self.list_annotated = QListWidget()
        self.list_todo = QListWidget()
        self.list_annotated.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_todo.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_annotated.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_todo.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_annotated.customContextMenuRequested.connect(
            lambda pos: self._show_case_list_context_menu(self.list_annotated, pos)
        )
        self.list_todo.customContextMenuRequested.connect(
            lambda pos: self._show_case_list_context_menu(self.list_todo, pos)
        )

        def create_group(title, widget):
            grp = QGroupBox(title)
            l = QVBoxLayout(grp)
            l.setContentsMargins(5, 15, 5, 5)
            l.addWidget(widget)
            return grp

        self.grp_annotated = create_group("已标注病例 (Completed)", self.list_annotated)
        self.grp_todo = create_group("待标注病例 (Todo)", self.list_todo)
        files_layout.addWidget(self.grp_annotated)
        files_layout.addWidget(self.grp_todo)

        self.list_annotated.itemClicked.connect(self.load_case_sequence)
        self.list_todo.itemClicked.connect(self.load_case_sequence)

        self._bind_case_list_search_hooks(self.list_annotated)
        self._bind_case_list_search_hooks(self.list_todo)

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

    # =========================
    # 病例搜索
    # =========================
    def _bind_case_list_search_hooks(self, lst: QListWidget) -> None:
        model = lst.model()
        if model is None:
            return

        model.rowsInserted.connect(lambda *args: self._schedule_case_search_refresh())
        model.rowsRemoved.connect(lambda *args: self._schedule_case_search_refresh())
        model.modelReset.connect(lambda *args: self._schedule_case_search_refresh())
        model.layoutChanged.connect(lambda *args: self._schedule_case_search_refresh())
        model.dataChanged.connect(lambda *args: self._schedule_case_search_refresh())

    def _schedule_case_search_refresh(self, delay_ms: int = 80) -> None:
        timer = getattr(self, "_case_search_refresh_timer", None)
        if timer is not None:
            timer.start(max(0, int(delay_ms)))

    def _iter_case_items(self, lst: QListWidget):
        for i in range(lst.count()):
            yield lst.item(i)

    def _visible_item_count(self, lst: QListWidget) -> int:
        return sum(1 for item in self._iter_case_items(lst) if not item.isHidden())

    def _build_case_item_search_candidates(self, item) -> list[str]:
        case_name = item.data(Qt.UserRole)
        # 数字搜索尽量避免被 statusTip / whatsThis 这类噪声字段污染，
        # 重点使用“用户看得到的名称”和“真实病例标识/路径”。
        return build_case_search_candidates(
            item.text(),
            case_name,
            item.toolTip(),
        )

    def _filter_case_list_widget(self, lst: QListWidget, engine: CaseSearchEngine) -> int:
        visible_count = 0
        for item in self._iter_case_items(lst):
            result = engine.match(self._build_case_item_search_candidates(item))
            matched = result.matched
            item.setHidden(not matched)
            if not matched and item.isSelected():
                item.setSelected(False)
            if matched:
                visible_count += 1
        return visible_count

    def _update_case_search_hit_label(
        self,
        visible_done: int,
        visible_pending: int,
        total_done: int,
        total_pending: int,
    ) -> None:
        visible_total = visible_done + visible_pending
        total = total_done + total_pending
        query = getattr(self, "case_search_text", "").strip()
        if query:
            self.lbl_case_search_hits.setText(f"{visible_total}/{total}")
            self.lbl_case_search_hits.setToolTip(
                f"当前搜索命中 {visible_total} 个病例（已标注 {visible_done}，待标注 {visible_pending}）"
            )
        else:
            self.lbl_case_search_hits.setText("")
            self.lbl_case_search_hits.setToolTip("")

    def _apply_case_filter_now(self) -> None:
        query = getattr(self, "case_search_text", "")
        engine = CaseSearchEngine(query)

        total_done = self.list_annotated.count()
        total_pending = self.list_todo.count()
        visible_done = self._filter_case_list_widget(self.list_annotated, engine)
        visible_pending = self._filter_case_list_widget(self.list_todo, engine)

        self.update_case_list_headers(
            total_cases=total_done + total_pending,
            done_cases=total_done,
            pending_cases=total_pending,
            filtered_done_cases=visible_done,
            filtered_pending_cases=visible_pending,
        )
        self._update_case_search_hit_label(
            visible_done, visible_pending, total_done, total_pending
        )

    def _on_case_search_text_changed(self, text):
        self.case_search_text = "" if text is None else str(text)
        self._schedule_case_search_refresh(60)

    def apply_case_filter(self, text: str | None = None) -> None:
        if text is not None:
            text = str(text)
            if hasattr(self, "edit_case_search") and self.edit_case_search.text() != text:
                prev = self.edit_case_search.blockSignals(True)
                self.edit_case_search.setText(text)
                self.edit_case_search.blockSignals(prev)
            self.case_search_text = text
        else:
            self.case_search_text = self.edit_case_search.text() if hasattr(self, "edit_case_search") else ""

        self._apply_case_filter_now()

    def focus_case_search(self):
        if hasattr(self, "edit_case_search"):
            self.edit_case_search.setFocus(Qt.ShortcutFocusReason)
            self.edit_case_search.selectAll()

    def clear_case_search(self):
        if hasattr(self, "edit_case_search"):
            self.edit_case_search.clear()
        else:
            self.case_search_text = ""
            self._apply_case_filter_now()

    def activate_first_visible_case(self):
        for lst in (self.list_todo, self.list_annotated):
            for item in self._iter_case_items(lst):
                if item.isHidden():
                    continue
                lst.setFocus(Qt.OtherFocusReason)
                lst.setCurrentItem(item)
                self.load_case_sequence(item)
                return

    def update_case_list_headers(
        self,
        total_cases: int | None = None,
        done_cases: int | None = None,
        pending_cases: int | None = None,
        filtered_done_cases: int | None = None,
        filtered_pending_cases: int | None = None,
    ) -> None:
        if total_cases is None or done_cases is None or pending_cases is None:
            done = self.list_annotated.count()
            pending = self.list_todo.count()
            total = done + pending
        else:
            done, pending, total = done_cases, pending_cases, total_cases

        visible_done = (
            filtered_done_cases
            if filtered_done_cases is not None
            else self._visible_item_count(self.list_annotated)
        )
        visible_pending = (
            filtered_pending_cases
            if filtered_pending_cases is not None
            else self._visible_item_count(self.list_todo)
        )
        search_active = bool(getattr(self, "case_search_text", "").strip())

        if hasattr(self, "grp_annotated"):
            if search_active:
                self.grp_annotated.setTitle(
                    f"已标注病例 (Completed: {visible_done}/{done})"
                )
            elif getattr(self, "task_mode", False) and total > 0:
                self.grp_annotated.setTitle(f"已标注病例 (Completed: {done}/{total})")
            else:
                self.grp_annotated.setTitle("已标注病例 (Completed)")

        if hasattr(self, "grp_todo"):
            if search_active:
                self.grp_todo.setTitle(
                    f"待标注病例 (Todo: {visible_pending}/{pending})"
                )
            elif getattr(self, "task_mode", False) and total > 0:
                self.grp_todo.setTitle(f"待标注病例 (Todo: {pending}/{total})")
            else:
                self.grp_todo.setTitle("待标注病例 (Todo)")

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
        QShortcut(QKeySequence("Ctrl+F"), self, self.focus_case_search)
        QShortcut(QKeySequence("A"), self, self.prev_image)
        QShortcut(QKeySequence("D"), self, self.next_image)
        QShortcut(QKeySequence("W"), self, self.prev_case)
        QShortcut(QKeySequence("S"), self, self.next_case)

        sc_toggle = QShortcut(QKeySequence("Z"), self)
        sc_toggle.activated.connect(self.action_toggle_case_status)

        # F2：重命名当前选中病例（单选），后续由 rename_selected_case 协调数据层
        QShortcut(QKeySequence("F2"), self, self.rename_selected_case)

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

    def _get_active_case_list(self):
        if self.list_todo.hasFocus():
            return self.list_todo
        if self.list_annotated.hasFocus():
            return self.list_annotated
        if self.list_todo.currentItem() and not self.list_todo.currentItem().isHidden():
            return self.list_todo
        if self.list_annotated.currentItem() and not self.list_annotated.currentItem().isHidden():
            return self.list_annotated
        for lst in (self.list_todo, self.list_annotated):
            for item in self._iter_case_items(lst):
                if item.isSelected() and not item.isHidden():
                    return lst
        return None

    def rename_selected_case(self):
        lst = self._get_active_case_list()
        if lst is None:
            self.statusBar().showMessage("未选中任何病例", 1000)
            return

        selected_items = [it for it in lst.selectedItems() if not it.isHidden()]
        if not selected_items:
            cur = lst.currentItem()
            if not cur or cur.isHidden():
                self.statusBar().showMessage("未选中任何病例", 1000)
                return
            selected_items = [cur]

        if len(selected_items) != 1:
            QMessageBox.information(self, "提示", "重命名仅支持单选一个病例。")
            return

        item = selected_items[0]
        case_name = item.data(Qt.UserRole)
        if not case_name:
            self.statusBar().showMessage("选中条目没有有效病例标识", 1500)
            return

        new_name, ok = QInputDialog.getText(
            self,
            "重命名病例",
            "新的病例名称:",
            text=str(case_name),
        )
        if not ok:
            return

        new_name = str(new_name).strip()
        if not new_name or new_name == case_name:
            return

        if hasattr(self, "rename_case"):
            self.rename_case(case_name, new_name)

        if getattr(self, "task_mode", False):
            if hasattr(self, "_build_task_case_lists"):
                self._build_task_case_lists()
        else:
            if hasattr(self, "refresh_lists"):
                self.refresh_lists()

        if hasattr(self, "_refresh_task_progress_ui"):
            self._refresh_task_progress_ui()

        self._schedule_case_search_refresh(120)
        self.statusBar().showMessage(f"已重命名: {case_name} -> {new_name}", 2000)

    def delete_selected_cases(self):
        lst = self._get_active_case_list()
        if lst is None:
            self.statusBar().showMessage("未选中任何病例", 1000)
            return

        selected_items = [it for it in lst.selectedItems() if not it.isHidden()]
        if not selected_items:
            cur = lst.currentItem()
            if not cur or cur.isHidden():
                self.statusBar().showMessage("未选中任何病例", 1000)
                return
            selected_items = [cur]

        case_names = []
        seen = set()
        for it in selected_items:
            case_name = it.data(Qt.UserRole)
            if not case_name or case_name in seen:
                continue
            seen.add(case_name)
            case_names.append(case_name)

        if not case_names:
            self.statusBar().showMessage("选中条目没有有效病例标识", 1500)
            return

        msg = f"确认删除 {len(case_names)} 个病例的任务/状态记录吗？\n不会删除物理文件。"
        if (
            QMessageBox.question(self, "确认删除", msg, QMessageBox.Yes | QMessageBox.No)
            != QMessageBox.Yes
        ):
            return

        for case_name in case_names:
            if hasattr(self, "delete_case"):
                self.delete_case(case_name, remove_files=False)

        if getattr(self, "task_mode", False):
            if hasattr(self, "_build_task_case_lists"):
                self._build_task_case_lists()
        else:
            if hasattr(self, "refresh_lists"):
                self.refresh_lists()

        if hasattr(self, "_refresh_task_progress_ui"):
            self._refresh_task_progress_ui()

        self._schedule_case_search_refresh(120)
        self.statusBar().showMessage(f"已删除 {len(case_names)} 个病例记录", 2000)

    def _show_case_list_context_menu(self, lst, pos):
        item = lst.itemAt(pos)
        if item and not item.isHidden() and not item.isSelected():
            lst.clearSelection()
            item.setSelected(True)
            lst.setCurrentItem(item)

        menu = QMenu(self)
        act_rename = menu.addAction("重命名病例")
        act_delete = menu.addAction("删除病例(仅删任务/状态)")

        action = menu.exec(lst.mapToGlobal(pos))
        if not action:
            return

        if action == act_rename:
            self.rename_selected_case()
        elif action == act_delete:
            self.delete_selected_cases()

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

        act_exit_task = QAction("退出任务模式", self)
        act_exit_task.triggered.connect(self.exit_task_mode)
        menu_load.addAction(act_exit_task)

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

        act_export_selected_task = QAction("导出选中病例为任务 JSON", self)
        act_export_selected_task.setToolTip("仅导出当前列表中被选中的病例为任务清单（支持多选）")
        act_export_selected_task.triggered.connect(self.export_selected_task_json)
        menu_export.addAction(act_export_selected_task)

    def _init_tools_menu(self):
        menu = self.menuBar().addMenu("整理操作")

        act_pa_filter = QAction("PA 筛选工具", self)
        act_pa_filter.triggered.connect(self.open_pa_filter_tool)
        menu.addAction(act_pa_filter)

        act_mask_audit = QAction("掩码/JSON 审计工具", self)
        act_mask_audit.triggered.connect(self.open_mask_audit_tool)
        menu.addAction(act_mask_audit)

        # [新功能] 空掩码检测：扫描已有掩码文件，找出内容全零的无效掩码
        act_empty_scan = QAction("空掩码检测", self)
        act_empty_scan.triggered.connect(self.open_empty_mask_scan_tool)
        menu.addAction(act_empty_scan)

    def _show_load_help(self):
        text = (
            "推荐加载方式：\n"
            "1. 选择原图目录\n"
            "2. （可选）选择掩码目录\n"
            "3. 点击“扫描”构建病例列表\n\n"
            "任务模式：点击“加载任务JSON”，将按任务键构建病例列表。\n\n"
            "现在支持 Ctrl+F 搜索当前病例列表，可按病例名、路径、中文目录名进行模糊搜索。"
        )
        QMessageBox.information(self, "加载方式说明", text)

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

        # 不清空搜索输入，仅保留关键字，等待新列表建立后自动重新过滤。
        self.case_search_text = self.edit_case_search.text() if hasattr(self, "edit_case_search") else ""

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

        self.update_case_list_headers(
            total_cases=0,
            done_cases=0,
            pending_cases=0,
            filtered_done_cases=0,
            filtered_pending_cases=0,
        )
        self._update_case_search_hit_label(0, 0, 0, 0)

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