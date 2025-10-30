"""
M8128B1 六轴力传感器驱动实现
"""
import serial
import struct
import time
import zlib
from typing import Dict, List, Tuple, Any, Optional
from .base import SensorBase
import threading


class M8128B1Sensor(SensorBase):
    """M8128B1 六轴力传感器驱动"""
    
    HDR = b"\xAA\x55"
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.buffer = b""

        self.ser_lock    = threading.RLock()     # 串口独占锁：所有 self.ser.read/write/reset 都要持有
        self.pause_read  = threading.Event()     # 置位=请读线程暂停读取
        self.read_paused = threading.Event()     # 读线程已暂停的确认

        
    def connect(self) -> bool:
        """连接传感器"""
        try:
            self.ser = serial.Serial(
                port=self.config["port"],
                baudrate=self.config["baudrate"],
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=0.03
            )
            self.connected = True
            print(f"✅ 传感器连接成功: {self.config['port']}")
            return True
        except Exception as e:
            print(f"❌ 传感器连接失败: {e}")
            return False
    
    def disconnect(self) -> bool:
        """断开传感器连接"""
        try:
            if self.ser and self.ser.is_open:
                self.stop_stream()
                self.ser.close()
            self.connected = False
            print("✅ 传感器已断开连接")
            return True
        except Exception as e:
            print(f"❌ 传感器断开失败: {e}")
            return False
    
    def configure(self) -> bool:
        """配置传感器参数"""
        try:
            if not self.connected:
                print("❌ 传感器未连接")
                return False
            
            # 读取当前配置
            self._send_cmd("AT+UARTCFG=?")
            print("UART:", self._read_ack())
            
            self._send_cmd("AT+DCKMD=?")
            print("DCKMD:", self._read_ack())
            
            # 设置采样率
            rate_hz = self.config.get("rate_hz", 200)
            self._send_cmd(f"AT+SMPF={rate_hz}")
            print("SMPF:", self._read_ack())
            
            # 设置每通道每帧组数
            dnpch_set = self.config.get("dnpch_set")
            if dnpch_set is not None:
                self._send_cmd(f"AT+DNpCH={dnpch_set}")
                print("DNpCH:", self._read_ack())
            
            print("✅ 传感器配置完成")
            return True
            
        except Exception as e:
            print(f"❌ 传感器配置失败: {e}")
            return False
    

    def start_stream(self) -> bool:
        """开始数据流"""
        try:
            if not self.connected:
                print("❌ 传感器未连接")
                return False

            with self.ser_lock:
                self.ser.reset_output_buffer()
                self.ser.reset_input_buffer()
                self.ser.write(b"AT+GSD\r\n")
                time.sleep(0.02)
                extra = self._sync_to_header(timeout=1.0)

            if extra:
                self.buffer += extra
            print("✅ 数据流已开始")
            return True

        except Exception as e:
            print(f"❌ 开始数据流失败: {e}")
            return False

    

    
    def stop_stream(self) -> bool:
        """停止数据流（持锁、带超时的ACK等待）"""
        try:
            if not self.connected:
                return True

            with self.ser_lock:
                self.ser.reset_output_buffer()
                self.ser.reset_input_buffer()
                self.ser.write(b"AT+GSD=STOP\r\n")
                self.ser.timeout = 0.6

                got_ok = False
                deadline = time.time() + 2.0
                while time.time() < deadline:
                    line = self.ser.readline().decode(errors="ignore").strip()
                    if not line:
                        continue
                    print("[STOP]", line)
                    if "$OK" in line:
                        got_ok = True
                        break

                if not got_ok:
                    print("⚠️ 停止数据流未确认，可能设备未响应 $OK")

                # 不要立刻 reset_input_buffer，避免把慢到的 $OK 清掉
                self.buffer = b""

            print("✅ 数据流已停止")
            return True

        except Exception as e:
            print(f"❌ 停止数据流失败: {e}")
            return False

    
    # 
    
    def zero_channels(self, channels: List[int] = None) -> bool:
        """清零指定通道（线程安全：暂停读 & 串口独占）"""
        try:
            if not self.connected:
                print("❌ 传感器未连接")
                return False

            if channels is None:
                channels = [1, 1, 1, 1, 1, 1]

            # 1) 通知读线程暂停，并等待它确认已暂停
            print("[六轴-ZERO] 请求暂停读取线程…")
            self.pause_read.set()
            self.read_paused.wait(timeout=0.5)  # 最多等0.5s

            # 2) 停流（内部已持锁）
            print("[六轴-ZERO] 停止数据流…")
            ok = self.stop_stream()
            if not ok:
                print("⚠️ [六轴-ZERO] 停流未确认，继续尝试清零")

            # 3) 串口独占：清空输入→发清零→等ACK（带截止时间）
            cmd = f"AT+ADJZF={';'.join(map(str, channels))}\r\n"
            with self.ser_lock:
                self.ser.reset_input_buffer()   # 清掉停流前残留
                print(f"[六轴-ZERO] 发送: {cmd.strip()}")
                self.ser.write(cmd.encode())

                got_ok = False
                self.ser.timeout = 0.6
                deadline = time.time() + 2.0
                while time.time() < deadline:
                    line = self.ser.readline().decode(errors="ignore").strip()
                    if line:
                        print("[六轴-ZERO-ACK]", line)
                    if "$OK" in line:
                        got_ok = True
                        break
                    time.sleep(0.05)

                if not got_ok:
                    print("⚠️ [六轴-ZERO] 超时未收到 $OK（将继续恢复数据流）")

            # 4) 给设备一点处理时间（可按需调整）
            time.sleep(0.2)

            # 5) 重启数据流（内部建议也加锁）
            print("[六轴-ZERO] 重启数据流…")
            extra = self._restart_stream()
            if extra:
                self.buffer += extra

            print("✅ [六轴-ZERO] 完成")
            return True

        except Exception as e:
            print(f"❌ [六轴-ZERO] 失败: {e}")
            return False

        finally:
            # 6) 恢复读取
            self.pause_read.clear()
            self.read_paused.clear()

    

    def read_data(self) -> List[Tuple[int, List[Tuple[float, ...]]]]:
        """读取传感器数据（尊重暂停，串口I/O上锁）"""
        try:
            if not self.connected:
                return []

            # —— 清零/控制期间暂停读取 —— 
            if self.pause_read.is_set():
                self.read_paused.set()
                time.sleep(0.01)
                return []
            else:
                self.read_paused.clear()

            # —— 串口读取必须独占 —— 
            chunk_size = self.config.get("read_chunk", 2048)
            with self.ser_lock:
                chunk = self.ser.read(chunk_size)

            if not chunk:
                return []

            self.buffer += chunk

            # —— 解析多帧（可在锁外进行） ——
            results = []
            while True:
                frame, self.buffer = self._find_one_frame(self.buffer)
                if frame is None:
                    self.buffer = self.buffer[-65536:]
                    break

                try:
                    pkg_no, groups = self._parse_frame(frame)
                    # print(f"解析成功: {pkg_no}, {groups}")
                    results.append((pkg_no, groups))
                except Exception as e:
                    print(f"解析错误: {e}")
                    print(f"帧数据: {frame.hex(' ').upper()}")
                    self.buffer = frame[1:] + self.buffer
                    break

            return results

        except Exception as e:
            print(f"❌ 读取数据失败: {e}")
            return []

   



    def _send_cmd(self, cmd: str):
        """发送指令"""
        if not cmd.endswith("\r\n"):
            cmd += "\r\n"
        self.ser.write(cmd.encode("ascii"))
    
    def _read_ack(self, timeout: float = 0.5) -> str:
        """读取ACK响应"""
        self.ser.timeout = timeout
        return self.ser.readline().decode(errors="ignore").strip()
    
    def _find_one_frame(self, buf: bytes) -> Tuple[Optional[bytes], bytes]:
        """查找一帧数据"""
        i = buf.find(self.HDR)
        if i < 0 or len(buf) - i < 6:
            return None, buf
        
        pkg_len = struct.unpack(">H", buf[i+2:i+4])[0]
        total = 2 + 2 + pkg_len
        
        if len(buf) - i < total:
            return None, buf
        
        frame = buf[i:i+total]
        rest = buf[i+total:]
        return frame, rest
    
    def _parse_frame(self, frame: bytes) -> Tuple[int, List[Tuple[float, ...]]]:
        """解析数据帧"""
        check_mode = self.config.get("check_mode", "SUM")
        ch_num = self.config.get("channels", 6)
        
        pkg_len = struct.unpack(">H", frame[2:4])[0]
        payload = frame[4:4+pkg_len]
        
        if len(payload) != pkg_len:
            raise ValueError("Payload长度不匹配")
        
        pkg_no = struct.unpack(">H", payload[:2])[0]
        
        # 校验
        if check_mode.upper() == "CRC32":
            if pkg_len < 2 + 4:
                raise ValueError("CRC32 payload太短")
            body = payload[2:-4]
            recv_crc = struct.unpack("<I", payload[-4:])[0]
            calc_crc = zlib.crc32(body) & 0xFFFFFFFF
            if recv_crc != calc_crc:
                raise ValueError("CRC32校验失败")
        else:
            if pkg_len < 2 + 1:
                raise ValueError("SUM payload太短")
            sum_byte = payload[-1]
            body = payload[2:-1]
            if (sum(payload[:-1]) & 0xFF) != sum_byte and (sum(body) & 0xFF) != sum_byte:
                raise ValueError("SUM校验失败")
        
        # 解析数据
        if len(body) % 4 != 0:
            raise ValueError("数据长度不是4的倍数")
        
        total_floats = len(body) // 4
        if total_floats % ch_num != 0:
            raise ValueError(f"浮点数数量{total_floats}不能被通道数{ch_num}整除")
        
        vals = struct.unpack("<" + "f"*total_floats, body)
        groups = [tuple(vals[i:i+ch_num]) for i in range(0, total_floats, ch_num)]
        
        return pkg_no, groups
    
    def _sync_to_header(self, timeout: float = 1.0) -> bytes:
        """同步到帧头"""
        deadline = time.time() + timeout
        buf = b""
        
        while time.time() < deadline:
            chunk = self.ser.read(512)
            if not chunk:
                continue
            buf += chunk
            i = buf.find(self.HDR)
            if i >= 0:
                return buf[i:]
            buf = buf[-4096:]
        
        return b""
    

    def _restart_stream(self) -> bytes:
        """重新开始数据流（持锁）"""
        with self.ser_lock:
            self.ser.reset_output_buffer()
            self.ser.reset_input_buffer()
            self.ser.write(b"AT+GSD\r\n")
            time.sleep(0.02)
            return self._sync_to_header(timeout=1.0)
