# main_window.py 说明文档

## 功能概述
`main_window.py` 是整个应用程序的入口和躯干。它定义了 `MedicalLabelPro` 主窗口类，通过多重继承（Mixin 模式）将 UI、数据管理、交互动作整合在一起，并负责全局状态的初始化。

## 主要逻辑与功能

*   **多重继承结构**:
    *   `class MedicalLabelPro(QMainWindow, UiMixin, DataMixin, ActionsMixin)`
    *   这种设计模式将庞大的逻辑拆分到了不同的文件中，`main_window.py` 仅负责组装它们。
*   **全局状态管理**:
    *   初始化工作目录变量（`orig_root`, `mask_root`）。
    *   管理当前应用的模式（`scan_mode`、`task_mode`、`single_pair_mode`）。
    *   初始化预取和缓存的性能参数（`ct_prefetch_count`, `xray_cache_max` 等）。
*   **组件实例化与连接**:
    *   实例化 `Canvas` 并将其信号（如缩放、坐标变化、内容修改）连接到主窗口的状态栏。
    *   调用 `_init_ui()`, `_init_toolbar()`, `_init_shortcuts()`, `_init_file_menu()`, `_init_window_menu()` 等方法完成界面装配。
*   **配置持久化 (`QSettings`)**:
    *   使用 `QSettings` 从系统注册表或配置文件中读取和保存性能参数（预取数量、缓存大小）。
*   **拖拽支持**:
    *   实现了主窗口级别的 `dragEnterEvent` 和 `dropEvent`，支持将图像文件直接拖入软件进行快速预览加载。