"""集中定义扩展名、导出格式与路径规则，避免多处散落维护。"""

from __future__ import annotations

import os

JPEG_EXTENSIONS = (".jpg", ".jpeg")
BITMAP_IMAGE_EXTENSIONS = (".png",) + JPEG_EXTENSIONS + (".bmp",)
TIFF_EXTENSIONS = (".tif", ".tiff")
NIFTI_EXTENSIONS = (".nii", ".nii.gz")
MASK_IMAGE_EXTENSIONS = BITMAP_IMAGE_EXTENSIONS
MASK_FILE_EXTENSIONS = MASK_IMAGE_EXTENSIONS + NIFTI_EXTENSIONS
KNOWN_IMAGE_EXTENSIONS = NIFTI_EXTENSIONS + BITMAP_IMAGE_EXTENSIONS + TIFF_EXTENSIONS
CT_SOURCE_EXTENSIONS = BITMAP_IMAGE_EXTENSIONS + TIFF_EXTENSIONS + (".dcm",)
XRAY_MASK_CANDIDATE_EXTENSIONS = NIFTI_EXTENSIONS + MASK_IMAGE_EXTENSIONS
XRAY_IGNORED_SOURCE_EXTENSIONS = {".py", ".json", ".txt", ".md", ".exe", ".dll", ".bat"}

DEFAULT_MASK_SUFFIX = "_mask"
DEFAULT_MASK_BITMAP_EXT = ".png"
DEFAULT_NIFTI_EXT = ".nii.gz"
DEFAULT_EXPORT_FORMAT = "png"
DEFAULT_EXPORT_QUALITY = 95
QUALITY_MIN = 1
QUALITY_MAX = 100
PNG_COMPRESSION_MAX = 9

DICOM_FILE_FILTER = "DICOM Files (*.dcm *.dicom);;All Files (*)"
MASK_FILE_FILTER = "Mask Files (*.png *.nii *.nii.gz);;All Files (*)"
NIFTI_MASK_EXPORT_FILTER = "NIfTI 掩码 (*.nii.gz *.nii);;PNG 掩码 (*.png)"

EXPORT_FORMAT_TO_EXT = {
    "png": ".png",
    "jpg": ".jpg",
    "nii": DEFAULT_NIFTI_EXT,
}

CT_MASK_CANDIDATE_SUFFIXES = (
    DEFAULT_NIFTI_EXT,
    ".nii",
    DEFAULT_MASK_SUFFIX + DEFAULT_NIFTI_EXT,
    DEFAULT_MASK_SUFFIX + ".nii",
    ".png",
    DEFAULT_MASK_SUFFIX + ".png",
)

PREVIEW_MASK_SEARCH_EXTENSIONS = (DEFAULT_MASK_BITMAP_EXT,) + NIFTI_EXTENSIONS


def endswith_any(value: str | None, suffixes: tuple[str, ...]) -> bool:
    return bool(value) and str(value).lower().endswith(suffixes)


def split_known_image_ext(path: str | None) -> tuple[str, str]:
    path = path or ""
    lower = path.lower()
    for ext in KNOWN_IMAGE_EXTENSIONS:
        if lower.endswith(ext):
            return path[: -len(ext)], ext
    return path, ""


def strip_known_image_ext(path: str | None) -> str:
    return split_known_image_ext(path)[0]


def default_mask_filename(stem: str, ext: str = DEFAULT_MASK_BITMAP_EXT) -> str:
    return f"{stem}{DEFAULT_MASK_SUFFIX}{ext}"


def default_mask_path(parent_dir: str, stem: str, ext: str = DEFAULT_MASK_BITMAP_EXT) -> str:
    return os.path.join(parent_dir, default_mask_filename(stem, ext))
