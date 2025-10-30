# -*- coding: utf-8 -*-
"""
README - 运动控制系统项目

## 项目简介

这是一个模块化的运动控制系统框架，支持多种运动控制卡、力矩电机和传感器。
系统采用分层架构设计，便于扩展和维护。

## 项目结构

```
project/
├── config/                    # 配置文件
│   ├── default.yaml          # 全局配置
│   └── axes_calibration.yaml # 轴标定配置
├── drivers/                   # 硬件驱动层
│   ├── motioncard/           # 运动控制卡驱动
│   │   ├── base.py          # 抽象基类
│   │   ├── ltsmc_dll.py     # 雷赛LTSMC驱动
│   │   ├── tcp_modbus.py    # ModbusTCP驱动
│   │   └── mock.py          # 模拟驱动
│   ├── torque/              # 力矩电机驱动
│   │   ├── base.py          # 抽象基类
│   │   ├── canopen.py       # CANopen驱动
│   │   └── mock.py          # 模拟驱动
│   └── sensors/             # 传感器驱动
│       ├── base.py          # 抽象基类
│       ├── encoder.py       # 编码器驱动
│       ├── dio.py           # 数字IO驱动
│       └── mock.py          # 模拟驱动
├── controllers/              # 控制器层
│   ├── motion_ctrl.py       # 运动控制器
│   ├── torque_ctrl.py       # 力矩控制器
│   └── sensor_fusion.py     # 传感器融合
├── services/                # 服务层
│   ├── bus.py              # 消息总线
│   ├── logger.py           # 日志服务
│   ├── recorder.py         # 数据记录
│   └── scheduler.py        # 任务调度
├── apps/                    # 应用层
│   ├── debug_motion.py     # 运动调试应用
│   ├── debug_torque.py     # 力矩调试应用
│   ├── debug_sensor.py     # 传感器调试应用
│   ├── debug_processing.py # 数据处理调试
│   └── integrated_run.py   # 集成运行应用
├── tests/                   # 测试
│   ├── test_motion_unit.py # 单元测试
│   └── test_integration.py # 集成测试
├── utils/                   # 工具函数
│   ├── math_tools.py       # 数学工具
│   └── safety.py           # 安全功能
└── README.md               # 本文件
```

## 功能特点

### 1. 模块化设计
- 抽象基类定义统一接口
- 支持多种硬件驱动
- 易于扩展新设备

### 2. 多种运动控制支持
- 雷赛LTSMC运动控制卡
- ModbusTCP协议控制器
- 模拟控制器（用于测试）

### 3. 力矩电机控制
- CANopen协议支持
- 多种控制模式（力矩/电流/速度/位置）
- PID参数调节

### 4. 传感器集成
- 编码器支持
- 数字IO处理
- 传感器融合算法

### 5. 实时数据处理
- 高频数据采集
- 实时滤波处理
- 数据记录和回放

### 6. 安全功能
- 软/硬限位保护
- 急停功能
- 故障检测和处理

## 快速开始

### 1. 环境要求
- Python 3.7+
- Windows 系统（用于LTSMC驱动）
- 相关硬件驱动库

### 2. 安装依赖
```bash
pip install pyyaml
pip install numpy
pip install pandas
# 可选依赖
pip install pymodbus  # ModbusTCP支持
pip install canopen   # CANopen支持
```

### 3. 配置设置
编辑 `config/default.yaml` 和 `config/axes_calibration.yaml` 文件，
根据实际硬件配置参数。

### 4. 运行测试
```bash
# 运动控制测试
python apps/debug_motion.py

# 力矩电机测试  
python apps/debug_torque.py

# 传感器测试
python apps/debug_sensor.py

# 集成测试
python apps/integrated_run.py
```

## 使用示例

### 运动控制示例
```python
from drivers.motioncard.ltsmc_dll import LTSMCMotionCard
from config import load_config

# 加载配置
config = load_config('config/default.yaml')

# 创建运动控制卡实例
with LTSMCMotionCard(config) as card:
    # 基础设置
    card.set_pulse_mode(0, 0)
    card.set_equiv(0, 1600.0)
    card.set_velocity_profile(0, 0, 30.0, 0.15, 0.15)
    
    # 运动控制
    card.move_relative(0, 10.0)  # 相对运动10单位
    card.wait_motion_done(0)
    
    print(f"当前位置: {card.get_position(0)}")
```

### 力矩电机示例
```python
from drivers.torque.canopen import CANopenTorqueMotor
from drivers.torque.base import TorqueMode

config = {
    'motor_id': 1,
    'can_interface': 'socketcan',
    'can_channel': 'can0',
    'node_id': 1
}

with CANopenTorqueMotor(config) as motor:
    # 设置力矩模式
    motor.set_control_mode(TorqueMode.TORQUE)
    motor.set_torque(2.0)  # 设置2Nm力矩
    
    time.sleep(1.0)
    print(f"实际力矩: {motor.get_torque()}")
```

## 开发指南

### 1. 添加新的运动控制卡驱动
1. 继承 `drivers.motioncard.base.MotionCard` 类
2. 实现所有抽象方法
3. 在配置文件中添加相应配置
4. 编写单元测试

### 2. 添加新的力矩电机驱动
1. 继承 `drivers.torque.base.TorqueMotor` 类  
2. 实现所有抽象方法
3. 支持多种控制模式
4. 编写单元测试

### 3. 添加新的传感器驱动
1. 继承 `drivers.sensors.base.Sensor` 类
2. 实现数据采集方法
3. 处理数据滤波和校准
4. 编写单元测试

### 4. 代码规范
- 使用类型提示
- 添加文档字符串
- 遵循PEP 8规范
- 编写完整的测试用例

## 测试

### 单元测试
```bash
python -m pytest tests/test_motion_unit.py
```

### 集成测试
```bash  
python -m pytest tests/test_integration.py
```

### 模拟测试（无硬件）
所有驱动都提供Mock版本，可以在无硬件环境下进行开发和测试。

## 故障排除

### 常见问题

1. **LTSMC.dll加载失败**
   - 确保DLL文件在正确路径
   - 检查Python位数与DLL匹配
   - 确认Windows系统

2. **CANopen连接失败**
   - 检查CAN接口配置
   - 确认节点ID正确
   - 检查波特率设置

3. **ModbusTCP连接超时**
   - 检查IP地址和端口
   - 确认网络连通性
   - 检查防火墙设置

### 日志调试
系统提供详细的日志记录，可以通过配置文件调整日志级别：
```yaml
logging:
  level: "DEBUG"  # INFO, WARNING, ERROR
  file_path: "logs/motion_control.log"
```

## 贡献

欢迎提交Issue和Pull Request！

## 许可证

本项目采用MIT许可证。

## 更新日志

### v1.0.0
- 初始版本发布
- 支持雷赛LTSMC运动控制卡
- 基础力矩电机控制
- 模拟驱动支持

### 未来计划
- [ ] 添加更多运动控制卡支持
- [ ] 优化实时性能
- [ ] 增加图形界面
- [ ] 支持更多传感器类型
- [ ] 机器学习算法集成
