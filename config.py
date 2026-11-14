# -*- coding: utf-8 -*-
"""配置读写。"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


@dataclass
class Config:
    # ---- 摄像头 ----
    camera_index: int = 0
    exposure: float = -4.0        # DirectShow 对数曝光, -4 ≈ 1/16 秒
    exposure_ref: float = -4.0    # 映射曲线的参考曝光, 自动换挡时用来归一化
    gain: float = -1.0            # -1 表示交给驱动 / 不强制
    roi: tuple = (0.28, 0.22, 0.72, 0.78)   # 取样区域 (x1, y1, x2, y2) 比例

    # ---- 亮度范围 ----
    min_brightness: int = 12
    max_brightness: int = 100
    night_min_brightness: int = 8

    # ---- 映射曲线 (灰度中位数为 0-255) ----
    black_point: float = 3.0      # 暗到这个灰度就取 min_brightness
    white_point: float = 320.0    # 亮到这个灰度就取 max_brightness (可 >255, 归一化后)
    gamma: float = 0.55           # <1 暗环境更亮, 1=线性, >1 更暗

    # ---- 控制节奏 ----
    sample_interval: float = 1.0  # 采样间隔(秒)
    smoothing_alpha: float = 0.25 # EMA 平滑系数, 越小越稳越慢
    deadband: float = 4.0         # 目标与当前相差小于该值(百分比)不动作
    max_step: float = 8.0         # 单次最大调整幅度(百分比)
    min_change_interval: float = 2.5   # 两次调整之间的最小间隔(秒)
    manual_override_minutes: float = 15.0  # 检测到用户手动调亮度后暂停多久

    # ---- 断续采样：看一会儿, 关上摄像头歇一会儿 ----
    burst_samples: int = 5        # 每轮连采几帧
    probe_interval: float = 20.0  # 两轮之间歇多久(秒), 歇的时候摄像头是关着的
    keep_camera_open: bool = False  # 调试用: 真的需要常开摄像头时才打开

    # ---- 行为 ----
    paused: bool = False
    autostart: bool = False

    def save(self) -> None:
        data = asdict(self)
        data["roi"] = list(self.roi)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                names = {f.name for f in fields(cls)}
                for k, v in data.items():
                    if k in names:
                        if k == "roi":
                            v = tuple(v)
                        setattr(cfg, k, v)
            except Exception:
                pass
        return cfg