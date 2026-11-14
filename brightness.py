# -*- coding: utf-8 -*-
"""屏幕亮度控制后端。

优先级:
  1. WMI (WmiMonitorBrightnessMethods) —— 真实背光, 内屏适用
  2. Gamma Ramp (GDI)                 —— 兜底, 只是压暗画面, 不改背光

WMI 通过一个常驻的 PowerShell 子进程调用, 避免每次开关进程的几百毫秒开销,
也避免 pywin32 / comtypes 对该 COM 接口的动态派发兼容问题。
"""
from __future__ import annotations

import ctypes
import subprocess
import threading
import time

CREATE_NO_WINDOW = 0x08000000
SENTINEL = "<<<AB_DONE>>>"


class WmiBrightness:
    """常驻 PowerShell 通道, 读写 WmiMonitorBrightness / WmiMonitorBrightnessMethods。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._levels = 101
        self._start()

    # ---------- 内部 ----------
    def _start(self) -> None:
        self._proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=CREATE_NO_WINDOW,
        )
        self._ask('$ErrorActionPreference = "Stop"; '
                  '[Console]::OutputEncoding = [Text.Encoding]::UTF8; '
                  '"ready"')
        # 缓存档位数
        n = self._ask("(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness).Levels")
        try:
            self._levels = max(2, int(n.strip()))
        except Exception:
            self._levels = 101

    def _ask(self, cmd: str) -> str:
        assert self._proc is not None and self._proc.stdin and self._proc.stdout
        with self._lock:
            self._proc.stdin.write(cmd + "\n")
            self._proc.stdin.write(f'Write-Output "{SENTINEL}"\n')
            self._proc.stdin.flush()
            out: list[str] = []
            deadline = time.time() + 10
            while True:
                line = self._proc.stdout.readline()
                if line == "":
                    raise RuntimeError("PowerShell 通道已断开")
                if line.strip() == SENTINEL:
                    return "".join(out).strip()
                out.append(line)
                if time.time() > deadline:
                    raise TimeoutError("PowerShell 调用超时")

    # ---------- 公共 ----------
    @property
    def levels(self) -> int:
        return self._levels

    def get(self) -> int:
        v = self._ask(
            "(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness)"
            ".CurrentBrightness"
        )
        return int(v.strip())

    def set(self, value: int) -> None:
        value = max(0, min(100, int(round(value))))
        self._ask(
            "$m = Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods;"
            f"Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness "
            f'-Arguments @{{Timeout=1;Brightness={value}}} | Out-Null;'
            f'"ok"'
        )

    def close(self) -> None:
        try:
            if self._proc:
                self._proc.stdin.close()
                self._proc.terminate()
        except Exception:
            pass


class GammaBrightness:
    """兜底: 通过 GDI gamma ramp 压暗输出。factor 1.0 = 原样。

    接口与 WmiBrightness 对齐(get/set/levels), 这样控制环不用区分后端。
    gamma 只能把画面压暗, 所以 100 就是"不做处理"。
    """

    levels = 101

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._gdi32 = ctypes.windll.gdi32
        self._level = 100
        self._orig = (ctypes.c_ushort * 256 * 3)()
        hdc = self._user32.GetDC(None)
        try:
            ok = self._gdi32.GetDeviceGammaRamp(hdc, ctypes.byref(self._orig))
        finally:
            self._user32.ReleaseDC(None, hdc)
        if not ok:
            raise RuntimeError("该显示器不支持 gamma ramp")

    def get(self) -> int:
        return self._level

    def set(self, value: int) -> None:
        value = max(0, min(100, int(round(value))))
        self._level = value
        self.apply(max(0.3, (value / 100.0) ** 0.7))

    def apply(self, factor: float) -> None:
        factor = max(0.25, min(1.0, factor))
        ramp = (ctypes.c_ushort * 256 * 3)()
        for ch in range(3):
            for i in range(256):
                base = self._orig[ch][i]
                ramp[ch][i] = int(base * factor)
        hdc = self._user32.GetDC(None)
        try:
            self._gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(ramp))
        finally:
            self._user32.ReleaseDC(None, hdc)

    def restore(self) -> None:
        hdc = self._user32.GetDC(None)
        try:
            self._gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(self._orig))
        finally:
            self._user32.ReleaseDC(None, hdc)

    def close(self) -> None:
        self.restore()


def make_backend():
    """返回 (backend, name)。"""
    try:
        b = WmiBrightness()
        b.get()
        return b, "wmi"
    except Exception:
        pass
    try:
        return GammaBrightness(), "gamma"
    except Exception:
        raise RuntimeError("没有可用的亮度控制方式")


if __name__ == "__main__":
    b, name = make_backend()
    print("backend =", name, "levels =", getattr(b, "levels", "?"))
    cur = b.get() if hasattr(b, "get") else None
    print("current =", cur)
    if hasattr(b, "set"):
        b.set(66)
        time.sleep(1)
        print("after 66 =", b.get())
        if cur is not None:
            b.set(cur)
            time.sleep(1)
            print("restored =", b.get())
    b.close()