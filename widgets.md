# widgets.py 说明文档

## 功能概述
`widgets.py` 定义了应用程序中独立的、可复用的自定义 Qt 控件组件。这些组件主要负责特定区域的信息展示或参数调节，通过信号将用户输入传递给主窗口。

## 主要逻辑与功能

*   **`DicomInfoPanel` (信息面板)**:
    *   右侧的侧边栏组件。
    *   包含一个不可编辑的 `QTableWidget`。
    *   提供 `update_info(path)` 方法，内部调用 `utils.get_dicom_metadata` 并将解析到的 DICOM Tag 和 Value 填充到表格中显示。
*   **`VisualControlWidget` (可视化控制条)**:
    *   嵌入在顶部工具栏的紧凑控制组件。
    *   内部包含反色按钮、透明度滑块、亮度滑块。
    *   **调窗控件**: 包含代表窗位 (C) 和窗宽 (W) 的两个滑块。提供 `set_window_controls` 方法，根据不同图像的实际动态范围动态更新滑块的最大/最小值。
    *   **滤镜控件**: 包含一个滤镜类型下拉框和一个控制滤镜强度的滑块。
    *   统一通过 `valueChanged(str, float)` 自定义信号将用户的调整操作发送出去。
*   **`PrefetchSettingsDialog` (性能设置对话框)**:
    *   弹窗组件，包含 CT 和 X光 两个 Tab 页。
    *   提供多个 `QSpinBox` 让用户调整序列预取张数、跨病号预取数量以及内存缓存上限。
    *   提供 `get_values()` 方法方便主窗口收集保存的设置。
*   **`ExportSettingsDialog` (导出设置对话框)**:
    *   弹窗组件，用于单张图像及掩码的合并导出。
    *   允许用户自定义导出分辨率（宽高）、图片质量、格式（PNG/JPG）以及是否反色。
    *   包含一个路径浏览输入框。