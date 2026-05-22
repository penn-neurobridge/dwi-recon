"""Whole-brain fiber tracking via DSI Studio.

Supports both single-pass tracking (.tt.gz) and iterative tracking
with per-point diffusion metric export (whole_brain_trk.h5,
whole_brain_trksubVox.h5).
"""

from pathlib import Path

import numpy as np

from dwi_preprocessing.config import Config
from dwi_preprocessing.utils.dsi import run_dsi
from dwi_preprocessing.utils.io import load_mat, save_h5


def fiber_tracking(
    cfg: Config,
    fib: Path,
    n_streamlines: int = 2_500_000,
) -> Path:
    """Run whole-brain fiber tracking (single pass, .tt.gz output).

    Returns
    -------
    Path to the .tt.gz file.
    """
    trk_gz = Path(f"{fib}.tt.gz")

    if trk_gz.is_file():
        print("  Fiber tracking (.tt.gz) already complete — skipping")
        return trk_gz

    run_dsi(cfg, [
        "--action=trk",
        f"--source={fib}",
        f"--tract_count={n_streamlines}",
        "--method=1",
        "--trim=1",
        "--min_length=30",
        "--max_length=300",
        "--step_size=1",
        f"--output={trk_gz}",
    ])

    return trk_gz


def fiber_tracking_ittr(
    cfg: Config,
    fib: Path,
    output_dir: Path,
    n_streamlines: int = 2_500_000,
    save_trksubvox: bool = False,
) -> dict[str, Path]:
    """Run fiber tracking in 10 iterations with per-point metric export.

    Produces:
      - whole_brain_trk.h5 — tract coordinates + per-tract mean metrics
      - whole_brain_trksubVox.h5 — per-point QA, FA, MD, AD, RD

    Parameters
    ----------
    cfg : Config
        Pipeline configuration.
    fib : Path
        GQI fib (.fz) file.
    output_dir : Path
        DSI Studio output directory.
    n_streamlines : int
        Total number of streamlines (split across 10 iterations).
    save_trksubvox : bool
        Whether to save per-point metrics.

    Returns
    -------
    dict with keys: trk, trksubvox (if save_trksubvox)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / "whole_brain"

    trk_file = Path(f"{prefix}_trk.h5")
    subvox_file = Path(f"{prefix}_trksubVox.h5")

    trk_exists = trk_file.is_file()
    subvox_exists = subvox_file.is_file()
    need_tracking = (not trk_exists) or (save_trksubvox and not subvox_exists)

    if not need_tracking:
        print("  whole_brain_trk.h5 and trksubVox.h5 already exist — skipping")
        result = {"trk": trk_file}
        if save_trksubvox:
            result["trksubvox"] = subvox_file
        return result

    if trk_exists and save_trksubvox and not subvox_exists:
        print("  trk.h5 exists but trksubVox.h5 missing — re-running tracking")

    # Run 10 iterations
    per_iter = n_streamlines // 10
    for ittr in range(1, 11):
        out_mat = Path(f"{prefix}_ittr{ittr}.mat")
        run_dsi(cfg, [
            "--action=trk",
            f"--source={fib}",
            f"--tract_count={per_iter}",
            "--method=1",
            "--trim=1",
            "--min_length=30",
            "--max_length=300",
            "--thread_count=16",
            "--step_size=1",
            "--export=qa.mat,fa.mat,md.mat,ad.mat,rd.mat",
            f"--output={out_mat}",
        ])

    # Concatenate all iterations
    trk_data = _concatenate_iterations(prefix)
    _save_trk_h5(trk_file, trk_data)

    result = {"trk": trk_file}

    if save_trksubvox:
        print("  Saving trksubVox.h5")
        _save_subvox_h5(subvox_file, trk_data)
        result["trksubvox"] = subvox_file

    # Cleanup iteration files
    for ittr_file in output_dir.glob("whole_brain_ittr*"):
        ittr_file.unlink()

    return result


# ── Private helpers ───────────────────────────────────────────────────

def _concatenate_iterations(prefix: Path) -> dict:
    """Load and concatenate 10 iteration files into arrays."""
    all_cord, all_len = [], []
    all_qa, all_fa, all_md, all_ad, all_rd = [], [], [], [], []

    for ittr in range(1, 11):
        base = Path(f"{prefix}_ittr{ittr}.mat")
        d = load_mat(base)
        all_cord.append(d["tracts"].astype(np.float32))
        all_len.append(d["length"].astype(np.float32).ravel())

        all_qa.append(load_mat(Path(f"{base}.qa.mat"), "data").astype(np.float32).ravel())
        all_fa.append(load_mat(Path(f"{base}.fa.mat"), "data").astype(np.float32).ravel())
        all_md.append(load_mat(Path(f"{base}.md.mat"), "data").astype(np.float32).ravel())
        all_ad.append(load_mat(Path(f"{base}.ad.mat"), "data").astype(np.float32).ravel())
        all_rd.append(load_mat(Path(f"{base}.rd.mat"), "data").astype(np.float32).ravel())

    cord = np.concatenate(all_cord, axis=1)  # (3, N_points)
    cord = np.vstack([cord, np.ones((1, cord.shape[1]), dtype=np.float32)])  # homogeneous
    length = np.concatenate(all_len)

    qa = np.concatenate(all_qa)
    fa = np.concatenate(all_fa)
    md = np.concatenate(all_md)
    ad = np.concatenate(all_ad)
    rd = np.concatenate(all_rd)

    # Start/end indices (0-indexed, inclusive)
    ends = np.cumsum(length.astype(np.int64))
    starts = np.concatenate([[0], ends[:-1]])

    # Per-tract mean metrics
    n_tracts = len(length)
    metrics = {m: np.zeros(n_tracts, dtype=np.float32)
               for m in ("qa", "fa", "md", "ad", "rd")}
    vals = {"qa": qa, "fa": fa, "md": md, "ad": ad, "rd": rd}

    for i in range(n_tracts):
        s, e = int(starts[i]), int(ends[i])
        for m, arr in vals.items():
            metrics[m][i] = np.mean(arr[s:e])

    return {
        "cord": cord,
        "length": length,
        "starts": starts,
        "ends": ends,
        "qa_trk": metrics["qa"],
        "fa_trk": metrics["fa"],
        "md_trk": metrics["md"],
        "ad_trk": metrics["ad"],
        "rd_trk": metrics["rd"],
        "qa_pts": qa,
        "fa_pts": fa,
        "md_pts": md,
        "ad_pts": ad,
        "rd_pts": rd,
    }


def _save_trk_h5(path: Path, data: dict) -> None:
    """Save tract data to whole_brain_trk.h5."""
    save_h5(path, {
        "trk": {
            "cord": data["cord"],
            "length": data["length"],
            "start_idx": data["starts"],
            "end_idx": data["ends"],
            "qa": data["qa_trk"],
            "fa": data["fa_trk"],
            "md": data["md_trk"],
            "ad": data["ad_trk"],
            "rd": data["rd_trk"],
        }
    })


def _save_subvox_h5(path: Path, data: dict) -> None:
    """Save per-point metrics to whole_brain_trksubVox.h5."""
    save_h5(path, {
        "trksubVox": {
            "qa": data["qa_pts"],
            "fa": data["fa_pts"],
            "md": data["md_pts"],
            "ad": data["ad_pts"],
            "rd": data["rd_pts"],
        }
    })
