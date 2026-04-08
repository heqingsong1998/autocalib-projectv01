"""阵列触觉传感器串口驱动。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import serial

from .base import ArraySensorBase
from .processor import ArraySensorProcessor
from .protocol import ArraySensorProtocol


class ArraySensor(ArraySensorBase):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        serial_cfg = config["serial"]
        frame_cfg = config["frame"]
        self.ser = None
        self.protocol = ArraySensorProtocol(
            frame_head=frame_cfg["head"],
            frame_size=int(frame_cfg["size"]),
            data_size=int(frame_cfg["data_size"]),
            payload_sum_bytes=int(frame_cfg["payload_sum_bytes"]),
        )
        self.processor = ArraySensorProcessor(config["processing"])
        self.serial_cfg = serial_cfg

    def connect(self) -> bool:
        try:
            self.ser = serial.Serial(
                port=self.serial_cfg["port"],
                baudrate=self.serial_cfg["baud"],
                timeout=float(self.serial_cfg.get("timeout", 0.03)),
            )
            self.connected = True
            return True
        except Exception:
            self.connected = False
            return False

    def disconnect(self) -> bool:
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.connected = False
            return True
        except Exception:
            return False

    def zero(self) -> None:
        last = self.read_frame()
        if not last:
            return
        self.processor.zero(last["raw"], last["temp1"], last["temp2"])

    def read_frame(self) -> Optional[Dict[str, Any]]:
        if not self.connected:
            return None
        chunk = self.ser.read(self.ser.in_waiting or 1)
        if not chunk:
            return None
        parsed_list = self.protocol.feed(chunk)
        if not parsed_list:
            return None
        parsed = parsed_list[-1]
        result = self.processor.process(parsed["raw"], parsed["temp1"], parsed["temp2"])
        result.update(parsed)
        result["timestamp"] = datetime.now().isoformat(timespec="milliseconds")
        return result
