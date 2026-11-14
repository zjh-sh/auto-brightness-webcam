# -*- coding: utf-8 -*-
"""确认程序空闲时真的把摄像头放开了: 反复抢一次, 看能不能抢到。"""
import sys
import time

import cv2

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ok = tries = 0
t0 = time.time()
while time.time() - t0 < 25:
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    tries += 1
    if cap.isOpened():
        got, _ = cap.read()
        if got:
            ok += 1
    cap.release()
    time.sleep(0.6)
print(f"尝试 {tries} 次, 成功打开并读到画面 {ok} 次")