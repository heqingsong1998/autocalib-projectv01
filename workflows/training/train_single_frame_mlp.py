from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

try:
    from .single_frame_dataset import load_frame_dataset, train_val_split
except ImportError:
    # 兼容直接以脚本方式运行: python workflows/training/train_single_frame_mlp.py
    from single_frame_dataset import load_frame_dataset, train_val_split

DEFAULT_DATASET_ROOT = "datasets\collect_20260414_095702"


@dataclass
class MLPParams:
    w1: np.ndarray
    b1: np.ndarray
    w2: np.ndarray
    b2: np.ndarray
    w_skip: np.ndarray
    b_skip: np.ndarray
    w3: np.ndarray
    b3: np.ndarray


@dataclass
class AdamState:
    m: MLPParams
    v: MLPParams
    t: int


def init_params(in_dim: int, hidden_dim1: int, hidden_dim2: int, out_dim: int, seed: int) -> MLPParams:
    rng = np.random.default_rng(seed)
    k1 = np.sqrt(2.0 / in_dim)
    k2 = np.sqrt(2.0 / hidden_dim1)
    k3 = np.sqrt(2.0 / hidden_dim2)
    ks = np.sqrt(2.0 / in_dim)
    return MLPParams(
        w1=(rng.standard_normal((in_dim, hidden_dim1), dtype=np.float32) * k1).astype(np.float32),
        b1=np.zeros((1, hidden_dim1), dtype=np.float32),
        w2=(rng.standard_normal((hidden_dim1, hidden_dim2), dtype=np.float32) * k2).astype(np.float32),
        b2=np.zeros((1, hidden_dim2), dtype=np.float32),
        w_skip=(rng.standard_normal((in_dim, hidden_dim2), dtype=np.float32) * ks).astype(np.float32),
        b_skip=np.zeros((1, hidden_dim2), dtype=np.float32),
        w3=(rng.standard_normal((hidden_dim2, out_dim), dtype=np.float32) * k3).astype(np.float32),
        b3=np.zeros((1, out_dim), dtype=np.float32),
    )


def zeros_like_params(params: MLPParams) -> MLPParams:
    return MLPParams(
        w1=np.zeros_like(params.w1),
        b1=np.zeros_like(params.b1),
        w2=np.zeros_like(params.w2),
        b2=np.zeros_like(params.b2),
        w_skip=np.zeros_like(params.w_skip),
        b_skip=np.zeros_like(params.b_skip),
        w3=np.zeros_like(params.w3),
        b3=np.zeros_like(params.b3),
    )


def copy_params(params: MLPParams) -> MLPParams:
    return MLPParams(
        w1=params.w1.copy(),
        b1=params.b1.copy(),
        w2=params.w2.copy(),
        b2=params.b2.copy(),
        w_skip=params.w_skip.copy(),
        b_skip=params.b_skip.copy(),
        w3=params.w3.copy(),
        b3=params.b3.copy(),
    )


def relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(x, 0.0)


def forward(params: MLPParams, x: np.ndarray) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    z1 = x @ params.w1 + params.b1
    a1 = relu(z1)
    z2 = a1 @ params.w2 + params.b2 + x @ params.w_skip + params.b_skip
    a2 = relu(z2)
    y = a2 @ params.w3 + params.b3
    cache = {"x": x, "z1": z1, "a1": a1, "z2": z2, "a2": a2}
    return y, cache


def compute_huber_loss_and_grad(y_pred: np.ndarray, y_true: np.ndarray, delta: float) -> Tuple[float, np.ndarray]:
    err = y_pred - y_true
    abs_err = np.abs(err)
    quad = abs_err <= delta
    loss = np.where(quad, 0.5 * err * err, delta * (abs_err - 0.5 * delta))
    grad = np.where(quad, err, delta * np.sign(err)).astype(np.float32)
    n = y_true.shape[0]
    grad = grad / float(n)
    return float(np.mean(loss)), grad


def compute_huber_loss(y_pred: np.ndarray, y_true: np.ndarray, delta: float) -> float:
    err = y_pred - y_true
    abs_err = np.abs(err)
    quad = abs_err <= delta
    loss = np.where(quad, 0.5 * err * err, delta * (abs_err - 0.5 * delta))
    return float(np.mean(loss))


def backward(params: MLPParams, cache: Dict[str, np.ndarray], dy: np.ndarray) -> MLPParams:
    dw3 = cache["a2"].T @ dy
    db3 = np.sum(dy, axis=0, keepdims=True)

    da2 = dy @ params.w3.T
    dz2 = da2 * (cache["z2"] > 0).astype(np.float32)

    dw2 = cache["a1"].T @ dz2
    db2 = np.sum(dz2, axis=0, keepdims=True)

    dw_skip = cache["x"].T @ dz2
    db_skip = np.sum(dz2, axis=0, keepdims=True)

    da1 = dz2 @ params.w2.T
    dz1 = da1 * (cache["z1"] > 0).astype(np.float32)

    dw1 = cache["x"].T @ dz1
    db1 = np.sum(dz1, axis=0, keepdims=True)

    return MLPParams(
        w1=dw1,
        b1=db1,
        w2=dw2,
        b2=db2,
        w_skip=dw_skip,
        b_skip=db_skip,
        w3=dw3,
        b3=db3,
    )


def init_adam_state(params: MLPParams) -> AdamState:
    return AdamState(m=zeros_like_params(params), v=zeros_like_params(params), t=0)


def _adam_step_one(p: np.ndarray, g: np.ndarray, m: np.ndarray, v: np.ndarray, t: int,
                   lr: float, beta1: float, beta2: float, eps: float, weight_decay: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    if weight_decay > 0.0:
        g = g + weight_decay * p
    m = beta1 * m + (1.0 - beta1) * g
    v = beta2 * v + (1.0 - beta2) * (g * g)
    m_hat = m / (1.0 - (beta1 ** t))
    v_hat = v / (1.0 - (beta2 ** t))
    p = p - lr * m_hat / (np.sqrt(v_hat) + eps)
    return p, m, v


def adam_update(
    params: MLPParams,
    grads: MLPParams,
    state: AdamState,
    lr: float,
    beta1: float,
    beta2: float,
    eps: float,
    weight_decay: float,
) -> None:
    state.t += 1
    t = state.t

    params.w1, state.m.w1, state.v.w1 = _adam_step_one(params.w1, grads.w1, state.m.w1, state.v.w1, t, lr, beta1, beta2, eps, weight_decay)
    params.b1, state.m.b1, state.v.b1 = _adam_step_one(params.b1, grads.b1, state.m.b1, state.v.b1, t, lr, beta1, beta2, eps, 0.0)
    params.w2, state.m.w2, state.v.w2 = _adam_step_one(params.w2, grads.w2, state.m.w2, state.v.w2, t, lr, beta1, beta2, eps, weight_decay)
    params.b2, state.m.b2, state.v.b2 = _adam_step_one(params.b2, grads.b2, state.m.b2, state.v.b2, t, lr, beta1, beta2, eps, 0.0)
    params.w_skip, state.m.w_skip, state.v.w_skip = _adam_step_one(params.w_skip, grads.w_skip, state.m.w_skip, state.v.w_skip, t, lr, beta1, beta2, eps, weight_decay)
    params.b_skip, state.m.b_skip, state.v.b_skip = _adam_step_one(params.b_skip, grads.b_skip, state.m.b_skip, state.v.b_skip, t, lr, beta1, beta2, eps, 0.0)
    params.w3, state.m.w3, state.v.w3 = _adam_step_one(params.w3, grads.w3, state.m.w3, state.v.w3, t, lr, beta1, beta2, eps, weight_decay)
    params.b3, state.m.b3, state.v.b3 = _adam_step_one(params.b3, grads.b3, state.m.b3, state.v.b3, t, lr, beta1, beta2, eps, 0.0)


def mae_deg(y_pred: np.ndarray, y_true: np.ndarray) -> Tuple[float, float, float]:
    err = np.abs(y_pred - y_true)
    return float(np.mean(err[:, 0])), float(np.mean(err[:, 1])), float(np.mean(err))


def train_epochs(
    params: MLPParams,
    x_train_n: np.ndarray,
    y_train_n: np.ndarray,
    x_val_n: np.ndarray,
    y_val_n: np.ndarray,
    y_mean: np.ndarray,
    y_std: np.ndarray,
    epochs: int,
    batch_size: int,
    lr: float,
    beta1: float,
    beta2: float,
    eps: float,
    weight_decay: float,
    huber_delta: float,
    early_stop_patience: int,
    log_every: int,
    seed: int,
    stage_name: str,
) -> MLPParams:
    rng = np.random.default_rng(seed)
    n_train = x_train_n.shape[0]
    state = init_adam_state(params)
    best_params = copy_params(params)
    best_val_loss = float("inf")
    bad_epochs = 0

    for epoch in range(1, epochs + 1):
        idx = np.arange(n_train)
        rng.shuffle(idx)

        for s in range(0, n_train, batch_size):
            b = idx[s:s + batch_size]
            xb = x_train_n[b]
            yb = y_train_n[b]

            y_pred, cache = forward(params, xb)
            _, dy = compute_huber_loss_and_grad(y_pred, yb, huber_delta)
            grads = backward(params, cache, dy)
            adam_update(params, grads, state, lr, beta1, beta2, eps, weight_decay)

        if epoch % log_every == 0 or epoch == 1 or epoch == epochs:
            train_pred_n, _ = forward(params, x_train_n)
            val_pred_n, _ = forward(params, x_val_n)
            train_loss = compute_huber_loss(train_pred_n, y_train_n, huber_delta)
            val_loss = compute_huber_loss(val_pred_n, y_val_n, huber_delta)
            val_pred = val_pred_n * y_std + y_mean
            val_true = y_val_n * y_std + y_mean
            m0, m1, mall = mae_deg(val_pred, val_true)
            print(
                f"[{stage_name} Epoch {epoch:04d}] train_loss={train_loss:.6f} "
                f"val_loss={val_loss:.6f} val_mae(theta0/theta1/all)={m0:.4f}/{m1:.4f}/{mall:.4f} deg"
            )

        val_pred_n, _ = forward(params, x_val_n)
        val_loss = compute_huber_loss(val_pred_n, y_val_n, huber_delta)
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_params = copy_params(params)
            bad_epochs = 0
        else:
            bad_epochs += 1
            if bad_epochs >= early_stop_patience:
                print(f"[{stage_name}] Early stopping at epoch={epoch}, best_val_loss={best_val_loss:.6f}")
                break

    return best_params


def run_train(args: argparse.Namespace) -> None:
    # 按需求：训练仅使用 64 通道 raw 特征。
    data = load_frame_dataset(
        dataset_root=args.dataset_root,
        use_raw=True,
        use_relative=False,
        use_force=False,
        use_pressure=False,
        use_temp=False,
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

    y_val_n = (y_val - y_mean) / y_std

    params = init_params(
        in_dim=x_train_n.shape[1],
        hidden_dim1=args.hidden_dim1,
        hidden_dim2=args.hidden_dim2,
        out_dim=2,
        seed=args.seed,
    )
    best_params = train_epochs(
        params=params,
        x_train_n=x_train_n,
        y_train_n=y_train_n,
        x_val_n=x_val_n,
        y_val_n=y_val_n,
        y_mean=y_mean,
        y_std=y_std,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        beta1=args.adam_beta1,
        beta2=args.adam_beta2,
        eps=args.adam_eps,
        weight_decay=args.weight_decay,
        huber_delta=args.huber_delta,
        early_stop_patience=args.early_stop_patience,
        log_every=args.log_every,
        seed=args.seed,
        stage_name="resmlp",
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model_npz = output_dir / "single_frame_mlp_model.npz"
    meta_json = output_dir / "single_frame_mlp_meta.json"

    np.savez(
        model_npz,
        model_type="residual_mlp_v1",
        w1=best_params.w1,
        b1=best_params.b1,
        w2=best_params.w2,
        b2=best_params.b2,
        w_skip=best_params.w_skip,
        b_skip=best_params.b_skip,
        w3=best_params.w3,
        b3=best_params.b3,
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
        "model_type": "residual_mlp_v1",
        "hidden_dim1": int(args.hidden_dim1),
        "hidden_dim2": int(args.hidden_dim2),
        "epochs": int(args.epochs),
        "huber_delta": float(args.huber_delta),
        "weight_decay": float(args.weight_decay),
        "early_stop_patience": int(args.early_stop_patience),
        "feature_flags": {
            "use_raw": True,
            "use_relative": False,
            "use_force": False,
            "use_pressure": False,
            "use_temp": False,
        },
        "split_by_sample": bool(args.split_by_sample),
    }
    meta_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"训练完成，模型已保存: {model_npz}")
    print(f"元数据已保存: {meta_json}")


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="单帧残差MLP训练（输入/输出维度不变）")
    p.add_argument(
        "--dataset-root",
        default=DEFAULT_DATASET_ROOT,
        help="数据集根目录（可为 datasets 或单个 run 目录），默认使用当前采集目录",
    )
    p.add_argument("--output-dir", default="workflows/training/artifacts", help="模型输出目录")

    p.add_argument("--epochs", type=int, default=500)
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--hidden-dim1", type=int, default=256)
    p.add_argument("--hidden-dim2", type=int, default=256)
    p.add_argument("--huber-delta", type=float, default=1.0)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--adam-beta1", type=float, default=0.9)
    p.add_argument("--adam-beta2", type=float, default=0.999)
    p.add_argument("--adam-eps", type=float, default=1e-8)
    p.add_argument("--early-stop-patience", type=int, default=50)
    p.add_argument("--val-ratio", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--log-every", type=int, default=20)

    p.add_argument("--split-by-sample", action="store_true", default=True,
                   help="按 sample_id 划分训练/验证，避免同一sample帧泄漏（默认开启）")
    p.add_argument("--split-by-frame", dest="split_by_sample", action="store_false",
                   help="直接按帧随机划分（不推荐，仅用于快速试验）")

    return p


def main() -> None:
    parser = build_argparser()
    args = parser.parse_args()
    run_train(args)


if __name__ == "__main__":
    main()
