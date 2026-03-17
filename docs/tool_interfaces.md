# 工具逻辑接口说明

## 目的

本说明用于约定两套工具逻辑的调用边界，确保逻辑层独立、UI 层只做参数与流程控制。

## 模块位置

1. `tools/pa_filter.py`：DICOM 胸片 PA 位筛选逻辑
2. `tools/mask_audit.py`：掩码/JSON 审计与纠正逻辑
3. `s.py`、`清洗json.py`：兼容 CLI 入口，仅代理 `main()`

## tools.pa_filter 接口

核心函数（UI 直接调用，勿走 `main()`）：

```python
decode_bytes_to_str(value) -> Optional[str]
get_view_position(dcm_path: Path) -> Optional[str]
is_pa_view(view_position: str) -> bool
scan_dicom_files(source_dir: Path) -> List[Path]
filter_pa_views(dicom_files: List[Path]) -> Tuple[List[Path], List[Tuple[Path, Optional[str]]]]
copy_pa_files(pa_files: List[Path], source_dir: Path, target_dir: Path) -> None
move_files_preserving_structure(files: List[Path], source_dir: Path, target_dir: Path) -> None
generate_report(all_files_info, pa_files, report_path: Path, source_dir: Path) -> None
```

调用建议（UI 侧流程）：

1. `scan_dicom_files` 获取候选列表
2. `filter_pa_views` 获取 PA 列表与识别信息
3. 需要报告时调用 `generate_report`
4. 需要复制/移动时调用 `copy_pa_files` / `move_files_preserving_structure`

## tools.mask_audit 接口

核心函数（UI 直接调用，勿走 `main()`）：

```python
load_json_mapping(json_path: Path) -> Dict[str, int]
audit_masks(root: Path, mapping: Dict[str, int]) -> Dict[str, Any]
save_json(data: Dict[str, Any], out_path: Path) -> None
build_corrected_mapping(original_mapping, report, sync_both_ways=False) -> (Dict[str, int], Dict[str, Any])
save_corrected_mapping(corrected_mapping: Dict[str, int], out_path: Path) -> None
quarantine_wrong_zero_masks(report, root, quarantine_dir, mode) -> (manifest, errors)
restore_from_manifest(manifest_path: Path, overwrite: bool = False) -> (restored, restored_items, errors)
```

调用建议（UI 侧流程）：

1. `load_json_mapping` 读取标签映射
2. `audit_masks` 生成审计报告
3. `save_json` 保存报告
4. 如需纠正 JSON：`build_corrected_mapping` -> `save_corrected_mapping`
5. 如需隔离掩码：`quarantine_wrong_zero_masks`，并保存 manifest
6. 恢复场景使用 `restore_from_manifest`

## UI 接入约定

1. UI 必须在后台线程调用耗时函数，主线程只负责进度与提示
2. UI 禁止直接调用 `main()`，避免 CLI 交互与阻塞
3. 任何文件复制/移动必须在 UI 层显式确认后再调用
4. 默认建议采用安全策略：仅报告或 dry-run
5. 日志输出仍在标准输出，若需 UI 日志可在 UI 层重定向
