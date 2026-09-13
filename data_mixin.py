"""数据流程：目录扫描、缓存、加载与病例切换逻辑。"""

import json
import os
import queue
import re
import threading
import sqlite3

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QListWidgetItem,
    QMessageBox,
    QProgressDialog,
)

from models import ImageEntry, ScanMode
from constants import (
    CT_MASK_CANDIDATE_SUFFIXES,
    CT_SOURCE_EXTENSIONS,
    DEFAULT_MASK_BITMAP_EXT,
    DEFAULT_NIFTI_EXT,
    MASK_FILE_EXTENSIONS,
    NIFTI_EXTENSIONS,
    XRAY_IGNORED_SOURCE_EXTENSIONS,
    XRAY_MASK_CANDIDATE_EXTENSIONS,
    default_mask_path,
    endswith_any,
    split_known_image_ext,
    strip_known_image_ext,
)
from utils import (
    imread_unicode,
    is_dual_folder_mode,
    load_pneumo_labels,
    natural_sort_key,
    read_dicom_with_window,
    read_mask_file,
    smart_read_image,
)


class DataMixin:
    def _get_meta_db_path(self):
        """返回当前数据根目录下的 SQLite 元数据路径。"""
        if not getattr(self, "orig_root", None):
            return ""
        return os.path.join(self.orig_root, ".chexagent_meta.sqlite")

    def _get_labels_type(self) -> str:
        """根据当前模式返回 labels 所属的类型标识。

        - 普通模式："regular"
        - 任务模式：任务 JSON 文件名（不含扩展名）
        """
        if getattr(self, "task_mode", False) and getattr(self, "task_json_path", None):
            base_name = os.path.splitext(os.path.basename(self.task_json_path))[0]
            return base_name or "task"
        return "regular"

    def _get_status_type(self) -> str:
        """case_status 使用与 labels 相同的类型空间。"""
        return self._get_labels_type()

    def _ensure_db_schema(self, conn: sqlite3.Connection) -> None:
        """确保 SQLite 元数据表已创建。"""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS labels (
                type       TEXT NOT NULL,
                key        TEXT NOT NULL,
                label      INTEGER NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (type, key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS case_status (
                type       TEXT NOT NULL,
                key        TEXT NOT NULL,
                status     TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (type, key)
            )
            """
        )
        conn.commit()

    def _get_db_connection(self) -> sqlite3.Connection | None:
        """获取一个已初始化 schema 的 SQLite 连接。

        采用短生命周期连接，调用方用完后负责关闭。
        """
        db_path = self._get_meta_db_path()
        if not db_path:
            return None
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
        self._ensure_db_schema(conn)
        return conn

    def _get_labels_json_path(self):
        if self.task_mode and self.task_json_path:
            return self.task_json_path
        if not self.orig_root:
            return ""
        return os.path.join(self.orig_root, "pneumothorax_labels.json")

    def _init_labels_cache(self):
        self._labels_json_path = self._get_labels_json_path()
        self._labels_cache = {}
        self._labels_dirty = False

        labels_type = self._get_labels_type()
        conn = self._get_db_connection()
        if conn is not None:
            try:
                # 1) 尝试从 SQLite 读取当前类型的所有标签
                cur = conn.execute(
                    "SELECT key, label FROM labels WHERE type = ?",
                    (labels_type,),
                )
                rows = cur.fetchall()
                if rows:
                    self._labels_cache = {k: int(v) for k, v in rows}
                # 2) 若 DB 为空且存在旧 JSON，则导入一次
                if not self._labels_cache and self._labels_json_path and os.path.exists(
                    self._labels_json_path
                ):
                    data: dict[str, int] | None = None
                    for enc in ("utf-8-sig", "utf-8", "gbk"):
                        try:
                            with open(self._labels_json_path, "r", encoding=enc) as f:
                                loaded = json.load(f)
                            if isinstance(loaded, dict):
                                data = loaded
                            break
                        except Exception:
                            continue
                    if data:
                        # [修复] key 统一规范化为正斜杠，避免 Windows 反斜杠导致查询失败
                        self._labels_cache = {
                            str(k).replace("\\", "/"): int(v) for k, v in data.items()
                        }
                        for key, label in self._labels_cache.items():
                            conn.execute(
                                """
                                INSERT INTO labels(type, key, label, updated_at)
                                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                                ON CONFLICT(type, key) DO UPDATE SET
                                  label = excluded.label,
                                  updated_at = excluded.updated_at
                                """,
                                (labels_type, key, label),
                            )
                        conn.commit()
            finally:
                conn.close()
        # 若尚未设置 orig_root，保持空缓存即可

        if not getattr(self, "_labels_timer_bound", False):
            self._labels_timer.timeout.connect(lambda: self._flush_labels_cache(False))
            self._labels_timer_bound = True

    def _schedule_labels_flush(self):
        self._labels_dirty = True
        self._labels_timer.stop()
        self._labels_timer.start(self._labels_debounce_ms)

    def _flush_labels_cache(self, force: bool = True):
        if not self._labels_dirty and not force:
            return

        labels_type = self._get_labels_type()
        conn = self._get_db_connection()
        if conn is None:
            return
        try:
            for key, label in self._labels_cache.items():
                conn.execute(
                    """
                    INSERT INTO labels(type, key, label, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(type, key) DO UPDATE SET
                      label = excluded.label,
                      updated_at = excluded.updated_at
                    """,
                    (labels_type, str(key), int(label)),
                )
            conn.commit()
            self._labels_dirty = False
        finally:
            conn.close()

    def _get_status_file_path(self):
        if self.task_mode and self.task_json_path:
            base_name = os.path.splitext(os.path.basename(self.task_json_path))[0]
            return os.path.join(self.orig_root, f"{base_name}_case_status.json")
        return os.path.join(self.orig_root, "case_status.json")

    def _load_case_status(self):
        status_type = self._get_status_type()
        conn = self._get_db_connection()
        if conn is None:
            # 退回旧 JSON（极端情况下，例如 orig_root 尚未设置）
            path = self._get_status_file_path()
            if path and os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    return data if isinstance(data, dict) else {}
                except Exception:
                    return {}
            return {}

        try:
            cur = conn.execute(
                "SELECT key, status FROM case_status WHERE type = ?",
                (status_type,),
            )
            rows = cur.fetchall()
            if rows:
                return {k: v for k, v in rows}

            # 若 DB 为空，尝试从旧 JSON 导入一次
            path = self._get_status_file_path()
            if path and os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        for key, status in data.items():
                            conn.execute(
                                """
                                INSERT INTO case_status(type, key, status, updated_at)
                                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                                ON CONFLICT(type, key) DO UPDATE SET
                                  status = excluded.status,
                                  updated_at = excluded.updated_at
                                """,
                                (status_type, str(key), str(status)),
                            )
                        conn.commit()
                        return data
                except Exception:
                    return {}
            return {}
        finally:
            conn.close()

    def _save_single_case_status(self, case_name, status):
        status_type = self._get_status_type()
        conn = self._get_db_connection()
        if conn is None:
            return
        try:
            conn.execute(
                """
                INSERT INTO case_status(type, key, status, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(type, key) DO UPDATE SET
                  status = excluded.status,
                  updated_at = excluded.updated_at
                """,
                (status_type, str(case_name), str(status)),
            )
            conn.commit()
        except Exception as e:
            print(f"Error saving status: {e}")
        finally:
            conn.close()

    def _save_task_case_status(self, case_name, status):
        if not self.task_mode:
            return
        status_type = self._get_status_type()
        conn = self._get_db_connection()
        if conn is None:
            return
        try:
            data_changed = False
            case_entries = self.task_case_entries.get(case_name, [])
            for entry in case_entries:
                key = self.task_key_map.get(entry.orig_path)
                if not key:
                    continue
                conn.execute(
                    """
                    INSERT INTO case_status(type, key, status, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(type, key) DO UPDATE SET
                      status = excluded.status,
                      updated_at = excluded.updated_at
                    """,
                    (status_type, str(key), str(status)),
                )
                data_changed = True
            if data_changed:
                conn.commit()
        except Exception as e:
            print(f"Error saving status: {e}")
        finally:
            conn.close()

    
    
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
        case_name = str(case_name or "").strip()
        if not case_name:
            return

        # 若当前病例即被删除病例，先清空当前视图状态
        if getattr(self, "current_case_name", None) == case_name:
            self.current_case_name = ""
            self.entries.clear()
            self.thumbnail_strip.clear()
            self.current_idx = -1
            if hasattr(self, "info_panel") and hasattr(self.info_panel, "clear"):
                self.info_panel.clear()
            if hasattr(self, "canvas"):
                try:
                    self.canvas.base_img = None
                    self.canvas.mask = None
                    self.canvas._cache_bg_pixmap = None
                    self.canvas._is_dirty = False
                    self.canvas.update()
                except Exception:
                    pass

        # 任务模式下：按 JSON key 维度删除
        if self.task_mode:
            case_entries = list(self.task_case_entries.get(case_name, []))
            if not case_entries:
                return

            # 1) 更新内存结构
            orig_paths = {e.orig_path for e in case_entries}
            self.task_entries = [e for e in self.task_entries if e.orig_path not in orig_paths]
            self.task_case_entries.pop(case_name, None)
            if case_name in self.task_case_order:
                self.task_case_order.remove(case_name)

            # 2) 初始化标签缓存
            if not getattr(self, "_labels_cache", None):
                self._init_labels_cache()
            labels = self._labels_cache

            # 3) 按 orig_path 找到 JSON key，删除 labels 与 case_status 中的记录
            status_type = self._get_status_type()
            labels_type = self._get_labels_type()
            conn = self._get_db_connection()
            try:
                for entry in case_entries:
                    orig_path = entry.orig_path
                    json_key = self.task_key_map.pop(orig_path, None)
                    if not json_key:
                        continue
                    # [修复] 统一规范化，防御性处理（task_key_map 源头已规范化，这里再保险一次）
                    key_str = str(json_key).replace("\\", "/")

                    if key_str in labels:
                        labels.pop(key_str, None)

                    if conn is not None:
                        # [修复] 显式 DELETE labels 表中的行，否则 _flush_labels_cache
                        # 只 INSERT/UPDATE 无法清除被删 key，下次启动会重新加载
                        conn.execute(
                            "DELETE FROM labels WHERE type = ? AND key = ?",
                            (labels_type, key_str),
                        )
                        conn.execute(
                            "DELETE FROM case_status WHERE type = ? AND key = ?",
                            (status_type, key_str),
                        )

                    # 物理文件删除目前默认关闭，仅在 remove_files=True 时尝试
                    if remove_files:
                        try:
                            if os.path.isfile(orig_path):
                                os.remove(orig_path)
                        except Exception:
                            pass
                        try:
                            if entry.mask_path and os.path.isfile(entry.mask_path):
                                os.remove(entry.mask_path)
                        except Exception:
                            pass

                if conn is not None:
                    conn.commit()
            finally:
                if conn is not None:
                    conn.close()

            # 4) 写回标签到 SQLite
            self._labels_dirty = True
            self._flush_labels_cache(force=True)

            return

        # 普通模式：按病例名前缀删除 labels 与 case_status
        if not getattr(self, "_labels_cache", None):
            self._init_labels_cache()
        labels = self._labels_cache

        prefix = case_name.rstrip("/")
        keys_to_delete = [
            k
            for k in list(labels.keys())
            if k == prefix or k.startswith(prefix + "/")
        ]
        for k in keys_to_delete:
            labels.pop(k, None)
        if keys_to_delete:
            self._schedule_labels_flush()

        # 删除 SQLite 中 labels 表和 case_status 表中该病例的记录
        conn = self._get_db_connection()
        if conn is not None:
            try:
                labels_type = self._get_labels_type()
                # [修复] 显式 DELETE labels 表行，否则 flush 只 INSERT/UPDATE，
                # 被删 key 会遗留在 DB 中，下次启动又被重新加载
                for k in keys_to_delete:
                    conn.execute(
                        "DELETE FROM labels WHERE type = ? AND key = ?",
                        (labels_type, str(k)),
                    )
                conn.execute(
                    "DELETE FROM case_status WHERE type = ? AND key = ?",
                    (self._get_status_type(), case_name),
                )
                conn.commit()
            except Exception as e:
                print(f"Error saving status: {e}")
            finally:
                conn.close()

    def _reset_cache(self, clear_cache: bool = True, invalidate_prefetch: bool = True):
        """清理/重置影像缓存与预取状态。

        - clear_cache=True：释放当前影像缓存（_image_cache），避免内存占用。
        - invalidate_prefetch=True：推进预取 epoch，使旧的预取线程自然退出。

        注意：本方法依赖于 main_window.py 中初始化的：
        - self._image_cache: OrderedDict
        - self._cache_lock: threading.Lock
        - self._prefetch_inflight: set
        """
        with self._cache_lock:
            if clear_cache:
                for key, cached_val in list(self._image_cache.items()):
                    if not cached_val:
                        continue
                    # cached_val 形如 (img, mask, meta)
                    try:
                        img = cached_val[0]
                        mask = cached_val[1] if len(cached_val) > 1 else None
                        # 这里只是丢弃引用，实际内存由 GC 回收
                        del img, mask
                    except Exception:
                        pass
                self._image_cache.clear()
            self._prefetch_inflight.clear()
        if invalidate_prefetch:
            self._next_prefetch_epoch()

    def _cache_get(self, key):
        """读取缓存并更新 LRU 顺序。"""
        with self._cache_lock:
            if key in self._image_cache:
                val = self._image_cache.pop(key)
                self._image_cache[key] = val
                return val
        return None

    def _get_active_cache_max(self):
        return (
            self.ct_cache_max
            if self.scan_mode == ScanMode.CT_SEQUENCE
            else self.xray_cache_max
        )

    def _cache_set(self, key, value):
        """写入缓存并按当前模式上限做 LRU 淘汰。"""
        meta = None
        if len(value) == 3:
            img, mask, meta = value
        else:
            img, mask = value

        with self._cache_lock:
            if key in self._image_cache:
                cached_val = self._image_cache.pop(key)
                old_img, old_mask = cached_val[0], cached_val[1]
                self._release_cache_entry(key, old_img, old_mask)

            self._image_cache[key] = (img, mask, meta)
            active_max = self._get_active_cache_max()
            while len(self._image_cache) > active_max:
                old_key, cached_val = self._image_cache.popitem(last=False)
                old_img, old_mask = cached_val[0], cached_val[1]
                self._release_cache_entry(old_key, old_img, old_mask)

    def _alloc_mask(self, shape):
        if not getattr(self, "_mask_pool_enabled", False):
            return np.zeros(shape, dtype=np.uint8)
        return self._get_mask_pool_view(shape)

    def _reset_mask_pool(self, max_shape):
        self._mask_pool = []
        self._mask_pool_size = 0
        self._mask_pool_max_shape = max_shape
        self._mask_pool_refs = {}

    def _get_mask_pool_view(self, shape):
        h, w = shape
        if h <= 0 or w <= 0:
            return np.zeros(shape, dtype=np.uint8)

        max_shape = getattr(self, "_mask_pool_max_shape", None)
        if not max_shape or h > max_shape[0] or w > max_shape[1]:
            max_h = max(h, max_shape[0] if max_shape else 0)
            max_w = max(w, max_shape[1] if max_shape else 0)
            self._reset_mask_pool((max_h, max_w))

        if self._mask_pool:
            base = self._mask_pool.pop()
        else:
            if self._mask_pool_size >= self._mask_pool_limit:
                return np.zeros(shape, dtype=np.uint8)
            base = np.zeros(self._mask_pool_max_shape, dtype=np.uint8)
            self._mask_pool_size += 1

        view = base[:h, :w]
        view.fill(0)
        self._mask_pool_refs[id(view)] = base
        return view

    def _release_cache_entry(self, key, img, mask):
        refs = getattr(self, "_mask_pool_refs", None)
        if refs:
            base = refs.pop(id(mask), None)
            if base is not None:
                self._mask_pool.append(base)
        del img, mask

    def rename_case(self, case_name: str, new_case_name: str) -> None:
        """重命名病例标识，并同步更新磁盘路径和 JSON / 状态。

        支持场景：
        - 普通模式 + CT 序列：按病例目录重命名 orig_root / mask_root 下的文件夹；
        - 普通模式 + X 光单张：按相对路径重命名单张文件以及对应掩码文件；
        - 任务模式：当前仅更新病例分组名（task_case_entries / task_case_order），
          不改物理路径和 JSON key（后续可按需扩展）。
        """

        case_name = str(case_name or "").strip()
        new_case_name = str(new_case_name or "").strip()
        if not case_name or not new_case_name or case_name == new_case_name:
            return

        # 任务模式：根据扫描模式分别处理
        if getattr(self, "task_mode", False):
            case_entries = list(self.task_case_entries.get(case_name, []))
            if not case_entries:
                return

            # X 光任务模式：执行完整的物理重命名 + 任务 JSON / 状态同步
            if self.scan_mode == ScanMode.XRAY_SINGLE and self.orig_root:
                if not getattr(self, "_labels_cache", None):
                    self._init_labels_cache()
                labels = self._labels_cache
                status_map = self._load_case_status()

                for entry in case_entries:
                    old_orig = entry.orig_path
                    # 旧相对路径
                    try:
                        old_rel = os.path.relpath(old_orig, self.orig_root).replace("\\", "/")
                    except Exception:
                        old_rel = case_name

                    # 构造新的相对路径：优先做前缀替换
                    if old_rel == case_name or old_rel.startswith(case_name + "/"):
                        suffix = old_rel[len(case_name) :]
                        new_rel = new_case_name + suffix
                    else:
                        new_rel = new_case_name

                    new_orig = os.path.normpath(os.path.join(self.orig_root, new_rel))

                    # 物理重命名原图
                    try:
                        new_dir = os.path.dirname(new_orig)
                        if new_dir and not os.path.exists(new_dir):
                            os.makedirs(new_dir, exist_ok=True)
                        if os.path.exists(old_orig) and not os.path.exists(new_orig):
                            os.rename(old_orig, new_orig)
                            # 删除发生重命名那一级的旧目录（如果已经为空）
                            old_dir = os.path.dirname(old_orig)
                            try:
                                if (
                                    old_dir
                                    and os.path.isdir(old_dir)
                                    and not os.listdir(old_dir)
                                ):
                                    os.rmdir(old_dir)
                            except Exception:
                                pass
                    except Exception as e:
                        print(f"Error renaming X-ray task case file: {e}")

                    # 尝试重命名掩码文件
                    try:
                        old_mask = self._resolve_xray_mask_path(old_orig, rel_src=old_rel)
                        if not old_mask:
                            old_mask = self._build_default_xray_mask_path(old_orig, rel_src=old_rel)
                        if old_mask and os.path.exists(old_mask):
                            new_mask = self._build_default_xray_mask_path(new_orig, rel_src=new_rel)
                            new_mask_dir = os.path.dirname(new_mask)
                            if new_mask_dir and not os.path.exists(new_mask_dir):
                                os.makedirs(new_mask_dir, exist_ok=True)
                            if not os.path.exists(new_mask):
                                os.rename(old_mask, new_mask)
                    except Exception as e:
                        print(f"Error renaming X-ray task mask file: {e}")

                    # 更新 entry 内存状态
                    entry.orig_path = new_orig
                    entry.case_name = new_case_name
                    entry.filename = os.path.basename(new_rel) or new_rel
                    # 更新掩码路径与 has_mask
                    try:
                        new_mask_path = self._build_default_xray_mask_path(new_orig, rel_src=new_rel)
                        entry.mask_path = new_mask_path
                        entry.has_mask = os.path.exists(new_mask_path)
                    except Exception:
                        # 若推导失败则保持原有掩码路径
                        pass

                    # 更新 task_key_map 与任务 JSON / 状态 JSON 键
                    old_key_obj = self.task_key_map.pop(old_orig, None)
                    old_key_str = (
                        str(old_key_obj).replace("\\", "/")
                        if old_key_obj is not None
                        else old_rel
                    )
                    # 任务 JSON 约定使用相对路径 key
                    new_key_str = new_rel

                    self.task_key_map[new_orig] = new_key_str

                    if old_key_str in labels:
                        labels[new_key_str] = labels.pop(old_key_str)

                    if old_key_str in status_map and new_key_str not in status_map:
                        status_map[new_key_str] = status_map.pop(old_key_str)

                # 更新病例分组映射与顺序
                self.task_case_entries[new_case_name] = case_entries
                if case_name in self.task_case_entries:
                    self.task_case_entries.pop(case_name, None)
                if case_name in self.task_case_order and new_case_name not in self.task_case_order:
                    idx = self.task_case_order.index(case_name)
                    self.task_case_order[idx] = new_case_name

                # 写回任务 JSON 与状态（SQLite）
                self._labels_dirty = True
                self._flush_labels_cache(force=True)
                # [修复] 写 SQLite 而非 JSON 文件
                _conn = self._get_db_connection()
                if _conn is not None:
                    try:
                        _st = self._get_status_type()
                        for _k, _v in status_map.items():
                            _conn.execute(
                                """
                                INSERT INTO case_status(type, key, status, updated_at)
                                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                                ON CONFLICT(type, key) DO UPDATE SET
                                  status = excluded.status,
                                  updated_at = excluded.updated_at
                                """,
                                (_st, str(_k), str(_v)),
                            )
                        # 删除已被 pop 掉的旧 key（status_map 里已不存在）
                        _conn.execute(
                            "DELETE FROM case_status WHERE type = ? AND key NOT IN (%s)"
                            % ",".join("?" * len(status_map)),
                            [_st] + [str(k) for k in status_map],
                        ) if status_map else _conn.execute(
                            "DELETE FROM case_status WHERE type = ?", (_st,)
                        )
                        _conn.commit()
                    except Exception as e:
                        print(f"Error saving status to SQLite: {e}")
                    finally:
                        _conn.close()

                # 重命名后，按旧病例根目录（第一段）尝试清理空树
                old_root_seg = str(case_name).replace("\\", "/").strip("/").split("/")[0]
                if old_root_seg:
                    old_orig_root = os.path.join(self.orig_root, old_root_seg)
                    self._delete_tree_if_no_data_files(old_orig_root)
                    if (
                        getattr(self, "mask_root", "")
                        and self.mask_root != self.orig_root
                    ):
                        old_mask_root = os.path.join(self.mask_root, old_root_seg)
                        self._delete_tree_if_no_data_files(old_mask_root)

                return

            # 其他任务模式（例如 CT 序列任务）：目前先只调整病例分组名和 entry.case_name
            for entry in case_entries:
                entry.case_name = new_case_name

            self.task_case_entries[new_case_name] = self.task_case_entries.pop(case_name)
            if case_name in self.task_case_order and new_case_name not in self.task_case_order:
                idx = self.task_case_order.index(case_name)
                self.task_case_order[idx] = new_case_name

            return

        # ---------------- 非任务模式：处理物理路径 + JSON 状态 -----------------
        # 1) 物理重命名
        if self.scan_mode == ScanMode.CT_SEQUENCE and self.orig_root:
            # CT：病例名 = orig_root 下一级目录
            old_dir = os.path.join(self.orig_root, case_name)
            new_dir = os.path.join(self.orig_root, new_case_name)
            try:
                if os.path.isdir(old_dir) and not os.path.exists(new_dir):
                    os.rename(old_dir, new_dir)
            except Exception as e:
                print(f"Error renaming CT case folder: {e}")

            # 双文件夹模式：同步重命名 mask_root 下的目录
            try:
                if is_dual_folder_mode(self.orig_root, self.mask_root) and self.mask_root:
                    old_mask_dir = os.path.join(self.mask_root, case_name)
                    new_mask_dir = os.path.join(self.mask_root, new_case_name)
                    if os.path.isdir(old_mask_dir) and not os.path.exists(new_mask_dir):
                        os.rename(old_mask_dir, new_mask_dir)
            except Exception as e:
                print(f"Error renaming CT mask folder: {e}")

        elif self.scan_mode == ScanMode.XRAY_SINGLE and self.orig_root:
            # X 光：病例名 = 相对路径
            old_path = os.path.join(self.orig_root, case_name)
            new_path = os.path.join(self.orig_root, new_case_name)
            try:
                new_dir = os.path.dirname(new_path)
                if new_dir and not os.path.exists(new_dir):
                    os.makedirs(new_dir, exist_ok=True)
                if os.path.exists(old_path) and not os.path.exists(new_path):
                    os.rename(old_path, new_path)
            except Exception as e:
                print(f"Error renaming X-ray case file: {e}")

            # 尝试同步重命名掩码文件
            try:
                old_mask = self._resolve_xray_mask_path(old_path, rel_src=case_name)
                if not old_mask:
                    old_mask = self._build_default_xray_mask_path(old_path, rel_src=case_name)
                if old_mask and os.path.exists(old_mask):
                    new_mask = self._build_default_xray_mask_path(new_path, rel_src=new_case_name)
                    new_mask_dir = os.path.dirname(new_mask)
                    if new_mask_dir and not os.path.exists(new_mask_dir):
                        os.makedirs(new_mask_dir, exist_ok=True)
                    if not os.path.exists(new_mask):
                        os.rename(old_mask, new_mask)
                        # 如旧掩码目录已空，删除该层目录
                        old_mask_dir = os.path.dirname(old_mask)
                        try:
                            if (
                                old_mask_dir
                                and os.path.isdir(old_mask_dir)
                                and not os.listdir(old_mask_dir)
                            ):
                                os.rmdir(old_mask_dir)
                        except Exception:
                            pass
            except Exception as e:
                print(f"Error renaming X-ray mask file: {e}")

            # 重命名后，按旧病例根目录（第一段）尝试清理空树
            old_root_seg = str(case_name).replace("\\", "/").strip("/").split("/")[0]
            if old_root_seg:
                old_orig_root = os.path.join(self.orig_root, old_root_seg)
                self._delete_tree_if_no_data_files(old_orig_root)
                if getattr(self, "mask_root", "") and self.mask_root != self.orig_root:
                    old_mask_root = os.path.join(self.mask_root, old_root_seg)
                    self._delete_tree_if_no_data_files(old_mask_root)

        # 2) 更新 pneumothorax_labels.json（标签 JSON）
        if not getattr(self, "_labels_cache", None):
            self._init_labels_cache()
        labels = self._labels_cache
        new_labels = {}
        prefix = case_name.rstrip("/")
        for k, v in labels.items():
            if k == prefix or k.startswith(prefix + "/"):
                suffix = k[len(prefix) :]
                new_k = new_case_name + suffix
                new_labels[new_k] = v
            else:
                new_labels[k] = v
        self._labels_cache = new_labels
        self._schedule_labels_flush()

        # 3) 更新 case_status（SQLite）
        status_map = self._load_case_status()
        if case_name in status_map and new_case_name not in status_map:
            status_map[new_case_name] = status_map.pop(case_name)
        # [修复] 写 SQLite 而非 JSON 文件
        _conn = self._get_db_connection()
        if _conn is not None:
            try:
                _st = self._get_status_type()
                if new_case_name in status_map:
                    _conn.execute(
                        """
                        INSERT INTO case_status(type, key, status, updated_at)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(type, key) DO UPDATE SET
                          status = excluded.status,
                          updated_at = excluded.updated_at
                        """,
                        (_st, str(new_case_name), str(status_map[new_case_name])),
                    )
                _conn.execute(
                    "DELETE FROM case_status WHERE type = ? AND key = ?",
                    (_st, str(case_name)),
                )
                _conn.commit()
            except Exception as e:
                print(f"Error saving status to SQLite: {e}")
            finally:
                _conn.close()

    def _delete_tree_if_no_data_files(self, root_dir: str) -> None:
        """如果 root_dir 子树中没有任何 DICOM 或掩码文件，则删除整棵目录树。

        仅删除以 .dcm/.dicom 及 MASK_FILE_EXTENSIONS 结尾的文件所在的空目录树，
        避免误删仍包含数据的病例根目录。
        """
        if not root_dir or not os.path.isdir(root_dir):
            return

        data_exts = (".dcm", ".dicom") + MASK_FILE_EXTENSIONS

        # 1) 先检查是否还存在任何数据文件
        has_data = False
        for dirpath, _, filenames in os.walk(root_dir):
            for name in filenames:
                lower = name.lower()
                if lower.endswith(data_exts):
                    has_data = True
                    break
            if has_data:
                break
        if has_data:
            return

        # 2) 自底向上删除所有空目录
        for dirpath, _, _ in os.walk(root_dir, topdown=False):
            try:
                if os.path.isdir(dirpath) and not os.listdir(dirpath):
                    os.rmdir(dirpath)
            except OSError:
                # 目录非空或权限不足时跳过
                pass

    @staticmethod
    def _split_compound_ext(path_str):
        lower = path_str.lower()
        return split_known_image_ext(path_str)

    @classmethod
    def _strip_compound_ext(cls, path_str):
        return strip_known_image_ext(path_str)

    @staticmethod
    def _is_nifti_file(path_str):
        return endswith_any(path_str, NIFTI_EXTENSIONS)

    @classmethod
    def _get_xray_mask_stem(cls, path_str):
        return os.path.basename(cls._strip_compound_ext(path_str or ""))

    def _extract_meaningful_stem(self, filename: str) -> str:
        """提取文件名中真正有意义的 stem，用于模糊匹配。"""
        no_ext = self._strip_compound_ext(filename)
        if not no_ext:
            return ""

        lower_no_ext = no_ext.lower()
        for suffix in ("_mask", "-mask", "_label", "-label", "_pred"):
            if lower_no_ext.endswith(suffix):
                no_ext = no_ext[: -len(suffix)]
                break
        return no_ext.lower()

    def _is_generic_xray_mask_name(self, filename):
        stem = self._get_xray_mask_stem(filename).lower()
        return bool(stem) and (
            stem == "untitled"
            or stem.startswith("untitled")
            or re.fullmatch(r"\d+", stem) is not None
        )

    @classmethod
    def _get_xray_composite_sidecar_source_stem(cls, filename):
        """
        识别这类复合侧车：
            00000001.dcm.png  -> 00000001
            abc.dicom.png     -> abc
            img.jpg.png       -> img
        返回“对应原图的 stem”；不是这类命名则返回 ""。
        """
        lower = os.path.basename(filename or "").lower()
        if not lower.endswith(MASK_FILE_EXTENSIONS):
            return ""

        # 先去掉掩码扩展名（例如 .png / .nii.gz）
        inner = cls._strip_compound_ext(lower)
        # 再尝试去掉一层“原图扩展名”
        src_stem = cls._strip_compound_ext(inner)

        # 只有真的又剥掉了一层已知图像扩展名，才认为是复合侧车
        if src_stem and src_stem != inner:
            return os.path.basename(src_stem)

        return ""

    def _is_xray_mask_sidecar(self, filename):
        lower = os.path.basename(filename).lower()
        stem = self._get_xray_mask_stem(lower).lower()
        has_mask_ext = lower.endswith(MASK_FILE_EXTENSIONS)

        # NIfTI 在当前项目里始终按掩码侧车处理
        if self._is_nifti_file(lower):
            return True

        # 识别 *.dcm.png / *.dicom.png / *.jpg.png 这类复合扩展名侧车
        if self._get_xray_composite_sidecar_source_stem(lower):
            return True

        if has_mask_ext and stem.endswith("_mask"):
            return True
        if has_mask_ext and self._is_generic_xray_mask_name(lower):
            return True
        return False

    def _iter_xray_source_filenames(self, dir_path):
        if not dir_path or not os.path.isdir(dir_path):
            return []

        ignored_exts = XRAY_IGNORED_SOURCE_EXTENSIONS
        try:
            filenames = [
                f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))
            ]
        except OSError:
            return []

        # 这里顺手统一成 compound-ext 语义，避免 os.path.splitext 单层剥皮误判
        base_names = set()
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if (
                ext not in ignored_exts
                and ext != ".png"
                and not self._is_xray_mask_sidecar(f)
            ):
                base_names.add(self._strip_compound_ext(f))

        result = []
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if ext in ignored_exts or self._is_xray_mask_sidecar(f):
                continue
            if ext == ".png" and self._strip_compound_ext(f) in base_names:
                continue
            result.append(f)

        result.sort(key=natural_sort_key)
        return result

    def _build_xray_dir_mask_map(self, src_dir, rel_dir=""):
        src_dir = os.path.normpath(src_dir or "")
        if not src_dir or not os.path.isdir(src_dir):
            return {}

        dual_mode = is_dual_folder_mode(self.orig_root, self.mask_root)
        mask_dir = (
            os.path.normpath(os.path.join(self.mask_root, rel_dir))
            if dual_mode and self.mask_root
            else src_dir
        )

        cache_key = (src_dir, mask_dir)
        cache = getattr(self, "_xray_dir_match_cache", None)
        if cache is None:
            cache = {}
            self._xray_dir_match_cache = cache
        if cache_key in cache:
            return dict(cache[cache_key])

        # 1. 收集所有原图
        source_filenames = self._iter_xray_source_filenames(src_dir)
        if not source_filenames:
            cache[cache_key] = {}
            return {}

        # 2. 收集当前目录下所有合法掩码文件（含位图和 NIfTI）
        all_mask_paths = set()
        if os.path.isdir(mask_dir):
            try:
                for mask_name in os.listdir(mask_dir):
                    mask_path = os.path.join(mask_dir, mask_name)
                    if not os.path.isfile(mask_path):
                        continue
                    lower = os.path.basename(mask_name).lower()
                    if lower.endswith(MASK_FILE_EXTENSIONS) or self._is_nifti_file(lower):
                        all_mask_paths.add(os.path.normpath(mask_path))
            except OSError:
                pass

        # 剔除掉和原图完全同名的伪装者，防止把原图误当掩码
        for filename in source_filenames:
            all_mask_paths.discard(os.path.normpath(os.path.join(src_dir, filename)))

        mapping = {}
        used_masks = set()
        unmatched_sources = []
        exact_exts = list(XRAY_MASK_CANDIDATE_EXTENSIONS)

        # ==========================================
        # 第一层：精确匹配（保持原有高优先级逻辑）
        # ==========================================
        for filename in source_filenames:
            full_src = os.path.normpath(os.path.join(src_dir, filename))
            rel_src = (
                os.path.join(rel_dir, filename).replace("\\", "/") if rel_dir else filename
            )
            file_stem = self._strip_compound_ext(filename)
            rel_stem = self._strip_compound_ext(rel_src)

            if dual_mode and self.mask_root:
                base_rel = rel_stem.replace("\\", "/")
                rel_with_src_ext = rel_src.replace("\\", "/")
                candidates = (
                    [os.path.join(self.mask_root, base_rel + ext) for ext in exact_exts]
                    + [
                        os.path.join(self.mask_root, base_rel + "_mask" + ext)
                        for ext in exact_exts
                    ]
                    + [
                        os.path.join(self.mask_root, rel_with_src_ext + ext)
                        for ext in exact_exts
                    ]
                )
            else:
                candidates = (
                    [os.path.join(src_dir, file_stem + ext) for ext in exact_exts]
                    + [os.path.join(src_dir, file_stem + "_mask" + ext) for ext in exact_exts]
                    + [os.path.join(src_dir, filename + ext) for ext in exact_exts]
                )

            chosen = ""
            seen = set()
            for candidate in candidates:
                if not candidate:
                    continue
                norm_candidate = os.path.normpath(candidate)
                if norm_candidate in seen:
                    continue
                seen.add(norm_candidate)
                if norm_candidate == full_src:
                    continue
                if norm_candidate in all_mask_paths and norm_candidate not in used_masks:
                    chosen = norm_candidate
                    break

            if chosen:
                mapping[full_src] = chosen
                used_masks.add(chosen)
            else:
                unmatched_sources.append((filename, full_src))

        if not unmatched_sources:
            cache[cache_key] = dict(mapping)
            return dict(mapping)

        # ==========================================
        # 第二层：模糊包含匹配
        # 只要掩码 stem 包含原图 stem，或原图 stem 包含掩码 stem，即视为匹配
        # ==========================================
        still_unmatched = []
        available_masks = sorted(
            list(all_mask_paths - used_masks),
            key=lambda p: natural_sort_key(os.path.basename(p)),
        )

        for filename, full_src in unmatched_sources:
            src_stem = self._extract_meaningful_stem(filename)
            if not src_stem:
                still_unmatched.append((filename, full_src))
                continue

            found = False
            for mask_path in list(available_masks):
                mask_stem = self._extract_meaningful_stem(os.path.basename(mask_path))
                if not mask_stem:
                    continue
                if src_stem in mask_stem or mask_stem in src_stem:
                    mapping[full_src] = mask_path
                    used_masks.add(mask_path)
                    available_masks.remove(mask_path)
                    found = True
                    break

            if not found:
                still_unmatched.append((filename, full_src))

        if not still_unmatched or not available_masks:
            cache[cache_key] = dict(mapping)
            return dict(mapping)

        # ==========================================
        # 第三层：终极数量盲配
        # 数量完全相等时，按自然排序一对一强行绑定
        # ==========================================
        still_unmatched.sort(key=lambda item: natural_sort_key(item[0]))
        available_masks.sort(key=lambda p: natural_sort_key(os.path.basename(p)))

        if len(still_unmatched) == len(available_masks):
            for (_, full_src), mask_path in zip(still_unmatched, available_masks):
                mapping[full_src] = mask_path

        cache[cache_key] = dict(mapping)
        return dict(mapping)

    def _resolve_xray_mask_path(self, orig_path, rel_src=None):
        if not orig_path:
            return ""

        rel_src = (rel_src or os.path.relpath(orig_path, self.orig_root)).replace("\\", "/")
        src_dir = os.path.dirname(orig_path)
        rel_dir = os.path.dirname(rel_src)
        mapping = self._build_xray_dir_mask_map(src_dir, rel_dir)
        return mapping.get(os.path.normpath(orig_path), "")

    def _resolve_ct_mask_path(self, orig_path, p_mask, rel_in_case):
        """CT 序列模式下搜索已有掩码（支持 NIfTI），找不到则回退为默认 PNG 路径。

        参数:
            orig_path:    原图绝对路径
            p_mask:       掩码根目录 (已含 case_name)
            rel_in_case:  原图相对于病例目录的相对路径 (如 "slice001.dcm")
        返回:
            掩码路径 (已有文件 或 默认 .png 路径)
        """
        stem = os.path.splitext(rel_in_case)[0]
        # NIfTI 的复合扩展名需特殊处理
        if rel_in_case.lower().endswith(DEFAULT_NIFTI_EXT):
            stem = rel_in_case[: -len(DEFAULT_NIFTI_EXT)]

        # 搜索顺序：先查已有文件，NIfTI 和 PNG 都查
        candidates = [
            os.path.join(p_mask, stem + suffix) for suffix in CT_MASK_CANDIDATE_SUFFIXES
        ]
        seen = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            norm = os.path.normpath(candidate)
            if norm != os.path.normpath(orig_path) and os.path.exists(candidate):
                return candidate

        # 回退：默认 PNG 路径
        return default_mask_path(p_mask, stem, DEFAULT_MASK_BITMAP_EXT)

    def _build_ct_case_entries(self, case_name):
        p_orig = (
            os.path.join(self.orig_root, case_name)
            if case_name != "Root"
            else self.orig_root
        )
        p_mask = os.path.join(self.mask_root, case_name) if self.mask_root else p_orig

        files = []
        exts = set(CT_SOURCE_EXTENSIONS)
        for root, _, filenames in os.walk(p_orig):
            for filename in filenames:
                if os.path.splitext(filename)[1].lower() not in exts:
                    continue
                full_src = os.path.join(root, filename)
                rel_in_case = os.path.relpath(full_src, p_orig)
                rel_src = os.path.relpath(full_src, self.orig_root).replace("\\", "/")
                mask_path = self._resolve_ct_mask_path(full_src, p_mask, rel_in_case)
                files.append(
                    ImageEntry(
                        case_name=case_name,
                        orig_path=full_src,
                        mask_path=mask_path,
                        filename=rel_in_case,
                        has_mask=os.path.exists(mask_path),
                        has_pneumothorax=self._labels_cache.get(rel_src, 0),
                    )
                )
        files.sort(key=lambda x: natural_sort_key(x.filename))
        return files

    # ------------------------------------------------------------------
    # 数据加载核心：磁盘读取 / 缓存读取（不涉及任何 UI 操作）
    # ------------------------------------------------------------------

    def _read_entry_from_disk(self, entry):
        """从磁盘读取 entry 的图像和掩码。

        返回 (img, mask, meta) 三元组；读取失败时返回 None。
        不操作缓存，不操作 UI，可在后台线程安全调用。
        """
        meta = None
        result = read_dicom_with_window(entry.orig_path)
        if result:
            img, raw, wc, ww, (min_val, max_val) = result
            meta = {"raw": raw, "wc": wc, "ww": ww, "min": min_val, "max": max_val}
        else:
            img = smart_read_image(entry.orig_path)

        if img is None:
            return None

        mask = None
        if os.path.exists(entry.mask_path):
            # [修复] 本应用保存的 NIfTI 掩码始终与原图共享像素网格，
            # target_shape 足以保证对齐。传 reference_image_path 会触发
            # read_mask_file 的物理空间重采样，一旦 NIfTI 的 spacing 与
            # 参考图不一致（写入时 CopyInformation 可能静默失败，遗留默认
            # spacing），掩码就会被放大，表现为"加载回来全红"。
            # 原判断仅覆盖 "DICOM + NIfTI"，这里扩展到任何 NIfTI 掩码，
            # 因为读取风险来自 NIfTI 的 spacing 元数据，与原图格式无关。
            mask_is_nifti = entry.mask_path.lower().endswith((".nii", ".nii.gz"))
            ref_path = None if mask_is_nifti else entry.orig_path

            mask, _ = read_mask_file(
                entry.mask_path,
                target_shape=img.shape[:2],
                reference_image_path=ref_path,
            )
        if mask is None:
            mask = self._alloc_mask(img.shape[:2])

        return img, mask, meta

    def _load_entry_payload(self, entry):
        """从缓存或磁盘加载 entry 的数据，返回 (img, mask, meta) 或 None。

        优先命中缓存；未命中则从磁盘读取并写入缓存。不涉及 UI 操作。
        """
        key = entry.orig_path

        # 缓存命中
        cached = self._cache_get(key)
        if cached:
            img, mask = cached[0], cached[1]
            meta = cached[2] if len(cached) >= 3 else None
            return img, mask, meta

        # 缓存未命中：磁盘读取
        payload = self._read_entry_from_disk(entry)
        if payload is None:
            return None

        img, mask, meta = payload
        self._cache_set(key, (img, mask, meta))
        return img, mask, meta

    def _build_prefetch_indices(self, current_idx):
        total = len(self.entries)
        if total <= 0 or self.ct_prefetch_count <= 0:
            return []

        span = min(total, self.ct_prefetch_count * 2 + 1)
        start = max(0, current_idx - span)
        end = min(total, current_idx + span + 1)

        candidates = [i for i in range(start, end) if i != current_idx]
        candidates.sort(key=lambda i: (abs(i - current_idx), i))

        return candidates[: self.ct_prefetch_count]

    def _next_prefetch_epoch(self):
        self._prefetch_epoch = getattr(self, "_prefetch_epoch", 0) + 1
        return self._prefetch_epoch

    def _next_prefetch_worker_token(self, kind):
        attr = f"_{kind}_prefetch_token"
        token = getattr(self, attr, 0) + 1
        setattr(self, attr, token)
        return token

    def _start_prefetch(self, current_idx):
        indices = self._build_prefetch_indices(current_idx)
        if not indices:
            return

        epoch = getattr(self, "_prefetch_epoch", 0)
        token = self._next_prefetch_worker_token("series")

        t = threading.Thread(
            target=self._prefetch_worker, args=(epoch, token, indices), daemon=True
        )
        t.start()

    def _prefetch_worker(self, epoch, token, indices):
        for i in indices:
            if epoch != getattr(self, "_prefetch_epoch", -1):
                return
            if token != getattr(self, "_series_prefetch_token", -1):
                return

            # [修复] 增加越界保护，防止主线程清空 entries 时后台预取线程还在强行读取报错
            if i < 0 or i >= len(self.entries):
                continue

            try:
                entry = self.entries[i]
            except IndexError:
                continue

            key = entry.orig_path

            with self._cache_lock:
                if key in self._image_cache or key in self._prefetch_inflight:
                    continue
                self._prefetch_inflight.add(key)

            try:
                payload = self._read_entry_from_disk(entry)
                if payload is None:
                    continue
                img, mask, meta = payload
                self._cache_set(key, (img, mask, meta))
            finally:
                with self._cache_lock:
                    self._prefetch_inflight.discard(key)

    def _start_cross_case_prefetch(self):
        if self.scan_mode == ScanMode.CT_SEQUENCE:
            target_count = self.ct_cross_count
        else:
            target_count = self.xray_prefetch_count
        if target_count <= 0:
            return
        if self.task_mode or self.single_pair_mode:
            return
        case_name = getattr(self, "current_case_name", None)
        if not case_name:
            return
        entries = self._collect_next_case_entries(case_name, target_count)
        if not entries:
            return
        epoch = getattr(self, "_prefetch_epoch", 0)
        token = self._next_prefetch_worker_token("cross_case")
        t = threading.Thread(
            target=self._prefetch_case_worker, args=(epoch, token, entries), daemon=True
        )
        t.start()

    def _collect_next_case_entries(self, case_name, count):
        """收集当前病例之后的 count 个病例的所有切片 Entry。

        修复：
        1. 同时搜索 list_todo 和 list_annotated，不再漏掉"已标注"病例的后续。
        2. 调用 _expand_case_to_entries，正确处理 CT 目录病例。
        """
        if count <= 0:
            return []

        # 把两个列表拼成统一的顺序视图：todo 在前，annotated 在后
        all_items = []
        for i in range(self.list_todo.count()):
            item = self.list_todo.item(i)
            if item:
                all_items.append(item.data(Qt.UserRole))
        for i in range(self.list_annotated.count()):
            item = self.list_annotated.item(i)
            if item:
                all_items.append(item.data(Qt.UserRole))

        try:
            current_index = all_items.index(case_name)
        except ValueError:
            return []

        entries = []
        for next_case in all_items[current_index + 1 : current_index + 1 + count]:
            entries.extend(self._expand_case_to_entries(next_case))
        return entries

    def _build_default_xray_mask_path(self, orig_path, rel_src=None):
        stem = self._strip_compound_ext(os.path.basename(orig_path))
        rel_src = (rel_src or os.path.relpath(orig_path, self.orig_root)).replace("\\", "/")
        rel_dir = os.path.dirname(rel_src)

        if is_dual_folder_mode(self.orig_root, self.mask_root) and self.mask_root:
            mask_dir = os.path.join(self.mask_root, rel_dir) if rel_dir else self.mask_root
        else:
            mask_dir = os.path.dirname(orig_path)

        preferred = "png"
        if hasattr(self, "_get_project_mask_format_preference"):
            preferred = self._get_project_mask_format_preference()

        ext = DEFAULT_NIFTI_EXT if preferred == "nii" else DEFAULT_MASK_BITMAP_EXT
        return default_mask_path(mask_dir, stem, ext)

    def _build_xray_entry(self, full_src, case_name, filename=None, rel_src=None, has_pneumo=None):
        filename = filename or os.path.basename(full_src)
        rel_src = (rel_src or os.path.relpath(full_src, self.orig_root)).replace("\\", "/")
        if has_pneumo is None:
            has_pneumo = self._labels_cache.get(rel_src, 0)

        mask_path = self._resolve_xray_mask_path(full_src, rel_src=rel_src)
        if not mask_path:
            mask_path = self._build_default_xray_mask_path(full_src, rel_src=rel_src)

        return ImageEntry(
            case_name=case_name,
            orig_path=full_src,
            mask_path=mask_path,
            filename=filename,
            has_mask=os.path.exists(mask_path),
            has_pneumothorax=has_pneumo,
        )

    def _build_xray_case_entries(self, case_name):
        case_file_path = os.path.join(self.orig_root, case_name)
        if os.path.isfile(case_file_path):
            return [
                self._build_xray_entry(
                    case_file_path,
                    case_name=case_name,
                    filename=os.path.basename(case_file_path),
                    rel_src=case_name.replace("\\", "/"),
                )
            ]

        if not os.path.isdir(case_file_path):
            return []

        files = []
        for filename in self._iter_xray_source_filenames(case_file_path):
            full_src = os.path.join(case_file_path, filename)
            rel_src = os.path.relpath(full_src, self.orig_root).replace("\\", "/")
            files.append(
                self._build_xray_entry(
                    full_src,
                    case_name=case_name,
                    filename=filename,
                    rel_src=rel_src,
                )
            )
        files.sort(key=lambda x: natural_sort_key(x.filename))
        return files

    def _refresh_task_progress_ui(self) -> None:
          """根据当前 task_mode / 列表状态刷新任务进度相关 UI。"""
          # 非任务模式：恢复 UI 到普通样式
          if not getattr(self, "task_mode", False):
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

          # 任务模式：根据病例列表统计进度
          done = self.list_annotated.count()
          pending = self.list_todo.count()
          total_cases = done + pending

          # 阳性病例数：基于 task_case_entries 按病例聚合
          positive_cases = 0
          for case_name in getattr(self, "task_case_order", []):
              entries = self.task_case_entries.get(case_name, [])
              if any(e.has_pneumothorax == 1 for e in entries):
                  positive_cases += 1

          task_name = ""
          if getattr(self, "task_json_path", ""):
              from pathlib import Path
              task_name = Path(self.task_json_path).stem

          # 更新左侧分组标题
          if hasattr(self, "update_case_list_headers"):
              self.update_case_list_headers(
                  total_cases=total_cases,
                  done_cases=done,
                  pending_cases=pending,
              )

          # 更新状态栏黄色任务进度标签
          if hasattr(self, "_update_task_status_bar"):
              self._update_task_status_bar(
                  task_name=task_name,
                  done=done,
                  total=total_cases,
                  positive_cases=positive_cases,
              )

          # 更新窗口标题
          if hasattr(self, "_update_window_title"):
              self._update_window_title()
    
    
    
    def _build_case_entries(self, case_name):
        """根据当前模式构建指定病例的 ImageEntry 列表。

        - 任务模式：直接使用 task_case_entries 中的 entries。
        - 普通 CT 模式：按病例目录展开所有切片。
        - 普通 X 光模式：按病例名（相对路径）展开。
        """
        if self.task_mode:
            files = list(self.task_case_entries.get(case_name, []))
            files.sort(key=lambda x: natural_sort_key(x.filename))
            return files

        if self.scan_mode == ScanMode.CT_SEQUENCE:
            return self._build_ct_case_entries(case_name)

        return self._build_xray_case_entries(case_name)

    def _expand_case_to_entries(self, case_name):
        """把一个病例名展开成 ImageEntry 列表，用于跨病例预取等场景。"""
        if not case_name:
            return []

        if self.task_mode:
            files = list(self.task_case_entries.get(case_name, []))
            files.sort(key=lambda x: natural_sort_key(x.filename))
            return files

        if self.scan_mode == ScanMode.CT_SEQUENCE:
            return self._build_ct_case_entries(case_name)

        return self._build_xray_case_entries(case_name)

    def _prefetch_case_worker(self, epoch, token, entries):
        for entry in entries:
            if epoch != getattr(self, "_prefetch_epoch", -1):
                return
            if token != getattr(self, "_cross_case_prefetch_token", -1):
                return
            key = entry.orig_path
            with self._cache_lock:
                if key in self._image_cache or key in self._prefetch_inflight:
                    continue
                self._prefetch_inflight.add(key)
            try:
                payload = self._read_entry_from_disk(entry)
                if payload is None:
                    continue
                img, mask, meta = payload
                self._cache_set(key, (img, mask, meta))
            finally:
                with self._cache_lock:
                    self._prefetch_inflight.discard(key)

    def select_orig_dir(self):
        """选择原图目录"""
        self.single_pair_mode = False
        d = QFileDialog.getExistingDirectory(self, "选择原图目录 (Source)")
        if d:
            self.task_mode = False
            self.orig_root = d
            self.refresh_lists()

    def select_mask_dir(self):
        """选择掩码目录"""
        self.single_pair_mode = False
        d = QFileDialog.getExistingDirectory(self, "选择掩码目录 (Mask)")
        if d:
            self.task_mode = False
            self.mask_root = d
            if self.orig_root:
                self.refresh_lists()

    def select_task_json(self):
        self.single_pair_mode = False
        path, _ = QFileDialog.getOpenFileName(
            self, "选择任务JSON文件", "", "JSON Files (*.json)"
        )
        if path:
            self.load_task_json(path)

    def export_selected_task_json(self):
        selected_items = list(self.list_annotated.selectedItems()) + list(
            self.list_todo.selectedItems()
        )
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

        task_dict = {}

        # 任务模式：严格沿用原始任务 JSON 的 key
        if self.task_mode:
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
        else:
            # 普通模式：根据扫描模式区分 CT / X 光
            if self.scan_mode == ScanMode.CT_SEQUENCE:
                base_dir = self.orig_root or ""
                for case_name in selected_case_names:
                    entries = self._build_ct_case_entries(case_name)
                    for entry in entries:
                        rel_src = os.path.relpath(entry.orig_path, base_dir).replace(
                            "\\", "/"
                        )
                        has_pneumo = entry.has_pneumothorax
                        has_pneumo = int(self._labels_cache.get(rel_src, has_pneumo))
                        task_dict[rel_src] = has_pneumo
            else:
                # X 光：UserRole 就是相对路径
                for case_name in selected_case_names:
                    rel_src = str(case_name).replace("\\", "/")
                    has_pneumo = int(self._labels_cache.get(rel_src, 0))
                    task_dict[rel_src] = has_pneumo

        if not task_dict:
            QMessageBox.information(self, "提示", "未能构造任何任务条目，请检查选择。")
            return

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

        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(task_dict, f, indent=4, ensure_ascii=False)
                self.statusBar().showMessage(
                    f"成功导出子任务 JSON: {os.path.basename(save_path)}", 5000
                )
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败:\n{e}")

    def _read_task_json(self, json_path):
        """多编码读取 JSON 文件，返回 dict 或 None。"""
        for enc in ("utf-8-sig", "utf-8", "gbk"):
            try:
                with open(json_path, "r", encoding=enc) as f:
                    data = json.load(f)
                if isinstance(data, dict) and data:
                    return data
            except Exception:
                continue
        return None

    def _resolve_task_base_dir(self, json_path, data):
        """根据 JSON 路径和首条 entry 推断影像根目录。"""
        json_dir = os.path.dirname(json_path)
        base_dir = self.orig_root if self.orig_root else json_dir

        first_rel = str(next(iter(data.keys()))).replace("\\", "/").lstrip("/")
        if not os.path.isabs(first_rel):
            old_path = os.path.join(base_dir, first_rel)
            new_path = os.path.join(json_dir, first_rel)
            if not os.path.exists(old_path) and os.path.exists(new_path):
                base_dir = json_dir

        return base_dir

    def _build_task_entries(self, data, base_dir):
        """纯数据函数：从 JSON dict 构建 entry 列表。

        返回 (entries, missing, task_key_map)。不操作 self 状态，不弹窗。
        """
        entries = []
        missing = []
        task_key_map = {}

        for rel_path, label in data.items():
            rel_str = str(rel_path).replace("\\", "/").lstrip("/")
            full_src = (
                rel_str if os.path.isabs(rel_str) else os.path.join(base_dir, rel_str)
            )
            full_src = os.path.normpath(full_src)

            if not os.path.exists(full_src):
                missing.append(rel_str)
                continue

            rel_norm = os.path.relpath(full_src, base_dir).replace("\\", "/")
            has_pneumo = 1 if str(label).strip() in ("1", "true", "True") else 0

            if self.scan_mode == ScanMode.CT_SEQUENCE:
                parts = rel_norm.split("/")
                case_name = parts[0] if len(parts) > 1 else "Root"
                # [修复] self.mask_root 在 _commit_task_context 之前可能为空，
                # 用 base_dir 兜底，避免拼出相对路径导致 NIfTI 掩码找不到
                mask_root_for_task = self.mask_root if self.mask_root else base_dir
                mask_path = self._resolve_ct_mask_path(
                    full_src, mask_root_for_task, rel_norm
                )
                filename = rel_norm
            else:
                case_name = rel_norm
                mask_path = self._resolve_xray_mask_path(full_src, rel_src=rel_norm)
                if not mask_path:
                    mask_path = self._build_default_xray_mask_path(full_src, rel_src=rel_norm)
                filename = os.path.basename(full_src)

            entry = ImageEntry(
                case_name=case_name,
                orig_path=full_src,
                mask_path=mask_path,
                filename=filename,
                has_mask=os.path.exists(mask_path),
                has_pneumothorax=has_pneumo,
            )
            entries.append(entry)
            # [修复] task_key_map 的 value 使用规范化后的 key（正斜杠、去掉前导"/"），
            # 与 _labels_cache 的 key 格式保持一致，避免下游查询/写入时反斜杠导致的
            # 键不匹配问题（Windows 上尤其常见）。
            task_key_map[entry.orig_path] = rel_str

        return entries, missing, task_key_map

    def _commit_task_context(self, json_path, base_dir, entries, task_key_map):
        """将解析结果写入 self.task_* 状态，切换为任务模式。不弹窗。"""
        if not self.mask_root or self.mask_root == self.orig_root:
            self.mask_root = base_dir
        self.orig_root = base_dir

        self.task_json_path = json_path
        self.task_entries = entries
        self.task_key_map = task_key_map
        self.task_case_entries = {}
        self.task_case_order = []

        for entry in entries:
            if entry.case_name not in self.task_case_entries:
                self.task_case_entries[entry.case_name] = []
                self.task_case_order.append(entry.case_name)
            self.task_case_entries[entry.case_name].append(entry)

        self.task_mode = True
        self._init_labels_cache()

        # [修复] 旧方案 flush 写回任务 JSON，_build_task_entries 读 JSON 得到最新值；
        # SQLite 方案 flush 只写 DB，JSON 不再更新，重启后 entry.has_pneumothorax
        # 会停留在原始 JSON 值。这里用 _labels_cache（来自 SQLite）覆盖，确保一致。
        for entry in self.task_entries:
            raw_key = self.task_key_map.get(entry.orig_path)
            if raw_key is not None:
                norm_key = str(raw_key).replace("\\", "/")
                if norm_key in self._labels_cache:
                    entry.has_pneumothorax = int(self._labels_cache[norm_key])

    def _build_task_case_lists(self):
        """根据 task_case_entries 重建任务模式下的左右病例列表。"""
        self.list_annotated.clear()
        self.list_todo.clear()
        status_map = self._load_case_status()

        for case_name in self.task_case_order:
            case_entries = self.task_case_entries.get(case_name, [])
            if not case_entries:
                continue

            # 病例是否阳性：只要有一张 has_pneumothorax == 1
            has_pneumo = any(e.has_pneumothorax == 1 for e in case_entries)

            # 病例是否完成：优先用 case_status，缺省时回退到 has_mask
            completed_flags: list[bool] = []
            for entry in case_entries:
                key = self.task_key_map.get(entry.orig_path)
                if key and key in status_map:
                    completed_flags.append(status_map.get(key) == "completed")
                else:
                    completed_flags.append(entry.has_mask)
            is_completed = all(completed_flags) if completed_flags else False

            item = QListWidgetItem(case_name)
            item.setData(Qt.UserRole, case_name)
            if has_pneumo:
                item.setForeground(QColor("#ff5555"))

            if is_completed:
                self.list_annotated.addItem(item)
            else:
                self.list_todo.addItem(item)

        # 自动选中一个病例并加载
        target_list = None
        if self.list_todo.count() > 0:
            target_list = self.list_todo
        elif self.list_annotated.count() > 0:
            target_list = self.list_annotated

        if target_list is not None:
            target_list.setCurrentRow(0)
            self.load_case_sequence(target_list.currentItem())

    # ------------------------------------------------------------------
    # load_task_json：协调函数（唯一允许碰 UI 的入口）
    # ------------------------------------------------------------------

    def load_task_json(self, json_path: str):
        self._flush_labels_cache()
        if hasattr(self, "_xray_dir_match_cache"):
            self._xray_dir_match_cache.clear()

        data = self._read_task_json(json_path)
        if data is None:
            QMessageBox.warning(self, "错误", "任务JSON为空或格式不正确")
            return

        self._cancel_pending_scan()

        base_dir = self._resolve_task_base_dir(json_path, data)
        entries, missing, task_key_map = self._build_task_entries(data, base_dir)

        if not entries:
            QMessageBox.warning(self, "错误", "未找到可加载的任务影像")
            return

        self._commit_task_context(json_path, base_dir, entries, task_key_map)
        self._build_task_case_lists()

        # 任务模式 UI 初始化
        if hasattr(self, "_refresh_task_progress_ui"):
            self._refresh_task_progress_ui()

        if missing:
            sample = "\n".join(missing[:8])
            QMessageBox.warning(
                self, "提示", f"以下任务路径未找到:\n{sample}\n共 {len(missing)} 条"
            )

    def _cancel_pending_scan(self):
        """中断正在进行的后台目录扫描。

        递增 token 使旧扫描线程失效，停止轮询定时器，关闭进度对话框，
        清空结果队列。可在 load_task_json / refresh_lists / 用户取消 等场景复用。
        """
        self._scan_token += 1
        if getattr(self, "_scan_timer", None):
            self._scan_timer.stop()
            self._scan_timer = None
        self._internal_scan_queue = None
        if getattr(self, "_scan_progress", None):
            self._scan_progress.close()
            self._scan_progress = None

    def _on_scan_cancelled(self):
        self._cancel_pending_scan()
        self.statusBar().showMessage("扫描已取消", 2000)

    def exit_task_mode(self):
        # 1) 强制写盘标签缓存，避免防抖丢最后一批
        if hasattr(self, "_flush_labels_cache"):
            self._flush_labels_cache(force=True)

        # 2) 不在任务模式直接提示
        if not getattr(self, "task_mode", False):
            QMessageBox.information(self, "提示", "当前不在任务模式。")
            return

        # 3) 清理任务相关字段
        self.task_mode = False
        self.task_json_path = ""
        self.task_entries = []
        self.task_case_entries.clear()
        self.task_case_order.clear()
        self.task_key_map.clear()

        # 4) 清空 UI 列表及当前病例状态
        self.list_annotated.clear()
        self.list_todo.clear()
        self.entries.clear()
        self.current_idx = -1
        self.thumbnail_strip.clear()
        if hasattr(self, "current_case_name"):
            self.current_case_name = ""

        QMessageBox.information(self, "提示", "已退出任务模式，请重新扫描影像目录。")

        # 5) 刷新标题/状态栏/分组标题
        if hasattr(self, "_refresh_task_progress_ui"):
            self._refresh_task_progress_ui()

    def _internal_scan_worker(
        self, token, scan_mode, orig_root, mask_root, status_map, result_queue
    ):
        found_cases = []
        try:
            if scan_mode == ScanMode.CT_SEQUENCE:
                patients = [
                    d
                    for d in os.listdir(orig_root)
                    if os.path.isdir(os.path.join(orig_root, d))
                ]

                for p in patients:
                    case_name = p
                    has_pneumo = False

                    prefix = case_name + "/"
                    for rel_path, val in self._labels_cache.items():
                        if rel_path.startswith(prefix) and val == 1:
                            has_pneumo = True
                            break

                    is_completed = False
                    if case_name in status_map:
                        is_completed = status_map[case_name] == "completed"
                    elif mask_root:
                        p_mask = os.path.join(mask_root, case_name)
                        is_completed = os.path.isdir(p_mask)

                    found_cases.append((case_name, is_completed, has_pneumo))

            else:
                for root_dir, _, _ in os.walk(orig_root):
                    for f in self._iter_xray_source_filenames(root_dir):
                        full_path = os.path.join(root_dir, f)

                        case_name = os.path.relpath(full_path, orig_root).replace(
                            "\\", "/"
                        )
                        has_pneumo = self._labels_cache.get(case_name, 0) == 1

                        is_completed = False
                        if case_name in status_map:
                            is_completed = status_map[case_name] == "completed"
                        else:
                            mask_path = self._resolve_xray_mask_path(
                                full_path, rel_src=case_name
                            )
                            is_completed = bool(mask_path and os.path.exists(mask_path))

                        found_cases.append((case_name, is_completed, has_pneumo))

            found_cases.sort(key=lambda x: natural_sort_key(x[0]))

        except Exception as e:
            print(f"内置扫描报错: {e}")

        result_queue.put(found_cases)

    def _poll_scan_result(self, token):
        if token != self._scan_token:
            return
        if self.task_mode:
            return
        if not hasattr(self, "_internal_scan_queue") or not self._internal_scan_queue:
            return

        try:
            found_cases = self._internal_scan_queue.get_nowait()
        except queue.Empty:
            return

        if getattr(self, "_scan_timer", None):
            self._scan_timer.stop()
            self._scan_timer = None
        self._internal_scan_queue = None

        if getattr(self, "_scan_progress", None):
            self._scan_progress.close()
            self._scan_progress = None

        if not isinstance(found_cases, list):
            return

        self.list_annotated.setUpdatesEnabled(False)
        self.list_todo.setUpdatesEnabled(False)

        for case, status, has_pneumo in found_cases:
            item = QListWidgetItem(case)
            item.setData(Qt.UserRole, case)
            if has_pneumo:
                item.setForeground(QColor("#ff5555"))
            if status:
                self.list_annotated.addItem(item)
            else:
                self.list_todo.addItem(item)

        self.list_annotated.setUpdatesEnabled(True)
        self.list_todo.setUpdatesEnabled(True)

        self.list_annotated.update()
        self.list_todo.update()
        QApplication.processEvents()

        self.statusBar().showMessage(f"扫描完成：{len(found_cases)} 个病例")

    def refresh_lists(self):
        """完全解耦的目录扫描，根据UI选项智能处理"""
        self.single_pair_mode = False
        if hasattr(self, "_xray_dir_match_cache"):
            self._xray_dir_match_cache.clear()

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

        self._cancel_pending_scan()
        token = self._scan_token

        progress = QProgressDialog("正在扫描病例...", "取消", 0, 0, self)
        progress.setWindowModality(Qt.NonModal)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()
        self._scan_progress = progress
        progress.canceled.connect(self._on_scan_cancelled)

        self._internal_scan_queue = queue.Queue()
        self._scan_thread = threading.Thread(
            target=self._internal_scan_worker,
            args=(
                token,
                self.scan_mode,
                self.orig_root,
                self.mask_root,
                status_map,
                self._internal_scan_queue,
            ),
        )
        self._scan_thread.daemon = True
        self._scan_thread.start()

        self._scan_timer = QTimer(self)
        self._scan_timer.setInterval(200)
        self._scan_timer.timeout.connect(lambda: self._poll_scan_result(token))
        self._scan_timer.start()

    def _start_case_background_work(self, case_name, thumb_token=None):
        if case_name != getattr(self, "current_case_name", None):
            return
        if self.current_idx < 0 or self.current_idx >= len(self.entries):
            return

        if self.scan_mode == ScanMode.CT_SEQUENCE:
            if thumb_token is not None and hasattr(self, "_thumb_drain_timer"):
                self._thumb_drain_timer.start()
                t = threading.Thread(
                    target=self._thumb_worker,
                    args=(list(self.entries), thumb_token),
                    daemon=True,
                )
                t.start()
            self._start_prefetch(self.current_idx)
            if self.current_idx == 0:
                self._start_cross_case_prefetch()
        else:
            self._start_cross_case_prefetch()

    # ------------------------------------------------------------------
    # load_case_sequence 拆分
    # ------------------------------------------------------------------

    def _before_case_switch(self):
        """切换病例前的收尾工作：保存、清空空掩码、推进预取 epoch。"""
        # [修复] 切换病例时立即推进预取 epoch，终止旧病例后台预取
        self._next_prefetch_epoch()

        if self.autosave_enabled and self.current_idx >= 0 and self.canvas._is_dirty:
            self.save_mask()

        if hasattr(self, "_cleanup_empty_masks"):
            self._cleanup_empty_masks()

    def _reset_case_view_state(self, case_name):
        """清空 UI 容器，重置索引，准备接收新病例数据。"""
        self.current_case_name = case_name
        self.entries.clear()
        self.thumbnail_strip.clear()
        self.current_idx = -1

        if hasattr(self, "info_panel") and hasattr(self.info_panel, "table"):
            self.info_panel.table.setRowCount(0)

    def _populate_case_navigation(self, files):
        """根据扫描模式初始化缩略图占位符和 seek_slider。

        返回 thumb_token (CT 模式) 或 None (X-ray 模式)。
        """
        is_ct = self.scan_mode == ScanMode.CT_SEQUENCE
        thumb_token = None

        if is_ct:
            self._thumb_token = getattr(self, "_thumb_token", 0) + 1
            thumb_token = self._thumb_token

            if not hasattr(self, "_thumb_queue"):
                self._thumb_queue = queue.Queue()
                self._thumb_drain_timer = QTimer(self)
                self._thumb_drain_timer.setInterval(40)
                self._thumb_drain_timer.timeout.connect(self._drain_thumb_queue)

            placeholder_pix = QPixmap(80, 80)
            placeholder_pix.fill(QColor("#252535"))
            placeholder_icon = QIcon(placeholder_pix)

            self.thumbnail_strip.setUpdatesEnabled(False)
            for i, entry in enumerate(files):
                l_item = QListWidgetItem(placeholder_icon, "")
                l_item.setToolTip(f"{i + 1}: {entry.filename}")
                self.thumbnail_strip.addItem(l_item)
            self.thumbnail_strip.setUpdatesEnabled(True)

            if self.entries:
                self.seek_slider.setRange(0, len(self.entries) - 1)
                self.seek_slider.setEnabled(True)
            else:
                self.seek_slider.setEnabled(False)
        else:
            self.seek_slider.setEnabled(False)

        return thumb_token

    def load_case_sequence(self, item):
        """协调函数：切换并加载一个病例的完整序列。"""
        self._before_case_switch()

        case_name = item.data(Qt.UserRole)
        self._reset_case_view_state(case_name)

        files = self._build_case_entries(case_name)
        self.entries = files

        # 性能优化：切病例时保留现有缓存，只推进 epoch 终止旧预取；
        # 这样首帧命中缓存时不会被强制重新读盘。
        self._reset_cache(clear_cache=False, invalidate_prefetch=False)

        self.statusBar().showMessage(f"加载序列: {case_name} ({len(files)} 张)")

        thumb_token = self._populate_case_navigation(files)

        if self.entries:
            self.load_image_at_index(0, start_background=False)
            QTimer.singleShot(
                0,
                lambda cn=case_name, tt=thumb_token: self._start_case_background_work(cn, tt),
            )

    def _thumb_worker(self, entries, token):
        """后台线程：逐张生成缩略图并放入队列，由主线程消费。"""
        for i, entry in enumerate(entries):
            if getattr(self, "_thumb_token", 0) != token:
                return

            icon = self._build_thumb_icon(entry)
            self._thumb_queue.put((token, i, icon))

        self._thumb_queue.put((token, None, None))

    def _build_thumb_icon(self, entry) -> QIcon:
        """优先复用缓存，降低缩略图线程对磁盘的重复读取。"""
        cached = None
        with self._cache_lock:
            cached = self._image_cache.get(entry.orig_path)

        img_thumb = None
        mask_img = None
        if cached:
            img_thumb = cached[0]
            if entry.has_mask and len(cached) >= 2:
                mask_img = cached[1]
        else:
            img_thumb = smart_read_image(entry.orig_path)
            if img_thumb is None:
                return QIcon()
            if entry.has_mask and os.path.exists(entry.mask_path):
                # [修复] 与 _read_entry_from_disk 对齐：NIfTI 掩码始终跳过物理空间
                # 重采样，只按 target_shape 对齐，避免 spacing 不一致导致的放大。
                mask_is_nifti = entry.mask_path.lower().endswith((".nii", ".nii.gz"))
                ref_path = None if mask_is_nifti else entry.orig_path

                mask_img, _ = read_mask_file(
                    entry.mask_path,
                    target_shape=(80, 80),
                    reference_image_path=ref_path,
                )

        img_thumb = cv2.resize(img_thumb, (80, 80), interpolation=cv2.INTER_AREA)
        if len(img_thumb.shape) == 2:
            img_thumb = cv2.cvtColor(img_thumb, cv2.COLOR_GRAY2RGB)

        if mask_img is not None:
            mask_thumb = cv2.resize(mask_img, (80, 80), interpolation=cv2.INTER_NEAREST)
            bin_mask = (mask_thumb >= 127).astype(np.uint8)
            overlay = np.zeros_like(img_thumb)
            overlay[..., 0] = 255
            overlay[..., 1] = 50
            overlay[..., 2] = 50
            alpha = 0.5
            mask3 = bin_mask[..., None].astype(np.float32)
            img_thumb = (
                img_thumb.astype(np.float32) * (1.0 - alpha * mask3)
                + overlay.astype(np.float32) * (alpha * mask3)
            ).astype(np.uint8)

        qimg = QImage(
            img_thumb.data, 80, 80, img_thumb.strides[0], QImage.Format_RGB888
        )
        pix = QPixmap.fromImage(qimg.copy())

        if entry.has_mask:
            p = QPainter(pix)
            p.setPen(QPen(Qt.green, 4))
            p.drawRect(0, 0, 79, 79)
            p.end()

        return QIcon(pix)

    def _drain_thumb_queue(self):
        """主线程定时器：批量消费队列，更新缩略图条目。"""
        BATCH = 20  # 每次最多处理 20 帧，避免单帧占用过长
        processed = 0
        while processed < BATCH:
            try:
                token, idx, icon = self._thumb_queue.get_nowait()
            except queue.Empty:
                break

            # 哨兵：本批次全部完成
            if idx is None:
                if getattr(self, "_thumb_token", 0) == token:
                    self._thumb_drain_timer.stop()
                break

            # 过期 token，丢弃
            if getattr(self, "_thumb_token", 0) != token:
                processed += 1
                continue

            item = self.thumbnail_strip.item(idx)
            if item is not None:
                item.setIcon(icon)
            processed += 1

    def load_image_at_index(self, idx, start_background=True):
        if idx < 0 or idx >= len(self.entries):
            return

        if self.autosave_enabled and self.current_idx >= 0 and self.current_idx != idx:
            if self.canvas._is_dirty:
                self.save_mask()

        preserve_view = self.current_idx != -1
        self.current_idx = idx

        if self.seek_slider.value() != idx:
            self.seek_slider.blockSignals(True)
            self.seek_slider.setValue(idx)
            self.seek_slider.blockSignals(False)

        if self.scan_mode == ScanMode.CT_SEQUENCE:
            self.thumbnail_strip.blockSignals(True)
            self.thumbnail_strip.setCurrentRow(idx)
            self.thumbnail_strip.scrollToItem(
                self.thumbnail_strip.item(idx), QAbstractItemView.PositionAtCenter
            )
            self.thumbnail_strip.blockSignals(False)

        entry = self.entries[idx]
        payload = self._load_entry_payload(entry)
        if payload is None:
            self.statusBar().showMessage(f"无法读取图片: {entry.filename}", 3000)
            return
        img, mask, meta = payload

        if meta:
            center = (
                meta["wc"]
                if meta["wc"] is not None
                else (meta["min"] + meta["max"]) / 2
            )
            width = (
                meta["ww"]
                if meta["ww"] is not None
                else max(2, meta["max"] - meta["min"])
            )
            self.canvas.load_image(
                img,
                mask,
                preserve_view=preserve_view,
                raw=meta["raw"],
                window_center=center,
                window_width=width,
            )
            self.viz_ctrl.set_window_controls(
                center, width, meta["min"], meta["max"], True
            )
        else:
            self.canvas.load_image(img, mask, preserve_view=preserve_view)
            self.viz_ctrl.set_window_controls(0, 0, 0, 0, False)

        if hasattr(self, "info_panel") and self.info_panel.isVisible():
            self.info_panel.update_info(entry.orig_path)

        self._update_status_ui()

        if start_background:
            if self.scan_mode == ScanMode.CT_SEQUENCE:
                self._start_prefetch(idx)
                if idx == 0:
                    self._start_cross_case_prefetch()
            else:
                self._start_cross_case_prefetch()

    def on_slider_change(self, value):
        if value != self.current_idx:
            self.load_image_at_index(value)

    def action_toggle_case_status(self):
        if self.current_idx >= 0 and self.canvas._is_dirty:
            self.save_mask()
        self._flush_labels_cache()

        current_list = None
        target_list = None
        new_status = ""

        # 1) 先确定当前操作来源列表和目标列表（保持原有逻辑）
        if self.list_todo.hasFocus():
            current_list = self.list_todo
            target_list = self.list_annotated
            new_status = "completed"
        elif self.list_annotated.hasFocus():
            current_list = self.list_annotated
            target_list = self.list_todo
            new_status = "todo"
        else:
            if self.list_todo.currentItem():
                current_list = self.list_todo
                target_list = self.list_annotated
                new_status = "completed"
            elif self.list_annotated.currentItem():
                current_list = self.list_annotated
                target_list = self.list_todo
                new_status = "todo"

        if current_list is None:
            self.statusBar().showMessage("未选中任何病例", 1000)
            return

        # 2) 获取当前列表中所有选中病例；若无选中则退回到 currentItem
        selected_items = current_list.selectedItems()
        if not selected_items:
            item = current_list.currentItem()
            if not item:
                self.statusBar().showMessage("未选中任何病例", 1000)
                return
            selected_items = [item]

        # 统一使用 UserRole 作为主键，避免受到文本标记（如 [!P]）影响
        case_names = []
        items_by_case = {}
        for item in selected_items:
            case_name = item.data(Qt.UserRole)
            if not case_name:
                continue
            if case_name not in items_by_case:
                items_by_case[case_name] = []
                case_names.append(case_name)
            items_by_case[case_name].append(item)

        if not case_names:
            self.statusBar().showMessage("未选中任何病例", 1000)
            return

        if self.task_mode:
            # [修复] 直接在 UI 中移动 item，不调 _build_task_case_lists，
            # 避免整表重建后强制跳回 row 0，破坏标注位置。
            first_row = current_list.row(selected_items[0]) if selected_items else 0
            moved_items = []
            for item in selected_items:
                case_name = item.data(Qt.UserRole)
                if not case_name:
                    continue
                self._save_task_case_status(case_name, new_status)
                row = current_list.row(item)
                current_list.takeItem(row)
                target_list.addItem(item)
                moved_items.append((item, case_name))

            if moved_items:
                # 原列表仍有内容：停留在相同行号（自动加载下一个待标注病例）
                remaining = current_list.count()
                if remaining > 0:
                    stay_row = min(first_row, remaining - 1)
                    current_list.setCurrentRow(stay_row)
                else:
                    # 原列表已清空：把焦点移到目标列表的最后一个被移入项
                    target_list.setCurrentItem(moved_items[-1][0])

            msg = (
                "已归档至 [已完成]" if new_status == "completed" else "已退回至 [待标注]"
            )
            if len(moved_items) == 1:
                self.statusBar().showMessage(f"{msg}: {moved_items[0][1]}", 2000)
            else:
                self.statusBar().showMessage(f"{msg}: {len(moved_items)} 个病例", 2000)
        else:
            # 普通扫描模式：批量移动 UI 中的条目并写入 case_status.json
            moved_items = []
            for item in selected_items:
                case_name = item.data(Qt.UserRole)
                if not case_name:
                    continue
                row = current_list.row(item)
                current_list.takeItem(row)
                target_list.addItem(item)
                moved_items.append((item, case_name))

                self._save_single_case_status(case_name, new_status)

            if moved_items:
                # 将焦点放到最后一个移动的病例上
                target_list.setCurrentItem(moved_items[-1][0])

            msg = (
                "已归档至 [已完成]" if new_status == "completed" else "已退回至 [待标注]"
            )
            if len(moved_items) == 1:
                self.statusBar().showMessage(
                    f"{msg}: {moved_items[0][1]}", 2000
                )
            elif len(moved_items) > 1:
                self.statusBar().showMessage(
                    f"{msg}: {len(moved_items)} 个病例", 2000
                )

        if hasattr(self, "_refresh_task_progress_ui"):
            self._refresh_task_progress_ui()

    def export_task_json(self):
        if self.task_mode:
            QMessageBox.information(self, "提示", "当前已经是任务模式，无需再次导出。")
            return

        if not self.orig_root or (
            self.list_todo.count() == 0 and self.list_annotated.count() == 0
        ):
            QMessageBox.warning(
                self, "警告", "当前没有扫描到任何影像，请先选择原图目录并等待扫描完成。"
            )
            return

        all_cases = []
        for i in range(self.list_todo.count()):
            all_cases.append(self.list_todo.item(i).data(Qt.UserRole))
        for i in range(self.list_annotated.count()):
            all_cases.append(self.list_annotated.item(i).data(Qt.UserRole))

        task_dict = {}
        for case_name in all_cases:
            rel_src = case_name.replace("\\", "/")
            has_pneumo = self._labels_cache.get(rel_src, 0)
            task_dict[rel_src] = has_pneumo

        default_save_path = os.path.join(self.orig_root, "master_task.json")
        save_path, _ = QFileDialog.getSaveFileName(
            self, "导出总体任务 JSON", default_save_path, "JSON Files (*.json)"
        )

        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(task_dict, f, indent=4, ensure_ascii=False)
                self.statusBar().showMessage(
                    f"成功导出总体任务 JSON: {os.path.basename(save_path)}", 5000
                )
                QMessageBox.information(
                    self, "成功", f"总任务清单已导出至:\n{save_path}"
                )
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败:\n{str(e)}")