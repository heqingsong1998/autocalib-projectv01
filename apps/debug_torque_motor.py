import sys
import threading
import time
from typing import Optional

import os, sys, yaml, time
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QWidget, QTextEdit, QGridLayout, QGroupBox, QDoubleSpinBox, QSpinBox, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer





from drivers.torque_motor.torque_card import TorqueMotorCard

# ================== 后台执行/并发控制 ==================
_op_lock = threading.Lock()
_op_thread = None

def _set_thread(t):
    global _op_thread
    with _op_lock:
        _op_thread = t

def _clear_thread():
    _set_thread(None)

def _join_thread(timeout=0.5):
    with _op_lock:
        t = _op_thread
    if t and t.is_alive():
        t.join(timeout=timeout)
        with _op_lock:
            return _op_thread
    return None

def _bg_wrapper(target):
    try:
        target()
    finally:
        _clear_thread()

def _run_in_bg(is_moving_fn, target):
    """
    仅允许一个动作线程；若线程存活但轴已停止，判作僵尸并释放引用。
    """
    global _op_thread
    with _op_lock:
        if _op_thread and _op_thread.is_alive():
            try:
                if not is_moving_fn():
                    _op_thread = None
                    print("检测到僵尸线程，已清理引用，允许启动新动作。")
                else:
                    print("已有动作在运行，请先 STOP 或等待结束。")
                    return False
            except Exception:
                print("已有动作在运行，请先 STOP 或等待结束。")
                return False
        t = threading.Thread(target=lambda: _bg_wrapper(target), daemon=True)
        _op_thread = t
        t.start()
        return True

# ================== 通用等待/STOP ==================
def wait_until_stop(card: TorqueMotorCard, axis: int = 0, timeout=60, dt=0.05, vel_eps=0.01):
    t0 = time.time()
    stable = 0
    while time.time() - t0 < timeout:
        try:
            moving = not card.is_done(axis)
        except Exception:
            moving = True
        try:
            vel = abs(card.get_velocity(axis))
        except Exception:
            vel = 999.0

        reached = False
        if (not moving) or reached or (vel < vel_eps):
            stable += 1
        else:
            stable = 0
        if stable >= 3:
            return True
        time.sleep(dt)
    return False

def stop_now(card: TorqueMotorCard, axis: int = 0, log_fn=print, fallback_servo_cycle=True):
    """优先 stop，失败则断/上伺服，最后清理后台线程引用"""
    try:
        card.stop(axis)
    except Exception as e:
        log_fn(f"stop() 异常：{e}")

    if not wait_until_stop(card, axis, timeout=2):
        if fallback_servo_cycle:
            log_fn("stop 未立刻生效，尝试断/上伺服...")
            try:
                card.set_servo(False); time.sleep(0.1); card.set_servo(True)
            except Exception as e:
                log_fn(f"伺服切换失败：{e}")

    _join_thread(timeout=0.5)

    try:
        moving = not card.is_done(axis)
    except Exception:
        moving = False
    if not moving:
        _clear_thread()
        return True
    return False

# ================== 主界面 ==================
class MotorControlUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.card: Optional[TorqueMotorCard] = None
        self.status_timer: Optional[QTimer] = None
        self.initUI()
        self.connect_motor()

    # ---------- UI 结构 ----------
    def initUI(self):
        self.setWindowTitle("电机控制（参照 motioncard 风格）")
        self.setGeometry(120, 120, 1050, 700)

        main = QVBoxLayout()

        # 连接参数
        conn_group = QGroupBox("连接")
        cg = QGridLayout()
        self.port_edit = QLineEdit(r"\\.\COM20")
        self.baud_edit = QSpinBox(); self.baud_edit.setRange(1200, 10000000); self.baud_edit.setValue(115200)
        self.slave_edit = QSpinBox(); self.slave_edit.setRange(0, 247); self.slave_edit.setValue(0)
        self.connect_btn = QPushButton("重连")
        self.connect_btn.clicked.connect(self.reconnect)
        cg.addWidget(QLabel("串口："), 0, 0); cg.addWidget(self.port_edit, 0, 1)
        cg.addWidget(QLabel("波特率："), 0, 2); cg.addWidget(self.baud_edit, 0, 3)
        cg.addWidget(QLabel("从站："), 0, 4); cg.addWidget(self.slave_edit, 0, 5)
        cg.addWidget(self.connect_btn, 0, 6)
        conn_group.setLayout(cg)
        main.addWidget(conn_group)

        # 相对运动参数
        rel_group = QGroupBox("相对运动")
        rg = QGridLayout()
        self.rel_dist = QDoubleSpinBox(); self.rel_dist.setRange(-1000, 1000); self.rel_dist.setValue(10.0); self.rel_dist.setSuffix(" mm")
        self.rel_vel  = QDoubleSpinBox(); self.rel_vel.setRange(0.1, 1000); self.rel_vel.setValue(10.0); self.rel_vel.setSuffix(" mm/s")
        self.rel_acc  = QDoubleSpinBox(); self.rel_acc.setRange(1.0, 5000); self.rel_acc.setValue(50.0); self.rel_acc.setSuffix(" mm/s²")
        self.rel_dec  = QDoubleSpinBox(); self.rel_dec.setRange(1.0, 5000); self.rel_dec.setValue(50.0); self.rel_dec.setSuffix(" mm/s²")
        self.rel_band = QDoubleSpinBox(); self.rel_band.setRange(0.001, 10.0); self.rel_band.setValue(0.1); self.rel_band.setSuffix(" mm")
        self.rel_btn  = QPushButton("执行相对运动")
        self.rel_btn.clicked.connect(self.on_move_rel)

        rg.addWidget(QLabel("距离 Δ (mm):"), 0, 0); rg.addWidget(self.rel_dist, 0, 1)
        rg.addWidget(QLabel("速度 v (mm/s):"), 0, 2); rg.addWidget(self.rel_vel, 0, 3)
        rg.addWidget(QLabel("加速度 acc (mm/s²):"), 1, 0); rg.addWidget(self.rel_acc, 1, 1)
        rg.addWidget(QLabel("减速度 dec (mm/s²):"), 1, 2); rg.addWidget(self.rel_dec, 1, 3)
        rg.addWidget(QLabel("定位带宽 band (mm):"), 2, 0); rg.addWidget(self.rel_band, 2, 1)
        rg.addWidget(self.rel_btn, 2, 3)
        rel_group.setLayout(rg)
        main.addWidget(rel_group)

        # 绝对运动参数
        abs_group = QGroupBox("绝对运动")
        ag = QGridLayout()
        self.abs_pos  = QDoubleSpinBox(); self.abs_pos.setRange(-10000, 10000); self.abs_pos.setValue(50.0); self.abs_pos.setSuffix(" mm")
        self.abs_vel  = QDoubleSpinBox(); self.abs_vel.setRange(0.1, 1000); self.abs_vel.setValue(10.0); self.abs_vel.setSuffix(" mm/s")
        self.abs_acc  = QDoubleSpinBox(); self.abs_acc.setRange(1.0, 5000); self.abs_acc.setValue(50.0); self.abs_acc.setSuffix(" mm/s²")
        self.abs_dec  = QDoubleSpinBox(); self.abs_dec.setRange(1.0, 5000); self.abs_dec.setValue(50.0); self.abs_dec.setSuffix(" mm/s²")
        self.abs_band = QDoubleSpinBox(); self.abs_band.setRange(0.001, 10.0); self.abs_band.setValue(0.1); self.abs_band.setSuffix(" mm")
        self.abs_btn  = QPushButton("执行绝对运动")
        self.abs_btn.clicked.connect(self.on_move_abs)

        ag.addWidget(QLabel("目标位置 (mm):"), 0, 0); ag.addWidget(self.abs_pos, 0, 1)
        ag.addWidget(QLabel("速度 v (mm/s):"), 0, 2); ag.addWidget(self.abs_vel, 0, 3)
        ag.addWidget(QLabel("加速度 acc (mm/s²):"), 1, 0); ag.addWidget(self.abs_acc, 1, 1)
        ag.addWidget(QLabel("减速度 dec (mm/s²):"), 1, 2); ag.addWidget(self.abs_dec, 1, 3)
        ag.addWidget(QLabel("定位带宽 band (mm):"), 2, 0); ag.addWidget(self.abs_band, 2, 1)
        ag.addWidget(self.abs_btn, 2, 3)
        abs_group.setLayout(ag)
        main.addWidget(abs_group)

        # 普通推压
        push_group = QGroupBox("普通推压")
        pg = QGridLayout()
        self.push_force = QDoubleSpinBox(); self.push_force.setRange(0.1, 200.0); self.push_force.setValue(5.0); self.push_force.setSuffix(" N")
        self.push_dist  = QDoubleSpinBox(); self.push_dist.setRange(0.1, 1000.0); self.push_dist.setValue(10.0); self.push_dist.setSuffix(" mm")
        self.push_vel   = QDoubleSpinBox(); self.push_vel.setRange(0.1, 100.0); self.push_vel.setValue(2.0); self.push_vel.setSuffix(" mm/s")
        self.push_btn   = QPushButton("执行普通推压")
        self.push_btn.clicked.connect(self.on_push)

        pg.addWidget(QLabel("力阈值 F (N):"), 0, 0); pg.addWidget(self.push_force, 0, 1)
        pg.addWidget(QLabel("最大行程 D (mm):"), 0, 2); pg.addWidget(self.push_dist, 0, 3)
        pg.addWidget(QLabel("速度 v (mm/s):"), 1, 0); pg.addWidget(self.push_vel, 1, 1)
        pg.addWidget(self.push_btn, 1, 3)
        push_group.setLayout(pg)
        main.addWidget(push_group)

        # 闭环推压
        ppush_group = QGroupBox("闭环推压（力控）")
        pg2 = QGridLayout()
        self.pp_force = QDoubleSpinBox(); self.pp_force.setRange(0.1, 200.0); self.pp_force.setValue(5.0); self.pp_force.setSuffix(" N")
        self.pp_dist  = QDoubleSpinBox(); self.pp_dist.setRange(0.1, 1000.0); self.pp_dist.setValue(10.0); self.pp_dist.setSuffix(" mm")
        self.pp_vel   = QDoubleSpinBox(); self.pp_vel.setRange(0.1, 100.0); self.pp_vel.setValue(2.0); self.pp_vel.setSuffix(" mm/s")
        self.pp_band  = QDoubleSpinBox(); self.pp_band.setRange(0.01, 10.0); self.pp_band.setValue(0.2); self.pp_band.setSuffix(" N")
        self.pp_chkms = QSpinBox();       self.pp_chkms.setRange(10, 5000);   self.pp_chkms.setValue(200)
        self.pp_btn   = QPushButton("进入闭环推压（需 STOP 退出）")
        self.pp_btn.clicked.connect(self.on_precise_push)

        pg2.addWidget(QLabel("目标力 F (N):"), 0, 0); pg2.addWidget(self.pp_force, 0, 1)
        pg2.addWidget(QLabel("最大行程 D (mm):"), 0, 2); pg2.addWidget(self.pp_dist, 0, 3)
        pg2.addWidget(QLabel("速度 v (mm/s):"), 1, 0); pg2.addWidget(self.pp_vel, 1, 1)
        pg2.addWidget(QLabel("力带宽 (N):"), 1, 2); pg2.addWidget(self.pp_band, 1, 3)
        pg2.addWidget(QLabel("判稳时间 (ms):"), 2, 0); pg2.addWidget(self.pp_chkms, 2, 1)
        pg2.addWidget(self.pp_btn, 2, 3)
        ppush_group.setLayout(pg2)
        main.addWidget(ppush_group)

        # 操作行：回零/STOP/力清零
        op_line = QHBoxLayout()
        self.home_btn = QPushButton("回原点"); self.home_btn.clicked.connect(self.on_home)
        self.stop_btn = QPushButton("STOP（最高优先）"); self.stop_btn.setStyleSheet("background:#d32f2f;color:white;font-weight:bold;")
        self.stop_btn.clicked.connect(self.on_stop)
        self.zero_btn = QPushButton("力清零 #25"); self.zero_btn.clicked.connect(self.on_force_zero)
        for b in (self.home_btn, self.stop_btn, self.zero_btn): op_line.addWidget(b)
        main.addLayout(op_line)

        # 状态 & 日志
        self.status_label = QLabel("未连接")
        self.log_output = QTextEdit(); self.log_output.setReadOnly(True)
        main.addWidget(self.status_label)
        main.addWidget(self.log_output)

        cw = QWidget(); cw.setLayout(main)
        self.setCentralWidget(cw)

    # ---------- 连接与状态 ----------
    def connect_motor(self):
        try:
            cfg = dict(
                port=self.port_edit.text(),
                baud=int(self.baud_edit.value()),
                slave=int(self.slave_edit.value()),
            )
            self.card = TorqueMotorCard(cfg)
            self.card.connect()
            self.card.set_servo(True)
            # self.card.config_home(2,10,10)
            try:
                v = self.card.get_version()
                self.log(f"已连接。版本: {getattr(v, 'major', '?')}.{getattr(v, 'minor', '?')}.{getattr(v, 'build', '?')} (type={getattr(v, 'type', '?')})")
            except Exception:
                self.log("已连接。版本读取失败")

            self.status_label.setText("电机状态：已连接")
            self.start_status_timer()
        except Exception as e:
            self.log(f"电机连接失败：{e}")
            self.status_label.setText("电机状态：连接失败")

    def reconnect(self):
        try:
            if self.card:
                try:
                    self.card.set_servo(False)
                except: pass
                try:
                    self.card.disconnect()
                except: pass
                self.card = None
            self.connect_motor()
        except Exception as e:
            self.log(f"重连失败：{e}")

    def start_status_timer(self):
        if self.status_timer:
            self.status_timer.stop()
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_status)
        self.status_timer.start(300)

    def refresh_status(self):
        if not self.card:
            return
        try:
            st = self.card.read_status()
            self.status_label.setText(
                f"位置={st['position']:.3f} mm | 速度={st['velocity']:.3f} mm/s | 力={st['force']:.3f} N | moving={st['moving']}"
            )
        except Exception as e:
            self.status_label.setText(f"状态刷新失败：{e}")

    def log(self, msg: str):
        # 切回主线程更新，避免 QTextCursor 跨线程类型问题
        QTimer.singleShot(0, lambda: self.log_output.append(msg))

    # ---------- 动作按钮回调 ----------
    def on_home(self):
        if not self.card: return
        def job():
            self.log("回原点中...")
            self.card.home(0)
            ok = wait_until_stop(self.card, 0, timeout=120)
            self.log(f"回零结束：{'OK' if ok else '超时'} | pos={self.card.get_position(0):.3f}")
        _run_in_bg(lambda: not self.card.is_done(0), job)

    def on_move_rel(self):
        if not self.card: return
        dist = self.rel_dist.value()
        v    = self.rel_vel.value()
        acc  = self.rel_acc.value()
        dec  = self.rel_dec.value()
        band = self.rel_band.value()
        def job():
            self.log(f"相对运动 Δ={dist} mm @ v={v}, acc={acc}, dec={dec}, band={band}")
            self.card.set_profile(0, 0.0, v, acc, dec, 0.0)
            self.card.set_band(0, band)
            self.card.move_rel(0, dist)
            ok = wait_until_stop(self.card, 0, timeout=60)
            self.log(f"相对运动结束：{'OK' if ok else '超时'} | pos={self.card.get_position(0):.3f}")
        _run_in_bg(lambda: not self.card.is_done(0), job)

    def on_move_abs(self):
        if not self.card: return
        pos  = self.abs_pos.value()
        v    = self.abs_vel.value()
        acc  = self.abs_acc.value()
        dec  = self.abs_dec.value()
        band = self.abs_band.value()
        def job():
            self.log(f"绝对运动 → {pos} mm @ v={v}, acc={acc}, dec={dec}, band={band}")
            self.card.set_profile(0, 0.0, v, acc, dec, 0.0)
            self.card.set_band(0, band)
            self.card.move_abs(0, pos)
            ok = wait_until_stop(self.card, 0, timeout=60)
            self.log(f"绝对运动结束：{'OK' if ok else '超时'} | pos={self.card.get_position(0):.3f}")
        _run_in_bg(lambda: not self.card.is_done(0), job)

    def on_push(self):
        if not self.card: return
        F  = self.push_force.value()
        D  = self.push_dist.value()
        v  = self.push_vel.value()
        def job():
            self.log(f"[PUSH] F={F} N, D={D} mm, v={v} mm/s")
            self.card.push(F, D, v)
            ok = wait_until_stop(self.card, 0, timeout=40)
            self.log(f"普通推压结束：{'OK' if ok else '超时'} | pos={self.card.get_position(0):.3f}")
        _run_in_bg(lambda: not self.card.is_done(0), job)

    def on_precise_push(self):
        if not self.card: return
        F  = self.pp_force.value()
        D  = self.pp_dist.value()
        v  = self.pp_vel.value()
        fb = self.pp_band.value()
        ms = int(self.pp_chkms.value())
        def job():
            self.log(f"[PRECISE] 进入闭环推压：F={F}N, D={D}mm, v={v}mm/s, band={fb}N, chk={ms}ms")
            self.log("提示：闭环推压是持续力控模式，请点 STOP 退出再进行其他运动。")
            self.card.precise_push(F, D, v, fb, ms)
        _run_in_bg(lambda: not self.card.is_done(0), job)

    def on_stop(self):
        if not self.card: return
        ok = stop_now(self.card, 0, log_fn=self.log)
        self.log("STOP 发出：" + ("已停止/释放" if ok else "可能未完全生效"))

    def on_force_zero(self):
        if not self.card: return
        try:
            stop_now(self.card, 0, log_fn=self.log)  # 清零前先停更稳妥
            self.card.trigger_command(25)
            self.log("已发送 力清零（#25）")
        except Exception as e:
            self.log(f"力清零失败：{e}")

    # ---------- 关闭 ----------
    def closeEvent(self, event):
        try:
            if self.status_timer:
                self.status_timer.stop()
        except: pass
        try:
            if self.card:
                try:
                    self.card.set_servo(False)
                    time.sleep(0.05)
                except: pass
                self.card.disconnect()
        except: pass
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ui = MotorControlUI()
    ui.show()
    sys.exit(app.exec_())