# NIfTI 掩码读取问题记录

## 现象

- 读取 **中文路径** 下的 NIfTI 掩码（`.nii` / `.nii.gz`）时，偶尔会报错，无法正常加载。
- 掩码文件名中如果包含某些标点符号（例如多个点号 `.` 等），也会出现 **无法打开 / 读取失败** 的情况。

## 代码路径

NIfTI 掩码的读取链路集中在以下位置：

- `utils.py:340-360  read_mask_file`
- `utils.py:264-329  _read_nifti_mask_aligned`
- `utils.py:181-219  _has_non_ascii / _safe_sitk_read_image`

### 入口：read_mask_file

```python
# utils.py:340-360

def read_mask_file(
    path: str,
    target_shape: tuple[int, int] | None = None,
    reference_image_path: str | None = None,
) -> tuple[np.ndarray | None, str | None]:
    ext = path.lower()

    if ext.endswith(MASK_IMAGE_EXTENSIONS):
        mask = imread_unicode(path, cv2.IMREAD_GRAYSCALE)
        ...

    if ext.endswith(NIFTI_EXTENSIONS):
        return _read_nifti_mask_aligned(
            path,
            target_shape=target_shape,
            reference_image_path=reference_image_path,
        )

    return None, "不支持的掩码格式"
```

结论：只要扩展名是 `.nii` / `.nii.gz`，就会走 `_read_nifti_mask_aligned`。

### NIfTI 读取核心：_read_nifti_mask_aligned

```python
# utils.py:264-329

def _read_nifti_mask_aligned(
    path: str,
    target_shape: tuple[int, int] | None = None,
    reference_image_path: str | None = None,
) -> tuple[np.ndarray | None, str | None]:
    temp_dirs: list[str] = []

    try:
        # 1) 安全读取 NIfTI（兼容中文路径兜底）
        mask_img, tmp1 = _safe_sitk_read_image(path)
        ...
```

真正读 NIfTI 文件的地方是 `_safe_sitk_read_image`。

### 路径兼容逻辑：_has_non_ascii / _safe_sitk_read_image

```python
# utils.py:181-219

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
```

## 问题分析

1. **中文路径 NIfTI 掩码**
   - 设计逻辑：
     - `sitk.ReadImage(path)` 失败，且 `os.path.exists(path)` 为真；
     - 如果 `_has_non_ascii(path) == True`，则复制到临时英文目录再读。
   - 可能的问题：
     - `os.path.exists(path)` 在某些特殊中文路径/网络盘上返回 False → 直接抛 `FileNotFoundError`，导致上层看到“读取 NIfTI 失败”；
     - 或者拷贝后 `sitk.ReadImage(dst)` 仍失败，但异常没有被更细致处理，上层也只看到泛化的 NIfTI 失败提示。

2. **带标点（尤其是多点号）的 NIfTI 掩码名**
   - 普通英文标点（例如 `.`、`-`、`_`）是 ASCII 字符，不会触发 `_has_non_ascii`：
     - 一旦 `sitk.ReadImage(path)` 抛异常，`_has_non_ascii(path) == False`，代码直接 `raise` 原异常；
     - **不会尝试复制到临时英文目录再读**。
   - 这意味着：
     - 只要 SimpleITK 自身对某些合法但复杂的路径（如多重 `.`）处理不稳定，就会直接暴露为“读取失败”，而并不享受兜底逻辑。

3. 总结

- 当前 `_safe_sitk_read_image` 的兜底逻辑 **仅在“路径包含非 ASCII 字符”时启用**：
  - 对中文路径：理论上能覆盖一部分问题，但仍依赖 `os.path.exists(path)` 和第二次 `ReadImage` 成功；
  - 对纯 ASCII 路径但包含“特殊标点/长度/编码”场景：完全没有兜底。
- 这与实际需求不符：
  - 对于“无法读取但文件确实存在”的情况，其实也希望能复制到临时简单路径再试一次，而不限定在“包含非 ASCII”上。

## 拟议解决思路（待实现）

> 此处只记录思路，不改代码，方便后续实现时对照。

1. **放宽兜底触发条件**
   - 现状：
     ```python
     if not _has_non_ascii(path):
         raise
     ```
   - 建议：
     - 考虑将“临时复制再读”的逻辑改为：
       - **只要 `os.path.exists(path)` 为 True，且第一次 `ReadImage` 失败，就尝试复制到临时目录再读一次**；
       - 可选地保留 `_has_non_ascii` 作为“是否值得兜底”的 hint，但不要把它作为唯一条件。

2. **增强错误信息与区分**
   - 在 `_read_nifti_mask_aligned` 中，对 `_safe_sitk_read_image` 抛出的异常信息做更精细包装：
     - 区分：文件不存在 / SimpleITK 解码失败 / 临时复制失败等；
     - 便于用户在 GUI 中判断是路径问题还是文件本身损坏。

3. **验证点**（实现时需要覆盖的测试场景）
   - 路径/文件名组合：
     - 纯中文目录 + `.nii` / `.nii.gz` 文件；
     - 混合中英文 + 多级子目录；
     - 文件名包含多个点号，如：`case.v1.mask.nii.gz`；
     - 非法/损坏的 NIfTI 文件，确认仍能给出清晰错误信息。

---

> 以上为 NIfTI 掩码在“中文路径 + 特殊标点名称”场景下的现有逻辑和问题分析，以及后续修改思路。下一步可以在 `utils.py` 中调整 `_safe_sitk_read_image` 的兜底条件，并补充相应测试。