# -*- coding: utf-8 -*-
"""环境光 -> 屏幕亮度 的映射与控制环。"""
from __future__ import annotations

import csv
import datetime as dt
import os
import threading
import time

from brightness import make_backend
from camera import AmbientSensor, CameraBusy

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brightness-log.csv")


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lum_to_pct(median: float, cfg) -> float:
    """归一化灰度 -> 亮度百分比。

    灰度用"参考曝光下"的中位数, 先线性映射到 0..1, 再用 gamma 调节低光段:
    gamma < 1 让暗环境更亮一些(默认 0.55), gamma = 1 为线性。
    """
    bp, wp = cfg.black_point, max(cfg.black_point + 1, cfg.white_point)
    t = clamp((median - bp) / (wp - bp), 0.0, 1.0)
    if cfg.gamma != 1.0:
        t = t ** cfg.gamma
    lo, hi = cfg.min_brightness, cfg.max_brightness
    hour = dt.datetime.now().hour
    if hour >= 21 or hour < 7:      # 夜里允许压得更低
        lo = min(lo, cfg.night_min_brightness)
    return lo + t * (hi - lo)


class Controller:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.sensor = AmbientSensor(cfg)
        self.backend, self.backend_name = make_backend()
        self.ema: float | None = None
        self.recent: list[float] = []
        self.last_set: int | None = None
        self.last_change = 0.0
        self.last_range = 0.0
        self.pending = 0
        self.manual_until = 0.0
        self.yield_until = 0.0
        self.bad_run = 0
        self.warm = 0
        self._init_log()

    # ---------- 日志 ----------
    def _init_log(self) -> None:
        if not os.path.exists(LOG_PATH):
            with open(LOG_PATH, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(
                    ["time", "median_raw", "median_norm", "sat", "ema", "target",
                     "brightness", "exposure", "event"]
                )

    def _log(self, sample, norm, target, brightness, event) -> None:
        try:
            with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    f"{sample.median:.1f}" if sample else "",
                    f"{norm:.1f}" if norm is not None else "",
                    f"{sample.sat_ratio:.3f}" if sample else "",
                    f"{self.ema:.1f}" if self.ema is not None else "",
                    f"{target:.1f}" if target is not None else "",
                    brightness if brightness is not None else "",
                    f"{self.cfg.exposure:.1f}" if sample else "",
                    event,
                ])
        except Exception:
            pass

    # ---------- 启动 ----------
    def start(self, retune: bool = False) -> None:
        self.sensor.open()
        if retune:
            self.cfg.exposure = self.sensor.autotune_exposure()
            self.cfg.exposure_ref = self.cfg.exposure
            self.cfg.save()
        self.last_set = self.backend.get()
        self.last_change = 0.0

    # ---------- 自动换挡 ----------
    def _autorange(self, sample, now: float) -> str:
        if now - self.last_range < 10.0:
            return ""
        exp = self.cfg.exposure
        # 只在画面"整体"确实过亮时才降曝光: 中位数 > 215 并且真有不少过曝像素。
        # 只看过曝比例会出错——背后有窗/灯时少数像素常年过曝, 曝光会被一路拽到最暗,
        # 而曝光一变暗, 归一化又把读数放大, 屏幕反而被顶到最亮。
        over = sample.median > 215 and sample.sat_ratio > 0.15
        if over and exp > -7.0:
            self.sensor.set_exposure(max(-7.0, exp - 0.5))
            self.last_range = now
            return "range-down"
        if sample.median < 6 and exp < -2.5:
            self.sensor.set_exposure(min(-2.5, exp + 0.5))   # 别再往上, 长曝光会掉帧
            self.last_range = now
            return "range-up"
        return ""

    # ---------- 单步 ----------
    def tick(self, apply: bool = True) -> dict:
        if self.cfg.paused:
            return {"paused": True}

        sample = self.sensor.read()
        range_ev = self._autorange(sample, time.time())
        if range_ev:
            # 换挡后驱动要几帧才真正生效, 立刻读会拿到旧画面, 归一化会瞬间翻倍
            time.sleep(0.4)
            for _ in range(3):
                self.sensor.read()
            sample = self.sensor.read()

        # 全黑帧(摄像头刚启动/被挡住)不可信: 直接丢, 不能进滤波也不能据此压亮度
        if sample.median < 1.0:
            cur = self.backend.get()
            self._log(sample, 0.0, float(cur), cur, "no-data")
            return {"median": 0.0, "ema": self.ema, "target": float(cur),
                    "brightness": cur, "event": "no-data"}

        # 归一化到参考曝光: 曝光每 +1 档画面亮一倍
        norm = sample.median * (2.0 ** (self.cfg.exposure_ref - sample.exposure))
        self.recent.append(norm)
        if len(self.recent) > 5:
            self.recent.pop(0)
        norm = sorted(self.recent)[len(self.recent) // 2]   # 中值滤波, 压制偶发暗帧
        a = clamp(self.cfg.smoothing_alpha, 0.02, 1.0)
        self.ema = norm if self.ema is None else (1 - a) * self.ema + a * norm

        target = lum_to_pct(self.ema, self.cfg)
        now = time.time()
        cur = self.backend.get()
        event = range_ev

        if not apply:      # 只测不调(用于 once/test)
            self._log(sample, norm, target, cur, "probe")
            return {"median": norm, "ema": self.ema, "target": target,
                    "brightness": cur, "event": "probe"}

        # 用户手动调过亮度(比如按 Fn 键) -> 尊重用户, 暂停一会儿
        if self.last_set is not None and abs(cur - self.last_set) >= 6 and \
                now - self.manual_until > self.cfg.manual_override_minutes * 60:
            self.manual_until = now + self.cfg.manual_override_minutes * 60
            self.last_set = cur
            event = "manual-override"

        if now < self.manual_until:
            self._log(sample, norm, target, cur, event or "hold")
            return {"median": norm, "ema": self.ema, "target": target,
                    "brightness": cur, "held": True, "event": event}

        want = abs(target - cur) > self.cfg.deadband
        self.pending = self.pending + 1 if want else 0
        # 变暗要多确认几次(灯光/摄像头被抢都会造成短暂假暗), 变亮反应快一些
        need = 5 if target < cur - 10 else 2
        if want and self.pending >= need and \
                now - self.last_change >= self.cfg.min_change_interval:
            step = clamp(target - cur, -self.cfg.max_step, self.cfg.max_step)
            new = int(round(clamp(cur + step, self.cfg.min_brightness, self.cfg.max_brightness)))
            if new != cur:
                self.backend.set(new)
                self.last_set = new
                self.last_change = now
                event = event or "adjust"
                cur = new

        self._log(sample, norm, target, cur, event or "steady")
        return {"median": norm, "ema": self.ema, "target": target,
                "brightness": cur, "event": event}

    # ---------- 主循环 ----------
    def run(self, stop: threading.Event, on_update=None) -> None:
        backoff = 1.0
        while not stop.is_set():
            if time.time() < self.yield_until:
                # 用户要让出摄像头(开会/拍照): 释放设备, 期间不改亮度
                if self.sensor.cap is not None:
                    try:
                        self.sensor.close()
                    except Exception:
                        pass
                if on_update:
                    left = int(self.yield_until - time.time())
                    on_update({"yield": left})
                stop.wait(2.0)
                continue
            # ---- 一轮: 开摄像头, 连采几帧, 然后关掉歇一会儿 ----
            burst = max(1, int(getattr(self.cfg, "burst_samples", 5)))
            busy = False
            for _ in range(burst):
                if stop.is_set():
                    break
                t0 = time.time()
                try:
                    if self.sensor.cap is None:
                        self.sensor.open()
                        # 刚打开摄像头的前几帧偏黑, 先丢掉, 否则会被当成"房间变暗"
                        self.warm = 1
                    if self.warm > 0:
                        self.warm -= 1
                        stop.wait(max(0.2, self.cfg.sample_interval))
                        continue
                    st = self.tick()
                    backoff = 1.0
                    if st.get("event") == "no-data":
                        self.bad_run += 1
                        if self.bad_run >= 10 and self.sensor.cap is not None:
                            # 连着读不到画面: 可能是被别的程序抢了摄像头, 重新打开自愈
                            try:
                                self.sensor.close()
                            except Exception:
                                pass
                            self.bad_run = 0
                            self.recent.clear()
                            self.ema = None
                    else:
                        self.bad_run = 0
                    if on_update:
                        on_update(st)
                except CameraBusy as e:
                    busy = True
                    if on_update:
                        on_update({"error": str(e)})
                    try:
                        self.sensor.close()
                    except Exception:
                        pass
                    break
                except Exception as e:
                    if on_update:
                        on_update({"error": f"{type(e).__name__}: {e}"})
                    stop.wait(2.0)
                stop.wait(max(0.0, self.cfg.sample_interval - (time.time() - t0)))

            if busy:
                stop.wait(min(backoff, 30))
                backoff = min(backoff * 2, 30)

            # ---- 歇着: 摄像头关掉, 别人可以用, 指示灯也灭 ----
            if not getattr(self.cfg, "keep_camera_open", False):
                try:
                    self.sensor.close()
                except Exception:
                    pass
                self.warm = 0
                deadline = time.time() + max(2.0, float(self.cfg.probe_interval))
                while not stop.is_set() and time.time() < deadline:
                    if on_update:
                        on_update({"next": max(0, int(round(deadline - time.time())))})
                    stop.wait(min(1.0, max(0.05, deadline - time.time())))

    def close(self) -> None:
        try:
            self.sensor.close()
        except Exception:
            pass
        try:
            self.backend.close()
        except Exception:
            pass