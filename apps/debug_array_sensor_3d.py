import csv
import os
import sys
from datetime import datetime

import numpy as np
import yaml

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from drivers.array_sensor.utils import create_array_sensor, initialize_array_sensor

from PyQt5 import QtCore, QtWidgets
import pyqtgraph.opengl as gl

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "default.yaml")
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")


def load_cfg():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class ArraySensor3DWindow(QtWidgets.QMainWindow):
    def __init__(self, sensor, sensor_cfg):
        super().__init__()
        self.sensor = sensor
        self.sensor_cfg = sensor_cfg
        self.mapping = np.asarray(sensor_cfg["processing"]["mapping"], dtype=int)

        self.collecting = False
        self.csv_file = None
        self.csv_writer = None

        self.setWindowTitle("Array Sensor 3D + 实时面板")
        self.resize(1300, 800)

        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)

        self.view = gl.GLViewWidget()
        self.view.opts["distance"] = 25
        self.view.setBackgroundColor("k")
        layout.addWidget(self.view, 3)

        panel = QtWidgets.QWidget()
        panel_layout = QtWidgets.QGridLayout(panel)
        layout.addWidget(panel, 2)

        self._init_3d_items()
        self._init_panel(panel_layout)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)

    def _init_3d_items(self):
        grid = gl.GLGridItem()
        grid.scale(1, 1, 1)
        self.view.addItem(grid)

        axis = gl.GLAxisItem()
        axis.setSize(10, 10, 10)
        self.view.addItem(axis)

        self.color_row = np.array([
            (54, 34, 159, 0.5), (76, 81, 255, 0.5), (34, 139, 244, 0.5), (10, 181, 224, 0.5),
            (41, 207, 157, 0.5), (168, 193, 47, 0.5), (255, 200, 53, 0.5), (255, 253, 24, 0.5)
        ]) / 255
        self.faces = np.array([
            [0, 1, 3], [0, 2, 3], [0, 1, 5], [0, 4, 5], [0, 2, 6], [0, 4, 6],
            [4, 5, 7], [4, 6, 7], [2, 3, 7], [2, 6, 7], [1, 3, 7], [1, 5, 7]
        ])

        self.vertexes = np.zeros((64, 8, 3), dtype=float)
        self.meshes = []
        for i in range(64):
            row, col = i // 8, i % 8
            self.vertexes[i, :4, :] = [(row, col, 0), (row, col + 0.8, 0), (row + 0.8, col, 0), (row + 0.8, col + 0.8, 0)]
            self.vertexes[i, 4:, :] = self.vertexes[i, :4, :]
            colors = np.array([self.color_row[row] for _ in range(12)])
            mesh = gl.GLMeshItem(vertexes=self.vertexes[i], faces=self.faces, faceColors=colors, drawEdges=True)
            self.view.addItem(mesh)
            self.meshes.append(mesh)

    def _init_panel(self, panel_layout: QtWidgets.QGridLayout):
        def mk_row(row, name):
            panel_layout.addWidget(QtWidgets.QLabel(name), row, 0)
            pressure = QtWidgets.QLineEdit("0.00")
            force = QtWidgets.QLineEdit("0.00")
            pressure.setReadOnly(True)
            force.setReadOnly(True)
            panel_layout.addWidget(pressure, row, 1)
            panel_layout.addWidget(QtWidgets.QLabel("Kpa"), row, 2)
            panel_layout.addWidget(force, row, 3)
            panel_layout.addWidget(QtWidgets.QLabel("N"), row, 4)
            return pressure, force

        self.p_fz, self.f_fz = mk_row(0, "法向压强")
        self.p_fx, self.f_fx = mk_row(1, "切向压强(x轴)")
        self.p_fy, self.f_fy = mk_row(2, "切向压强(y轴)")

        self.btn_start = QtWidgets.QPushButton("开始采集")
        self.btn_save = QtWidgets.QPushButton("保存数据")
        self.btn_zero = QtWidgets.QPushButton("清零")

        self.btn_start.clicked.connect(self.start_collect)
        self.btn_save.clicked.connect(self.save_data)
        self.btn_zero.clicked.connect(self.zero_sensor)

        panel_layout.addWidget(self.btn_start, 3, 0, 1, 2)
        panel_layout.addWidget(self.btn_save, 3, 2, 1, 2)
        panel_layout.addWidget(self.btn_zero, 3, 4)

        self.status = QtWidgets.QLabel("状态：运行中")
        panel_layout.addWidget(self.status, 4, 0, 1, 5)
        panel_layout.setRowStretch(5, 1)

    def start_collect(self):
        if self.collecting:
            return
        os.makedirs(LOG_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(LOG_DIR, f"array_sensor_{ts}.csv")
        self.csv_file = open(path, "w", newline="", encoding="utf-8")
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow([
            "timestamp", "fx", "fy", "fz", "px", "py", "pz", "temp1", "temp2", *[f"r{i}" for i in range(64)]
        ])
        self.collecting = True
        self.status.setText(f"状态：采集中 -> {path}")

    def save_data(self):
        if self.csv_file:
            self.csv_file.flush()
            self.csv_file.close()
        self.csv_file = None
        self.csv_writer = None
        self.collecting = False
        self.status.setText("状态：已停止采集并保存")

    def zero_sensor(self):
        self.sensor.zero()
        self.status.setText("状态：已清零")

    def _tick(self):
        frame = self.sensor.read_frame()
        if frame is None:
            return

        force = frame["force"]
        pressure = frame["pressure"]

        self.p_fz.setText(f"{pressure['fz']:.2f}")
        self.f_fz.setText(f"{force['fz']:.2f}")
        self.p_fx.setText(f"{pressure['fx']:.2f}")
        self.f_fx.setText(f"{force['fx']:.2f}")
        self.p_fy.setText(f"{pressure['fy']:.2f}")
        self.f_fy.setText(f"{force['fy']:.2f}")

        rel = np.asarray(frame["relative"], dtype=float) / 100.0
        for i in range(64):
            row, col = i // 8, i % 8
            sensor_index = self.mapping[row, col]
            h = rel[sensor_index]
            self.vertexes[i, 4:, :] = [(row, col, h), (row, col + 0.8, h), (row + 0.8, col, h), (row + 0.8, col + 0.8, h)]
            self.meshes[i].setMeshData(
                vertexes=self.vertexes[i],
                faces=self.faces,
                faceColors=np.array([self.color_row[row]] * 12),
            )

        if self.collecting and self.csv_writer:
            self.csv_writer.writerow([
                frame["timestamp"],
                force["fx"], force["fy"], force["fz"],
                pressure["fx"], pressure["fy"], pressure["fz"],
                frame["temp1"], frame["temp2"],
                *frame["relative"],
            ])

    def closeEvent(self, event):
        try:
            self.timer.stop()
        except Exception:
            pass
        try:
            self.save_data()
        except Exception:
            pass
        try:
            self.sensor.disconnect()
        except Exception:
            pass
        super().closeEvent(event)


def main():
    cfg = load_cfg()
    sensor_cfg = cfg.get("sensor", {}).get("array_sensor")
    if not sensor_cfg:
        raise ValueError("配置缺少 sensor.array_sensor")

    sensor = create_array_sensor(sensor_cfg)
    if not initialize_array_sensor(sensor):
        raise RuntimeError("阵列传感器初始化失败")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = ArraySensor3DWindow(sensor, sensor_cfg)
    win.show()
    app.exec_()


if __name__ == "__main__":
    main()
