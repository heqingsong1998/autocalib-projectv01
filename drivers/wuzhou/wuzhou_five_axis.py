"""
五轴USB-CAN传感器驱动实现
通过USB-CAN盒与传感器通信
"""
import serial
import struct
import time
from typing import Dict, List, Tuple, Any, Optional
from .base import SensorBase


class WuzhouFiveAxisSensor(SensorBase):
    """五轴USB-CAN传感器驱动"""
    
    # 传感器数据帧结构常量
    FRAME_HEADER = bytes.fromhex("5A 40 04 80 00 C3 51")  # 帧头(7B)
    FRAME_TAIL = 0xA5                                      # 帧尾(1B)
    FRAME_LEN = 72                                         # 总长度(7+64+1)
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.buffer = b""
        self.init_frames = config.get("init_frames", [])
        self.zero_frame_hex = config.get("zero_frame_hex", "")
        
    def connect(self) -> bool:
        """连接传感器"""
        try:
            self.ser = serial.Serial(
                port=self.config["port"],
                baudrate=self.config["baudrate"],
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=self.config.get("timeout", 0.05)
            )
            self.connected = True
            print(f"✅ 五轴传感器连接成功: {self.config['port']}")
            return True
        except Exception as e:
            print(f"❌ 五轴传感器连接失败: {e}")
            return False
    
    def disconnect(self) -> bool:
        """断开传感器连接"""
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.connected = False
            print("✅ 五轴传感器已断开连接")
            return True
        except Exception as e:
            print(f"❌ 五轴传感器断开失败: {e}")
            return False
    
    def configure(self) -> bool:
        """配置传感器参数（发送初始化帧）"""
        try:
            if not self.connected:
                print("❌ 传感器未连接")
                return False
            
            print("📡 发送初始化指令...")
            self._send_init_frames()
            
            print("✅ 五轴传感器配置完成")
            return True
            
        except Exception as e:
            print(f"❌ 五轴传感器配置失败: {e}")
            return False
    
    def start_stream(self) -> bool:
        """开始数据流（五轴传感器自动发送数据）"""
        try:
            if not self.connected:
                print("❌ 传感器未连接")
                return False
            
            # 清空缓冲区
            self.ser.reset_input_buffer()
            self.buffer = b""
            
            print("✅ 五轴传感器数据流已开始")
            return True
            
        except Exception as e:
            print(f"❌ 开始数据流失败: {e}")
            return False
    
    def stop_stream(self) -> bool:
        """停止数据流（五轴传感器无需特殊停止指令）"""
        try:
            if not self.connected:
                return True
            
            # 清空缓冲区
            self.ser.reset_input_buffer()
            self.buffer = b""
            
            print("✅ 五轴传感器数据流已停止")
            return True
            
        except Exception as e:
            print(f"❌ 停止数据流失败: {e}")
            return False
    
    def zero_channels(self, channels: List[int] = None) -> bool:
        """清零传感器（发送清零帧）"""
        try:
            if not self.connected:
                print("❌ 传感器未连接")
                return False
            
            if not self.zero_frame_hex:
                print("❌ 未配置清零帧")
                return False
            
            print("📡 发送清零指令...")
            pkt = bytes.fromhex(self.zero_frame_hex)
            self.ser.write(pkt)
            print(f"[ZERO] 发送: {self.zero_frame_hex}")
            
            # 给设备一点处理时间
            time.sleep(0.02)
            
            print("✅ 五轴传感器清零完成")
            return True
            
        except Exception as e:
            print(f"❌ 五轴传感器清零失败: {e}")
            return False
    
    def read_data(self) -> List[Tuple[int, List[Tuple[float, ...]]]]:
        """读取传感器数据"""
        try:
            if not self.connected:
                return []
            
            # 读取数据块
            chunk_size = self.config.get("read_chunk", 256)
            chunk = self.ser.read(chunk_size)
            if not chunk:
                return []
            
            self.buffer += chunk
            
            # 解析多帧数据
            results = []
            frame_count = 0
            
            while True:
                frame, self.buffer = self._find_frame(self.buffer)
                if frame is None:
                    # 防止缓冲区过大
                    self.buffer = self.buffer[-4096:]
                    break
                
                try:
                    # 解析传感器数据
                    sensor_data = self._parse_sensor_frame(frame)
                    # 转换为标准格式：(帧号, [(数据组)])
                    # 五轴传感器返回一组数据：(c1,c2,c3,c4,c0,FZ,MY,MX,FX,FY)
                    data_tuple = (
                        sensor_data["c1"], sensor_data["c2"], sensor_data["c3"],
                        sensor_data["c4"], sensor_data["c0"], sensor_data["FZ"],
                        sensor_data["MY"], sensor_data["MX"], sensor_data["FX"],
                        sensor_data["FY"]
                    )
                    results.append((frame_count, [data_tuple]))
                    frame_count += 1
                    
                except Exception as e:
                    # 解析错误时的软恢复
                    print(f"解析错误: {e}")
                    print(f"帧数据: {frame.hex(' ').upper()}")
                    # 将帧的第一个字节去掉并放回缓冲区
                    self.buffer = frame[1:] + self.buffer
                    break
            
            return results
            
        except Exception as e:
            print(f"❌ 读取数据失败: {e}")
            return []
    
    def get_sensor_info(self) -> Dict[str, Any]:
        """获取传感器信息"""
        return {
            "type": "五轴USB-CAN传感器",
            "manufacturer": "梧州",
            "channels": ["c1", "c2", "c3", "c4", "c0", "FZ", "MY", "MX", "FX", "FY"],
            "communication": "USB-CAN",
            "frame_length": self.FRAME_LEN,
            "data_format": "int16"
        }
    
    def _send_init_frames(self):
        """发送初始化指令帧"""
        for frame_hex in self.init_frames:
            pkt = bytes.fromhex(frame_hex)
            self.ser.write(pkt)
            print(f"[INIT] 发送: {frame_hex}")
            time.sleep(0.05)  # 50ms间隔
    
    def _find_frame(self, buf: bytes) -> Tuple[Optional[bytes], bytes]:
        """在缓存中寻找一帧完整数据"""
        while True:
            idx = buf.find(self.FRAME_HEADER)
            if idx < 0:
                return None, buf  # 没找到头
            if len(buf) - idx < self.FRAME_LEN:
                return None, buf[idx:]  # 不够一帧，留待下次
            
            frame = buf[idx:idx + self.FRAME_LEN]
            if frame[-1] != self.FRAME_TAIL:
                # 帧尾不符，丢1字节继续找，做软对齐
                buf = buf[idx + 1:]
                continue
            
            rest = buf[idx + self.FRAME_LEN:]
            return frame, rest
    
    def _parse_sensor_frame(self, frame: bytes) -> Dict[str, int]:
        """
        解析一帧72字节数据
        返回字典 {c1,c2,c3,c4,c0,FZ,MY,MX,FX,FY}
        """
        payload = frame[len(self.FRAME_HEADER):-1]  # 去掉帧头和尾，64B
        values = struct.unpack("<32h", payload)     # 小端，有符号int16

        # 按正/负号配置二次项、一次项、常数项（quad, lin, const）
        # 公式：scaled = quad*v*v + lin*v + const
        sign_coeff = {
            "FZ": {"pos": {"quad": 0.0, "lin": 1.0,   "const": 0.0},
                   "neg": {"quad": 0.0, "lin": 1.0,   "const": 0.0}},
            "MX": {"pos": {"quad": 0.0, "lin": 0.095, "const": 0.0},  # 原先0.095缩放
                   "neg": {"quad": 0.0, "lin": 0.095, "const": 0.0}},
            "MY": {"pos": {"quad": 0.0, "lin": 1.0,   "const": 0.0},
                   "neg": {"quad": 0.0, "lin": 1.0,   "const": 0.0}},
            "FX": {"pos": {"quad": 0.0, "lin": 1.0,   "const": 0.0},
                   "neg": {"quad": 0.0, "lin": 1.0,   "const": 0.0}},
            "FY": {"pos": {"quad": 0.0, "lin": 1.0,   "const": 0.0},
                   "neg": {"quad": 0.0, "lin": 1.0,   "const": 0.0}},
        }

        def scale_by_sign(v: int, key: str) -> int:
            branch = "pos" if v >= 0 else "neg"
            cfg = sign_coeff.get(key, {}).get(branch, {"quad": 0.0, "lin": 1.0, "const": 0.0})
            quad = cfg.get("quad", 0.0)
            lin = cfg.get("lin", 1.0)
            const = cfg.get("const", 0.0)
            scaled = quad * (v * v) + lin * v + const
            return scaled

        fields = {
            "c1": values[0],
            "c2": values[1],
            "c3": values[2],
            "c4": values[3],
            "c0": values[4],
            "FZ": scale_by_sign(values[5], "FZ"),
            "MY": scale_by_sign(values[7], "MY"),
            "MX": scale_by_sign(values[6], "MX"),
            "FX": scale_by_sign(values[8], "FX"),
            "FY": scale_by_sign(values[9], "FY"),
            # 其余 values[10:] 暂未定义
        }
        return fields

