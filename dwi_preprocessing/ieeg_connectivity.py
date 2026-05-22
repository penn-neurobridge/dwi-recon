"""iEEG electrode-level structural connectivity.

Projects cortical electrodes to white-matter surface, finds tracts
passing within a sphere around each electrode pair, and builds
per-metric connectivity matrices.
"""

import os
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.spatial import KDTree

from dwi_preprocessing.utils.geometry import inpolyhedron
from dwi_preprocessing.utils.io import load_h5, save_h5
from dwi_preprocessing.utils.surfaces import read_surf


# ── Step 1: Grey-to-white projection ─────────────────────────────────

def ieeg_grey2white(
    freesurfer_dir: Path,
    electrodes_csv: Path,
    output_dir: Path,
) -> pd.DataFrame:
    """Project cortical (grey-matter) electrodes onto the WM surface.

    Parameters
    ----------
    freesurfer_dir : Path
        FreeSurfer subject directory.
    electrodes_csv : Path
        electrodes2ROI.csv from ieeg_recon module 3.
    output_dir : Path
        Output directory (e.g. derivatives/connectivityIEEG).

    Returns
    -------
    DataFrame with updated electrode positions.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_csv = output_dir / "electrodes_surf_proj.csv"

    if cache_csv.is_file():
        print("  Electrodes already projected — loading cache")
        return pd.read_csv(str(cache_csv))

    electrodes = pd.read_csv(str(electrodes_csv))
    electrodes = electrodes[electrodes["roi"] != "outside-brain"].reset_index(drop=True)

    # Cortical contacts only (roiNum > 999)
    in_cortex = electrodes["roiNum"] > 999
    in_cortex_idx = np.where(in_cortex)[0]
    elec_surf = electrodes.loc[in_cortex, ["surfmm_x", "surfmm_y", "surfmm_z"]].values

    # Load surfaces
    surf_dir = freesurfer_dir / "surf"
    lpv, lpf = read_surf(str(surf_dir / "lh.pial"))
    lwv, lwf = read_surf(str(surf_dir / "lh.white"))
    rpv, rpf = read_surf(str(surf_dir / "rh.pial"))
    rwv, rwf = read_surf(str(surf_dir / "rh.white"))

    # Find electrodes outside white matter
    outside_wm = _find_outside_wm(elec_surf, lwv, lwf, rwv, rwf)
    out_ids = np.where(outside_wm)[0]

    # Project outside-WM electrodes to nearest WM vertex
    wm_xyz = _project_to_wm(elec_surf, out_ids, lpv, rpv, lwv, rwv)

    # Update coordinates
    gm_global_idx = in_cortex_idx[out_ids]
    electrodes.loc[gm_global_idx, "surfmm_x"] = wm_xyz[:, 0]
    electrodes.loc[gm_global_idx, "surfmm_y"] = wm_xyz[:, 1]
    electrodes.loc[gm_global_idx, "surfmm_z"] = wm_xyz[:, 2]

    electrodes.to_csv(str(cache_csv), index=False)
    return electrodes


# ── Step 2: Build edge list ───────────────────────────────────────────

def make_edge_list(
    electrodes: pd.DataFrame,
    sphere_dia: float,
    trk_h5: Path,
    subvox_h5: Path,
    surfras_txt: Path,
    output_dir: Path,
) -> pd.DataFrame:
    """Find tracts passing within sphere_dia of electrode pairs.

    Parameters
    ----------
    electrodes : DataFrame
        Projected electrode positions.
    sphere_dia : float
        Sphere diameter in mm around each electrode.
    trk_h5 : Path
        whole_brain_trk.h5.
    subvox_h5 : Path
        whole_brain_trksubVox.h5.
    surfras_txt : Path
        trk_to_t1surfRAS.txt transform.
    output_dir : Path
        Output directory (e.g. derivatives/connectivityIEEG).

    Returns
    -------
    DataFrame with columns: roi1, roi2, length, qa, fa, md, ad, rd, trkindx
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    cache = output_dir / f"edgeList_{sphere_dia}mmSph.csv"

    if cache.is_file():
        print(f"  Edge list ({sphere_dia}mm) already exists — loading")
        return pd.read_csv(str(cache))

    ieeg_projected = electrodes[["surfmm_x", "surfmm_y", "surfmm_z"]].values

    # Load tracts
    print("  Loading whole_brain_trk.h5...")
    trk = load_h5(trk_h5, group="trk")
    cord = trk["cord"]              # (4, N_points)
    length = trk["length"].ravel()
    starts = trk["start_idx"].astype(np.int64).ravel()
    ends = trk["end_idx"].astype(np.int64).ravel()

    # Transform to surface RAS
    xform = np.loadtxt(str(surfras_txt))
    cord = xform @ cord

    # Load per-point metrics (as separate contiguous arrays so joblib can
    # memory-map and share them read-only across worker processes)
    print("  Loading whole_brain_trksubVox.h5...")
    sv = load_h5(subvox_h5, group="trksubVox")
    qa = np.ascontiguousarray(sv["qa"].ravel())
    fa = np.ascontiguousarray(sv["fa"].ravel())
    md = np.ascontiguousarray(sv["md"].ravel())
    ad = np.ascontiguousarray(sv["ad"].ravel())
    rd = np.ascontiguousarray(sv["rd"].ravel())

    n_tracts = len(length)
    cord_xyz = np.ascontiguousarray(cord[:3, :])
    starts = np.ascontiguousarray(starts)
    ends = np.ascontiguousarray(ends)

    # True multiprocess parallelism (like MATLAB parpool): the default loky
    # backend runs separate processes, and joblib auto-memmaps the large
    # arrays (cord_xyz, qa/fa/md/ad/rd) so they are shared, not re-pickled.
    # Tracts are split into a few chunks per CPU for load balancing.
    n_jobs = -1
    n_cpu = os.cpu_count() or 4
    n_chunks = min(n_tracts, n_cpu * 4)
    chunks = [c for c in np.array_split(np.arange(n_tracts), n_chunks) if len(c)]

    print(f"  Building edge list ({sphere_dia}mm) over {n_tracts} tracts "
          f"on {n_cpu} CPUs ({len(chunks)} chunks)...")

    chunk_results = Parallel(n_jobs=n_jobs)(
        delayed(_process_tract_chunk)(
            chunk, cord_xyz, starts, ends, qa, fa, md, ad, rd,
            ieeg_projected, sphere_dia,
        )
        for chunk in chunks
    )
    all_edges = [res for chunk in chunk_results for res in chunk]

    if all_edges:
        edge_arr = np.vstack(all_edges)
        edge_list = pd.DataFrame(edge_arr, columns=[
            "roi1", "roi2", "length", "qa", "fa", "md", "ad", "rd", "trkindx"
        ])
    else:
        edge_list = pd.DataFrame(columns=[
            "roi1", "roi2", "length", "qa", "fa", "md", "ad", "rd", "trkindx"
        ])

    edge_list.to_csv(str(cache), index=False)
    return edge_list


# ── Step 3: Connectivity matrices ─────────────────────────────────────

def make_connectivity_matrix(
    edge_list: pd.DataFrame,
    sphere_dia: float,
    electrodes_csv: Path,
    output_dir: Path,
) -> Path:
    """Aggregate edge list into symmetric connectivity matrices.

    Saves per-subject connectivity.h5 with groups for each sphere diameter.

    Parameters
    ----------
    edge_list : DataFrame
        Edge list from make_edge_list.
    sphere_dia : float
        Sphere diameter label.
    electrodes_csv : Path
        Original electrodes2ROI.csv for electrode count.
    output_dir : Path
        Output directory (e.g. derivatives/connectivityIEEG).

    Returns
    -------
    Path to connectivity.h5.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    conn_h5 = output_dir / "connectivity.h5"

    group_name = f"ieeg-sc-{int(sphere_dia)}mmSph"

    # Check if this group already exists
    if conn_h5.is_file():
        existing = load_h5(conn_h5)
        if group_name in existing:
            print(f"  Connectivity ({sphere_dia}mm) already in connectivity.h5 — skipping")
            return conn_h5

    # Load electrode metadata
    electrodes = pd.read_csv(str(electrodes_csv))
    electrodes = electrodes[electrodes["roi"] != "outside-brain"].reset_index(drop=True)
    n = len(electrodes)

    # Aggregate
    metrics = ("count", "length", "qa", "fa", "md", "ad", "rd")
    conn = {m: np.zeros((n, n)) for m in metrics}

    for _, row in edge_list.iterrows():
        r1 = int(row["roi1"]) - 1  # Back to 0-indexed
        r2 = int(row["roi2"]) - 1
        if r1 >= n or r2 >= n:
            continue
        conn["count"][r1, r2] += 1
        conn["length"][r1, r2] += row["length"]
        conn["qa"][r1, r2] += row["qa"]
        conn["fa"][r1, r2] += row["fa"]
        conn["md"][r1, r2] += row["md"]
        conn["ad"][r1, r2] += row["ad"]
        conn["rd"][r1, r2] += row["rd"]

    # Symmetrise
    for m in metrics:
        conn[m] = conn[m] + conn[m].T

    # Mean (divide by count)
    for m in ("length", "qa", "fa", "md", "ad", "rd"):
        with np.errstate(divide="ignore", invalid="ignore"):
            conn[m] = np.where(conn["count"] > 0, conn[m] / conn["count"], 0.0)

    # Half diagonal of count
    np.fill_diagonal(conn["count"], np.diag(conn["count"]) / 2)

    # Replace NaN
    for m in metrics:
        conn[m] = np.nan_to_num(conn[m], nan=0.0)

    # Build full H5 data — include electrode metadata + connectivity
    h5_data: dict = {}

    # Electrode info group
    h5_data["ieeg"] = {
        "coordinate": electrodes[["surfmm_x", "surfmm_y", "surfmm_z"]].values.T,
        "labels": np.array(electrodes["labels"].tolist(), dtype=object).reshape(1, -1),
    }

    # Atlas info group
    if "roi" in electrodes.columns:
        h5_data["ieeg-atlas-dkt"] = {
            "roi": np.array(electrodes["roi"].tolist(), dtype=object).reshape(1, -1),
            "roi_fsnum": electrodes["roiNum"].values.astype(float).reshape(1, -1),
        }

    # Load existing H5 data if file exists (to preserve other sphere groups)
    if conn_h5.is_file():
        existing = load_h5(conn_h5)
        for k, v in existing.items():
            if k not in h5_data:
                h5_data[k] = v

    # Add connectivity for this sphere diameter
    h5_data[group_name] = conn

    save_h5(conn_h5, h5_data)
    print(f"  Connectivity ({sphere_dia}mm) saved: {n}x{n}")
    return conn_h5


# ── Private helpers ───────────────────────────────────────────────────

def _find_outside_wm(
    elec_surf: np.ndarray,
    lwv: np.ndarray,
    lwf: np.ndarray,
    rwv: np.ndarray,
    rwf: np.ndarray,
) -> np.ndarray:
    """Test which electrodes are outside both WM surfaces."""
    in_left = inpolyhedron(lwv, lwf, elec_surf)
    in_right = inpolyhedron(rwv, rwf, elec_surf)
    return ~in_left & ~in_right


def _project_to_wm(
    elec_surf: np.ndarray,
    out_ids: np.ndarray,
    lpv: np.ndarray,
    rpv: np.ndarray,
    lwv: np.ndarray,
    rwv: np.ndarray,
) -> np.ndarray:
    """Project outside-WM electrodes to nearest pial → corresponding WM vertex."""
    lp_tree = KDTree(lpv)
    rp_tree = KDTree(rpv)

    wm_xyz = np.full((len(out_ids), 3), np.nan)

    for k, oid in enumerate(out_ids):
        dl, il = lp_tree.query(elec_surf[oid])
        dr, ir = rp_tree.query(elec_surf[oid])
        if dl < dr:
            wm_xyz[k] = lwv[il]
        else:
            wm_xyz[k] = rwv[ir]

    return wm_xyz


def _process_tract_chunk(
    t_indices: np.ndarray,
    cord_xyz: np.ndarray,
    starts: np.ndarray,
    ends: np.ndarray,
    qa: np.ndarray,
    fa: np.ndarray,
    md: np.ndarray,
    ad: np.ndarray,
    rd: np.ndarray,
    ieeg_projected: np.ndarray,
    sphere_dia: float,
) -> list[np.ndarray]:
    """Process a contiguous chunk of tracts in one worker process.

    Looping inside the worker (rather than one joblib task per tract)
    keeps per-task overhead low while the large arrays are memory-mapped
    and shared across processes.
    """
    out = []
    for t in t_indices:
        res = _process_tract(
            int(t), cord_xyz, starts, ends, qa, fa, md, ad, rd,
            ieeg_projected, sphere_dia,
        )
        if res is not None:
            out.append(res)
    return out


def _process_tract(
    t: int,
    cord_xyz: np.ndarray,
    starts: np.ndarray,
    ends: np.ndarray,
    qa: np.ndarray,
    fa: np.ndarray,
    md: np.ndarray,
    ad: np.ndarray,
    rd: np.ndarray,
    ieeg_projected: np.ndarray,
    sphere_dia: float,
) -> np.ndarray | None:
    """Process a single tract: find electrode pairs within sphere_dia."""
    s = int(starts[t])
    e = int(ends[t]) + 1  # inclusive → exclusive
    tract_pts = cord_xyz[:, s:e].T  # (n_pts, 3)

    tree = KDTree(tract_pts)
    dists, _ = tree.query(ieeg_projected)

    connected = np.where(dists <= sphere_dia)[0]
    if len(connected) < 2:
        return None

    # Find electrode positions along the tract
    elec_on_trk = []
    for elec_idx in connected:
        d_to_tract = np.linalg.norm(tract_pts - ieeg_projected[elec_idx], axis=1)
        pos = int(np.argmin(d_to_tract))
        if d_to_tract[pos] <= sphere_dia:
            elec_on_trk.append((int(elec_idx), pos))

    if len(elec_on_trk) < 2:
        return None

    # Sort by position along tract
    elec_on_trk.sort(key=lambda x: x[1])
    elec_indices = [x[0] for x in elec_on_trk]
    elec_positions = [x[1] for x in elec_on_trk]

    # All electrode pairs along this tract
    results = []
    for i, j in combinations(range(len(elec_indices)), 2):
        roi1 = elec_indices[i] + 1  # 1-indexed (MATLAB-compatible)
        roi2 = elec_indices[j] + 1
        pos_start = elec_positions[i]
        pos_end = elec_positions[j]

        abs_start = s + pos_start
        abs_end = s + pos_end + 1  # exclusive

        seg_len = pos_end - pos_start + 1
        seg_qa = np.mean(qa[abs_start:abs_end])
        seg_fa = np.mean(fa[abs_start:abs_end])
        seg_md = np.mean(md[abs_start:abs_end])
        seg_ad = np.mean(ad[abs_start:abs_end])
        seg_rd = np.mean(rd[abs_start:abs_end])

        results.append([roi1, roi2, seg_len, seg_qa, seg_fa,
                        seg_md, seg_ad, seg_rd, t + 1])

    return np.array(results)
