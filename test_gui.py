# -*- coding: utf-8 -*-
"""界面视觉自测: 用假控制器把每个页签截图下来, 不碰摄像头和屏幕。"""
import os
import sys
import threading

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PIL import ImageGrab                     # noqa: E402

import gui                                    # noqa: E402
from config import Config                     # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_gui-tabs")


class FakeSensor:
    cap = True

    def set_exposure(self, e):
        pass

    def read(self):
        class S:
            median = 84.0
        return S()

    def autotune_exposure(self):
        return -2.5


class FakeCtrl:
    sensor = FakeSensor()

    def __init__(self):
        self.yield_until = 0.0


cfg = Config()
latest = {"st": {"median": 84.0, "ema": 81.0, "target": 53.0, "brightness": 53,
                 "event": "steady"}}
stop = threading.Event()

app = gui.App(cfg, FakeCtrl(), stop, latest)
app.show()
app.root.attributes("-topmost", True)
app.root.update()
app.root.after(300)
app.root.update()

# 断续采样: 歇着的时候状态行要显示倒计时
latest["st"]["next"] = 12
app._poll()
print("状态行(等待中):", app.v_state.get())
assert "后看一眼" in app.v_state.get(), "倒计时没显示出来"
latest["st"].pop("next")
app._poll()
print("状态行(采样中):", app.v_state.get())

os.makedirs(OUT, exist_ok=True)
for i in range(3):
    app.nb.select(i)
    app.root.update_idletasks()
    app.root.update()
    app.root.lift()
    x, y = app.root.winfo_rootx(), app.root.winfo_rooty()
    w, h = app.root.winfo_width(), app.root.winfo_height()
    pad = 8
    img = ImageGrab.grab(bbox=(x - pad, y - pad - 30, x + w + pad, y + h + pad))
    name = os.path.join(OUT, f"tab{i}.png")
    img.save(name)
    print(f"tab{i}: {img.size} -> {name}")

app.root.destroy()