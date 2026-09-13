# PTX Annotation

面向胸部 X 光与 CT 气胸数据的桌面标注、复核与掩码管理工具，基于 PySide6 构建，支持 DICOM、PNG 与 NIfTI 工作流。

## 功能

- CT 序列与 X 光单图两种工作模式
- DICOM 读取、窗宽窗位显示与快速预览
- PNG / NIfTI 掩码读取、编辑、保存与导出
- 画笔、橡皮、多边形、撤销 / 重做
- 病例搜索、任务 JSON、完成状态与标签管理
- 图像缓存、序列预取与跨病例预取
- PA 位筛选、掩码审计与标签清洗工具
- SQLite 元数据持久化

## 环境安装

推荐 Python 3.10 或 3.11。

```bash
python -m venv .venv
```

Windows：

```bash
.venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux：

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## 启动

```bash
python app.py
```

也可以直接传入影像文件进行快速预览：

```bash
python app.py path/to/image.dcm
```

## 基本使用

1. 在工具栏选择 `CT SEQUENCE` 或 `X-RAY SINGLE`。
2. 通过“文件 -> 加载”选择原图目录，需要时选择掩码目录。
3. 扫描病例后，从左侧病例列表进入目标病例。
4. 使用画笔、橡皮或多边形工具修订掩码。
5. 使用 `Ctrl+S` 保存；开启自动保存后，切换病例时会自动写回。
6. 使用 `T / F` 设置当前病例的气胸阳性 / 阴性标签。

常用快捷键：

| 快捷键 | 功能 |
| --- | --- |
| `1 / 2 / 3` | 画笔 / 橡皮 / 多边形 |
| `A / D` | 上一张 / 下一张 |
| `W / S` | 上一病例 / 下一病例 |
| `Ctrl+S` | 保存掩码 |
| `Ctrl+Z / Ctrl+Y` | 撤销 / 重做 |
| `Ctrl+F` | 搜索病例 |
| `T / F` | 阳性 / 阴性标签 |

## 项目结构

```text
PTX-Annotation/
├── app.py                  # 程序入口
├── app_config.py           # 应用名称、版本与性能默认配置
├── main_window.py          # 主窗口与共享运行状态
├── ui_mixin.py             # UI、菜单、快捷键、病例搜索
├── actions_mixin.py        # 保存、导出、导航与交互动作
├── data_mixin.py           # 扫描、加载、缓存、预取与 SQLite
├── canvas.py               # 图像 / 掩码绘制画布
├── widgets.py              # 对话框与复合控件
├── models.py               # 核心数据模型与枚举
├── constants.py            # 文件格式、扩展名与路径规则
├── utils.py                # DICOM / OpenCV / NIfTI 通用 I/O
├── icons.py                # 界面图标生成
├── tools/                  # 独立业务工具
│   ├── case_search.py
│   ├── mask_audit.py
│   └── pa_filter.py
├── tests/                  # 自动化测试
├── docs/                   # 设计与排障文档
├── assets/                 # 程序资源
├── scripts/                # 构建与维护脚本
├── requirements.txt
└── requirements-dev.txt
```

## 程序架构

```text
                    app.py
                      |
                      v
               MedicalLabelPro
                      |
        +-------------+-------------+
        |             |             |
        v             v             v
    UiMixin       DataMixin     ActionsMixin
        |             |             |
        |             |             +---- 保存 / 导出 / 导航
        |             +------------------ 扫描 / 缓存 / 预取 / SQLite
        +-------------------------------- UI / 菜单 / 快捷键
                      |
                      v
                    Canvas
                      |
                      v
             图像显示与掩码编辑
```

数据流：

```text
影像目录 / 任务 JSON
        |
        v
   病例扫描与解析
        |
        v
    ImageEntry
        |
        +------> 图像缓存 / 后台预取 ------> Canvas
        |
        +------> SQLite 状态与标签
        |
        +------> 掩码读取 / 保存 / 导出
```

当前结构采用 Mixin 组合已有业务能力。后续如果继续扩大项目，优先将扫描、缓存、预取和元数据存储逐步抽成独立 service，而不是继续扩大单个 Mixin 文件。

## 测试

安装开发依赖：

```bash
pip install -r requirements-dev.txt
```

运行测试：

```bash
pytest -q
```

## 打包

推荐使用仓库中的统一构建脚本：

```bash
python scripts/build.py
```

默认生成 `onedir` 版本，输出目录：

```text
dist/PTX-Annotation/
```

如需单文件：

```bash
python scripts/build.py --onefile
```

也可以直接调用 PyInstaller：

```bash
pyinstaller --noconfirm --clean --windowed --onedir \
  --name PTX-Annotation \
  --icon assets/icon.ico \
  app.py
```

对于 PySide6、SimpleITK、OpenCV 这类依赖较多的桌面程序，优先推荐 `onedir`，更容易定位动态库或插件缺失问题。

## 数据与隐私

仓库只用于程序代码与脱敏测试逻辑，不应提交真实医疗影像、患者信息、任务运行数据库或本地标注产物。

`.gitignore` 已屏蔽常见 DICOM / NIfTI 数据、SQLite 运行状态、缓存和构建产物。公开仓库提交前仍建议人工检查待提交文件。
