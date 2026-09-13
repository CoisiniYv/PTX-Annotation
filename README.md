# PTX Annotation

用于胸部 X 光与 CT 气胸数据的标注、复核与掩码管理桌面工具。

> 当前重构分支：`refactor/project-structure-docs-packaging`。

## 功能

- CT 序列与 X 光单图两种工作模式
- PNG / NIfTI 掩码读取、编辑与保存
- DICOM 读取及窗宽窗位显示
- 画笔、橡皮、多边形、撤销/重做
- 病例搜索、任务 JSON、标注状态管理
- 图像缓存与后台预取
- PA 位筛选及掩码/JSON 审计工具
- SQLite 元数据持久化

## 环境

建议 Python 3.10 或 3.11。

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## 启动

```bash
python app.py
```

也可以将影像文件作为参数传入：

```bash
python app.py path/to/image.dcm
```

### 基本使用

1. 在工具栏选择 `CT SEQUENCE` 或 `X-RAY SINGLE`。
2. 从“文件 -> 加载”选择原图目录；需要时选择掩码目录。
3. 扫描病例后，从左侧列表进入病例。
4. 使用画笔、橡皮或多边形修订掩码。
5. `Ctrl+S` 保存；开启自动保存后切换病例时会自动写回。
6. `T/F` 可设置当前病例气胸阳性/阴性标签。

常用快捷键：`1/2/3` 切换工具，`A/D` 上一张/下一张，`W/S` 上一病例/下一病例，`Ctrl+Z/Ctrl+Y` 撤销/重做，`Ctrl+F` 搜索病例。

## 项目架构

```text
app.py                         应用入口
  |
  v
main_window.py                 主窗口与共享运行状态
  |
  +-- ui_mixin.py              UI、菜单、快捷键、病例搜索
  +-- actions_mixin.py         保存、导出、导航、交互动作
  +-- data_mixin.py            扫描、加载、缓存、预取、SQLite
  +-- canvas.py                掩码绘制与显示画布
  +-- widgets.py               对话框与复合控件
  +-- models.py                ImageEntry / ScanMode / ToolType
  +-- constants.py             扩展名与格式常量
  +-- utils.py                 DICOM / OpenCV / NIfTI 通用 I/O
  +-- tools/
      +-- case_search.py       病例搜索
      +-- pa_filter.py         PA 位筛选
      +-- mask_audit.py        掩码与标签审计
```

运行时数据流：

```text
影像目录 / 任务 JSON
        |
        v
DataMixin -> ImageEntry -> 缓存/预取 -> Canvas
        |                         |
        v                         v
SQLite 状态/标签            ActionsMixin
                                  |
                                  v
                            保存/导出掩码
```

`MedicalLabelPro` 通过 Mixin 组合现有业务能力。当前重构优先保持功能稳定，后续建议逐步把 `DataMixin` 中的扫描、元数据存储、缓存与预取拆成独立 service，而不是一次性大规模改写。

## 数据与隐私

仓库用于程序代码，不应提交真实医疗影像、患者信息、任务运行数据库或本地标注产物。`.gitignore` 应持续屏蔽 DICOM/NIfTI 数据以及 `.chexagent_meta.sqlite` 等运行时文件。

## 测试

```bash
pytest -q
```

## 打包

安装开发依赖：

```bash
pip install -r requirements-dev.txt
```

Windows 推荐使用 PyInstaller：

```bash
pyinstaller --noconfirm --clean --windowed --onedir --name PTX-Annotation --icon icon1.ico app.py
```

生成目录位于 `dist/PTX-Annotation/`。如需单文件版本，可将 `--onedir` 改成 `--onefile`；对于 PySide6、SimpleITK、OpenCV 这类依赖较多的桌面应用，`onedir` 通常更容易排查缺失动态库问题。

## 维护建议

- 不要在提交信息中自动加入 AI `Co-Authored-By` trailer，除非确实希望 GitHub 将该身份显示为共同作者。
- 新功能优先放入 `tools/` 或独立 service，避免继续扩大 `data_mixin.py` 与 `actions_mixin.py`。
- 修改 DICOM/NIfTI I/O 后应运行现有测试并使用脱敏样例做人工回归。
