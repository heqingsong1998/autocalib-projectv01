# -*- coding: utf-8 -*-
import numpy as np
from collections import deque
from typing import Tuple, Iterable, Union, Dict, Any

class VolterraCompensator:
    def __init__(
        self,
        volterra_shear: Union[Iterable[float], Dict[str, Iterable[float]]],
        volterra_normal: Iterable[float],
        history_len: int = 501,
        sign_eps: float = 0.0,
    ) -> None:
        if history_len < 2:
            raise ValueError("history_len 必须 ≥ 2")
        self.H = int(history_len)
        self.sign_eps = float(sign_eps)

        def _to_vec(x: Any) -> np.ndarray:
            return np.asarray(list(x), dtype=float).reshape(-1)

        if isinstance(volterra_shear, dict):
            all_vec = _to_vec(volterra_shear["all"]) if "all" in volterra_shear else None
            pos_vec = _to_vec(volterra_shear["pos"]) if "pos" in volterra_shear else None
            neg_vec = _to_vec(volterra_shear["neg"]) if "neg" in volterra_shear else None

            self.vx_pos = _to_vec(volterra_shear.get("x_pos", pos_vec if pos_vec is not None else (all_vec if all_vec is not None else [])))
            self.vx_neg = _to_vec(volterra_shear.get("x_neg", neg_vec if neg_vec is not None else (all_vec if all_vec is not None else [])))
            self.vy_pos = _to_vec(volterra_shear.get("y_pos", pos_vec if pos_vec is not None else (all_vec if all_vec is not None else [])))
            self.vy_neg = _to_vec(volterra_shear.get("y_neg", neg_vec if neg_vec is not None else (all_vec if all_vec is not None else [])))

            if min(self.vx_pos.size, self.vx_neg.size, self.vy_pos.size, self.vy_neg.size) == 0:
                raise ValueError("volterra_shear 缺核：请提供 x_pos/x_neg/y_pos/y_neg 或使用 'pos'/'neg'/'all'")
        else:
            base = _to_vec(volterra_shear)
            self.vx_pos = self.vx_neg = self.vy_pos = self.vy_neg = base

        self.vn = _to_vec(volterra_normal)

        self.hx_pos = deque(maxlen=self.H)
        self.hx_neg = deque(maxlen=self.H)
        self.hy_pos = deque(maxlen=self.H)
        self.hy_neg = deque(maxlen=self.H)
        self.hz     = deque(maxlen=self.H)

    def reset(self) -> None:
        self.hx_pos.clear(); self.hx_neg.clear()
        self.hy_pos.clear(); self.hy_neg.clear()
        self.hz.clear()

    @staticmethod
    def _apply_axis(hist: deque, kernel: np.ndarray, val: float) -> float:
        prev = list(hist)
        hist.append(float(val))
        if not prev:
            return float(val)
        prev_arr = np.asarray(prev, dtype=float)[::-1]
        delta = float(val) - prev_arr
        k = min(kernel.size, delta.size)
        return float(val + (np.dot(kernel[:k], delta[:k]) if k > 0 else 0.0))

    def _is_pos(self, v: float) -> bool:
        return v >= -self.sign_eps  # |v|≤eps 归正向，避免0附近抖动

    def update(self, Fx: float, Fy: float, Fz: float) -> Tuple[float, float, float]:
        Fx_hat = self._apply_axis(self.hx_pos, self.vx_pos, Fx) if self._is_pos(Fx) \
                 else self._apply_axis(self.hx_neg, self.vx_neg, Fx)
        Fy_hat = self._apply_axis(self.hy_pos, self.vy_pos, Fy) if self._is_pos(Fy) \
                 else self._apply_axis(self.hy_neg, self.vy_neg, Fy)
        Fz_hat = self._apply_axis(self.hz, self.vn, Fz)
        return Fx_hat, Fy_hat, Fz_hat
