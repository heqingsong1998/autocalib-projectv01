
from collections import deque
##动态补偿python程序
# 封装为可复用的动态补偿滤波器类（X方向）
class DynamicCompensator:
    # 封装参数
    AXIS_PARAMS = {
        'x_pos': {  # X轴参数
            "alpha_n": 0.99999009,
            "beta_n": 0.00000867,
            "alpha_p": [0.99990083, 0.99990036, 0.99910478, 0, 0, 0, 0],
            "beta_p": [0.06427631, 0.00615128, 0.00999999,0, 0, 0, 0]
        },
        'y_pos': {  # y轴参数
            "alpha_n": 0.999995,
            "beta_n": 0.00000005,
            "alpha_p": [0.9999, 0.9995, 0.996, 0, 0, 0, 0],
            "beta_p": [0.015, 0.025, 0.03, 0, 0, 0, 0]
        },
        'x_neg': {  # X轴参数
            "alpha_n": 0.99999033,
            "beta_n": 0.00000214,
            "alpha_p": [0.99999990, 0.99999989,0, 0, 0, 0, 0],
            "beta_p": [0.00000290, 0.00000032, 0, 0, 0, 0, 0]
        },
        'y_neg': {  # y轴参数
            "alpha_n": 0.999995,
            "beta_n": 0.00000005,
            "alpha_p": [0.9999, 0.9995, 0.996, 0, 0, 0, 0],
            "beta_p": [0.015, 0.025, 0.03, 0, 0, 0, 0]
        },


        'z': {  # z轴参数
            "alpha_n": 0.99999972,
            "beta_n": 0.00000199,
            "alpha_p": [0.99991031,0.99991423, 0.99901882, 0.985,0.989,0.987, 0.8765],
            "beta_p": [0.00011295, 0.00005316, 0.08915782, 0.040, 0.065, 0.042, 0.062]
        }

    }

    def __init__(self, axis_index):
        """
        初始化动态补偿器
        :param axis_index: 轴索引 x_pos y_pos x_neg y_neg z
        """
        if axis_index not in self.AXIS_PARAMS:
            raise ValueError(f"无效的轴索引: {axis_index}")
        self.params = self.AXIS_PARAMS[axis_index]

        # 状态变量
        self.COEXn = 0.1
        self.COEXp = [0.0 for _ in range(7)]
        self.RawForceOld = 0.0

    def reset(self):
        """重置状态"""
        self.COEXn = 0.0
        self.COEXp = [0.0 for _ in range(7)]
        self.RawForceOld = 0.0

    def update(self, raw_force):
        """
        更新动态补偿值
        :param raw_force: 原始力值
        :return: 补偿后的力值
        """
        # 差值
        diff = raw_force - self.RawForceOld
        self.RawForceOld = raw_force

        # 更新 COEXn（趋势估计）
        self.COEXn = self.COEXn * self.params["alpha_n"] + (raw_force - self.COEXn) * self.params["beta_n"]

        # 更新各级 IIR 滤波器 只用到四阶 所以使用range(4)
        for i in range(7):
            self.COEXp[i] = self.COEXp[i] * self.params["alpha_p"][i] + diff * self.params["beta_p"][i]

        # 输出最终动态补偿后的电容值，后续步骤应该是标定，单独进行
        compensated_force = (raw_force - self.COEXn + sum(self.COEXp[:7]))
        return compensated_force



# 封装为可复用的单轴迟滞补偿器类（X方向）
class HysteresisCompensator:
    """
    单轴迟滞补偿器 - 使用时需要为每个轴单独实例化
    """

    # 传感器的各轴补偿参数
    COMPENSATION_PARAMS = {
        'x_pos': {'a': -0.0000031893555885, 'b': 0.093387218347826, 'c': -136.2157506041},
        'y_pos': {'a': -0.0000028893555885, 'b': 0.083387218347826, 'c': -126.2157506041},
        'x_neg': {'a': -0.0000035893555885, 'b': 0.103387218347826, 'c': -146.2157506041},
        'y_neg': {'a': -0.0000029893555885, 'b': 0.088387218347826, 'c': -131.2157506041},
        'z': {'a': -9.9874e-06 , 'b': 0.15841, 'c': 0}
    }

    def __init__(self, axis_name):
        """
        初始化指定轴的补偿器

        Args:
            axis_name: 轴名称 ('x_pos', 'y_pos', 'x_neg', 'y_neg', 'z')
        """
        if axis_name not in self.COMPENSATION_PARAMS:
            raise ValueError(f"Invalid axis name: {axis_name}. Must be one of {list(self.COMPENSATION_PARAMS.keys())}")

        self.axis_name = axis_name
        params = self.COMPENSATION_PARAMS[axis_name]
        self.a = params['a']
        self.b = params['b']
        self.c = params['c']

        # 状态变量
        self.queue = deque(maxlen=10)
        self.max_value = 0
        self.up_flag = 0
        self.down_flag = 0
        self.state = 0
        self.compensation_active = False

    def compensate(self, input_value):
        """
        输入轴值，返回补偿后的值

        Args:
            input_value: 轴力值（int）

        Returns:
            补偿后的轴值（int）
        """
        # 只对负值进行补偿
        if input_value > 0:
            return input_value

        # 更新队列
        self.queue.append(input_value)

        # 查找队列最大值
        if len(self.queue) > 0:
            self.max_value = max(self.queue)

            # 下降检测
            if self.max_value - input_value > 30:
                self.down_flag += 1
                self.up_flag = 0
            # 上升检测
            elif input_value - self.max_value > 30:
                self.up_flag += 1
                self.down_flag = 0
            else:
                self.up_flag = 0
                self.down_flag = 0

            # 状态确认
            if self.down_flag >= 3:
                self.state = -1
                self.compensation_active = False
            elif self.up_flag >= 3:
                self.state = 1
                self.compensation_active = True

            # 执行补偿
            if self.compensation_active and self.state == 1:
                abs_value = -input_value
                compensation = int(self.a * abs_value * abs_value +
                                   self.b * abs_value + self.c)
                return input_value + compensation

        return input_value

    def reset(self):
        """重置状态"""
        self.queue.clear()
        self.max_value = 0
        self.up_flag = 0
        self.down_flag = 0
        self.state = 0
        self.compensation_active = False


