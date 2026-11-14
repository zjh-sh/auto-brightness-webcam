# -*- coding: utf-8 -*-
"""笔记本摄像头自动亮度 —— 入口。

  python run.py tray           托盘常驻(推荐)
  python run.py run            前台运行, 控制台打印状态
  python run.py once           只测一次, 打印结果
  python run.py calibrate      重新测曝光/采样曲线
  python run.py test-camera    只测摄像头, 不动屏幕亮度
  python run.py autostart on|off
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from config import Config, CONFIG_PATH  # noqa: E402
from control import Controller  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

LOCK_PORT = 50777


def single_instance() -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        s.listen(1)
        single_instance._sock = s  # type: ignore[attr-defined]
        return True
    except OSError:
        return False


def instance_running() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", LOCK_PORT), timeout=0.4):
            return True
    except OSError:
        return False


def warn_if_running(cmd: str) -> bool:
    if instance_running():
        print(f"托盘实例正在运行，会抢走摄像头。请先在托盘菜单退出，再执行 {cmd}。")
        return True
    return False


# --------------------------- commands ---------------------------
def first_run_tune(cfg) -> None:
    """第一次运行(还没有 config.json)时, 按当前房间挑一次曝光。

    别人 clone 下来直接就能用, 不用先手动跑 calibrate。
    """
    from config import CONFIG_PATH
    if os.path.exists(CONFIG_PATH):
        return
    if instance_running():
        # 已有托盘实例占着摄像头, 这时候测出来的是它锁死的画面, 别信
        cfg.save()
        return
    try:
        from camera import AmbientSensor
        s = AmbientSensor(cfg)
        s.open()
        try:
            exp = s.autotune_exposure()
            exp = min(-2.5, max(-7.0, exp))
            s.set_exposure(exp)
            time.sleep(0.4)
            vals = sorted(s.read().median for _ in range(3))
            med = vals[len(vals) // 2]
            if med < 1.0:
                raise RuntimeError("读不到有效画面")
        finally:
            s.close()
        cfg.exposure = exp
        cfg.exposure_ref = exp
        cfg.save()
        print(f"首次运行: 自动选定曝光 {exp}（当前环境读数 {med:.0f}）")
    except Exception as e:
        cfg.save()
        print(f"首次自动测光失败({e})，先用默认曝光 {cfg.exposure}")


def cmd_run(args) -> int:
    if warn_if_running("run"):
        return 1
    cfg = Config.load()
    first_run_tune(cfg)
    ctrl = Controller(cfg)
    ctrl.start(retune=args.retune)
    stop = threading.Event()
    print(f"后端: {ctrl.backend_name} | 曝光: {cfg.exposure} | "
          f"档位: {getattr(ctrl.backend, 'levels', 101)} | Ctrl+C 退出")

    def show(st):
        if "error" in st:
            print(f"[{time.strftime('%H:%M:%S')}] 错误: {st['error']}")
        elif st.get("paused"):
            print(f"[{time.strftime('%H:%M:%S')}] 已暂停")
        else:
            print(f"[{time.strftime('%H:%M:%S')}] 环境光={st['median']:5.1f} "
                  f"平滑={st['ema']:5.1f} 目标={st['target']:5.1f}% "
                  f"当前={st['brightness']:3d}% {st.get('event', '')}")

    try:
        ctrl.run(stop, on_update=show)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        ctrl.close()
    return 0


def cmd_once(args) -> int:
    if warn_if_running("once"):
        return 1
    cfg = Config.load()
    ctrl = Controller(cfg)
    ctrl.start(retune=args.retune)
    try:
        st = ctrl.tick(apply=False)
        if st["median"] < 1.0:
            print("读不到有效画面：摄像头可能被其他程序（微信/Teams/相机）或托盘常驻实例占用。")
        else:
            print(f"环境光={st['median']:.1f}  目标亮度={st['target']:.1f}%  "
                  f"当前亮度={st['brightness']}%  (只测不调)")
    finally:
        ctrl.close()
    return 0


def cmd_test_camera(args) -> int:
    if warn_if_running("test-camera"):
        return 1
    cfg = Config.load()
    from camera import AmbientSensor

    sensor = AmbientSensor(cfg)
    sensor.open()
    exp = sensor.autotune_exposure()
    print(f"选定曝光: {exp}")
    try:
        for i in range(int(args.seconds) if hasattr(args, "seconds") else 10):
            s = sensor.read()
            print(f"  median={s.median:6.1f} mean={s.mean:6.1f} "
                  f"过曝={s.sat_ratio:5.1%} 死黑={s.dark_ratio:5.1%}")
            time.sleep(1)
    finally:
        sensor.close()
    return 0


def cmd_calibrate(args) -> int:
    if warn_if_running("calibrate"):
        return 1
    cfg = Config.load()
    from camera import AmbientSensor

    sensor = AmbientSensor(cfg)
    sensor.open()
    print("正在自动选择曝光(让当前环境落在量程中段)...")
    exp = sensor.autotune_exposure()
    cfg.exposure = exp
    cfg.save()
    print(f"曝光 = {exp}")

    print("\n接下来 8 秒: 请保持正常坐姿, 不要挡摄像头。正在记录你的环境光基线...")
    vals = []
    for _ in range(8):
        s = sensor.read()
        vals.append(s.median)
        time.sleep(1)
    sensor.close()
    vals.sort()
    med = vals[len(vals) // 2]
    print(f"基线 median = {med:.1f}")
    suggestion_black = max(2.0, med * 0.35)
    suggestion_white = max(med * 2.2, suggestion_black + 20)
    print(f"\n建议参数(可在 config.json 调整):")
    print(f'  "black_point": {suggestion_black:.1f},   "white_point": {suggestion_white:.1f}')
    ans = input("是否写入这组参数? [Y/n] ").strip().lower()
    if ans in ("", "y", "yes"):
        cfg.black_point = suggestion_black
        cfg.white_point = suggestion_white
        cfg.save()
        print("已保存。")
    return 0


def cmd_autostart(args) -> int:
    import subprocess

    startup = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                           "Start Menu", "Programs", "Startup")
    lnk = os.path.join(startup, "摄像头自动亮度.lnk")
    pythonw = os.path.join(BASE, ".venv", "Scripts", "pythonw.exe")
    script = os.path.join(BASE, "run.py")

    if args.mode == "off":
        if os.path.exists(lnk):
            os.remove(lnk)
            print("已移除开机自启")
        else:
            print("本来就没有开机自启")
        cfg = Config.load()
        cfg.autostart = False
        cfg.save()
        return 0

    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{lnk}'); "
        f"$s.TargetPath = '{pythonw}'; "
        f"$s.Arguments = '\"{script}\" tray'; "
        f"$s.WorkingDirectory = '{BASE}'; "
        "$s.WindowStyle = 7; $s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    cfg = Config.load()
    cfg.autostart = True
    cfg.save()
    print(f"已设置开机自启: {lnk}")
    return 0


def cmd_tray(args) -> int:
    if not single_instance():
        print("已经有一个实例在运行。")
        return 1
    import pystray
    from PIL import Image, ImageDraw

    import gui

    cfg = Config.load()
    first_run_tune(cfg)
    ctrl = Controller(cfg)
    ctrl.start(retune=args.retune)
    stop = threading.Event()
    latest: dict = {"st": {}}

    # ---------- 托盘 ----------
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((20, 20, 44, 44), fill=(255, 196, 0, 255))
    import math
    for i in range(8):
        ang = i * math.pi / 4
        x1, y1 = 32 + 15 * math.cos(ang), 32 + 15 * math.sin(ang)
        x2, y2 = 32 + 25 * math.cos(ang), 32 + 25 * math.sin(ang)
        d.line((x1, y1, x2, y2), fill=(255, 196, 0, 255), width=4)

    app: gui.App | None = None

    def worker():
        def on_update(st):
            latest["st"] = st
            if "yield" in st:
                m, s = divmod(max(0, st["yield"]), 60)
                txt = f"已让出摄像头 {m}:{s:02d}"
            elif "error" in st:
                txt = f"{st['error'][:36]}"
            elif st.get("paused"):
                txt = "已暂停"
            elif st.get("event") == "no-data":
                txt = "读不到画面（摄像头被占用？）"
            elif "brightness" in st:
                txt = f"环境光 {st['ema']:.0f} → {st['brightness']}%"
            else:
                txt = "运行中"
            latest["text"] = txt
            try:
                icon.update_menu()
            except Exception:
                pass

        ctrl.run(stop, on_update=on_update)

    def show_win(icon, item):
        if app:
            app.q.put("show")

    def toggle_pause(icon, item):
        cfg.paused = not cfg.paused
        cfg.save()
        latest["text"] = "已暂停" if cfg.paused else "恢复采样…"
        icon.update_menu()

    def retune(icon, item):
        try:
            exp = ctrl.sensor.autotune_exposure()
            ctrl.sensor.set_exposure(exp)
            cfg.exposure = exp
            cfg.exposure_ref = exp
            cfg.save()
            latest["text"] = f"曝光已更新 {exp:.1f}"
        except Exception as e:
            latest["text"] = f"测光失败: {e}"
        icon.update_menu()

    def open_log(icon, item):
        os.startfile(os.path.join(BASE, "brightness-log.csv"))

    def quit_(icon, item):
        stop.set()
        if app:
            app.q.put("quit")
        else:
            icon.stop()

    def yield_camera(icon, item):
        ctrl.yield_until = time.time() + 30 * 60
        latest["text"] = "已让出摄像头 30:00"
        icon.update_menu()

    menu = pystray.Menu(
        pystray.MenuItem(lambda i: latest.get("text", "摄像头自动亮度"), None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("设置…", show_win, default=True),
        pystray.MenuItem("暂停 / 继续", toggle_pause, checked=lambda i: cfg.paused),
        pystray.MenuItem("重新测光", retune),
        pystray.MenuItem("让出摄像头 30 分钟", yield_camera),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("打开日志", open_log),
        pystray.MenuItem("退出", quit_),
    )
    icon = pystray.Icon("AutoBrightness", img, "摄像头自动亮度", menu)

    # ---------- 主界面 ----------
    app = gui.App(cfg, ctrl, stop, latest)
    threading.Thread(target=worker, daemon=True).start()
    try:
        icon.run_detached()
    except Exception as e:
        print(f"托盘图标创建失败（不影响主界面）: {e}")

    app.show()
    try:
        app.root.mainloop()
    finally:
        stop.set()
        try:
            icon.stop()
        except Exception:
            pass
        ctrl.close()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="笔记本摄像头自动亮度")
    p.add_argument("--retune", action="store_true", help="启动时重新选择曝光")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("tray")
    sub.add_parser("run")
    sub.add_parser("once")
    sub.add_parser("calibrate")
    tc = sub.add_parser("test-camera")
    tc.add_argument("--seconds", type=int, default=10)
    au = sub.add_parser("autostart")
    au.add_argument("mode", choices=["on", "off"])
    a = p.parse_args()

    cmd = a.cmd or "tray"
    if cmd == "run":
        return cmd_run(a)
    if cmd == "once":
        return cmd_once(a)
    if cmd == "calibrate":
        return cmd_calibrate(a)
    if cmd == "test-camera":
        return cmd_test_camera(a)
    if cmd == "autostart":
        return cmd_autostart(a)
    return cmd_tray(a)


if __name__ == "__main__":
    sys.exit(main())