# -*- coding: utf-8 -*-
"""截取主界面窗口的内容(PrintWindow, 被别的窗口挡住也能截到)。"""
import ctypes
import ctypes.wintypes as wt
import sys

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

u32, g32 = ctypes.windll.user32, ctypes.windll.gdi32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    u32.SetProcessDPIAware()

TITLE = "摄像头自动亮度"
hwnd = u32.FindWindowW(None, TITLE)
if not hwnd:
    print("没找到窗口")
    raise SystemExit(1)

rect = wt.RECT()
u32.GetWindowRect(hwnd, ctypes.byref(rect))
w, h = rect.right - rect.left, rect.bottom - rect.top

hdc = u32.GetWindowDC(hwnd)
mdc = g32.CreateCompatibleDC(hdc)
bmp = g32.CreateCompatibleBitmap(hdc, w, h)
g32.SelectObject(mdc, bmp)
u32.PrintWindow(hwnd, mdc, 2)          # PW_RENDERFULLCONTENT


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
                ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


bi = BITMAPINFOHEADER()
bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
bi.biWidth, bi.biHeight = w, -h
bi.biPlanes, bi.biBitCount, bi.biCompression = 1, 32, 0

buf = ctypes.create_string_buffer(w * h * 4)
g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
out = "D:\\Documents\\AutoBrightness\\_shot-window.png"
img.save(out)

g32.DeleteObject(bmp)
g32.DeleteDC(mdc)
u32.ReleaseDC(hwnd, hdc)
print(f"窗口 {w}x{h} -> {out}")