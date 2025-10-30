from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Union

class MotionStatus(Enum):
    """运动状态枚举"""
    IDLE = "idle"           # 空闲
    RUNNING = "running"     # 运行中
    DONE = "done"           # 完成
    ERROR = "error"         # 错误
    HOMING = "homing"       # 回零中

class MotionCard(ABC):
    """运动控制卡抽象基类"""
    
    # ================= 连接管理 =================
    @abstractmethod
    def connect(self):
        """连接控制卡"""
        pass
    
    @abstractmethod
    def disconnect(self):
        """断开控制卡连接"""
        pass
    
    # ================= 基本运动控制 =================
    @abstractmethod
    def move_abs(self, axis: int, pos: float):
        """绝对位置运动
        
        Args:
            axis: 轴号
            pos: 目标位置
        """
        pass
    
    @abstractmethod
    def move_rel(self, axis: int, dist: float):
        """相对位置运动
        
        Args:
            axis: 轴号
            dist: 相对距离
        """
        pass
    
    @abstractmethod
    def stop(self, axis: int, mode: int = 0):
        """停止运动
        
        Args:
            axis: 轴号
            mode: 停止模式 (0=减速停止, 1=急停)
        """
        pass
    
    @abstractmethod
    def is_done(self, axis: int) -> bool:
        """检查运动是否完成
        
        Args:
            axis: 轴号
            
        Returns:
            True: 运动完成, False: 运动中
        """
        pass
    
    @abstractmethod
    def get_position(self, axis: int) -> float:
        """获取当前位置
        
        Args:
            axis: 轴号
            
        Returns:
            当前位置值
        """
        pass
    
    # ================= 限位和原点 =================
    @abstractmethod
    def set_el_mode(self, axis: int, enable: int = 3, logic: int = 0, mode: int = 1):
        """配置硬件限位
        
        Args:
            axis: 轴号
            enable: 使能模式
            logic: 逻辑电平
            mode: 限位模式
        """
        pass
    
    @abstractmethod
    def set_home_logic(self, axis: int, org_logic: int = 1, filter_time: int = 0):
        """配置原点信号逻辑
        
        Args:
            axis: 轴号
            org_logic: 原点逻辑 (0=常开, 1=常闭)
            filter_time: 滤波时间
        """
        pass
    
    @abstractmethod
    def set_home_profile(self, axis: int, low_vel: float, high_vel: float, 
                        tacc: float, tdec: float):
        """设置回零速度参数
        
        Args:
            axis: 轴号
            low_vel: 低速(精确定位速度)
            high_vel: 高速(寻找原点速度)  
            tacc: 加速时间
            tdec: 减速时间
        """
        pass
    
    @abstractmethod
    def home(self, axis: int):
        """执行回零操作
        
        Args:
            axis: 轴号
        """
        pass
    
    @abstractmethod
    def is_home_done(self, axis: int) -> bool:
        """检查回零是否完成
        
        Args:
            axis: 轴号
            
        Returns:
            True: 回零完成, False: 回零中
        """
        pass
    
    # ================= IO状态读取 =================
    @abstractmethod
    def read_axis_io(self, axis: int) -> Dict[str, bool]:
        """读取轴IO状态
        
        Args:
            axis: 轴号
            
        Returns:
            IO状态字典，包含以下键值:
            - alm: 报警信号
            - pel: 正限位信号
            - nel: 负限位信号  
            - emg: 急停信号
            - org: 原点信号
            - slp: 正软限位
            - sln: 负软限位
            - inp: 到位信号
            - ez: EZ信号
        """
        pass
    
    @abstractmethod
    def read_org_signal(self, axis: int) -> bool:
        """读取原点信号
        
        Args:
            axis: 轴号
            
        Returns:
            True: 在原点, False: 不在原点
        """
        pass
    
    @abstractmethod
    def read_pel_signal(self, axis: int) -> bool:
        """读取正限位信号
        
        Args:
            axis: 轴号
            
        Returns:
            True: 正限位触发, False: 正限位正常
        """
        pass
    
    @abstractmethod
    def read_org_signal_direct(self, axis: int) -> bool:
        """直接读取原点信号
        
        Args:
            axis: 轴号
            
        Returns:
            True: 原点信号有效, False: 原点信号无效
        """
        pass
    @abstractmethod
    def set_position(self, axis: int, pos: float = 0.0):
        """设置当前位置寄存器数值（通常回零后调用，清零位置）

        Args:
            axis: 轴号
            pos: 目标位置
        """
        pass    

    @abstractmethod
    def set_pulse_mode(self, axis: int, mode: int = 0):
        """设置脉冲输出模式

        Args:
            axis: 轴号
            mode: 脉冲模式 (0=脉冲+方向, 1=双脉冲, 2=正交脉冲)      
        """
        pass
    @abstractmethod
    def set_equiv(self, axis: int, pulses_per_unit: float):
        """
        设置脉冲当量 (多少脉冲=1个unit)
        例如：丝杆2mm，细分800 → equiv=400 脉冲/mm

        Args:
            axis: 轴号
            pulses_per_unit: 脉冲当量 (脉冲数/单位距离)
        """
        pass
    @abstractmethod
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
        pass
    @abstractmethod
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
        pass
    @abstractmethod
    def cam_load_table(self, master_axis: int, slave_axis: int,
                       master_pos: list[float], slave_pos: list[float],
                       src_mode: int = 0):
        """
        下载电子凸轮表（位置映射表）
        - master_pos / slave_pos: 等长数组；相对位置模式，首点建议为 (0, 0)，master_pos 单调
        - src_mode: 0=以主轴指令位置为基准，1=以主轴反馈位置为基准
        """
        pass
    
    @abstractmethod
    def cam_start_follow(self, slave_axis: int):
        """
        让从轴进入电子凸轮跟随模式。
        注意：通常要求主轴在启动前处于静止状态，随后再启动主轴运动。
        """
        pass
