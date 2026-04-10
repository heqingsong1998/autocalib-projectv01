from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np


@dataclass
class FrameDataset:
    x: np.ndarray  # [N, D]
    y: np.ndarray  # [N, 2]
    sample_ids: np.ndarray  # [N]
    source_files: List[Path]


def _ensure_2d(arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 1:
        return arr.reshape(1, -1)
    return arr


def _collect_npz_files(dataset_root: Path) -> List[Path]:
    if (dataset_root / "samples").is_dir():
        return sorted((dataset_root / "samples").glob("sample_*.npz"))
    return sorted(dataset_root.glob("**/samples/sample_*.npz"))


def load_frame_dataset(
    dataset_root: str,
    use_raw: bool = True,
    use_relative: bool = True,
    use_force: bool = True,
    use_pressure: bool = True,
    use_temp: bool = True,
) -> FrameDataset:
    root = Path(dataset_root)
    files = _collect_npz_files(root)
    if not files:
        raise FileNotFoundError(f"未找到样本文件: {root}")

    x_list: List[np.ndarray] = []
    y_list: List[np.ndarray] = []
    sid_list: List[np.ndarray] = []

    for file in files:
        with np.load(file, allow_pickle=False) as d:
            theta_cmd = np.asarray(d["theta_cmd"], dtype=np.float32).reshape(1, 2)

            blocks: List[np.ndarray] = []
            if use_raw and "raw" in d:
                blocks.append(_ensure_2d(np.asarray(d["raw"], dtype=np.float32)))
            if use_relative and "relative" in d:
                blocks.append(_ensure_2d(np.asarray(d["relative"], dtype=np.float32)))
            if use_force and "force" in d:
                blocks.append(_ensure_2d(np.asarray(d["force"], dtype=np.float32)))
            if use_pressure and "pressure" in d:
                blocks.append(_ensure_2d(np.asarray(d["pressure"], dtype=np.float32)))
            if use_temp and "temp" in d:
                blocks.append(_ensure_2d(np.asarray(d["temp"], dtype=np.float32)))

            if not blocks:
                raise ValueError(f"文件中未找到可用特征: {file}")

            n_frames = blocks[0].shape[0]
            for b in blocks[1:]:
                if b.shape[0] != n_frames:
                    raise ValueError(f"帧数不一致: {file}")

            x = np.concatenate(blocks, axis=1)
            y = np.repeat(theta_cmd, repeats=n_frames, axis=0)
            sid = np.asarray([file.stem] * n_frames)

            x_list.append(x)
            y_list.append(y)
            sid_list.append(sid)

    return FrameDataset(
        x=np.concatenate(x_list, axis=0),
        y=np.concatenate(y_list, axis=0),
        sample_ids=np.concatenate(sid_list, axis=0),
        source_files=files,
    )


def train_val_split(
    sample_ids: np.ndarray,
    val_ratio: float = 0.2,
    seed: int = 42,
    split_by_sample: bool = True,
) -> Tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    n = len(sample_ids)
    if n == 0:
        raise ValueError("空数据集")

    if split_by_sample:
        uniq = np.unique(sample_ids)
        rng.shuffle(uniq)
        n_val_u = max(1, int(len(uniq) * val_ratio))
        val_set = set(uniq[:n_val_u].tolist())
        val_mask = np.asarray([sid in val_set for sid in sample_ids])
    else:
        idx = np.arange(n)
        rng.shuffle(idx)
        n_val = max(1, int(n * val_ratio))
        val_mask = np.zeros(n, dtype=bool)
        val_mask[idx[:n_val]] = True

    train_mask = ~val_mask
    if not np.any(train_mask) or not np.any(val_mask):
        raise ValueError("训练/验证划分失败")
    return train_mask, val_mask
