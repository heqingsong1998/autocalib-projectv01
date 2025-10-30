import serial
import time

# ============ 协议常量 ============
FRAME_LEN = 88
HEAD_A = bytes([0x00, 0x00, 0x00, 0x26])
HEAD_B = bytes([0x00, 0x00, 0x01, 0x26])
TAIL   = bytes([0x00]*8)

OFF_HEAD_B = 64
OFF_TAIL   = 80

DATA_A_START, DATA_A_LEN = 4, 60
DATA_B_START, DATA_B_LEN = 68, 12
UNIT_SIZE = 6

# ============ 串口参数 ============
PORT = "COM11"        # 改成你的串口号
BAUD = 115200
TIMEOUT = 0.02

# ============ 缓冲区类 ============
class SerialBuffer:
    def __init__(self, max_bytes=1024*1024):
        self.buf = bytearray()
        self.max = max_bytes

    def append(self, data: bytes):
        self.buf += data
        if len(self.buf) > self.max:
            self.buf = self.buf[-(self.max + FRAME_LEN):]

    def extract_frames(self):
        data = self.buf
        frames = []
        i = 0
        last_cut = 0

        while True:
            idx = data.find(HEAD_A, i)
            if idx < 0:
                break
            if len(data) - idx < FRAME_LEN:
                break

            cand = data[idx:idx + FRAME_LEN]
            if (cand[0:4] == HEAD_A and
                cand[OFF_HEAD_B:OFF_HEAD_B+4] == HEAD_B and
                cand[OFF_TAIL:OFF_TAIL+8] == TAIL):
                frames.append(bytes(cand))
                i = idx + FRAME_LEN
                last_cut = i
            else:
                i = idx + 1

        if last_cut > 0:
            self.buf = self.buf[last_cut:]

        return frames

# ============ 帧解析 ============
def parse_units(block: bytes, base_index: int):
    values = []
    for i in range(len(block) // UNIT_SIZE):
        u = block[i*UNIT_SIZE:(i+1)*UNIT_SIZE]
        # “高字节在前”的无符号 16 位
        val = (u[4] << 8) | u[5]
        values.append(val)
    return values

def parse_frame(frame: bytes):
    data_a = frame[DATA_A_START:DATA_A_START+DATA_A_LEN]
    data_b = frame[DATA_B_START:DATA_B_START+DATA_B_LEN]
    vals = parse_units(data_a, 0) + parse_units(data_b, 10)
    return vals  # 共 12 个数值

# ============ 主循环 ============
def main():
    ser = serial.Serial(PORT, BAUD, timeout=TIMEOUT)
    sbuf = SerialBuffer(2*1024*1024)

    print("开始接收数据帧并解析…… (Ctrl+C 退出)")
    try:
        while True:
            chunk = ser.read(4096)
            if chunk:
                sbuf.append(chunk)
                frames = sbuf.extract_frames()
                for fr in frames:
                    values = parse_frame(fr)
                    # 打印12个数值
                    print("解析出的12个数值：", values)
            else:
                time.sleep(0.002)
    except KeyboardInterrupt:
        print("\n已退出。")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
