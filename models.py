"""数据结构与枚举：统一管理核心数据模型。"""
from dataclasses import dataclass
from enum import Enum, auto


@dataclass
class ImageEntry:
    case_name: str
    orig_path: str
    mask_path: str
    filename: str
    has_mask: bool
    has_pneumothorax: int = 0


class ToolType(Enum):
    ERASER = auto()
    BRUSH = auto()
    POLYGON = auto()


class ScanMode(Enum):
    CT_SEQUENCE = auto()
    XRAY_SINGLE = auto()
