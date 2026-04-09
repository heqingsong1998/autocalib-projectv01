import os
import sys
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import yaml
from PyQt5 import QtCore, QtWidgets

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

        self._worker: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._busy_lock = threading.Lock()

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
        self.btn_home_axes = QtWidgets.QPushButton("轴0/轴1回原点")
        self.btn_home_axes.clicked.connect(self.home_axes)
        self.btn_home_torque = QtWidgets.QPushButton("力矩电机回原点")
        self.btn_home_torque.clicked.connect(self.home_torque)
        self.btn_start = QtWidgets.QPushButton("开始采集")
        self.btn_start.clicked.connect(self.start_collect)
        self.btn_stop = QtWidgets.QPushButton("停止采集")
        self.btn_stop.clicked.connect(self.stop_collect)
        self.btn_stop.setStyleSheet("background:#d32f2f;color:white;font-weight:bold;")

        for b in (
            self.btn_connect,
            self.btn_zero_sensor,
            self.btn_home_axes,
            self.btn_home_torque,
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
        self.push_dist.setValue(8.0)
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
        self.static_frames.setValue(20)

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
        self.point_timeout.setValue(15.0)
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
        grid.addWidget(QtWidgets.QLabel("静态采集帧数"), r, 4)
        grid.addWidget(self.static_frames, r, 5)

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
            self._worker = threading.Thread(target=fn, daemon=True)
            self._worker.start()

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
        frame = self.array_sensor.read_frame()
        if frame is None:
            self.sig_log.emit("暂无阵列数据，无法清零")
            return
        self.array_sensor.processor.zero(frame["raw"], frame["temp1"], frame["temp2"])
        self.sig_log.emit("阵列传感器清零完成")

    def home_axes(self):
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
        self._run_bg(self._home_torque_impl)

    def _home_torque_impl(self):
        if not self.torque:
            self.sig_log.emit("力矩电机未连接")
            return
        self.torque.home(0)
        self._wait_torque_done(20.0)
        self.sig_log.emit("力矩电机回原点完成")

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

        axis0_vals = frange(params["axis0_min"], params["axis0_max"], params["step_deg"])
        axis1_vals = frange(params["axis1_min"], params["axis1_max"], params["step_deg"])
        points = [(a0, a1) for a0 in axis0_vals for a1 in axis1_vals]
        total = len(points)

        run_id = make_run_id("collect")
        out_root = os.path.join(params["output_dir"], run_id)
        os.makedirs(out_root, exist_ok=True)

        writer = ArrayDatasetWriter(
            output_root=out_root,
            run_id=run_id,
            run_meta=build_run_meta(self.cfg, params),
        )

        self.sig_log.emit(f"开始采集，run_id={run_id}, 总点数={total}")

        done = 0
        sample_idx = 1

        try:
            for theta0, theta1 in points:
                if self._stop_event.is_set():
                    self.sig_log.emit("采集被用户停止")
                    break

                # 1) 平台角度运动
                self._move_axis_checked(0, theta0, params["point_timeout"])
                self._move_axis_checked(1, theta1, params["point_timeout"])

                # 2) 力矩电机下压
                self.torque.precise_push(
                    params["force_n"],
                    params["push_dist"],
                    params["push_vel"],
                    params["force_band"],
                    int(params["chk_ms"]),
                )
                self._wait_torque_done(params["point_timeout"])

                # 3) 静态采样
                frames = self._collect_array_frames(params["static_frames"], timeout_s=params["point_timeout"])
                if len(frames) < params["static_frames"]:
                    raise RuntimeError(
                        f"点({theta0},{theta1})采样帧不足: {len(frames)}/{params['static_frames']}"
                    )

                # 4) 单样本保存
                rec = writer.save_sample(
                    sample_idx=sample_idx,
                    theta0_cmd_deg=theta0,
                    theta1_cmd_deg=theta1,
                    frames=frames,
                )

                sample_idx += 1
                done += 1
                self.sig_progress.emit(done, total)
                self.sig_log.emit(
                    f"✅ 完成 {done}/{total}: ({theta0:+.3f},{theta1:+.3f}) -> {rec.sample_path}"
                )

                # 5) 力矩电机回原点，准备下一点
                self.torque.home(0)
                self._wait_torque_done(params["point_timeout"])

            self.sig_log.emit(f"采集结束：完成点数 {done}/{total}")
            self.sig_log.emit(f"输出目录：{out_root}")

        except Exception as e:
            self.sig_log.emit(f"采集异常: {e}")
        finally:
            writer.close()

    def _read_params(self) -> Dict:
        params = {
            "force_n": float(self.force_n.value()),
            "push_dist": float(self.push_dist.value()),
            "push_vel": float(self.push_vel.value()),
            "force_band": float(self.force_band.value()),
            "chk_ms": int(self.chk_ms.value()),
            "static_frames": int(self.static_frames.value()),
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

    def _wait_torque_done(self, timeout_s: float):
        t0 = time.time()
        stable = 0
        while time.time() - t0 < timeout_s:
            if self._stop_event.is_set():
                self.torque.stop(0)
                raise RuntimeError("用户停止")
            moving = not self.torque.is_done(0)
            vel = abs(self.torque.get_velocity(0))
            if (not moving) or vel < 0.01:
                stable += 1
            else:
                stable = 0
            if stable >= 3:
                return
            time.sleep(0.05)
        self.torque.stop(0)
        raise RuntimeError("力矩电机等待超时")

    def _collect_array_frames(self, n_frames: int, timeout_s: float) -> List[Dict]:
        collected: List[Dict] = []
        t0 = time.time()
        while len(collected) < n_frames and time.time() - t0 < timeout_s:
            if self._stop_event.is_set():
                raise RuntimeError("用户停止")
            frames = self.array_sensor.read_frames() if hasattr(self.array_sensor, "read_frames") else []
            if not frames:
                one = self.array_sensor.read_frame()
                frames = [one] if one is not None else []
            if not frames:
                time.sleep(0.001)
                continue
            need = n_frames - len(collected)
            collected.extend(frames[:need])
        return collected

    def closeEvent(self, event):
        self._stop_event.set()
        try:
            if self._worker and self._worker.is_alive():
                self._worker.join(timeout=1.5)
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
