from __future__ import annotations

import argparse
from typing import Dict

import numpy as np


class SingleFrameMLP:
    def __init__(self, model_path: str):
        m = np.load(model_path, allow_pickle=False)
        self.w1 = np.asarray(m["w1"], dtype=np.float32)
        self.b1 = np.asarray(m["b1"], dtype=np.float32)
        self.w2 = np.asarray(m["w2"], dtype=np.float32)
        self.b2 = np.asarray(m["b2"], dtype=np.float32)
        self.x_mean = np.asarray(m["x_mean"], dtype=np.float32)
        self.x_std = np.asarray(m["x_std"], dtype=np.float32)
        self.y_mean = np.asarray(m["y_mean"], dtype=np.float32)
        self.y_std = np.asarray(m["y_std"], dtype=np.float32)

    def _forward(self, x: np.ndarray) -> np.ndarray:
        z1 = x @ self.w1 + self.b1
        a1 = np.maximum(z1, 0.0)
        y = a1 @ self.w2 + self.b2
        return y

    def predict(self, frame_feature: np.ndarray) -> np.ndarray:
        x = np.asarray(frame_feature, dtype=np.float32).reshape(1, -1)
        x_n = (x - self.x_mean) / self.x_std
        y_n = self._forward(x_n)
        y = y_n * self.y_std + self.y_mean
        return y[0]


def build_feature_from_frame(
    frame: Dict,
    use_raw: bool = True,
    use_relative: bool = True,
    use_force: bool = True,
    use_pressure: bool = True,
    use_temp: bool = True,
) -> np.ndarray:
    blocks = []
    if use_raw:
        blocks.append(np.asarray(frame.get("raw", [0.0] * 64), dtype=np.float32).reshape(-1))
    if use_relative:
        blocks.append(np.asarray(frame.get("relative", [0.0] * 64), dtype=np.float32).reshape(-1))
    if use_force:
        f = frame.get("force", {}) or {}
        blocks.append(np.asarray([f.get("fx", 0.0), f.get("fy", 0.0), f.get("fz", 0.0)], dtype=np.float32))
    if use_pressure:
        p = frame.get("pressure", {}) or {}
        blocks.append(np.asarray([p.get("fx", 0.0), p.get("fy", 0.0), p.get("fz", 0.0)], dtype=np.float32))
    if use_temp:
        blocks.append(np.asarray([frame.get("temp1", 0.0), frame.get("temp2", 0.0)], dtype=np.float32))

    if not blocks:
        raise ValueError("至少开启一个特征源")
    return np.concatenate(blocks, axis=0)


def demo_predict_on_npz(model_path: str, sample_npz: str, frame_index: int = 0) -> None:
    model = SingleFrameMLP(model_path)
    with np.load(sample_npz, allow_pickle=False) as d:
        frame = {
            "raw": d["raw"][frame_index],
            "relative": d["relative"][frame_index],
            "force": {"fx": d["force"][frame_index][0], "fy": d["force"][frame_index][1], "fz": d["force"][frame_index][2]},
            "pressure": {
                "fx": d["pressure"][frame_index][0],
                "fy": d["pressure"][frame_index][1],
                "fz": d["pressure"][frame_index][2],
            },
            "temp1": d["temp"][frame_index][0],
            "temp2": d["temp"][frame_index][1],
        }
        feat = build_feature_from_frame(frame)
        pred = model.predict(feat)
        label = np.asarray(d["theta_cmd"], dtype=np.float32)

    print(f"预测角度: theta0={pred[0]:.4f}°, theta1={pred[1]:.4f}°")
    print(f"样本标签: theta0={label[0]:.4f}°, theta1={label[1]:.4f}°")


def main() -> None:
    parser = argparse.ArgumentParser(description="单帧MLP推理/快速验证")
    parser.add_argument("--model", required=True, help="single_frame_mlp_model.npz 路径")
    parser.add_argument("--sample-npz", help="可选：用于快速验证的 sample_xxxxxx.npz")
    parser.add_argument("--frame-index", type=int, default=0)
    args = parser.parse_args()

    if args.sample_npz:
        demo_predict_on_npz(args.model, args.sample_npz, args.frame_index)
    else:
        print("已加载模型，可在代码中使用 SingleFrameMLP.predict(...) 做在线推理。")


if __name__ == "__main__":
    main()
