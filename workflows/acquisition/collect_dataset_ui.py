import os
import sys
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import yaml
from PyQt5 import QtCore, QtWidgets
import pyqtgraph.opengl as gl

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from drivers.array_sensor.utils import create_array_sensor, initialize_array_sensor
from drivers.motioncard.ltsmc_dll import LTSMCMotionCard
from drivers.motioncard.utils import full_axis_initialization, perform_homing
from drivers.torque_motor.torque_card import TorqueMotorCard
from workflows.acquisition.dataset_writer import ArrayDatasetWriter, build_run_meta, make_run_id


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "default.yaml")
DATASET_ROOT = os.path.join(PROJECT_ROOT, "datasets")


def load_cfg() -> Dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def frange(start: float, stop: float, step: float) -> List[float]:
    vals: List[float] = []
    v = float(start)
    eps = abs(step) * 1e-6
    while v <= stop + eps:
        vals.append(round(v, 6))
        v += step
    return vals


class ArraySensor3DDialog(QtWidgets.QDialog):
    def __init__(self, sensor_cfg: Dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("阵列传感器3D视图")
        self.resize(960, 700)

        self.mapping = np.asarray(sensor_cfg["processing"]["mapping"], dtype=int)

        root = QtWidgets.QVBoxLayout(self)
        self.view = gl.GLViewWidget()
        self.view.opts["distance"] = 25
        self.view.setBackgroundColor("k")
        root.addWidget(self.view)

        self._init_3d_items()

    def _init_3d_items(self):
        grid = gl.GLGridItem()
        grid.scale(1, 1, 1)
        self.view.addItem(grid)

        axis = gl.GLAxisItem()
        axis.setSize(10, 10, 10)
        self.view.addItem(axis)

        self.color_row = np.array([
            (54, 34, 159, 0.5), (76, 81, 255, 0.5), (34, 139, 244, 0.5), (10, 181, 224, 0.5),
            (41, 207, 157, 0.5), (168, 193, 47, 0.5), (255, 200, 53, 0.5), (255, 253, 24, 0.5),
        ]) / 255
        self.faces = np.array([
            [0, 1, 3], [0, 2, 3], [0, 1, 5], [0, 4, 5], [0, 2, 6], [0, 4, 6],
            [4, 5, 7], [4, 6, 7], [2, 3, 7], [2, 6, 7], [1, 3, 7], [1, 5, 7],
        ])

        self.vertexes = np.zeros((64, 8, 3), dtype=float)
        self.meshes = []
        for i in range(64):
            row, col = i // 8, i % 8
            self.vertexes[i, :4, :] = [
                (row, col, 0),
                (row, col + 0.8, 0),
                (row + 0.8, col, 0),
                (row + 0.8, col + 0.8, 0),
            ]
            self.vertexes[i, 4:, :] = self.vertexes[i, :4, :]
            colors = np.array([self.color_row[row] for _ in range(12)])
            mesh = gl.GLMeshItem(vertexes=self.vertexes[i], faces=self.faces, faceColors=colors, drawEdges=True)
            self.view.addItem(mesh)
            self.meshes.append(mesh)

    def update_from_frame(self, frame: Dict, zero_reference: np.ndarray):
        rel = (np.asarray(frame["raw"], dtype=float) - zero_reference) / 100.0
        for i in range(64):
            row, col = i // 8, i % 8
            sensor_index = self.mapping[row, col]
            h = rel[sensor_index]
            self.vertexes[i, 4:, :] = [
                (row, col, h),
                (row, col + 0.8, h),
                (row + 0.8, col, h),
                (row + 0.8, col + 0.8, h),
            ]
            self.meshes[i].setMeshData(
                vertexes=self.vertexes[i],
                faces=self.faces,
                faceColors=np.array([self.color_row[row]] * 12),
            )


class CollectorUI(QtWidgets.QMainWindow):
    sig_log = QtCore.pyqtSignal(str)
    sig_progress = QtCore.pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("阵列数据采集系统（轴0/1 + 力矩电机）")
        self.resize(1180, 760)

        self.cfg: Dict = load_cfg()
        self.motion: Optional[LTSMCMotionCard] = None
        self.torque: Optional[TorqueMotorCard] = None
        self.array_sensor = None
        self._last_array_frame: Optional[Dict] = None
        self._array_frame_lock = threading.Lock()
        self._zero_reference_ui = np.zeros(64, dtype=float)
        self.array_3d_dialog: Optional[ArraySensor3DDialog] = None
        self._last_torque_force_zero_ts: float = 0.0
        self._torque_force_zero_cooldown_s: float = 0.5
        self._torque_retract_step_mm: float = 1.0
        self._last_3d_refresh_ts: float = 0.0
        # 3D显示限频：默认约10Hz，兼顾实时性与采集稳定性。
        self._collect_3d_refresh_interval_s: float = 0.10

        self._worker: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._busy_lock = threading.Lock()
        self._sensor_io_lock = threading.Lock()
        self._preview_running = True
        self._preview_thread = threading.Thread(target=self._array_preview_loop, daemon=True)
        self._preview_thread.start()
        self._torque_status_timer = QtCore.QTimer(self)
        self._torque_status_timer.timeout.connect(self._refresh_torque_status)
        self._torque_status_timer.start(300)

        self._build_ui()
        self.sig_log.connect(self._append_log)
        self.sig_progress.connect(self._update_progress)

    def _build_ui(self):
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)

        # 控制按钮
        btn_row = QtWidgets.QHBoxLayout()
        self.btn_connect = QtWidgets.QPushButton("连接设备")
        self.btn_connect.clicked.connect(self.connect_all)
        self.btn_zero_sensor = QtWidgets.QPushButton("阵列传感器清零")
        self.btn_zero_sensor.clicked.connect(self.zero_array_sensor)
        self.btn_show_3d = QtWidgets.QPushButton("显示3D图像")
        self.btn_show_3d.clicked.connect(self.show_array_3d)
        self.btn_home_axes = QtWidgets.QPushButton("轴0/轴1回原点")
        self.btn_home_axes.clicked.connect(self.home_axes)
        self.btn_home_torque = QtWidgets.QPushButton("力矩电机回原点")
        self.btn_home_torque.clicked.connect(self.home_torque)
        self.btn_zero_torque_force = QtWidgets.QPushButton("力矩电机力清零")
        self.btn_zero_torque_force.clicked.connect(self.zero_torque_force)
        self.btn_start = QtWidgets.QPushButton("开始采集")
        self.btn_start.clicked.connect(self.start_collect)
        self.btn_stop = QtWidgets.QPushButton("停止采集")
        self.btn_stop.clicked.connect(self.stop_collect)
        self.btn_stop.setStyleSheet("background:#d32f2f;color:white;font-weight:bold;")

        for b in (
            self.btn_connect,
            self.btn_zero_sensor,
            self.btn_show_3d,
            self.btn_home_axes,
            self.btn_home_torque,
            self.btn_zero_torque_force,
            self.btn_start,
            self.btn_stop,
        ):
            btn_row.addWidget(b)
        root.addLayout(btn_row)

        grid = QtWidgets.QGridLayout()

        self.force_n = QtWidgets.QDoubleSpinBox()
        self.force_n.setRange(0.1, 200.0)
        self.force_n.setDecimals(3)
        self.force_n.setValue(5.0)
        self.force_n.setSuffix(" N")

        self.push_dist = QtWidgets.QDoubleSpinBox()
        self.push_dist.setRange(0.1, 100.0)
        self.push_dist.setDecimals(3)
        self.push_dist.setValue(50.0)
        self.push_dist.setSuffix(" mm")

        self.push_vel = QtWidgets.QDoubleSpinBox()
        self.push_vel.setRange(0.1, 100.0)
        self.push_vel.setDecimals(3)
        self.push_vel.setValue(2.0)
        self.push_vel.setSuffix(" mm/s")

        self.force_band = QtWidgets.QDoubleSpinBox()
        self.force_band.setRange(0.01, 20.0)
        self.force_band.setDecimals(3)
        self.force_band.setValue(0.2)
        self.force_band.setSuffix(" N")

        self.chk_ms = QtWidgets.QSpinBox()
        self.chk_ms.setRange(10, 5000)
        self.chk_ms.setValue(200)
        self.chk_ms.setSuffix(" ms")

        self.static_frames = QtWidgets.QSpinBox()
        self.static_frames.setRange(1, 500)
        self.static_frames.setValue(50)

        self.repeat_presses = QtWidgets.QSpinBox()
        self.repeat_presses.setRange(1, 50)
        self.repeat_presses.setValue(10)

        self.axis0_min = QtWidgets.QDoubleSpinBox()
        self.axis0_min.setRange(-180.0, 180.0)
        self.axis0_min.setDecimals(3)
        self.axis0_min.setValue(-1.0)
        self.axis0_min.setSuffix(" °")
        self.axis0_max = QtWidgets.QDoubleSpinBox()
        self.axis0_max.setRange(-180.0, 180.0)
        self.axis0_max.setDecimals(3)
        self.axis0_max.setValue(1.0)
        self.axis0_max.setSuffix(" °")

        self.axis1_min = QtWidgets.QDoubleSpinBox()
        self.axis1_min.setRange(-180.0, 180.0)
        self.axis1_min.setDecimals(3)
        self.axis1_min.setValue(-1.0)
        self.axis1_min.setSuffix(" °")
        self.axis1_max = QtWidgets.QDoubleSpinBox()
        self.axis1_max.setRange(-180.0, 180.0)
        self.axis1_max.setDecimals(3)
        self.axis1_max.setValue(1.0)
        self.axis1_max.setSuffix(" °")

        self.step_deg = QtWidgets.QDoubleSpinBox()
        self.step_deg.setRange(0.001, 10.0)
        self.step_deg.setDecimals(4)
        self.step_deg.setValue(0.1)
        self.step_deg.setSuffix(" °")

        self.point_timeout = QtWidgets.QDoubleSpinBox()
        self.point_timeout.setRange(1.0, 60.0)
        self.point_timeout.setValue(50.0)
        self.point_timeout.setSuffix(" s")

        self.output_dir = QtWidgets.QLineEdit(DATASET_ROOT)

        r = 0
        grid.addWidget(QtWidgets.QLabel("目标力"), r, 0)
        grid.addWidget(self.force_n, r, 1)
        grid.addWidget(QtWidgets.QLabel("最大下压位移"), r, 2)
        grid.addWidget(self.push_dist, r, 3)
        grid.addWidget(QtWidgets.QLabel("下压速度"), r, 4)
        grid.addWidget(self.push_vel, r, 5)

        r += 1
        grid.addWidget(QtWidgets.QLabel("力带宽"), r, 0)
        grid.addWidget(self.force_band, r, 1)
        grid.addWidget(QtWidgets.QLabel("判稳时间"), r, 2)
        grid.addWidget(self.chk_ms, r, 3)
        grid.addWidget(QtWidgets.QLabel("每次按压采样帧数"), r, 4)
        grid.addWidget(self.static_frames, r, 5)

        r += 1
        grid.addWidget(QtWidgets.QLabel("每标签重复按压次数"), r, 0)
        grid.addWidget(self.repeat_presses, r, 1)

        r += 1
        grid.addWidget(QtWidgets.QLabel("轴0范围"), r, 0)
        grid.addWidget(self.axis0_min, r, 1)
        grid.addWidget(QtWidgets.QLabel("到"), r, 2)
        grid.addWidget(self.axis0_max, r, 3)
        grid.addWidget(QtWidgets.QLabel("轴1范围"), r, 4)
        grid.addWidget(self.axis1_min, r, 5)

        r += 1
        grid.addWidget(QtWidgets.QLabel("轴1最大"), r, 0)
        grid.addWidget(self.axis1_max, r, 1)
        grid.addWidget(QtWidgets.QLabel("步进"), r, 2)
        grid.addWidget(self.step_deg, r, 3)
        grid.addWidget(QtWidgets.QLabel("单点超时"), r, 4)
        grid.addWidget(self.point_timeout, r, 5)

        r += 1
        grid.addWidget(QtWidgets.QLabel("输出目录"), r, 0)
        grid.addWidget(self.output_dir, r, 1, 1, 5)

        root.addLayout(grid)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        root.addWidget(self.progress)

        self.torque_status_label = QtWidgets.QLabel("力矩电机状态：未连接")
        root.addWidget(self.torque_status_label)

        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        root.addWidget(self.log, 1)

    def _append_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {msg}")

    def _update_progress(self, done: int, total: int):
        if total <= 0:
            self.progress.setValue(0)
            return
        self.progress.setValue(int(done * 100 / total))

    def _run_bg(self, fn):
        with self._busy_lock:
            if self._worker and self._worker.is_alive():
                self.sig_log.emit("当前有任务执行中，请先停止或等待完成")
                return
            def _safe_runner():
                try:
                    fn()
                except Exception as e:
                    self.sig_log.emit(f"任务异常: {e}")

            self._worker = threading.Thread(target=_safe_runner, daemon=True)
            self._worker.start()

    def _array_preview_loop(self):
        while self._preview_running:
            try:
                if not self.array_sensor:
                    time.sleep(0.2)
                    continue

                if not (self.array_3d_dialog and self.array_3d_dialog.isVisible()):
                    time.sleep(0.15)
                    continue

                worker_busy = bool(self._worker and self._worker.is_alive())
                if worker_busy:
                    # 采集进行中仅低频读取单帧，减少对主采样流程的影响。
                    frame = self._sensor_read_frame()
                else:
                    frames = self._sensor_read_frames()
                    frame = frames[-1] if frames else self._sensor_read_frame()
                if frame is None:
                    time.sleep(0.08 if worker_busy else 0.05)
                    continue

                self._set_last_array_frame(frame)
                self._refresh_array_3d_throttled(force=False)
                time.sleep(0.10 if worker_busy else 0.06)
            except Exception:
                time.sleep(0.2)

    def _set_last_array_frame(self, frame: Optional[Dict]):
        with self._array_frame_lock:
            self._last_array_frame = frame

    def _refresh_array_3d_throttled(self, force: bool = False):
        if not (self.array_3d_dialog and self.array_3d_dialog.isVisible()):
            return
        now = time.time()
        if (not force) and (now - self._last_3d_refresh_ts < self._collect_3d_refresh_interval_s):
            return
        self._last_3d_refresh_ts = now
        QtCore.QMetaObject.invokeMethod(self, "_refresh_array_3d_on_ui", QtCore.Qt.QueuedConnection)

    def _get_last_array_frame(self) -> Optional[Dict]:
        with self._array_frame_lock:
            return self._last_array_frame

    def _sensor_read_frame(self):
        if not self.array_sensor:
            return None
        with self._sensor_io_lock:
            return self.array_sensor.read_frame()

    def _sensor_read_frames(self):
        if not self.array_sensor:
            return []
        if not hasattr(self.array_sensor, "read_frames"):
            return []
        with self._sensor_io_lock:
            return self.array_sensor.read_frames()

    def connect_all(self):
        self._run_bg(self._connect_all_impl)

    def _connect_all_impl(self):
        try:
            self.sig_log.emit("开始连接设备...")

            self.motion = LTSMCMotionCard(self.cfg["motioncard"])
            self.motion.connect()
            self.sig_log.emit("运动卡已连接")

            self.torque = TorqueMotorCard(self.cfg.get("torque_motor", {}))
            self.torque.connect()
            self.sig_log.emit("力矩电机已连接")

            array_cfg = self.cfg["sensor"]["array_sensor"]
            self.array_sensor = create_array_sensor(array_cfg)
            if not initialize_array_sensor(self.array_sensor):
                raise RuntimeError("阵列传感器初始化失败")
            self.sig_log.emit("阵列传感器已连接")
            self.sig_log.emit("设备连接完成")
        except Exception as e:
            self.sig_log.emit(f"连接失败: {e}")

    def zero_array_sensor(self):
        self._run_bg(self._zero_array_sensor_impl)

    def _zero_array_sensor_impl(self):
        if not self.array_sensor:
            self.sig_log.emit("阵列传感器未连接")
            return

        frames = self._sensor_read_frames()
        frame = frames[-1] if frames else self._sensor_read_frame()
        if frame is None:
            frame = self._get_last_array_frame()
            if frame is None:
                self.sig_log.emit("暂无阵列数据，无法清零")
                return

        self._set_last_array_frame(frame)
        self._zero_reference_ui = np.asarray(frame["raw"], dtype=float).copy()
        self.array_sensor.processor.zero(frame["raw"], frame["temp1"], frame["temp2"])
        self.sig_log.emit("阵列传感器清零完成")

    def show_array_3d(self):
        self._run_bg(self._show_array_3d_impl)

    def _show_array_3d_impl(self):
        if not self.array_sensor:
            self.sig_log.emit("阵列传感器未连接")
            return

        frames = self._sensor_read_frames()
        frame = frames[-1] if frames else self._sensor_read_frame()
        if frame is None:
            self.sig_log.emit("暂无阵列数据，无法显示3D")
            return

        self._set_last_array_frame(frame)
        QtCore.QMetaObject.invokeMethod(self, "_show_array_3d_on_ui", QtCore.Qt.QueuedConnection)

    @QtCore.pyqtSlot()
    def _show_array_3d_on_ui(self):
        frame = self._get_last_array_frame()
        if frame is None:
            self.sig_log.emit("暂无阵列数据，无法显示3D")
            return

        if self.array_3d_dialog is None:
            sensor_cfg = self.cfg["sensor"]["array_sensor"]
            self.array_3d_dialog = ArraySensor3DDialog(sensor_cfg, parent=self)

        self.array_3d_dialog.update_from_frame(frame, self._zero_reference_ui)
        self.array_3d_dialog.show()
        self.array_3d_dialog.raise_()
        self.array_3d_dialog.activateWindow()
        self.sig_log.emit("3D图像已刷新")

    @QtCore.pyqtSlot()
    def _refresh_array_3d_on_ui(self):
        frame = self._get_last_array_frame()
        if frame is None or self.array_3d_dialog is None:
            return
        self.array_3d_dialog.update_from_frame(frame, self._zero_reference_ui)

    def home_axes(self):
        # stop_collect 后允许手动动作继续执行
        self._stop_event.clear()
        self._run_bg(self._home_axes_impl)

    def _home_axes_impl(self):
        if not self.motion:
            self.sig_log.emit("运动卡未连接")
            return

        for axis in (0, 1):
            self.sig_log.emit(f"轴{axis}初始化...")
            if not full_axis_initialization(self.motion, axis):
                self.sig_log.emit(f"轴{axis}初始化失败")
                return
            self.sig_log.emit(f"轴{axis}回原点...")
            if not perform_homing(self.motion, axis, timeout=60.0):
                self.sig_log.emit(f"轴{axis}回原点失败")
                return

        self.sig_log.emit("轴0/1回原点完成")

    def home_torque(self):
        # stop_collect 后允许手动动作继续执行
        self._stop_event.clear()
        self._run_bg(self._home_torque_impl)

    def _home_torque_impl(self):
        if not self.torque:
            self.sig_log.emit("力矩电机未连接")
            return
        self._home_torque_only(timeout_s=20.0)
        self.sig_log.emit("力矩电机回原点完成")

    def zero_torque_force(self):
        # stop_collect 后允许手动动作继续执行
        self._stop_event.clear()
        self._run_bg(self._zero_torque_force_impl)

    def _zero_torque_force_impl(self):
        if not self.torque:
            self.sig_log.emit("力矩电机未连接")
            return
        self._force_zero_torque(log_success=True)

    def _force_zero_torque(self, log_success: bool = False):
        try:
            # 先发停机指令，再执行力清零，提升清零成功率。
            self.torque.stop(0)
        except Exception:
            pass
        try:
            self.torque.trigger_command(25)
            self._last_torque_force_zero_ts = time.time()
            if log_success:
                self.sig_log.emit("已发送力清零（#25）")
        except Exception as e:
            self.sig_log.emit(f"力清零失败: {e}")

    def _force_zero_torque_checked(self, retries: int = 3, settle_s: float = 0.15, ok_abs_force_n: float = 0.5) -> bool:
        """
        采集流程中的力清零：带重试与读数校验，避免长时间运行后的力零点漂移累积。
        """
        last_force = float("nan")
        for _ in range(retries):
            self._force_zero_torque(log_success=False)
            time.sleep(settle_s)
            try:
                st = self.torque.read_status()
                last_force = float(st["force"])
                if np.isfinite(last_force) and abs(last_force) <= ok_abs_force_n:
                    self.sig_log.emit(f"力清零完成，当前力={last_force:.3f} N")
                    return True
            except Exception:
                pass
        self.sig_log.emit(f"力清零校验未通过，继续流程（当前力={last_force:.3f} N）")
        return False

    def _wait_force_zero_cooldown_before_motion(self, action_name: str):
        elapsed = time.time() - self._last_torque_force_zero_ts
        remain = self._torque_force_zero_cooldown_s - elapsed
        if remain <= 0:
            return
        self.sig_log.emit(f"力清零后等待 {remain:.3f}s，再执行{action_name}")
        # 冷却等待不应阻断后续动作，避免在非采集流程中误触 stop_event 导致电机不运动。
        time.sleep(remain)

    def _home_torque_only(self, timeout_s: float, require_motion_start: bool = False):
        self._wait_force_zero_cooldown_before_motion("回原点")
        self.torque.home(0)
        self._wait_torque_done(timeout_s, require_motion_start=require_motion_start)

    def _retract_torque_step(self, timeout_s: float, step_mm: Optional[float] = None):
        dist = float(step_mm if step_mm is not None else self._torque_retract_step_mm)
        if dist <= 0:
            raise ValueError("回退步长必须大于0")
        self._wait_force_zero_cooldown_before_motion("回退")
        self.torque.move_rel(0, -dist)
        self._wait_torque_done(timeout_s, require_motion_start=True)
        self.sig_log.emit(f"力矩电机回退完成：{-dist:.3f} mm")

    def start_collect(self):
        self._stop_event.clear()
        self._run_bg(self._collect_impl)

    def stop_collect(self):
        self._stop_event.set()
        self.sig_log.emit("已请求停止采集")

    def _collect_impl(self):
        if not (self.motion and self.torque and self.array_sensor):
            self.sig_log.emit("请先连接所有设备")
            return

        try:
            params = self._read_params()
        except Exception as e:
            self.sig_log.emit(f"参数错误: {e}")
            return

        try:
            self._prepare_home_before_collect()
        except Exception as e:
            self.sig_log.emit(f"采集前回零失败: {e}")
            return

        axis0_vals = frange(params["axis0_min"], params["axis0_max"], params["step_deg"])
        axis1_vals = frange(params["axis1_min"], params["axis1_max"], params["step_deg"])
        points = [(a0, a1) for a0 in axis0_vals for a1 in axis1_vals]
        total_points = len(points)
        total_samples = total_points * params["repeat_presses"]

        run_id = make_run_id("collect")
        out_root = os.path.join(params["output_dir"], run_id)
        os.makedirs(out_root, exist_ok=True)

        writer = ArrayDatasetWriter(
            output_root=out_root,
            run_id=run_id,
            run_meta=build_run_meta(self.cfg, params),
        )

        self.sig_log.emit(
            f"开始采集，run_id={run_id}, 标签点数={total_points}, "
            f"每标签重复按压={params['repeat_presses']}次, 总样本数={total_samples}"
        )

        done = 0
        sample_idx = 1
        zero_interval = max(1, total_samples // 4)
        self.sig_log.emit(f"力清零策略：开始1次 + 每{zero_interval}样本1次 + 结束1次")

        try:
            # 采集开始前先做一次力清零
            self._force_zero_torque_checked(retries=3, settle_s=0.15, ok_abs_force_n=0.5)
            # 采集开始前先做一次阵列清零，确保首个样本的3D与相对量基线一致。
            self._zero_array_sensor_impl()

            for theta0, theta1 in points:
                if self._stop_event.is_set():
                    self.sig_log.emit("采集被用户停止")
                    break

                # 1) 平台角度运动（每个标签点执行一次）
                self._move_axis_checked(0, theta0, params["point_timeout"])
                self._move_axis_checked(1, theta1, params["point_timeout"])

                # 2) 同一标签重复按压采样，增加标签内多样性
                for rep in range(1, params["repeat_presses"] + 1):
                    if self._stop_event.is_set():
                        self.sig_log.emit("采集被用户停止")
                        break

                    # 力矩电机下压
                    start_pos = self.torque.get_position(0)
                    self._wait_force_zero_cooldown_before_motion("下压")
                    self.torque.precise_push(
                        params["force_n"],
                        params["push_dist"],
                        params["push_vel"],
                        params["force_band"],
                        int(params["chk_ms"]),
                    )
                    self._wait_torque_force_ready(
                        timeout_s=params["point_timeout"],
                        target_force_n=params["force_n"],
                        force_band_n=params["force_band"],
                        stable_ms=int(params["chk_ms"]),
                        start_pos_mm=start_pos,
                        max_travel_mm=params["push_dist"],
                        require_motion_start=True,
                    )

                    # 静态采样
                    frames = self._collect_array_frames(params["static_frames"], timeout_s=params["point_timeout"])
                    if len(frames) < params["static_frames"]:
                        raise RuntimeError(
                            f"点({theta0},{theta1})第{rep}次采样帧不足: {len(frames)}/{params['static_frames']}"
                        )

                    # 单样本保存
                    rec = writer.save_sample(
                        sample_idx=sample_idx,
                        theta0_cmd_deg=theta0,
                        theta1_cmd_deg=theta1,
                        frames=frames,
                    )

                    # 力矩电机先回退 1mm，再执行清零，避免受力状态清零造成3D基线偏移。
                    self._retract_torque_step(timeout_s=params["point_timeout"], step_mm=1.0)

                    # 每个样本完成后执行一次阵列传感器清零，减少零点漂移累积。
                    self._zero_array_sensor_impl()

                    sample_idx += 1
                    done += 1
                    self.sig_progress.emit(done, total_samples)
                    self.sig_log.emit(
                        f"✅ 完成 {done}/{total_samples}: ({theta0:+.3f},{theta1:+.3f}) 第{rep}/{params['repeat_presses']}次 -> {rec.sample_path}"
                    )

                    # 采集中按总样本 1/4 间隔执行力清零（不在最后一个样本重复）
                    if done < total_samples and done % zero_interval == 0:
                        self._force_zero_torque_checked(retries=3, settle_s=0.15, ok_abs_force_n=0.5)

            if done == total_samples and not self._stop_event.is_set():
                self.sig_log.emit("全部点采集完成，执行收尾回零：力矩电机 -> 轴0/轴1")
                self._home_torque_only(timeout_s=30.0, require_motion_start=True)
                self._home_axes_impl()
                self._force_zero_torque_checked(retries=3, settle_s=0.15, ok_abs_force_n=0.5)

            self.sig_log.emit(f"采集结束：完成样本数 {done}/{total_samples}")
            self.sig_log.emit(f"输出目录：{out_root}")

        except Exception as e:
            self.sig_log.emit(f"采集异常: {e}")
        finally:
            writer.close()

    def _prepare_home_before_collect(self):
        self.sig_log.emit("采集前执行回零：轴0/轴1 -> 力矩电机")
        for axis in (0, 1):
            if self._stop_event.is_set():
                raise RuntimeError("用户停止")
            self.sig_log.emit(f"[预处理] 轴{axis}初始化...")
            if not full_axis_initialization(self.motion, axis):
                raise RuntimeError(f"轴{axis}初始化失败")
            self.sig_log.emit(f"[预处理] 轴{axis}回原点...")
            if not perform_homing(self.motion, axis, timeout=60.0):
                raise RuntimeError(f"轴{axis}回原点失败")

        if self._stop_event.is_set():
            raise RuntimeError("用户停止")
        self.sig_log.emit("[预处理] 力矩电机回原点...")
        self._home_torque_only(timeout_s=20.0, require_motion_start=True)
        self.sig_log.emit("采集前回零完成")

    def _read_params(self) -> Dict:
        params = {
            "force_n": float(self.force_n.value()),
            "push_dist": float(self.push_dist.value()),
            "push_vel": float(self.push_vel.value()),
            "force_band": float(self.force_band.value()),
            "chk_ms": int(self.chk_ms.value()),
            "static_frames": int(self.static_frames.value()),
            "repeat_presses": int(self.repeat_presses.value()),
            "axis0_min": float(self.axis0_min.value()),
            "axis0_max": float(self.axis0_max.value()),
            "axis1_min": float(self.axis1_min.value()),
            "axis1_max": float(self.axis1_max.value()),
            "step_deg": float(self.step_deg.value()),
            "point_timeout": float(self.point_timeout.value()),
            "output_dir": self.output_dir.text().strip() or DATASET_ROOT,
        }

        if params["axis0_min"] > params["axis0_max"]:
            raise ValueError("轴0最小值不能大于最大值")
        if params["axis1_min"] > params["axis1_max"]:
            raise ValueError("轴1最小值不能大于最大值")
        if params["step_deg"] <= 0:
            raise ValueError("步进必须 > 0")
        return params

    def _move_axis_checked(self, axis: int, target: float, timeout_s: float):
        self.motion.move_abs(axis, target)
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if self._stop_event.is_set():
                self.motion.stop(axis, mode=1)
                raise RuntimeError("用户停止")
            io = self.motion.read_axis_io(axis)
            if io.get("alm"):
                self.motion.stop(axis, mode=1)
                raise RuntimeError(f"轴{axis}报警")
            if io.get("emg"):
                self.motion.stop(axis, mode=1)
                raise RuntimeError(f"轴{axis}急停")
            if io.get("pel") or io.get("nel"):
                self.motion.stop(axis, mode=1)
                raise RuntimeError(f"轴{axis}触发限位")
            if self.motion.is_done(axis):
                return
            time.sleep(0.02)
        self.motion.stop(axis, mode=1)
        raise RuntimeError(f"轴{axis}运动超时")

    def _wait_torque_done(self, timeout_s: float, require_motion_start: bool = False):
        t0 = time.time()
        stable = 0
        seen_motion = False
        while time.time() - t0 < timeout_s:
            if self._stop_event.is_set():
                self.torque.stop(0)
                raise RuntimeError("用户停止")
            moving = not self.torque.is_done(0)
            vel = abs(self.torque.get_velocity(0))
            if moving or vel >= 0.01:
                seen_motion = True
            if (not moving) or vel < 0.01:
                if require_motion_start and not seen_motion:
                    stable = 0
                else:
                    stable += 1
            else:
                stable = 0
            if stable >= 3:
                return
            time.sleep(0.05)
        self.torque.stop(0)
        raise RuntimeError("力矩电机等待超时")

    def _wait_torque_force_ready(
        self,
        timeout_s: float,
        target_force_n: float,
        force_band_n: float,
        stable_ms: int,
        start_pos_mm: float,
        max_travel_mm: float,
        require_motion_start: bool = False,
    ):
        t0 = time.time()
        seen_motion = False
        dt = 0.05
        need_stable_count = max(1, int(stable_ms / (dt * 1000.0)))
        stable_force_count = 0

        while time.time() - t0 < timeout_s:
            if self._stop_event.is_set():
                self.torque.stop(0)
                raise RuntimeError("用户停止")

            st = self.torque.read_status()
            pos = float(st["position"])
            vel = abs(float(st["velocity"]))
            force = float(st["force"])
            moving = bool(st.get("moving", False))

            if moving or vel >= 0.01:
                seen_motion = True

            if np.isfinite(force) and abs(force - target_force_n) <= force_band_n:
                stable_force_count += 1

            if stable_force_count >= need_stable_count:
                self.sig_log.emit(
                    f"力达到阈值并稳定：F={force:.3f}N, pos={pos:.3f}mm"
                )
                return

            # 在某些工况下命令发出后电机位移/速度变化很小，但力已接近目标。
            # 若尚未检测到明显运动，仅阻止“最大行程”分支，不阻止“力达标”分支。
            if require_motion_start and not seen_motion:
                time.sleep(dt)
                continue

            travel = abs(pos - start_pos_mm)
            if np.isfinite(travel) and travel >= max(0.0, max_travel_mm - 0.05):
                self.sig_log.emit(
                    f"达到最大行程触发采集：travel={travel:.3f}mm, F={force:.3f}N(未达目标{target_force_n:.3f}N)"
                )
                return

            time.sleep(dt)

        self.torque.stop(0)
        raise RuntimeError("力矩电机未在超时时间内达到“目标力稳定”或“最大行程”条件")

    def _collect_array_frames(self, n_frames: int, timeout_s: float) -> List[Dict]:
        collected: List[Dict] = []
        t0 = time.time()
        while len(collected) < n_frames and time.time() - t0 < timeout_s:
            if self._stop_event.is_set():
                raise RuntimeError("用户停止")
            frames = self._sensor_read_frames()
            if not frames:
                one = self._sensor_read_frame()
                frames = [one] if one is not None else []
            if not frames:
                time.sleep(0.001)
                continue
            self._set_last_array_frame(frames[-1])
            self._refresh_array_3d_throttled(force=False)
            need = n_frames - len(collected)
            collected.extend(frames[:need])
        self._refresh_array_3d_throttled(force=True)
        return collected

    @QtCore.pyqtSlot()
    def _refresh_torque_status(self):
        if not self.torque:
            self.torque_status_label.setText("力矩电机状态：未连接")
        else:
            try:
                st = self.torque.read_status()
                self.torque_status_label.setText(
                    f"力矩电机：位置={st['position']:.3f} mm | 速度={st['velocity']:.3f} mm/s | 力={st['force']:.3f} N"
                )
            except Exception as e:
                self.torque_status_label.setText(f"力矩电机状态刷新失败：{e}")

    def closeEvent(self, event):
        self._stop_event.set()
        self._preview_running = False
        try:
            if self._torque_status_timer:
                self._torque_status_timer.stop()
        except Exception:
            pass
        try:
            if self._worker and self._worker.is_alive():
                self._worker.join(timeout=1.5)
        except Exception:
            pass

        try:
            if self._preview_thread and self._preview_thread.is_alive():
                self._preview_thread.join(timeout=1.0)
        except Exception:
            pass

        try:
            if self.array_3d_dialog:
                self.array_3d_dialog.close()
        except Exception:
            pass

        try:
            if self.array_sensor:
                self.array_sensor.disconnect()
        except Exception:
            pass

        try:
            if self.torque:
                self.torque.disconnect()
        except Exception:
            pass

        try:
            if self.motion:
                self.motion.disconnect()
        except Exception:
            pass

        super().closeEvent(event)


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = CollectorUI()
    win.show()
    app.exec_()


if __name__ == "__main__":
    main()
