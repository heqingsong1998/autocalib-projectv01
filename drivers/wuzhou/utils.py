"""
传感器工具函数
"""
from typing import Dict, Any
from .wuzhou_five_axis import WuzhouFiveAxisSensor


def create_sensor(sensor_type: str, config: Dict[str, Any]):
    """
    创建传感器对象
    
    Args:
        sensor_type: 传感器类型
        config: 传感器配置
        
    Returns:
        传感器对象
    """
    sensor_type = sensor_type.lower()
    
    if sensor_type == "wuzhou_five_axis":
        return WuzhouFiveAxisSensor(config)
    else:
        raise ValueError(f"不支持的传感器类型: {sensor_type}")


def initialize_sensor(sensor, auto_config: bool = True) -> bool:
    """
    初始化传感器
    
    Args:
        sensor: 传感器对象
        auto_config: 是否自动配置
        
    Returns:
        True: 初始化成功, False: 初始化失败
    """
    print("=== 传感器初始化 ===")
    
    try:
        # 连接传感器
        if not sensor.connect():
            return False
        
        # 配置传感器
        if auto_config and not sensor.configure():
            return False
        
        print("🎉 传感器初始化完成")
        return True
        
    except Exception as e:
        print(f"❌ 传感器初始化失败: {e}")
        return False


def display_sensor_data(frame_no: int, data_tuple: tuple):
    """
    格式化显示五轴传感器数据
    
    Args:
        frame_no: 帧号
        data_tuple: 数据元组 (c1, c2, c3, c4, c0, FZ, MY, MX, FX, FY)
    """
    if len(data_tuple) == 10:
        c1, c2, c3, c4, c0, FZ, MY, MX, FX, FY = data_tuple
        print(f"#{frame_no:05d} "
              f"c1={c1:6d} c2={c2:6d} c3={c3:6d} c4={c4:6d} c0={c0:6d} "
              f"FZ={FZ:6d} MY={MY:6d} MX={MX:6d} FX={FX:6d} FY={FY:6d}")
    else:
        print(f"#{frame_no:05d} Data: {data_tuple}")