# JSON 存储方式 vs SQLite 方案对比设计

> 目的：对比当前项目使用多个 JSON 文件存储标签与病例状态的方案，和改为使用 SQLite 的设计方案，便于评估是否迁移以及如何迁移。

---

## 1. 现状：基于 JSON 的存储方式

### 1.1 气胸标签（pneumothorax_labels.json / 任务 JSON）

**相关代码：**
- `data_mixin.py:49-79 _get_labels_json_path/_init_labels_cache/_flush_labels_cache`
- `data_mixin.py` 中多处使用 `self._labels_cache.get(rel_src, 0)` 读取标签

**行为描述：**

- 普通模式：
  - 标签文件路径：
    - `_get_labels_json_path` 返回 `orig_root/pneumothorax_labels.json`；
  - JSON 结构：

    ```json
    {
      "relative/path/to/image1.dcm": 1,
      "relative/path/to/image2.png": 0,
      ...
    }
    ```

    - key：图像相对 `orig_root` 的路径（统一使用 `/` 作为分隔符）；
    - value：整型 0/1，表示是否有气胸。

- 任务模式：
  - `_get_labels_json_path` 直接返回任务 JSON 路径 `task_json_path`；
  - `_init_labels_cache` 会把任务 JSON 读入 `_labels_cache`：
    - key：任务 JSON 中的原始 key（可能是路径或其他标识）；
    - value：0/1 标记。

- 初始化与写入：
  - `_init_labels_cache`：
    - 根据 `_get_labels_json_path` 决定读取哪个 JSON；
    - 支持多种编码（utf-8-sig / utf-8 / gbk）；
    - 将 JSON 全量加载到 `_labels_cache: dict`；
    - 绑定定时器 `_labels_timer`，用于防抖写盘。
  - `_schedule_labels_flush` / `_flush_labels_cache`：
    - 每次修改 `_labels_cache` 时调用 `_schedule_labels_flush`，延迟写入；
    - `_flush_labels_cache` 把 `_labels_cache` 全量 `json.dump` 回对应 JSON 文件。

**特点：**
- 实现简单、可读性好；
- 整个标签数据一次性 load / dump；
- 适合数据量较小时使用，但随着病例增多，JSON 文件可能越来越大。

---

### 1.2 病例状态（case_status.json / {task}_case_status.json）

**相关代码：**
- `data_mixin.py:92-131 _get_status_file_path/_load_case_status/_save_single_case_status/_save_task_case_status`

**行为描述：**

- 普通模式：
  - 状态文件路径：
    - `_get_status_file_path` 返回 `orig_root/case_status.json`；
  - JSON 结构：

    ```json
    {
      "case_001": "done",
      "case_002": "todo",
      ...
    }
    ```

    - key：病例名（左侧列表的 case_name）；
    - value：状态字符串（例如 `"todo"` / `"done"` 等）。

- 任务模式：
  - 状态文件路径：
    - `_get_status_file_path` 返回 `orig_root/{task_name}_case_status.json`，其中 `task_name` 来源于任务 JSON 文件名；
  - JSON 结构：

    ```json
    {
      "<task_key_1>": "done",
      "<task_key_2>": "todo",
      ...
    }
    ```

    - key：任务 JSON 中的 key（与 `task_key_map` 对应）；
    - value：状态字符串。

- 读取与写入：
  - `_load_case_status`：
    - 打开 `_get_status_file_path` 返回的 JSON 文件，读入一个 `dict`；
  - `_save_single_case_status`（普通模式）：
    - 先用 `_load_case_status` 读出当前 map；
    - 更新 `data[case_name] = status`；
    - 将 dict 全量写回 JSON；
  - `_save_task_case_status`（任务模式）：
    - 先 `_load_case_status` 读出 JSON；
    - 遍历当前病例的 `task_case_entries`，通过 `task_key_map` 找到每个 `entry.orig_path` 对应的任务 key；
    - 对这些 key 统一写入同一个 status；
    - 将 dict 全量写回 JSON。

**特点：**
- 简单直接，易于人工检查和编辑；
- 每次保存都会重写整个 JSON 文件；
- 对任务模式而言，需要维护 `{task}_case_status.json` 的额外文件。

---

### 1.3 删除病例时 JSON 的一致性维护

**相关代码：**
- `data_mixin.py:134-248 delete_case`

**行为描述（简略）：**

- 如果当前正在查看的病例就是要删除的病例，会先清空 UI 和内存中的 `entries` / `thumbnail_strip` 等。

- 任务模式：
  - 根据 `case_name` 找到 `task_case_entries` 中的条目；
  - 用 `task_key_map` 找到每个 `orig_path` 对应的 JSON key；
  - 在 `_labels_cache` 和 `_load_case_status()` 返回的 dict 中删掉这些 key；
  - 可选地删除物理文件（`remove_files=True`）；
  - 调 `_flush_labels_cache(force=True)` 写回任务 JSON / 标签 JSON；
  - 将修改后的状态 dict 写回 `{task}_case_status.json`。

- 普通模式：
  - `_labels_cache` 中删除所有 key 为 `case_name` 或以 `case_name + '/'` 为前缀的条目；
  - 调 `_schedule_labels_flush()`，异步将标签写回 `pneumothorax_labels.json`；
  - `_load_case_status()` 读出 `case_status.json`，删掉 `case_name`，全量写回。

---

## 2. 目标：使用 SQLite 替代多 JSON 文件

### 2.1 总体思路

- 在每个 `orig_root` 下使用**一个** SQLite 数据库文件，例如：
  - `orig_root/.chexagent_meta.db`；
- 用表结构替代当前的多个 JSON 文件：
  - `labels` 表：存储“条目 key → 气胸标签”；
  - `case_status` 表：存储“病例或任务条目 key → 状态”；
  - 可选 `meta` 表：记录 schema 版本和该 DB 对应的 `orig_root` 等元信息。
- 对上层调用保持尽量透明：
  - `_labels_cache` 仍然存在，用于内存缓存 + 防抖；
  - 只是 `_init_labels_cache/_flush_labels_cache` 底层不再 `json.load/dump`，而是读写 SQLite；
  - `_load_case_status/_save_*` 不再重写 JSON，而是对 SQLite 做增删改查。

### 2.2 建议的 SQLite 表结构

#### 表 1：`labels` — 气胸标签

```sql
CREATE TABLE labels (
    key        TEXT PRIMARY KEY,    -- 当前 JSON 的 key：
                                   -- 普通模式 = 相对 orig_root 路径
                                   -- 任务模式 = 任务 JSON key
    label      INTEGER NOT NULL,    -- 0/1
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- 与现有 `_labels_cache` 的 key 完全一致：
  - 普通模式：`rel_src`（例如 `"case_001/0001.dcm"`）；
  - 任务模式：任务 JSON 原始 key。

#### 表 2：`case_status` — 病例 / 任务条目状态

```sql
CREATE TABLE case_status (
    key        TEXT PRIMARY KEY,    -- 普通模式: case_name
                                   -- 任务模式: 任务 JSON key
    status     TEXT NOT NULL,       -- 如 "todo" / "done"
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- 普通模式：
  - `key = case_name`；
- 任务模式：
  - `key = 任务 JSON 的 key`（与 `{task}_case_status.json` 中的 key 一致）。

#### 表 3（可选）：`meta` — 元信息

```sql
CREATE TABLE meta (
    name  TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 示例数据：
INSERT INTO meta(name, value) VALUES
  ('schema_version', '1'),
  ('orig_root', 'D:/data/ct_root');
```

主要用于版本管理和简单校验（例如防止把错误的 DB 拿去配别的目录）。

---

## 3. 行为映射：JSON → SQLite

### 3.1 `_init_labels_cache` / `_flush_labels_cache`

**现状（JSON）：**
- 初始化：
  - 根据 `_get_labels_json_path` 选择标签 JSON 或任务 JSON；
  - `json.load` 全部内容到 `_labels_cache`。
- flush：
  - 将 `_labels_cache` 全量 `json.dump` 回原路径。

**改为 SQLite 后的设计：**

- 初始化 `_init_labels_cache`：
  1. 确定当前 DB 路径（例如 `orig_root/.chexagent_meta.db`），建立连接；
  2. 从 `labels` 表执行：

     ```sql
     SELECT key, label FROM labels;
     ```

     将结果填入 `_labels_cache: Dict[str, int]`；
  3. 若是任务模式且需要兼容旧任务 JSON：
     - 若 `labels` 表为空，可以从任务 JSON 导入一遍（仅在第一次创建 DB 时，见迁移策略）。

- flush `_flush_labels_cache`：
  1. 若 `_labels_dirty` 为 False 且非强制 flush，直接返回；
  2. 对 `_labels_cache` 中所有 `(key, label)` 批量执行 upsert：

     ```sql
     INSERT INTO labels(key, label, updated_at)
     VALUES (?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(key) DO UPDATE SET
       label = excluded.label,
       updated_at = excluded.updated_at;
     ```

  3. 将 `_labels_dirty` 置为 False。

> 注意：
> - `_labels_cache` 和 `_schedule_labels_flush` 的防抖逻辑可以完全复用；
> - 只是最终持久化目标从一个 JSON 文件变成 `labels` 表。

---

### 3.2 `_load_case_status` / `_save_single_case_status` / `_save_task_case_status`

**现状（JSON）：**

- `_load_case_status`：

  ```python
  path = self._get_status_file_path()
  if os.path.exists(path):
      with open(path, "r", encoding="utf-8") as f:
          return json.load(f)
  return {}
  ```

- `_save_single_case_status`：
  - 读 JSON → 更新 dict → 全量写回。

- `_save_task_case_status`：
  - 读 JSON → 遍历 `task_case_entries` + `task_key_map` → 更新多个 key → 全量写回。

**改为 SQLite 后的设计：**

- `_load_case_status`：

  ```python
  def _load_case_status(self):
      rows = cursor.execute("SELECT key, status FROM case_status").fetchall()
      return {key: status for (key, status) in rows}
  ```

- `_save_single_case_status`（普通模式）：

  ```sql
  INSERT INTO case_status(key, status, updated_at)
  VALUES (:key, :status, CURRENT_TIMESTAMP)
  ON CONFLICT(key) DO UPDATE SET
    status = excluded.status,
    updated_at = excluded.updated_at;
  ```

  - 其中 `key = case_name`。

- `_save_task_case_status`（任务模式）：
  - 不再修改 JSON，而是对每个任务 key 调用同样的 upsert：

    ```python
    for entry in case_entries:
        key = self.task_key_map.get(entry.orig_path)
        if not key:
            continue
        # upsert into case_status(key, status)
    ```

---

### 3.3 `delete_case` 行为映射

**现状（JSON）：**

- 任务模式：
  - 在 `_labels_cache` 中删除对应任务 key；
  - 在 `_load_case_status()` 返回的 dict 中删除相同 key；
  - flush 标签 JSON；
  - 重写 `{task}_case_status.json`。

- 普通模式：
  - `_labels_cache` 中删除所有 key 为 `case_name` 或前缀为 `case_name + '/'` 的条目；
  - `_schedule_labels_flush`，异步写入 `pneumothorax_labels.json`；
  - `case_status.json` 中删除 `case_name`，重写文件。

**改为 SQLite 后：**

- 任务模式：
  - `_labels_cache` 删除对应 key（与现在一样）；
  - `status_map` 可以继续用 `_load_case_status()` 将整个表 load 到内存，然后在内存 dict 中删掉对应 key 再写回，或直接在 DB 中执行：

    ```sql
    DELETE FROM case_status WHERE key = :task_key;
    ```

  - Flush 标签：`_flush_labels_cache(force=True)` 会把 `_labels_cache` 写入 `labels` 表；

- 普通模式：
  - `_labels_cache` 删除所有前缀匹配的 key，`_schedule_labels_flush()` → 最终覆盖写入 `labels` 表；
  - `case_status` 可以：

    ```sql
    DELETE FROM case_status WHERE key = :case_name;
    ```

  - 上层逻辑几乎不变，只是底层的“写回 JSON”换成了“更新 SQLite 表”。

---

## 4. 迁移策略（从 JSON 迁移到 SQLite）

为避免丢失已有数据，建议对每个 `orig_root` 采用“首次使用时迁移”的策略：

1. 在 `DataMixin` 初始化或首次访问标签/状态时：
   - 检查 `<orig_root>/.chexagent_meta.db` 是否存在：
     - 若不存在：
       - 创建 DB 文件；
       - 建表 `labels` / `case_status` / `meta`；
       - 从现有 JSON 导入一次数据；
     - 若存在：
       - 直接打开 DB 使用；

2. 导入过程（仅在 DB 不存在时运行一次）：

   - 从 `pneumothorax_labels.json`（若存在）读入 `{key: label}`，执行批量 upsert 到 `labels` 表；
   - 从 `case_status.json` 读入 `{case_name: status}`，写入 `case_status` 表；
   - 对每个历史任务：
     - `{task}_case_status.json` 中 `{task_key: status}` 同样写入 `case_status` 表；
     - 若任务 JSON 里也包含标签信息，可以根据需要导入到 `labels`。

3. 迁移后的 JSON 策略：
   - **推荐：** 保留 JSON 文件（只读），不再作为写入目标：
     - 便于人工查看和备份；
     - 新写入一律走 SQLite，避免双写同步问题。

---

## 5. 初步优劣对比

### JSON 方案的优点

- 人类可读，便于手工修改或查看；
- 不依赖任何数据库驱动，部署简单；
- 实现成本低，开发者容易理解。

### JSON 方案的不足（在当前项目语境下）

- 多文件（pneumothorax_labels.json / case_status.json / {task}_case_status.json / 任务 JSON），结构分散；
- 每次写入都需要重写整个 JSON，在病例/任务数量较大时 IO 和锁粒度较粗；
- 随着功能增加（例如更多标签类型），JSON 结构容易变复杂、不易扩展。

### SQLite 方案的优点

- 单一 DB 文件集中管理所有标签与状态；
- 自然支持事务和并发访问（即便当前主要是 UI 线程 + 后台线程）；
- 便于扩展字段，未来如果需要更多标签（例如多类病变）可以直接加列或加表；
- 查询灵活，可以方便实现统计、筛选、历史日志等功能。

### SQLite 方案的风险 / 复杂度

- 引入新的依赖（`sqlite3` 虽然是标准库，但对错误恢复要更小心）；
- 调试不再是简单地打开 JSON 看一眼，而是需要工具或简单脚本查询 DB；
- 需要设计好迁移逻辑，避免首次升级时出现数据不一致。

---

## 6. 待你评估的问题点

1. **DB 文件位置和命名**是否符合你的习惯？
   - 例如用 `orig_root/.chexagent_meta.db`，还是更显式一点的文件名？

2. **任务模式与普通模式是否共用一套 labels / case_status 表**：
   - 目前设计是共用，用 key 空间来区分；
   - 是否需要额外字段（如 `mode` 或 `task_id`）来进一步区分？

3. **是否保留 JSON 写入能力**：
   - 方案中建议迁移后只读 JSON，不再写回；
   - 你是否希望保留“一键导出 JSON”的功能，方便外部工具使用？

4. **是否需要在 DB 中记录更多元信息**：
   - 例如每次修改的操作日志、用户标注时间、标注者 ID 等，这会影响表结构设计。

你可以在这份文档上直接指出你希望调整的地方，我再基于你的反馈细化最终的 SQLite 方案和具体实现计划。