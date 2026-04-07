# -*- coding: utf-8 -*-
import datetime
import csv
import os
import sys
import threading
import serial
import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QMessageBox, QFileDialog, QMainWindow
import pyqtgraph.opengl as gl
from PyQt5.QtCore import QObject, pyqtSignal
# from volterra_compensator import VolterraCompensator
# from volterra_plus import VOLTERRA_SHEAR, VOLTERRA_NORMAL, HISTORY_LEN
from sensor_data_processor import DynamicCompensator,HysteresisCompensator
# 1) 类从 volterra_compensator.py 来
from volterra_compensator import VolterraCompensator

# 2) 核参数从 volterra_plus.py 来（方案C四方向）
from volterra_plus import (
    VOLTERRA_SHEAR_X_POS, VOLTERRA_SHEAR_X_NEG,
    VOLTERRA_SHEAR_Y_POS, VOLTERRA_SHEAR_Y_NEG,
    VOLTERRA_NORMAL, HISTORY_LEN,
)
import re
from collections import deque

import struct

FRAME_HEAD = [0x4000, 0xC000, 0xC000, 0x4000]  # int16，小端
FRAME_SIZE = 146
DATA_SIZE = 64

# 传感器索引映射数组 (8x8)
# 这个数组定义了64个传感器在物理阵列中的排列顺序
sensor_mapping = np.array([
    [7, 6, 5, 4, 3, 2, 1, 0],
    [15, 14, 13, 12, 11, 10, 9, 8],
    [23, 22, 21, 20, 19, 18, 17, 16],
    [31, 30, 29, 28, 27, 26, 25, 24],
    [39, 38, 37, 36, 35, 34, 33, 32],
    [47, 46, 45, 44, 43, 42, 41, 40],
    [55, 54, 53, 52, 51, 50, 49, 48],
    [63, 62, 61, 60, 59, 58, 57, 56]
])

# 基于当前脚本位置定位项目根目录，避免依赖运行时工作目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(project_root, 'UI'))

# 导入UI模块
from sensorarray import Ui_MainWindow

# 假设传感器数据是一个8x8阵列，存储在data中
data = [0] * 64  # 初始化传感器数据
zero_reference_data = [0] * 64  # 用于存储清零参考值

# 串口设置
def init_serial(port='COM6', baud=115200):
    global mSerial
    mSerial = serial.Serial(port, baud)
    th = threading.Thread(target=read_serial)
    th.daemon = True
    th.start()


def clean_serial_data(line):
    # 使用正则表达式移除不可见字符
    line = re.sub(r'[^\x20-\x7E]', '', line)  # 仅保留可见字符（ASCII范围）
    return line

def read_serial():
    global data
    buffer = bytearray()

    while True:
        try:
            # 读取串口当前缓冲数据
            buffer += mSerial.read(mSerial.in_waiting or 1)
            # print(len(buffer))  # 打印当前缓冲区内容
            # 查找并处理完整帧
            while len(buffer) >= FRAME_SIZE:
                # 从每个可能的起始点尝试找帧头
                found = False
                for i in range(len(buffer) - FRAME_SIZE + 1):
                    # 提取4个int16小端帧头
                    head = [int.from_bytes(buffer[i + j*2:i + j*2 + 2], 'little') for j in range(4)]
                    if head == FRAME_HEAD:
                        frame = buffer[i:i + FRAME_SIZE]
                        buffer = buffer[i + FRAME_SIZE:]  # 移除已处理内容
                        found = True
                        break
                if not found:
                    buffer = buffer[-3:]  # 留下最后几个字节尝试下一轮匹配
                    break

                # 计算校验（前144字节累加）
                checksum_calc = sum(frame[:144]) & 0xFFFF
                checksum_recv = int.from_bytes(frame[144:146], 'little')
                if checksum_calc != checksum_recv:
                    print("校验失败：计算值", checksum_calc, "≠ 接收值", checksum_recv)
                    continue

                # 解析 64 个 int16 触觉值（单位换算成 float）
                sensor_data = [
                    # struct.unpack_from('<h', frame, 8 + i * 2)[0] / 100.0
                    struct.unpack_from('<h', frame, 8 + i * 2)[0]
                    for i in range(DATA_SIZE)
                ]

                # 温度解析（每个温度由整数和小数部分组成）
                temp1_int  = struct.unpack_from('<h', frame, 136)[0]
                temp1_frac = struct.unpack_from('<h', frame, 138)[0]
                temp2_int  = struct.unpack_from('<h', frame, 140)[0]
                temp2_frac = struct.unpack_from('<h', frame, 142)[0]
                temp1 = temp1_int + temp1_frac * 0.001
                temp2 = temp2_int + temp2_frac * 0.001

                # 时间戳
                timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

                # 发射信号（你自己的数据槽函数接收这个）
                data = sensor_data
                signal_emitter.data_updated.emit(data, timestamp, temp1, temp2)


        except Exception as e:
            print("Serial error:", e)



# 定义信号
class SignalEmitter(QObject):
    data_updated = pyqtSignal(list, str,float,float)  # 接受两个参数：数据列表和时间戳（字符串） # 增加 temp1 和 temp2 参数


# 创建UI更新信号发射器
signal_emitter = SignalEmitter()

# 3D图形显示
def create_window():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    w = gl.GLViewWidget()
    w.opts['distance'] = 25
    w.setBackgroundColor('k')
    w.setWindowTitle('3D Capacitive Sensor Viewer')
    w.show()

    # 添加网格和坐标轴
    grid = gl.GLGridItem()
    grid.scale(1, 1, 1)
    w.addItem(grid)

    axis = gl.GLAxisItem()
    axis.setSize(10, 10, 10)
    w.addItem(axis)

    return app, w

def init_cubes(window):
    global cube, vertexes, color_row, faces
    color_row = np.array([(54, 34, 159, 0.5), (76, 81, 255, 0.5), (34, 139, 244, 0.5), (10, 181, 224, 0.5),
                          (41, 207, 157, 0.5), (168, 193, 47, 0.5), (255, 200, 53, 0.5), (255, 253, 24, 0.5)]) / 255
    faces = np.array([[0, 1, 3], [0, 2, 3], [0, 1, 5], [0, 4, 5], [0, 2, 6], [0, 4, 6],
                      [4, 5, 7], [4, 6, 7], [2, 3, 7], [2, 6, 7], [1, 3, 7], [1, 5, 7]])
    vertexes = np.zeros((64, 8, 3))
    cube = [0] * 64
    for i in range(64):
        row, col = i // 8, i % 8
        vertexes[i, :4, :] = [(row, col, 0), (row, col + 0.8, 0),
                              (row + 0.8, col, 0), (row + 0.8, col + 0.8, 0)]
        vertexes[i, 4:, :] = vertexes[i, :4, :]
        colors = np.array([color_row[row] for _ in range(12)])
        cube[i] = gl.GLMeshItem(vertexes=vertexes[i], faces=faces, faceColors=colors, drawEdges=True)
        window.addItem(cube[i])

# 更新显示
def update():
    global cube, vertexes

    relative_data = [(data[i] - zero_reference_data[i]) / 100.0 for i in range(64)]

    for i in range(64):
        row, col = i // 8, i % 8
        # 使用映射数组获取对应的传感器数据索引
        sensor_index = sensor_mapping[row, col]
        height_value = relative_data[sensor_index]

        vertexes[i, 4:, :] = [(row, col, height_value), (row, col + 0.8, height_value),
                              (row + 0.8, col, height_value), (row + 0.8, col + 0.8, height_value)]
        cube[i].setMeshData(vertexes=vertexes[i], faces=faces, faceColors=np.array([color_row[row]] * 12))

        # 计算 Fx 和 Fz
def calculate_fx_fy_fz(data):
    # 将数据重新整理为8x8的矩阵
    # 使用NumPy的高级索引功能
    data_array = np.array(data)
    Cbar3 = data_array[sensor_mapping]

    # 计算 Fx（X 方向剪切力）- 修改为相邻行对差值
    FxTemp = np.array([
        Cbar3[0, :] - Cbar3[1, :],  # 第0行减去第1行
        Cbar3[2, :] - Cbar3[3, :],  # 第2行减去第3行
        Cbar3[4, :] - Cbar3[5, :],  # 第4行减去第5行
        Cbar3[6, :] - Cbar3[7, :],  # 第6行减去第7行
    ])



    # 计算 Fx 合力 - 将所有差值矩阵相加
    arrFx = np.sum(FxTemp)
    # 若需要缩放
    arrFx = arrFx * 1

    FyTemp = np.array([

        ##此段代码应该是计算fy方向的
        Cbar3[:, 0] - Cbar3[:, 1],
        Cbar3[:, 2] - Cbar3[:, 3],
        Cbar3[:, 4] - Cbar3[:, 5],
        Cbar3[:, 6] - Cbar3[:, 7]
    ])
    arrFy = np.sum(FyTemp)

    # 若需要缩放
    arrFy = arrFy * 1
    #  # 计算 Fz（Z 方向正压力）
    arrFz = Cbar3
    # 若需要缩放
    arrFz = arrFz * 1

    return arrFx, arrFy, arrFz

# 主窗口类
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.data = data
        self.timestamp = None

        self.temp1 = None  # 新增：存储 temp1
        self.temp2 = None  # 新增：存储 temp2

        self.relative_temp1 = None  # 存储温度差值1
        self.relative_temp2 = None  # 存储温度差值2

        self.baseline_temp1 = 0  # 存储温度基准值1
        self.baseline_temp2 = 0  # 存储温度基准值2


        self.zero_reference_ui = [0] * 64
        self.collecting = False
        self.csv_writer = None
        self.csv_file = None

        self.data_counter = 0  # 新增：记录数据点的计数器

        self.connect_signals()

        # 连接信号
        signal_emitter.data_updated.connect(self.update_data)  # 连接信号并接收传递的data

        # 设置定时器，每100ms触发一次update_ui
        self.ui_update_timer = QtCore.QTimer(self)
        self.ui_update_timer.timeout.connect(self.update_ui)  # 每100ms调用update_ui
        self.ui_update_timer.start(100)  # 100ms更新一次UI


        ##实例化动态补偿器
        # 创建动态补偿器实例
        self.compensator_x_pos = DynamicCompensator('x_pos')  # X轴正方向
        self.compensator_y_pos = DynamicCompensator('y_pos')  # Y轴正方向
        self.compensator_x_neg = DynamicCompensator('x_neg')  # X轴负方向
        self.compensator_y_neg = DynamicCompensator('y_neg')  # Y轴负方向

        self.compensator_z = DynamicCompensator('z')

        ##实例化迟滞补偿器
        self.hysteresis_compensator_z = HysteresisCompensator('z')  # Z轴
        # Volterra 历史补偿
        # Volterra 历史补偿（四方向核）
        self.volterra = VolterraCompensator(
            volterra_shear={
                'x_pos': VOLTERRA_SHEAR_X_POS,
                'x_neg': VOLTERRA_SHEAR_X_NEG,
                'y_pos': VOLTERRA_SHEAR_Y_POS,
                'y_neg': VOLTERRA_SHEAR_Y_NEG,
            },
            volterra_normal=VOLTERRA_NORMAL,
            history_len=HISTORY_LEN,
            sign_eps=1e-6,  # 0 点抖动阈值，可按量纲调整
        )
        self.use_volterra = True

    def connect_signals(self):
        # 绑定UI按钮事件
        self.ui.Start_collecting.clicked.connect(self.on_start_collect)
        self.ui.sensor_zero.clicked.connect(self.record_zero_point)
        self.ui.save_data.clicked.connect(self.save_data)

    def update_data(self, data, timestamp, temp1, temp2):
        """接收数据和时间戳，更新UI和保存"""
        self.data = data
        self.timestamp = timestamp

        self.temp1 = temp1  # 更新 temp1
        self.temp2 = temp2  # 更新 temp2



        if self.collecting:
            self.save_data_row()  # 串口接收到数据时直接保存数据

    def update_ui(self):
        """更新UI显示"""
        relative_data = [self.data[i] - self.zero_reference_ui[i] for i in range(64)]

        # 使用共享的计算方法
        fz_value, fx_value, fy_value, fz_pressure, fx_pressure, fy_pressure = self.calculate_compensated_values(
            relative_data)


        # 更新UI中的显示值
        self.ui.normol_pressure_value.setText(f"{fz_pressure:.2f}")  # 法向压强值
        self.ui.normol_force_value.setText(f"{fz_value:.2f}")  # 法向力值
        self.ui.tangential_pressure_value_x.setText(f"{fx_pressure:.2f}")  # 切向压强值
        self.ui.tangential_force_value_x.setText(f"{fx_value:.2f}")  # 切向力值
        self.ui.tangential_pressure_value_y.setText(f"{fy_pressure:.2f}")  # 切向压强值
        self.ui.tangential_force_value_y.setText(f"{fy_value:.2f}")  # 切向力值

    def record_zero_point(self):
        """清零功能"""
        global zero_reference_data
        self.zero_reference_ui = self.data.copy()

        # 计算温度差值
        self.baseline_temp1 = self.temp1  # 更新基准温度
        self.baseline_temp2 = self.temp2  # 更新基准温度


        zero_reference_data = self.data.copy()
        if hasattr(self, "volterra") and self.volterra is not None:
            self.volterra.reset()

        QMessageBox.information(self, "清零", "当前传感器数据已设为基准（零点）")

    def on_start_collect(self):
        """开始采集数据"""
        # 创建CSV文件
        now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"sensor_data_{now}.csv"
        self.csv_file = open(filename, mode='a', newline='')
        self.csv_writer = csv.writer(self.csv_file)


        ###注意 在做数据记录时可以不保存时间戳，不然文件将会很大
        # 写入CSV文件头部（包括64个传感器数据和总和列）
        header = [f"cap_{i}" for i in range(64)] + ["total", "force_value", "fz_capacitance", "fz_value",
                                                    "fx_capacitance", "fx_value","fy_capacitance", "fy_value","temp1", "temp2","relative_temp1","relative_temp2", "timestamp"]  # 增加列


        self.csv_writer.writerow(header)

        self.collecting = True
        self.ui.Start_collecting.setText("正在采集...")
        QMessageBox.information(self, "开始采集", "数据采集已开始，请按停止按钮保存数据")

    def save_data_row(self):
        """保存传感器数据到CSV文件"""
        if not self.collecting or self.csv_writer is None:
            return

        # 每隔1个数据点保存一次
        self.data_counter += 1
        if self.data_counter % 1 != 0:
            return

        # 重置计数器
        self.data_counter = 0

        # 获取当前传感器数据，并计算相对数据
        relative_data = [self.data[i] - self.zero_reference_ui[i] for i in range(64)]
        total_relative_data = sum(relative_data)

        self.relative_temp1 = self.temp1 - self.baseline_temp1  # 计算温度差值
        self.relative_temp2 = self.temp2 - self.baseline_temp2  # 计算温度差值

        # 计算力值：relative_data的总和乘以0.1
        force_value = total_relative_data * 1.0


        # 使用共享的计算方法
        fz_value, fx_value, fy_value, fz_pressure, fx_pressure, fy_pressure = self.calculate_compensated_values(
            relative_data)

        # 记录时间戳
        timestamp = f'"{self.timestamp}"'  # 确保时间戳作为字符串处理


        # 写入数据行：加入力值列和时间戳
        row = relative_data + [total_relative_data, force_value, fz_value, fz_pressure, fx_value, fx_pressure, fy_value, fy_pressure,
                               self.temp1, self.temp2, self.relative_temp1, self.relative_temp2, timestamp]



        self.csv_writer.writerow(row)

    def calculate_compensated_values(self, relative_data):
        """计算各种补偿和标定后的值"""
        # 四个补偿器的控制配置 - 方便调试时快速切换
        compensation_config = {
            'use_temperature_compensation': False,  # 第一个：温度补偿
            'use_dynamic_compensation': True,  # 第二个：动态补偿
            'use_hysteresis_compensation': True,  # 第三个：迟滞补偿
            'use_calibration': True,  # 第四个：标定
        }

        # 计算各轴力的总和
        arrFx, arrFy, arrFz = calculate_fx_fy_fz(relative_data)
        # fx_sum = arrFx.sum()
        # fy_sum = arrFy.sum()
        # fz_sum = arrFz.sum()

        # 确保温度差值已计算
        if self.relative_temp1 is None:
            self.relative_temp1 = 0

        # ... 前面已算出 fx_sum, fy_sum, fz_sum
        fx_sum = float(arrFx)
        fy_sum = float(arrFy)
        fz_sum = float(arrFz.sum())

        # Volterra：按四方向核进行历史补偿（保持不变）
        if getattr(self, "use_volterra", False) and getattr(self, "volterra", None) is not None:
            fx_sum, fy_sum, fz_sum = self.volterra.update(fx_sum, fy_sum, fz_sum)

        # 下面再进入动态/迟滞/标定等补偿
        # ...

        # ----------------------------------------------------

        # 初始化补偿数据（从原始数据开始）
        fz_compensated = fz_sum
        fx_compensated = fx_sum
        fy_compensated = fy_sum






        # 1. 温度补偿器
        if compensation_config['use_temperature_compensation']:
            fz_compensated = fz_compensated + self.relative_temp1 * (-9.6442)
            fx_compensated = fx_compensated + self.relative_temp1 * 1.2181
            fy_compensated = fy_compensated + self.relative_temp1 * (-0.19054)




        # 2. 动态补偿器
        if compensation_config['use_dynamic_compensation']:
            fz_compensated = self.compensator_z.update(fz_compensated)

            # X轴动态补偿 - 根据正负值选择补偿器
            if fx_compensated >= 0:
                fx_compensated = self.compensator_x_pos.update(fx_compensated)
            else:
                fx_compensated = self.compensator_x_neg.update(fx_compensated)

            # Y轴动态补偿 - 根据正负值选择补偿器
            if fy_compensated >= 0:
                fy_compensated = self.compensator_y_pos.update(fy_compensated)
            else:
                fy_compensated = self.compensator_y_neg.update(fy_compensated)



        # 3. 迟滞补偿器
        if compensation_config['use_hysteresis_compensation']:
            # TODO: 实现迟滞补偿
            # Z轴迟滞补偿
            fz_compensated = self.hysteresis_compensator_z.compensate(int(fz_compensated))


            # fx_compensated = self.hysteresis_compensator_x.update(fx_compensated)
            # fy_compensated = self.hysteresis_compensator_y.update(fy_compensated)
            pass

        # 4. 标定器
        if compensation_config['use_calibration']:
            # Z轴标定
            fz_value = (fz_compensated * fz_compensated *  1.453e-07  + fz_compensated * 0.028351) / 100

            # X轴标定 - 根据正负值使用不同参数
            if fx_compensated >= 0:
                fx_value = (fx_compensated * fx_compensated * -3.14019e-04 + fx_compensated * 8.87596e-01) / 100
            else:
                fx_value = (fx_compensated * fx_compensated * 4.80751e-04 + fx_compensated * 1.0419e+00) / 100

            # Y轴标定 - 根据正负值使用不同参数
            if fy_compensated >= 0:
                fy_value = (fy_compensated * fy_compensated * -6.06168e-04 + fy_compensated * 1.35464e+00) / 100
            else:
                fy_value = (fy_compensated * fy_compensated * 9.80956e-04 + fy_compensated * 1.44280e+00) / 100
        else:
            # 如果不使用标定，直接返回补偿后的原始值
            fz_value = fz_compensated
            fx_value = fx_compensated
            fy_value = fy_compensated

        # 压强计算
        fz_pressure = fz_value * 10
        fx_pressure = fx_value * 10
        fy_pressure = fy_value * 10

        return fz_value, fx_value, fy_value, fz_pressure, fx_pressure, fy_pressure

    def save_data(self):
        """保存数据并停止采集"""
        if self.csv_file:
            self.csv_file.close()
        self.collecting = False
        self.ui.Start_collecting.setText("开始采集")
        QMessageBox.information(self, "保存数据", "数据采集已停止，文件已保存")

# 主函数
def main():
    init_serial(port='COM3', baud=2000000)
    app, window = create_window()
    init_cubes(window)

    timer = QtCore.QTimer()
    timer.timeout.connect(update)
    timer.start(100)

    win = MainWindow()
    win.show()

    app.exec_()

if __name__ == '__main__':
    main()
