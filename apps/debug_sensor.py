import os
import sys
import time
import signal
import csv
import threading
from datetime import datetime
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
    zero_req = {"flag": False}
    zero_lock = threading.Lock()

    def _on_stop(signum: Optional[int] = None, frame=None):
        stop_flag["stop"] = True

    signal.signal(signal.SIGINT, _on_stop)
    signal.signal(signal.SIGTERM, _on_stop)

    def _command_loop():
        """
        命令线程：
        - 输入 z + 回车：触发六轴清零
        - 输入 q + 回车：退出
        """
        while not stop_flag["stop"]:
            try:
                cmd = input().strip().lower()
            except EOFError:
                break
            except Exception:
                continue

            if cmd == "z":
                with zero_lock:
                    zero_req["flag"] = True
                print("收到清零请求：将执行六轴清零...")
            elif cmd == "q":
                stop_flag["stop"] = True
                print("收到退出请求...")
                break
            elif cmd:
                print("未知命令，请输入 z(清零) 或 q(退出)")

    if not initialize_sensor(sensor, auto_config=True):
        raise RuntimeError("传感器初始化失败")

    if not sensor.start_stream():
        raise RuntimeError("传感器启动数据流失败")

    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(log_dir, f"m8128b1_debug_{ts}.csv")

    csv_f = open(csv_path, "w", newline="", encoding="utf-8")
    writer = csv.writer(csv_f)
    writer.writerow(
        [
            "timestamp",
            "elapsed_s",
            "pkg_no",
            "group_idx",
            "Fx",
            "Fy",
            "Fz",
            "Mx",
            "My",
            "Mz",
        ]
    )

    cmd_thread = threading.Thread(target=_command_loop, daemon=True)
    cmd_thread.start()

    print("\n开始读取数据并写入 CSV（Ctrl+C 停止，输入 z 回车可清零，输入 q 回车退出）...")
    print(f"CSV 文件: {csv_path}\n")

    last_status = 0.0
    sample_count = 0
    t0 = time.time()

    try:
        while not stop_flag["stop"]:
            with zero_lock:
                do_zero = zero_req["flag"]
                zero_req["flag"] = False
            if do_zero:
                ok = sensor.zero_channels([1, 1, 1, 1, 1, 1])
                print("六轴清零结果:", "✅ 成功" if ok else "❌ 失败")

            data_list = sensor.read_data()
            if not data_list:
                time.sleep(0.005)
                continue

            for pkg_no, groups in data_list:
                for idx, values in enumerate(groups):
                    sample_count += 1
                    now = time.time()
                    elapsed = now - t0
                    fx, fy, fz, mx, my, mz = (list(values[:6]) + [float("nan")] * 6)[:6]
                    writer.writerow(
                        [
                            datetime.now().isoformat(timespec="milliseconds"),
                            f"{elapsed:.6f}",
                            pkg_no,
                            idx,
                            f"{fx:.6f}",
                            f"{fy:.6f}",
                            f"{fz:.6f}",
                            f"{mx:.6f}",
                            f"{my:.6f}",
                            f"{mz:.6f}",
                        ]
                    )

            if sample_count % 200 == 0:
                csv_f.flush()

            now = time.time()
            if now - last_status >= 1.0:
                rate = sample_count / max(now - t0, 1e-6)
                print(f"[状态] 已采集样本: {sample_count}, 平均速率: {rate:.1f} samples/s")
                last_status = now

        print("\n收到停止信号，准备退出...")

    finally:
        try:
            csv_f.flush()
            csv_f.close()
        except Exception:
            pass

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
        print(f"CSV 已保存: {csv_path}")
        print("✅ 调试结束")


if __name__ == "__main__":
    main()
