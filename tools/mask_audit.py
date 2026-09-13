#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PNG 掩码与标签 JSON 审计/清洗工具。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any


def normalize_rel_path(rel_path: str) -> Path:
    rel_path = str(rel_path).strip().replace("\\", "/").lstrip("/")
    parts = [p for p in rel_path.split("/") if p not in ("", ".")]
    return Path(*parts)


def parse_label_value(v: Any) -> int:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return 1 if v != 0 else 0
    if isinstance(v, str):
        vv = v.strip().lower()
        if vv in {"1", "true", "yes", "y"}:
            return 1
        if vv in {"0", "false", "no", "n", ""}:
            return 0
    raise ValueError(f"无法解析标签值: {v!r}")


def load_json_mapping(json_path: Path) -> Dict[str, int]:
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("JSON 顶层必须是 dict，格式应为 {相对路径: 0/1, ...}")
    return {str(k): parse_label_value(v) for k, v in data.items()}


# ======================================================================
# 空掩码检测：读取现有掩码文件，判断其内容是否全零（无任何标注像素）
# ======================================================================

def detect_empty_masks(
    mask_paths: List[str],
    progress_cb=None,
    cancel_cb=None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """扫描掩码文件列表，返回 (empty_list, error_list)。

    - empty_list: 内容全零的掩码条目，每项为 {path, size_bytes}
    - error_list: 读取失败的条目，每项为 {path, error}

    参数:
        mask_paths: 待检测的掩码文件绝对路径列表。
        progress_cb: 可选回调 progress_cb(done, total)，用于 UI 进度更新。
        cancel_cb:   可选回调 cancel_cb() -> bool，返回 True 表示请求取消。

    注意：懒加载 cv2 / SimpleITK，避免在非 GUI 场景下引入额外依赖。
    """
    import os

    empty_list: List[Dict[str, Any]] = []
    error_list: List[Dict[str, Any]] = []

    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception as e:
        error_list.append({"path": "(imports)", "error": f"cv2/numpy 缺失: {e}"})
        return empty_list, error_list

    _sitk = None

    def _path_has_non_ascii(p: str) -> bool:
        try:
            p.encode("ascii")
            return False
        except UnicodeEncodeError:
            return True

    def _read_nifti_array_safe(path: str):
        """读 NIfTI 数组；路径含非 ASCII 时先复制到临时 ASCII 路径。

        这是 Windows 上 SimpleITK C++ ImageFileReader 的已知限制：
        narrow-char 路径无法识别中文/日文/韩文等字符。
        """
        nonlocal _sitk
        if _sitk is None:
            import SimpleITK as _sitk_mod  # type: ignore
            _sitk = _sitk_mod

        if not _path_has_non_ascii(path):
            img = _sitk.ReadImage(path)
            return _sitk.GetArrayFromImage(img)

        import shutil as _shutil
        import tempfile as _tempfile
        lower = path.lower()
        if lower.endswith(".nii.gz"):
            suffix = ".nii.gz"
        elif lower.endswith(".nii"):
            suffix = ".nii"
        else:
            suffix = os.path.splitext(path)[1] or ".nii"

        tmp_dir = _tempfile.mkdtemp(prefix="sitk_ascii_scan_")
        try:
            tmp_path = os.path.join(tmp_dir, "mask" + suffix)
            _shutil.copy2(path, tmp_path)
            img = _sitk.ReadImage(tmp_path)
            return _sitk.GetArrayFromImage(img)
        finally:
            _shutil.rmtree(tmp_dir, ignore_errors=True)

    total = len(mask_paths)
    for i, p in enumerate(mask_paths):
        if cancel_cb and cancel_cb():
            break
        if progress_cb:
            try:
                progress_cb(i, total)
            except Exception:
                pass

        try:
            if not p or not os.path.isfile(p):
                error_list.append({"path": p, "error": "文件不存在"})
                continue

            size_bytes = os.path.getsize(p)
            lower = p.lower()

            if lower.endswith((".nii", ".nii.gz")):
                try:
                    arr = _read_nifti_array_safe(p)
                except ImportError as e:
                    error_list.append({"path": p, "error": f"SimpleITK 缺失: {e}"})
                    continue
                except Exception as e:
                    error_list.append({"path": p, "error": f"NIfTI 读取失败: {e}"})
                    continue
            else:
                # PNG / BMP / JPG 等位图：用 unicode-safe 的 imdecode
                try:
                    buf = np.fromfile(p, dtype=np.uint8)
                    if buf.size == 0:
                        error_list.append({"path": p, "error": "空文件"})
                        continue
                    arr = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
                except Exception as e:
                    error_list.append({"path": p, "error": f"位图读取失败: {e}"})
                    continue
                if arr is None:
                    error_list.append({"path": p, "error": "位图解码失败"})
                    continue

            if arr is None or getattr(arr, "size", 0) == 0:
                error_list.append({"path": p, "error": "数组为空"})
                continue

            # 多通道（RGBA / RGB）：任意通道非零即视为有内容
            try:
                max_val = float(arr.max())
            except Exception as e:
                error_list.append({"path": p, "error": f"无法计算最大值: {e}"})
                continue

            if max_val <= 0.0:
                empty_list.append({"path": p, "size_bytes": int(size_bytes)})
        except Exception as e:
            error_list.append({"path": p, "error": f"未知错误: {e}"})

    if progress_cb:
        try:
            progress_cb(total, total)
        except Exception:
            pass

    return empty_list, error_list


def find_mask_pngs(root: Path, rel_key: str) -> List[Path]:
    """
    对于 key=.../IM0，寻找可能的掩码文件：
      - IM0.png
      - IM0_mask.png
      - IM0.dcm.png
      - IM0.xxx.png
    若 IM0 本身是目录，额外扫描目录下一层 *.png。
    """
    rel_path = normalize_rel_path(rel_key)
    abs_base = root / rel_path
    parent = abs_base.parent
    name = abs_base.name

    found = set()

    if parent.is_dir():
        pattern = re.compile(
            rf"^{re.escape(name)}(?:|_mask|(?:\.[^.]+)+)\.png$",
            re.IGNORECASE,
        )
        for p in parent.iterdir():
            if p.is_file() and p.name.lower().endswith(".png"):
                if pattern.match(p.name):
                    found.add(p.resolve())

    if abs_base.is_dir():
        for p in abs_base.iterdir():
            if p.is_file() and p.name.lower().endswith(".png"):
                found.add(p.resolve())

    return sorted(found)


def audit_masks(root: Path, mapping: Dict[str, int]) -> Dict[str, Any]:
    total = 0
    actual_has_mask_count = 0
    label_1_count = 0
    label_0_count = 0

    ok_positive = []
    missing_positive = []
    wrong_zero_with_mask = []
    correct_zero_without_mask = []

    for rel_key, label in mapping.items():
        total += 1
        if label == 1:
            label_1_count += 1
        else:
            label_0_count += 1

        mask_files = find_mask_pngs(root, rel_key)
        has_mask = len(mask_files) > 0

        if has_mask:
            actual_has_mask_count += 1

        item = {
            "rel_path": rel_key,
            "label": label,
            "has_mask": has_mask,
            "mask_files": [str(p) for p in mask_files],
        }

        if label == 1 and has_mask:
            ok_positive.append(item)
        elif label == 1 and not has_mask:
            missing_positive.append(item)
        elif label == 0 and has_mask:
            wrong_zero_with_mask.append(item)
        else:
            correct_zero_without_mask.append(item)

    return {
        "summary": {
            "total_cases": total,
            "label_1_cases": label_1_count,
            "label_0_cases": label_0_count,
            "actual_has_mask_cases": actual_has_mask_count,
            "label_1_and_found_mask": len(ok_positive),
            "label_1_but_missing_mask": len(missing_positive),
            "label_0_but_found_mask": len(wrong_zero_with_mask),
            "label_0_and_no_mask": len(correct_zero_without_mask),
        },
        "details": {
            "label_1_and_found_mask": ok_positive,
            "label_1_but_missing_mask": missing_positive,
            "label_0_but_found_mask": wrong_zero_with_mask,
            "label_0_and_no_mask": correct_zero_without_mask,
        },
    }


def save_json(data: Dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def unique_quarantine_path(quarantine_dir: Path, src_path: Path, root: Path) -> Path:
    """在隔离区尽量保留相对路径，避免重名覆盖。"""
    try:
        rel = src_path.resolve().relative_to(root.resolve())
    except Exception:
        rel = Path(src_path.name)

    dst = quarantine_dir / rel
    if not dst.exists():
        return dst

    stem = dst.stem
    suffix = dst.suffix
    parent = dst.parent
    i = 1
    while True:
        candidate = parent / f"{stem}__dup{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def quarantine_wrong_zero_masks(
    report: Dict[str, Any],
    root: Path,
    quarantine_dir: Path,
    mode: str,
) -> Tuple[Dict[str, Any], List[str]]:
    """把 value=0 但存在的掩码移动/复制到隔离区，并返回 manifest。"""
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    ops = []
    errors = []
    seen = set()

    for item in report["details"]["label_0_but_found_mask"]:
        rel_path = item["rel_path"]
        for path_str in item["mask_files"]:
            if path_str in seen:
                continue
            seen.add(path_str)

            src = Path(path_str)
            if not src.exists() or not src.is_file():
                errors.append(f"不存在或不是文件: {src}")
                continue

            dst = unique_quarantine_path(quarantine_dir, src, root)
            dst.parent.mkdir(parents=True, exist_ok=True)

            try:
                if mode == "move":
                    shutil.move(str(src), str(dst))
                elif mode == "copy":
                    shutil.copy2(str(src), str(dst))
                else:
                    raise ValueError(f"未知模式: {mode}")

                ops.append(
                    {
                        "rel_case_path": rel_path,
                        "action": mode,
                        "src_original": str(src),
                        "dst_quarantine": str(dst),
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                    }
                )
            except Exception as e:
                errors.append(f"{src} -> {dst} :: {e}")

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "root": str(root),
        "quarantine_dir": str(quarantine_dir),
        "operations": ops,
        "errors": errors,
    }
    return manifest, errors


def restore_from_manifest(
    manifest_path: Path,
    overwrite: bool = False,
) -> Tuple[int, List[str], List[str]]:
    """从 manifest 恢复。"""
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    restored = 0
    restored_items = []
    errors = []

    operations = manifest.get("operations", [])
    mode = manifest.get("mode", "")

    for op in operations:
        src_q = Path(op["dst_quarantine"])
        dst_o = Path(op["src_original"])

        try:
            if not src_q.exists():
                errors.append(f"隔离文件不存在: {src_q}")
                continue

            if dst_o.exists() and not overwrite:
                errors.append(f"原路径已存在，跳过恢复: {dst_o}")
                continue

            dst_o.parent.mkdir(parents=True, exist_ok=True)

            if mode == "move":
                shutil.move(str(src_q), str(dst_o))
            elif mode == "copy":
                shutil.copy2(str(src_q), str(dst_o))
            else:
                errors.append(f"manifest 中未知 mode: {mode}")
                continue

            restored += 1
            restored_items.append(f"{src_q} -> {dst_o}")
        except Exception as e:
            errors.append(f"{src_q} -> {dst_o} :: {e}")

    return restored, restored_items, errors


def print_summary(report: Dict[str, Any], print_limit: int) -> None:
    summary = report["summary"]
    print("=" * 80)
    print("扫描完成")
    print("=" * 80)
    print(f"总例数: {summary['total_cases']}")
    print(f"JSON 标记为 1 的例数: {summary['label_1_cases']}")
    print(f"JSON 标记为 0 的例数: {summary['label_0_cases']}")
    print(f"实际扫描到有掩码的例数: {summary['actual_has_mask_cases']}")
    print(f"值为 1 且找到了掩码: {summary['label_1_and_found_mask']}")
    print(f"值为 1 但没找到掩码: {summary['label_1_but_missing_mask']}")
    print(f"值为 0 但找到了掩码（错误标注）: {summary['label_0_but_found_mask']}")
    print(f"值为 0 且没有掩码: {summary['label_0_and_no_mask']}")
    print("-" * 80)

    wrong_items = report["details"]["label_0_but_found_mask"]
    if wrong_items:
        print("值为 0 但存在 png 掩码的错误标注列表：")
        for idx, item in enumerate(wrong_items[:print_limit], 1):
            print(f"[{idx}] {item['rel_path']}")
            for mf in item["mask_files"]:
                print(f"     - {mf}")
        if len(wrong_items) > print_limit:
            print(f"... 还有 {len(wrong_items) - print_limit} 条未显示，请查看报告 JSON。")
    else:
        print("没有发现值为 0 但存在 png 掩码的错误标注。")
    print("=" * 80)


def build_corrected_mapping(
    original_mapping: Dict[str, int],
    report: Dict[str, Any],
    sync_both_ways: bool = False,
) -> Tuple[Dict[str, int], Dict[str, Any]]:
    """
    根据扫描结果生成新的纠正 mapping。

    默认 (sync_both_ways=False)：
      - 只修正：label=1 但没找到掩码 -> 0

    若 sync_both_ways=True：
      - 有掩码 -> 1
      - 无掩码 -> 0
    """
    corrected = dict(original_mapping)

    has_mask_map = {}
    for item in report["details"]["label_1_and_found_mask"]:
        has_mask_map[item["rel_path"]] = True
    for item in report["details"]["label_1_but_missing_mask"]:
        has_mask_map[item["rel_path"]] = False
    for item in report["details"]["label_0_but_found_mask"]:
        has_mask_map[item["rel_path"]] = True
    for item in report["details"]["label_0_and_no_mask"]:
        has_mask_map[item["rel_path"]] = False

    changed_1_to_0 = []
    changed_0_to_1 = []
    unchanged = 0

    for rel_path, old_value in original_mapping.items():
        has_mask = has_mask_map.get(rel_path, False)

        if sync_both_ways:
            new_value = 1 if has_mask else 0
        else:
            if old_value == 1 and not has_mask:
                new_value = 0
            else:
                new_value = old_value

        corrected[rel_path] = new_value

        if new_value == old_value:
            unchanged += 1
        elif old_value == 1 and new_value == 0:
            changed_1_to_0.append(rel_path)
        elif old_value == 0 and new_value == 1:
            changed_0_to_1.append(rel_path)

    stats = {
        "sync_both_ways": sync_both_ways,
        "total_cases": len(original_mapping),
        "unchanged": unchanged,
        "changed_1_to_0": len(changed_1_to_0),
        "changed_0_to_1": len(changed_0_to_1),
        "changed_1_to_0_paths": changed_1_to_0,
        "changed_0_to_1_paths": changed_0_to_1,
    }
    return corrected, stats


def save_corrected_mapping(corrected_mapping: Dict[str, int], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(corrected_mapping, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="安全审计 png 掩码，支持隔离与恢复。")

    parser.add_argument("--root", help="数据 root 目录")
    parser.add_argument("--json", help="标注 JSON 路径，格式 {相对路径: 0/1}")
    parser.add_argument("--report-out", default="mask_audit_report.json", help="输出报告 JSON")
    parser.add_argument("--print-limit", type=int, default=200, help="终端最多打印多少条")
    parser.add_argument("--quarantine-dir", default="mask_quarantine", help="隔离目录")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--move-wrong-zero", action="store_true", help="把值为 0 但存在的掩码移动到隔离区")
    group.add_argument("--copy-wrong-zero", action="store_true", help="把值为 0 但存在的掩码复制到隔离区")
    group.add_argument("--restore-from-manifest", help="从 manifest 恢复")

    parser.add_argument("--overwrite", action="store_true", help="恢复时若原文件已存在则覆盖")

    parser.add_argument(
        "--write-corrected-json",
        help="输出纠正后的 JSON；默认只修正 值为1但没找到掩码 -> 0",
    )
    parser.add_argument(
        "--sync-both-ways",
        action="store_true",
        help="双向同步：有掩码 -> 1，无掩码 -> 0。默认不启用，仅修正 1->0",
    )

    args = parser.parse_args()

    if args.restore_from_manifest:
        manifest_path = Path(args.restore_from_manifest).expanduser().resolve()
        if not manifest_path.exists():
            print(f"[错误] manifest 不存在: {manifest_path}", file=sys.stderr)
            sys.exit(2)

        restored, restored_items, errors = restore_from_manifest(
            manifest_path,
            overwrite=args.overwrite,
        )
        print("=" * 80)
        print("恢复完成")
        print("=" * 80)
        print(f"manifest: {manifest_path}")
        print(f"成功恢复文件数: {restored}")
        if restored_items:
            print("-" * 80)
            for x in restored_items[: args.print_limit]:
                print(x)
            if len(restored_items) > args.print_limit:
                print(f"... 还有 {len(restored_items) - args.print_limit} 条未显示。")
        if errors:
            print("-" * 80)
            print("恢复时的错误：")
            for e in errors:
                print(f"  - {e}")
        print("=" * 80)
        return

    if not args.root or not args.json:
        parser.error("审计模式下必须提供 --root 和 --json")

    root = Path(args.root).expanduser().resolve()
    json_path = Path(args.json).expanduser().resolve()
    report_out = Path(args.report_out).expanduser().resolve()
    quarantine_dir = Path(args.quarantine_dir).expanduser().resolve()

    if not root.exists() or not root.is_dir():
        print(f"[错误] root 目录不存在或不是目录: {root}", file=sys.stderr)
        sys.exit(2)

    if not json_path.exists() or not json_path.is_file():
        print(f"[错误] JSON 文件不存在: {json_path}", file=sys.stderr)
        sys.exit(2)

    try:
        mapping = load_json_mapping(json_path)
        report = audit_masks(root, mapping)
        save_json(report, report_out)

        if args.write_corrected_json:
            corrected_path = Path(args.write_corrected_json).expanduser().resolve()
            corrected_mapping, corrected_stats = build_corrected_mapping(
                original_mapping=mapping,
                report=report,
                sync_both_ways=args.sync_both_ways,
            )
            save_corrected_mapping(corrected_mapping, corrected_path)

            print("-" * 80)
            print("已生成纠正后的 JSON")
            print(f"输出路径: {corrected_path}")
            print(f"总例数: {corrected_stats['total_cases']}")
            print(f"保持不变: {corrected_stats['unchanged']}")
            print(f"1 -> 0 的数量: {corrected_stats['changed_1_to_0']}")
            print(f"0 -> 1 的数量: {corrected_stats['changed_0_to_1']}")

            if corrected_stats["changed_1_to_0"] > 0:
                print("1 -> 0 的前若干项：")
                for x in corrected_stats["changed_1_to_0_paths"][: args.print_limit]:
                    print(f"  - {x}")

            if corrected_stats["changed_0_to_1"] > 0:
                print("0 -> 1 的前若干项：")
                for x in corrected_stats["changed_0_to_1_paths"][: args.print_limit]:
                    print(f"  - {x}")

    except Exception as e:
        print(f"[错误] 扫描失败: {e}", file=sys.stderr)
        sys.exit(2)

    print(f"root 目录: {root}")
    print(f"JSON 文件: {json_path}")
    print(f"报告文件: {report_out}")
    print_summary(report, args.print_limit)

    if args.move_wrong_zero or args.copy_wrong_zero:
        mode = "move" if args.move_wrong_zero else "copy"
        manifest, errors = quarantine_wrong_zero_masks(
            report,
            root,
            quarantine_dir,
            mode=mode,
        )

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        manifest_path = quarantine_dir / f"manifest_{ts}.json"
        save_json(manifest, manifest_path)

        print(f"[{mode}] 已处理值为 0 但存在的掩码")
        print(f"隔离目录: {quarantine_dir}")
        print(f"manifest: {manifest_path}")
        print(f"成功处理文件数: {len(manifest['operations'])}")
        if errors:
            print("处理时的错误：")
            for e in errors:
                print(f"  - {e}")
    else:
        print("[dry-run] 未移动/复制任何文件。")
        print("如需更安全处理，可使用：")
        print("  --copy-wrong-zero     仅复制到隔离区")
        print("  --move-wrong-zero     移动到隔离区")
        print("恢复命令示例：")
        print("  --restore-from-manifest /path/to/manifest_xxx.json")


if __name__ == "__main__":
    main()