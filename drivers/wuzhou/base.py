"""
传感器基类定义
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Any
import serial


class SensorBase(ABC):
    """传感器抽象基类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化传感器
        
        Args:
            config: 传感器配置字典
        """
        self.config = config
        self.ser: serial.Serial = None
        self.connected = False
    
    @abstractmethod
    def connect(self) -> bool:
        """
        连接传感器
        
        Returns:
            True: 连接成功, False: 连接失败
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """
        断开传感器连接
        
        Returns:
            True: 断开成功, False: 断开失败
        """
        pass
    
    @abstractmethod
    def configure(self) -> bool:
        """
        配置传感器参数
        
        Returns:
            True: 配置成功, False: 配置失败
        """
        pass
    
    @abstractmethod
    def start_stream(self) -> bool:
        """
        开始数据流
        
        Returns:
            True: 开始成功, False: 开始失败
        """
        pass
    
    @abstractmethod
    def stop_stream(self) -> bool:
        """
        停止数据流
        
        Returns:
            True: 停止成功, False: 停止失败
        """
        pass
    
    @abstractmethod
    def zero_channels(self, channels: List[int] = None) -> bool:
        """
        清零指定通道
        
        Args:
            channels: 要清零的通道列表，None表示所有通道
            
        Returns:
            True: 清零成功, False: 清零失败
        """
        pass
    
    @abstractmethod
    def read_data(self) -> List[Tuple[int, List[Tuple[float, ...]]]]:
        """
        读取传感器数据
        
        Returns:
            数据列表，格式为 [(frame_no, groups), ...]
            其中 groups 为 [(data_tuple), ...]
        """
        pass
    
    @abstractmethod
    def get_sensor_info(self) -> Dict[str, Any]:
        """
        获取传感器信息
        
        Returns:
            传感器信息字典
        """
        pass