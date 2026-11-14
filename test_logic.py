# -*- coding: utf-8 -*-
"""离线测试: 1) 映射曲线 2) 调节节奏 3) 瞬变抗扰(脚本化假传感器)。"""
import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import control as ctl                       # noqa: E402
from camera import Sample                   # noqa: E402
from config import Config                   # noqa: E402

# 离线测试别写进真正的运行日志
import tempfile, os                        # noqa: E402
ctl.LOG_PATH = os.path.join(tempfile.gettempdir(), "ab-offline-test.csv")

cfg = Config()
cfg.black_point, cfg.white_point, cfg.gamma = 3.0, 320.0, 0.55

# ------------------------- 1. 映射曲线 -------------------------
print("映射曲线 (灰度 -> 亮度%):")
prev, ok = -1, True
for m in (0, 3, 10, 20, 40, 60, 90, 120, 160, 200, 260, 320, 400):
    p = ctl.lum_to_pct(m, cfg)
    print(f"  {m:5.0f} -> {p:5.1f}%")
    ok &= p >= prev and cfg.min_brightness - 0.1 <= p <= cfg.max_brightness + 0.1
    prev = p
print("单调且在范围内:", "OK" if ok else "FAIL")

# ------------------------- 2. 渐变节奏 -------------------------
cur, last_change, changes = 40, 0.0, 0
for i in range(60):
    env = 20 + (200 - 20) * i / 59
    target = ctl.lum_to_pct(env, cfg)
    if abs(target - cur) > cfg.deadband and i - last_change >= cfg.min_change_interval:
        cur = int(round(cur + max(-cfg.max_step, min(cfg.max_step, target - cur))))
        last_change = i
        changes += 1
print(f"\n环境光 20->200 (60 步): 调整 {changes} 次, 终值 {cur}%")

# ------------------------- 3. 瞬变抗扰 -------------------------
class FakeClock:
    t = 1000.0

    def time(self):
        return self.t

    def sleep(self, _s):      # 虚拟时钟: 换挡后的稳定等待直接跳过
        pass


class FakeSensor:
    def __init__(self, seq):
        self.seq = list(seq)
        self.i = 0

    def read(self):
        v = self.seq[min(self.i, len(self.seq) - 1)]
        self.i += 1
        return Sample(median=v, mean=v, sat_ratio=0.0, dark_ratio=0.0,
                      exposure=cfg.exposure, ts=0.0)

    def set_exposure(self, e):
        pass

    def close(self):
        pass


class FakeBackend:
    levels = 101

    def __init__(self, v=50):
        self.v = v
        self.history = [v]

    def get(self):
        return self.v

    def set(self, v):
        self.v = v
        self.history.append(v)

    def close(self):
        pass


def run_seq(seq, start=50):
    clock = FakeClock()
    real_time = ctl.time
    ctl.time = clock
    try:
        c = ctl.Controller(cfg)
        c.sensor = FakeSensor(seq)
        c.backend = FakeBackend(start)
        c.backend_name = "fake"
        c.last_set = start
        c.ema = None
        for _ in range(len(seq)):
            c.tick()
            clock.t += cfg.sample_interval
        return c.backend.history
    finally:
        ctl.time = real_time


print("\n瞬变抗扰 (基准灰度 72 -> 亮度 50%):")
h = run_seq([72] * 3 + [17, 17] + [72] * 6)
print(f"  手挡 2 帧:     亮度序列 {h}")
print("  判定:", "OK 未被带动" if max(h) == 50 and min(h) == 50 else "FAIL 被瞬变带偏")

h = run_seq([72] * 3 + [40] * 6)
print(f"  持续变暗:      亮度序列 {h}")
print("  判定:", "OK 已跟随" if h[-1] < 50 else "FAIL 没跟随")

h = run_seq([72] * 3 + [0, 0, 0] + [72] * 4)
print(f"  全黑帧(挡镜头): 亮度序列 {h}")
print("  判定:", "OK 未误降" if min(h) >= 50 else "FAIL 被黑帧带偏")