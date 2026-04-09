# drivers/motioncard/ltsmc_dll.py
import os
import sys
import platform
import time
import ctypes
from ctypes import c_short, c_ushort, c_uint32, c_double, c_char_p, WinDLL

from .base import MotionCard


def _ck(ret, name=""):
    """检查 DLL 函数返回值"""
    if ret != 0:
        raise RuntimeError(f"{name} 调用失败, 错误码={ret}")


class LTSMCMotionCard(MotionCard):
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.cn = c_ushort(0)
        self.connected = False

        # ---- 加载 DLL ----
        dll_path = cfg["dll_path"]
        if not os.path.isabs(dll_path):
            dll_path = os.path.abspath(dll_path)

        if platform.system() != "Windows":
            raise OSError("LTSMC.dll 仅支持 Windows")

        if sys.maxsize <= 2**32:
            raise OSError("请使用 64 位 Python (需匹配 64 位 LTSMC.dll)")

        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"LTSMC.dll 未找到: {dll_path}")

        self.smc = WinDLL(dll_path)
        smc = self.smc

        # ---- 必备函数声明 ----
        smc.smc_board_init.argtypes = [c_ushort, c_ushort, c_char_p, c_uint32]
        smc.smc_board_init.restype = c_short

        smc.smc_board_close.argtypes = [c_ushort]
        smc.smc_board_close.restype = c_short

        smc.smc_pmove_unit.argtypes = [c_ushort, c_ushort, c_double, c_ushort]
        smc.smc_pmove_unit.restype = c_short

        smc.smc_check_done.argtypes = [c_ushort, c_ushort]
        smc.smc_check_done.restype = c_short

        smc.smc_stop.argtypes = [c_ushort, c_ushort, c_ushort]
        smc.smc_stop.restype = c_short

        smc.smc_get_position_unit.argtypes = [c_ushort, c_ushort, ctypes.POINTER(c_double)]
        smc.smc_get_position_unit.restype = c_short

        # ---- 限位/原点相关 ----
        smc.smc_set_el_mode.argtypes = [c_ushort, c_ushort, c_ushort, c_ushort, c_ushort]
        smc.smc_set_el_mode.restype = c_short

        smc.smc_set_home_pin_logic.argtypes = [c_ushort, c_ushort, c_ushort, c_ushort]
        smc.smc_set_home_pin_logic.restype = c_short

        smc.smc_home_move.argtypes = [c_ushort, c_ushort]
        smc.smc_home_move.restype = c_short

        smc.smc_get_home_result.argtypes = [c_ushort, c_ushort, ctypes.POINTER(c_ushort)]
        smc.smc_get_home_result.restype = c_short

        smc.smc_set_home_profile_unit.argtypes = [c_ushort, c_ushort, c_double, c_double, c_double, c_double]
        smc.smc_set_home_profile_unit.restype = c_short

        smc.smc_set_position_unit.argtypes = [c_ushort, c_ushort, c_double]
        smc.smc_set_position_unit.restype  = c_short

        # ---- 读取 IO 状态 ----
        smc.smc_axis_io_status.argtypes = [c_ushort, c_ushort]
        smc.smc_axis_io_status.restype = c_uint32

        smc.smc_read_org_pin.argtypes = [c_ushort, c_ushort]
        smc.smc_read_org_pin.restype = c_short
        
        # 设置脉冲模式
        smc.smc_set_pulse_outmode.argtypes = [c_ushort, c_ushort, c_ushort]
        smc.smc_set_pulse_outmode.restype = c_short
        #设置脉冲当量
        smc.smc_set_equiv.argtypes = [c_ushort, c_ushort, c_double]
        smc.smc_set_equiv.restype  = c_short
        #设置速度模式
        smc.smc_set_profile_unit.argtypes = [
                                                c_ushort,  # ConnectNo
                                                c_ushort,  # axis
                                                c_double,  # Min_Vel
                                                c_double,  # Max_Vel
                                                c_double,  # Tacc
                                                c_double,  # Tdec
                                                c_double   # Stop_Vel
                                            ]
        smc.smc_set_profile_unit.restype = c_short

        smc.smc_set_homemode.argtypes = [
                                                c_ushort,   # ConnectNo
                                                c_ushort,   # axis
                                                c_ushort,   # home_dir
                                                c_double,   # vel_mode
                                                c_ushort,   # Mode
                                                c_ushort    # source
]
        smc.smc_set_homemode.restype = c_short

        #设置电子凸轮
        smc.smc_cam_table_unit.argtypes = [
            c_ushort,              # ConnectNo
            c_ushort,              # MasterAxisNo
            c_ushort,              # SlaveAxisNo
            c_uint32,              # Count
            ctypes.POINTER(c_double),  # pMasterPos
            ctypes.POINTER(c_double),  # pSlavePos
            c_ushort               # SrcMode: 0=主轴指令位置, 1=主轴反馈位置
        ]
        smc.smc_cam_table_unit.restype = c_short

        # short smc_cam_move(WORD ConnectNo, WORD AxisNo);
        smc.smc_cam_move.argtypes = [
            c_ushort,              # ConnectNo
            c_ushort               # AxisNo (从轴)
        ]
        smc.smc_cam_move.restype = c_short

    
    # ================= 基本接口 =================
    def connect(self):
        """连接控制卡"""
        if self.connected:
            return 0

        # 从配置中获取IP地址
        if "tcp" in self.cfg and "ip" in self.cfg["tcp"]:
            ip_address = self.cfg["tcp"]["ip"]
            ip_bytes = ip_address.encode("ascii")  # 转换为字节串
        else:
            raise ValueError("配置文件中未找到TCP IP地址")
        
        ret = self.smc.smc_board_init(0, 2, ip_bytes, 0)
        
        print(f"连接到IP: {ip_address}, ret={ret}")
        _ck(ret, "smc_board_init")
        self.connected = True
        return ret

    def disconnect(self):
        if not self.connected:
            return
        _ck(self.smc.smc_board_close(self.cn), "smc_board_close")
        self.connected = False

    def move_abs(self, axis: int, pos: float):
        _ck(self.smc.smc_pmove_unit(self.cn, c_ushort(axis), c_double(pos), c_ushort(1)),
            "smc_pmove_unit(abs)")

    def move_rel(self, axis: int, dist: float):
        _ck(self.smc.smc_pmove_unit(self.cn, c_ushort(axis), c_double(dist), c_ushort(0)),
            "smc_pmove_unit(rel)")

    def stop(self, axis: int, mode: int = 0):
        _ck(self.smc.smc_stop(self.cn, c_ushort(axis), c_ushort(mode)), "smc_stop")

    def is_done(self, axis: int) -> bool:
        ret = self.smc.smc_check_done(self.cn, c_ushort(axis))
        return ret == 1

    def get_position(self, axis: int) -> float:
        val = c_double()
        _ck(self.smc.smc_get_position_unit(self.cn, c_ushort(axis), ctypes.byref(val)),
            "smc_get_position_unit")
        return val.value
    def set_pulse_mode(self, axis: int, mode: int = 0):
        """
        设置脉冲输出模式
        mode: 0=脉冲+方向, 1=双脉冲, 2=正交脉冲
        """
        _ck(self.smc.smc_set_pulse_outmode(self.cn, c_ushort(axis), c_ushort(mode)),
            "smc_set_pulse_outmode")

    def set_equiv(self, axis: int, pulses_per_unit: float):
        """
        设置脉冲当量 (多少脉冲=1个unit)
        例如：丝杆2mm，细分800 → equiv=400 脉冲/mm
        """
        _ck(self.smc.smc_set_equiv(self.cn, c_ushort(axis), c_double(pulses_per_unit)),
            "smc_set_equiv")

    def set_profile(self, axis: int, vmin: float, vmax: float, acc: float, dec: float, stop: float = 0.0):
            """
            设置速度曲线 (单位版)
            axis: 轴号
            vmin: 起始速度 (unit/s)
            vmax: 最大速度 (unit/s)
            acc : 加速时间 (s)
            dec : 减速时间 (s)
            stop: 停止速度 (unit/s, 通常为0)
            """
            _ck(self.smc.smc_set_profile_unit(
                self.cn,
                c_ushort(axis),
                c_double(vmin),
                c_double(vmax),
                c_double(acc),
                c_double(dec),
                c_double(stop)
            ), "smc_set_profile_unit")


    # ================= 限位/原点 =================
    def set_home_mode(self, axis: int,
                    home_dir: int = 0,
                    vel_mode: float = 1.0,
                    mode: int = 1,
                    source: int = 0):
        """
        设置回原点模式
        home_dir : 0=负向, 1=正向
        vel_mode : 回零速度模式 (一般填1，表示用 smc_set_home_profile_unit 的速度)
        mode     : 回零模式 (0=一次回零, 1=一次回零+回找)
        source   : 回零信号来源 (通常=0=标准ORG端口)
        """
        _ck(self.smc.smc_set_homemode(
            self.cn,
            c_ushort(axis),
            c_ushort(home_dir),
            c_double(vel_mode),
            c_ushort(mode),
            c_ushort(source)
        ), "smc_set_homemode")




    def set_el_mode(self, axis: int, enable: int = 3, logic: int = 0, mode: int = 1):
        """配置硬件限位: enable=3只正限位, logic=0低电平有效, mode=1减速停"""
        _ck(self.smc.smc_set_el_mode(self.cn, c_ushort(axis),
                                     c_ushort(enable), c_ushort(logic), c_ushort(mode)),
            "smc_set_el_mode")

    def set_home_logic(self, axis: int, org_logic: int = 1, filter_time: int = 0):
        """配置原点信号逻辑: org_logic=0低有效(常开),1高有效(常闭)"""
        _ck(self.smc.smc_set_home_pin_logic(self.cn, c_ushort(axis),
                                            c_ushort(org_logic), c_ushort(filter_time)),
            "smc_set_home_pin_logic")

    def set_home_profile(self, axis: int, low_vel: float, high_vel: float, tacc: float, tdec: float):
        _ck(self.smc.smc_set_home_profile_unit(self.cn, c_ushort(axis),
                                               c_double(low_vel), c_double(high_vel),
                                               c_double(tacc), c_double(tdec)),
            "smc_set_home_profile_unit")

    def home(self, axis: int):
        _ck(self.smc.smc_home_move(self.cn, c_ushort(axis)), "smc_home_move")

    def is_home_done(self, axis: int) -> bool:
        state = c_ushort()
        _ck(self.smc.smc_get_home_result(self.cn, c_ushort(axis), ctypes.byref(state)),
            "smc_get_home_result")
        return state.value == 1
    
    def set_position(self, axis: int, pos: float = 0.0):
        """设置当前位置寄存器数值（通常回零后调用，清零位置）"""
        _ck(self.smc.smc_set_position_unit(self.cn, c_ushort(axis), c_double(pos)),
            "smc_set_position_unit")


    # ================= IO 状态 =================
    def read_axis_io(self, axis: int) -> dict:
        """一次性读取轴IO信号状态 (见表3.2)"""
        mask = self.smc.smc_axis_io_status(self.cn, c_ushort(axis))
        return {
            "alm": bool(mask & (1 << 0)),   # 报警
            "pel": bool(mask & (1 << 1)),   # 正限位
            "nel": bool(mask & (1 << 2)),   # 负限位
            "emg": bool(mask & (1 << 3)),   # 急停
            "org": bool(mask & (1 << 4)),   # 原点
            "slp": bool(mask & (1 << 6)),   # 正软限位
            "sln": bool(mask & (1 << 7)),   # 负软限位
            "inp": bool(mask & (1 << 8)),   # 到位
            "ez":  bool(mask & (1 << 9)),   # EZ
        }

    def read_org_signal(self, axis: int) -> bool:
        return self.read_axis_io(axis)["org"]

    def read_pel_signal(self, axis: int) -> bool:
        return self.read_axis_io(axis)["pel"]

    def read_org_signal_direct(self, axis: int) -> bool:
        """
        直接读取原点ORG信号状态
        True=有效, False=无效
        """
        ret = self.smc.smc_read_org_pin(self.cn, c_ushort(axis))
        if ret < 0:
            raise RuntimeError(f"smc_read_org_pin 调用失败, ret={ret}")
        return bool(ret)

        # ================= 电子凸轮（Cam） =================
    def cam_load_table(self, master_axis: int, slave_axis: int,
                       master_pos: list[float], slave_pos: list[float],
                       src_mode: int = 0):
        """
        下载电子凸轮表（位置映射表）
        - master_pos / slave_pos: 等长数组；相对位置模式，首点建议为 (0, 0)，master_pos 单调
        - src_mode: 0=以主轴指令位置为基准，1=以主轴反馈位置为基准
        """
        if len(master_pos) != len(slave_pos):
            raise ValueError("master_pos 与 slave_pos 长度不一致")

        n = len(master_pos)
        if n < 2:
            raise ValueError("凸轮表至少需要 2 个点")

        m_arr = (c_double * n)(*master_pos)
        s_arr = (c_double * n)(*slave_pos)

        _ck(self.smc.smc_cam_table_unit(
            self.cn,
            c_ushort(master_axis),
            c_ushort(slave_axis),
            c_uint32(n),
            m_arr,
            s_arr,
            c_ushort(src_mode)
        ), "smc_cam_table_unit")

    def cam_start_follow(self, slave_axis: int):
        """
        让从轴进入电子凸轮跟随模式。
        注意：通常要求主轴在启动前处于静止状态，随后再启动主轴运动。
        """
        _ck(self.smc.smc_cam_move(self.cn, c_ushort(slave_axis)),
            "smc_cam_move")
