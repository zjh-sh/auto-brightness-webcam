# -*- coding: utf-8 -*-
"""用摄像头估计环境光。

关键点: 必须锁定曝光, 否则摄像头自动曝光会把画面"补"回正常亮度,
环境光变化就被抵消了, 读数毫无意义。

次级问题: 固定曝光只能覆盖有限动态范围。白天窗口会过曝、深夜会死黑,
所以这里做"自动换挡": 只在快过曝/快死黑时缓慢加减曝光, 并把读数按
2^(参考曝光-当前曝光) 归一到同一基准, 这样映射曲线不用跟着变。
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Sample:
    median: float        # ROI 灰度中位数 0-255, 抗高光干扰
    mean: float          # ROI 灰度均值
    sat_ratio: float     # 过曝像素比例
    dark_ratio: float    # 死黑像素比例
    exposure: float      # 本帧使用的曝光值
    ts: float


class CameraBusy(RuntimeError):
    pass


class AmbientSensor:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.cap: cv2.VideoCapture | None = None

    # ---------- 打开/关闭 ----------
    def open(self) -> None:
        self.close()
        cap = cv2.VideoCapture(self.cfg.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            raise CameraBusy("摄像头打不开(可能被微信/Teams/相机应用占用)")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cap = cap
        self._lock_exposure(self.cfg.exposure, self.cfg.gain)
        for _ in range(8):          # 丢弃启动阶段的不稳定帧
            cap.read()

    def _lock_exposure(self, exposure: float, gain: float = -1.0) -> None:
        assert self.cap is not None
        # DirectShow: 0.25 = 手动曝光, 0.75 = 自动
        self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
        self.cap.set(cv2.CAP_PROP_EXPOSURE, float(exposure))
        if gain >= 0:
            self.cap.set(cv2.CAP_PROP_GAIN, float(gain))
        for _ in range(4):
            self.cap.read()

    def set_exposure(self, exposure: float) -> None:
        self.cfg.exposure = exposure
        self._lock_exposure(exposure, self.cfg.gain)

    def close(self) -> None:
        if self.cap is not None:
            try:
                self.cap.release()
            finally:
                self.cap = None

    # ---------- 读数 ----------
    def _ensure(self) -> None:
        """单次调用(校准/测光/点一下看看)时自动开一下摄像头。"""
        if self.cap is None:
            self.open()

    def read(self) -> Sample:
        self._ensure()
        ok, frame = self.cap.read()
        if not ok or frame is None:
            raise CameraBusy("读帧失败")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        x1, y1, x2, y2 = self.cfg.roi
        roi = gray[int(h * y1):int(h * y2), int(w * x1):int(w * x2)]
        flat = roi.ravel()
        sat = float(np.count_nonzero(flat >= 250)) / flat.size
        dark = float(np.count_nonzero(flat <= 5)) / flat.size
        useful = flat[flat < 250]     # 去掉过曝像素, 避免窗外高光把结果拉高
        if useful.size < flat.size * 0.2:
            useful = flat
        return Sample(
            median=float(np.median(useful)),
            mean=float(np.mean(useful)),
            sat_ratio=sat,
            dark_ratio=dark,
            exposure=float(self.cfg.exposure),
            ts=time.time(),
        )

    # ---------- 自动找曝光 ----------
    def autotune_exposure(self, target: float = 70.0, lo: float = -10, hi: float = -2.5) -> float:
        """挑一个让当前环境落在量程中段的曝光值, 上下都留余量。"""
        self._ensure()
        best_exp, best_err = self.cfg.exposure, 1e9
        exp = lo
        while exp <= hi + 1e-6:
            self._lock_exposure(exp, self.cfg.gain)
            vals = [self.read() for _ in range(3)]
            med = float(np.median([v.median for v in vals]))
            sat = float(np.max([v.sat_ratio for v in vals]))
            err = abs(med - target) + (500 if sat > 0.05 else 0)
            if err < best_err:
                best_err, best_exp = err, exp
            exp += 0.5
        self.set_exposure(best_exp)
        return best_exp