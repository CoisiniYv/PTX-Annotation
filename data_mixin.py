"""数据流程：目录扫描、缓存、加载与病例切换逻辑。"""

import json
import os
import queue
import re
import threading

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
        if self._labels_json_path and os.path.exists(self._labels_json_path):
            for enc in ("utf-8-sig", "utf-8", "gbk"):
                try:
                    with open(self._labels_json_path, "r", encoding=enc) as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        self._labels_cache = data
                    break
                except Exception:
                    continue
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
        path = self._labels_json_path or self._get_labels_json_path()
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._labels_cache, f, indent=4, ensure_ascii=False)
            self._labels_dirty = False
        except Exception:
            return

    def _get_status_file_path(self):
        if self.task_mode and self.task_json_path:
            base_name = os.path.splitext(os.path.basename(self.task_json_path))[0]
            return os.path.join(self.orig_root, f"{base_name}_case_status.json")
        return os.path.join(self.orig_root, "case_status.json")

    def _load_case_status(self):
        path = self._get_status_file_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_single_case_status(self, case_name, status):
        data = self._load_case_status()
        data[case_name] = status
        try:
            with open(self._get_status_file_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving status: {e}")

    def _save_task_case_status(self, case_name, status):
        if not self.task_mode:
            return
        data = self._load_case_status()
        case_entries = self.task_case_entries.get(case_name, [])
        for entry in case_entries:
            key = self.task_key_map.get(entry.orig_path)
            if key:
                data[key] = status
        try:
            with open(self._get_status_file_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving status: {e}")

    def _reset_cache(self, clear_cache: bool = True, invalidate_prefetch: bool = True):
        with self._cache_lock:
            if clear_cache:
                for key, cached_val in list(self._image_cache.items()):
                    img, mask = cached_val[0], cached_val[1]
                    self._release_cache_entry(key, img, mask)
                self._image_cache.clear()
            self._prefetch_inflight.clear()
        if invalidate_prefetch:
            self._next_prefetch_epoch()

    def _cache_get(self, key):
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
        if getattr(self, "_mask_pool_refs", None):
            base = self._mask_pool_refs.pop(id(mask), None)
            if base is not None:
                self._mask_pool.append(base)
        del img, mask

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

    def _is_generic_xray_mask_name(self, filename):
        stem = self._get_xray_mask_stem(filename).lower()
        return bool(stem) and (
            stem == "untitled"
            or stem.startswith("untitled")
            or re.fullmatch(r"\d+", stem) is not None
        )

    def _is_xray_mask_sidecar(self, filename):
        lower = os.path.basename(filename).lower()
        stem = self._get_xray_mask_stem(lower).lower()
        has_mask_ext = lower.endswith(MASK_FILE_EXTENSIONS)

        # NIfTI 在当前项目里始终按掩码侧车处理
        if self._is_nifti_file(lower):
            return True

        # 仅当文件本身就是常见掩码格式时，才把 _mask / Untitled / 纯数字 命名
        # 视为侧车掩码；否则像“1”“2”这类无扩展名 DICOM 会被误排除，导致整目录扫不出来。
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

        base_names = set()
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if (
                ext not in ignored_exts
                and ext != ".png"
                and not self._is_xray_mask_sidecar(f)
            ):
                base_names.add(os.path.splitext(f)[0])

        result = []
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if ext in ignored_exts or self._is_xray_mask_sidecar(f):
                continue
            if ext == ".png" and os.path.splitext(f)[0] in base_names:
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

        source_filenames = self._iter_xray_source_filenames(src_dir)
        if not source_filenames:
            cache[cache_key] = {}
            return {}

        mapping = {}
        used_masks = set()
        exact_exts = list(XRAY_MASK_CANDIDATE_EXTENSIONS)

        def _candidate_paths(file_stem, rel_stem):
            if dual_mode and self.mask_root:
                base_rel = rel_stem.replace("\\", "/")
                return [
                    os.path.join(self.mask_root, base_rel + ext) for ext in exact_exts
                ] + [
                    os.path.join(self.mask_root, base_rel + "_mask" + ext)
                    for ext in exact_exts
                ]
            return [
                os.path.join(src_dir, file_stem + ext) for ext in exact_exts
            ] + [
                os.path.join(src_dir, file_stem + "_mask" + ext)
                for ext in exact_exts
            ]

        unmatched = []
        for filename in source_filenames:
            full_src = os.path.join(src_dir, filename)
            rel_src = os.path.join(rel_dir, filename).replace("\\", "/") if rel_dir else filename
            file_stem = self._strip_compound_ext(filename)
            rel_stem = self._strip_compound_ext(rel_src)
            chosen = ""
            seen = set()
            for candidate in _candidate_paths(file_stem, rel_stem):
                if not candidate:
                    continue
                norm_candidate = os.path.normpath(candidate)
                if norm_candidate in seen:
                    continue
                seen.add(norm_candidate)
                if norm_candidate == os.path.normpath(full_src):
                    continue
                if os.path.exists(candidate):
                    chosen = candidate
                    used_masks.add(norm_candidate)
                    break
            if chosen:
                mapping[os.path.normpath(full_src)] = chosen
            else:
                unmatched.append((filename, full_src))

        generic_masks = []
        if os.path.isdir(mask_dir):
            try:
                for mask_name in os.listdir(mask_dir):
                    mask_path = os.path.join(mask_dir, mask_name)
                    if not os.path.isfile(mask_path):
                        continue
                    lower = mask_name.lower()
                    if not lower.endswith(MASK_FILE_EXTENSIONS):
                        continue
                    norm_mask = os.path.normpath(mask_path)
                    if norm_mask in used_masks:
                        continue
                    if self._is_generic_xray_mask_name(mask_name):
                        generic_masks.append(mask_path)
            except OSError:
                generic_masks = []

        generic_masks.sort(key=lambda p: natural_sort_key(os.path.basename(p)))
        unmatched.sort(key=lambda item: natural_sort_key(item[0]))

        if generic_masks and unmatched:
            can_pair = len(generic_masks) == len(unmatched) or (
                len(generic_masks) == 1 and len(unmatched) == 1
            )
            if can_pair:
                for (_, full_src), mask_path in zip(unmatched, generic_masks):
                    mapping[os.path.normpath(full_src)] = mask_path

        cache[cache_key] = dict(mapping)
        return dict(mapping)

    def _resolve_xray_mask_path(self, orig_path, rel_src=None):
        if not orig_path:
            return ""

        rel_src = (rel_src or os.path.relpath(orig_path, self.orig_root)).replace(
            "\\", "/"
        )
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
                meta = None
                result = read_dicom_with_window(entry.orig_path)
                if result:
                    img, raw, wc, ww, (min_val, max_val) = result
                    meta = {
                        "raw": raw,
                        "wc": wc,
                        "ww": ww,
                        "min": min_val,
                        "max": max_val,
                    }
                else:
                    img = smart_read_image(entry.orig_path)

                if img is None:
                    continue

                mask = None
                if os.path.exists(entry.mask_path):
                    mask, _ = read_mask_file(
                        entry.mask_path,
                        target_shape=img.shape[:2],
                        reference_image_path=entry.orig_path,
                    )
                if mask is None:
                    mask = self._alloc_mask(img.shape[:2])
                if meta:
                    self._cache_set(key, (img, mask, meta))
                else:
                    self._cache_set(key, (img, mask))
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

    def _build_default_xray_mask_path(self, orig_path):
        stem = self._strip_compound_ext(os.path.basename(orig_path))
        mask_dir = self.mask_root or os.path.dirname(orig_path)
        return default_mask_path(mask_dir, stem, DEFAULT_MASK_BITMAP_EXT)

    def _build_xray_entry(self, full_src, case_name, filename=None, rel_src=None, has_pneumo=None):
        filename = filename or os.path.basename(full_src)
        rel_src = (rel_src or os.path.relpath(full_src, self.orig_root)).replace("\\", "/")
        if has_pneumo is None:
            has_pneumo = self._labels_cache.get(rel_src, 0)

        mask_path = self._resolve_xray_mask_path(full_src, rel_src=rel_src)
        if not mask_path:
            mask_path = self._build_default_xray_mask_path(full_src)

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

    def _build_case_entries(self, case_name):
        if self.task_mode:
            files = list(self.task_case_entries.get(case_name, []))
            files.sort(key=lambda x: natural_sort_key(x.filename))
            return files
        if self.scan_mode == ScanMode.CT_SEQUENCE:
            return self._build_ct_case_entries(case_name)
        return self._build_xray_case_entries(case_name)

    def _expand_case_to_entries(self, case_name):
        """把一个病例名展开成 ImageEntry 列表。"""
        if not case_name:
            return []
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
                meta = None
                result = read_dicom_with_window(entry.orig_path)
                if result:
                    img, raw, wc, ww, (min_val, max_val) = result
                    meta = {
                        "raw": raw,
                        "wc": wc,
                        "ww": ww,
                        "min": min_val,
                        "max": max_val,
                    }
                else:
                    img = smart_read_image(entry.orig_path)
                if img is None:
                    continue
                mask = None
                if os.path.exists(entry.mask_path):
                    mask, _ = read_mask_file(
                        entry.mask_path,
                        target_shape=img.shape[:2],
                        reference_image_path=entry.orig_path,
                    )
                if mask is None:
                    mask = self._alloc_mask(img.shape[:2])
                if meta:
                    self._cache_set(key, (img, mask, meta))
                else:
                    self._cache_set(key, (img, mask))
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

    def load_task_json(self, json_path: str):
        self._flush_labels_cache()
        if hasattr(self, "_xray_dir_match_cache"):
            self._xray_dir_match_cache.clear()
        data = None
        for enc in ("utf-8-sig", "utf-8", "gbk"):
            try:
                with open(json_path, "r", encoding=enc) as f:
                    data = json.load(f)
                break
            except Exception:
                continue

        if not isinstance(data, dict) or not data:
            QMessageBox.warning(self, "错误", "任务JSON为空或格式不正确")
            return

        self._scan_token += 1
        if getattr(self, "_scan_timer", None):
            self._scan_timer.stop()
            self._scan_timer = None
        self._internal_scan_queue = None
        if getattr(self, "_scan_progress", None):
            self._scan_progress.close()
            self._scan_progress = None

        json_dir = os.path.dirname(json_path)
        base_dir = self.orig_root if self.orig_root else json_dir

        if data:
            first_rel = str(next(iter(data.keys()))).replace("\\", "/").lstrip("/")
            if not os.path.isabs(first_rel):
                old_path = os.path.join(base_dir, first_rel)
                new_path = os.path.join(json_dir, first_rel)
                if not os.path.exists(old_path) and os.path.exists(new_path):
                    base_dir = json_dir

        if not self.mask_root or self.mask_root == self.orig_root:
            self.mask_root = base_dir
        self.orig_root = base_dir

        entries = []
        missing = []
        self.task_key_map = {}

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
                if len(parts) > 1:
                    case_name = parts[0]
                else:
                    case_name = "Root"
                # [修复] 搜索已有掩码（含 NIfTI），而非硬编码 .png
                mask_path = self._resolve_ct_mask_path(
                    full_src, self.mask_root, rel_norm
                )
                filename = rel_norm
            else:
                case_name = rel_norm
                mask_path = self._resolve_xray_mask_path(full_src, rel_src=rel_norm)
                if not mask_path:
                    mask_path = self._build_default_xray_mask_path(full_src)
                filename = os.path.basename(full_src)

            has_mask = os.path.exists(mask_path)

            entry = ImageEntry(
                case_name=case_name,
                orig_path=full_src,
                mask_path=mask_path,
                filename=filename,
                has_mask=has_mask,
                has_pneumothorax=has_pneumo,
            )
            entries.append(entry)
            self.task_key_map[entry.orig_path] = rel_path

        if not entries:
            QMessageBox.warning(self, "错误", "未找到可加载的任务影像")
            return

        self.task_json_path = json_path
        self.task_entries = entries
        self.task_case_entries = {}
        self.task_case_order = []

        for entry in entries:
            if entry.case_name not in self.task_case_entries:
                self.task_case_entries[entry.case_name] = []
                self.task_case_order.append(entry.case_name)
            self.task_case_entries[entry.case_name].append(entry)

        self.task_mode = True
        self._init_labels_cache()
        self._build_task_case_lists()

        if missing:
            sample = "\n".join(missing[:8])
            QMessageBox.warning(
                self, "提示", f"以下任务路径未找到:\n{sample}\n共 {len(missing)} 条"
            )

    def _on_scan_cancelled(self):
        self._scan_token += 1
        if getattr(self, "_scan_timer", None):
            self._scan_timer.stop()
            self._scan_timer = None
        self._internal_scan_queue = None
        if getattr(self, "_scan_progress", None):
            self._scan_progress.close()
            self._scan_progress = None
        self.statusBar().showMessage("扫描已取消", 2000)

    def _build_task_case_lists(self):
        self.list_annotated.clear()
        self.list_todo.clear()
        status_map = self._load_case_status()

        for case_name in self.task_case_order:
            case_entries = self.task_case_entries.get(case_name, [])
            if not case_entries:
                continue
            has_pneumo = any(e.has_pneumothorax == 1 for e in case_entries)
            completed_flags = []
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

        if self.list_todo.count() > 0:
            self.list_todo.setCurrentRow(0)
            self.load_case_sequence(self.list_todo.currentItem())
        elif self.list_annotated.count() > 0:
            self.list_annotated.setCurrentRow(0)
            self.load_case_sequence(self.list_annotated.currentItem())

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

        self._scan_token += 1
        token = self._scan_token

        if getattr(self, "_scan_progress", None):
            self._scan_progress.close()
            self._scan_progress = None

        if getattr(self, "_scan_timer", None):
            self._scan_timer.stop()
            self._scan_timer = None

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

    def load_case_sequence(self, item):
        # [修复] 切换病例时立即推进预取 epoch，终止旧病例后台预取；同一病例内的不同预取类型互不取消。
        self._next_prefetch_epoch()

        if self.autosave_enabled and self.current_idx >= 0 and self.canvas._is_dirty:
            self.save_mask()

        if hasattr(self, "_cleanup_empty_masks"):
            self._cleanup_empty_masks()

        case_name = item.data(Qt.UserRole)
        self.current_case_name = case_name

        self.entries.clear()
        self.thumbnail_strip.clear()
        self.current_idx = -1

        if hasattr(self, "info_panel") and hasattr(self.info_panel, "table"):
            self.info_panel.table.setRowCount(0)

        files = self._build_case_entries(case_name)
        self.entries = files

        # 性能优化：切病例时保留现有缓存，只推进 epoch 终止旧预取；
        # 这样首帧命中缓存时不会被强制重新读盘。
        self._reset_cache(clear_cache=False, invalidate_prefetch=False)

        self.statusBar().showMessage(f"加载序列: {case_name} ({len(files)} 张)")

        is_ct = self.scan_mode == ScanMode.CT_SEQUENCE
        thumb_token = None

        # CT 模式：先插入占位符，首帧显示后再启动缩略图与预取，避免首屏与后台 IO 抢盘。
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
                mask_img, _ = read_mask_file(
                    entry.mask_path,
                    target_shape=(80, 80),
                    reference_image_path=entry.orig_path,
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
        key = entry.orig_path
        cached = self._cache_get(key)
        meta = None
        if cached:
            img, mask = cached[0], cached[1]
            if len(cached) >= 3:
                meta = cached[2]
        else:
            result = read_dicom_with_window(entry.orig_path)
            if result:
                img, raw, wc, ww, (min_val, max_val) = result
                meta = {"raw": raw, "wc": wc, "ww": ww, "min": min_val, "max": max_val}
            else:
                img = smart_read_image(entry.orig_path)
            if img is None:
                self.statusBar().showMessage(f"无法读取图片: {entry.filename}", 3000)
                return
            mask = None
            if os.path.exists(entry.mask_path):
                mask, _ = read_mask_file(
                    entry.mask_path,
                    target_shape=img.shape[:2],
                    reference_image_path=entry.orig_path,
                )
            if mask is None:
                mask = self._alloc_mask(img.shape[:2])
            if meta:
                self._cache_set(key, (img, mask, meta))
            else:
                self._cache_set(key, (img, mask))

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
            else:
                self.statusBar().showMessage("未选中任何病例", 1000)
                return

        item = current_list.currentItem()
        if not item:
            return

        case_name = item.data(Qt.UserRole)
        if self.task_mode:
            self._save_task_case_status(case_name, new_status)
            self._build_task_case_lists()
            msg = (
                "已归档至 [已完成]"
                if new_status == "completed"
                else "已退回至 [待标注]"
            )
            self.statusBar().showMessage(f"{msg}: {case_name}", 2000)
            return

        row = current_list.row(item)
        current_list.takeItem(row)
        target_list.addItem(item)
        target_list.setCurrentItem(item)

        self._save_single_case_status(case_name, new_status)

        msg = "已归档至 [已完成]" if new_status == "completed" else "已退回至 [待标注]"
        self.statusBar().showMessage(f"{msg}: {case_name}", 2000)

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