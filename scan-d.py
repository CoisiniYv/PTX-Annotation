"""
目录扫描：独立的扫描逻辑与工作线程

本模块提供了两种扫描模式的实现：
1. CT序列模式 (ScanMode.CT_SEQUENCE)：一个文件夹代表一个病人
2. X光单张模式 (ScanMode.XRAY_SINGLE)：一个文件代表一个病例

注意：此文件已被 data_mixin.py 中的 _internal_scan_worker 替代
保留此文件仅用于参考和向后兼容
"""

import os

from PySide6.QtCore import QObject, Signal

from models import ScanMode
from utils import is_dual_folder_mode, load_pneumo_labels, natural_sort_key


def _scandir_dirs(path: str):
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_dir():
                    yield entry.name
    except Exception:
        return


def _scandir_files(path: str):
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_file():
                    yield entry.name
    except Exception:
        return


def _walk_scandir(top: str):
    stack = [top]
    while stack:
        root = stack.pop()
        dirs = []
        files = []
        try:
            with os.scandir(root) as it:
                for entry in it:
                    if entry.is_dir():
                        dirs.append(entry.name)
                    elif entry.is_file():
                        files.append(entry.name)
        except Exception:
            continue
        yield root, dirs, files
        for d in reversed(dirs):
            stack.append(os.path.join(root, d))


def scan_directory_process(scan_mode, orig_root, mask_root, status_map, result_queue):
    """
    独立进程扫描函数（已废弃，建议使用 data_mixin._internal_scan_worker）

    扫描原图目录，根据扫描模式识别病例：

    CT模式 (ScanMode.CT_SEQUENCE):
        - 扫描原图目录的顶层文件夹
        - 每个文件夹代表一个病人
        - 返回：(病人文件夹名, 是否已标注, 是否阳性)

    X光模式 (ScanMode.XRAY_SINGLE):
        - 递归扫描原图目录下的所有图片文件
        - 每个文件代表一个病例
        - 过滤掉PNG掩码文件（通过基名匹配）
        - 返回：(文件相对路径, 是否已标注, 是否阳性)

    参数：
        scan_mode: 扫描模式（CT_SEQUENCE 或 XRAY_SINGLE）
        orig_root: 原图根目录
        mask_root: 掩码根目录
        status_map: 病例状态字典 {case_name: "completed"/"todo"}
        result_queue: 结果队列，用于进程间通信
    """
    found_cases = []
    try:
        if scan_mode == ScanMode.CT_SEQUENCE:
            # ============================================================
            # CT模式：扫描顶层文件夹，每个文件夹是一个病人
            # ============================================================
            label_map = load_pneumo_labels([orig_root, mask_root])
            candidates = list(_scandir_dirs(orig_root))
            candidates.sort(key=natural_sort_key)

            for case_name in candidates:
                # 检查是否已标注
                is_completed = False
                if case_name in status_map:
                    is_completed = status_map[case_name] == "completed"
                else:
                    # 检查掩码文件夹下是否有PNG文件
                    mask_case_dir = os.path.join(mask_root, case_name)
                    if os.path.isdir(mask_case_dir):
                        masks = [
                            f
                            for f in _scandir_files(mask_case_dir)
                            if f.lower().endswith(".png")
                        ]
                        if len(masks) > 0:
                            is_completed = True

                # 检查是否阳性（标签JSON中任意切片标记为1）
                has_pneumo = False
                if label_map:
                    prefix = case_name + "/"
                    for rel_path, val in label_map.items():
                        if rel_path.startswith(prefix) and val == 1:
                            has_pneumo = True
                            break

                found_cases.append((case_name, is_completed, has_pneumo))
        else:
            # ============================================================
            # X光模式：递归扫描所有图片文件，每个文件是一个病例
            # ============================================================
            # 加载标签JSON
            label_dirs = [orig_root]
            if mask_root:
                label_dirs.append(mask_root)
            label_map = load_pneumo_labels(label_dirs)

            # 定义需要忽略的文件类型
            IGNORED_EXTS = {".py", ".json", ".txt", ".md", ".exe", ".dll", ".bat"}

            for root, dirs, files in _walk_scandir(orig_root):
                # 第一遍：建立原图基名集合
                # 目的：识别哪些PNG是掩码，避免误识别为原图
                base_names = set()
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext not in IGNORED_EXTS and ext != ".png":
                        base_names.add(f)  # 完整文件名
                        base_names.add(os.path.splitext(f)[0])  # 基名

                # 第二遍：筛选真正的原图文件
                for f in files:
                    ext = os.path.splitext(f)[1].lower()

                    # 跳过非图片文件
                    if ext in IGNORED_EXTS:
                        continue

                    # 关键过滤：PNG文件如果基名在原图集合中，说明是掩码
                    # 例如：0001.dcm存在，则0001.png被视为掩码
                    if ext == ".png":
                        stem = f[:-4]
                        if stem in base_names:
                            continue

                    # 构建文件路径和相对路径
                    full_src = os.path.join(root, f)
                    rel_src = os.path.relpath(full_src, orig_root).replace("\\", "/")

                    # 查询标签
                    has_pneumo = label_map.get(rel_src, 0)

                    # 检查掩码是否存在
                    has_mask = False
                    if mask_root:
                        # 双目录模式：支持两种命名方式
                        m1 = os.path.join(mask_root, rel_src)  # 完整路径
                        m2 = os.path.join(mask_root, rel_src + ".png")  # 追加.png
                        base_rel_src, _ = os.path.splitext(rel_src)
                        m3 = os.path.join(mask_root, base_rel_src + ".png")  # 替换扩展名
                        has_mask = (
                            os.path.exists(m1)
                            or os.path.exists(m2)
                            or os.path.exists(m3)
                        )
                    else:
                        # 单目录模式：掩码与原图在同一目录
                        m1 = full_src + ".png"
                        base_full, _ = os.path.splitext(full_src)
                        m2 = base_full + ".png"
                        has_mask = (os.path.exists(m1) and m1 != full_src) or (
                            os.path.exists(m2) and m2 != full_src
                        )

                    found_cases.append((rel_src, has_mask, has_pneumo == 1))

            # 自然排序
            found_cases.sort(key=lambda x: natural_sort_key(x[0]))
    finally:
        try:
            result_queue.put(found_cases)
        except:
            pass


class DirectoryScanWorker(QObject):
    """
    Qt线程工作器（已废弃，建议使用 data_mixin._internal_scan_worker）

    提供基于Qt信号槽的异步扫描功能
    与 scan_directory_process 功能相同，但使用Qt信号而非队列通信
    """
    finished = Signal(list, dict, bool)

    def __init__(self, scan_mode, orig_root, mask_root, status_map):
        super().__init__()
        self.scan_mode = scan_mode
        self.orig_root = orig_root
        self.mask_root = mask_root
        self.status_map = status_map or {}
        self._cancelled = False

    def cancel(self):
        """取消扫描"""
        self._cancelled = True

    def run(self):
        """
        执行扫描任务

        扫描完成后发出 finished 信号：
        - 参数1: found_cases 列表 [(case_name, is_completed, has_pneumo), ...]
        - 参数2: data_store 字典（保留用于扩展）
        - 参数3: canceled 布尔值（是否被取消）
        """
        found_cases = []
        data_store = {}
        canceled = False
        try:
            if self.scan_mode == ScanMode.CT_SEQUENCE:
                # ============================================================
                # CT模式：扫描顶层文件夹
                # ============================================================
                candidates = list(_scandir_dirs(self.orig_root))
                candidates.sort(key=natural_sort_key)

                for case_name in candidates:
                    # 检查是否取消
                    if self._cancelled:
                        canceled = True
                        break

                    # 检查是否已标注
                    is_completed = False
                    if case_name in self.status_map:
                        is_completed = self.status_map[case_name] == "completed"
                    else:
                        mask_case_dir = os.path.join(self.mask_root, case_name)
                        if os.path.isdir(mask_case_dir):
                            masks = [
                                f
                                for f in _scandir_files(mask_case_dir)
                                if f.lower().endswith(".png")
                            ]
                            if len(masks) > 0:
                                is_completed = True

                    found_cases.append((case_name, is_completed))
            else:
                # ============================================================
                # X光模式：扫描所有图片文件
                # ============================================================
                label_map = load_pneumo_labels([self.orig_root, self.mask_root])
                dual_mode = is_dual_folder_mode(self.orig_root, self.mask_root)

                for root, dirs, files in _walk_scandir(self.orig_root):
                    # 检查是否取消
                    if self._cancelled:
                        canceled = True
                        break

                    valid_files_in_dir = []
                    if dual_mode:
                        # 双目录模式：只处理PNG文件且有对应掩码
                        for f in files:
                            if not f.lower().endswith(".png"):
                                continue

                            full_src = os.path.join(root, f)
                            rel_src = os.path.relpath(full_src, self.orig_root).replace(
                                "\\", "/"
                            )
                            has_pneumo = label_map.get(rel_src, 0)

                            mask_path = os.path.join(self.mask_root, rel_src)
                            has_mask = os.path.exists(mask_path)
                            if not has_mask:
                                continue

                            valid_files_in_dir.append(
                                {
                                    "case_name": rel_src,
                                    "has_mask": has_mask,
                                    "has_pneumo": has_pneumo,
                                }
                            )
                    else:
                        # 单目录模式：处理所有非PNG图片文件
                        IGNORED_EXTS = {
                            ".jpg",
                            ".jpeg",
                            ".bmp",
                            ".py",
                            ".json",
                            ".txt",
                            ".md",
                            ".exe",
                            ".dll",
                            ".bat",
                        }

                        for f in files:
                            ext = os.path.splitext(f)[1].lower()

                            # 单目录模式下，所有PNG都是掩码，跳过
                            if ext in IGNORED_EXTS or ext == ".png":
                                continue

                            full_src = os.path.join(root, f)
                            rel_src = os.path.relpath(full_src, self.orig_root).replace(
                                "\\", "/"
                            )
                            has_pneumo = label_map.get(rel_src, 0)

                            # 支持两种掩码命名方式
                            # 方式A: 追加后缀 (12345.dcm -> 12345.dcm.png)
                            mask_p1 = os.path.join(self.mask_root, rel_src + ".png")

                            # 方式B: 替换扩展名 (12345.dcm -> 12345.png)
                            base_rel_src, _ = os.path.splitext(rel_src)
                            mask_p2 = os.path.join(
                                self.mask_root, base_rel_src + ".png"
                            )

                            has_mask = os.path.exists(mask_p1) or os.path.exists(
                                mask_p2
                            )

                            valid_files_in_dir.append(
                                {
                                    "case_name": rel_src,
                                    "has_mask": has_mask,
                                    "has_pneumo": has_pneumo,
                                }
                            )

                    # 将有效文件添加到结果列表
                    if valid_files_in_dir:
                        for item in valid_files_in_dir:
                            case_name = item["case_name"]
                            if case_name in self.status_map:
                                is_completed = self.status_map[case_name] == "completed"
                            else:
                                is_completed = item["has_mask"]
                            has_pneumo = item["has_pneumo"] == 1
                            found_cases.append((case_name, is_completed, has_pneumo))

                # 自然排序
                found_cases.sort(key=lambda x: natural_sort_key(x[0]))
        finally:
            # 发出完成信号
            self.finished.emit(found_cases, data_store, canceled)
