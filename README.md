# 运动采集项目（精简版）

本仓库当前包含以下设备相关代码：

1. 运动控制卡驱动（雷赛 LTSMC）
2. 六轴力传感器驱动（M8128B1）
3. 8x8 阵列触觉传感器驱动（串口帧协议）
4. 力矩电机驱动（motormaster）

## 当前目录结构

```text
.
├── apps/
│   ├── __init__.py
│   ├── debug_array_sensor_3d.py # 阵列触觉传感器3D显示
│   ├── debug_motion.py         # LTSMC 运动控制调试
│   └── debug_torque_motor.py   # 力矩电机调试 UI
├── config/
│   └── default.yaml            # 运动卡 / M8128B1 / 力矩电机配置
├── drivers/
│   ├── __init__.py
│   ├── array_sensor/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── compensation.py
│   │   ├── processor.py
│   │   ├── protocol.py
│   │   ├── serial_sensor.py
│   │   ├── volterra_plus.py
│   │   └── utils.py
│   ├── motioncard/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── ltsmc_dll.py
│   │   └── utils.py
│   ├── sensors/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── m8128b1.py
│   │   └── utils.py
│   └── torque_motor/
│       ├── __init__.py
│       ├── base.py
│       ├── torque_card.py
│       └── sdk_standalone-main-V4/
├── LTSMC.dll
├── LTSMC.lib
└── README.md
```

## 依赖环境

- Python 3.10+
- Windows（使用 LTSMC.dll 时）
- pyserial
- pyyaml
- PyQt5（`apps/debug_torque_motor.py`）
- pyqtgraph（`apps/debug_array_sensor_3d.py`）
- motormaster（力矩电机 SDK）

## 快速运行

### 1) 运动控制卡调试

```bash
python apps/debug_motion.py
```

### 2) 力矩电机调试 UI

```bash
python apps/debug_torque_motor.py
```

### 3) M8128B1 六轴传感器

可通过 `drivers/sensors/utils.py` 创建并初始化：

```python
from drivers.sensors.utils import create_sensor, initialize_sensor

cfg = {
    "port": "COM5",
    "baudrate": 115200,
    "channels": 6,
    "rate_hz": 200,
}

sensor = create_sensor("m8128b1", cfg)
ok = initialize_sensor(sensor)
```

### 4) 阵列触觉传感器 3D 可视化

```bash
python apps/debug_array_sensor_3d.py
```

## 配置说明

- `config/default.yaml` 中包含：
  - `motioncard`
  - `axes`
  - `sensor.m8128b1`
  - `sensor.array_sensor`
  - `torque_motor`
