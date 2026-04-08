"""阵列触觉传感器补偿算法。"""
from __future__ import annotations

from collections import deque
from typing import Dict, Iterable, Tuple

import numpy as np


class DynamicCompensator:
    def __init__(self, alpha_n: float, beta_n: float, alpha_p: Iterable[float], beta_p: Iterable[float]):
        self.alpha_n = float(alpha_n)
        self.beta_n = float(beta_n)
        self.alpha_p = list(alpha_p)
        self.beta_p = list(beta_p)
        self.reset()

    def reset(self):
        self.coexn = 0.0
        self.coexp = [0.0 for _ in range(len(self.alpha_p))]
        self.raw_old = 0.0

    def update(self, raw: float) -> float:
        diff = raw - self.raw_old
        self.raw_old = raw
        self.coexn = self.coexn * self.alpha_n + (raw - self.coexn) * self.beta_n
        for i in range(len(self.coexp)):
            self.coexp[i] = self.coexp[i] * self.alpha_p[i] + diff * self.beta_p[i]
        return raw - self.coexn + sum(self.coexp)


class HysteresisCompensator:
    def __init__(self, a: float, b: float, c: float, threshold: float = 30.0, queue_size: int = 10):
        self.a, self.b, self.c = float(a), float(b), float(c)
        self.threshold = threshold
        self.queue = deque(maxlen=queue_size)
        self.reset()

    def reset(self):
        self.max_value = 0.0
        self.up_flag = 0
        self.down_flag = 0
        self.state = 0
        self.active = False

    def compensate(self, x: float) -> float:
        if x > 0:
            return x
        self.queue.append(x)
        self.max_value = max(self.queue)
        if self.max_value - x > self.threshold:
            self.down_flag, self.up_flag = self.down_flag + 1, 0
        elif x - self.max_value > self.threshold:
            self.up_flag, self.down_flag = self.up_flag + 1, 0
        else:
            self.up_flag = self.down_flag = 0

        if self.down_flag >= 3:
            self.state, self.active = -1, False
        elif self.up_flag >= 3:
            self.state, self.active = 1, True

        if self.active and self.state == 1:
            xv = -x
            return x + (self.a * xv * xv + self.b * xv + self.c)
        return x


class VolterraCompensator:
    def __init__(self, cfg: Dict):
        self.vx_pos = np.asarray(cfg["shear"]["x_pos"], dtype=float)
        self.vx_neg = np.asarray(cfg["shear"]["x_neg"], dtype=float)
        self.vy_pos = np.asarray(cfg["shear"]["y_pos"], dtype=float)
        self.vy_neg = np.asarray(cfg["shear"]["y_neg"], dtype=float)
        self.vn = np.asarray(cfg["normal"], dtype=float)
        self.sign_eps = float(cfg.get("sign_eps", 1e-6))
        h = int(cfg.get("history_len", 128))
        self.hx_pos = deque(maxlen=h)
        self.hx_neg = deque(maxlen=h)
        self.hy_pos = deque(maxlen=h)
        self.hy_neg = deque(maxlen=h)
        self.hz = deque(maxlen=h)

    def reset(self):
        self.hx_pos.clear(); self.hx_neg.clear(); self.hy_pos.clear(); self.hy_neg.clear(); self.hz.clear()

    @staticmethod
    def _apply(hist: deque, kernel: np.ndarray, val: float) -> float:
        prev = list(hist)
        hist.append(float(val))
        if not prev:
            return float(val)
        arr = np.asarray(prev, dtype=float)[::-1]
        d = float(val) - arr
        k = min(len(kernel), len(d))
        return float(val + (np.dot(kernel[:k], d[:k]) if k else 0.0))

    def update(self, fx: float, fy: float, fz: float) -> Tuple[float, float, float]:
        fx_hat = self._apply(self.hx_pos if fx >= -self.sign_eps else self.hx_neg, self.vx_pos if fx >= -self.sign_eps else self.vx_neg, fx)
        fy_hat = self._apply(self.hy_pos if fy >= -self.sign_eps else self.hy_neg, self.vy_pos if fy >= -self.sign_eps else self.vy_neg, fy)
        fz_hat = self._apply(self.hz, self.vn, fz)
        return fx_hat, fy_hat, fz_hat
