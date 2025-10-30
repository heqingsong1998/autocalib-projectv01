from typing import Any, Dict
from .liuzhou_six_axis import LiuzhouSixAxisSensor

def create_sensor(config: Dict[str, Any]) -> LiuzhouSixAxisSensor:
    return LiuzhouSixAxisSensor(config)

def initialize_sensor(sensor: LiuzhouSixAxisSensor) -> bool:
    return sensor.connect() and sensor.configure() and sensor.start_stream()

def display_sensor_data(frame_no: int, data: tuple):
    """在控制台格式化显示六轴传感器数据（包含温度）"""
    Fx, Fy, Fz, Mx, My, Mz, Temp = data
    print(
        f"#{frame_no:06d} | "
        f"Fx={Fx:6d}, Fy={Fy:6d}, Fz={Fz:6d}, "
        f"Mx={Mx:6d}, My={My:6d}, Mz={Mz:6d} | "
        f"Temp={Temp:6d}"
    )