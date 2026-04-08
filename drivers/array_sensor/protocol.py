"""阵列触觉传感器帧协议解析。"""
from __future__ import annotations

import struct
from typing import Any, Dict, List, Optional


class ArraySensorProtocol:
    def __init__(self, frame_head: List[int], frame_size: int, data_size: int, payload_sum_bytes: int):
        self.frame_head = frame_head
        self.frame_size = frame_size
        self.data_size = data_size
        self.payload_sum_bytes = payload_sum_bytes
        self.buffer = bytearray()

    def feed(self, chunk: bytes) -> List[Dict[str, Any]]:
        self.buffer += chunk
        frames: List[Dict[str, Any]] = []

        while len(self.buffer) >= self.frame_size:
            start = self._find_head()
            if start < 0:
                self.buffer = self.buffer[-8:]
                break

            if start > 0:
                self.buffer = self.buffer[start:]

            if len(self.buffer) < self.frame_size:
                break

            raw = bytes(self.buffer[: self.frame_size])
            self.buffer = self.buffer[self.frame_size :]
            parsed = self._parse_one(raw)
            if parsed is not None:
                frames.append(parsed)

        return frames

    def _find_head(self) -> int:
        max_idx = len(self.buffer) - self.frame_size
        for i in range(max_idx + 1):
            head = [int.from_bytes(self.buffer[i + j * 2 : i + j * 2 + 2], "little") for j in range(4)]
            if head == self.frame_head:
                return i
        return -1

    def _parse_one(self, frame: bytes) -> Optional[Dict[str, Any]]:
        checksum_calc = sum(frame[: self.payload_sum_bytes]) & 0xFFFF
        checksum_recv = int.from_bytes(frame[self.payload_sum_bytes : self.payload_sum_bytes + 2], "little")
        if checksum_calc != checksum_recv:
            return None

        sensor_data = [struct.unpack_from("<h", frame, 8 + i * 2)[0] for i in range(self.data_size)]
        temp1_int = struct.unpack_from("<h", frame, 136)[0]
        temp1_frac = struct.unpack_from("<h", frame, 138)[0]
        temp2_int = struct.unpack_from("<h", frame, 140)[0]
        temp2_frac = struct.unpack_from("<h", frame, 142)[0]

        return {
            "raw": sensor_data,
            "temp1": temp1_int + temp1_frac * 0.001,
            "temp2": temp2_int + temp2_frac * 0.001,
        }
