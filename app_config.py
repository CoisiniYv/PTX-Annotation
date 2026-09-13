"""应用级常量与默认配置。"""

from __future__ import annotations

from dataclasses import dataclass

APP_NAME = "PTX Annotation"
APP_DISPLAY_NAME = "智能矫正终端 CT/X 融合版"
APP_VERSION = "0.2.0"

# 保留既有 QSettings 命名空间，避免升级后丢失用户设置。
QT_SETTINGS_ORGANIZATION = "CheXagent"
QT_SETTINGS_APPLICATION = "Penu"


@dataclass(frozen=True)
class PerformanceDefaults:
    ct_prefetch_count: int = 8
    ct_cross_count: int = 2
    ct_cache_max: int = 40
    xray_prefetch_count: int = 5
    xray_cache_max: int = 12
    xray_default_mask_format: str = "png"
    mask_pool_limit: int = 6


PERFORMANCE_DEFAULTS = PerformanceDefaults()
