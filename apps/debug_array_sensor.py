import os
import sys
import time
import signal

import yaml

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from drivers.array_sensor.utils import create_array_sensor, initialize_array_sensor

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "default.yaml")


def load_cfg():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    cfg = load_cfg()
    sensor_cfg = cfg.get("sensor", {}).get("array_sensor")
    if not sensor_cfg:
        raise ValueError("配置缺少 sensor.array_sensor")

    sensor = create_array_sensor(sensor_cfg)
    if not initialize_array_sensor(sensor):
        raise RuntimeError("阵列传感器初始化失败")

    stop = {"flag": False}

    def _stop(*_):
        stop["flag"] = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    print("开始读取阵列传感器数据（Ctrl+C 退出，输入 z 回车清零）")

    try:
        while not stop["flag"]:
            frame = sensor.read_frame()
            if frame is None:
                time.sleep(0.005)
                continue

            f = frame["force"]
            p = frame["pressure"]
            print(
                f"[{frame['timestamp']}] Fx={f['fx']:+.4f} Fy={f['fy']:+.4f} Fz={f['fz']:+.4f} | "
                f"Px={p['fx']:+.4f} Py={p['fy']:+.4f} Pz={p['fz']:+.4f} | "
                f"T1={frame['temp1']:.3f} T2={frame['temp2']:.3f}"
            )
    finally:
        sensor.disconnect()
        print("阵列传感器已断开")


if __name__ == "__main__":
    main()
