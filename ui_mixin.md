# ui_mixin.py 说明文档

## 功能概述
`ui_mixin.py` 专门负责构建应用程序的图形用户界面 (GUI)。它定义了窗口的布局、面板的停靠、工具栏的按钮、菜单栏的选项以及所有的键盘快捷键映射。

## 主要逻辑与功能

*   **布局构建 (`_init_ui`)**:
    *   使用 `QSplitter` 构建灵活的三栏布局：
        1.  左侧：病例列表面板（Todo & Completed）。
        2.  中央：工作区（包含 `Canvas`、进度滑块 `seek_slider` 和缩略图条 `thumbnail_strip`）。
        3.  右侧：DICOM 元信息面板 (`info_panel`)。
*   **工具栏装配 (`_init_toolbar`)**:
    *   模式切换下拉框（CT/X-Ray）。
    *   标注工具按钮组（画笔、橡皮、多边形），使用 `QActionGroup` 保证互斥。
    *   智能锁定控制区（暗部/亮部切换，阈值调节）。
    *   集成 `VisualControlWidget` 以提供亮度、透明度、调窗和滤镜控制。
*   **菜单栏构建**:
    *   `_init_file_menu()`: 文件加载、保存、任务 JSON 的导入导出。
    *   `_init_window_menu()`: 控制各个面板的显示/隐藏，打开性能设置面板。
*   **信号与槽的映射 (`_on_viz_change`)**:
    *   作为 UI 控件和 `Canvas` 之间的桥梁。监听 `VisualControlWidget` 发出的信号，并将对应的属性（反色、透明度、调窗、滤镜类型、滤镜强度）直接应用到 `Canvas` 实例上。
*   **快捷键绑定 (`_init_shortcuts`)**:
    *   `Ctrl+S`: 保存。
    *   `Ctrl+Z / Ctrl+Y`: 撤销/重做。
    *   `W/A/S/D`: 病例和图像的前后导航。
    *   `Z`: 标记完成/退回。
    *   `T/F`: 标记气胸阴阳性。