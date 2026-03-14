# utils.py 说明文档

## 功能概述
`utils.py` 是底层工具函数库。它封装了与 UI 无关的核心图像处理逻辑，包括 DICOM 解析、SimpleITK NIfTI 读写、OpenCV 常规图像读写，以及应用程序的 QSS 样式主题注入。

## 主要逻辑与功能

*   **DICOM 处理**:
    *   `read_dicom_with_window(path)`: 核心读取函数。使用 `pydicom` 读取原始数据，应用 `RescaleSlope` 和 `RescaleIntercept` 获得真实的物理值（如 CT 的 HU 值）。同时解析并返回内置的窗宽窗位（WW/WC）元数据。
    *   `get_dicom_metadata(path)`: 快速提取患者 ID、研究日期等头部信息供右侧信息面板使用。
*   **高级掩码读写 (`read_mask_file` / `write_mask_file`)**:
    *   支持普通的位图掩码（PNG/JPG）和 3D 医学影像格式（NIfTI: `.nii`, `.nii.gz`）。
    *   **NIfTI 空间对齐 (`_read_nifti_mask_aligned`)**: 使用 `SimpleITK`。如果提供了参考的原图路径，会自动按照原图的物理坐标系（Spacing, Origin, Direction）对 NIfTI 掩码进行精准重采样（Resample），确保无论矩阵系如何变化，物理位置绝对对齐。
    *   **中文路径兜底 (`_safe_sitk_read_image`)**: SimpleITK 原生不支持中文字符路径。这里实现了一个精巧的机制：当检测到路径含有非 ASCII 字符时，自动拷贝到纯英文的临时目录读取后再销毁，解决了国内用户的痛点。
*   **通用图像 I/O**:
    *   `imread_unicode` / `imwrite_unicode`: 利用 numpy buffer 绕过 `cv2.imread` 不支持中文路径的问题。
*   **辅助工具**:
    *   `natural_sort_key`: 实现“自然排序”，确保 `image2.png` 排在 `image10.png` 前面。
    *   `apply_tech_theme`: 使用硬编码的 QSS 字符串为整个应用程序注入一套深色科技风主题。