# 病例列表 / 任务列表 行为说明与需求设计

## 1. 背景与问题

当前应用支持两种工作模式：

- **普通扫描模式（双文件夹 / X 光单张）**
- **任务 JSON 模式**

左侧有两个病例列表：

- 已标注病例列表：`list_annotated`
- 待标注病例列表：`list_todo`

当前逻辑中，只要扫描或加载任务时检测到“已有掩码”，就会把对应病例判定为“已完成标注”，这与实际工作流不完全匹配。

用户希望增加：

1. **批量状态切换**：可多选病例后，使用 Z 键在“已完成”和“待标注”之间批量切换；
2. **病例级重命名 / 删除**：支持直接对“病例名”进行重命名或删除，同时 **同步更新任务 JSON、标签 JSON、状态 JSON**，并在需要时处理磁盘上的文件 / 文件夹；
3. **病例搜索**：支持通过左侧搜索框或 `Ctrl+F` 对当前病例列表进行即时过滤，兼容中文、英文、数字、Windows 路径与相对路径输入。

---

## 2. 现有实现概览

### 2.1 左侧病例列表 UI

文件：`ui_mixin.py`

- 列表控件与搜索框定义（`UiMixin._init_ui`）
  位置：`ui_mixin.py:58-123`

  ```python
  self.case_search_text = ""
  self._case_search_refresh_timer = QTimer(self)
  self._case_search_refresh_timer.setSingleShot(True)
  self._case_search_refresh_timer.timeout.connect(self._apply_case_filter_now)

  self.lbl_case_search = QLabel("病例搜索")
  self.edit_case_search = QLineEdit()
  self.edit_case_search.setPlaceholderText("Ctrl+F 搜索病例名 / 路径（支持模糊匹配）")
  self.edit_case_search.setClearButtonEnabled(True)
  self.edit_case_search.textChanged.connect(self._on_case_search_text_changed)
  self.edit_case_search.returnPressed.connect(self.activate_first_visible_case)

  self.lbl_case_search_hits = QLabel("")

  self.list_annotated = QListWidget()   # 已标注
  self.list_todo = QListWidget()        # 待标注
  self.list_annotated.setSelectionMode(QAbstractItemView.ExtendedSelection)
  self.list_todo.setSelectionMode(QAbstractItemView.ExtendedSelection)

  self.grp_annotated = create_group("已标注病例 (Completed)", self.list_annotated)
  self.grp_todo = create_group("待标注病例 (Todo)", self.list_todo)

  self.list_annotated.itemClicked.connect(self.load_case_sequence)
  self.list_todo.itemClicked.connect(self.load_case_sequence)

  self._bind_case_list_search_hooks(self.list_annotated)
  self._bind_case_list_search_hooks(self.list_todo)
  ```

- 搜索相关方法
  位置：`ui_mixin.py:185-354`

  - `_bind_case_list_search_hooks(lst)`：给列表 model 绑定 `rowsInserted/rowsRemoved/modelReset/layoutChanged/dataChanged`，在病例列表变化后自动重新过滤。
  - `_schedule_case_search_refresh(delay_ms=80)`：使用单次 `QTimer` 做轻量防抖，避免列表频繁变化时重复刷新。
  - `_build_case_item_search_candidates(item)`：基于 `item.text()`、`item.data(Qt.UserRole)`、`item.toolTip()` 生成搜索候选文本。
  - `_filter_case_list_widget(lst, engine)`：逐条调用搜索引擎并通过 `item.setHidden(...)` 过滤显示项。
  - `_apply_case_filter_now()`：同时过滤 `list_annotated` / `list_todo`，并刷新分组标题与命中数标签。
  - `focus_case_search()` / `clear_case_search()` / `activate_first_visible_case()`：分别用于聚焦搜索框、清空搜索、按回车激活第一个可见病例。
  - `update_case_list_headers(...)`：搜索激活时，标题切换为 `visible/total` 形式，如 `Completed: 3/20`、`Todo: 5/80`。

- 文件菜单中相关动作
  位置：`ui_mixin.py:633-686`

  搜索功能不额外占用菜单入口，主要通过左侧搜索框与快捷键触发。

- 快捷键
  位置：`ui_mixin.py:444-463`

  ```python
  QShortcut(QKeySequence("Ctrl+F"), self, self.focus_case_search)
  ```

  按 `Ctrl+F` 可直接聚焦到搜索框，并自动全选已有关键字。

- 模式切换下的搜索状态
  位置：`ui_mixin.py:736-790`

  `_change_scan_mode` 在切换 CT / X 光模式时不会清空搜索框文本，而是保留 `case_search_text`；待新列表建立后会自动重新应用过滤逻辑。

### 2.2 病例搜索实现

文件：`tools/case_search.py`

该模块提供一个轻量、无第三方依赖的病例搜索实现，供左侧病例列表复用。

#### 2.2.1 归一化与候选构建

- `normalize_search_text(value)`：
  - 使用 `unicodedata.normalize("NFKC", ...)` 统一全角/半角；
  - 压缩多余空白；
  - 若输入包含 `\` 或 `/`，先 `os.path.normpath(...)` 再统一成 `/`；
  - 最终使用 `casefold()` 做大小写无关比较。

- `tokenize_search_text(value)`：
  - 以 `\\ / 空格 . _ -` 为分隔符切词；
  - 适合处理诸如病例名、目录名、日期串、文件名组合。

- `digits_only(value)`：
  - 去除所有非数字字符，生成“数字压缩键”；
  - 用于日期、检查号、病例编号等只输部分数字的搜索。

- `build_case_search_candidates(*values)`：
  - 输入通常来自 `item.text()`、`case_name`、`toolTip()`；
  - 会生成以下候选：
    - 原始文本；
    - 归一化文本；
    - Windows / POSIX 路径变体；
    - 路径各级目录名；
    - `basename` / `stem`；
    - 数字压缩键及前 6/8 位前缀；
    - 分词后的 token 与 token 的数字压缩键。

#### 2.2.2 匹配策略

核心类：`CaseSearchEngine`。

当前实现已经从早期“模糊相似度”方案收敛为**精确子串匹配优先**：

- 空查询：视为全部命中；
- 纯数字查询：
  - 支持与 `stem`、`basename`、完整路径数字串、路径段数字串进行精确相等或子串匹配；
  - 适合输入如 `202401`、`0315`、`000123` 快速定位病例；
- 非数字查询：
  - 依次尝试完整归一化文本、`basename`、`stem`、完整路径、路径段的精确相等 / 子串命中；
  - 支持多 token 全命中，如 `张三 ct`、`住院号 2024`；
  - 不再依赖模糊相似度比较，因此行为更稳定、可预期。

虽然 `QLineEdit` 占位文字里仍写着“支持模糊匹配”，但 `tools/case_search.py:3-12` 与 `tools/case_search.py:76-198` 的实际逻辑已经是**标准化后的精确匹配 + 数字串压缩匹配**。

#### 2.2.3 UI 表现

- 搜索是**即时过滤**，不是额外弹窗；
- 过滤通过 `QListWidgetItem.setHidden(True/False)` 完成，不改变原始病例顺序；
- 若某条目在过滤后隐藏，且原本处于选中状态，会自动取消选中，避免批量操作误作用于不可见项；
- 按回车会调用 `activate_first_visible_case()` 直接打开第一个可见病例；
- 命中数显示在搜索框右侧，格式为 `可见数/总数`；
- 搜索激活时，左右分组标题同步显示过滤后的可见数量。

- 分组标题更新（任务模式下显示进度比例）
  位置：`ui_mixin.py:308-354`
  函数：`update_case_list_headers(...)`

  该函数现在同时承担两类显示：
  1. 普通状态下显示原有 `Completed / Todo`；
  2. 搜索状态下显示 `visible/total` 过滤结果。

- 原有列表行为保持不变：搜索仅影响显示层，不改变病例主键、任务状态、标签缓存和导出逻辑。

### 2.3 任务相关核心状态

文件：`main_window.py`

- 构造函数中的任务状态字段
  位置：`main_window.py:18-37`

  ```python
  self.task_json_path = ""
  self.task_entries: list[ImageEntry] = []
  self.task_mode = False
  self.task_case_entries = {}    # case_name -> [ImageEntry, ...]
  self.task_case_order = []      # 病例顺序
  self.task_key_map = {}         # orig_path -> 原始 JSON key
  self._labels_cache = {}        # 标签缓存（普通模式：labels.json；任务模式：任务JSON）
  ```

### 2.4 标签与状态持久化结构

文件：`data_mixin.py`

- 标签文件路径与缓存（`_labels_cache`）
  位置：`data_mixin.py:49-88`

  ```python
  def _get_labels_json_path(self):
      if self.task_mode and self.task_json_path:
          return self.task_json_path
      if not self.orig_root:
          return ""
      return os.path.join(self.orig_root, "pneumothorax_labels.json")
  ```

  - 普通模式：`orig_root/pneumothorax_labels.json`
  - 任务模式：直接使用当前任务 JSON 文件

- 每病例状态文件 `case_status.json`
  位置：`data_mixin.py:92-121`

  ```python
  def _get_status_file_path(self):
      if self.task_mode and self.task_json_path:
          base = os.path.splitext(os.path.basename(self.task_json_path))[0]
          return os.path.join(self.orig_root, f"{base}_case_status.json")
      return os.path.join(self.orig_root, "case_status.json")
  ```

  - 读：`_load_case_status()` `data_mixin.py:98-106`
  - 写：
    - 普通模式单病例：`_save_single_case_status` `data_mixin.py:108-116`
    - 任务模式按病例批量：`_save_task_case_status` `data_mixin.py:117-130`
      遍历 `task_case_entries[case_name]` 对应的 JSON key 写入状态。

### 2.5 普通扫描模式：构造“已完成 / 待标注”列表

文件：`data_mixin.py`

- 扫描入口：`select_orig_dir` / `select_mask_dir` `data_mixin.py:844-862`
  调用 `refresh_lists()`。

- `refresh_lists()` 主流程
  位置：`data_mixin.py:1290-1340`

  ```python
  if not self.orig_root:
      return

  if not self.task_mode:
      self._init_labels_cache()

  if self.task_mode:
      self._build_task_case_lists()
      return

  self.list_annotated.clear()
  self.list_todo.clear()

  status_map = self._load_case_status()
  # 创建后台线程 _internal_scan_worker(...)，再用 QTimer 周期性调用 _poll_scan_result
  ```

- 后台扫描线程 `_internal_scan_worker`
  位置：`data_mixin.py:1184-1235`

  - CT 模式 (`ScanMode.CT_SEQUENCE`)：
    - `case_name` = `orig_root` 下一级子目录名
    - 是否阳性：根据 `_labels_cache` 中以 `case_name + "/"` 开头的 key 是否存在值为 1
    - 是否完成：
      1. 若 `status_map[case_name] == "completed"` → 已完成
      2. 否则若 `mask_root/case_name` 为目录 → 已完成
  - X 光模式 (`ScanMode.XRAY_SINGLE`)：
    - 遍历 `orig_root` 下所有原图文件（过滤掩码）
    - `case_name` = `os.path.relpath(full_path, orig_root).replace("\\", "/")`
    - 是否阳性：`_labels_cache[case_name] == 1`
    - 是否完成：
      1. 若 `status_map[case_name] == "completed"` → 已完成
      2. 否则若 `_resolve_xray_mask_path` 找到掩码且存在 → 已完成

  所有结果汇总为：`found_cases: list[tuple(case_name, is_completed, has_pneumo)]`

- 扫描结果填充列表 `_poll_scan_result`
  位置：`data_mixin.py:1243-1280`

  ```python
  for case, status, has_pneumo in found_cases:
      item = QListWidgetItem(case)
      item.setData(Qt.UserRole, case)
      if has_pneumo:
          item.setForeground(QColor("#ff5555"))
      if status:
          self.list_annotated.addItem(item)  # 已标注
      else:
          self.list_todo.addItem(item)       # 待标注
  ```

> 结论：普通扫描模式下，“是否完成”在无显式状态时，会回退为 **“是否有掩码”**。
  ```python
  act_orig.triggered.connect(self.select_orig_dir)       # 原图目录
  act_mask.triggered.connect(self.select_mask_dir)       # 掩码目录
  act_refresh.triggered.connect(self.refresh_lists)      # 扫描
  act_task.triggered.connect(self.select_task_json)      # 加载任务JSON
  act_exit_task.triggered.connect(self.exit_task_mode)   # 退出任务模式
  ...
  act_export_task.triggered.connect(self.export_task_json)
  act_export_selected_task.triggered.connect(self.export_selected_task_json)
  ```

### 2.2 任务相关核心状态

文件：`main_window.py`

- 构造函数中的任务状态字段
  位置：`main_window.py:18-37`

  ```python
  self.task_json_path = ""
  self.task_entries: list[ImageEntry] = []
  self.task_mode = False
  self.task_case_entries = {}    # case_name -> [ImageEntry, ...]
  self.task_case_order = []      # 病例顺序
  self.task_key_map = {}         # orig_path -> 原始 JSON key
  self._labels_cache = {}        # 标签缓存（普通模式：labels.json；任务模式：任务JSON）
  ```

### 2.3 标签与状态持久化结构

文件：`data_mixin.py`

- 标签文件路径与缓存（`_labels_cache`）
  位置：`data_mixin.py:49-88`

  ```python
  def _get_labels_json_path(self):
      if self.task_mode and self.task_json_path:
          return self.task_json_path
      if not self.orig_root:
          return ""
      return os.path.join(self.orig_root, "pneumothorax_labels.json")
  ```

  - 普通模式：`orig_root/pneumothorax_labels.json`
  - 任务模式：直接使用当前任务 JSON 文件

- 每病例状态文件 `case_status.json`
  位置：`data_mixin.py:92-121`

  ```python
  def _get_status_file_path(self):
      if self.task_mode and self.task_json_path:
          base = os.path.splitext(os.path.basename(self.task_json_path))[0]
          return os.path.join(self.orig_root, f"{base}_case_status.json")
      return os.path.join(self.orig_root, "case_status.json")
  ```

  - 读：`_load_case_status()` `data_mixin.py:98-106`
  - 写：
    - 普通模式单病例：`_save_single_case_status` `data_mixin.py:108-116`
    - 任务模式按病例批量：`_save_task_case_status` `data_mixin.py:117-130`
      遍历 `task_case_entries[case_name]` 对应的 JSON key 写入状态。

### 2.4 普通扫描模式：构造“已完成 / 待标注”列表

文件：`data_mixin.py`

- 扫描入口：`select_orig_dir` / `select_mask_dir` `data_mixin.py:844-862`
  调用 `refresh_lists()`。

- `refresh_lists()` 主流程
  位置：`data_mixin.py:1290-1340`

  ```python
  if not self.orig_root:
      return

  if not self.task_mode:
      self._init_labels_cache()

  if self.task_mode:
      self._build_task_case_lists()
      return

  self.list_annotated.clear()
  self.list_todo.clear()

  status_map = self._load_case_status()
  # 创建后台线程 _internal_scan_worker(...)，再用 QTimer 周期性调用 _poll_scan_result
  ```

- 后台扫描线程 `_internal_scan_worker`
  位置：`data_mixin.py:1184-1235`

  - CT 模式 (`ScanMode.CT_SEQUENCE`)：
    - `case_name` = `orig_root` 下一级子目录名
    - 是否阳性：根据 `_labels_cache` 中以 `case_name + "/"` 开头的 key 是否存在值为 1
    - 是否完成：
      1. 若 `status_map[case_name] == "completed"` → 已完成
      2. 否则若 `mask_root/case_name` 为目录 → 已完成
  - X 光模式 (`ScanMode.XRAY_SINGLE`)：
    - 遍历 `orig_root` 下所有原图文件（过滤掩码）
    - `case_name` = `os.path.relpath(full_path, orig_root).replace("\\", "/")`
    - 是否阳性：`_labels_cache[case_name] == 1`
    - 是否完成：
      1. 若 `status_map[case_name] == "completed"` → 已完成
      2. 否则若 `_resolve_xray_mask_path` 找到掩码且存在 → 已完成

  所有结果汇总为：`found_cases: list[tuple(case_name, is_completed, has_pneumo)]`

- 扫描结果填充列表 `_poll_scan_result`
  位置：`data_mixin.py:1243-1280`

  ```python
  for case, status, has_pneumo in found_cases:
      item = QListWidgetItem(case)
      item.setData(Qt.UserRole, case)
      if has_pneumo:
          item.setForeground(QColor("#ff5555"))
      if status:
          self.list_annotated.addItem(item)  # 已标注
      else:
          self.list_todo.addItem(item)       # 待标注
  ```

> 结论：普通扫描模式下，“是否完成”在无显式状态时，会回退为 **“是否有掩码”**。

### 2.5 任务 JSON 模式：构造“已完成 / 待标注”列表

文件：`data_mixin.py`

- 入口：`select_task_json` `data_mixin.py:863-870`
  选择 JSON 后调用 `load_task_json(path)`。

- 任务加载流程 `load_task_json`
  位置：`data_mixin.py:1100-1121`

  1. `_read_task_json` 读取 dict[key → label]
     `data_mixin.py:953-963`
  2. `_resolve_task_base_dir` 推断 `base_dir`
     `data_mixin.py:965-977`
  3. `_build_task_entries` 构造 `entries` + `task_key_map`
     `data_mixin.py:979-1028`
  4. `_commit_task_context` 写入 `task_*` 状态，开启 `task_mode`
     `data_mixin.py:1030-1049`
  5. `_build_task_case_lists` 基于 `task_case_entries` 构造列表
     `data_mixin.py:1051-1084`
  6. `_refresh_task_progress_ui` 更新任务进度与窗口标题
     `data_mixin.py:734-787`

- 任务模式下构造列表 `_build_task_case_lists`  位置：`data_mixin.py:1051-1084`

  ```python
  status_map = self._load_case_status()

  for case_name in self.task_case_order:
      case_entries = self.task_case_entries.get(case_name, [])
      has_pneumo = any(e.has_pneumothorax == 1 for e in case_entries)

      # 完成判定：先看 case_status，缺省时回退 has_mask
      completed_flags = []
      for entry in case_entries:
          key = self.task_key_map.get(entry.orig_path)
          if key and key in status_map:
              completed_flags.append(status_map.get(key) == "completed")
          else:
              completed_flags.append(entry.has_mask)
      is_completed = all(completed_flags) if completed_flags else False

      item = QListWidgetItem(case_name)
      ...
      if is_completed:
          self.list_annotated.addItem(item)
      else:
          self.list_todo.addItem(item)
  ```

> 结论：任务模式下也存在 **“无状态时，has_mask 即视为完成”** 的回退逻辑。

### 2.6 当前 Z 键行为（批量状态切换）

文件：`ui_mixin.py`, `data_mixin.py`

- 快捷键定义
  位置：`ui_mixin.py:262-263`

  ```python
  sc_toggle = QShortcut(QKeySequence("Z"), self)
  sc_toggle.activated.connect(self.action_toggle_case_status)
  ```

- 实现函数 `action_toggle_case_status`
  位置：`data_mixin.py:1652-1708`

  更新后的核心逻辑：

  1. 如有需要，先保存当前病例掩码并写盘 `_flush_labels_cache()`。
  2. 判定当前“源列表 / 目标列表 / new_status”的逻辑保持不变：
     - 焦点在 `list_todo` → 从“待标注”切到“已完成”；
     - 焦点在 `list_annotated` → 反向；
     - 否则退回到有 `currentItem` 的列表。
  3. 在确定 `current_list` 后：
     - 优先使用 `current_list.selectedItems()` 作为批量操作集合；
     - 若当前无选中项，则退回只对 `currentItem` 操作（兼容旧行为）。
  4. 始终通过 `item.data(Qt.UserRole)` 获取 `case_name` 作为主键，不依赖 `item.text()`，避免被文本标记（如 `[!P]`）影响。
  5. 分模式处理：
     - **任务模式**：
       - 对所有选中的 `case_name` 调用 `_save_task_case_status(case_name, new_status)`；
       - 调用 `_build_task_case_lists()` 重建左右列表；
       - 状态栏提示会区分单个病例和批量病例（显示病例名或“X 个病例”）。
     - **普通扫描模式**：
       - 对所有选中的 item：
         - 从 `current_list` 中移除，加入 `target_list`；
         - 调用 `_save_single_case_status(case_name, new_status)` 写入 `case_status.json`；
       - 将焦点设置到最后一个移动的病例上；
       - 状态栏同样区分单个/多个病例提示。
  6. 最后统一调用 `_refresh_task_progress_ui()` 更新任务进度条、窗口标题和分组标题。

---

## 3. 新功能需求说明

### 3.1 需求一：批量 Z 键切换病例状态

**现状问题**

- `list_annotated` / `list_todo` 已经设置为 `ExtendedSelection`。
- 但 `action_toggle_case_status` 只对一个 `currentItem` 生效，无法批量切换。

**目标**

- 保持 Z 键使用方式不变（按键 → 在当前列表方向上进行“已完成 / 待标注”切换）；
- 支持用户多选病例后，一次按 Z 键可以对所有选中的病例批量更新状态：
  - 普通模式：批量移动列表项并更新 `case_status.json`；
  - 任务模式：批量更新 `{task_base}_case_status.json` 中多个 JSON 条目，并重建列表。

---

### 3.2 需求二：病例重命名与删除（含 JSON 同步）

用户希望：

1. **重命名病例（病例级）**
   - 通过 F2 快捷键或右键菜单触发；
   - 操作的是左侧列表中的“病例名”（`QListWidgetItem.text()` / `UserRole` 中的 `case_name`）；
   - 需要：
     - 真实修改磁盘中的病例文件夹/文件名称；
     - 同步更新：
       - 普通模式标签：`pneumothorax_labels.json`；
       - 普通模式状态：`case_status.json`；
       - 任务模式标签（任务 JSON 文件本身）：`task_json_path` 所指 JSON；
       - 任务模式状态：`{task_base}_case_status.json`；
       - 内存数据结构：`task_case_entries` / `task_entries` / `task_case_order` / `task_key_map`；
     - 最终列表显示新病例名，后续加载、导出、任务模式等完全使用更新后的路径。

2. **删除病例**
   - 右键菜单提供“删除病例”；
   - 至少删除所有 JSON 中该病例相关的信息：
     - 普通模式：标签 JSON + `case_status.json`；
     - 任务模式：任务 JSON + `{task_base}_case_status.json`；
   - 可以有（可配置）是否删除磁盘文件/目录的选项：
     - 默认安全策略：只删除 JSON / 状态，不删除物理文件；
     - 扩展策略：增加“同时删除文件”的提示与选项。
   - UI 上从 `list_todo` / `list_annotated` 中移除该病例项，如果当前正在查看该病例，则清空视图状态。

---

## 4. 设计方案概要

> 下列为后续实现时将参考的设计纲要，不在本阶段改动代码。

### 4.1 批量 Z 键切换设计

**修改点**

- 仍使用 `ui_mixin.py:262-263` 中的 Z 快捷键；
- 修改 `data_mixin.py:1621-1677 action_toggle_case_status` 实现。

**行为设计**

1. 判断当前“源列表 / 目标列表 / new_status”逻辑保持不变（按焦点与 currentItem）。
2. 不再只操作 `currentItem`，而是：

   - 普通模式：
     - 从源列表中取 `selectedItems()`；
     - 对每个病例名 `case_name`：
       - 从源列表中移除对应 item；
       - 加入目标列表；
       - 调用 `_save_single_case_status(case_name, new_status)`。
   - 任务模式：
     - 取当前列表的 `selectedItems()`（病例名列表）；
     - 对每个 `case_name` 调用 `_save_task_case_status(case_name, new_status)`；
     - 最后调用一次 `_build_task_case_lists()` 重建列表。

3. 操作结束后，统一调用 `_refresh_task_progress_ui()` 更新进度栏和窗口标题。

### 4.2 病例重命名 / 删除设计（已部分实现）

#### 4.2.1 UI 交互层

**快捷键与右键菜单**

- F2 快捷键（重命名）：
  - 位置：`ui_mixin.py:253-268`
  - 新增：`QShortcut(QKeySequence("F2"), self, self.rename_selected_case)` → 为后续重命名入口预留。

- 病例列表右键菜单：
  - 位置：`ui_mixin.py:61-70`, `ui_mixin.py:300-399`
  - 对 `list_annotated`、`list_todo` 设置：

    ```python
    self.list_annotated.setContextMenuPolicy(Qt.CustomContextMenu)
    self.list_todo.setContextMenuPolicy(Qt.CustomContextMenu)
    self.list_annotated.customContextMenuRequested.connect(
        lambda pos: self._show_case_list_context_menu(self.list_annotated, pos)
    )
    self.list_todo.customContextMenuRequested.connect(
        lambda pos: self._show_case_list_context_menu(self.list_todo, pos)
    )
    ```

  - 上下文菜单实现：`_show_case_list_context_menu` `ui_mixin.py`（靠近 `_init_tools_menu`）：

    - 菜单项：
      - “重命名病例”
      - “删除病例(仅删任务/状态)”
    - 选中逻辑：
      - 优先使用 `lst.selectedItems()`；若为空，则回退到光标处的单个 `item`；
      - 始终通过 `item.data(Qt.UserRole)` 获取 `case_name`。
    - 重命名行为：
      - 使用 `QInputDialog.getText` 弹出输入框，限定单选病例；
      - 成功后调用 `self.rename_case(current_name, new_name)`；
      - 普通模式下调用 `refresh_lists()`，任务模式下调用 `_build_task_case_lists()`；
      - 最后调用 `_refresh_task_progress_ui()` 刷新进度显示。
    - 删除行为：
      - 对所有选中病例名 `cn` 调用 `self.delete_case(cn, remove_files=False)`，**仅删除任务/标签/状态，不删物理文件**；
      - 同时从 UI 列表中移除对应的 `QListWidgetItem`；
      - 调用 `_refresh_task_progress_ui()` 更新进度与标题。

> 说明：`rename_selected_case` 本身暂未单独实现，高层重命名入口目前通过右键菜单 + `rename_case` 完成。

#### 4.2.2 数据层：删除病例 `delete_case`

文件：`data_mixin.py:117-213` 附近

新增方法：

```python
def delete_case(self, case_name: str, remove_files: bool = False) -> None:
    """删除一个病例的任务/标签/状态记录。

    - 普通模式：
      - 从 pneumothorax_labels.json 中移除该病例相关的所有键；
      - 从 case_status.json 中移除该病例键；
      - 不删除物理文件（remove_files 预留）。
    - 任务模式：
      - 从 task_case_entries / task_entries / task_case_order / task_key_map 中移除；
      - 从任务 JSON(_labels_cache) 与 {task}_case_status.json 中删除对应条目。
    - 如当前正在查看该病例，将画布与病例视图重置为空。
    """
    ...
```

**通用行为**：

- 如果当前病例 (`current_case_name`) 恰好是被删除的病例：
  - 清空 `entries`、`thumbnail_strip`、`current_idx`；
  - 清空 `info_panel`；
  - 重置 `canvas`（base_img/mask/_cache_bg_pixmap/_is_dirty）并刷新画布。

**任务模式 (`self.task_mode == True`)**：

- 内存结构：
  - 取出 `case_entries = task_case_entries[case_name]`；
  - 将所有属于该病例的 `entry` 从 `task_entries` 中移除；
  - 从 `task_case_entries` 字典中删除该病例；
  - 从 `task_case_order` 列表中删除该病例名。
- JSON 层：
  - 确保 `_labels_cache` 已初始化；
  - 加载当前任务状态映射 `status_map = _load_case_status()`；
  - 对每个 `entry`：
    - 找到其 JSON key：`json_key = task_key_map.pop(entry.orig_path, None)`；
    - 删除 `_labels_cache[json_key]`（若存在）；
    - 删除 `status_map[json_key]`（若存在）；
    - 如 `remove_files=True`，尝试删除 `entry.orig_path` 与 `entry.mask_path` 对应物理文件（当前右键菜单默认传入 `False`）。
  - 将 `_labels_cache` 写回（`_labels_dirty=True` + `_flush_labels_cache(force=True)`）；
  - 覆盖写 `{task_base}_case_status.json`：

    ```python
    with open(self._get_status_file_path(), "w", encoding="utf-8") as f:
        json.dump(status_map, f, indent=4, ensure_ascii=False)
    ```

**普通模式 (`self.task_mode == False`)**：

- 标签 JSON（`pneumothorax_labels.json`）：
  - 初始化 `_labels_cache`（如有必要）；
  - 构造病例前缀 `prefix = case_name.rstrip("/")`；
  - 删除所有满足 `k == prefix` 或 `k.startswith(prefix + "/")` 的键；
  - 若有删除，调用 `_schedule_labels_flush()` 延迟写回。
- 状态 JSON（`case_status.json`）：
  - 加载 `status_map = _load_case_status()`；
  - 如果 `case_name` 在 `status_map` 中，则删除该键；
  - 覆盖写回 `case_status.json`。
- 当前右键菜单使用 `remove_files=False`，不触碰物理图像/掩码文件，仅清理标签与状态。

#### 4.2.3 数据层：重命名病例 `rename_case`

文件：`data_mixin.py` 中 `_save_task_case_status` 之后

新增方法：

```python
def rename_case(self, case_name: str, new_case_name: str) -> None:
    """重命名病例标识，并同步更新 JSON 与内存结构。

    目前重点支持 CT 序列模式：
    - 普通模式：
      - 重命名 orig_root 下的病例文件夹；
      - 若是双文件夹模式，则同步重命名 mask_root 下对应文件夹；
      - 更新 pneumothorax_labels.json 与 case_status.json 中的键。
    - 任务模式：
      - 重命名 orig_root 下的病例文件夹（CT）；
      - 更新 task_case_entries / task_entries / task_case_order / task_key_map；
      - 更新任务 JSON(_labels_cache) 与 {task}_case_status.json 中的路径键。

    X 光模式下暂不做物理文件改名，仅更新 JSON 键的 case_name，避免路径歧义。
    """
    ...
```

**普通模式**：

- CT 序列：
  - 物理重命名：

    ```python
    old_dir = os.path.join(self.orig_root, case_name)
    new_dir = os.path.join(self.orig_root, new_case_name)
    if os.path.isdir(old_dir) and not os.path.exists(new_dir):
        os.rename(old_dir, new_dir)

    # 掩码目录（双文件夹模式）
    if is_dual_folder_mode(self.orig_root, self.mask_root) and self.mask_root:
        old_mask_dir = os.path.join(self.mask_root, case_name)
        new_mask_dir = os.path.join(self.mask_root, new_case_name)
        if os.path.isdir(old_mask_dir) and not os.path.exists(new_mask_dir):
            os.rename(old_mask_dir, new_mask_dir)
    ```

  - 标签 JSON 更新：
    - 初始化 `_labels_cache`；
    - 遍历所有键 `k`：
      - 若 `k == case_name` 或以 `"case_name/"` 开头，则切换为 `new_case_name` 前缀：

        ```python
        prefix = case_name.rstrip("/")
        for k, v in labels.items():
            if k == prefix or k.startswith(prefix + "/"):
                suffix = k[len(prefix) :]
                new_k = new_case_name + suffix
                new_labels[new_k] = v
            else:
                new_labels[k] = v
        ```

      - 最终用 `new_labels` 覆盖 `_labels_cache` 并调用 `_schedule_labels_flush()`。

  - 状态 JSON 更新：
    - `status_map = _load_case_status()`；
    - 若 `case_name` 在 `status_map` 中且新名字不存在，则迁移：

      ```python
      status_map[new_case_name] = status_map.pop(case_name)
      ```

    - 覆盖写回 `case_status.json`。

- XRAY 模式：
  - 当前实现仅更新 JSON 层的前缀，不对物理文件路径做重命名（避免复杂路径推断）。

**任务模式**：

- 内存结构更新：
  - 拿到 `case_entries = task_case_entries[case_name]`；
  - 遍历 `task_entries`：
    - 对 `entry.case_name == case_name` 的条目：
      - 保存旧路径 `old_orig = entry.orig_path`；
      - 计算新路径 `new_orig`（CT 模式下通过在 `orig_root` 相对路径上替换病例前缀实现）；
      - 更新：

        ```python
        entry.case_name = new_case_name
        entry.orig_path = new_orig
        rel_norm = os.path.relpath(new_orig, self.orig_root).replace("\\", "/")
        entry.filename = rel_norm
        ```

      - 从 `task_key_map` 中取出旧 JSON key：`json_key = task_key_map.pop(old_orig, None)`；
      - 基于旧 key 形式生成新 key：
        - 旧 key 为绝对路径 → 新 key 用 `new_orig`；
        - 旧 key 为相对路径 → 新 key 用 `rel_norm`；
      - 更新 `task_key_map[new_orig] = new_key_str`；
      - 更新 `_labels_cache` 与 `status_map`：

        ```python
        if old_key_str in labels:
            labels[new_key_str] = labels.pop(old_key_str)

        if old_key_str in status_map and new_key_str not in status_map:
            status_map[new_key_str] = status_map.pop(old_key_str)
        ```

  - 更新 `task_case_entries` / `task_case_order`：
    - `task_case_entries[new_case_name] = task_case_entries.pop(case_name)`；
    - 在 `task_case_order` 中将旧病例名替换为新病例名。

- 物理目录重命名（CT 模式下）：

  ```python
  old_dir = os.path.join(self.orig_root, case_name)
  new_dir = os.path.join(self.orig_root, new_case_name)
  ...  # 与普通模式相同逻辑
  ```

- 最后写回 JSON：
  - `_labels_dirty = True; _flush_labels_cache(force=True)`；
  - 覆盖写 `{task_base}_case_status.json`。

> 注意：任务模式下 X 光场景暂未对物理文件执行重命名，仅更新 JSON 层与内存结构中与 case_name 相关的字段。

4. **任务模式 + X 光单张**

   - 类似 CT 任务模式，但 `case_name` 通常就是一条图像的相对路径：
     - 磁盘：重命名 `orig_path` 对应文件和掩码；
     - 内存：更新 `entry` / `task_case_entries` / `task_entries` / `task_key_map`；
     - JSON：更新任务 JSON 和 case_status 中对应 key；
     - 最后重建列表和进度 UI。

### 4.3 病例删除设计

#### 4.3.1 UI 层

- 右键菜单中增加“删除病例”：
  - 对当前选中的一到多个病例项调用 `delete_case(case_name)` 或批量版本；
  - 弹出确认对话框：
    - 默认仅删除 JSON / 状态；
    - 可选“同时删除磁盘文件”。

#### 4.3.2 数据层 `delete_case`

文件：`data_mixin.py` 新增：

```python
def delete_case(self, case_name: str, *, remove_files: bool = False) -> None:
    ...
```

**普通模式**

- JSON：
  - 标签 JSON（`pneumothorax_labels.json`）：
    - 删除所有属于该病例的 key：
      - CT：前缀为 `case_name + "/"`；
      - XRAY：等于或在该路径子树下的所有 key。
  - 状态 JSON（`case_status.json`）：
    - 删除 `data[case_name]`。
- 文件（可选 `remove_files=True`）：
  - CT：
    - 删除 `orig_root/case_name` 目录；
    - 若为双文件夹模式：删除 `mask_root/case_name` 目录。
  - XRAY：
    - 删除对应图像文件（及掩码）。
- 内存与 UI：
  - 若当前显示病例即 `case_name`：
    - 清空 `entries`、`thumbnail_strip`、`current_idx` 等；
  - 从 `list_todo` / `list_annotated` 中移除该病例条目；
  - 最后调用 `refresh_lists()` 重新扫描与构建列表。

**任务模式**

- 内存：
  - 从 `task_case_entries` 中删除该病例条目；
  - 从 `task_case_order` 中移除该病例名；
  - 在 `task_entries` 中删除所有对应 `entry`；
  - 在 `task_key_map` 中删除相应的 `orig_path` 键。
- JSON：
  - 当前任务 JSON：
    - 根据 `task_key_map` 删除所有属于该病例的 JSON key；
  - `case_status` JSON：
    - 同样删除这些 JSON key 对应的状态记录；
  - 写回：
    - `_flush_labels_cache(force=True)`（任务 JSON）；
    - 覆盖写 `{task_base}_case_status.json`。
- 文件（可选 `remove_files=True`）：
  - 删除全部 `entry.orig_path` 和 `entry.mask_path` 对应文件 / 目录。
- UI：
  - 从 `list_todo` / `list_annotated` 中移除该病例；
  - 若当前病例被删除，则清空视图状态；
  - 调用 `_refresh_task_progress_ui()` 更新进度和标题。

---

## 5. has_mask 自动完成行为的说明

当前行为（扫描与任务模式中）：

- 在没有 explicit case_status 记录时，会使用 “是否有掩码（has_mask）” 作为默认完成判定依据；
- 用户通过 Z 键（未来扩展为批量）更改状态后，相应状态会写入 `case_status.json` 或 `{task_base}_case_status.json`，后续扫描 / 加载仍以 case_status 为优先。

本设计阶段：

- **暂不直接移除 has_mask 的回退逻辑**，避免对已有项目行为造成突变；
- 通过新增的“批量 Z 切换”和“重命名 / 删除 + JSON 同步”功能，让用户可以快速统一管理状态和病例组织；
- 如后续确认需要，可以在单独修改中，将 `_internal_scan_worker` 和 `_build_task_case_lists` 中的“回退到 has_mask”部分移除或换成其他策略。

---

## 6. 后续实现的主要修改点清单

仅列出需要重点关注的函数与文件，便于实现阶段查阅：

- UI 相关：
  - `ui_mixin.py:52-80` — 病例列表 UI 初始化
  - `ui_mixin.py:138-161` — `update_case_list_headers`
  - `ui_mixin.py:253-260` — 常用快捷键
  - `ui_mixin.py:262-263` — Z 键绑定 `action_toggle_case_status`
  - （新增）F2 快捷键、列表右键菜单、`rename_selected_case` / `delete_selected_cases`

- 任务与状态：
  - `main_window.py:18-37` — 任务相关字段定义
  - `main_window.py:97-137` — `_update_task_status_bar` / `_update_window_title`
  - `data_mixin.py:49-88` — `_get_labels_json_path` / `_init_labels_cache` / `_flush_labels_cache`
  - `data_mixin.py:92-121` — 状态文件路径与读写（`_get_status_file_path` / `_load_case_status` / `_save_*_case_status`）

- 列表构造：
  - `data_mixin.py:1184-1235` — `_internal_scan_worker`（扫描模式）
  - `data_mixin.py:1243-1289` — `_poll_scan_result`
  - `data_mixin.py:1290-1340` — `refresh_lists`
  - `data_mixin.py:979-1028` — `_build_task_entries`
  - `data_mixin.py:1030-1049` — `_commit_task_context`
  - `data_mixin.py:1051-1084` — `_build_task_case_lists`

- 状态切换与任务导出：
  - `data_mixin.py:1621-1677` — `action_toggle_case_status`（需要扩展为批量模式）
  - `data_mixin.py:1680-1719` — `export_task_json`
  - `data_mixin.py:871-951` — `export_selected_task_json`

- 将要新增的接口：
  - `data_mixin.py`：
    - `rename_case(self, case_name: str, new_case_name: str) -> None`
    - `delete_case(self, case_name: str, *, remove_files: bool = False) -> None`

---

> 本说明文档用于指导后续实现与评估。
> 如需要，可以按“功能一：批量 Z 切换”、“功能二：重命名 / 删除”的顺序分步骤改动和测试。
