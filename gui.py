# -*- coding: utf-8 -*-
"""主界面: 状态 + 设置。

全部用 tk.Canvas / tk.Label 自绘(圆角滑块、分段页签、开关、状态胶囊),
不套 ttk 主题, 所以不会有一堆灰扑扑的 90 年代控件。零额外依赖。
"""
from __future__ import annotations

import ctypes
import os
import queue
import time
import tkinter as tk
from tkinter import messagebox

BASE = os.path.dirname(os.path.abspath(__file__))
YAHEI = "Microsoft YaHei UI"

# ---- 配色(单色系 + 一个强调色, 别超过三种色相) ----
BG = "#ffffff"
CARD = "#f6f7f9"
BORDER = "#e6e8ee"
TEXT = "#1b1f24"
MUTED = "#6b7280"
FAINT = "#9ca3af"
ACCENT = "#2f6fed"
ACCENT_HOVER = "#255ac4"
TRACK = "#e3e6ec"
OK_BG, OK_FG = "#e7f5ec", "#12805c"
WARN_BG, WARN_FG = "#fff4e5", "#a25c00"
IDLE_BG, IDLE_FG = "#eef0f4", "#5b6270"

F_TITLE = (YAHEI, 15, "bold")
F_SUB = (YAHEI, 9)
F_BODY = (YAHEI, 10)
F_SMALL = (YAHEI, 9)
F_HUGE = (YAHEI, 30, "bold")
F_UNIT = (YAHEI, 11)
F_SECTION = (YAHEI, 10, "bold")

BTN_W = 22
WIN_W, WIN_H = 620, 660


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# --------------------------------------------------------------------- 控件
def _round_line(cv: tk.Canvas, x1: float, x2: float, y: float, w: int, color: str) -> None:
    """两端是圆的横线, 用来当滑块轨道/进度条。"""
    if x2 - x1 < 1:
        x2 = x1 + 1
    cv.create_line(x1, y, x2, y, width=w, fill=color, capstyle="round")


class Slider(tk.Frame):
    """自绘滑块: 细轨道 + 圆角填充 + 白色描边圆钮。"""

    def __init__(self, master, var: tk.DoubleVar, lo: float, hi: float,
                 res: float, fmt: str = "{:.0f}", width: int = 0) -> None:
        super().__init__(master, bg=BG)
        self.var, self.lo, self.hi, self.res, self.fmt = var, lo, hi, res, fmt
        self.cv = tk.Canvas(self, height=24, width=1, bg=BG, highlightthickness=0,
                            bd=0, cursor="hand2", takefocus=1)
        self.cv.pack(fill="x", expand=True)
        if width:
            self.cv.configure(width=width)
        self._drag = False
        self.cv.bind("<Configure>", lambda e: self._draw())
        self.cv.bind("<Button-1>", self._click)
        self.cv.bind("<B1-Motion>", self._click)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.cv.bind("<Left>", lambda e: self._nudge(-1))
        self.cv.bind("<Right>", lambda e: self._nudge(1))
        var.trace_add("write", lambda *a: self._draw())

    # -- 坐标换算
    def _span(self) -> tuple[float, float]:
        return 11.0, max(30.0, float(self.cv.winfo_width()) - 11.0)

    def _frac(self) -> float:
        if self.hi <= self.lo:
            return 0.0
        return min(1.0, max(0.0, (float(self.var.get()) - self.lo) / (self.hi - self.lo)))

    def _draw(self) -> None:
        cv = self.cv
        cv.delete("all")
        x1, x2 = self._span()
        y = 12
        _round_line(cv, x1, x2, y, 5, TRACK)
        x = x1 + (x2 - x1) * self._frac()
        if x > x1 + 0.5:
            _round_line(cv, x1, x, y, 5, ACCENT)
        cv.create_oval(x - 7, y - 7, x + 7, y + 7, fill="#ffffff", outline=ACCENT,
                       width=2)

    def _snap(self, v: float) -> float:
        v = round(v / self.res) * self.res
        return min(self.hi, max(self.lo, round(v, 6)))

    def _click(self, event) -> None:
        self._drag = True
        x1, x2 = self._span()
        f = min(1.0, max(0.0, (event.x - x1) / (x2 - x1)))
        self.var.set(self._snap(self.lo + f * (self.hi - self.lo)))

    def _release(self, _event=None) -> None:
        self._drag = False

    def _nudge(self, direction: int) -> None:
        self.var.set(self._snap(float(self.var.get()) + direction * self.res))


class Switch(tk.Canvas):
    """iOS 风格开关: 圆角胶囊 + 白圆点。"""

    W, H = 40, 22

    def __init__(self, master, var: tk.BooleanVar, command=None) -> None:
        super().__init__(master, width=self.W, height=self.H, bg=BG,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.var, self.command = var, command
        self._pos = 1.0 if var.get() else 0.0
        self._anim: str | None = None
        self.bind("<Button-1>", self._toggle)
        var.trace_add("write", lambda *a: self._animate())
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        w, h, r = self.W, self.H, self.H / 2
        bg = ACCENT if self._pos > 0.5 else "#cfd4dd"
        self.create_oval(0, 0, h, h, fill=bg, outline=bg)
        self.create_oval(w - h, 0, w, h, fill=bg, outline=bg)
        self.create_rectangle(h / 2, 0, w - h / 2, h, fill=bg, outline=bg)
        cx = r + (w - 2 * r) * self._pos
        pad = 3
        self.create_oval(cx - r + pad, pad, cx + r - pad, h - pad,
                         fill="#ffffff", outline="#ffffff")

    def _animate(self) -> None:
        if self._anim:
            try:
                self.after_cancel(self._anim)
            except Exception:
                pass
        target = 1.0 if self.var.get() else 0.0

        def step() -> None:
            diff = target - self._pos
            if abs(diff) < 0.06:
                self._pos = target
                self._draw()
                self._anim = None
                return
            self._pos += diff * 0.35
            self._draw()
            self._anim = self.after(12, step)

        step()

    def _toggle(self, _event=None) -> None:
        self.var.set(not self.var.get())
        if self.command:
            self.command()


class SegTabs(tk.Frame):
    """分段式页签(替代 ttk.Notebook): 当前项下面一条强调色短线。"""

    def __init__(self, master, titles: list[str], on_select) -> None:
        super().__init__(master, bg=BG)
        self.on_select = on_select
        self.index = 0
        self.items: list[tuple[tk.Label, tk.Canvas]] = []
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x")
        for i, t in enumerate(titles):
            cell = tk.Frame(row, bg=BG)
            cell.pack(side="left", padx=(0, 22))
            lbl = tk.Label(cell, text=t, font=F_BODY, bg=BG, fg=MUTED,
                           cursor="hand2", padx=2, pady=4)
            lbl.pack()
            bar = tk.Canvas(cell, height=2, width=1, bg=BG, highlightthickness=0, bd=0)
            bar.pack(fill="x")
            lbl.bind("<Button-1>", lambda e, i=i: self.select(i))
            bar.bind("<Button-1>", lambda e, i=i: self.select(i))
            self.items.append((lbl, bar))
        self._paint()

    def select(self, i: int) -> None:
        if i == self.index:
            self.on_select(i)
            return
        self.index = i
        self._paint()
        self.on_select(i)

    def _paint(self) -> None:
        for i, (lbl, bar) in enumerate(self.items):
            on = i == self.index
            lbl.configure(font=(YAHEI, 10, "bold") if on else F_BODY,
                          fg=TEXT if on else MUTED)
            bar.delete("all")
            if on:
                w = max(18, lbl.winfo_reqwidth())
                bar.create_line(0, 1, w, 1, width=2, fill=ACCENT, capstyle="round")
            else:
                bar.configure(height=2)


# ------------------------------------------------------------------- 界面
class _TabProxy:
    """兼容旧代码里的 app.nb.select(i) 写法。"""

    def __init__(self, app: "App") -> None:
        self._app = app

    def select(self, i: int) -> None:
        self._app.select_tab(i)

    def index(self) -> int:
        return self._app._segtabs.index


class App:
    """设置窗口。控制器在工作线程里跑, 这里只读状态、改配置。"""

    def __init__(self, cfg, ctrl, stop, latest, on_apply=None) -> None:
        self.cfg = cfg
        self.ctrl = ctrl
        self.stop = stop
        self.latest = latest
        self.on_apply = on_apply
        self.q: queue.Queue[str] = queue.Queue()
        self.vars: dict[str, tk.Variable] = {}
        self.rows: list[tuple] = []
        self._last_bright = -1
        self._placed = False
        self._frames: list[tk.Frame] = []

        enable_dpi_awareness()
        self.root = tk.Tk()
        self.root.title("摄像头自动亮度")
        self.root.configure(bg=BG)
        self.root.minsize(WIN_W + 40, 560)
        try:
            self.root.tk.call("tk", "scaling", self.root.winfo_fpixels("1i") / 72.0)
        except Exception:
            pass

        self._build()
        self.tabs = _TabProxy(self)
        self.nb = self.tabs          # 旧代码兼容
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self.root.after(400, self._poll)

    # ------------------------------------------------------------ 基础构件
    def _button(self, master, text: str, command, primary: bool = False,
                width: int = 0) -> tk.Button:
        kw = dict(text=text, command=command, font=F_BODY, bd=0,
                  relief="flat", highlightthickness=0, padx=16, pady=7,
                  cursor="hand2", activeforeground=("#ffffff" if primary else TEXT))
        if width:
            kw["width"] = width
        if primary:
            kw.update(bg=ACCENT, fg="#ffffff", activebackground=ACCENT_HOVER)
            hover = ACCENT_HOVER
        else:
            kw.update(bg=BG, fg=TEXT, activebackground=CARD)
            hover = "#f0f2f6"
        btn = tk.Button(master, **kw)
        btn.bind("<Enter>", lambda e: btn.configure(bg=hover))
        btn.bind("<Leave>", lambda e: btn.configure(bg=kw["bg"]))
        return btn

    def _card(self, master) -> tk.Frame:
        f = tk.Frame(master, bg=CARD, highlightthickness=1,
                     highlightbackground=BORDER, bd=0)
        return f

    def _build(self) -> None:
        pad = tk.Frame(self.root, bg=BG, padx=22, pady=16)
        pad.pack(fill="both", expand=True)

        # ---------- 标题 ----------
        head = tk.Frame(pad, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="摄像头自动亮度", font=F_TITLE, bg=BG, fg=TEXT
                 ).pack(side="left")
        tk.Label(head, text="用摄像头当环境光传感器", font=F_SUB, bg=BG, fg=FAINT
                 ).pack(side="left", padx=(10, 0), pady=(5, 0))
        self.pill = tk.Label(head, text="● 运行中", font=F_SMALL, bg=OK_BG,
                             fg=OK_FG, padx=10, pady=3)
        self.pill.pack(side="right")

        # ---------- 状态卡 ----------
        card = self._card(pad)
        card.pack(fill="x", pady=(14, 0))
        inner = tk.Frame(card, bg=CARD, padx=18, pady=14)
        inner.pack(fill="x")

        left = tk.Frame(inner, bg=CARD)
        left.pack(side="left", anchor="n")
        tk.Label(left, text="当前亮度", font=F_SMALL, bg=CARD, fg=MUTED
                 ).pack(anchor="w")
        num = tk.Frame(left, bg=CARD)
        num.pack(anchor="w")
        self.v_bright = tk.StringVar(value="--")
        tk.Label(num, textvariable=self.v_bright, font=F_HUGE, bg=CARD, fg=TEXT
                 ).pack(side="left")
        tk.Label(num, text="%", font=F_UNIT, bg=CARD, fg=MUTED
                 ).pack(side="left", anchor="s", pady=(0, 8), padx=(2, 0))
        self.bar = tk.Canvas(left, height=8, width=190, bg=CARD,
                             highlightthickness=0, bd=0)
        self.bar.pack(anchor="w", pady=(8, 0))
        self.bar.bind("<Configure>", lambda e: self._draw_bar(
            self._last_bright if self._last_bright >= 0 else 0))

        right = tk.Frame(inner, bg=CARD)
        right.pack(side="left", fill="x", expand=True, padx=(46, 0))
        self.v_env = tk.StringVar(value="--")
        self.v_target = tk.StringVar(value="--")
        self.v_state = tk.StringVar(value="正在启动…")
        for i, (name, var) in enumerate((("环境光", self.v_env),
                                         ("目标亮度", self.v_target),
                                         ("状态", self.v_state))):
            tk.Label(right, text=name, font=F_SMALL, bg=CARD, fg=MUTED,
                     width=6, anchor="w").grid(row=i, column=0, sticky="w", pady=3)
            tk.Label(right, textvariable=var, font=F_BODY, bg=CARD, fg=TEXT,
                     anchor="w").grid(row=i, column=1, sticky="w", pady=3)

        # ---------- 页签 ----------
        self._segtabs = SegTabs(pad, ["亮度", "摄像头", "其它"], self._on_tab)
        self._segtabs.pack(fill="x", pady=(18, 0))
        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(pad, bg=BG, pady=6)
        body.pack(fill="both", expand=True)
        self.body = body
        for i, builder in enumerate((self._tab_bright, self._tab_camera,
                                     self._tab_misc)):
            f = tk.Frame(body, bg=BG, pady=8)
            builder(f)
            self._frames.append(f)
        self._frames[0].pack(fill="both", expand=True)

        # ---------- 底部 ----------
        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=(6, 0))
        bar = tk.Frame(pad, bg=BG)
        bar.pack(fill="x", pady=(12, 0))
        self.v_hint = tk.StringVar(value="")
        tk.Label(bar, textvariable=self.v_hint, font=F_SMALL, bg=BG, fg=MUTED
                 ).pack(side="left")
        self._button(bar, "关闭到托盘", self.hide, width=12).pack(side="right")
        self._button(bar, "应用", self.apply, primary=True, width=10
                     ).pack(side="right", padx=(0, 8))

    # ------------------------------------------------------------- 表单行
    def _slider(self, parent, row: int, text: str, key: str, value,
                from_: float, to: float, res: float, fmt: str, hint: str = "") -> None:
        parent.columnconfigure(1, weight=1, minsize=170)
        parent.columnconfigure(3, minsize=176)
        var = tk.DoubleVar(value=value)
        self.vars[key] = var
        lbl = tk.Label(parent, text=text, font=F_BODY, bg=BG, fg=TEXT,
                       width=9, anchor="w")
        lbl.grid(row=row, column=0, sticky="w", pady=7)
        s = Slider(parent, var, from_, to, res, fmt)
        s.grid(row=row, column=1, sticky="we", padx=(6, 14))
        val = tk.Label(parent, text=fmt.format(value), font=F_BODY, bg=BG,
                       fg=TEXT, width=7, anchor="e")
        val.grid(row=row, column=2, sticky="e")
        hint_lbl = None
        if hint:
            hint_lbl = tk.Label(parent, text=hint, font=F_SMALL, bg=BG,
                                fg=FAINT, anchor="w")
            hint_lbl.grid(row=row, column=3, sticky="w", padx=(14, 0))

        def upd(*_):
            try:
                val.configure(text=fmt.format(var.get()))
            except Exception:
                pass

        var.trace_add("write", upd)
        self.rows.append((lbl, s, val, hint_lbl))

    def _tab_bright(self, f: tk.Frame) -> None:
        c = self.cfg
        self._slider(f, 0, "最低亮度", "min_brightness", c.min_brightness,
                     0, 60, 1, "{:.0f}%", "再暗也不低于此值")
        self._slider(f, 1, "最高亮度", "max_brightness", c.max_brightness,
                     40, 100, 1, "{:.0f}%", "最亮不超过此值")
        self._slider(f, 2, "夜间最低", "night_min_brightness", c.night_min_brightness,
                     0, 40, 1, "{:.0f}%", "21:00–7:00 生效")
        self._slider(f, 3, "曲线弯曲", "gamma", c.gamma, 0.3, 1.2, 0.05, "{:.2f}",
                     "小 = 暗环境更亮")
        self._slider(f, 4, "死区", "deadband", c.deadband, 1, 15, 0.5, "{:.1f}%",
                     "小于此偏差就不动")
        self._slider(f, 5, "单步上限", "max_step", c.max_step, 1, 20, 1, "{:.0f}%",
                     "每次最多调这么多")
        self._slider(f, 6, "调节间隔", "min_change_interval", c.min_change_interval,
                     0.5, 15, 0.5, "{:.1f}s", "两次调亮最短间隔")
        self._button(f, "按当前房间重新标定曲线…", self.calibrate
                     ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(16, 0))

    def _tab_camera(self, f: tk.Frame) -> None:
        c = self.cfg
        self._slider(f, 0, "曝光", "exposure", c.exposure, -9.0, -2.5, 0.5, "{:.1f}",
                     "越小画面越暗")
        self._slider(f, 1, "采样间隔", "sample_interval", c.sample_interval,
                     0.5, 5, 0.5, "{:.1f}s", "越小反应越快")
        self._slider(f, 2, "平滑系数", "smoothing_alpha", c.smoothing_alpha,
                     0.05, 1.0, 0.05, "{:.2f}", "小 = 更稳但更慢")
        self._slider(f, 3, "手动后暂停", "manual_override_minutes",
                     c.manual_override_minutes, 0, 60, 1, "{:.0f} 分",
                     "你按 Fn 调过后安静多久")
        self._slider(f, 4, "采样周期", "probe_interval", c.probe_interval,
                     5, 120, 5, "{:.0f}s", "多久看一眼，其余时间关掉")
        row = tk.Frame(f, bg=BG)
        row.grid(row=5, column=0, columnspan=4, sticky="w", pady=(16, 0))
        self._button(row, "重新测光（自动挑曝光）", self.retune).pack(side="left")
        self._button(row, "让出摄像头 30 分钟", self.yield_camera
                     ).pack(side="left", padx=(8, 0))
        tk.Label(f, text="开会 / 视频通话前点一下，程序会先退出摄像头",
                 font=F_SMALL, bg=BG, fg=FAINT
                 ).grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))

    def _switch_row(self, parent, row: int, text: str, desc: str,
                    var: tk.BooleanVar, command) -> None:
        sw = Switch(parent, var, command)
        sw.grid(row=row, column=0, sticky="w", pady=(4, 2))
        box = tk.Frame(parent, bg=BG)
        box.grid(row=row, column=1, sticky="w", padx=(12, 0), pady=(4, 2))
        tk.Label(box, text=text, font=F_BODY, bg=BG, fg=TEXT
                 ).pack(anchor="w")
        tk.Label(box, text=desc, font=F_SMALL, bg=BG, fg=FAINT
                 ).pack(anchor="w")

    def _tab_misc(self, f: tk.Frame) -> None:
        self.v_paused = tk.BooleanVar(value=not self.cfg.paused)
        self.v_auto = tk.BooleanVar(value=self.cfg.autostart)
        self._switch_row(f, 0, "启用自动调节", "关掉后只留托盘图标，不动屏幕亮度",
                         self.v_paused, self.toggle_enabled)
        self._switch_row(f, 1, "开机自动启动", "登录后自动在托盘里跑起来",
                         self.v_auto, self.toggle_autostart)

        tk.Frame(f, bg=BORDER, height=1).grid(row=2, column=0, columnspan=3,
                                              sticky="we", pady=14)
        for i, (text, cmd) in enumerate(
                (("打开运行日志", lambda: self._open("brightness-log.csv")),
                 ("打开配置文件", self._open_cfg),
                 ("恢复默认设置", self.reset_defaults))):
            self._button(f, text, cmd).grid(row=3 + i, column=0, columnspan=2,
                                            sticky="w", pady=2)
        tk.Label(f, text="配置保存在程序目录下的 config.json",
                 font=F_SMALL, bg=BG, fg=FAINT
                 ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(16, 0))

    def _on_tab(self, i: int) -> None:
        for n, fr in enumerate(self._frames):
            if n == i:
                fr.pack(fill="both", expand=True)
            else:
                fr.pack_forget()

    def select_tab(self, i: int) -> None:
        self._segtabs.select(i)

    # ------------------------------------------------------------- 动作
    def _open(self, name: str) -> None:
        try:
            os.startfile(os.path.join(BASE, name))
        except Exception as e:
            self.v_hint.set(f"打开失败: {e}")

    def _open_cfg(self) -> None:
        from config import CONFIG_PATH
        self._open(os.path.basename(CONFIG_PATH))

    def apply(self) -> None:
        c = self.cfg
        old_exp = c.exposure
        for key, var in self.vars.items():
            v = var.get()
            if key in ("min_brightness", "max_brightness", "night_min_brightness"):
                setattr(c, key, int(round(v)))
            else:
                setattr(c, key, float(v))
        if c.min_brightness >= c.max_brightness:
            c.min_brightness = max(5, c.max_brightness - 10)
        if c.night_min_brightness > c.min_brightness:
            c.night_min_brightness = c.min_brightness
        c.save()
        if abs(c.exposure - old_exp) > 1e-6:
            try:
                self.ctrl.sensor.set_exposure(c.exposure)
            except Exception:
                pass
        if self.on_apply:
            self.on_apply()
        self.v_hint.set(f"已保存 · {time.strftime('%H:%M:%S')}")

    def reset_defaults(self) -> None:
        from config import Config
        d = Config()
        for key, var in self.vars.items():
            var.set(getattr(d, key))
        self.v_hint.set("已填入默认值，点「应用」生效")

    def toggle_enabled(self) -> None:
        self.cfg.paused = not self.v_paused.get()
        self.cfg.save()
        self.v_hint.set("已" + ("暂停" if self.cfg.paused else "恢复") + "自动调节")

    def toggle_autostart(self) -> None:
        mode = "on" if self.v_auto.get() else "off"
        try:
            import subprocess
            import sys
            subprocess.run([sys.executable, os.path.join(BASE, "run.py"),
                            "autostart", mode], check=False,
                           creationflags=0x08000000)
            self.cfg.autostart = self.v_auto.get()
            self.cfg.save()
            self.v_hint.set("开机自启已" + ("开启" if mode == "on" else "关闭"))
        except Exception as e:
            self.v_hint.set(f"设置失败: {e}")

    def yield_camera(self) -> None:
        self.ctrl.yield_until = time.time() + 30 * 60
        self.v_hint.set("摄像头已让出 30 分钟，会自动恢复")

    def calibrate(self) -> None:
        self.v_hint.set("正在测光…")
        self.root.update_idletasks()
        try:
            exp = self.ctrl.sensor.autotune_exposure()
            self.ctrl.sensor.set_exposure(exp)
            self.cfg.exposure = exp
            self.cfg.exposure_ref = exp
            if "exposure" in self.vars:
                self.vars["exposure"].set(exp)
            vals = []
            for _ in range(6):
                vals.append(self.ctrl.sensor.read().median)
                time.sleep(1)
            vals.sort()
            med = vals[len(vals) // 2]
            bp = max(2.0, med * 0.35)
            wp = max(med * 2.2, bp + 20)
            if messagebox.askyesno(
                    "标定完成",
                    f"曝光 {exp:.1f}，当前环境读数 {med:.0f}\n"
                    f"建议曲线: 黑点 {bp:.0f} / 白点 {wp:.0f}\n\n写入并应用？"):
                self.cfg.black_point, self.cfg.white_point = bp, wp
                self.cfg.save()
                self.v_hint.set("曲线已更新")
            else:
                self.cfg.save()
                self.v_hint.set("曝光已更新，曲线未改")
        except Exception as e:
            self.v_hint.set(f"标定失败: {e}")

    def retune(self) -> None:
        self.v_hint.set("正在测光…")
        self.root.update_idletasks()
        try:
            exp = self.ctrl.sensor.autotune_exposure()
            self.ctrl.sensor.set_exposure(exp)
            self.cfg.exposure = exp
            self.cfg.exposure_ref = exp
            self.cfg.save()
            if "exposure" in self.vars:
                self.vars["exposure"].set(exp)
            self.v_hint.set(f"曝光已更新为 {exp:.1f}")
        except Exception as e:
            self.v_hint.set(f"测光失败: {e}")

    # ------------------------------------------------------------- 显示
    def show(self) -> None:
        if not self._placed:
            self._placed = True
            self.root.update_idletasks()
            w, h = max(self.root.winfo_reqwidth(), WIN_W), max(
                self.root.winfo_reqheight(), WIN_H)
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            self.root.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self) -> None:
        self.root.withdraw()

    def quit(self) -> None:
        self.stop_event_set()
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def stop_event_set(self) -> None:
        try:
            self.stop.set()
        except Exception:
            pass

    # ------------------------------------------------------------- 刷新
    def _pill(self, text: str, bg: str, fg: str) -> None:
        try:
            self.pill.configure(text=text, bg=bg, fg=fg)
        except Exception:
            pass

    def _draw_bar(self, pct: float) -> None:
        cv = self.bar
        w = max(40, cv.winfo_width())
        cv.delete("all")
        y = 4
        _round_line(cv, 4, w - 4, y, 7, TRACK)
        x = 4 + (w - 8) * max(0.0, min(1.0, pct / 100.0))
        if x > 5:
            _round_line(cv, 4, x, y, 7, ACCENT)

    def _poll(self) -> None:
        try:
            while True:
                cmd = self.q.get_nowait()
                if cmd == "show":
                    self.show()
                elif cmd == "quit":
                    self.quit()
                    return
        except queue.Empty:
            pass

        try:
            want = not self.cfg.paused
            if self.v_paused.get() != want:
                self.v_paused.set(want)
        except Exception:
            pass

        st = self.latest.get("st") or {}
        if "error" in st:
            self.v_state.set(f"错误 · {st['error'][:36]}")
            self._pill("● 出错", WARN_BG, WARN_FG)
        elif st.get("yield"):
            m, s = divmod(max(0, int(st["yield"])), 60)
            self.v_state.set(f"已让出摄像头 {m}:{s:02d}")
            self._pill("● 让出中", WARN_BG, WARN_FG)
        elif st.get("next") is not None:
            self.v_state.set(f"运行中 · {st['next']}s 后看一眼")
            self._pill("● 运行中", OK_BG, OK_FG)
        elif self.cfg.paused or st.get("paused"):
            self.v_state.set("已暂停")
            self._pill("● 已暂停", IDLE_BG, IDLE_FG)
        else:
            self.v_state.set("运行中")
            self._pill("● 运行中", OK_BG, OK_FG)

        if "median" in st:
            ema = st.get("ema")
            if ema is None:
                self.v_env.set(f"{st['median']:.0f}")
            else:
                self.v_env.set(f"{st['median']:.0f}（平滑 {ema:.0f}）")
            self.v_target.set(f"{st['target']:.0f}%")
        b = st.get("brightness")
        if b is not None:
            if b != self._last_bright:
                self._last_bright = b
                self.v_bright.set(f"{int(b)}")
            self._draw_bar(float(b))
        try:
            self.root.after(500, self._poll)
        except Exception:
            pass