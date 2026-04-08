from typing import Any, Dict

from .serial_sensor import ArraySensor


def create_array_sensor(config: Dict[str, Any]) -> ArraySensor:
    return ArraySensor(config)


def initialize_array_sensor(sensor: ArraySensor) -> bool:
    print("=== 阵列传感器初始化 ===")
    if not sensor.connect():
        print("❌ 串口连接失败")
        return False
    print("✅ 串口连接成功")
    return True
