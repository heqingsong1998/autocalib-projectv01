"""
传感器工具函数
"""
from typing import Dict, Any
from .m8128b1 import M8128B1Sensor


def create_sensor(sensor_type: str, config: Dict[str, Any]):
    """
    创建传感器对象
    
    Args:
        sensor_type: 传感器类型
        config: 传感器配置
        
    Returns:
        传感器对象
    """
    if sensor_type.lower() == "m8128b1":
        return M8128B1Sensor(config)
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


def test_sensor_communication(sensor) -> bool:
    """
    测试传感器通信
    
    Args:
        sensor: 传感器对象
        
    Returns:
        True: 通信正常, False: 通信异常
    """
    print("=== 传感器通信测试 ===")
    
    try:
        # 开始数据流
        if not sensor.start_stream():
            return False
        
        # 读取几帧数据进行测试
        for i in range(10):
            data_list = sensor.read_data()
            if data_list:
                pkg_no, groups = data_list[0]
                print(f"测试帧 #{pkg_no}: {len(groups)} 组数据")
                break
        else:
            print("❌ 未收到测试数据")
            return False
        
        # 停止数据流
        sensor.stop_stream()
        
        print("✅ 传感器通信测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 传感器通信测试失败: {e}")
        return False