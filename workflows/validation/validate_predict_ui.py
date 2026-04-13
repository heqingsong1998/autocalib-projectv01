from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import yaml
from PyQt5 import QtCore, QtWidgets

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from drivers.array_sensor.utils import create_array_sensor, initialize_array_sensor
from drivers.motioncard.ltsmc_dll import LTSMCMotionCard
from drivers.motioncard.utils import full_axis_initialization, perform_homing
from drivers.torque_motor.torque_card import TorqueMotorCard
from workflows.validation.infer_single_frame_mlp import SingleFrameMLP, build_feature_from_frame


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "default.yaml")


def load_cfg() -> Dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class ValidationPredictUI(QtWidgets.QMainWindow):
    sig_log = QtCore.pyqtSignal(str)
    sig_progress = QtCore.pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("在线验证系统（轴0/1 + 力矩电机 + 单帧MLP）")
        self.resize(1220, 760)

        self.cfg: Dict = load_cfg()
        self.motion: Optional[LTSMCMotionCard] = None
        self.torque: Optional[TorqueMotorCard] = None
        self.array_sensor = None

        self.model: Optional[SingleFrameMLP] = None
        self.feature_flags: Dict[str, bool] = {
            "use_raw": True,
            "use_relative": False,
            "use_force": False,
            "use_pressure": False,
            "use_temp": False,
        }
        self.model_path_default = self.cfg.get("validation", {}).get(
            "single_frame_model",
            os.path.join(PROJECT_ROOT, "workflows", "training", "artifacts", "single_frame_mlp_model.npz"),
        )

        self._last_array_frame: Optional[Dict] = None
        self._array_lock = threading.Lock()
        self._worker: Optional[threading.Thread] = None
        self._busy_lock = threading.Lock()
        self._stop_event = threading.Event()

        self._status_timer = QtCore.QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(300)

        self._build_ui()
        self.sig_log.connect(self._append_log)
        self.sig_progress.connect(self._update_progress)

    def _build_ui(self):
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_connect = QtWidgets.QPushButton("连接设备")
        self.btn_connect.clicked.connect(self.connect_all)
        self.btn_home_axes = QtWidgets.QPushButton("轴0/轴1回原点")
        self.btn_home_axes.clicked.connect(self.home_axes)
        self.btn_home_torque = QtWidgets.QPushButton("力矩电机回原点")
        self.btn_home_torque.clicked.connect(self.home_torque)
        self.btn_load_model = QtWidgets.QPushButton("加载模型")
        self.btn_load_model.clicked.connect(self.load_model)
        self.btn_oneclick = QtWidgets.QPushButton("一键预测（随机30组）")
        self.btn_oneclick.clicked.connect(self.start_one_click_predict)
        self.btn_stop = QtWidgets.QPushButton("停止")
        self.btn_stop.setStyleSheet("background:#d32f2f;color:white;font-weight:bold;")
        self.btn_stop.clicked.connect(self.stop_tasks)

        for b in (
            self.btn_connect,
            self.btn_home_axes,
            self.btn_home_torque,
            self.btn_load_model,
            self.btn_oneclick,
            self.btn_stop,
        ):
            btn_row.addWidget(b)
        root.addLayout(btn_row)

        grid = QtWidgets.QGridLayout()

        self.model_path = QtWidgets.QLineEdit(self.model_path_default)

        self.random_count = QtWidgets.QSpinBox()
        self.random_count.setRange(1, 2000)
        self.random_count.setValue(30)

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

        self.point_timeout = QtWidgets.QDoubleSpinBox()
        self.point_timeout.setRange(1.0, 120.0)
        self.point_timeout.setValue(15.0)
        self.point_timeout.setSuffix(" s")

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

        self.chk_zero_each_point = QtWidgets.QCheckBox("每组预测前阵列清零（推荐）")
        self.chk_zero_each_point.setChecked(True)

        r = 0
        grid.addWidget(QtWidgets.QLabel("模型路径"), r, 0)
        grid.addWidget(self.model_path, r, 1, 1, 5)

        r += 1
        grid.addWidget(QtWidgets.QLabel("随机组数"), r, 0)
        grid.addWidget(self.random_count, r, 1)
        grid.addWidget(QtWidgets.QLabel("单点超时"), r, 2)
        grid.addWidget(self.point_timeout, r, 3)

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
        grid.addWidget(QtWidgets.QLabel("目标力"), r, 2)
        grid.addWidget(self.force_n, r, 3)
        grid.addWidget(QtWidgets.QLabel("最大下压位移"), r, 4)
        grid.addWidget(self.push_dist, r, 5)

        r += 1
        grid.addWidget(QtWidgets.QLabel("下压速度"), r, 0)
        grid.addWidget(self.push_vel, r, 1)
        grid.addWidget(QtWidgets.QLabel("力带宽"), r, 2)
        grid.addWidget(self.force_band, r, 3)
        grid.addWidget(QtWidgets.QLabel("判稳时间"), r, 4)
        grid.addWidget(self.chk_ms, r, 5)

        r += 1
        grid.addWidget(self.chk_zero_each_point, r, 0, 1, 3)

        root.addLayout(grid)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        root.addWidget(self.progress)

        self.motor_status = QtWidgets.QLabel("力矩电机状态：未连接")
        self.pred_status = QtWidgets.QLabel("在线预测：模型未加载")
        root.addWidget(self.motor_status)
        root.addWidget(self.pred_status)

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

            def _runner():
                try:
                    fn()
                except Exception as e:
                    self.sig_log.emit(f"任务异常: {e}")

            self._worker = threading.Thread(target=_runner, daemon=True)
            self._worker.start()

    def _set_last_frame(self, frame: Optional[Dict]):
        with self._array_lock:
            self._last_array_frame = frame

    def _get_last_frame(self) -> Optional[Dict]:
        with self._array_lock:
            return self._last_array_frame

    def connect_all(self):
        self._run_bg(self._connect_all_impl)

    def _connect_all_impl(self):
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

    def load_model(self):
        model_path = self.model_path.text().strip()
        if not model_path:
            self.pred_status.setText("在线预测：模型路径为空")
            return
        model_path = os.path.abspath(model_path)
        if not os.path.isfile(model_path):
            self.model = None
            self.pred_status.setText(f"在线预测：模型不存在（{model_path}）")
            self.sig_log.emit(f"模型不存在: {model_path}")
            return

        self.model = SingleFrameMLP(model_path)
        meta_path = os.path.splitext(model_path)[0].replace("_model", "_meta") + ".json"
        if os.path.isfile(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            flags = meta.get("feature_flags") or {}
            for k in self.feature_flags:
                if k in flags:
                    self.feature_flags[k] = bool(flags[k])

        self.pred_status.setText("在线预测：模型已加载")
        self.sig_log.emit(f"模型已加载: {model_path}")

    def home_axes(self):
        self._stop_event.clear()
        self._run_bg(self._home_axes_impl)

    def _home_axes_impl(self):
        if not self.motion:
            self.sig_log.emit("运动卡未连接")
            return
        for axis in (0, 1):
            self.sig_log.emit(f"轴{axis}初始化...")
            if not full_axis_initialization(self.motion, axis):
                raise RuntimeError(f"轴{axis}初始化失败")
            self.sig_log.emit(f"轴{axis}回原点...")
            if not perform_homing(self.motion, axis, timeout=60.0):
                raise RuntimeError(f"轴{axis}回原点失败")
        self.sig_log.emit("轴0/1回原点完成")

    def home_torque(self):
        self._stop_event.clear()
        self._run_bg(self._home_torque_impl)

    def _home_torque_impl(self):
        if not self.torque:
            self.sig_log.emit("力矩电机未连接")
            return
        self.torque.home(0)
        self._wait_torque_done(timeout_s=20.0, require_motion_start=True)
        self.sig_log.emit("力矩电机回原点完成")

    def start_one_click_predict(self):
        self._stop_event.clear()
        self._run_bg(self._one_click_predict_impl)

    def stop_tasks(self):
        self._stop_event.set()
        self.sig_log.emit("已请求停止")

    def _read_params(self) -> Dict[str, float]:
        params = {
            "count": int(self.random_count.value()),
            "axis0_min": float(self.axis0_min.value()),
            "axis0_max": float(self.axis0_max.value()),
            "axis1_min": float(self.axis1_min.value()),
            "axis1_max": float(self.axis1_max.value()),
            "timeout": float(self.point_timeout.value()),
            "force_n": float(self.force_n.value()),
            "push_dist": float(self.push_dist.value()),
            "push_vel": float(self.push_vel.value()),
            "force_band": float(self.force_band.value()),
            "chk_ms": int(self.chk_ms.value()),
        }
        if params["axis0_min"] > params["axis0_max"]:
            raise ValueError("轴0最小值不能大于最大值")
        if params["axis1_min"] > params["axis1_max"]:
            raise ValueError("轴1最小值不能大于最大值")
        return params

    def _one_click_predict_impl(self):
        if not (self.motion and self.torque and self.array_sensor):
            self.sig_log.emit("请先连接设备")
            return
        if not self.model:
            self.sig_log.emit("请先加载模型")
            return

        p = self._read_params()
        rng = np.random.default_rng(int(time.time()))
        points = [
            (
                float(rng.uniform(p["axis0_min"], p["axis0_max"])),
                float(rng.uniform(p["axis1_min"], p["axis1_max"])),
            )
            for _ in range(p["count"])
        ]

        self.sig_log.emit(f"开始一键预测，共 {len(points)} 组随机角度")
        self._home_axes_impl()
        self._home_torque_impl()

        errs0: List[float] = []
        errs1: List[float] = []
        done = 0

        for idx, (t0_cmd, t1_cmd) in enumerate(points, start=1):
            if self._stop_event.is_set():
                self.sig_log.emit("一键预测被用户停止")
                break

            if self.chk_zero_each_point.isChecked():
                self._zero_array_sensor_for_validation(timeout_s=min(3.0, p["timeout"]))

            self._move_axis_checked(0, t0_cmd, p["timeout"])
            self._move_axis_checked(1, t1_cmd, p["timeout"])

            start_pos = self.torque.get_position(0)
            self.torque.precise_push(
                p["force_n"],
                p["push_dist"],
                p["push_vel"],
                p["force_band"],
                int(p["chk_ms"]),
            )
            self._wait_torque_force_ready(
                timeout_s=p["timeout"],
                target_force_n=p["force_n"],
                force_band_n=p["force_band"],
                stable_ms=int(p["chk_ms"]),
                start_pos_mm=start_pos,
                max_travel_mm=p["push_dist"],
                require_motion_start=True,
            )

            frame = self._read_latest_frame(timeout_s=p["timeout"])
            feat = build_feature_from_frame(
                frame,
                use_raw=self.feature_flags["use_raw"],
                use_relative=self.feature_flags["use_relative"],
                use_force=self.feature_flags["use_force"],
                use_pressure=self.feature_flags["use_pressure"],
                use_temp=self.feature_flags["use_temp"],
            )
            pred = self.model.predict(feat)

            e0 = float(pred[0] - t0_cmd)
            e1 = float(pred[1] - t1_cmd)
            errs0.append(abs(e0))
            errs1.append(abs(e1))

            self.sig_log.emit(
                f"[{idx:02d}/{len(points)}] cmd=({t0_cmd:+.3f},{t1_cmd:+.3f})°, "
                f"pred=({pred[0]:+.3f},{pred[1]:+.3f})°, err=({e0:+.3f},{e1:+.3f})°"
            )

            self.torque.move_rel(0, -1.0)
            self._wait_torque_done(timeout_s=p["timeout"], require_motion_start=True)

            done += 1
            self.sig_progress.emit(done, len(points))

        if done > 0:
            mae0 = float(np.mean(errs0))
            mae1 = float(np.mean(errs1))
            mae = float(np.mean(np.asarray(errs0) + np.asarray(errs1)) / 2.0)
            self.sig_log.emit(f"预测复测完成: done={done}/{len(points)}, MAE(theta0/theta1/all)={mae0:.4f}/{mae1:.4f}/{mae:.4f}°")

        if done == len(points) and not self._stop_event.is_set():
            self.sig_log.emit("全部复测完成，执行回零：力矩电机 -> 轴0/轴1")
            self._home_torque_impl()
            self._home_axes_impl()

    def _zero_array_sensor_for_validation(self, timeout_s: float = 2.0):
        frame = self._read_latest_frame(timeout_s=timeout_s)
        raw = frame.get("raw")
        if raw is None:
            raise RuntimeError("阵列帧缺少 raw，无法清零")

        temp1 = float(frame.get("temp1", 0.0))
        temp2 = float(frame.get("temp2", 0.0))
        self.array_sensor.processor.zero(raw, temp1, temp2)
        self.sig_log.emit("阵列传感器已清零（本组预测前）")
        time.sleep(0.15)

    def _read_latest_frame(self, timeout_s: float) -> Dict:
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if self._stop_event.is_set():
                raise RuntimeError("用户停止")
            frames = self.array_sensor.read_frames() if hasattr(self.array_sensor, "read_frames") else []
            frame = frames[-1] if frames else self.array_sensor.read_frame()
            if frame is not None:
                self._set_last_frame(frame)
                return frame
            time.sleep(0.01)
        raise RuntimeError("读取阵列传感器帧超时")

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
                return

            if require_motion_start and not seen_motion:
                time.sleep(dt)
                continue

            travel = abs(pos - start_pos_mm)
            if np.isfinite(travel) and travel >= max(0.0, max_travel_mm - 0.05):
                return

            time.sleep(dt)

        self.torque.stop(0)
        raise RuntimeError("力矩电机未在超时时间内达到“目标力稳定”或“最大行程”条件")

    @QtCore.pyqtSlot()
    def _refresh_status(self):
        if not self.torque:
            self.motor_status.setText("力矩电机状态：未连接")
        else:
            try:
                st = self.torque.read_status()
                self.motor_status.setText(
                    f"力矩电机：位置={st['position']:.3f} mm | 速度={st['velocity']:.3f} mm/s | 力={st['force']:.3f} N"
                )
            except Exception as e:
                self.motor_status.setText(f"力矩电机状态刷新失败：{e}")

        if not self.model:
            self.pred_status.setText("在线预测：模型未加载")
            return

        frame = self._get_last_frame()
        if frame is None and self.array_sensor and not (self._worker and self._worker.is_alive()):
            try:
                frames = self.array_sensor.read_frames() if hasattr(self.array_sensor, "read_frames") else []
                frame = frames[-1] if frames else self.array_sensor.read_frame()
                if frame is not None:
                    self._set_last_frame(frame)
            except Exception:
                frame = None

        if frame is None:
            self.pred_status.setText("在线预测：等待传感器帧")
            return

        try:
            feat = build_feature_from_frame(
                frame,
                use_raw=self.feature_flags["use_raw"],
                use_relative=self.feature_flags["use_relative"],
                use_force=self.feature_flags["use_force"],
                use_pressure=self.feature_flags["use_pressure"],
                use_temp=self.feature_flags["use_temp"],
            )
            pred = self.model.predict(feat)
            self.pred_status.setText(f"在线预测：theta0={pred[0]:+.3f}° | theta1={pred[1]:+.3f}°")
        except Exception as e:
            self.pred_status.setText(f"在线预测失败：{e}")

    def closeEvent(self, event):
        self._stop_event.set()
        try:
            if self._status_timer:
                self._status_timer.stop()
        except Exception:
            pass

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
    win = ValidationPredictUI()
    win.show()
    app.exec_()


if __name__ == "__main__":
    main()
