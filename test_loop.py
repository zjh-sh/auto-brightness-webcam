# -*- coding: utf-8 -*-
"""联机测试: 跑 N 秒真实控制环, 打印每一步, 结束时恢复原亮度。

  .venv\\Scripts\\python.exe test_loop.py 45
"""
import sys
import time

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import Config          # noqa: E402
from control import Controller     # noqa: E402


def main() -> int:
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 40
    cfg = Config.load()
    ctrl = Controller(cfg)
    ctrl.start()
    orig = ctrl.backend.get()
    print(f"后端={ctrl.backend_name} 曝光={cfg.exposure} 起始亮度={orig}% 运行 {secs:.0f}s")
    t_end = time.time() + secs
    try:
        while time.time() < t_end:
            t0 = time.time()
            st = ctrl.tick()
            print(f"  env={st['median']:6.1f} ema={st['ema']:6.1f} "
                  f"target={st['target']:5.1f}% bright={st['brightness']:3d}% "
                  f"{st.get('event','')}")
            time.sleep(max(0.0, cfg.sample_interval - (time.time() - t0)))
    finally:
        ctrl.backend.set(orig)
        ctrl.close()
        print(f"已恢复原亮度 {orig}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())