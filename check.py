# -*- coding: utf-8 -*-
"""硬件自检：确认亮度接口、摄像头、手动曝光是否可用。

用法:  .venv\\Scripts\\python.exe check.py
"""
import sys
import time
import ctypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def line(t):
    print("\n" + "=" * 60)
    print(t)
    print("=" * 60)


def probe_brightness():
    line("1. 屏幕亮度接口 (WMI)")
    try:
        import comtypes.client

        locator = comtypes.client.CreateObject("WbemScripting.SWbemLocator")
        svc = locator.ConnectServer(".", "root/wmi")
        monitors = svc.ExecQuery("SELECT * FROM WmiMonitorBrightness")
        methods = svc.ExecQuery("SELECT * FROM WmiMonitorBrightnessMethods")

        mon = list(monitors)
        meth = list(methods)
        print(f"亮度传感器数量: {len(mon)}   可写方法数量: {len(meth)}")
        if not mon:
            print("[X] 没有 WmiMonitorBrightness —— 内屏不支持 WMI 调亮度")
            return False
        for m in mon:
            print(f"  - {m.InstanceName}  当前亮度 = {m.CurrentBrightness}  "
                  f"档位数 = {getattr(m, 'NumLevels', '?')}")

        cur = int(mon[0].CurrentBrightness)
        target = cur - 8 if cur >= 20 else cur + 8
        print(f"\n测试写入: {cur} -> {target} ...")
        meth[0].WlrmSetBrightness(1, target)
        time.sleep(0.8)
        after = int(list(svc.ExecQuery("SELECT * FROM WmiMonitorBrightness"))[0].CurrentBrightness)
        print(f"写入后读回: {after}  {'[OK] 亮度可写' if after == target else '[?] 读回不一致'}")
        meth[0].WlrmSetBrightness(1, cur)
        time.sleep(0.5)
        back = int(list(svc.ExecQuery("SELECT * FROM WmiMonitorBrightness"))[0].CurrentBrightness)
        print(f"已恢复原亮度: {back}")
        return after == target
    except Exception as e:
        print(f"[X] WMI 亮度接口失败: {type(e).__name__}: {e}")
        return False


def probe_gamma():
    line("2. Gamma 兜底接口 (GDI)")
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        hdc = user32.GetDC(None)
        ramp = (ctypes.c_ushort * 256 * 3)()
        ok = gdi32.GetDeviceGammaRamp(hdc, ctypes.byref(ramp))
        user32.ReleaseDC(None, hdc)
        print(f"GetDeviceGammaRamp -> {'[OK] 可读' if ok else '[X] 不支持'}")
        return bool(ok)
    except Exception as e:
        print(f"[X] {e}")
        return False


def probe_camera():
    line("3. 摄像头")
    import cv2
    import numpy as np

    print(f"OpenCV {cv2.__version__}")
    found = []
    for idx in range(4):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                found.append(idx)
                print(f"  索引 {idx}: 可用, 分辨率 {frame.shape[1]}x{frame.shape[0]}")
        cap.release()
    if not found:
        print("[X] 没有找到可用摄像头")
        return False

    idx = found[0]
    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    for _ in range(5):
        cap.read()

    def g(p):
        try:
            return cap.get(p)
        except Exception:
            return float("nan")

    print(f"\n默认值: 曝光={g(cv2.CAP_PROP_EXPOSURE):.3f}  "
          f"自动曝光标志={g(cv2.CAP_PROP_AUTO_EXPOSURE):.3f}  "
          f"增益={g(cv2.CAP_PROP_GAIN):.3f}  亮度={g(cv2.CAP_PROP_BRIGHTNESS):.3f}")

    # 尝试锁定曝光（DSHOW: 0.25 = 手动）
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
    time.sleep(0.3)
    print(f"设置手动曝光后读回: {g(cv2.CAP_PROP_AUTO_EXPOSURE):.3f}")

    for exp in (-5, -7):
        cap.set(cv2.CAP_PROP_EXPOSURE, exp)
        time.sleep(0.4)
        vals = []
        for _ in range(6):
            ok, frame = cap.read()
            if ok:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                h, w = gray.shape
                roi = gray[h // 4: h * 3 // 4, w // 4: w * 3 // 4]
                vals.append(float(roi.mean()))
        if vals:
            print(f"曝光={exp}: 读回曝光={g(cv2.CAP_PROP_EXPOSURE):.3f}  "
                  f"中心亮度均值={np.mean(vals):.1f} (波动 {np.std(vals):.1f})")

    # 恢复自动曝光
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
    cap.release()
    return True


def main():
    print("笔记本摄像头自动亮度 —— 硬件自检")
    print(f"Python {sys.version.split()[0]}   {sys.executable}")
    b = probe_brightness()
    probe_gamma()
    c = probe_camera()
    line("结论")
    print(f"WMI 亮度可写: {'是' if b else '否'}")
    print(f"摄像头可用:   {'是' if c else '否'}")


if __name__ == "__main__":
    main()