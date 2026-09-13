"""PTX Annotation 打包入口。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "app.py"
ICON = ROOT / "icon1.ico"


def build(onefile: bool = False) -> None:
    mode_flag = "--onefile" if onefile else "--onedir"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        mode_flag,
        "--name",
        "PTX-Annotation",
    ]
    if ICON.exists():
        cmd.extend(["--icon", str(ICON)])
    cmd.append(str(ENTRY))
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="构建 PTX Annotation 桌面程序")
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="生成单文件程序；默认使用更易排错的 onedir 模式",
    )
    args = parser.parse_args()
    build(onefile=args.onefile)


if __name__ == "__main__":
    main()
