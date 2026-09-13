"""交互动作：保存、标记、状态更新与快捷切换。"""

import os
import queue
import shutil
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import SimpleITK as sitk
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QListWidgetItem,
    QMessageBox,
    QProgressDialog,
)

from models import ImageEntry, ScanMode
from utils import (
    imread_unicode,
    imwrite_unicode,
    imwrite_with_quality,
    read_dicom_with_window,
    read_mask_file,
    smart_read_image,
    write_mask_file,
)
from tools import mask_audit, pa_filter
from widgets import (
    ExportSettingsDialog,
    MaskAuditDialog,
    PaFilterDialog,
    PrefetchSettingsDialog,
)


class ActionsMixin:
    def _connect_canvas_signals(self):
        """在主窗口 __init__ 末尾调用一次，连接 canvas 的拖拽信号。"""
        self.canvas.file_dropped.connect(self._on_mask_file_dropped)

    def _on_mask_file_dropped(self, path: str):
        """处理从外部拖入画布的掩码文件（支持 png / nii / nii.gz）。"""
        if self.current_idx < 0 or self.canvas.base_img is None:
            QMessageBox.warning(self, "提示", "请先加载原图，再拖入掩码文件。")
            return

        entry = self.entries[self.current_idx]
        h, w = self.canvas.base_img.shape[:2]
        mask, err = read_mask_file(
            path,
            target_shape=(h, w),
            reference_image_path=entry.orig_path,
        )
        if err:
            QMessageBox.warning(self, "读取失败", err)
            return
        if mask is None:
            QMessageBox.warning(self, "读取失败", "无法解析掩码文件。")
            return

        self.canvas._push_undo()
        self.canvas.mask = mask.copy()
        self.canvas._mark_dirty()
        self.canvas.update()

        entry.has_mask = True

        # 关键：拖拽进来的 NIfTI 掩码也要记录来源，保存时才会出现 NIfTI 选项
        self._single_pair_source_mask_path = path
        self._single_pair_source_mask_is_nifti = path.lower().endswith((".nii", ".nii.gz"))

        # [修复] 同步更新 entry.mask_path，确保 Ctrl+S / 自动保存
        # 写回与拖入相同格式的文件，而非写到旧的 .png 默认路径
        entry.mask_path = path
        if hasattr(self, "_xray_dir_match_cache"):
            self._xray_dir_match_cache.clear()

        fname = os.path.basename(path)
        self.statusBar().showMessage(f"已加载掩码: {fname}", 2000)

    def open_perf_settings(self):
        from models import ScanMode

        dlg = PrefetchSettingsDialog(
            self,
            ct_prefetch_count=self.ct_prefetch_count,
            ct_cross_count=self.ct_cross_count,
            ct_cache_max=self.ct_cache_max,
            xray_prefetch_count=self.xray_prefetch_count,
            xray_cache_max=self.xray_cache_max,
            xray_default_mask_format=getattr(self, "xray_default_mask_format", "png"),
        )
        if dlg.exec() == QDialog.Accepted:
            v = dlg.get_values()
            self.ct_prefetch_count = v["ct_prefetch_count"]
            self.ct_cross_count = v["ct_cross_count"]
            self.ct_cache_max = v["ct_cache_max"]
            self.xray_prefetch_count = v["xray_prefetch_count"]
            self.xray_cache_max = v["xray_cache_max"]
            self.xray_default_mask_format = str(
                v.get("xray_default_mask_format", getattr(self, "xray_default_mask_format", "png"))
            ).strip().lower()
            if self.xray_default_mask_format not in ("png", "nii"):
                self.xray_default_mask_format = "png"

            # 当前生效的 cache_max 随模式切换
            active_max = (
                self.ct_cache_max
                if self.scan_mode == ScanMode.CT_SEQUENCE
                else self.xray_cache_max
            )
            with self._cache_lock:
                while len(self._image_cache) > active_max:
                    old_key, cached_val = self._image_cache.popitem(last=False)
                    old_img, old_mask = cached_val[0], cached_val[1]
                    self._release_cache_entry(old_key, old_img, old_mask)
            if hasattr(self, "_save_perf_settings"):
                self._save_perf_settings()

    def closeEvent(self, event):
        if self.autosave_enabled and self.current_idx >= 0 and self.canvas._is_dirty:
            self.save_mask()
        self._flush_labels_cache()
        self._cleanup_empty_masks()
        super().closeEvent(event)

    def _contains_non_ascii(self, path: str) -> bool:
        if not path:
            return False
        try:
            path.encode("ascii")
            return False
        except UnicodeEncodeError:
            return True

    def _get_ascii_temp_root(self):
        candidates = []
        if os.name == "nt":
            candidates.extend(
                [
                    r"C:\Temp",
                    r"C:\Windows\Temp",
                    os.environ.get("TEMP", ""),
                    os.environ.get("TMP", ""),
                    tempfile.gettempdir(),
                ]
            )
        else:
            candidates.extend([tempfile.gettempdir(), "/tmp", os.getcwd()])

        for candidate in candidates:
            if not candidate:
                continue
            candidate = os.path.normpath(candidate)
            if self._contains_non_ascii(candidate):
                continue
            try:
                os.makedirs(candidate, exist_ok=True)
                probe = os.path.join(candidate, f".__mask_write_probe_{os.getpid()}")
                with open(probe, "wb") as f:
                    f.write(b"1")
                os.remove(probe)
                return candidate
            except Exception:
                continue
        return None

    def _write_mask_file_compat(self, save_path, mask_to_save, reference_mask_path=None):
        lower_path = (save_path or "").lower()
        is_nifti = lower_path.endswith((".nii", ".nii.gz"))

        if not is_nifti or not self._contains_non_ascii(save_path):
            return write_mask_file(
                save_path,
                mask_to_save,
                reference_mask_path=reference_mask_path,
            )

        temp_root = self._get_ascii_temp_root()
        if not temp_root:
            return write_mask_file(
                save_path,
                mask_to_save,
                reference_mask_path=reference_mask_path,
            )

        temp_dir = os.path.join(temp_root, "xray_mask_ascii_tmp")
        try:
            os.makedirs(temp_dir, exist_ok=True)
        except Exception:
            return write_mask_file(
                save_path,
                mask_to_save,
                reference_mask_path=reference_mask_path,
            )

        suffix = ".nii.gz" if lower_path.endswith(".nii.gz") else ".nii"
        temp_path = os.path.join(
            temp_dir,
            f"mask_{os.getpid()}_{uuid.uuid4().hex}{suffix}",
        )

        ok, err = write_mask_file(
            temp_path,
            mask_to_save,
            reference_mask_path=reference_mask_path,
        )
        if not ok:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            return ok, err

        try:
            save_dir = os.path.dirname(save_path)
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
            if os.path.exists(save_path):
                os.remove(save_path)
            shutil.move(temp_path, save_path)
            return True, None
        except Exception as e:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            return False, f"NIfTI 临时写出成功，但移动到目标路径失败: {e}"

    def _split_known_image_ext(self, path: str):
        lower = (path or "").lower()
        for ext in (".nii.gz", ".nii", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"):
            if lower.endswith(ext):
                return path[: -len(ext)], ext
        return path, ""

    def _ensure_export_path_ext(self, path: str, fmt: str) -> str:
        stem, _ = self._split_known_image_ext(path)
        if fmt == "png":
            return stem + ".png"
        if fmt == "jpg":
            return stem + ".jpg"
        if fmt == "nii":
            return stem + ".nii.gz"
        return path

    def _get_export_mask_path(self, out_path: str, fmt: str) -> str:
        stem, _ = self._split_known_image_ext(out_path)
        if fmt == "nii":
            return stem + "_mask.nii.gz"
        return stem + "_mask.png"

    def _get_project_mask_format_preference(self):
        fmt = str(getattr(self, "xray_default_mask_format", "png") or "png").strip().lower()
        return "nii" if fmt in ("nii", "nii.gz", "nifti") else "png"

    def _build_single_preview_default_mask_path(self, image_path: str) -> str:
        base_dir = os.path.dirname(image_path)
        filename = os.path.basename(image_path)
        if filename.lower().endswith(".nii.gz"):
            base_name = filename[:-7]
        else:
            base_name = os.path.splitext(filename)[0]
        ext = ".nii.gz" if self._get_project_mask_format_preference() == "nii" else ".png"
        return os.path.join(base_dir, f"{base_name}_mask{ext}")

    def _get_nifti_export_reference_path(self, entry):
        ref = getattr(self, "_single_pair_source_mask_path", None)
        if ref and str(ref).lower().endswith((".nii", ".nii.gz", ".dcm", ".dicom")):
            return ref
        orig = getattr(entry, "orig_path", None)
        if orig and str(orig).lower().endswith((".nii", ".nii.gz", ".dcm", ".dicom")):
            return orig
        return None

    def _source_is_dicom_for_export(self, entry):
        orig = str(getattr(entry, "orig_path", "") or "").lower()
        return orig.endswith((".dcm", ".dicom"))

    def _mask_to_binary_uint8(self, mask, shape=None):
        if mask is None:
            if shape is None:
                return np.zeros((1, 1), dtype=np.uint8)
            return np.zeros(shape, dtype=np.uint8)

        arr = np.asarray(mask)
        if arr.size == 0:
            if shape is None:
                return np.zeros((1, 1), dtype=np.uint8)
            return np.zeros(shape, dtype=np.uint8)

        if arr.ndim == 0:
            value = 255 if arr.item() > 0 else 0
            if shape is None:
                return np.asarray([[value]], dtype=np.uint8)
            return np.full(shape, value, dtype=np.uint8)

        if arr.ndim > 2:
            arr = arr[..., 0]

        arr = (arr > 0).astype(np.uint8) * 255
        if shape is not None and arr.shape[:2] != tuple(shape):
            arr = cv2.resize(
                arr,
                (int(shape[1]), int(shape[0])),
                interpolation=cv2.INTER_NEAREST,
            )
        return np.ascontiguousarray(arr)

    def _read_reference_image_2d(self, reference_path):
        tmp_dir = None
        try:
            try:
                ref_img = sitk.ReadImage(reference_path)
            except Exception:
                if not reference_path or not os.path.exists(reference_path):
                    raise
                if not self._contains_non_ascii(reference_path):
                    raise
                tmp_dir = tempfile.mkdtemp(prefix="sitk_ascii_")
                lower = reference_path.lower()
                suffix = (
                    ".nii.gz"
                    if lower.endswith(".nii.gz")
                    else os.path.splitext(reference_path)[1] or ".nii"
                )
                tmp_path = os.path.join(tmp_dir, "ref" + suffix)
                shutil.copy2(reference_path, tmp_path)
                ref_img = sitk.ReadImage(tmp_path)

            dim = ref_img.GetDimension()
            if dim == 2:
                return ref_img, tmp_dir
            if dim == 3:
                size = list(ref_img.GetSize())
                singleton_axes = [i for i, s in enumerate(size) if s == 1]
                if len(singleton_axes) == 1:
                    axis = singleton_axes[0]
                    extract_size = list(size)
                    extract_index = [0, 0, 0]
                    extract_size[axis] = 0
                    ref_img = sitk.Extract(ref_img, extract_size, extract_index)
                    return ref_img, tmp_dir
            raise ValueError(
                f"参考图像维度不支持: dimension={dim}, size={tuple(ref_img.GetSize())}"
            )
        except Exception:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            raise

    def _write_nifti_array_compat(
        self,
        save_path,
        arr,
        reference_image_path=None,
        binary=False,
    ):
        try:
            out_arr = np.asarray(arr)
        except Exception as e:
            return False, f"导出数组无效: {e}"

        if out_arr.ndim == 3:
            if out_arr.shape[2] == 4:
                out_arr = cv2.cvtColor(out_arr, cv2.COLOR_BGRA2GRAY)
            elif out_arr.shape[2] == 3:
                out_arr = cv2.cvtColor(out_arr, cv2.COLOR_BGR2GRAY)
            else:
                out_arr = out_arr[:, :, 0]

        if out_arr.ndim != 2:
            return False, f"当前仅支持导出 2D NIfTI，实际数组形状为 {out_arr.shape}"

        out_arr = np.ascontiguousarray(out_arr)
        if binary:
            out_arr = (out_arr > 0).astype(np.uint8)
        elif out_arr.dtype == np.bool_:
            out_arr = out_arr.astype(np.uint8)
        elif not np.issubdtype(out_arr.dtype, np.number):
            out_arr = out_arr.astype(np.float32)
        else:
            out_arr = out_arr.astype(
                np.float32 if np.issubdtype(out_arr.dtype, np.floating) else out_arr.dtype,
                copy=False,
            )

        try:
            out_img = sitk.GetImageFromArray(out_arr)
        except Exception as e:
            return False, f"创建 NIfTI 图像失败: {e}"

        ref_tmp_dir = None
        if reference_image_path:
            try:
                ref_img, ref_tmp_dir = self._read_reference_image_2d(reference_image_path)
                ref_size = tuple(ref_img.GetSize())
                out_size = (out_arr.shape[1], out_arr.shape[0])  # sitk (W, H)
                if ref_size == out_size:
                    out_img.CopyInformation(ref_img)
                else:
                    # [修复] 尺寸不一致时不能用 CopyInformation（SimpleITK 会拒绝）。
                    # 以前这里静默跳过，导致写出的 NIfTI 用默认 spacing=(1,1)；
                    # 下次加载若走物理空间重采样，掩码会被放大到覆盖全图（全红）。
                    # 正确做法：手动继承 spacing / origin / direction，让下次按
                    # 物理空间解读时与参考图一致；size 差异由 target_shape 兜底对齐。
                    try:
                        out_img.SetSpacing(ref_img.GetSpacing())
                        out_img.SetOrigin(ref_img.GetOrigin())
                        out_img.SetDirection(ref_img.GetDirection())
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                if ref_tmp_dir:
                    shutil.rmtree(ref_tmp_dir, ignore_errors=True)

        if not self._contains_non_ascii(save_path):
            try:
                sitk.WriteImage(out_img, save_path)
                return True, None
            except Exception as e:
                return False, f"写入 NIfTI 失败: {e}"

        temp_root = self._get_ascii_temp_root()
        if not temp_root:
            try:
                sitk.WriteImage(out_img, save_path)
                return True, None
            except Exception as e:
                return False, f"写入 NIfTI 失败: {e}"

        temp_dir = os.path.join(temp_root, "xray_nifti_ascii_tmp")
        try:
            os.makedirs(temp_dir, exist_ok=True)
        except Exception:
            try:
                sitk.WriteImage(out_img, save_path)
                return True, None
            except Exception as e:
                return False, f"写入 NIfTI 失败: {e}"

        suffix = ".nii.gz" if str(save_path).lower().endswith(".nii.gz") else ".nii"
        temp_path = os.path.join(
            temp_dir,
            f"img_{os.getpid()}_{uuid.uuid4().hex}{suffix}",
        )

        try:
            sitk.WriteImage(out_img, temp_path)
            save_dir = os.path.dirname(save_path)
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
            if os.path.exists(save_path):
                os.remove(save_path)
            shutil.move(temp_path, save_path)
            return True, None
        except Exception as e:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            return False, f"写入 NIfTI 失败: {e}"

    def _export_image_file(self, out_path, img, quality, reference_mask_path=None):
        lower_path = (out_path or "").lower()
        if lower_path.endswith((".nii", ".nii.gz")):
            if img is None:
                return False, "导出图像为空"
            return self._write_nifti_array_compat(
                out_path,
                img,
                reference_image_path=reference_mask_path,
                binary=False,
            )

        ok = imwrite_with_quality(out_path, img, quality)
        if ok:
            return True, None
        return False, "导出图像失败"

    def _resolve_xray_save_path(self, entry):
        save_path = getattr(entry, "mask_path", "") or ""
        preferred = self._get_project_mask_format_preference()
        want_nifti = preferred == "nii"

        # 已有文件存在 → 直接用，不切换格式
        if save_path and os.path.exists(save_path):
            return save_path

        # single_pair_mode 有专用的默认路径构建
        if self.single_pair_mode:
            if not save_path:
                return self._build_single_preview_default_mask_path(entry.orig_path)
            lower = save_path.lower()
            current_is_nifti = lower.endswith((".nii", ".nii.gz"))
            if want_nifti != current_is_nifti:
                return self._build_single_preview_default_mask_path(entry.orig_path)
            return save_path

        # 通用逻辑（CT / X-ray / 双文件夹）：掩码不存在时按偏好决定扩展名
        if not save_path and hasattr(self, "_build_default_xray_mask_path"):
            rel_src = None
            if getattr(self, "orig_root", None) and getattr(entry, "orig_path", None):
                try:
                    rel_src = os.path.relpath(entry.orig_path, self.orig_root).replace("\\", "/")
                except Exception:
                    rel_src = None
            save_path = self._build_default_xray_mask_path(entry.orig_path, rel_src=rel_src)

        return save_path

    @staticmethod
    def _switch_mask_ext_to_nifti(path):
        for ext in (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"):
            if path.lower().endswith(ext):
                return path[:-len(ext)] + ".nii.gz"
        return path + ".nii.gz"

    @staticmethod
    def _switch_mask_ext_to_png(path):
        lower = path.lower()
        if lower.endswith(".nii.gz"):
            return path[:-7] + ".png"
        if lower.endswith(".nii"):
            return path[:-4] + ".png"
        return path

    # ==========================================
    # CT 与通用保存逻辑
    # ==========================================
    def save_mask(self):
        if self.current_idx < 0 or self.canvas.mask is None:
            return

        entry = self.entries[self.current_idx]
        mask_to_save = self._mask_to_binary_uint8(self.canvas.mask)

        save_path = self._resolve_xray_save_path(entry)

        # 单对模式：如果原始加载的是 NIfTI，或项目首选掩码格式就是 NIfTI，
        # 则保存时允许用户显式选择导出为 nii/nii.gz 或 png
        if self.single_pair_mode and (
            getattr(self, "_single_pair_source_mask_is_nifti", False)
            or self._get_project_mask_format_preference() == "nii"
        ):
            base_dir = os.path.dirname(entry.orig_path)
            filename = os.path.basename(entry.orig_path)

            if filename.lower().endswith(".nii.gz"):
                base_name = filename[:-7]
            else:
                base_name = os.path.splitext(filename)[0]

            default_path = os.path.join(base_dir, f"{base_name}_mask.nii.gz")

            chosen_path, selected_filter = QFileDialog.getSaveFileName(
                self,
                "导出最新掩码",
                default_path,
                "NIfTI 掩码 (*.nii.gz *.nii);;PNG 掩码 (*.png)",
            )
            if not chosen_path:
                self.statusBar().showMessage("已取消导出", 1500)
                return

            lower = chosen_path.lower()

            if "NIfTI" in selected_filter:
                if not (lower.endswith(".nii") or lower.endswith(".nii.gz")):
                    chosen_path += ".nii.gz"
            elif "PNG" in selected_filter:
                if not lower.endswith(".png"):
                    chosen_path += ".png"
            else:
                # 兜底：某些平台 selected_filter 可能为空
                lower = chosen_path.lower()
                if not (
                    lower.endswith(".nii")
                    or lower.endswith(".nii.gz")
                    or lower.endswith(".png")
                ):
                    chosen_path += ".nii.gz"

            save_path = chosen_path

        if not save_path:
            QMessageBox.warning(self, "错误", "无法保存：未分配掩码路径。")
            return

        save_dir = os.path.dirname(save_path)
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)

        # 保存为 NIfTI 时继承原始空间信息（spacing / origin / direction）
        reference_mask_path = None
        if save_path.lower().endswith((".nii", ".nii.gz")):
            reference_mask_path = self._get_nifti_export_reference_path(entry)

            if not reference_mask_path and os.path.exists(save_path):
                reference_mask_path = save_path

            # 兜底：第一次保存时用原图路径尝试继承空间信息
            if not reference_mask_path:
                reference_mask_path = entry.orig_path

        ok, err = self._write_mask_file_compat(
            save_path,
            mask_to_save,
            reference_mask_path=reference_mask_path,
        )

        # [修复] 如果因为尺寸不匹配失败（DICOM 原图被 SimpleITK 读出的尺寸
        # 可能与 pydicom/OpenCV 读出的画布尺寸不同），降级为不带空间信息保存。
        if not ok and reference_mask_path and "不一致" in (err or ""):
            ok, err = self._write_mask_file_compat(
                save_path,
                mask_to_save,
                reference_mask_path=None,
            )

        if ok:
            entry.mask_path = save_path
            entry.has_mask = True
            if hasattr(self, "_xray_dir_match_cache"):
                self._xray_dir_match_cache.clear()
            # [修复] 仅在单对/快速预览模式下更新 mask_root。
            # 批量模式的 mask_root 由 select_mask_dir / load_task_json 设定，
            # 不应被单次保存的子目录覆盖，否则后续其他病例的 p_mask 拼接会全部错误。
            if self.single_pair_mode and os.path.dirname(save_path):
                self.mask_root = os.path.dirname(save_path)

            cache_img = (
                self.canvas.base_img.copy()
                if self.canvas.base_img is not None
                else None
            )
            cache_mask = (
                self.canvas.mask.copy() if self.canvas.mask is not None else None
            )
            if cache_img is not None and cache_mask is not None:
                existing = self._cache_get(entry.orig_path)
                meta = existing[2] if (existing and len(existing) >= 3) else None
                payload = (
                    (cache_img, cache_mask, meta)
                    if meta is not None
                    else (cache_img, cache_mask)
                )
                self._cache_set(entry.orig_path, payload)

            if self.scan_mode == ScanMode.CT_SEQUENCE:
                item = self.thumbnail_strip.item(self.current_idx)
                if item:
                    pix = item.icon().pixmap(80, 80)
                    p = QPainter(pix)
                    p.setPen(QPen(Qt.green, 6))
                    p.drawRect(0, 0, 79, 79)
                    p.end()
                    item.setIcon(QIcon(pix))

            self.canvas._is_dirty = False
            self.canvas.content_modified.emit(False)
            self.statusBar().showMessage(
                f"已保存: {os.path.basename(save_path)}", 1500
            )
        else:
            QMessageBox.critical(self, "错误", err or f"保存失败: {save_path}")

    def load_single_pair(self):
        dicom_path, _ = QFileDialog.getOpenFileName(
            self, "选择DICOM文件", "", "DICOM Files (*.dcm *.dicom);;All Files (*)"
        )
        if not dicom_path:
            return
        mask_path, _ = QFileDialog.getOpenFileName(
            self, "选择标注文件", "", "Mask Files (*.png *.nii *.nii.gz);;All Files (*)"
        )
        if not mask_path:
            return
        # 修复：优先走 read_dicom_with_window 取 meta，保证窗宽窗位不丢失
        _dcm_result = read_dicom_with_window(dicom_path)
        if _dcm_result:
            img, _raw, _wc, _ww, _range = _dcm_result
            _meta = {
                "raw": _raw,
                "wc": _wc,
                "ww": _ww,
                "min": _range[0],
                "max": _range[1],
            }
        else:
            img = smart_read_image(dicom_path)
            _meta = None
        if img is None:
            QMessageBox.warning(self, "错误", "无法读取DICOM文件")
            return
        h, w = img.shape[:2]
        mask, err = read_mask_file(
            mask_path,
            target_shape=(h, w),
            reference_image_path=dicom_path,
        )
        if err:
            QMessageBox.warning(self, "错误", err)
            return
        if mask is None:
            QMessageBox.warning(self, "错误", "无法读取标注文件")
            return

        self.single_pair_mode = True
        self.task_mode = False
        self.task_json_path = ""
        self.task_entries = []
        self.task_case_entries = {}
        self.task_case_order = []
        self.task_key_map = {}
        self.orig_root = os.path.dirname(dicom_path)
        self._single_pair_source_mask_path = mask_path
        self._single_pair_source_mask_is_nifti = bool(
            mask_path and mask_path.lower().endswith((".nii", ".nii.gz"))
        )
        if not mask_path:
            self._single_pair_source_mask_path = None
            self._single_pair_source_mask_is_nifti = False
            
        case_name = os.path.basename(dicom_path)
        filename = os.path.basename(dicom_path)
        export_mask_path = mask_path
        self.mask_root = os.path.dirname(export_mask_path)

        entry = ImageEntry(
            case_name=case_name,
            orig_path=dicom_path,
            mask_path=export_mask_path,
            filename=filename,
            has_mask=True,
            has_pneumothorax=0,
        )

        self.entries = [entry]
        self.current_idx = -1
        self._reset_cache()
        # 修复：写入三元组，meta 不为 None 时窗宽窗位控件才能被激活
        _sp_payload = (img, mask, _meta) if _meta is not None else (img, mask)
        self._cache_set(entry.orig_path, _sp_payload)

        self.list_annotated.clear()
        self.list_todo.clear()
        item = QListWidgetItem(case_name)
        item.setData(Qt.UserRole, case_name)
        self.list_todo.addItem(item)
        self.list_todo.setCurrentRow(0)

        self.thumbnail_strip.clear()
        thumb_img = cv2.resize(img, (80, 80), interpolation=cv2.INTER_AREA)
        if len(thumb_img.shape) == 2:
            thumb_img = cv2.cvtColor(thumb_img, cv2.COLOR_GRAY2RGB)
        thumb_img[0:5, :] = [0, 255, 0]
        thumb_img[-5:, :] = [0, 255, 0]
        thumb_img[:, 0:5] = [0, 255, 0]
        thumb_img[:, -5:] = [0, 255, 0]
        qimg = QImage(
            thumb_img.data, 80, 80, thumb_img.strides[0], QImage.Format_RGB888
        )
        l_item = QListWidgetItem(QIcon(QPixmap.fromImage(qimg)), "")
        l_item.setToolTip(filename)
        self.thumbnail_strip.addItem(l_item)

        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(True)
        self.load_image_at_index(0)
        self.statusBar().showMessage("已加载单对图像", 2000)

    def load_quick_preview(self, image_path: str):
        if not image_path:
            return
        # 修复：优先走 read_dicom_with_window 取 meta，保证窗宽窗位不丢失
        _dcm_result = read_dicom_with_window(image_path)
        if _dcm_result:
            img, _raw, _wc, _ww, _range = _dcm_result
            _qp_meta = {
                "raw": _raw,
                "wc": _wc,
                "ww": _ww,
                "min": _range[0],
                "max": _range[1],
            }
        else:
            img = smart_read_image(image_path)
            _qp_meta = None
        if img is None:
            self.statusBar().showMessage("无法读取图像", 2000)
            return
        mask_path = None
        base_dir = os.path.dirname(image_path)
        filename = os.path.basename(image_path)
        lower = filename.lower()
        base_name = filename
        if hasattr(self, "_resolve_xray_mask_path"):
            rel_src = os.path.basename(image_path).replace("\\", "/")
            mask_path = self._resolve_xray_mask_path(image_path, rel_src=rel_src)
        if lower.endswith(".nii.gz"):
            base_name = filename[:-7]
        else:
            base_name = os.path.splitext(filename)[0]
        if not mask_path:
            for ext in (".png", ".nii", ".nii.gz"):
                candidate_mask = os.path.join(base_dir, f"{base_name}_mask{ext}")
                if os.path.exists(candidate_mask):
                    mask_path = candidate_mask
                    break
        mask = None
        if mask_path:
            h, w = img.shape[:2]
            mask, err = read_mask_file(
                mask_path,
                target_shape=(h, w),
                reference_image_path=image_path,
            )
            if err:
                mask = None
        if mask is None:
            mask = self._alloc_mask(img.shape[:2])

        self.single_pair_mode = True
        self.task_mode = False
        self.task_json_path = ""
        self.task_entries = []
        self.task_case_entries = {}
        self.task_case_order = []
        self.task_key_map = {}
        self.orig_root = base_dir
        self._single_pair_source_mask_path = mask_path
        self._single_pair_source_mask_is_nifti = bool(
            mask_path and mask_path.lower().endswith((".nii", ".nii.gz"))
        )

        export_mask_path = mask_path or self._build_single_preview_default_mask_path(image_path)
        self.mask_root = os.path.dirname(export_mask_path)

        entry = ImageEntry(
            case_name=filename,
            orig_path=image_path,
            mask_path=export_mask_path,
            filename=filename,
            has_mask=mask_path is not None,
            has_pneumothorax=0,
        )

        self.entries = [entry]
        self.current_idx = -1
        self._reset_cache()
        # 修复：写入三元组，meta 不为 None 时窗宽窗位控件才能被激活
        _qp_payload = (img, mask, _qp_meta) if _qp_meta is not None else (img, mask)
        self._cache_set(entry.orig_path, _qp_payload)

        self.list_annotated.clear()
        self.list_todo.clear()
        item = QListWidgetItem(filename)
        item.setData(Qt.UserRole, filename)
        self.list_todo.addItem(item)
        self.list_todo.setCurrentRow(0)

        self.thumbnail_strip.clear()
        thumb_img = cv2.resize(img, (80, 80), interpolation=cv2.INTER_AREA)
        if len(thumb_img.shape) == 2:
            thumb_img = cv2.cvtColor(thumb_img, cv2.COLOR_GRAY2RGB)
        thumb_img[0:5, :] = [0, 255, 0]
        thumb_img[-5:, :] = [0, 255, 0]
        thumb_img[:, 0:5] = [0, 255, 0]
        thumb_img[:, -5:] = [0, 255, 0]
        qimg = QImage(
            thumb_img.data, 80, 80, thumb_img.strides[0], QImage.Format_RGB888
        )
        l_item = QListWidgetItem(QIcon(QPixmap.fromImage(qimg)), "")
        l_item.setToolTip(filename)
        self.thumbnail_strip.addItem(l_item)

        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(True)
        self.load_image_at_index(0)
        self.statusBar().showMessage("已快速预览图像", 2000)

    def export_current(self):
        if self.current_idx < 0 or self.canvas.base_img is None:
            QMessageBox.warning(self, "提示", "没有可导出的图像")
            return

        entry = self.entries[self.current_idx]
        h, w = self.canvas.base_img.shape[:2]

        if entry.filename.lower().endswith(".nii.gz"):
            base_name = entry.filename[:-7]
        else:
            base_name = os.path.splitext(entry.filename)[0]

        export_fmt = getattr(self, "last_export_format", "png")
        export_fmt = export_fmt if export_fmt in ("png", "jpg", "nii") else "png"
        export_ext = ".nii.gz" if export_fmt == "nii" else (".jpg" if export_fmt == "jpg" else ".png")
        default_path = os.path.join(
            os.path.dirname(entry.orig_path), f"{base_name}{export_ext}"
        )

        dialog = ExportSettingsDialog(
            self, width=w, height=h, quality=95, default_path=default_path
        )

        if dialog.exec() != QDialog.Accepted:
            return

        out_w, out_h, quality, fmt, out_path, invert_export = dialog.get_values()

        if not out_path:
            QMessageBox.warning(self, "提示", "请设置导出路径")
            return

        fmt = (fmt or "png").lower()
        self.last_export_format = fmt
        out_path = self._ensure_export_path_ext(out_path, fmt)
        source_is_dicom = self._source_is_dicom_for_export(entry)

        if fmt == "nii":
            # NIfTI 导出应保持当前底层矩阵大小，不能沿用“任意缩放导出”的位图逻辑。
            img = self.canvas.base_img.copy()
            if invert_export:
                img = cv2.bitwise_not(img)

            mask = self._mask_to_binary_uint8(self.canvas.mask, shape=(h, w))
            reference_mask_path = self._get_nifti_export_reference_path(entry)
        else:
            img = cv2.resize(
                self.canvas.base_img, (out_w, out_h), interpolation=cv2.INTER_AREA
            )

            if invert_export:
                img = cv2.bitwise_not(img)

            mask = self._mask_to_binary_uint8(self.canvas.mask, shape=(h, w))
            mask = cv2.resize(mask, (out_w, out_h), interpolation=cv2.INTER_NEAREST)
            mask = self._mask_to_binary_uint8(mask, shape=(out_h, out_w))
            reference_mask_path = None

        exported_paths = []
        should_export_image = not (fmt == "nii" and source_is_dicom)

        if should_export_image:
            ok, err = self._export_image_file(
                out_path,
                img,
                quality,
                reference_mask_path=reference_mask_path,
            )
            if not ok:
                QMessageBox.warning(self, "错误", err or "导出图像失败")
                return
            exported_paths.append(os.path.basename(out_path))

        if fmt == "nii":
            mask_path = out_path if source_is_dicom else self._get_export_mask_path(out_path, fmt)
            ok, err = self._write_mask_file_compat(
                mask_path,
                mask,
                reference_mask_path=reference_mask_path,
            )
            if not ok:
                QMessageBox.warning(self, "错误", err or "导出掩码失败")
                return
            exported_paths.append(os.path.basename(mask_path))
        else:
            mask_path = self._get_export_mask_path(out_path, fmt)
            if not imwrite_unicode(mask_path, mask):
                QMessageBox.warning(self, "错误", "导出掩码失败")
                return
            exported_paths.append(os.path.basename(mask_path))

        self.statusBar().showMessage(
            "已导出: " + " / ".join(exported_paths),
            2000,
        )

    def _cleanup_empty_masks(self):
        if not self.entries:
            return
        for entry in self.entries:
            # [修复] NIfTI 掩码不参与自动清理：
            # 1) NIfTI 通常是外部工具生成的重要数据，不应被自动删除
            # 2) 保存后重新读取 NIfTI 时空间对齐可能导致误判为全黑
            if entry.mask_path.lower().endswith((".nii", ".nii.gz")):
                continue
            if os.path.exists(entry.mask_path):
                try:
                    mask, _ = read_mask_file(
                        entry.mask_path,
                        reference_image_path=entry.orig_path,
                    )
                    if mask is not None and cv2.countNonZero(mask) == 0:
                        os.remove(entry.mask_path)
                except Exception:
                    pass

    def _update_pneumo_label(self, val):
        if self.current_idx < 0:
            return
        entry = self.entries[self.current_idx]
        entry.has_pneumothorax = val

        if self.scan_mode == ScanMode.CT_SEQUENCE:
            item = self.thumbnail_strip.item(self.current_idx)
            if item:
                img = smart_read_image(entry.orig_path)
                if img is not None:
                    img = cv2.resize(img, (80, 80), interpolation=cv2.INTER_AREA)
                    if len(img.shape) == 2:
                        img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)

                    if val == 1:
                        img[0:5, :] = [0, 0, 255]
                        img[-5:, :] = [0, 0, 255]
                        img[:, 0:5] = [0, 0, 255]
                        img[:, -5:] = [0, 0, 255]
                    elif entry.has_mask:
                        img[0:5, :] = [0, 255, 0]
                        img[-5:, :] = [0, 255, 0]
                        img[:, 0:5] = [0, 255, 0]
                        img[:, -5:] = [0, 255, 0]

                    qimg = QImage(
                        img.data, 80, 80, img.strides[0], QImage.Format_RGB888
                    )
                    item.setIcon(QIcon(QPixmap.fromImage(qimg)))

        target_item = None
        for lst in [self.list_annotated, self.list_todo]:
            for i in range(lst.count()):
                it = lst.item(i)
                if it.data(Qt.UserRole) == entry.case_name:
                    target_item = it
                    break
            if target_item:
                break

        if target_item:
            txt = target_item.text()
            if val == 1:
                target_item.setForeground(QColor("#ff5555"))
                if "[!P]" not in txt:
                    target_item.setText(txt + " [!P]")
            else:
                target_item.setForeground(QColor("#e0e0e0"))
                if "[!P]" in txt:
                    target_item.setText(txt.replace(" [!P]", ""))

        rel_path = os.path.relpath(entry.orig_path, self.orig_root).replace("\\", "/")
        json_key = rel_path
        if self.task_mode:
            # [修复] task_key_map 存的是原始 JSON key，可能含反斜杠；
            # 规范化后与 _labels_cache 的 key 格式保持一致，避免插入重复 key
            raw_key = self.task_key_map.get(entry.orig_path, rel_path)
            json_key = str(raw_key).replace("\\", "/")
        if not getattr(self, "_labels_cache", None):
            self._init_labels_cache()
        self._labels_cache[json_key] = val
        self._schedule_labels_flush()

        label_text = "气胸阳性 [!P]" if val == 1 else "气胸阴性 (清除标记)"
        self.statusBar().showMessage(f"标签已更新: {label_text}", 1000)
        self._update_status_ui()

    def _update_status_ui(self):
        if self.current_idx < 0:
            return
        entry = self.entries[self.current_idx]

        text = f"FILE: {entry.filename} | DIR: {entry.case_name}"
        style = "color: #00f0ff; font-weight: bold; padding-right: 20px;"

        if entry.has_pneumothorax == 1:
            text += " | [气胸阳性]"
            style = "color: #ff5555; font-weight: bold; padding-right: 20px;"

        if self.canvas._is_dirty:
            text += " [未保存]"
            style = "color: #ffaa00; font-weight: bold; padding-right: 20px;"

        self.status_label.setText(text)
        self.status_label.setStyleSheet(style)

    # ==========================================
    # 快捷切换逻辑
    # ==========================================

    # ==========================================
    # 工具：PA 筛选 / 掩码审计
    # ==========================================
    def open_pa_filter_tool(self):
        dlg = PaFilterDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return

        vals = dlg.get_values()
        if not vals.get("source_dir"):
            QMessageBox.warning(self, "提示", "请先选择源 DICOM 目录")
            return

        source_dir = Path(vals["source_dir"]).expanduser().resolve()
        if not source_dir.exists():
            QMessageBox.warning(self, "提示", f"源目录不存在: {source_dir}")
            return

        target_dir = (
            Path(vals["target_dir"]).expanduser().resolve()
            if vals.get("target_dir")
            else None
        )
        move_dir = (
            Path(vals["move_excluded_dir"]).expanduser().resolve()
            if vals.get("move_excluded_dir")
            else None
        )

        if target_dir and target_dir == source_dir:
            QMessageBox.warning(self, "提示", "源目录与 PA 输出目录不能相同")
            return
        if move_dir and move_dir == source_dir:
            QMessageBox.warning(self, "提示", "源目录与移动目录不能相同")
            return
        if target_dir and move_dir and target_dir == move_dir:
            QMessageBox.warning(self, "提示", "PA 输出目录与移动目录不能相同")
            return

        params = {
            "source_dir": source_dir,
            "target_dir": target_dir,
            "move_excluded_dir": move_dir,
            "report": bool(vals.get("report", False)),
            "dry_run": bool(vals.get("dry_run", True)),
        }
        self._start_pa_filter_task(params)

    def open_mask_audit_tool(self):
        dlg = MaskAuditDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return

        vals = dlg.get_values()
        mode = vals.get("mode", "audit")

        if mode == "restore":
            manifest_path = vals.get("manifest_path", "").strip()
            if not manifest_path:
                QMessageBox.warning(self, "提示", "请先选择 manifest 文件")
                return
            manifest = Path(manifest_path).expanduser().resolve()
            if not manifest.exists():
                QMessageBox.warning(self, "提示", f"manifest 不存在: {manifest}")
                return
        else:
            root = vals.get("root", "").strip()
            json_path = vals.get("json_path", "").strip()
            if not root or not json_path:
                QMessageBox.warning(self, "提示", "请先选择 root 目录与 JSON 文件")
                return
            root_path = Path(root).expanduser().resolve()
            json_file = Path(json_path).expanduser().resolve()
            if not root_path.exists() or not root_path.is_dir():
                QMessageBox.warning(self, "提示", f"root 目录无效: {root_path}")
                return
            if not json_file.exists():
                QMessageBox.warning(self, "提示", f"JSON 文件不存在: {json_file}")
                return

        self._start_mask_audit_task(vals)

    # ==========================================
    # 空掩码检测：扫描内容全零的无效掩码
    # ==========================================
    def open_empty_mask_scan_tool(self):
        """扫描当前加载数据中所有 has_mask=True 的条目，检测内容全零的掩码。"""
        # 1) 收集要扫描的掩码路径（兼容任务模式 / 普通模式）
        mask_paths: list[str] = []
        seen: set[str] = set()

        def _collect(entries):
            for e in entries or []:
                p = getattr(e, "mask_path", "") or ""
                if not p or not getattr(e, "has_mask", False):
                    continue
                if p in seen:
                    continue
                if not os.path.isfile(p):
                    continue
                seen.add(p)
                mask_paths.append(p)

        if getattr(self, "task_mode", False):
            _collect(getattr(self, "task_entries", []))
        else:
            # 普通模式：遍历两个列表里所有病例，展开为 entries
            if hasattr(self, "list_todo") and hasattr(self, "list_annotated"):
                for lst in (self.list_todo, self.list_annotated):
                    for i in range(lst.count()):
                        item = lst.item(i)
                        if not item:
                            continue
                        case_name = item.data(Qt.UserRole)
                        if not case_name:
                            continue
                        try:
                            _collect(self._expand_case_to_entries(case_name))
                        except Exception:
                            pass

        if not mask_paths:
            QMessageBox.information(
                self,
                "空掩码检测",
                "未发现任何已标注为有掩码的条目。\n请先扫描目录或加载任务 JSON。",
            )
            return

        # 2) 启动后台扫描任务
        self._cancel_empty_mask_scan()
        self._empty_mask_scan_token = getattr(self, "_empty_mask_scan_token", 0) + 1
        token = self._empty_mask_scan_token
        self._empty_mask_scan_cancelled = False

        progress = QProgressDialog(
            f"正在检测空掩码 (共 {len(mask_paths)} 个)...", "取消", 0, len(mask_paths), self
        )
        progress.setWindowModality(Qt.NonModal)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        progress.show()
        self._empty_mask_scan_progress = progress
        progress.canceled.connect(lambda: self._cancel_empty_mask_scan(user_cancel=True))

        self._empty_mask_scan_queue = queue.Queue()
        self._empty_mask_scan_progress_queue = queue.Queue()

        def _progress_cb(done, total):
            try:
                self._empty_mask_scan_progress_queue.put_nowait((done, total))
            except Exception:
                pass

        def _cancel_cb():
            return getattr(self, "_empty_mask_scan_cancelled", False)

        def _worker(tk, paths, q):
            try:
                empty_list, error_list = mask_audit.detect_empty_masks(
                    paths, progress_cb=_progress_cb, cancel_cb=_cancel_cb
                )
                q.put({"ok": True, "empty": empty_list, "errors": error_list})
            except Exception as e:
                q.put({"ok": False, "error": str(e)})

        t = threading.Thread(
            target=_worker,
            args=(token, list(mask_paths), self._empty_mask_scan_queue),
            daemon=True,
        )
        self._empty_mask_scan_thread = t
        t.start()

        timer = QTimer(self)
        timer.setInterval(150)
        timer.timeout.connect(lambda: self._poll_empty_mask_scan(token))
        timer.start()
        self._empty_mask_scan_timer = timer

    def _cancel_empty_mask_scan(self, user_cancel: bool = False):
        self._empty_mask_scan_cancelled = True
        timer = getattr(self, "_empty_mask_scan_timer", None)
        if timer is not None:
            timer.stop()
            self._empty_mask_scan_timer = None
        progress = getattr(self, "_empty_mask_scan_progress", None)
        if progress is not None:
            try:
                progress.close()
            except Exception:
                pass
            self._empty_mask_scan_progress = None
        if user_cancel:
            self.statusBar().showMessage("空掩码检测已取消", 2000)

    def _poll_empty_mask_scan(self, token):
        if token != getattr(self, "_empty_mask_scan_token", -1):
            return

        # 1) 先消费进度信息
        pq = getattr(self, "_empty_mask_scan_progress_queue", None)
        if pq is not None:
            latest = None
            try:
                while True:
                    latest = pq.get_nowait()
            except queue.Empty:
                pass
            progress = getattr(self, "_empty_mask_scan_progress", None)
            if latest is not None and progress is not None:
                done, total = latest
                try:
                    if progress.maximum() != total:
                        progress.setMaximum(total)
                    progress.setValue(done)
                except Exception:
                    pass

        # 2) 看是否有最终结果
        q = getattr(self, "_empty_mask_scan_queue", None)
        if q is None:
            return
        try:
            result = q.get_nowait()
        except queue.Empty:
            return

        # 清理定时器/进度
        timer = getattr(self, "_empty_mask_scan_timer", None)
        if timer is not None:
            timer.stop()
            self._empty_mask_scan_timer = None
        progress = getattr(self, "_empty_mask_scan_progress", None)
        if progress is not None:
            try:
                progress.close()
            except Exception:
                pass
            self._empty_mask_scan_progress = None

        if not result.get("ok"):
            QMessageBox.warning(
                self, "空掩码检测", f"扫描失败: {result.get('error', '未知错误')}"
            )
            return

        empty_list = result.get("empty", [])
        error_list = result.get("errors", [])
        self._show_empty_mask_result_dialog(empty_list, error_list)

    def _show_empty_mask_result_dialog(self, empty_list, error_list):
        """展示空掩码结果，并允许选择性删除。"""
        if not empty_list and not error_list:
            QMessageBox.information(self, "空掩码检测", "未发现空掩码或读取错误。")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(
            f"空掩码检测结果 - 空掩码 {len(empty_list)} 个，读取错误 {len(error_list)} 个"
        )
        dlg.resize(760, 520)

        from PySide6.QtWidgets import (
            QVBoxLayout,
            QHBoxLayout,
            QLabel,
            QListWidget,
            QListWidgetItem as _LI,
            QPushButton,
            QCheckBox,
        )

        layout = QVBoxLayout(dlg)

        info = QLabel(
            f"共检测到 <b>{len(empty_list)}</b> 个内容全零的掩码文件。"
            + (f"<br>另有 {len(error_list)} 个读取错误（不可删除，仅展示）。" if error_list else "")
        )
        info.setTextFormat(Qt.RichText)
        layout.addWidget(info)

        list_widget = QListWidget(dlg)
        list_widget.setSelectionMode(QListWidget.ExtendedSelection)

        for item_info in empty_list:
            p = item_info.get("path", "")
            sz = item_info.get("size_bytes", 0)
            li = _LI(f"[空] {p}    ({sz} bytes)")
            li.setData(Qt.UserRole, {"kind": "empty", "path": p})
            li.setFlags(li.flags() | Qt.ItemIsUserCheckable)
            li.setCheckState(Qt.Checked)
            list_widget.addItem(li)

        for item_info in error_list:
            p = item_info.get("path", "")
            err = item_info.get("error", "")
            li = _LI(f"[错误] {p}  —  {err}")
            li.setData(Qt.UserRole, {"kind": "error", "path": p})
            # 错误项不可勾选删除（红字提示）
            li.setFlags((li.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsUserCheckable)
            li.setForeground(QColor("#ff5555"))
            list_widget.addItem(li)

        layout.addWidget(list_widget)

        select_bar = QHBoxLayout()
        btn_select_all = QPushButton("全选空掩码")
        btn_select_none = QPushButton("全不选")
        select_bar.addWidget(btn_select_all)
        select_bar.addWidget(btn_select_none)
        select_bar.addStretch(1)
        layout.addLayout(select_bar)

        def _toggle_all(state):
            for i in range(list_widget.count()):
                it = list_widget.item(i)
                meta = it.data(Qt.UserRole) or {}
                if meta.get("kind") != "empty":
                    continue
                it.setCheckState(state)

        btn_select_all.clicked.connect(lambda: _toggle_all(Qt.Checked))
        btn_select_none.clicked.connect(lambda: _toggle_all(Qt.Unchecked))

        btn_bar = QHBoxLayout()
        btn_delete = QPushButton("删除选中空掩码")
        btn_close = QPushButton("关闭")
        btn_bar.addStretch(1)
        btn_bar.addWidget(btn_delete)
        btn_bar.addWidget(btn_close)
        layout.addLayout(btn_bar)

        def _do_delete():
            targets = []
            for i in range(list_widget.count()):
                it = list_widget.item(i)
                meta = it.data(Qt.UserRole) or {}
                if meta.get("kind") != "empty":
                    continue
                if it.checkState() != Qt.Checked:
                    continue
                targets.append(meta.get("path", ""))

            targets = [p for p in targets if p]
            if not targets:
                QMessageBox.information(dlg, "提示", "未勾选任何空掩码。")
                return

            reply = QMessageBox.question(
                dlg,
                "确认删除",
                f"确定要删除 {len(targets)} 个空掩码文件吗？此操作不可恢复。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

            deleted = 0
            failed = []
            for p in targets:
                try:
                    if os.path.isfile(p):
                        os.remove(p)
                        deleted += 1
                except Exception as e:
                    failed.append((p, str(e)))

            # 同步内存中 entry.has_mask / mask 缓存 / 目录匹配缓存
            self._mark_masks_deleted(set(targets))

            msg = f"已删除 {deleted} 个空掩码。"
            if failed:
                sample = "\n".join([f"{p}: {err}" for p, err in failed[:5]])
                msg += f"\n{len(failed)} 个失败:\n{sample}"
            QMessageBox.information(dlg, "完成", msg)
            dlg.accept()

        btn_delete.clicked.connect(_do_delete)
        btn_close.clicked.connect(dlg.reject)

        dlg.exec()

    def _mark_masks_deleted(self, deleted_paths: set):
        """删除空掩码后同步内存状态：entry.has_mask / 缓存 / 当前视图。"""
        if not deleted_paths:
            return

        def _patch_entries(entries):
            for e in entries or []:
                mp = getattr(e, "mask_path", "") or ""
                if mp in deleted_paths:
                    e.has_mask = False

        if getattr(self, "task_mode", False):
            _patch_entries(getattr(self, "task_entries", []))
            for case_name, case_entries in getattr(self, "task_case_entries", {}).items():
                _patch_entries(case_entries)

        _patch_entries(getattr(self, "entries", []))

        # 清理目录匹配缓存（X 光模式按目录缓存了掩码映射）
        if hasattr(self, "_xray_dir_match_cache"):
            try:
                self._xray_dir_match_cache.clear()
            except Exception:
                pass

        # 清理已加载的影像缓存中涉及到这些掩码的条目
        try:
            with self._cache_lock:
                for key in list(self._image_cache.keys()):
                    # 这里 key 是 orig_path，查不到掩码路径，保守做法是清空缓存
                    pass
        except Exception:
            pass

        # 若当前加载的 entry 的掩码被删，刷新画布以反映状态
        try:
            if 0 <= self.current_idx < len(self.entries):
                cur_entry = self.entries[self.current_idx]
                if getattr(cur_entry, "mask_path", "") in deleted_paths:
                    self.load_image_at_index(self.current_idx, start_background=False)
        except Exception:
            pass

        if hasattr(self, "_update_status_ui"):
            try:
                self._update_status_ui()
            except Exception:
                pass

    def _start_pa_filter_task(self, params):
        self._cancel_pa_filter_task()
        self._pa_filter_token = getattr(self, "_pa_filter_token", 0) + 1
        token = self._pa_filter_token

        progress = QProgressDialog("正在筛选 PA 位...", "取消", 0, 0, self)
        progress.setWindowModality(Qt.NonModal)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()
        self._pa_filter_progress = progress
        progress.canceled.connect(lambda: self._cancel_pa_filter_task(user_cancel=True))

        self._pa_filter_queue = queue.Queue()
        t = threading.Thread(
            target=self._pa_filter_worker,
            args=(token, params, self._pa_filter_queue),
            daemon=True,
        )
        self._pa_filter_thread = t
        t.start()

        timer = QTimer(self)
        timer.setInterval(200)
        timer.timeout.connect(lambda: self._poll_pa_filter_result(token))
        timer.start()
        self._pa_filter_timer = timer

    def _pa_filter_worker(self, token, params, result_queue):
        try:
            source_dir = params["source_dir"]
            target_dir = params.get("target_dir")
            move_dir = params.get("move_excluded_dir")
            report = params.get("report", False)
            dry_run = params.get("dry_run", True)

            dicom_files = pa_filter.scan_dicom_files(source_dir)
            if not dicom_files:
                result_queue.put({"ok": False, "message": "未找到任何 DICOM 文件"})
                return

            pa_files, all_files_info = pa_filter.filter_pa_views(dicom_files)
            pa_set = set(pa_files)
            excluded_files = [f for f, _ in all_files_info if f not in pa_set]

            report_path = None
            if report:
                report_dir = target_dir or move_dir or source_dir
                report_dir.mkdir(parents=True, exist_ok=True)
                report_path = report_dir / "pa_filter_report.txt"
                pa_filter.generate_report(
                    all_files_info, pa_files, report_path, source_dir
                )

            if not dry_run:
                if target_dir and pa_files:
                    pa_filter.copy_pa_files(pa_files, source_dir, target_dir)
                if move_dir and excluded_files:
                    pa_filter.move_files_preserving_structure(
                        excluded_files, source_dir, move_dir
                    )

            result_queue.put(
                {
                    "ok": True,
                    "total": len(all_files_info),
                    "pa_count": len(pa_files),
                    "excluded_count": len(excluded_files),
                    "report_path": str(report_path) if report_path else "",
                    "copied": bool(target_dir and not dry_run),
                    "moved": bool(move_dir and not dry_run),
                }
            )
        except Exception as e:
            result_queue.put({"ok": False, "message": str(e)})

    def _poll_pa_filter_result(self, token):
        if token != getattr(self, "_pa_filter_token", None):
            return
        q = getattr(self, "_pa_filter_queue", None)
        if not q:
            return
        try:
            result = q.get_nowait()
        except queue.Empty:
            return

        if getattr(self, "_pa_filter_timer", None):
            self._pa_filter_timer.stop()
            self._pa_filter_timer = None
        if getattr(self, "_pa_filter_progress", None):
            self._pa_filter_progress.close()
            self._pa_filter_progress = None
        self._pa_filter_queue = None

        if not result.get("ok"):
            QMessageBox.warning(self, "PA 筛选失败", result.get("message", "未知错误"))
            return

        msg = [
            f"总文件数: {result.get('total', 0)}",
            f"PA 位文件数: {result.get('pa_count', 0)}",
            f"其他体位文件数: {result.get('excluded_count', 0)}",
        ]
        if result.get("report_path"):
            msg.append(f"报告路径: {result['report_path']}")
        if result.get("copied"):
            msg.append("已执行 PA 文件复制")
        if result.get("moved"):
            msg.append("已执行非 PA 文件移动")

        QMessageBox.information(self, "PA 筛选完成", "\n".join(msg))

    def _cancel_pa_filter_task(self, user_cancel: bool = False):
        self._pa_filter_token = getattr(self, "_pa_filter_token", 0) + 1
        if getattr(self, "_pa_filter_timer", None):
            self._pa_filter_timer.stop()
            self._pa_filter_timer = None
        if getattr(self, "_pa_filter_progress", None):
            self._pa_filter_progress.close()
            self._pa_filter_progress = None
        self._pa_filter_queue = None
        if user_cancel:
            self.statusBar().showMessage("PA 筛选已取消", 2000)

    def _start_mask_audit_task(self, params):
        self._cancel_mask_audit_task()
        self._mask_audit_token = getattr(self, "_mask_audit_token", 0) + 1
        token = self._mask_audit_token

        progress = QProgressDialog("正在执行掩码/JSON 审计...", "取消", 0, 0, self)
        progress.setWindowModality(Qt.NonModal)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()
        self._mask_audit_progress = progress
        progress.canceled.connect(lambda: self._cancel_mask_audit_task(user_cancel=True))

        self._mask_audit_queue = queue.Queue()
        t = threading.Thread(
            target=self._mask_audit_worker,
            args=(token, params, self._mask_audit_queue),
            daemon=True,
        )
        self._mask_audit_thread = t
        t.start()

        timer = QTimer(self)
        timer.setInterval(200)
        timer.timeout.connect(lambda: self._poll_mask_audit_result(token))
        timer.start()
        self._mask_audit_timer = timer

    def _mask_audit_worker(self, token, params, result_queue):
        try:
            mode = params.get("mode", "audit")
            if mode == "restore":
                manifest = Path(params.get("manifest_path", "")).expanduser().resolve()
                restored, items, errors = mask_audit.restore_from_manifest(
                    manifest,
                    overwrite=bool(params.get("overwrite", False)),
                )
                result_queue.put(
                    {
                        "ok": True,
                        "mode": "restore",
                        "restored": restored,
                        "errors": errors,
                    }
                )
                return

            root = Path(params.get("root", "")).expanduser().resolve()
            json_path = Path(params.get("json_path", "")).expanduser().resolve()
            report_out = params.get("report_out", "").strip()
            report_path = (
                Path(report_out).expanduser().resolve()
                if report_out
                else root / "mask_audit_report.json"
            )
            quarantine_mode = params.get("quarantine_mode", "none")
            quarantine_dir = params.get("quarantine_dir", "").strip()
            quarantine_path = (
                Path(quarantine_dir).expanduser().resolve()
                if quarantine_dir
                else root / "mask_quarantine"
            )

            mapping = mask_audit.load_json_mapping(json_path)
            report = mask_audit.audit_masks(root, mapping)
            mask_audit.save_json(report, report_path)

            corrected_path = ""
            corrected_stats = None
            if params.get("write_corrected"):
                out_path = params.get("corrected_path", "").strip()
                if not out_path:
                    out_path = str(root / "labels_corrected.json")
                corrected_path = str(Path(out_path).expanduser().resolve())
                corrected_mapping, corrected_stats = mask_audit.build_corrected_mapping(
                    original_mapping=mapping,
                    report=report,
                    sync_both_ways=bool(params.get("sync_both_ways", False)),
                )
                mask_audit.save_corrected_mapping(
                    corrected_mapping, Path(corrected_path)
                )

            manifest_path = ""
            manifest_errors = []
            if quarantine_mode in ("copy", "move"):
                manifest, manifest_errors = mask_audit.quarantine_wrong_zero_masks(
                    report,
                    root,
                    quarantine_path,
                    mode=quarantine_mode,
                )
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                manifest_path = str(
                    (quarantine_path / f"manifest_{ts}.json").resolve()
                )
                mask_audit.save_json(manifest, Path(manifest_path))

            result_queue.put(
                {
                    "ok": True,
                    "mode": "audit",
                    "summary": report.get("summary", {}),
                    "report_path": str(report_path),
                    "corrected_path": corrected_path,
                    "corrected_stats": corrected_stats or {},
                    "manifest_path": manifest_path,
                    "manifest_errors": manifest_errors,
                }
            )
        except Exception as e:
            result_queue.put({"ok": False, "message": str(e)})

    def _poll_mask_audit_result(self, token):
        if token != getattr(self, "_mask_audit_token", None):
            return
        q = getattr(self, "_mask_audit_queue", None)
        if not q:
            return
        try:
            result = q.get_nowait()
        except queue.Empty:
            return

        if getattr(self, "_mask_audit_timer", None):
            self._mask_audit_timer.stop()
            self._mask_audit_timer = None
        if getattr(self, "_mask_audit_progress", None):
            self._mask_audit_progress.close()
            self._mask_audit_progress = None
        self._mask_audit_queue = None

        if not result.get("ok"):
            QMessageBox.warning(
                self, "掩码/JSON 审计失败", result.get("message", "未知错误")
            )
            return

        if result.get("mode") == "restore":
            errors = result.get("errors") or []
            msg = [f"成功恢复: {result.get('restored', 0)}"]
            if errors:
                msg.append(f"恢复错误: {len(errors)} 条")
            QMessageBox.information(self, "恢复完成", "\n".join(msg))
            return

        summary = result.get("summary", {})
        msg = [
            f"总例数: {summary.get('total_cases', 0)}",
            f"标记 1 的例数: {summary.get('label_1_cases', 0)}",
            f"标记 0 的例数: {summary.get('label_0_cases', 0)}",
            f"实际有掩码: {summary.get('actual_has_mask_cases', 0)}",
            f"1 且有掩码: {summary.get('label_1_and_found_mask', 0)}",
            f"1 但无掩码: {summary.get('label_1_but_missing_mask', 0)}",
            f"0 但有掩码: {summary.get('label_0_but_found_mask', 0)}",
            f"0 且无掩码: {summary.get('label_0_and_no_mask', 0)}",
            f"报告路径: {result.get('report_path', '')}",
        ]

        if result.get("corrected_path"):
            msg.append(f"纠正 JSON: {result.get('corrected_path')}")
        if result.get("manifest_path"):
            msg.append(f"manifest: {result.get('manifest_path')}")
        if result.get("manifest_errors"):
            msg.append(f"隔离错误: {len(result.get('manifest_errors'))} 条")

        QMessageBox.information(self, "审计完成", "\n".join(msg))

    def _cancel_mask_audit_task(self, user_cancel: bool = False):
        self._mask_audit_token = getattr(self, "_mask_audit_token", 0) + 1
        if getattr(self, "_mask_audit_timer", None):
            self._mask_audit_timer.stop()
            self._mask_audit_timer = None
        if getattr(self, "_mask_audit_progress", None):
            self._mask_audit_progress.close()
            self._mask_audit_progress = None
        self._mask_audit_queue = None
        if user_cancel:
            self.statusBar().showMessage("掩码/JSON 审计已取消", 2000)

    def prev_image(self):
        if self.current_idx > 0:
            self.load_image_at_index(self.current_idx - 1)

    def next_image(self):
        if self.current_idx < len(self.entries) - 1:
            self.load_image_at_index(self.current_idx + 1)

    def prev_case(self):
        # 适用于左侧列表切换 (CT与X光多序列)
        current_list = (
            self.list_annotated if self.list_annotated.hasFocus() else self.list_todo
        )
        if not current_list.hasFocus():
            current_list = self.list_todo

        row = current_list.currentRow()
        if row > 0:
            current_list.setCurrentRow(row - 1)
            # 调用定义在 data_mixin.py 中的序列加载功能
            self.load_case_sequence(current_list.currentItem())

    def next_case(self):
        # 适用于左侧列表切换 (CT与X光多序列)
        current_list = (
            self.list_annotated if self.list_annotated.hasFocus() else self.list_todo
        )
        if not current_list.hasFocus():
            current_list = self.list_todo

        row = current_list.currentRow()
        if row < current_list.count() - 1:
            current_list.setCurrentRow(row + 1)
            # 调用定义在 data_mixin.py 中的序列加载功能
            self.load_case_sequence(current_list.currentItem())

    # ==========================================
    # 占位符 (防止 ui_mixin.py 中的快捷键调用崩溃)
    # ==========================================
    def action_toggle_case_status(self):
        """防止快捷键 Z 崩溃，可根据需要在此添加状态切换逻辑"""
        pass