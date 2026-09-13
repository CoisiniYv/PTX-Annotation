# 任务模式与任务 JSON 改动方案（功能 1 / 2 / 4）

> 本文档描述：在现有架构上不大改动前提下，对任务模式与任务 JSON 相关功能做的三项增强：
> 1）任务模式明显标识 + 进度展示；2）导出“选中病例”为任务 JSON；4）任务进度可视化。
> 同时修正若干与现有实现不一致的细节（key 体系、状态切换落点、标签写盘等）。

---

## 功能 1：任务模式明显标识 + 进度展示

### 1.1 窗口标题带任务信息

**改动点**

- 文件：`main_window.py`
- 类：`MedicalLabelPro`

**具体方案**

1. 在 `__init__` 里把硬编码标题改成通过一个助手方法设置：

   ```python
   # 原来：
   # self.setWindowTitle("智能矫正终端CT\\X融合版")

   # 改为在 __init__ 末尾调用：
   self._update_window_title()
   ```

2. 新增私有方法 `_update_window_title(self)`：

   - 根据当前状态决定标题：
     - 非任务模式：`"智能矫正终端CT\\X融合版"`
     - 任务模式（仅当有任务统计数据时）：
       `"智能矫正终端CT\\X融合版 - 任务: {task_name} ({done}/{total})"`
   - `task_name` 取自 `self.task_json_path` 的文件名（去掉扩展名）。
   - `{done}/{total}` 由统一进度刷新入口 `_refresh_task_progress_ui` 提供（见 1.3）。

3. 在下列场景调用 `_update_window_title()`：

   - 成功加载任务 JSON 时（`load_task_json` / `_commit_task_context` 完成后）。
   - 退出任务模式时（`exit_task_mode`，见 1.4）。
   - 每次任务进度变化时（例如切换病例状态，见功能 4）。

---

### 1.2 状态栏展示任务进度

**改动点**

- 文件：`main_window.py`
- 类：`MedicalLabelPro`
- 现状：`__init__` 中已有 `self.status_label` 作为鼠标/脏状态信息栏。

**具体方案**

1. 在 `__init__` 中新增一个永久任务进度标签：

   ```python
   self.task_status_label = QLabel("")
   self.task_status_label.setStyleSheet("color: #ffaa00; padding-right: 10px;")
   self.task_status_label.setVisible(False)
   self.statusBar().addPermanentWidget(self.task_status_label)
   ```

2. 新增方法 `_update_task_status_bar`：

   ```python
   def _update_task_status_bar(
       self,
       *,
       task_name: str,
       done: int,
       total: int,
       positive_cases: int | None = None,
   ) -> None:
       if not self.task_mode or total == 0:
           self.task_status_label.setVisible(False)
           self.task_status_label.clear()
           return

       if positive_cases is None:
           text = f"任务: {task_name} 进度: {done}/{total}"
       else:
           text = f"任务: {task_name} 进度: {done}/{total} (阳性病例: {positive_cases})"

       self.task_status_label.setText(text)
       self.task_status_label.setVisible(True)
   ```

3. 由统一的进度刷新入口 `_refresh_task_progress_ui` 调用 `_update_task_status_bar`（见 1.3）。

---

### 1.3 统一任务进度汇总 + UI 更新入口（DataMixin）

**改动点**

- 文件：`data_mixin.py`
- 类：`DataMixin`（混入到 `MedicalLabelPro`）

**设计目标**

- 集中计算：
  - 总病例数 `total_cases`
  - 已完成病例数 `done_cases`
  - 待标注病例数 `pending_cases`
  - （任务模式下）阳性病例数 `positive_cases`
- 同一入口负责：
  - 更新左侧列表分组标题（见 4.1）；
  - 更新状态栏任务进度（见 1.2）；
  - 更新窗口标题（见 1.1）。

**具体方案**

1. 在 `DataMixin` 中新增 `_refresh_task_progress_ui(self) -> None`：

   ```python
   def _refresh_task_progress_ui(self) -> None:
       # self 实际上是 MedicalLabelPro

       # 非任务模式：只负责把 UI 恢复成普通样式
       if not self.task_mode:
           if hasattr(self, "update_case_list_headers"):
               self.update_case_list_headers()
           if hasattr(self, "_update_task_status_bar"):
               self._update_task_status_bar(
                   task_name="",
                   done=0,
                   total=0,
                   positive_cases=None,
               )
           if hasattr(self, "_update_window_title"):
               self._update_window_title()
           return

       # 任务模式：用列表项数量统计 completed / todo 数量
       done = self.list_annotated.count()
       pending = self.list_todo.count()
       total_cases = done + pending

       # 阳性病例数：基于 task_case_entries 里的 entry.has_pneumothorax 聚合
       positive_cases = 0
       for case_name in getattr(self, "task_case_order", []):
           entries = self.task_case_entries.get(case_name, [])
           if any(e.has_pneumothorax == 1 for e in entries):
               positive_cases += 1

       task_name = ""
       if getattr(self, "task_json_path", ""):
           from pathlib import Path

           task_name = Path(self.task_json_path).stem

       if hasattr(self, "update_case_list_headers"):
           self.update_case_list_headers(
               total_cases=total_cases,
               done_cases=done,
               pending_cases=pending,
           )

       if hasattr(self, "_update_task_status_bar"):
           self._update_task_status_bar(
               task_name=task_name,
               done=done,
               total=total_cases,
               positive_cases=positive_cases,
           )

       if hasattr(self, "_update_window_title"):
           self._update_window_title()
   ```

2. 在以下时机调用 `_refresh_task_progress_ui()`：

   - 任务 JSON 成功加载后：`load_task_json` 中 `_build_task_case_lists()` 完成后。
   - 任务模式下切换病例状态时：`DataMixin.action_toggle_case_status` 完成状态变更后（见 4.3）。
   - 退出任务模式时：`exit_task_mode` 完成状态清理后（见 1.4）。

> 注意：**状态切换逻辑的真正实现位于 `DataMixin.action_toggle_case_status`，`ActionsMixin.action_toggle_case_status` 只是占位空壳。所有刷新进度的钩子必须挂在 `DataMixin` 版本上。**

---

### 1.4 “退出任务模式”菜单项 + 标签 flush

**改动点**

- 文件：`ui_mixin.py`
- 函数：`_init_file_menu`
- 文件：`data_mixin.py` 或 `actions_mixin.py`（实现逻辑，推荐放 `DataMixin`）

**菜单项**

在“文件”菜单中增加一个动作：

```python
act_exit_task = QAction("退出任务模式", self)
act_exit_task.triggered.connect(self.exit_task_mode)
menu.addAction(act_exit_task)
```

**exit_task_mode 逻辑**

实现 `exit_task_mode(self)`（建议放在 `DataMixin`）：

1. 首先强制写盘标签缓存，避免防抖导致的最后一批标签丢失：

   ```python
   if hasattr(self, "_flush_labels_cache"):
       self._flush_labels_cache(force=True)
   ```

2. 若 `not self.task_mode`：

   ```python
   QMessageBox.information(self, "提示", "当前不在任务模式。")
   return
   ```

3. 清理任务相关字段：

   ```python
   self.task_mode = False
   self.task_json_path = ""
   self.task_entries = []
   self.task_case_entries.clear()
   self.task_case_order.clear()
   self.task_key_map.clear()
   ```

4. 清空 UI 列表及当前病例状态：

   ```python
   self.list_annotated.clear()
   self.list_todo.clear()
   self.entries.clear()
   self.current_idx = -1
   self.thumbnail_strip.clear()
   if hasattr(self, "current_case_name"):
       self.current_case_name = ""
   ```

5. 弹提示："已退出任务模式，请重新扫描影像目录。"

6. 调用 `_refresh_task_progress_ui()`，确保标题 / 状态栏 / 分组标题恢复到普通模式。

> 是否自动重新扫描：建议**不自动**调用 `refresh_lists`，只弹提示，让用户手动点击“扫描”，行为更可预期。

---

## 功能 2：导出“选中病例”为任务 JSON

### 2.1 菜单项

**改动点**

- 文件：`ui_mixin.py`
- 函数：`_init_file_menu`

**具体方案**

在「导出」子菜单中，新增一条动作（紧挨着“导出整体任务 JSON”）：

```python
act_export_selected_task = QAction("导出选中病例为任务 JSON", self)
act_export_selected_task.setToolTip("仅导出当前列表中被选中的病例为任务清单（支持多选）")
act_export_selected_task.triggered.connect(self.export_selected_task_json)
menu_export.addAction(act_export_selected_task)
```

---

### 2.2 列表多选模式（配合 selectedItems）

**改动点**

- 文件：`ui_mixin.py`
- 函数：`_init_ui`

**具体方案**

1. 引入 `QAbstractItemView`：

   ```python
   from PySide6.QtWidgets import (
       ...,
       QAbstractItemView,
       ...,
   )
   ```

2. 初始化病例列表后开启扩展多选：

   ```python
   self.list_annotated = QListWidget()
   self.list_todo = QListWidget()
   self.list_annotated.setSelectionMode(QAbstractItemView.ExtendedSelection)
   self.list_todo.setSelectionMode(QAbstractItemView.ExtendedSelection)
   ```

> 说明：这样用户可以按 Ctrl/Shift 框选多条病例，`selectedItems()` 的语义才是真正的“选中子集”。

---

### 2.3 数据收集 + 导出逻辑（按模式区分）

**改动点**

- 文件：`data_mixin.py`
- 函数：新增 `export_selected_task_json(self)`

**统一原则**

- **只使用 `item.data(Qt.UserRole)` 作为逻辑 key，不再使用 `item.text()` 参与任何 key 计算。**
- 任务 JSON 的 key 语义与 `load_task_json` 完全对齐：
  - CT 模式：按 **图像相对路径（per-image）**；
  - X 光模式：按 **图像相对路径（当前实现 case_name 即此语义）**；
  - 任务模式：按 **原任务 JSON 的 key（`task_key_map`）**。

**具体方案**

1. 收集选中病例名（列表层面）：

   ```python
   selected_items = list(self.list_annotated.selectedItems()) + list(self.list_todo.selectedItems())
   if not selected_items:
       QMessageBox.information(self, "提示", "请先在病例列表中选择至少一个病例。")
       return

   selected_case_names = []
   for item in selected_items:
       case_name = item.data(Qt.UserRole)
       if not case_name:
           continue
       selected_case_names.append(case_name)

   if not selected_case_names:
       QMessageBox.information(self, "提示", "选中的条目没有有效病例标识。")
       return
   ```

2. 构造任务 JSON：根据当前模式分三种情况。

#### 2.3.1 普通模式 + CT 序列（ScanMode.CT_SEQUENCE）

- 现有 `export_task_json` 在 CT 模式下是“按病例名（目录）当 key”，**无法被 `load_task_json` 正确回灌**。新功能不再沿用这个方案。
- 新方案：
  - 先按病例展开成 `ImageEntry` 列表，再按“图像相对路径”写入任务 JSON。

伪代码：

```python
from pathlib import Path

base_dir = self.orig_root

for case_name in selected_case_names:
    # 按病例展开成切片级 entries
    entries = self._build_ct_case_entries(case_name)
    for entry in entries:
        rel_src = os.path.relpath(entry.orig_path, base_dir).replace("\\", "/")
        has_pneumo = entry.has_pneumothorax
        # 如果 labels_cache 有覆盖，以缓存为准
        has_pneumo = int(self._labels_cache.get(rel_src, has_pneumo))
        task_dict[rel_src] = has_pneumo
```

这样生成的 JSON 与 `load_task_json` 的 CT 分支所使用的 key 完全一致，可以直接回灌。

#### 2.3.2 普通模式 + X 光单张（ScanMode.XRAY_SINGLE）

- 当前扫描逻辑中，X 光模式下左侧列表的 `UserRole` 就是：
  `case_name = relpath(full_src, orig_root).replace("\\", "/")`。
- 新功能里，直接把这个 `case_name` 当作 JSON key 即可。

伪代码：

```python
base_dir = self.orig_root  # 仅用于推断 labels_cache key

for case_name in selected_case_names:
    rel_src = str(case_name).replace("\\", "/")
    has_pneumo = int(self._labels_cache.get(rel_src, 0))
    task_dict[rel_src] = has_pneumo
```

#### 2.3.3 任务模式（self.task_mode == True）

- 任务模式下应尽量保持与原任务 JSON key 完全一致，不能重新推断。
- 方案：
  - 对每个选中病例名 `case_name`：
    - 取 `case_entries = self.task_case_entries.get(case_name, [])`；
    - 对每个 `entry`：
      - key：`json_key = self.task_key_map.get(entry.orig_path)`；
      - label：优先 `entry.has_pneumothorax`，如 `_labels_cache` 中有覆盖则使用覆盖值。

伪代码：

```python
for case_name in selected_case_names:
    case_entries = self.task_case_entries.get(case_name, [])
    for entry in case_entries:
        json_key = self.task_key_map.get(entry.orig_path)
        if not json_key:
            continue
        json_key_str = str(json_key).replace("\\", "/")
        has_pneumo = entry.has_pneumothorax
        has_pneumo = int(self._labels_cache.get(json_key_str, has_pneumo))
        task_dict[json_key_str] = has_pneumo
```

3. 询问保存路径 + 写 JSON：

- 文件对话框逻辑复用现有 `export_task_json`：

  ```python
  default_name = "task_selected.json"
  if self.task_mode and self.task_json_path:
      from pathlib import Path
      base = Path(self.task_json_path).stem
      default_name = f"{base}_subset.json"

  default_save_path = os.path.join(self.orig_root or "", default_name)
  save_path, _ = QFileDialog.getSaveFileName(
      self,
      "导出子任务 JSON",
      default_save_path,
      "JSON Files (*.json)",
  )
  ```

- 写文件时可重用当前实现中的简单写法，后续如需要再统一成“临时文件 + 覆盖”的安全写入模式：

  ```python
  if save_path:
      with open(save_path, "w", encoding="utf-8") as f:
          json.dump(task_dict, f, indent=4, ensure_ascii=False)
      self.statusBar().showMessage(
          f"成功导出子任务 JSON: {os.path.basename(save_path)}", 5000
      )
  ```

---

## 功能 4：任务进度可视化（列表标题 & 汇总）

### 4.1 左侧分组标题带进度数字

**改动点**

- 文件：`ui_mixin.py`
- 函数：`_init_ui`

**具体方案**

1. 保存病例列表的分组框引用：

   ```python
   self.grp_annotated = create_group("已标注病例 (Completed)", self.list_annotated)
   self.grp_todo = create_group("待标注病例 (Todo)", self.list_todo)
   files_layout.addWidget(self.grp_annotated)
   files_layout.addWidget(self.grp_todo)
   ```

2. 新增一个 UI 辅助方法，用于更新标题（实现在 `UiMixin` 内）：

   ```python
   def update_case_list_headers(
       self,
       total_cases: int | None = None,
       done_cases: int | None = None,
       pending_cases: int | None = None,
   ) -> None:
       # 默认使用当前列表数量
       if total_cases is None or done_cases is None or pending_cases is None:
           done = self.list_annotated.count()
           pending = self.list_todo.count()
           total = done + pending
       else:
           done, pending, total = done_cases, pending_cases, total_cases

       if hasattr(self, "grp_annotated"):
           if self.task_mode and total > 0:
               self.grp_annotated.setTitle(f"已标注病例 (Completed: {done}/{total})")
           else:
               self.grp_annotated.setTitle("已标注病例 (Completed)")

       if hasattr(self, "grp_todo"):
           if self.task_mode and total > 0:
               self.grp_todo.setTitle(f"待标注病例 (Todo: {pending}/{total})")
           else:
               self.grp_todo.setTitle("待标注病例 (Todo)")
   ```

3. 在 `_refresh_task_progress_ui` 中调用 `update_case_list_headers(...)`，如 1.3 所述，让标题随任务进度实时变化。

---

### 4.2 阳性病例数统计（基于 task_case_entries）

**改动点**

- 文件：`data_mixin.py`
- 函数：`_refresh_task_progress_ui`

**具体方案**

- 不再尝试用列表项的文本/键去匹配 `_labels_cache`，而是完全依赖 `task_case_entries` 中 `ImageEntry.has_pneumothorax` 字段进行病例级聚合：

  ```python
  positive_cases = 0
  for case_name in getattr(self, "task_case_order", []):
      entries = self.task_case_entries.get(case_name, [])
      if any(e.has_pneumothorax == 1 for e in entries):
          positive_cases += 1
  ```

- 聚合结果由 `_refresh_task_progress_ui` 传给 `_update_task_status_bar`，不再在 UI 层重新推导。

> 如未来需要在普通模式下也展示阳性统计，可以采用类似做法：在扫描完成后立即构建一个 `{case_name: has_positive}` 映射并缓存，而不是在 UI 上用列表文本和 `_labels_cache` 混拼。

---

### 4.3 与病例状态切换联动（正确挂点）

**改动点**

- 文件：`data_mixin.py`
- 函数：`action_toggle_case_status`（真正生效的版本）

**当前实现要点**

- 非任务模式：
  - 在两个列表之间移动当前病例 item；
  - 写入单例状态 JSON：`_save_single_case_status(case_name, new_status)`。
- 任务模式：
  - 通过 `_save_task_case_status(case_name, new_status)` 保存每个 entry 的状态；
  - 重新调用 `_build_task_case_lists()` 刷新 Todo/Done 列表。

**新增联动**

在 `DataMixin.action_toggle_case_status` 末尾（任务模式和普通模式分支各自完成状态更新之后）统一加上一行：

```python
if hasattr(self, "_refresh_task_progress_ui"):
    self._refresh_task_progress_ui()
```

- 任务模式下：
  - `_build_task_case_lists()` 已经重新构造了左右列表，`_refresh_task_progress_ui` 会基于最新列表和 `task_case_entries` 重新计算进度和阳性数。
- 非任务模式下：
  - `_refresh_task_progress_ui` 会走“非任务模式”分支，只负责把分组标题/任务状态栏/标题恢复/清空，不会出错。

> 再次强调：**真正需要修改的是 `DataMixin.action_toggle_case_status`（data_mixin.py 中的实现），`ActionsMixin.action_toggle_case_status` 只是为了防止快捷键崩溃的空壳。所有与状态切换联动的逻辑都应挂在 DataMixin 版本上。**

---

## 总结

- 功能 1：通过 `_update_window_title` + `task_status_label` + `_refresh_task_progress_ui`，让任务模式在标题栏和状态栏上都有清晰的“当前任务 + 进度 + 阳性病例数”展示，并在退出任务模式时自动恢复。
- 功能 2：新增“导出选中病例为任务 JSON”，
  - 明确统一 key 语义：
    - CT / X-ray 普通模式用图像相对路径；
    - 任务模式用原任务 JSON 的 key；
  - 列表开启多选模式，以支持真正的“子集任务”导出。
- 功能 4：
  - 左侧分组标题带上 `Completed: x/y` 与 `Todo: z/y`；
  - 阳性病例数基于 `task_case_entries` 聚合；
  - 在 `DataMixin.action_toggle_case_status` 中统一挂钩 `_refresh_task_progress_ui`，保证状态变化立即反映到 UI。

上述设计在不打破现有 CT/X 光扫描和任务加载逻辑的前提下，把任务模式的可见性、可操作性和可回灌性补齐，后续可以按本文档直接落地代码实现。