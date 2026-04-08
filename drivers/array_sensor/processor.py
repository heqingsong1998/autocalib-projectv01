"""阵列触觉传感器数据处理。"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from .compensation import DynamicCompensator, HysteresisCompensator, VolterraCompensator


class ArraySensorProcessor:
    def __init__(self, config: Dict[str, Any]):
        self.cfg = config
        self.mapping = np.asarray(config["mapping"], dtype=int)
        self.zero_reference = np.zeros(64, dtype=float)
        self.baseline_temp1 = 0.0
        self.baseline_temp2 = 0.0

        dc = config["dynamic_compensation"]
        self.dc = {
            axis: DynamicCompensator(**dc[axis])
            for axis in ("x_pos", "x_neg", "y_pos", "y_neg", "z")
        }
        z_hys = config["hysteresis_compensation"]["z"]
        self.hys_z = HysteresisCompensator(**z_hys)
        self.volterra = VolterraCompensator(config["volterra"])

    def zero(self, raw: List[int], temp1: float, temp2: float) -> None:
        self.zero_reference = np.asarray(raw, dtype=float)
        self.baseline_temp1 = float(temp1)
        self.baseline_temp2 = float(temp2)
        self.volterra.reset()
        for item in self.dc.values():
            item.reset()
        self.hys_z.reset()

    def process(self, raw: List[int], temp1: float, temp2: float) -> Dict[str, Any]:
        relative = np.asarray(raw, dtype=float) - self.zero_reference
        fx, fy, fz_matrix = self._calculate_axes(relative)
        fz = float(np.sum(fz_matrix))

        sw = self.cfg["switches"]
        if sw.get("use_volterra", True):
            fx, fy, fz = self.volterra.update(fx, fy, fz)

        if sw.get("use_temperature_compensation", False):
            dt1 = temp1 - self.baseline_temp1
            tc = self.cfg["temperature_compensation"]
            fz += dt1 * tc["z"]
            fx += dt1 * tc["x"]
            fy += dt1 * tc["y"]

        if sw.get("use_dynamic_compensation", True):
            fz = self.dc["z"].update(fz)
            fx = self.dc["x_pos"].update(fx) if fx >= 0 else self.dc["x_neg"].update(fx)
            fy = self.dc["y_pos"].update(fy) if fy >= 0 else self.dc["y_neg"].update(fy)

        if sw.get("use_hysteresis_compensation", True):
            fz = self.hys_z.compensate(fz)

        if sw.get("use_calibration", True):
            fz_v = self._poly(fz, self.cfg["calibration"]["z"]) / 100.0
            fx_v = self._poly(fx, self.cfg["calibration"]["x_pos" if fx >= 0 else "x_neg"]) / 100.0
            fy_v = self._poly(fy, self.cfg["calibration"]["y_pos" if fy >= 0 else "y_neg"]) / 100.0
        else:
            fz_v, fx_v, fy_v = fz, fx, fy

        pressure_scale = float(self.cfg.get("pressure_scale", 10.0))
        return {
            "relative": relative.tolist(),
            "raw_force": {"fx": fx, "fy": fy, "fz": fz},
            "force": {"fx": fx_v, "fy": fy_v, "fz": fz_v},
            "pressure": {"fx": fx_v * pressure_scale, "fy": fy_v * pressure_scale, "fz": fz_v * pressure_scale},
            "temp": {"t1": temp1, "t2": temp2, "dt1": temp1 - self.baseline_temp1, "dt2": temp2 - self.baseline_temp2},
        }

    def _calculate_axes(self, relative: np.ndarray):
        c = relative[self.mapping]
        fx_temp = np.array([c[0, :] - c[1, :], c[2, :] - c[3, :], c[4, :] - c[5, :], c[6, :] - c[7, :]])
        fy_temp = np.array([c[:, 0] - c[:, 1], c[:, 2] - c[:, 3], c[:, 4] - c[:, 5], c[:, 6] - c[:, 7]])
        return float(np.sum(fx_temp)), float(np.sum(fy_temp)), c

    @staticmethod
    def _poly(x: float, cfg: Dict[str, float]) -> float:
        return cfg["a"] * x * x + cfg["b"] * x + cfg.get("c", 0.0)
