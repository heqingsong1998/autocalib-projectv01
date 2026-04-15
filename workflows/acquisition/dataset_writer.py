from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import numpy as np


@dataclass
class SampleRecord:
    run_id: str
    sample_id: str
    theta0_cmd_deg: float
    theta1_cmd_deg: float
    frames: int
    sample_path: str
    start_ts: str
    end_ts: str


class ArrayDatasetWriter:
    """将阵列传感器采样结果保存为训练友好的结构。

    目录结构：
      root/
        manifest.csv
        manifest.jsonl
        run_meta.json
        samples/
          sample_000001.npz
          sample_000002.npz
    """

    def __init__(self, output_root: str, run_id: str, run_meta: Dict[str, Any]):
        self.output_root = Path(output_root)
        self.run_id = run_id
        self.samples_dir = self.output_root / "samples"
        self.samples_dir.mkdir(parents=True, exist_ok=True)

        self.manifest_csv_path = self.output_root / "manifest.csv"
        self.manifest_jsonl_path = self.output_root / "manifest.jsonl"
        self.run_meta_path = self.output_root / "run_meta.json"

        with open(self.run_meta_path, "w", encoding="utf-8") as f:
            json.dump(run_meta, f, ensure_ascii=False, indent=2)

        self._csv_f = open(self.manifest_csv_path, "w", newline="", encoding="utf-8")
        self._csv_writer = csv.writer(self._csv_f)
        self._csv_writer.writerow([
            "run_id",
            "sample_id",
            "theta0_cmd_deg",
            "theta1_cmd_deg",
            "frames",
            "sample_path",
            "start_ts",
            "end_ts",
        ])

        self._jsonl_f = open(self.manifest_jsonl_path, "w", encoding="utf-8")

    def close(self) -> None:
        try:
            self._csv_f.flush()
            self._csv_f.close()
        except Exception:
            pass
        try:
            self._jsonl_f.flush()
            self._jsonl_f.close()
        except Exception:
            pass

    def save_sample(
        self,
        sample_idx: int,
        theta0_cmd_deg: float,
        theta1_cmd_deg: float,
        frames: List[Dict[str, Any]],
    ) -> SampleRecord:
        if not frames:
            raise ValueError("frames 不能为空")

        sample_id = f"sample_{sample_idx:06d}"
        sample_file = self.samples_dir / f"{sample_id}.npz"

        timestamps = [str(f.get("timestamp", "")) for f in frames]
        raw = np.asarray([f.get("raw", [0.0] * 64) for f in frames], dtype=np.float32)
        relative = np.asarray([f.get("relative", [0.0] * 64) for f in frames], dtype=np.float32)

        force = np.asarray(
            [
                [
                    float(f.get("force", {}).get("fx", 0.0)),
                    float(f.get("force", {}).get("fy", 0.0)),
                    float(f.get("force", {}).get("fz", 0.0)),
                ]
                for f in frames
            ],
            dtype=np.float32,
        )
        pressure = np.asarray(
            [
                [
                    float(f.get("pressure", {}).get("fx", 0.0)),
                    float(f.get("pressure", {}).get("fy", 0.0)),
                    float(f.get("pressure", {}).get("fz", 0.0)),
                ]
                for f in frames
            ],
            dtype=np.float32,
        )

        temp = np.asarray(
            [
                [
                    float(f.get("temp1", 0.0)),
                    float(f.get("temp2", 0.0)),
                ]
                for f in frames
            ],
            dtype=np.float32,
        )

        np.savez_compressed(
            sample_file,
            theta_cmd=np.asarray([theta0_cmd_deg, theta1_cmd_deg], dtype=np.float32),
            timestamps=np.asarray(timestamps),
            raw=raw,
            relative=relative,
            force=force,
            pressure=pressure,
            temp=temp,
        )

        rec = SampleRecord(
            run_id=self.run_id,
            sample_id=sample_id,
            theta0_cmd_deg=float(theta0_cmd_deg),
            theta1_cmd_deg=float(theta1_cmd_deg),
            frames=int(len(frames)),
            sample_path=str(sample_file.relative_to(self.output_root)),
            start_ts=timestamps[0],
            end_ts=timestamps[-1],
        )

        self._csv_writer.writerow([
            rec.run_id,
            rec.sample_id,
            f"{rec.theta0_cmd_deg:.6f}",
            f"{rec.theta1_cmd_deg:.6f}",
            rec.frames,
            rec.sample_path,
            rec.start_ts,
            rec.end_ts,
        ])
        self._csv_f.flush()

        self._jsonl_f.write(json.dumps(rec.__dict__, ensure_ascii=False) + "\n")
        self._jsonl_f.flush()
        return rec


def make_run_id(prefix: str = "run") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def build_run_meta(config_snapshot: Dict[str, Any], ui_params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "config_snapshot": config_snapshot,
        "ui_params": ui_params,
    }
