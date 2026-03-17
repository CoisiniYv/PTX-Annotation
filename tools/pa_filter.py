#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DICOM 胸部 X 光片 PA 位筛选工具（支持中英文识别）。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Tuple, Optional

try:
    import chardet
except ImportError:  # pragma: no cover - 仅在缺失依赖时走到
    chardet = None

import pydicom
from tqdm import tqdm


def decode_bytes_to_str(value) -> Optional[str]:
    """解码 DICOM 中的字节字符串，支持多种编码。"""
    if value is None:
        return None

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, bytes):
        for enc in ("utf-8", "gbk", "gb18030", "iso-8859-1"):
            try:
                return value.decode(enc).strip()
            except UnicodeDecodeError:
                pass

        if chardet is not None:
            try:
                detected = chardet.detect(value)
                if detected.get("encoding"):
                    return value.decode(detected["encoding"]).strip()
            except Exception:
                pass

    try:
        return str(value).strip()
    except Exception:
        return None


def get_view_position(dcm_path: Path) -> Optional[str]:
    """从 DICOM 文件中获取拍摄体位（View Position）。"""
    try:
        ds = pydicom.dcmread(
            dcm_path,
            specific_tags=[
                (0x0018, 0x5101),  # View Position
                (0x0008, 0x103E),  # Series Description
                (0x0008, 0x1030),  # Study Description
                (0x0018, 0x1030),  # Protocol Name
            ],
        )

        view_pos_tag = ds.get((0x0018, 0x5101), None)
        if view_pos_tag is not None:
            view_pos = decode_bytes_to_str(view_pos_tag.value)
            if view_pos:
                return view_pos

        protocol_name = ds.get((0x0018, 0x1030), None)
        if protocol_name is not None:
            proto = decode_bytes_to_str(protocol_name.value)
            if proto and any(
                keyword in proto.upper()
                for keyword in [
                    "PA",
                    "AP",
                    "LAT",
                    "LATERAL",
                    "前后",
                    "后前",
                    "正位",
                    "侧位",
                    "侧片",
                ]
            ):
                return proto

        series_desc = ds.get((0x0008, 0x103E), None)
        if series_desc is not None:
            desc = decode_bytes_to_str(series_desc.value)
            if desc and any(
                keyword in desc.upper()
                for keyword in [
                    "PA",
                    "AP",
                    "LAT",
                    "LATERAL",
                    "前后",
                    "后前",
                    "正位",
                    "侧位",
                    "侧片",
                ]
            ):
                return desc

        study_desc = ds.get((0x0008, 0x1030), None)
        if study_desc is not None:
            desc = decode_bytes_to_str(study_desc.value)
            if desc and any(
                keyword in desc.upper()
                for keyword in [
                    "PA",
                    "AP",
                    "LAT",
                    "LATERAL",
                    "前后",
                    "后前",
                    "正位",
                    "侧位",
                    "侧片",
                ]
            ):
                return desc

        ds = pydicom.dcmread(dcm_path)

        if hasattr(ds, "ViewPosition"):
            view_pos = decode_bytes_to_str(ds.ViewPosition)
            if view_pos:
                return view_pos

        if hasattr(ds, "ProtocolName"):
            proto = decode_bytes_to_str(ds.ProtocolName)
            if proto and any(
                keyword in proto.upper()
                for keyword in [
                    "PA",
                    "AP",
                    "LAT",
                    "LATERAL",
                    "前后",
                    "后前",
                    "正位",
                    "侧位",
                    "侧片",
                ]
            ):
                return proto

        if hasattr(ds, "SeriesDescription"):
            desc = decode_bytes_to_str(ds.SeriesDescription)
            if desc and any(
                keyword in desc.upper()
                for keyword in [
                    "PA",
                    "AP",
                    "LAT",
                    "LATERAL",
                    "前后",
                    "后前",
                    "正位",
                    "侧位",
                    "侧片",
                ]
            ):
                return desc

        if hasattr(ds, "StudyDescription"):
            desc = decode_bytes_to_str(ds.StudyDescription)
            if desc and any(
                keyword in desc.upper()
                for keyword in [
                    "PA",
                    "AP",
                    "LAT",
                    "LATERAL",
                    "前后",
                    "后前",
                    "正位",
                    "侧位",
                    "侧片",
                ]
            ):
                return desc

        if hasattr(ds, "ImageComments"):
            comments = decode_bytes_to_str(ds.ImageComments)
            if comments and any(
                keyword in comments.upper()
                for keyword in [
                    "PA",
                    "AP",
                    "LAT",
                    "LATERAL",
                    "前后",
                    "后前",
                    "正位",
                    "侧位",
                    "侧片",
                ]
            ):
                return comments

        return None

    except Exception as e:
        print(f"读取文件失败 {dcm_path}: {e}")
        return None


def is_pa_view(view_position: str) -> bool:
    """判断是否为 PA 位（后前位）。"""
    if not view_position:
        return False

    view_upper = view_position.upper().replace(" ", "")

    pa_indicators = [
        "PA",
        "P-A",
        "POSTEROANTERIOR",
        "POSTERO-ANTERIOR",
        "CHESTPA",
        "CHEST_PA",
        "CXRPA",
    ]

    pa_chinese_indicators = [
        "胸部后前位",
        "后前位",
        "胸部正位",
        "正位",
        "胸片后前位",
        "胸正位",
        "站立位胸片",
        "胸片正位",
        "胸片(后前位)",
        "胸部X线(后前位)",
    ]

    ap_indicators = [
        "AP",
        "A-P",
        "ANTEROPOSTERIOR",
        "ANTERO-POSTERIOR",
        "CHESTAP",
        "CHEST_AP",
        "CXRAP",
    ]

    ap_chinese_indicators = [
        "胸部前后位",
        "前后位",
        "床旁",
        "卧位",
        "床边",
        "移动",
        "AP位",
        "前后",
    ]

    lat_indicators = [
        "LAT",
        "LATERAL",
        "LLAT",
        "RLAT",
        "LEFTLATERAL",
        "RIGHTLATERAL",
        "L-LAT",
        "R-LAT",
        "RL",
        "LL",
        "RLD",
        "LLD",
        "LAO",
        "RAO",
        "LPO",
        "RPO",
        "OBLIQUE",
        "DECUBITUS",
    ]

    lat_chinese_indicators = [
        "侧位",
        "左侧位",
        "右侧位",
        "侧片",
        "侧位胸片",
        "侧胸片",
        "左侧",
        "右侧",
    ]

    for ap in ap_indicators:
        if ap in view_upper:
            return False

    for ap_cn in ap_chinese_indicators:
        if ap_cn in view_position:
            return False

    for lat in lat_indicators:
        if lat in view_upper:
            return False

    for lat_cn in lat_chinese_indicators:
        if lat_cn in view_position:
            return False

    for pa in pa_indicators:
        if pa in view_upper:
            return True

    for pa_cn in pa_chinese_indicators:
        if pa_cn in view_position:
            return True

    if (
        "胸部" in view_position
        or "胸片" in view_position
        or "CHEST" in view_upper
    ):
        ap_related = ["卧位", "床旁", "床边", "移动", "AP", "前后位"]
        lat_related = ["侧位", "侧片", "LAT"]
        if (
            not any(ap_word in view_position for ap_word in ap_related)
            and not any(lat_word in view_position for lat_word in lat_related)
            and "LAT" not in view_upper
        ):
            return True

    return False


def scan_dicom_files(source_dir: Path) -> List[Path]:
    """扫描目录下所有 DICOM 文件。"""
    dicom_extensions = {".dcm", ".dicom", ".DCM", ".DICOM"}
    dicom_files: List[Path] = []

    print(f"正在扫描目录: {source_dir}")
    for ext in dicom_extensions:
        dicom_files.extend(source_dir.rglob(f"*{ext}"))

    for file_path in source_dir.rglob("*"):
        if file_path.is_file() and not file_path.suffix:
            try:
                with open(file_path, "rb") as f:
                    header = f.read(132)
                    if len(header) >= 132 and header[128:132] == b"DICM":
                        dicom_files.append(file_path)
            except Exception:
                continue

    dicom_files = list(dict.fromkeys(dicom_files))

    print(f"扫描完成，找到 {len(dicom_files)} 个文件")
    return dicom_files


def filter_pa_views(
    dicom_files: List[Path],
) -> Tuple[List[Path], List[Tuple[Path, Optional[str]]]]:
    """筛选 PA 位的 DICOM 文件。"""
    pa_files: List[Path] = []
    all_files_info: List[Tuple[Path, Optional[str]]] = []

    print("\n正在分析 DICOM 文件...")
    for dcm_path in tqdm(dicom_files, desc="读取 DICOM 元数据"):
        view_pos = get_view_position(dcm_path)
        all_files_info.append((dcm_path, view_pos))

        if len(all_files_info) <= 10:
            print(f"调试 - 文件: {dcm_path.name}")
            print(f"      识别结果: {view_pos}")
            print(f"      是否 PA 位? {is_pa_view(view_pos)}")

        if is_pa_view(view_pos):
            pa_files.append(dcm_path)

    return pa_files, all_files_info


def copy_pa_files(pa_files: List[Path], source_dir: Path, target_dir: Path):
    """复制 PA 位 DICOM 文件到目标目录，保持原有目录结构。"""
    if not pa_files:
        print("未找到符合条件的 PA 位文件")
        return

    print(f"\n找到 {len(pa_files)} 个 PA 位文件，开始复制...")

    target_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    failed_count = 0

    for src_path in tqdm(pa_files, desc="复制文件"):
        try:
            relative_path = src_path.relative_to(source_dir)
            dest_path = target_dir / relative_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            if src_path != dest_path:
                shutil.copy2(src_path, dest_path)
                success_count += 1

        except Exception as e:
            print(f"复制文件失败 {src_path}: {e}")
            failed_count += 1

    print(f"\n复制完成！成功复制 {success_count} 个文件")
    if failed_count > 0:
        print(f"失败 {failed_count} 个文件")
    print(f"文件已保存到: {target_dir}")


def move_files_preserving_structure(
    files: List[Path],
    source_dir: Path,
    target_dir: Path,
):
    """移动文件到目标目录，保持原有目录结构。"""
    if not files:
        print("未找到需要移动的文件")
        return

    print(f"\n找到 {len(files)} 个文件需要移动，开始移动...")

    target_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    failed_count = 0

    for src_path in tqdm(files, desc="移动文件"):
        try:
            relative_path = src_path.relative_to(source_dir)
            dest_path = target_dir / relative_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            if src_path != dest_path:
                shutil.move(str(src_path), str(dest_path))
                success_count += 1

        except Exception as e:
            print(f"移动文件失败 {src_path}: {e}")
            failed_count += 1

    print(f"\n移动完成！成功移动 {success_count} 个文件")
    if failed_count > 0:
        print(f"失败 {failed_count} 个文件")
    print(f"文件已移动到: {target_dir}")


def generate_report(
    all_files_info: List[Tuple[Path, Optional[str]]],
    pa_files: List[Path],
    report_path: Path,
    source_dir: Path,
):
    """生成筛选报告。"""
    pa_set = set(pa_files)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("DICOM 文件筛选报告\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"源目录: {source_dir}\n")
        f.write(f"总文件数: {len(all_files_info)}\n")
        f.write(f"PA 位文件数: {len(pa_files)}\n")
        f.write(f"其他体位文件数: {len(all_files_info) - len(pa_files)}\n\n")

        from collections import Counter

        view_counts = Counter()
        for _, view_pos in all_files_info:
            if view_pos:
                view_counts[view_pos] += 1

        f.write("各类拍摄体位统计:\n")
        f.write("-" * 30 + "\n")
        for view_pos, count in view_counts.most_common():
            f.write(f"{view_pos:<25} : {count:>4} 个\n")

        f.write("\n\nPA 位文件列表\n")
        f.write("-" * 50 + "\n")
        for file_path, view_pos in all_files_info:
            if file_path in pa_set:
                relative_path = file_path.relative_to(source_dir)
                f.write(f"[PA] {relative_path}\n")
                f.write(f"     View Position: {view_pos}\n")

        f.write("\n\n非 PA 位文件列表\n")
        f.write("-" * 50 + "\n")
        for file_path, view_pos in all_files_info:
            if file_path not in pa_set and view_pos:
                relative_path = file_path.relative_to(source_dir)
                f.write(f"[排除] {relative_path}\n")
                f.write(f"       View Position: {view_pos}\n")

        files_no_view = [(f, v) for f, v in all_files_info if f not in pa_set and not v]
        if files_no_view:
            f.write("\n\n未识别到 View Position 的文件\n")
            f.write("-" * 50 + "\n")
            for file_path, _ in files_no_view:
                relative_path = file_path.relative_to(source_dir)
                f.write(f"[未知] {relative_path}\n")

    print(f"\n筛选报告已保存到: {report_path}")
    print(f"报告包含 {len(all_files_info)} 个文件的详细信息")


def main():
    """CLI 入口。"""
    import argparse

    parser = argparse.ArgumentParser(
        description="筛选 PA 位（后前位）的胸部 X 光 DICOM 文件，支持中英文识别",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s -s /path/to/source -t /path/to/target
  %(prog)s -s /path/to/source -t /path/to/target --move-excluded /path/to/excluded
  %(prog)s -s /path/to/source -t /path/to/target --report
  %(prog)s -s /path/to/source -t /path/to/target --dry-run
  %(prog)s -s /path/to/source -t /path/to/target --debug

注意事项:
  - 支持中文编码: GBK、GB18030、UTF-8
  - 支持中英文混合的 View Position
  - 自动识别胸部后前位、正位等表述
  - 优先读取标准 ViewPosition(0018,5101)，若缺失再依次检查 ProtocolName、SeriesDescription、StudyDescription
        """,
    )

    parser.add_argument("-s", "--source", type=str, required=True, help="源 DICOM 文件目录路径")
    parser.add_argument(
        "-t",
        "--target",
        type=str,
        required=False,
        help="目标导出目录路径（用于存放 PA 位文件，若不指定则不复制）",
    )
    parser.add_argument(
        "--move-excluded",
        type=str,
        help="将非 PA 位文件移动到指定目录（保留目录结构）",
    )
    parser.add_argument("--report", action="store_true", help="生成筛选报告")
    parser.add_argument("--dry-run", action="store_true", help="仅扫描分析，不复制/移动文件")
    parser.add_argument("--debug", action="store_true", help="显示调试信息")

    args = parser.parse_args()

    source_dir = Path(args.source).resolve()
    target_dir = Path(args.target).resolve() if args.target else None

    if not source_dir.exists():
        print(f"错误: 源目录不存在: {source_dir}")
        return

    if target_dir and source_dir == target_dir:
        print("错误: 源目录和目标目录不能相同")
        return

    move_excluded_dir = None
    if args.move_excluded:
        move_excluded_dir = Path(args.move_excluded).resolve()
        if move_excluded_dir == source_dir:
            print("错误: 排除文件的移动目标目录不能与源目录相同")
            return
        if target_dir and move_excluded_dir == target_dir:
            print("错误: 排除文件的移动目标目录不能与 PA 文件目标目录相同")
            return

    if not target_dir and not move_excluded_dir and not args.report:
        print("提示: 未指定任何输出操作（-t 或 --move-excluded 或 --report）")
        print("      程序将仅进行扫描和统计")

    print("=" * 60)
    print("DICOM 胸部 X 光片 PA 位筛选工具（支持中文识别）")
    print("=" * 60)
    print(f"源目录: {source_dir}")
    if target_dir:
        print(f"PA 文件目标目录: {target_dir}")
    else:
        print("PA 文件目标目录: (未指定，跳过复制)")

    if move_excluded_dir:
        print(f"非 PA 文件移动目录: {move_excluded_dir}")
    print("-" * 60)

    print("正在扫描 DICOM 文件...")
    dicom_files = scan_dicom_files(source_dir)

    if not dicom_files:
        print("未找到任何 DICOM 文件")
        return

    print(f"找到 {len(dicom_files)} 个 DICOM 文件")

    pa_files, all_files_info = filter_pa_views(dicom_files)
    pa_set = set(pa_files)
    excluded_files = [f for f, _ in all_files_info if f not in pa_set]

    print("\n" + "=" * 60)
    print("筛选结果统计")
    print(f"总文件数: {len(all_files_info)}")
    print(f"PA 位文件数: {len(pa_files)}")
    print(f"其他体位文件数: {len(excluded_files)}")
    print("=" * 60)

    from collections import Counter

    view_counts = Counter()
    for _, view_pos in all_files_info:
        if view_pos:
            view_counts[view_pos] += 1

    print("\n拍摄体位分布:")
    print("-" * 40)
    for view_pos, count in view_counts.most_common(20):
        percentage = (count / len(all_files_info)) * 100
        status = "PA" if is_pa_view(view_pos) else "排除"
        print(f"{status:<4} {view_pos:<25} : {count:>4} 个({percentage:>5.1f}%)")

    if len(view_counts) > 20:
        print(f"... 还有 {len(view_counts) - 20} 种其他体位")

    if args.report:
        report_dir = target_dir if target_dir else (move_excluded_dir if move_excluded_dir else source_dir)
        report_path = report_dir / "pa_filter_report.txt"
        report_dir.mkdir(parents=True, exist_ok=True)
        generate_report(all_files_info, pa_files, report_path, source_dir)

    if not args.dry_run:
        if target_dir and pa_files:
            print(f"\n发现 {len(pa_files)} 个 PA 位文件")
            print("\n前 5 个将要复制的文件:")
            for i, file_path in enumerate(pa_files[:5], 1):
                print(f"{i}. {file_path.relative_to(source_dir)}")

            if len(pa_files) > 5:
                print(f"... 还有 {len(pa_files) - 5} 个文件")

            response = input("是否开始复制 PA 文件? [Y/n]: ")
            if response.lower() != "n":
                copy_pa_files(pa_files, source_dir, target_dir)
            else:
                print("PA 文件复制操作已取消")
        elif target_dir:
            print("\n未找到符合条件的 PA 位文件")
            if not args.debug:
                print("提示: 可使用 --debug 参数查看详细的识别过程")

        if move_excluded_dir and excluded_files:
            print(f"\n发现 {len(excluded_files)} 个非 PA 位文件")
            print("\n前 5 个将要移动的文件:")
            for i, file_path in enumerate(excluded_files[:5], 1):
                print(f"{i}. {file_path.relative_to(source_dir)}")

            if len(excluded_files) > 5:
                print(f"... 还有 {len(excluded_files) - 5} 个文件")

            response = input(
                f"是否开始移动非 PA 文件到 {move_excluded_dir}? [Y/n]: "
            )
            if response.lower() != "n":
                move_files_preserving_structure(excluded_files, source_dir, move_excluded_dir)
            else:
                print("非 PA 文件移动操作已取消")
        elif move_excluded_dir:
            print("\n未找到非 PA 位文件，无需移动")
    else:
        print("\n【dry-run 模式】未执行文件复制/移动操作")
        print("提示: 去掉 --dry-run 参数即可执行实际操作")


if __name__ == "__main__":
    main()
