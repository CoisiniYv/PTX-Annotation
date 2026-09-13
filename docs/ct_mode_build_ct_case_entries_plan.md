# CT 模式 `_build_ct_case_entries` 与文档修正设计方案

> 版本：2026-03-24
> 相关文件：`CLAUDE.md`、`data_mixin.py`、`actions_mixin.py`、`tools/pa_filter.py`、`docs/CT标注修复.py`

---

## 1. 背景

当前主工程中，CLAUDE.md 对 CT 序列模式与相关工具的描述和实际代码存在若干不一致之处，尤其是：

- CT 模式病例展开函数 `_build_ct_case_entries` 的实现不完整或未按文档约定工作；
- 文档中将“加载任务 JSON”与“目录扫描”描述为同一条管线，容易误导后续维护；
- PA 筛选工具对“复制/移动非 PA 文件”的表述与真实行为不符；
- 拖拽掩码到画布时，文档宣称会更新缓存，但实际只更新当前帧与条目元信息，LRU 图像缓存仍在保存阶段统一更新。

本方案的目标是：

1. 统一 CLAUDE.md 与现有代码的真实行为；
2. 为补全 `_build_ct_case_entries` 提供清晰设计，复用 `docs/CT标注修复.py` 中已验证的 CT 扩展逻辑；
3. 保证现有 LRU 缓存与预取机制、X 光模式行为不受负面影响；
4. 为后续实现任务提供明确步骤。

---

## 2. 当前问题概览

### 2.1 `_build_ct_case_entries` 描述与实现不一致

- CLAUDE.md 中写到：
  - `DataMixin._build_ct_case_entries` 在 CT 模式下：
    - 从 `orig_root/case_name`（或 `Root`）递归扫描符合 `CT_SOURCE_EXTENSIONS` 的原图文件；
    - 使用 `_resolve_ct_mask_path` 推断掩码路径；
    - 构造该病例内的 `ImageEntry` 列表；
    - `_build_case_entries/_expand_case_to_entries` 在 CT 模式下会调用该函数。
- 实际代码：
  - `_build_case_entries/_expand_case_to_entries` 确实依赖 `_build_ct_case_entries(case_name)`；
  - 但 `_build_ct_case_entries` 的逻辑尚未完整实现上述步骤（或仅为占位），导致 CT 模式病例展开能力不足。

### 2.2 任务 JSON 与目录扫描的流程混淆

- CLAUDE.md 在“扫描功能（点击“扫描”或加载任务 JSON 时驱动）”中，将“点击扫描”和“加载任务 JSON”放在同一段描述：
  - 暗示两者都走 `refresh_lists → _internal_scan_worker → _poll_scan_result` 这条后台扫描管线；
- 实际代码：
  - 目录扫描（普通模式）走 `refresh_lists → _internal_scan_worker → _poll_scan_result`；
  - 任务 JSON 加载走 `load_task_json → _build_task_entries → _commit_task_context → _build_task_case_lists`，完全不调用 `refresh_lists`。

### 2.3 PA 筛选复制 / 移动行为描述不准确

- CLAUDE.md：
  - 写道 `PaFilterDialog + _start_pa_filter_task/_pa_filter_worker` “可选择复制/移动非 PA 文件并生成报告”；
- 实际代码：
  - PA 文件：可复制到 `target_dir`（`copy_pa_files`）；
  - 非 PA 文件：可移动到 `move_excluded_dir`（`move_files_preserving_structure`）；
  - 没有“复制非 PA 文件”的分支。

### 2.4 拖拽掩码时“更新缓存”的表述不严谨

- CLAUDE.md：
  - 在 ActionsMixin 部分写道 `_connect_canvas_signals` 连接 `canvas.file_dropped → _on_mask_file_dropped`，
  - 并称“自动 resize 对齐并更新 `ImageEntry.mask_path` 与缓存”。
- 实际代码：
  - `_on_mask_file_dropped`：
    - 读入并 resize 掩码；
    - 更新 `canvas.mask` 与 `ImageEntry.mask_path/has_mask`；
    - 清理部分 X-ray 相关缓存（如 `_xray_dir_match_cache`）；
    - **不会**即时更新 LRU 图像缓存 `_image_cache`；
  - LRU 缓存更新发生在 `save_mask` 内部：重建 payload 后调用 `_cache_set`。

---

## 3. 设计目标

1. **CT 模式可用且行为清晰**
   - `_build_ct_case_entries` 能够稳定、正确地为每个 CT 病例构建完整序列 `ImageEntry` 列表；
   - 支持递归目录、自然排序和多种图像格式（含 DICOM / PNG / JPG / BMP / TIFF 等）。

2. **保持现有架构与其它模式不被破坏**
   - 不修改 X 光单张模式的扫描与病例展开逻辑；
   - 不破坏现有 LRU 缓存 (`_image_cache`) 与预取机制；
   - 不引入与当前任务模式（task_mode）相冲突的假设。

3. **文档准确反映代码现实**
   - CLAUDE.md 的结构说明与具体行为描述可作为后续维护的“单一真相源（source of truth）”；
   - 针对历史遗留差异，在文档中明确标注注意事项 / TODO，避免误导后续开发者。

---

## 4. CLAUDE.md 的调整方案

### 4.1 新增「已知注意事项 / TODO」小节

在 `CLAUDE.md` 中「## 和 Claude Code 协作约定」前新增一节，例如：

```markdown
## 已知注意事项 / TODO

- CT 序列病例展开实现（`_build_ct_case_entries`）
  - 当前 `data_mixin.py` 中已经存在 `_build_ct_case_entries` 的声明和调用，但实现逻辑尚未完全对齐文档：
    - 递归扫描 CT 序列时还未统一使用 `CT_SOURCE_EXTENSIONS`；
    - 与 `_resolve_ct_mask_path` 的结合逻辑需进一步完善，以确保每个切片都能正确匹配到掩码。
  - TODO：补齐 `_build_ct_case_entries` 实现，并保证 CT 模式下 `load_case_sequence/_expand_case_to_entries` 正常工作。

- 任务 JSON 与目录扫描是两套独立流程
  - 目录扫描走 `refresh_lists → _internal_scan_worker → _poll_scan_result`；
  - 任务 JSON 走 `load_task_json → _build_task_entries/_build_task_case_lists`，不会触发 `refresh_lists`。

- PA 筛选工具的复制 / 移动行为
  - 当前实现中：
    - PA 文件可复制到 `target_dir`；
    - 非 PA 文件只能移动到 `move_excluded_dir`（如配置），没有“复制非 PA 文件”的操作。
  - 文档应表述为「复制 PA 文件 / 移动非 PA 文件」。

- 拖拽掩码文件时的缓存更新
  - `canvas.file_dropped → _on_mask_file_dropped`：
    - 会更新 `canvas.mask` 与 `ImageEntry.mask_path/has_mask`；
    - 但不会立刻更新 LRU 图像缓存 `_image_cache`，缓存更新在保存 (`save_mask`) 时完成。
  - 如需在拖拽时同步缓存，需在 `_on_mask_file_dropped` 中增加相应逻辑。
```

### 4.2 修正扫描功能与任务 JSON 描述

原文中“扫描功能（点击“扫描”或加载任务 JSON 时驱动）”暗示两者共用同一扫描线程。建议改为：

```markdown
  - 扫描功能（点击“扫描”菜单时驱动）：
    - `refresh_lists`：在当前 `scan_mode` 下，从 `orig_root`/`mask_root` 开始扫描病例；通过 `_internal_scan_worker` 在后台线程执行，结果由 `_poll_scan_result` 应用到 UI 列表。
    - CT 模式：病例 = 原图根目录下的一级子目录；是否完成由 case_status 或掩码子目录是否存在决定。
    - X-ray 模式：病例 = `orig_root` 下的单个文件或相对路径；是否完成由 `case_status` 或 `_resolve_xray_mask_path` 告知的掩码存在情况决定。

  - 任务 JSON 模式（独立于目录扫描线程，不会调用 `refresh_lists`）：
    - `load_task_json`：从 JSON 文件加载任务（路径 → 标签），解析为 `ImageEntry` 列表，区分 CT 序列与 X 光模式路径语义（目录 vs 文件）。
    - `_resolve_task_base_dir`：根据任务 JSON 所在目录与首条 key 推断影像根目录，兼容相对路径与绝对路径。
    - `_build_task_entries/_commit_task_context/_build_task_case_lists`：将 JSON 数据映射到 `task_entries/task_case_entries/task_case_order/task_key_map` 数据结构，并重建病例列表；`case_status` 在任务模式下使用任务 key 而非路径 key。
```

### 4.3 修正文中 PA 筛选工具描述

在 ActionsMixin 描述中的 PA 筛选条目，将：

> 可选择复制/移动非 PA 文件与生成报告

改为：

```markdown
    - `PaFilterDialog + _start_pa_filter_task/_pa_filter_worker`：在后台线程使用 `tools.pa_filter` 对 DICOM 目录进行 PA 位筛选，可选择复制 PA 文件到目标目录，并将非 PA 文件移动到隔离目录，同时生成筛选报告。
```

### 4.4 修正文中拖拽掩码时“更新缓存”的表述

在 “画布信号” 小节中，将：

> 支持拖拽掩码 NIfTI/PNG 到当前图像上，自动 resize 对齐并更新 `ImageEntry.mask_path` 与缓存。

改为：

```markdown
    - `_connect_canvas_signals` 在主窗构造后调用，连接 `canvas.file_dropped` → `_on_mask_file_dropped`，支持拖拽掩码 NIfTI/PNG 到当前图像上，自动 resize 对齐并更新 `ImageEntry.mask_path/has_mask` 以及画布中的掩码状态（LRU 图像缓存仍在保存时统一更新）。
```

---

## 5. `_build_ct_case_entries` 的实现设计

这一节是针对 `data_mixin.py` 中 CT 模式病例展开的具体方案，核心参考 `docs/CT标注修复.py` 中 `MaskCorrectorWindow.load_patient_images` 的行为。

### 5.1 输入输出约定

- 输入：
  - `case_name: str`：左侧病例列表中的病例标识，典型为 `orig_root` 下的一级子目录名；
- 依赖成员：
  - `self.orig_root` / `self.mask_root`：CT 模式下的原图与掩码根目录；
  - `CT_SOURCE_EXTENSIONS`：CT 模式下允许的原图扩展名集合（`constants.py` 中定义，包含 `png/jpg/jpeg/bmp/tif/tiff/dcm` 等）；
  - `_resolve_ct_mask_path(...)`：给定病例与切片路径，返回候选掩码路径。
- 输出：
  - `List[ImageEntry]`：该病例内的所有切片条目。每个条目应至少包含：
    - `orig_path`：原图绝对路径；
    - `mask_path`：推断得到的掩码路径（可能为 `None`）；
    - `has_mask: bool`：掩码是否真实存在；
    - `case_name`：当前病例名（用于状态 JSON 与 UI 显示）；
    - 其余字段按现有 `models.ImageEntry` 规范填充。

### 5.2 目录展开与文件过滤

参考 `CT标注修复.py` 中 `load_patient_images` 的做法：

1. 计算病例目录：
   - `orig_case_dir = os.path.join(self.orig_root, case_name)`；
   - 掩码病例根目录可为 `mask_case_root = os.path.join(self.mask_root, case_name)`，具体规则交由 `_resolve_ct_mask_path` 统一处理。

2. 递归扫描原图：
   - 使用 `os.walk(orig_case_dir)` 遍历子目录；
   - 对每个文件 `f`，若 `ext.lower() in CT_SOURCE_EXTENSIONS` 则视为原图：
     - `full = os.path.join(root, f)`；
     - `rel = os.path.relpath(full, orig_case_dir)`；
     - 记录为 `(rel, full)`。

3. 排序：
   - 使用“自然排序”保证有数字的文件名按数值顺序排列：
     - `files.sort(key=lambda x: natural_sort_key(x[0]))`；
   - `natural_sort_key` 的实现可以参考 `CT标注修复.py` 中已有版本，或复用目前主工程已有的排序工具（如有）。

### 5.3 掩码路径推断与 `ImageEntry` 构造

对排序后的每个 `(rel, full)`：

1. 使用 `_resolve_ct_mask_path` 推断掩码路径：
   - 伪代码示例：
   - `mask_path = self._resolve_ct_mask_path(case_name, rel)`（具体参数签名以现有实现为准）；
   - `_resolve_ct_mask_path` 内部按照 `CT_MASK_CANDIDATE_SUFFIXES` 优先查找 NIfTI / PNG 掩码，找不到时返回“默认 PNG 掩码路径”（用于保存时创建）。

2. 计算 `has_mask`：
   - `has_mask = bool(mask_path and os.path.exists(mask_path))`；

3. 构造 `ImageEntry`：
   - 使用主工程的 `ImageEntry` 数据结构，而不是 `docs/CT标注修复.py` 中的简化版：
   - 字段示例（按实际模型调整）：
     - `case_name = case_name`；
     - `orig_rel = rel`（如模型有相对路径字段可填）；
     - `orig_path = full`；
     - `mask_path = mask_path`；
     - `has_mask = has_mask`；
     - 其他如 `has_pneumothorax` 等用默认值初始化。

4. 将每个 `ImageEntry` 添加到列表中并返回。

### 5.4 与 LRU / 预取机制的关系

- `_build_ct_case_entries` 只负责构建静态的 `ImageEntry` 列表：
  - 不触碰 `_image_cache`；
  - 不执行实际 DICOM / 图像读盘；
- 图像与掩码的真正读盘行为仍然通过 `_load_entry_payload(entry)`：
  - 优先命中 `_image_cache`；
  - 未命中时从磁盘读取，并调用 `_cache_set(entry, payload)` 写入 LRU；
- 预取：
  - 预取线程依赖的是 `ImageEntry` 序列和当前索引；
  - 只要 `ImageEntry` 的 `orig_path` 唯一且稳定、`case_name` 正确，现有 `_build_prefetch_indices/_start_prefetch/_start_cross_case_prefetch` 逻辑无需修改。

### 5.5 与 X 光模式的隔离

为保证 X 光模式不受影响：

1. 不修改 X 光相关函数：
   - `_iter_xray_source_filenames`、`_build_xray_entry`、`_build_xray_case_entries`、`_resolve_xray_mask_path` 维持现状；

2. 保持 `_build_case_entries/_expand_case_to_entries` 中的模式分支：
   - `scan_mode == ScanMode.CT_SEQUENCE` → 仅调用 `_build_ct_case_entries`；
   - `scan_mode == ScanMode.XRAY_SINGLE` → 仅调用 `_build_xray_case_entries`；

3. 若引入 CT 专用辅助函数（如 `_iter_ct_source_files(case_name)`），只在 CT 分支使用，不与 X 光共用，以降低耦合度。

---

## 6. 任务 JSON 与目录扫描的行为说明

此处不改动代码，仅明确未来维护时的认知：

- 目录扫描（普通模式）：
  - 由用户点击“扫描”菜单触发；
  - 走 `refresh_lists → _internal_scan_worker → _poll_scan_result` 背景线程；
  - 结果更新普通模式下的 todo/annotated 列表。

- 任务 JSON 模式：
  - 由用户加载任务 JSON 触发；
  - 走 `load_task_json → _build_task_entries/_commit_task_context/_build_task_case_lists`；
  - 结果覆盖当前病例列表与任务进度统计；
  - 不调用 `refresh_lists`，避免与目录扫描线程混淆。

后续如需更改任务模式行为（例如支持某种“任务 + 扫描混合模式”），必须同步更新 CLAUDE.md 的对应段落。

---

## 7. PA 筛选行为与文案统一方案

### 7.1 推荐方案 A：只修正文本描述

- 保持当前代码逻辑：
  - PA 文件：可复制到 `target_dir`；
  - 非 PA 文件：可移动到 `move_excluded_dir`；
- CLAUDE.md 与 UI 文案（`PaFilterDialog`）统一表述为：
  - “复制 PA 文件 / 移动非 PA 文件”。

### 7.2 备选方案 B：扩展为“非 PA 可复制/移动”

如未来确有需要，可按以下方向扩展：

1. 在 `PaFilterDialog` 中新增配置项，让用户指定非 PA 文件的处理方式：
   - 仅移动；
   - 仅复制；
   - 同时复制 + 移动（视业务需要而定）。

2. 在 `tools/pa_filter.py` 中新增相应的 `copy_excluded_files(...)` 函数或复用现有拷贝逻辑；

3. 在 `_pa_filter_worker` 中根据用户配置调用不同的操作函数。

考虑到复杂度与需求优先级，目前建议先执行方案 A，仅修正文档与 UI 文案。

---

## 8. 拖拽掩码缓存策略

### 8.1 推荐方案：仅修正文档，保留现有行为

- 保留当前实现：
  - 拖拽掩码更新画布与 `ImageEntry.mask_path/has_mask`；
  - LRU 图像缓存 `_image_cache` 在 `save_mask` 中统一更新；
- 在 CLAUDE.md 中明确这一点，避免误以为拖拽本身也会写入缓存。

### 8.2 如果未来需要“拖拽即更新 LRU”的增强

可为后续版本预留设计思路（不在本轮实现）：

1. 在 `_on_mask_file_dropped` 中：
   - 基于当前 `ImageEntry` 自行构造新的 payload `(img, new_mask, meta)`；
   - 调用 `_cache_set(entry, payload)` 更新 `_image_cache`；

2. 需要特别注意：
   - 确保与预取线程对同一条目读写时的并发安全（必要时通过主线程调度或锁保护）；
   - 评估频繁拖拽掩码对缓存命中率与内存占用的影响。

---

## 9. 实施顺序与下次任务建议

下次实际动手实现时，建议按以下顺序进行：

1. **更新 CLAUDE.md 文档**
   - 新增「已知注意事项 / TODO」小节；
   - 修正“扫描功能 / 任务 JSON 模式”的描述；
   - 修正文中 PA 筛选与拖拽掩码的表述。

2. **在 `data_mixin.py` 中补全 `_build_ct_case_entries`**
   - 参照本方案第 5 节；
   - 充分复用 `docs/CT标注修复.py` 中 `load_patient_images` 的思路（递归扫描 + 自然排序 + 相对路径 + 掩码配对）；
   - 保证不触碰 X 光相关函数与 LRU/预取逻辑。

3. **本地验证 CT 与 X 光模式**
   - 选用小规模 CT 序列数据：验证病例展开、序列加载、预取与保存掩码；
   - 切换到 X 光模式：验证扫描、病例展开、掩码匹配与保存不受影响。

4. **根据需要调整 PA 筛选与拖拽策略**
   - 若仅修正文案：改 CLAUDE.md 与 UI 文本即可；
   - 若未来需要更复杂行为，再单独起任务。

本文件旨在作为后续实现和代码审查的依据，避免在下次修改时重新推导同样的设计思路。