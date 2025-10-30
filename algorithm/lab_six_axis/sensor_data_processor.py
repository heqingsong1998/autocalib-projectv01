
from collections import deque

#温度补偿器
class TemperatureCompensator:
    """
    温度补偿器 - 为每个轴提供独立的温度补偿参数（区分正负方向）
    """

    # 各轴温度补偿系数 - 区分 positive 和 negative
    TEMPERATURE_COEFFICIENTS = {
        'fx': {'positive': 0, 'negative': 0},  # FX轴温度补偿系数
        'fy': {'positive': 0, 'negative': 0},  # FY轴温度补偿系数
        'fz': {'positive': -0.47, 'negative': -0.47},  # FZ轴温度补偿系数
        'mx': {'positive': 0, 'negative': 0},  # MX轴温度补偿系数
        'my': {'positive': 0, 'negative': 0},  # MY轴温度补偿系数
        'mz': {'positive': 0, 'negative': 0}   # MZ轴温度补偿系数
    }

    def __init__(self, axis_name):
        """
        初始化温度补偿器

        Args:
            axis_name: 轴名称 ('fx', 'fy', 'fz', 'mx', 'my', 'mz')
        """
        if axis_name not in self.TEMPERATURE_COEFFICIENTS:
            raise ValueError(
                f"Invalid axis name: {axis_name}. Must be one of {list(self.TEMPERATURE_COEFFICIENTS.keys())}")

        self.axis_name = axis_name
        self.coefficients = self.TEMPERATURE_COEFFICIENTS[axis_name]

    def compensate(self, force_value, temperature_delta):
        """
        计算温度补偿后的力值

        Args:
            force_value: 原始力值
            temperature_delta: 温度差值（当前温度 - 基准温度）

        Returns:
            补偿后的力值
        """
        # 根据力值的正负选择对应的补偿系数
        direction = 'positive' if force_value >= 0 else 'negative'
        coefficient = self.coefficients[direction]
        
        compensation = temperature_delta * coefficient
        return force_value + compensation

    def reset(self):
        """重置状态（温度补偿器无状态，此方法为保持接口一致性）"""
        pass




##动态补偿python程序
# 封装为可复用的动态补偿滤波器类
class DynamicCompensator:
    # 封装参数 - 区分 positive 和 negative
    AXIS_PARAMS = {
        'fx': {
            'positive': {  # X轴正向参数
                "alpha_n": 0.99999009,
                "beta_n": 0.00000867,
                "alpha_p": [1, 1, 1, 0, 0, 0, 0],
                "beta_p": [0, 0, 0, 0, 0, 0, 0]
            },
            'negative': {  # X轴负向参数
                "alpha_n": 0.99999009,
                "beta_n": 0.00000867,
                "alpha_p": [1, 1, 1, 0, 0, 0, 0],
                "beta_p": [0, 0, 0, 0, 0, 0, 0]
            }
        },
        'fy': {
            'positive': {  # Y轴正向参数
                "alpha_n": 0.999995,
                "beta_n": 0.00000005,
                "alpha_p": [1, 1, 1, 0, 0, 0, 0],
                "beta_p": [0, 0, 0, 0, 0, 0, 0]
            },
            'negative': {  # Y轴负向参数
                "alpha_n": 0.999995,
                "beta_n": 0.00000005,
                "alpha_p": [1, 1, 1, 0, 0, 0, 0],
                "beta_p": [0, 0, 0, 0, 0, 0, 0]
            }
        },
        'fz': {
            'positive': {  # Z轴正向参数
                "alpha_n": 0.99999033,
                "beta_n": 0.00000214,
                "alpha_p": [0.99990888, 0.99998743, 0.99998951, 0.99900792, 0, 0, 0],
                "beta_p": [0.00000434, 0.100000, 0.04256439, 0.04707234, 0, 0, 0]
            },
            'negative': {  # Z轴负向参数
                "alpha_n": 0.99999033,
                "beta_n": 0.00000214,
                "alpha_p": [0.99990888, 0.99998743, 0.99998951, 0.99900792, 0, 0, 0],
                "beta_p": [0.00000434, 0.100000, 0.04256439, 0.04707234, 0, 0, 0]
            }
        },
        'mx': {
            'positive': {  # MX轴正向参数
                "alpha_n": 0.999995,
                "beta_n": 0.00000005,
                "alpha_p": [1, 1, 1, 0, 0, 0, 0],
                "beta_p": [0, 0, 0, 0, 0, 0, 0]
            },
            'negative': {  # MX轴负向参数
                "alpha_n": 0.999995,
                "beta_n": 0.00000005,
                "alpha_p": [1, 1, 1, 0, 0, 0, 0],
                "beta_p": [0, 0, 0, 0, 0, 0, 0]
            }
        },
        'my': {
            'positive': {  # MY轴正向参数
                "alpha_n": 0.9990,
                "beta_n": 0.0000050,
                "alpha_p": [1, 1, 1, 0, 0, 0, 0],
                "beta_p": [0, 0, 0, 0, 0, 0, 0]
            },
            'negative': {  # MY轴负向参数
                "alpha_n": 0.9990,
                "beta_n": 0.0000050,
                "alpha_p": [1, 1, 1, 0, 0, 0, 0],
                "beta_p": [0, 0, 0, 0, 0, 0, 0]
            }
        },
        'mz': {
            'positive': {  # MZ轴正向参数
                "alpha_n": 0.9990,
                "beta_n": 0.0000050,
                "alpha_p": [1, 1, 1, 0, 0, 0, 0],
                "beta_p": [0, 0, 0, 0, 0, 0, 0]
            },
            'negative': {  # MZ轴负向参数
                "alpha_n": 0.9990,
                "beta_n": 0.0000050,
                "alpha_p": [1, 1, 1, 0, 0, 0, 0],
                "beta_p": [0, 0, 0, 0, 0, 0, 0]
            }
        }
    }

    def __init__(self, axis_index):
        """
        初始化动态补偿器
        :param axis_index: 轴索引 fx fy fz mx my mz
        """
        if axis_index not in self.AXIS_PARAMS:
            raise ValueError(f"无效的轴索引: {axis_index}")
        self.axis_index = axis_index
        self.all_params = self.AXIS_PARAMS[axis_index]

        # 状态变量 - 为正负方向分别维护状态
        self.COEXn_pos = 0.1
        self.COEXp_pos = [0.0 for _ in range(7)]
        self.RawForceOld_pos = 0.0
        
        self.COEXn_neg = 0.1
        self.COEXp_neg = [0.0 for _ in range(7)]
        self.RawForceOld_neg = 0.0

    def reset(self):
        """重置状态"""
        self.COEXn_pos = 0.1
        self.COEXp_pos = [0.0 for _ in range(7)]
        self.RawForceOld_pos = 0.0
        
        self.COEXn_neg = 0.1
        self.COEXp_neg = [0.0 for _ in range(7)]
        self.RawForceOld_neg = 0.0

    def update(self, raw_force):
        """
        更新动态补偿值
        :param raw_force: 原始力值
        :return: 补偿后的力值
        """
        # 根据力值的正负选择对应的参数和状态
        if raw_force >= 0:
            direction = 'positive'
            params = self.all_params['positive']
            COEXn = self.COEXn_pos
            COEXp = self.COEXp_pos
            RawForceOld = self.RawForceOld_pos
        else:
            direction = 'negative'
            params = self.all_params['negative']
            COEXn = self.COEXn_neg
            COEXp = self.COEXp_neg
            RawForceOld = self.RawForceOld_neg

        # 差值
        diff = raw_force - RawForceOld

        # 更新 COEXn（趋势估计）
        COEXn = COEXn * params["alpha_n"] + (raw_force - COEXn) * params["beta_n"]

        # 更新各级 IIR 滤波器 只用到四阶 所以使用range(4)
        for i in range(4):
            COEXp[i] = COEXp[i] * params["alpha_p"][i] + diff * params["beta_p"][i]

        # 输出最终动态补偿后的电容值
        compensated_force = (raw_force - COEXn + sum(COEXp[:4]))

        # 保存状态到对应方向
        if raw_force >= 0:
            self.COEXn_pos = COEXn
            self.COEXp_pos = COEXp
            self.RawForceOld_pos = raw_force
        else:
            self.COEXn_neg = COEXn
            self.COEXp_neg = COEXp
            self.RawForceOld_neg = raw_force

        return compensated_force



# 封装为可复用的单轴迟滞补偿器类
class HysteresisCompensator:
    """
    单轴迟滞补偿器 - 使用时需要为每个轴单独实例化（区分正负方向）
    """

    # 传感器的各轴补偿参数 - 区分 positive 和 negative
    COMPENSATION_PARAMS = {
        'fx': {
            'positive': {'a': -0.0000031893555885, 'b': 0.093387218347826, 'c': -136.2157506041},
            'negative': {'a': -0.0000031893555885, 'b': 0.093387218347826, 'c': -136.2157506041}
        },
        'fy': {
            'positive': {'a': -0.0000028893555885, 'b': 0.083387218347826, 'c': -126.2157506041},
            'negative': {'a': -0.0000028893555885, 'b': 0.083387218347826, 'c': -126.2157506041}
        },
        'fz': {
            'positive': {'a': -0.0000035893555885, 'b': 0.103387218347826, 'c': -146.2157506041},
            'negative': {'a': -0.0000035893555885, 'b': 0.103387218347826, 'c': -146.2157506041}
        },
        'mx': {
            'positive': {'a': -0.0000029893555885, 'b': 0.088387218347826, 'c': -131.2157506041},
            'negative': {'a': -0.0000029893555885, 'b': 0.088387218347826, 'c': -131.2157506041}
        },
        'my': {
            'positive': {'a': -9.9874e-06, 'b': 0.15841, 'c': 0},
            'negative': {'a': -9.9874e-06, 'b': 0.15841, 'c': 0}
        },
        'mz': {
            'positive': {'a': -9.9874e-06, 'b': 0.15841, 'c': 0},
            'negative': {'a': -9.9874e-06, 'b': 0.15841, 'c': 0}
        }
    }

    def __init__(self, axis_name):
        """
        初始化指定轴的补偿器

        Args:
            axis_name: 轴名称 ('fx', 'fy', 'fz', 'mx', 'my', 'mz')
        """
        if axis_name not in self.COMPENSATION_PARAMS:
            raise ValueError(f"Invalid axis name: {axis_name}. Must be one of {list(self.COMPENSATION_PARAMS.keys())}")

        self.axis_name = axis_name
        self.all_params = self.COMPENSATION_PARAMS[axis_name]

        # 为正负方向分别维护状态变量
        # 正方向状态
        self.queue_pos = deque(maxlen=10)
        self.max_value_pos = 0
        self.up_flag_pos = 0
        self.down_flag_pos = 0
        self.state_pos = 0
        self.compensation_active_pos = False

        # 负方向状态
        self.queue_neg = deque(maxlen=10)
        self.max_value_neg = 0
        self.up_flag_neg = 0
        self.down_flag_neg = 0
        self.state_neg = 0
        self.compensation_active_neg = False

    def compensate(self, input_value):
        """
        输入轴值，返回补偿后的值

        Args:
            input_value: 轴力值

        Returns:
            补偿后的轴值
        """
        # 根据输入值的正负选择对应的参数和状态
        if input_value >= 0:
            # 正向补偿逻辑
            params = self.all_params['positive']
            
            # 更新队列
            self.queue_pos.append(input_value)

            # 查找队列最大值
            if len(self.queue_pos) > 0:
                self.max_value_pos = max(self.queue_pos)

                # 下降检测
                if self.max_value_pos - input_value > 30:
                    self.down_flag_pos += 1
                    self.up_flag_pos = 0
                # 上升检测
                elif input_value - self.max_value_pos > 30:
                    self.up_flag_pos += 1
                    self.down_flag_pos = 0
                else:
                    self.up_flag_pos = 0
                    self.down_flag_pos = 0

                # 状态确认
                if self.down_flag_pos >= 3:
                    self.state_pos = -1
                    self.compensation_active_pos = False
                elif self.up_flag_pos >= 3:
                    self.state_pos = 1
                    self.compensation_active_pos = True

                # 执行补偿（正值不补偿或根据需要调整）
                if self.compensation_active_pos and self.state_pos == 1:
                    abs_value = input_value
                    compensation = int(params['a'] * abs_value * abs_value +
                                     params['b'] * abs_value + params['c'])
                    return input_value + compensation

            return input_value
        
        else:
            # 负向补偿逻辑
            params = self.all_params['negative']
            
            # 更新队列
            self.queue_neg.append(input_value)

            # 查找队列最大值（对负值而言，最大值是绝对值最小的）
            if len(self.queue_neg) > 0:
                self.max_value_neg = max(self.queue_neg)

                # 下降检测
                if self.max_value_neg - input_value > 30:
                    self.down_flag_neg += 1
                    self.up_flag_neg = 0
                # 上升检测
                elif input_value - self.max_value_neg > 30:
                    self.up_flag_neg += 1
                    self.down_flag_neg = 0
                else:
                    self.up_flag_neg = 0
                    self.down_flag_neg = 0

                # 状态确认
                if self.down_flag_neg >= 3:
                    self.state_neg = -1
                    self.compensation_active_neg = False
                elif self.up_flag_neg >= 3:
                    self.state_neg = 1
                    self.compensation_active_neg = True

                # 执行补偿
                if self.compensation_active_neg and self.state_neg == 1:
                    abs_value = -input_value
                    compensation = int(params['a'] * abs_value * abs_value +
                                     params['b'] * abs_value + params['c'])
                    return input_value + compensation

            return input_value

    def reset(self):
        """重置状态"""
        # 重置正方向状态
        self.queue_pos.clear()
        self.max_value_pos = 0
        self.up_flag_pos = 0
        self.down_flag_pos = 0
        self.state_pos = 0
        self.compensation_active_pos = False
        
        # 重置负方向状态
        self.queue_neg.clear()
        self.max_value_neg = 0
        self.up_flag_neg = 0
        self.down_flag_neg = 0
        self.state_neg = 0
        self.compensation_active_neg = False


#标定补偿器
class CalibrationProcessor:
    """
    标定器 - 为每个轴提供独立的标定参数和计算（区分正负方向）
    """

    # 各轴标定参数 - 区分 positive 和 negative
    CALIBRATION_PARAMS = {
        'fx': {
            'positive': {'a': 0, 'b': 0.0065},
            'negative': {'a': 0, 'b': 0.0065}
        },
        'fy': {
            'positive': {'a': 1e-7, 'b': 0.0058},
            'negative': {'a': 1e-7, 'b': 0.0058}
        },
        'fz': {
            'positive': {'a': 4e-8, 'b': 0.003},
            'negative': {'a': 4e-8, 'b': 0.003}
        },
        'mx': {
            'positive': {'a': 0, 'b': 1},
            'negative': {'a': 0, 'b': 1}
        },
        'my': {
            'positive': {'a': 0, 'b': 1},
            'negative': {'a': 0, 'b': 1}
        },
        'mz': {
            'positive': {'a': 0, 'b': 1},
            'negative': {'a': 0, 'b': 1}
        }
    }

    def __init__(self, axis_name):
        """
        初始化标定器

        Args:
            axis_name: 轴名称 ('fx', 'fy', 'fz', 'mx', 'my', 'mz')
        """
        if axis_name not in self.CALIBRATION_PARAMS:
            raise ValueError(f"Invalid axis name: {axis_name}. Must be one of {list(self.CALIBRATION_PARAMS.keys())}")

        self.axis_name = axis_name
        self.all_params = self.CALIBRATION_PARAMS[axis_name]

    def calibrate(self, compensated_value):
        """
        计算标定后的力值

        Args:
            compensated_value: 补偿后的原始值

        Returns:
            标定后的力值
        """
        # 根据值的正负选择对应的标定参数
        direction = 'positive' if compensated_value >= 0 else 'negative'
        params = self.all_params[direction]
        
        a = params['a']
        b = params['b']
        
        # 使用二次多项式进行标定：a*x² + b*x
        calibrated_value = (compensated_value * compensated_value * a +
                           compensated_value * b)
        return calibrated_value

    def reset(self):
        """重置状态（标定器无状态，此方法为保持接口一致性）"""
        pass