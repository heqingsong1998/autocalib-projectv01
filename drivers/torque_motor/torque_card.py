
from .base import TorqueBaseCard
from dataclasses import dataclass

# 你现有的 SDK（请确保可导入）
import motormaster

from typing import Any, Dict, Optional


@dataclass
class TorqueProfile:
    vmin: float = 0.0
    vmax: float = 10.0
    acc: float = 50.0
    dec: float = 50.0
    stop: float = 0.0
    band: float = 0.1  # 位置判稳带宽（mm）


def _ck(cond: bool, name: str = ""):
    if not cond:
        raise RuntimeError(f"{name} 调用失败")


class TorqueMotorCard(TorqueBaseCard):
    """
    将 motormaster 的 axis 句柄封装为“卡接口”风格，供 UI 使用。
    """
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.axis: Optional[Any] = None
        self.connected: bool = False
        self.profile = TorqueProfile()

    # ============== 连接/断开 ==============
    def connect(self) -> int:
        if self.connected and self.axis:
            return 0
        port = self.cfg.get("port", r"\\.\COM20")
        baud = int(self.cfg.get("baud", 115200))
        slave = int(self.cfg.get("slave", 0))
        self.axis = motormaster.create_axis_modbus_rtu(port, baud, slave)
        try:
            try:
                self.axis.reset_error()
            except Exception:
                pass
            self.set_servo(True)
            self.connected = True
            return 0
        except Exception as e:
            try:
                motormaster.destroy_axis(self.axis)
            except Exception:
                pass
            self.axis = None
            self.connected = False
            raise e

    def disconnect(self) -> int:
        if not self.axis:
            self.connected = False
            return 0
        try:
            self.set_servo(False)
        except Exception:
            pass
        try:
            motormaster.destroy_axis(self.axis)
        finally:
            self.axis = None
            self.connected = False
        return 0

    # ============== 伺服/参数 ==============
    def set_servo(self, on: bool) -> int:
        _ck(self.axis is not None, "set_servo_on_off")
        self.axis.set_servo_on_off(bool(on))
        return 0

    def set_profile(self, axis: int, vmin: float, vmax: float, acc: float, dec: float, stop: float = 0.0) -> int:
        self.profile.vmin = float(vmin)
        self.profile.vmax = float(vmax)
        self.profile.acc = float(acc)
        self.profile.dec = float(dec)
        self.profile.stop = float(stop)
        return 0

    def set_band(self, axis: int, band_mm: float) -> int:
        self.profile.band = float(band_mm)
        return 0

    # ============== 回原点参数配置（独立） ==============
    def config_home(self, velocity: float, acceleration: float, deacceleration: float) -> int:
        """
        配置回原点速度/加减速度。用法：
            card.connect()
            card.config_home(100, 500, 500)
            card.home(0)
        """
        _ck(self.axis is not None, "config_motion")
        # 底层真实函数名：ConfigMotion
        self.axis.config_motion(float(velocity), float(acceleration), float(deacceleration))
        return 0


    # ============== 运动控制 ==============
    def move_abs(self, axis: int, pos: float) -> int:
        _ck(self.axis is not None, "move_absolute")
        self.axis.move_absolute(float(pos),
                                float(self.profile.vmax),
                                float(self.profile.acc),
                                float(self.profile.dec),
                                float(self.profile.band))
        return 0

    def move_rel(self, axis: int, dist: float) -> int:
        _ck(self.axis is not None, "move_relative")
        self.axis.move_relative(float(dist),
                                float(self.profile.vmax),
                                float(self.profile.acc),
                                float(self.profile.dec),
                                float(self.profile.band))
        return 0

    def stop(self, axis: int, mode: int = 0) -> int:
        _ck(self.axis is not None, "stop")
        self.axis.stop()
        return 0

    def is_done(self, axis: int) -> bool:
        _ck(self.axis is not None, "is_done")
        try:
            return not bool(self.axis.is_moving())
        except Exception:
            return False

    def get_position(self, axis: int) -> float:
        _ck(self.axis is not None, "position")
        return float(self.axis.position())

    def get_velocity(self, axis: int) -> float:
        _ck(self.axis is not None, "velocity")
        return float(self.axis.velocity())

    # ============== 回零/位置 ==============
    def home(self, axis: int) -> int:
        _ck(self.axis is not None, "go_home")
        self.axis.go_home()
        return 0

    def set_position(self, axis: int, pos: float = 0.0) -> int:
        _ck(self.axis is not None, "set_position")
        for name in ("set_position", "set_current_position", "set_pos"):
            fn = getattr(self.axis, name, None)
            if callable(fn):
                fn(float(pos))
                return 0
        raise RuntimeError("底层 SDK 未提供设置当前位置的方法")

    # ============== 状态/扩展 ==============
    def read_status(self) -> Dict[str, Any]:
        _ck(self.axis is not None, "read_status")
        pos = float(self.axis.position())
        vel = float(self.axis.velocity())
        try:
            force = float(self.axis.force_sensor())
        except Exception:
            force = float("nan")
        try:
            moving = bool(self.axis.is_moving())
        except Exception:
            moving = False
        return dict(position=pos, velocity=vel, force=force, moving=moving)

    def push(self, force_n: float, dist_mm: float, vel_mm_s: float) -> int:
        _ck(self.axis is not None, "push")
        self.axis.push(float(force_n), float(dist_mm), float(vel_mm_s))
        return 0

    def precise_push(self, force_n: float, dist_mm: float, vel_mm_s: float, band_n: float, chk_ms: int) -> int:
        _ck(self.axis is not None, "precise_push")
        self.axis.precise_push(float(force_n), float(dist_mm), float(vel_mm_s),
                               float(band_n), int(chk_ms))
        return 0

    def trigger_command(self, code: int) -> int:
        _ck(self.axis is not None, "trig_command")
        # 底层真实函数名：trig_command
        self.axis.trig_command(int(code))
        return 0

    # ============== 可选 ==============
    def get_version(self) -> Any:
        _ck(self.axis is not None, "get_version")
        return self.axis.get_version()