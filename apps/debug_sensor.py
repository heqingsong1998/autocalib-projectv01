import os
import sys
import time
import signal
from typing import Optional

import yaml

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from drivers.sensors.utils import create_sensor, initialize_sensor  # noqa: E402


CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "default.yaml")


def load_cfg() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fmt_six_axis(values: tuple[float, ...]) -> str:
    """格式化六轴数据: Fx, Fy, Fz, Mx, My, Mz。"""
    if len(values) < 6:
        return f"原始数据(通道不足6): {values}"

    fx, fy, fz, mx, my, mz = values[:6]
    return (
        f"Fx={fx:>9.3f} | Fy={fy:>9.3f} | Fz={fz:>9.3f} | "
        f"Mx={mx:>9.3f} | My={my:>9.3f} | Mz={mz:>9.3f}"
    )


def main() -> None:
    print("=== M8128B1 六轴力传感器调试 ===")

    cfg = load_cfg()
    sensor_cfg = (cfg.get("sensor") or {}).get("m8128b1")
    if not sensor_cfg:
        raise ValueError("配置文件缺少 sensor.m8128b1")

    print(
        "使用配置:",
        {
            "port": sensor_cfg.get("port"),
            "baudrate": sensor_cfg.get("baudrate"),
            "channels": sensor_cfg.get("channels"),
            "rate_hz": sensor_cfg.get("rate_hz"),
        },
    )

    sensor = create_sensor("m8128b1", sensor_cfg)
    stop_flag = {"stop": False}

    def _on_stop(signum: Optional[int] = None, frame=None):
        stop_flag["stop"] = True

    signal.signal(signal.SIGINT, _on_stop)
    signal.signal(signal.SIGTERM, _on_stop)

    if not initialize_sensor(sensor, auto_config=True):
        raise RuntimeError("传感器初始化失败")

    if not sensor.start_stream():
        raise RuntimeError("传感器启动数据流失败")

    print("\n开始读取数据（Ctrl+C 停止）...\n")

    last_print = 0.0
    sample_count = 0
    t0 = time.time()

    try:
        while not stop_flag["stop"]:
            data_list = sensor.read_data()
            if not data_list:
                time.sleep(0.005)
                continue

            for pkg_no, groups in data_list:
                for idx, values in enumerate(groups):
                    sample_count += 1
                    now = time.time()

                    # 限制打印频率，避免终端刷屏太快
                    if now - last_print >= 0.05:
                        elapsed = now - t0
                        print(
                            f"[t={elapsed:7.3f}s] pkg={pkg_no:>6} group={idx:>2} | "
                            f"{fmt_six_axis(values)}"
                        )
                        last_print = now

        print("\n收到停止信号，准备退出...")

    finally:
        try:
            sensor.stop_stream()
        except Exception:
            pass

        try:
            sensor.disconnect()
        except Exception:
            pass

        dt = max(time.time() - t0, 1e-6)
        print(f"总样本数: {sample_count}, 运行时长: {dt:.2f}s, 平均样本速率: {sample_count / dt:.1f} samples/s")
        print("✅ 调试结束")


if __name__ == "__main__":
    main()
