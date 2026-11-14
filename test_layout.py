# -*- coding: utf-8 -*-
"""客观量一下各页的列位置, 确认说明文字左边缘是否真的对齐。"""
import sys
import threading

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import gui                                    # noqa: E402
from config import Config                     # noqa: E402


class FakeCtrl:
    class sensor:
        cap = True

        @staticmethod
        def set_exposure(e):
            pass

    yield_until = 0.0

app = gui.App(Config(), FakeCtrl(), threading.Event(),
              {"st": {"median": 84.0, "ema": 81.0, "target": 53.0,
                      "brightness": 53, "event": "steady"}})
app.show()
app.root.update_idletasks()
app.root.update()

for i in range(3):
    app.nb.select(i)
    app.root.update_idletasks()
    app.root.update()
    frame = app.nb.nametowidget(app.nb.tabs()[i])
    print(f"=== tab{i}: {app.nb.tab(i, 'text').strip()} ===")
    rows = {}
    for ch in frame.winfo_children():
        info = ch.grid_info() if ch.winfo_manager() == "grid" else {}
        if not info:
            continue
        r, c = int(info["row"]), int(info["column"])
        try:
            txt = ch.cget("text")
        except Exception:
            txt = ""
        rows.setdefault(r, []).append((c, ch.winfo_class(), ch.winfo_rootx(),
                                       ch.winfo_width(), str(txt)[:22]))
    for r in sorted(rows):
        parts = sorted(rows[r])
        print(f" row{r}: " + " | ".join(f"c{c}:{cls} x={x} w={w} {t}"
                                        for c, cls, x, w, t in parts))

app.root.destroy()