# -*- coding: utf-8 -*-
"""检查 pythonw 进程是否真的创建了托盘图标(枚举它的隐藏窗口)。"""
import ctypes
import ctypes.wintypes as wt
import subprocess

user32 = ctypes.windll.user32
EnumWindows = user32.EnumWindows
GetClassNameW = user32.GetClassNameW
GetWindowTextW = user32.GetWindowTextW
GetWindowThreadProcessId = user32.GetWindowThreadProcessId

out = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-Process pythonw -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }"],
    capture_output=True, text=True).stdout
pids = {int(x) for x in out.split() if x.strip().isdigit()}
print("pythonw pids:", sorted(pids))

rows = []


def cb(hwnd, _):
    pid = wt.DWORD()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value not in pids:
        return True
    cls = ctypes.create_unicode_buffer(256)
    GetClassNameW(hwnd, cls, 256)
    txt = ctypes.create_unicode_buffer(256)
    GetWindowTextW(hwnd, txt, 256)
    rows.append((pid.value, cls.value, txt.value))
    return True


CBTYPE = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
EnumWindows(CBTYPE(cb), 0)

for pid, cls, txt in rows:
    print(f"  pid={pid} class={cls!r} title={txt!r}")
if not rows:
    print("  (没有找到窗口)")
print("托盘消息窗口存在:", any("Tray" in c or "SystemTray" in c for _, c, _ in rows))