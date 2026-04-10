from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

from .single_frame_dataset import load_frame_dataset, train_val_split


@dataclass
class MLPParams:
    w1: np.ndarray
    b1: np.ndarray
    w2: np.ndarray
    b2: np.ndarray


def init_params(in_dim: int, hidden_dim: int, out_dim: int, seed: int) -> MLPParams:
    rng = np.random.default_rng(seed)
    k1 = np.sqrt(2.0 / in_dim)
    k2 = np.sqrt(2.0 / hidden_dim)
    return MLPParams(
        w1=(rng.standard_normal((in_dim, hidden_dim), dtype=np.float32) * k1).astype(np.float32),
        b1=np.zeros((1, hidden_dim), dtype=np.float32),
        w2=(rng.standard_normal((hidden_dim, out_dim), dtype=np.float32) * k2).astype(np.float32),
        b2=np.zeros((1, out_dim), dtype=np.float32),
    )


def relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(x, 0.0)


def forward(params: MLPParams, x: np.ndarray) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    z1 = x @ params.w1 + params.b1
    a1 = relu(z1)
    y = a1 @ params.w2 + params.b2
    cache = {"x": x, "z1": z1, "a1": a1}
    return y, cache


def compute_loss(y_pred: np.ndarray, y_true: np.ndarray) -> float:
    return float(np.mean((y_pred - y_true) ** 2))


def backward(params: MLPParams, cache: Dict[str, np.ndarray], y_pred: np.ndarray, y_true: np.ndarray) -> MLPParams:
    n = y_true.shape[0]
    dy = (2.0 / n) * (y_pred - y_true)

    dw2 = cache["a1"].T @ dy
    db2 = np.sum(dy, axis=0, keepdims=True)

    da1 = dy @ params.w2.T
    dz1 = da1 * (cache["z1"] > 0).astype(np.float32)

    dw1 = cache["x"].T @ dz1
    db1 = np.sum(dz1, axis=0, keepdims=True)

    return MLPParams(w1=dw1, b1=db1, w2=dw2, b2=db2)


def update(params: MLPParams, grads: MLPParams, lr: float) -> None:
    params.w1 -= lr * grads.w1
    params.b1 -= lr * grads.b1
    params.w2 -= lr * grads.w2
    params.b2 -= lr * grads.b2


def mae_deg(y_pred: np.ndarray, y_true: np.ndarray) -> Tuple[float, float, float]:
    err = np.abs(y_pred - y_true)
    return float(np.mean(err[:, 0])), float(np.mean(err[:, 1])), float(np.mean(err))


def run_train(args: argparse.Namespace) -> None:
    data = load_frame_dataset(
        dataset_root=args.dataset_root,
        use_raw=args.use_raw,
        use_relative=args.use_relative,
        use_force=args.use_force,
        use_pressure=args.use_pressure,
        use_temp=args.use_temp,
    )

    train_mask, val_mask = train_val_split(
        sample_ids=data.sample_ids,
        val_ratio=args.val_ratio,
        seed=args.seed,
        split_by_sample=args.split_by_sample,
    )

    x_train, y_train = data.x[train_mask], data.y[train_mask]
    x_val, y_val = data.x[val_mask], data.y[val_mask]

    x_mean = x_train.mean(axis=0, keepdims=True)
    x_std = x_train.std(axis=0, keepdims=True)
    x_std = np.where(x_std < 1e-6, 1.0, x_std)

    y_mean = y_train.mean(axis=0, keepdims=True)
    y_std = y_train.std(axis=0, keepdims=True)
    y_std = np.where(y_std < 1e-6, 1.0, y_std)

    x_train_n = (x_train - x_mean) / x_std
    x_val_n = (x_val - x_mean) / x_std
    y_train_n = (y_train - y_mean) / y_std

    params = init_params(x_train_n.shape[1], args.hidden_dim, 2, args.seed)

    rng = np.random.default_rng(args.seed)
    n_train = x_train_n.shape[0]

    for epoch in range(1, args.epochs + 1):
        idx = np.arange(n_train)
        rng.shuffle(idx)

        for s in range(0, n_train, args.batch_size):
            b = idx[s:s + args.batch_size]
            xb = x_train_n[b]
            yb = y_train_n[b]

            y_pred, cache = forward(params, xb)
            grads = backward(params, cache, y_pred, yb)
            update(params, grads, args.lr)

        if epoch % args.log_every == 0 or epoch == 1 or epoch == args.epochs:
            train_pred_n, _ = forward(params, x_train_n)
            val_pred_n, _ = forward(params, x_val_n)
            train_loss = compute_loss(train_pred_n, y_train_n)
            val_loss = compute_loss(val_pred_n, (y_val - y_mean) / y_std)
            val_pred = val_pred_n * y_std + y_mean
            m0, m1, mall = mae_deg(val_pred, y_val)
            print(
                f"[Epoch {epoch:04d}] train_loss={train_loss:.6f} "
                f"val_loss={val_loss:.6f} val_mae(theta0/theta1/all)={m0:.4f}/{m1:.4f}/{mall:.4f} deg"
            )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model_npz = output_dir / "single_frame_mlp_model.npz"
    meta_json = output_dir / "single_frame_mlp_meta.json"

    np.savez(
        model_npz,
        w1=params.w1,
        b1=params.b1,
        w2=params.w2,
        b2=params.b2,
        x_mean=x_mean,
        x_std=x_std,
        y_mean=y_mean,
        y_std=y_std,
    )

    meta = {
        "dataset_root": str(Path(args.dataset_root).resolve()),
        "n_total_frames": int(data.x.shape[0]),
        "n_train_frames": int(x_train.shape[0]),
        "n_val_frames": int(x_val.shape[0]),
        "n_source_samples": int(len(data.source_files)),
        "input_dim": int(data.x.shape[1]),
        "hidden_dim": int(args.hidden_dim),
        "feature_flags": {
            "use_raw": args.use_raw,
            "use_relative": args.use_relative,
            "use_force": args.use_force,
            "use_pressure": args.use_pressure,
            "use_temp": args.use_temp,
        },
        "split_by_sample": bool(args.split_by_sample),
    }
    meta_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"训练完成，模型已保存: {model_npz}")
    print(f"元数据已保存: {meta_json}")


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="单帧展开训练：2层MLP回归(theta0, theta1)")
    p.add_argument("--dataset-root", required=True, help="数据集根目录（可为 datasets 或单个 run 目录）")
    p.add_argument("--output-dir", default="workflows/training/artifacts", help="模型输出目录")

    p.add_argument("--epochs", type=int, default=300)
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--hidden-dim", type=int, default=128)
    p.add_argument("--val-ratio", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--log-every", type=int, default=20)

    p.add_argument("--split-by-sample", action="store_true", default=True,
                   help="按 sample_id 划分训练/验证，避免同一sample帧泄漏（默认开启）")
    p.add_argument("--split-by-frame", dest="split_by_sample", action="store_false",
                   help="直接按帧随机划分（不推荐，仅用于快速试验）")

    p.add_argument("--use-raw", action="store_true", default=True)
    p.add_argument("--no-raw", dest="use_raw", action="store_false")
    p.add_argument("--use-relative", action="store_true", default=True)
    p.add_argument("--no-relative", dest="use_relative", action="store_false")
    p.add_argument("--use-force", action="store_true", default=True)
    p.add_argument("--no-force", dest="use_force", action="store_false")
    p.add_argument("--use-pressure", action="store_true", default=True)
    p.add_argument("--no-pressure", dest="use_pressure", action="store_false")
    p.add_argument("--use-temp", action="store_true", default=True)
    p.add_argument("--no-temp", dest="use_temp", action="store_false")
    return p


def main() -> None:
    parser = build_argparser()
    args = parser.parse_args()
    run_train(args)


if __name__ == "__main__":
    main()
