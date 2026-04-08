import os
import sys
import signal
from typing import List

import numpy as np
import yaml

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from drivers.array_sensor.utils import create_array_sensor, initialize_array_sensor

try:
    from PyQt5 import QtCore, QtWidgets
    import pyqtgraph.opengl as gl
except Exception as e:  # pragma: no cover
    raise RuntimeError("运行 3D 可视化需要安装 PyQt5 与 pyqtgraph") from e

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "default.yaml")


def load_cfg():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def init_view():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    view = gl.GLViewWidget()
    view.opts["distance"] = 25
    view.setBackgroundColor("k")
    view.setWindowTitle("Array Sensor 8x8 - 3D")
    view.show()

    grid = gl.GLGridItem()
    grid.scale(1, 1, 1)
    view.addItem(grid)

    axis = gl.GLAxisItem()
    axis.setSize(10, 10, 10)
    view.addItem(axis)
    return app, view


def build_meshes(view):
    color_row = np.array([
        (54, 34, 159, 0.5), (76, 81, 255, 0.5), (34, 139, 244, 0.5), (10, 181, 224, 0.5),
        (41, 207, 157, 0.5), (168, 193, 47, 0.5), (255, 200, 53, 0.5), (255, 253, 24, 0.5)
    ]) / 255
    faces = np.array([
        [0, 1, 3], [0, 2, 3], [0, 1, 5], [0, 4, 5], [0, 2, 6], [0, 4, 6],
        [4, 5, 7], [4, 6, 7], [2, 3, 7], [2, 6, 7], [1, 3, 7], [1, 5, 7]
    ])

    vertexes = np.zeros((64, 8, 3), dtype=float)
    meshes = []
    for i in range(64):
        row, col = i // 8, i % 8
        vertexes[i, :4, :] = [(row, col, 0), (row, col + 0.8, 0), (row + 0.8, col, 0), (row + 0.8, col + 0.8, 0)]
        vertexes[i, 4:, :] = vertexes[i, :4, :]
        colors = np.array([color_row[row] for _ in range(12)])
        mesh = gl.GLMeshItem(vertexes=vertexes[i], faces=faces, faceColors=colors, drawEdges=True)
        view.addItem(mesh)
        meshes.append(mesh)
    return vertexes, faces, color_row, meshes


def main():
    cfg = load_cfg()
    sensor_cfg = cfg.get("sensor", {}).get("array_sensor")
    if not sensor_cfg:
        raise ValueError("配置缺少 sensor.array_sensor")

    sensor = create_array_sensor(sensor_cfg)
    if not initialize_array_sensor(sensor):
        raise RuntimeError("阵列传感器初始化失败")

    app, view = init_view()
    vertexes, faces, color_row, meshes = build_meshes(view)

    stop = {"flag": False}

    def _stop(*_):
        stop["flag"] = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    def update_3d():
        if stop["flag"]:
            timer.stop()
            sensor.disconnect()
            app.quit()
            return

        frame = sensor.read_frame()
        if frame is None:
            return

        relative: List[float] = frame["relative"]
        mapping = np.asarray(sensor_cfg["processing"]["mapping"], dtype=int)
        rel = np.asarray(relative, dtype=float) / 100.0

        for i in range(64):
            row, col = i // 8, i % 8
            sensor_index = mapping[row, col]
            h = rel[sensor_index]
            vertexes[i, 4:, :] = [(row, col, h), (row, col + 0.8, h), (row + 0.8, col, h), (row + 0.8, col + 0.8, h)]
            meshes[i].setMeshData(vertexes=vertexes[i], faces=faces, faceColors=np.array([color_row[row]] * 12))

    timer = QtCore.QTimer()
    timer.timeout.connect(update_3d)
    timer.start(50)

    app.exec_()


if __name__ == "__main__":
    main()
