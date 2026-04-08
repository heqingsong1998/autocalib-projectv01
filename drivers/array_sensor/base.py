"""阵列触觉传感器抽象接口。"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ArraySensorBase(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.connected = False

    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        pass

    @abstractmethod
    def zero(self) -> None:
        pass

    @abstractmethod
    def read_frame(self) -> Optional[Dict[str, Any]]:
        """读取一帧并返回解析+补偿后的结果。"""
        pass
