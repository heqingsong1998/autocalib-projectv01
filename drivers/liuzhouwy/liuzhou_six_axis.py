import time
import struct
import serial
from typing import Any, Dict, List, Tuple, Optional

# 相对路径导入，假设 drivers 和 algorithm 是同级目录
from algorithm.lab_six_axis.sensor_data_processor import (
    TemperatureCompensator,
    DynamicCompensator,
    HysteresisCompensator,
    CalibrationProcessor
)
from .base import SensorBase

class LiuzhouSixAxisSensor(SensorBase):
    """
    六轴串口传感器驱动（配对两帧），并集成数据处理流水线。
    帧1: HEAD1(7) + payload(8: Fx,Fy,Fz,My >4h) + A5
    帧2: HEAD2(7) + payload(8: Mx,Mz,Temp,Rsv >2hHH) + A5
    """
    HEAD1 = bytes.fromhex("5A 08 04 00 00 30 01")
    HEAD2 = bytes.fromhex("5A 08 04 00 00 30 02")
    TAIL  = 0xA5
    FRAME_LEN = 16

    INIT1 = bytes.fromhex("49 3B 42 57 00 00 03 00 00 00 00 00 00 00 00 00 00 00 00 00 45 2E")
    INIT2 = bytes.fromhex("49 3B 44 57 01 00 01 00 00 00 00 00 00 00 00 00 00 00 00 00 45 2E")
    ZERO_CMD = bytes.fromhex("5A 08 04 00 00 10 00 01 A8 00 00 00 00 00 B0 A5")

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.buffer = bytearray()

        # --- 数据处理开关 (直接在此处修改 True/False 进行调试) ---
        self.processing_enabled = True      # 总开关
        self.enable_temperature = False      # 启用温度补偿
        self.enable_dynamic = True          # 启用动态补偿
        self.enable_hysteresis = False       # 启用迟滞补偿
        self.enable_calibration = True      # 启用最终标定
        
        if self.processing_enabled:
            print("✅ 实验室六轴数据处理流水线已启用")
            self.base_temp = 0.0  # 温度补偿的基准温度
            self.axis_names = ['fx', 'fy', 'fz', 'mx', 'my', 'mz']
            
            # 为每个轴实例化所有补偿器
            self.temp_compensators = {name: TemperatureCompensator(name) for name in self.axis_names}
            self.dyn_compensators = {name: DynamicCompensator(name) for name in self.axis_names}
            self.hys_compensators = {name: HysteresisCompensator(name) for name in self.axis_names}
            self.calibrators = {name: CalibrationProcessor(name) for name in self.axis_names}
        else:
            print("ℹ️ 实验室六轴数据处理流水线被禁用，将输出原始值")

    def connect(self) -> bool:
        try:
            self.ser = serial.Serial(
                port=self.config["port"],
                baudrate=self.config.get("baudrate", 115200),
                bytesize=8, parity="N", stopbits=1,
                timeout=self.config.get("timeout", 0.05),
            )
            self.connected = True
            print(f"✅ 实验室六轴传感器连接成功: {self.config['port']}")
            return True
        except Exception as e:
            print(f"❌ 实验室六轴传感器连接失败: {e}")
            return False

    def disconnect(self) -> bool:
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.connected = False
            print("✅ 实验室六轴传感器已断开连接")
            return True
        except Exception as e:
            print(f"❌ 实验室六轴传感器断开失败: {e}")
            return False

    def _send_init(self):
        self.ser.write(self.INIT1); time.sleep(0.05)
        self.ser.write(self.INIT2); time.sleep(0.05)

    def configure(self) -> bool:
        if not self.connected:
            print("❌ 传感器未连接"); return False
        try:
            self._send_init()
            print("✅ 实验室六轴传感器配置完成")
            return True
        except Exception as e:
            print(f"❌ 配置失败: {e}")
            return False

    def start_stream(self) -> bool:
        if not self.connected:
            print("❌ 传感器未连接"); return False
        self.ser.reset_input_buffer()
        self.buffer.clear()
        print("✅ 实验室六轴传感器数据流已开始")
        return True

    def stop_stream(self) -> bool:
        if not self.connected:
            return True
        self.ser.reset_input_buffer()
        self.buffer.clear()
        print("✅ 实验室六轴传感器数据流已停止")
        return True

    def zero_channels(self, channels=None) -> bool:
        if not self.connected:
            print("❌ 传感器未连接"); return False
        try:
            self.ser.write(self.ZERO_CMD)
            time.sleep(0.02)
            # 清零时也重置所有补偿器的状态
            if self.processing_enabled:
                for name in self.axis_names:
                    self.dyn_compensators[name].reset()
                    self.hys_compensators[name].reset()
            print("✅ 实验室六轴清零完成（补偿器状态已重置）")
            return True
        except Exception as e:
            print(f"❌ 清零失败: {e}")
            return False

    def read_data(self) -> List[Tuple[int, List[Tuple[float, ...]]]]:
        if not self.connected:
            return []
        chunk = self.ser.read(self.config.get("read_chunk", 256))
        if not chunk:
            return []
        self.buffer += chunk
        out: List[Tuple[int, List[Tuple[float, ...]]]] = []
        frame_no = 0

        while True:
            pair, rest = self._find_pair(self.buffer)
            if pair is None:
                # 防膨胀
                self.buffer = self.buffer[-2048:]
                break
            (f1, f2) = pair
            try:
                # 解析并处理数据
                processed_data = self._parse_and_process_pair(f1, f2)
                out.append((frame_no, [processed_data]))
                frame_no += 1
                self.buffer = rest
            except Exception as e:
                print(f"❌ 处理帧时出错: {e}")
                # 丢1字节软对齐
                self.buffer = self.buffer[1:]
        return out

    def _find_pair(self, buf: bytearray) -> Tuple[Optional[Tuple[bytes, bytes]], bytearray]:
        i = 0
        n = len(buf)
        while i + self.FRAME_LEN*2 <= n:
            if buf[i:i+7] == self.HEAD1 and buf[i+16-1] == self.TAIL:
                # 候选帧2紧随其后
                j = i + self.FRAME_LEN
                if buf[j:j+7] == self.HEAD2 and buf[j+16-1] == self.TAIL:
                    f1 = bytes(buf[i:i+self.FRAME_LEN])
                    f2 = bytes(buf[j:j+self.FRAME_LEN])
                    rest = buf[j+self.FRAME_LEN:]
                    return (f1, f2), bytearray(rest)
                else:
                    i += 1
            else:
                i += 1
        return None, buf

    def _parse_and_process_pair(self, f1: bytes, f2: bytes) -> tuple:
        p1 = f1[7:-1]
        p2 = f2[7:-1]
        Fx, Fy, Fz, My = struct.unpack(">4h", p1)
        # Mx, Mz, Temp_raw, _rsv = struct.unpack(">2hHH", p2)
        Mx, Mz, Temp_raw, _rsv = struct.unpack(">4h", p2)
        
        # 如果禁用了处理，直接返回原始值
        if not self.processing_enabled:
            return (Fx, Fy, Fz, Mx, My, Mz, Temp_raw)

        # --- 开始处理流水线 ---
        raw_values = [Fx, Fy, Fz, Mx, My, Mz]
        #print(raw_values)
        processed_values = []
        
        temp_delta = Temp_raw - self.base_temp

        for i, name in enumerate(self.axis_names):
            val = raw_values[i]
            
            # 1. 温度补偿
            if self.enable_temperature:
                val = self.temp_compensators[name].compensate(val, temp_delta)
                # print(val)
            # 2. 动态补偿
            if self.enable_dynamic:
                val = self.dyn_compensators[name].update(val)
            
            # 3. 迟滞补偿
            if self.enable_hysteresis:
                val = self.hys_compensators[name].compensate(val)
            
            # 4. 标定
            if self.enable_calibration:
                val = self.calibrators[name].calibrate(val)
            
            processed_values.append(val)
            
        return tuple(processed_values) + (Temp_raw,)

    def get_sensor_info(self) -> Dict[str, Any]:
        return {
            "type": "六轴串口传感器",
            "manufacturer": "柳州",
            "channels": ["Fx","Fy","Fz","Mx","My","Mz","Temp"],
            "communication": "UART",
            "frame_length": self.FRAME_LEN,
            "data_format": "mixed: >4h + >2hHH",
        }