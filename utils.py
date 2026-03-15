"""工具函数：图像读取、DICOM 元数据与样式主题等通用能力。"""

import json
import os
import re
import SimpleITK as sitk
import cv2
import numpy as np
import pydicom
from PySide6.QtWidgets import QApplication
import shutil
import tempfile
from pathlib import Path

from constants import (
    JPEG_EXTENSIONS,
    MASK_IMAGE_EXTENSIONS,
    NIFTI_EXTENSIONS,
    PNG_COMPRESSION_MAX,
    QUALITY_MAX,
    QUALITY_MIN,
)

def smart_read_image(path: str) -> np.ndarray | None:
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext in MASK_IMAGE_EXTENSIONS:
            return imread_unicode(path)
        result = read_dicom_with_window(path)
        if result:
            img, _, _, _, _ = result
            return img
        return imread_unicode(path)
    except Exception:
        return imread_unicode(path)


def read_dicom_with_window(path: str):
    try:
        ds = pydicom.dcmread(path, force=True)
        if not hasattr(ds, "pixel_array"):
            return None
        data = ds.pixel_array.astype(np.float32)
        slope = float(ds.get("RescaleSlope", 1.0))
        intercept = float(ds.get("RescaleIntercept", 0.0))
        data = data * slope + intercept

        wc = ds.get("WindowCenter", None)
        ww = ds.get("WindowWidth", None)
        if isinstance(wc, (list, tuple)):
            wc = wc[0] if wc else None
        if isinstance(ww, (list, tuple)):
            ww = ww[0] if ww else None
        if wc is not None:
            wc = float(wc)
        if ww is not None:
            ww = float(ww)

        if wc is not None and ww is not None and ww > 1:
            lower = wc - 0.5 - (ww - 1) / 2
            upper = wc - 0.5 + (ww - 1) / 2
            display = np.clip(data, lower, upper)
            display = (display - lower) / (upper - lower) * 255.0
            img_gray = display.astype(np.uint8)
        else:
            min_val = float(np.min(data))
            max_val = float(np.max(data))
            if max_val == min_val:
                img_gray = np.zeros_like(data, dtype=np.uint8)
            else:
                norm = (data - min_val) / (max_val - min_val) * 255.0
                img_gray = norm.astype(np.uint8)

        img_bgr = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
        min_val = float(np.min(data))
        max_val = float(np.max(data))
        return img_bgr, data, wc, ww, (min_val, max_val)
    except Exception:
        return None


def get_dicom_metadata(path: str) -> dict:
    info = {}
    try:
        ds = pydicom.dcmread(path, stop_before_pixels=True, force=True)

        def get_val(tag, default="N/A"):
            return str(ds.get(tag, default))

        info["Patient ID"] = get_val("PatientID")
        info["Patient Name"] = get_val("PatientName")
        info["Study Date"] = get_val("StudyDate")
        info["Modality"] = get_val("Modality")
        info["Instance"] = get_val("InstanceNumber", "-")
    except Exception:
        info["Status"] = "Not DICOM"
    return info


def imread_unicode(path: str, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, flags)
    except Exception:
        return None


def imwrite_unicode(path: str, img: np.ndarray) -> bool:
    try:
        ext = os.path.splitext(path)[1]
        if not ext:
            ext = ".png"
        ok, buf = cv2.imencode(ext, img)
        if not ok:
            return False
        buf.tofile(path)
        return True
    except Exception:
        return False


def imwrite_with_quality(path: str, img: np.ndarray, quality: int) -> bool:
    try:
        ext = os.path.splitext(path)[1].lower()
        if not ext:
            ext = ".png"
        params = []
        if ext in JPEG_EXTENSIONS:
            q = int(max(QUALITY_MIN, min(QUALITY_MAX, quality)))
            params = [cv2.IMWRITE_JPEG_QUALITY, q]
        elif ext == ".png":
            q = int(max(QUALITY_MIN, min(QUALITY_MAX, quality)))
            compression = int(round((100 - q) / 100 * 9))
            compression = max(0, min(9, compression))
            params = [cv2.IMWRITE_PNG_COMPRESSION, compression]
        ok, buf = cv2.imencode(ext, img, params)
        if not ok:
            return False
        buf.tofile(path)
        return True
    except Exception:
        return False




def _resize_mask_if_needed(mask: np.ndarray, target_shape: tuple[int, int] | None):
    if target_shape is None:
        return mask
    target_h, target_w = int(target_shape[0]), int(target_shape[1])
    if target_h <= 0 or target_w <= 0:
        return mask
    if mask.shape[:2] == (target_h, target_w):
        return mask
    return cv2.resize(mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)


def _sitk_force_2d(img: sitk.Image, name: str) -> sitk.Image:
    dim = img.GetDimension()
    if dim == 2:
        return img

    # 允许单层 3D（例如 size=(W,H,1) 或某一轴为 1），压成 2D
    if dim == 3:
        size = list(img.GetSize())
        singleton_axes = [i for i, s in enumerate(size) if s == 1]
        if len(singleton_axes) == 1:
            axis = singleton_axes[0]
            extract_size = list(size)
            extract_index = [0, 0, 0]
            extract_size[axis] = 0
            return sitk.Extract(img, extract_size, extract_index)

    raise ValueError(
        f"{name}维度不支持：dimension={dim}, size={tuple(img.GetSize())}。"
        "当前仅支持 2D 或单层 3D 图像。"
    )

def _has_non_ascii(s: str) -> bool:
    try:
        s.encode("ascii")
        return False
    except UnicodeEncodeError:
        return True
    
def _safe_sitk_read_image(path: str):
    """
    先直接读；如果失败且路径包含非 ASCII 字符，
    则复制到临时英文路径后再读。
    返回: (image, temp_dir_to_cleanup or None)
    """
    try:
        img = sitk.ReadImage(path)
        return img, None
    except Exception as e:
        if not os.path.exists(path):
            raise FileNotFoundError(f"文件不存在: {path}") from e

        # 只有路径含非 ASCII 时才走兜底复制
        if not _has_non_ascii(path):
            raise

        temp_dir = tempfile.mkdtemp(prefix="sitk_ascii_")
        src = Path(path)

        # 保留后缀，特别处理 .nii.gz
        if src.name.lower().endswith(".nii.gz"):
            dst_name = "temp_mask.nii.gz"
        else:
            dst_name = f"temp{src.suffix}"

        dst = os.path.join(temp_dir, dst_name)
        shutil.copy2(path, dst)

        img = sitk.ReadImage(dst)
        return img, temp_dir
    
def _safe_sitk_write_image(img: sitk.Image, target_path: str) -> tuple[bool, str | None]:
    """
    先尝试直接写。
    如果失败，且目标路径包含非 ASCII 字符，则先写到纯英文临时路径，
    再用 Python 复制到最终目标路径。
    """
    try:
        sitk.WriteImage(img, target_path)
        return True, None
    except Exception as e:
        # 目标目录不存在时先明确报错
        target_dir = os.path.dirname(target_path)
        if target_dir and not os.path.exists(target_dir):
            return False, f"目标目录不存在: {target_dir}"

        # 仅当路径包含非 ASCII 时，走临时英文路径兜底
        if not _has_non_ascii(target_path):
            return False, f"写入 NIfTI 失败: {e}"

        temp_dir = tempfile.mkdtemp(prefix="sitk_write_ascii_")
        try:
            lower = target_path.lower()
            if lower.endswith(".nii.gz"):
                temp_name = "temp_mask.nii.gz"
            elif lower.endswith(".nii"):
                temp_name = "temp_mask.nii"
            else:
                temp_name = "temp_mask.nii.gz"

            temp_path = os.path.join(temp_dir, temp_name)

            # 让 SimpleITK 只写英文路径
            sitk.WriteImage(img, temp_path)

            # 再由 Python 复制到最终中文路径
            shutil.copyfile(temp_path, target_path)
            return True, None

        except Exception as e2:
            return False, f"写入 NIfTI 失败: {e2}"

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            
def _read_nifti_mask_aligned(
    path: str,
    target_shape: tuple[int, int] | None = None,
    reference_image_path: str | None = None,
) -> tuple[np.ndarray | None, str | None]:
    temp_dirs: list[str] = []

    try:
        # 1) 安全读取 NIfTI（兼容中文路径兜底）
        mask_img, tmp1 = _safe_sitk_read_image(path)
        if tmp1:
            temp_dirs.append(tmp1)

        try:
            mask_img = _sitk_force_2d(mask_img, "NIfTI 掩码")
        except Exception as e:
            return None, str(e)

        # 2) 掩码先二值化，避免标签插值污染
        mask_img = sitk.Cast(mask_img > 0, sitk.sitkUInt8)

        # 3) 如果提供参考图像，则按参考图像空间重采样
        if reference_image_path:
            try:
                ref_img, tmp2 = _safe_sitk_read_image(reference_image_path)
                if tmp2:
                    temp_dirs.append(tmp2)

                ref_img = _sitk_force_2d(ref_img, "参考图像")
            except Exception as e:
                return None, f"读取参考图像失败: {e}"

            if mask_img.GetDimension() != ref_img.GetDimension():
                return (
                    None,
                    f"掩码维度({mask_img.GetDimension()})与参考图像维度({ref_img.GetDimension()})不一致",
                )

            try:
                mask_img = sitk.Resample(
                    mask_img,
                    ref_img,
                    sitk.Transform(),
                    sitk.sitkNearestNeighbor,
                    0,
                    sitk.sitkUInt8,
                )
            except Exception as e:
                return None, f"NIfTI 掩码重采样失败: {e}"

        # 4) 转回 numpy
        try:
            arr = sitk.GetArrayFromImage(mask_img)
            arr = np.squeeze(np.asarray(arr))
        except Exception as e:
            return None, f"NIfTI 转数组失败: {e}"

        if arr.ndim != 2:
            return None, f"当前仅支持 2D 掩码，实际数组形状为 {arr.shape}"

        mask = (arr > 0).astype(np.uint8) * 255
        mask = _resize_mask_if_needed(mask, target_shape)
        return np.ascontiguousarray(mask), None

    except Exception as e:
        return None, f"读取 NIfTI 失败: {e}"

    finally:
        for d in temp_dirs:
            try:
                shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass



def read_mask_file(
    path: str,
    target_shape: tuple[int, int] | None = None,
    reference_image_path: str | None = None,
) -> tuple[np.ndarray | None, str | None]:
    ext = path.lower()

    if ext.endswith(MASK_IMAGE_EXTENSIONS):
        mask = imread_unicode(path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            return None, "读取掩码失败"
        mask = (np.asarray(mask) > 0).astype(np.uint8) * 255
        mask = _resize_mask_if_needed(mask, target_shape)
        return np.ascontiguousarray(mask), None

    if ext.endswith(NIFTI_EXTENSIONS):
        return _read_nifti_mask_aligned(
            path,
            target_shape=target_shape,
            reference_image_path=reference_image_path,
        )

    return None, "不支持的掩码格式"


def binarize_mask(mask: np.ndarray, threshold: int | float) -> np.ndarray:
    return (np.asarray(mask) >= threshold).astype(np.uint8) * 255


def natural_sort_key(s: str):
    return [
        int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)
    ]


def apply_tech_theme(app: QApplication):
    """深色科技主题"""
    bg_color = "#1e1e2e"
    panel_color = "#252535"
    text_color = "#e0e0e0"
    accent_color = "#00f0ff"
    border_color = "#3e3e4e"

    _apply_theme_qss(app, bg_color, panel_color, text_color, accent_color, border_color)


def apply_light_theme(app: QApplication):
    """浅色护眼主题"""
    bg_color = "#f0f2f5"
    panel_color = "#ffffff"
    text_color = "#333333"  # 深色文字
    accent_color = "#0078d7"  # 科技蓝
    border_color = "#d1d5db"

    _apply_theme_qss(app, bg_color, panel_color, text_color, accent_color, border_color)


def _apply_theme_qss(
    app: QApplication, bg_color, panel_color, text_color, accent_color, border_color
):
    """通用的 QSS 注入逻辑"""
    # 动态计算悬浮态颜色（简单处理：使用带有透明度的强调色）
    hover_color = (
        "rgba(0, 120, 215, 30)" if text_color == "#333333" else "rgba(0, 240, 255, 30)"
    )
    checked_color = (
        "rgba(0, 120, 215, 60)" if text_color == "#333333" else "rgba(0, 240, 255, 60)"
    )

    style_sheet = f"""
    QMainWindow {{ background-color: {bg_color}; }}
    QWidget {{ color: {text_color}; font-family: "Microsoft YaHei UI", "Segoe UI", "SimHei"; font-size: 10pt; }}

    /* --- 新增：菜单栏与下拉菜单的颜色适配 --- */
    QMenuBar {{ background-color: {panel_color}; color: {text_color}; }}
    QMenuBar::item {{ background-color: transparent; color: {text_color}; padding: 4px 10px; }}
    QMenuBar::item:selected {{ background-color: {accent_color}; color: #ffffff; }}

    QMenu {{ background-color: {panel_color}; color: {text_color}; border: 1px solid {border_color}; }}
    QMenu::item {{ padding: 6px 20px; }}
    QMenu::item:selected {{ background-color: {accent_color}; color: #ffffff; }}
    /* ---------------------------------------- */

    QToolBar {{ background-color: {panel_color}; border-bottom: 2px solid {accent_color}; spacing: 8px; padding: 4px; }}
    QToolButton {{ background-color: transparent; border: 1px solid transparent; border-radius: 4px; padding: 4px; color: {text_color}; }}
    QToolButton:hover {{ background-color: {hover_color}; border: 1px solid {accent_color}; }}
    QToolButton:checked {{ background-color: {checked_color}; border: 1px solid {accent_color}; color: #fff; }}

    QDockWidget::title {{ background: {panel_color}; padding: 6px; border-left: 4px solid {accent_color}; font-weight: bold; }}

    QListWidget {{ background-color: {panel_color}; border: 1px solid {border_color}; border-radius: 4px; outline: none; }}
    QListWidget::item {{ padding: 4px; }}
    QListWidget::item:selected {{ background-color: {checked_color}; border: 1px solid {accent_color}; color: {text_color}; font-weight: bold; }}

    QListWidget#ThumbnailStrip {{ background-color: {bg_color}; border-top: 2px solid {accent_color}; padding: 5px; }}
    QListWidget#ThumbnailStrip::item {{ border: 1px solid {border_color}; margin-right: 2px; background-color: {panel_color}; }}
    QListWidget#ThumbnailStrip::item:selected {{ border: 2px solid {accent_color}; background-color: {checked_color}; }}

    QSlider::groove:horizontal {{ border: 1px solid {border_color}; height: 4px; background: {bg_color}; margin: 2px 0; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {accent_color}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}

    QComboBox {{
        background-color: {panel_color};
        border: 1px solid {border_color};
        border-radius: 4px;
        padding: 4px 10px;
        color: {accent_color};
        font-weight: bold;
    }}
    QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 20px; border-left-width: 0px; }}
    QComboBox QAbstractItemView {{ background-color: {panel_color}; selection-background-color: {accent_color}; selection-color: #ffffff; color: {text_color}; }}

    QSpinBox {{ background-color: {panel_color}; color: {text_color}; border: 1px solid {border_color}; border-radius: 3px; padding: 3px; }}
    QLabel#ToolLabel {{ color: {accent_color}; font-weight: bold; }}
    QSplitter::handle {{ background-color: {border_color}; }}

    QGroupBox {{ border: 1px solid {border_color}; margin-top: 20px; font-weight: bold; color: {accent_color}; border-radius: 4px; }}
    QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; left: 10px; }}

    QTableWidget {{ background-color: {panel_color}; color: {text_color}; border: none; gridline-color: {border_color}; }}
    QHeaderView::section {{ background-color: {bg_color}; color: {text_color}; border: none; padding: 4px; font-weight: bold; }}
    QTableWidget::item {{ padding: 5px; }}
    """
    app.setStyleSheet(style_sheet)


def load_pneumo_labels(base_dirs):
    for base in base_dirs:
        if not base:
            continue
        json_path = os.path.join(base, "pneumothorax_labels.json")
        if not os.path.exists(json_path):
            continue
        for enc in ("utf-8-sig", "utf-8", "gbk"):
            try:
                with open(json_path, "r", encoding=enc) as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
                return {}
            except Exception:
                continue
    return {}


def is_dual_folder_mode(orig_root, mask_root):
    if not orig_root or not mask_root:
        return False
    return os.path.normcase(os.path.abspath(orig_root)) != os.path.normcase(
        os.path.abspath(mask_root)
    )

def write_mask_file(
    path: str,
    mask: np.ndarray,
    reference_mask_path: str | None = None,
) -> tuple[bool, str | None]:
    ext = path.lower()

    try:
        mask_bin = (np.asarray(mask) > 0).astype(np.uint8)
    except Exception as e:
        return False, f"掩码数组无效: {e}"

    # 位图格式
    if ext.endswith(MASK_IMAGE_EXTENSIONS):
        out = (mask_bin * 255).astype(np.uint8)
        ok = imwrite_unicode(path, out)
        if not ok:
            return False, "保存位图掩码失败"
        return True, None

    # NIfTI 格式
    if ext.endswith(NIFTI_EXTENSIONS):
        try:
            out_img = sitk.GetImageFromArray(mask_bin.astype(np.uint8))
        except Exception as e:
            return False, f"创建 NIfTI 图像失败: {e}"

        # 如果有原始 NIfTI 掩码，就尽量继承其空间信息
        if reference_mask_path:
            tmp_dir = None
            try:
                ref_img, tmp_dir = _safe_sitk_read_image(reference_mask_path)
                ref_img_2d = _sitk_force_2d(ref_img, "参考掩码")

                # CopyInformation 要求 size 和 dimension 一致
                # SimpleITK 文档明确要求这两项匹配，否则会抛异常
                if tuple(ref_img_2d.GetSize()) != (mask_bin.shape[1], mask_bin.shape[0]):
                    if tmp_dir:
                        shutil.rmtree(tmp_dir, ignore_errors=True)
                    return False, (
                        f"保存 NIfTI 失败：当前掩码尺寸 {mask_bin.shape} 与参考掩码尺寸 "
                        f"{(ref_img_2d.GetSize()[1], ref_img_2d.GetSize()[0])} 不一致"
                    )

                out_img.CopyInformation(ref_img_2d)

                if tmp_dir:
                    shutil.rmtree(tmp_dir, ignore_errors=True)

            except Exception as e:
                if tmp_dir:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                return False, f"读取参考掩码失败: {e}"

        ok, err = _safe_sitk_write_image(out_img, path)
        if not ok:
            return False, err
        return True, None

    return False, "不支持的导出格式"