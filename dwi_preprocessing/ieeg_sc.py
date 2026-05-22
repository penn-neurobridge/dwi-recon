"""IEEGsc — Python port of iEEGsc.m

Computes structural connectivity between iEEG electrode contacts using
whole-brain fiber tracts and per-point diffusion metrics (QA, FA, MD, AD, RD).
"""

import os
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import KDTree
from joblib import Parallel, delayed

from dwi_preprocessing.utils.surfaces import read_surf
from dwi_preprocessing.utils.geometry import inpolyhedron
from dwi_preprocessing.utils.io import load_mat, save_mat_v73


class IEEGsc:
    """iEEG structural connectivity from DWI tractography.

    Expects the standard derivatives directory layout:
        <output>/preprocessDWI/dsiStudio/whole_brain_trk.mat
        <output>/preprocessDWI/dsiStudio/whole_brain_trksubVox.mat
        <output>/connectivityDWI/tracts_to_T1/trk_to_t1surfRAS.txt
        <output>/freesurfer/surf/{lh,rh}.{pial,white}
        <output>/ieeg_recon/module3/electrodes2ROI.csv
    """

    # Relative paths within the derivatives directory
    _PATHS = {
        "whole_brain_trk": ("preprocessDWI", "dsiStudio", "whole_brain_trk.mat"),
        "whole_brain_trksubVox": ("preprocessDWI", "dsiStudio", "whole_brain_trksubVox.mat"),
        "trk_to_t1surfRAS": ("connectivityDWI", "tracts_to_T1", "trk_to_t1surfRAS.txt"),
        "freeSurferDir": ("freesurfer",),
        "IEEGdata": ("ieeg_recon", "module3", "electrodes2ROI.csv"),
    }

    def __init__(self, output: str | Path):
        self.output = Path(output)

    def _path(self, key: str) -> Path:
        return self.output / os.path.join(*self._PATHS[key])

    # ------------------------------------------------------------------
    # Step 1: Project grey-matter electrodes to white-matter surface
    # ------------------------------------------------------------------

    def ieeg_grey2white(self) -> pd.DataFrame:
        """Project cortical (grey-matter) electrodes onto the WM surface.

        Returns a DataFrame with electrode positions updated so that
        contacts originally in grey matter are projected to the nearest
        white-matter surface vertex.
        """
        outdir = self.output / "connectivityIEEG"
        outdir.mkdir(exist_ok=True)
        cache = outdir / "electrodes_surf_proj.mat"

        if cache.is_file():
            print("  Electrodes already projected — loading cache")
            # Load from mat and reconstruct DataFrame
            d = load_mat(str(cache))
            return pd.DataFrame(d["electrodes"]) if "electrodes" in d else pd.read_csv(str(self._path("IEEGdata")))

        electrodes = pd.read_csv(str(self._path("IEEGdata")))

        # Remove outside-brain contacts
        electrodes = electrodes[electrodes["roi"] != "outside-brain"].reset_index(drop=True)

        # Cortical contacts only (roiNum > 999)
        in_cortex = electrodes["roiNum"] > 999
        in_cortex_idx = np.where(in_cortex)[0]

        elec_surf = electrodes.loc[in_cortex, ["surfmm_x", "surfmm_y", "surfmm_z"]].values

        # Load surfaces
        fs_dir = str(self._path("freeSurferDir"))
        lpv, lpf = read_surf(os.path.join(fs_dir, "surf", "lh.pial"))
        lwv, lwf = read_surf(os.path.join(fs_dir, "surf", "lh.white"))
        rpv, rpf = read_surf(os.path.join(fs_dir, "surf", "rh.pial"))
        rwv, rwf = read_surf(os.path.join(fs_dir, "surf", "rh.white"))

        # Test which electrodes are inside the WM surfaces
        in_left = inpolyhedron(lwv, lwf, elec_surf)
        in_right = inpolyhedron(rwv, rwf, elec_surf)
        outside_wm = ~in_left & ~in_right
        out_ids = np.where(outside_wm)[0]

        # For electrodes outside WM, find nearest pial vertex
        lp_tree = KDTree(lpv)
        rp_tree = KDTree(rpv)

        vids = np.zeros(len(out_ids), dtype=int)
        sides = [""] * len(out_ids)

        for k, oid in enumerate(out_ids):
            dl, il = lp_tree.query(elec_surf[oid])
            dr, ir = rp_tree.query(elec_surf[oid])
            if dl < dr:
                vids[k] = il
                sides[k] = "l"
            else:
                vids[k] = ir
                sides[k] = "r"

        # Build WM projection coordinates
        wm_xyz = np.full((len(out_ids), 3), np.nan)
        for k in range(len(out_ids)):
            if sides[k] == "l":
                wm_xyz[k] = lwv[vids[k]]
            else:
                wm_xyz[k] = rwv[vids[k]]

        # Update electrode coordinates: project GM contacts to WM surface
        gm_global_idx = in_cortex_idx[out_ids]
        electrodes.loc[gm_global_idx, "surfmm_x"] = wm_xyz[:, 0]
        electrodes.loc[gm_global_idx, "surfmm_y"] = wm_xyz[:, 1]
        electrodes.loc[gm_global_idx, "surfmm_z"] = wm_xyz[:, 2]

        # Save cache as CSV (more portable than .mat for DataFrames)
        electrodes.to_csv(str(outdir / "electrodes_surf_proj.csv"), index=False)
        # Also save .mat for MATLAB compatibility
        save_mat_v73(str(cache), {"electrodes_csv_path": str(outdir / "electrodes_surf_proj.csv")})

        return electrodes

    # ------------------------------------------------------------------
    # Step 2: Build edge list (tract-electrode connections)
    # ------------------------------------------------------------------

    def make_edge_list(self, electrodes: pd.DataFrame,
                       sphere_dia: float) -> pd.DataFrame:
        """Find tracts passing within sphere_dia of electrode pairs.

        Returns a DataFrame with columns:
            roi1, roi2, length, qa, fa, md, ad, rd, trkindx
        """
        outdir = self.output / "connectivityIEEG"
        outdir.mkdir(exist_ok=True)
        cache = outdir / f"edgeList_{sphere_dia}mmSph.csv"

        if cache.is_file():
            print(f"  Edge list ({sphere_dia}mm) already exists — loading")
            return pd.read_csv(str(cache))

        ieeg_projected = electrodes[["surfmm_x", "surfmm_y", "surfmm_z"]].values

        # Load tracts
        print(f"  Loading whole_brain_trk.mat...")
        trk_raw = load_mat(str(self._path("whole_brain_trk")))
        # Handle nested h5py struct
        if "trk" in trk_raw and isinstance(trk_raw["trk"], dict):
            trk = trk_raw["trk"]
        else:
            trk = trk_raw

        cord = trk["cord"]  # (4, N_points)
        length = trk["length"].ravel()
        start_end = trk["startEnd"]  # (N_tracts, 2) — 1-indexed from MATLAB

        # Load transform and apply
        xform = np.loadtxt(str(self._path("trk_to_t1surfRAS")))
        cord = xform @ cord  # Transform to surface RAS

        # Load subvoxel metrics
        print(f"  Loading whole_brain_trksubVox.mat...")
        subvox_raw = load_mat(str(self._path("whole_brain_trksubVox")))
        if "trksubVox" in subvox_raw and isinstance(subvox_raw["trksubVox"], dict):
            sv = subvox_raw["trksubVox"]
        else:
            sv = subvox_raw

        subvox_qa = sv["qa"].ravel()
        subvox_fa = sv["fa"].ravel()
        subvox_md = sv["md"].ravel()
        subvox_ad = sv["ad"].ravel()
        subvox_rd = sv["rd"].ravel()

        # Convert start_end to 0-indexed Python
        se = start_end.astype(np.int64)
        se[:, 0] -= 1  # 1-indexed -> 0-indexed start
        se[:, 1] -= 1  # 1-indexed -> 0-indexed end (inclusive)

        # Process in bins for memory efficiency (same as MATLAB)
        n_tracts = len(length)
        n_bins = 1000
        bin_edges = np.linspace(0, n_tracts, n_bins + 1, dtype=int)

        cord_xyz = cord[:3, :]  # (3, N_points)

        print(f"  Building edge list ({sphere_dia}mm) over {n_tracts} tracts...")
        all_edges = []

        for b in range(n_bins):
            b_start = bin_edges[b]
            b_end = bin_edges[b + 1]
            if b_start >= b_end:
                continue

            bin_results = Parallel(n_jobs=-1, prefer="threads")(
                delayed(self._process_tract)(
                    t, cord_xyz, se, subvox_qa, subvox_fa, subvox_md,
                    subvox_ad, subvox_rd, ieeg_projected, sphere_dia, b_start
                )
                for t in range(b_start, b_end)
            )

            for res in bin_results:
                if res is not None:
                    all_edges.append(res)

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
        # Also save .mat for MATLAB compatibility
        save_mat_v73(
            str(outdir / f"edgeList_{sphere_dia}mmSph.mat"),
            {"edgeList": edge_arr if all_edges else np.array([])}
        )
        return edge_list

    @staticmethod
    def _process_tract(t, cord_xyz, se, sq, sf, sm, sa, sr,
                       ieeg_projected, sphere_dia, offset):
        """Process a single tract: find electrodes within sphere_dia."""
        s, e = int(se[t, 0]), int(se[t, 1]) + 1  # inclusive -> exclusive
        tract_pts = cord_xyz[:, s:e].T  # (n_pts, 3)

        tree = KDTree(tract_pts)
        dists, _ = tree.query(ieeg_projected)

        connected = np.where(dists <= sphere_dia)[0]
        if len(connected) < 2:
            return None

        # For each connected electrode, find its position along the tract
        elec_on_trk = []
        for elec_idx in connected:
            d_to_tract = np.linalg.norm(tract_pts - ieeg_projected[elec_idx], axis=1)
            pos = np.argmin(d_to_tract)
            if d_to_tract[pos] <= sphere_dia:
                elec_on_trk.append((elec_idx, pos))

        if len(elec_on_trk) < 2:
            return None

        # Sort by position along tract
        elec_on_trk.sort(key=lambda x: x[1])
        elec_indices = [x[0] for x in elec_on_trk]
        elec_positions = [x[1] for x in elec_on_trk]

        # All pairs
        results = []
        for (i, ei), (j, ej) in combinations(range(len(elec_indices)), 2):
            roi1 = elec_indices[i] + 1  # 1-indexed for MATLAB compat
            roi2 = elec_indices[j] + 1
            pos_start = elec_positions[i]
            pos_end = elec_positions[j]

            abs_start = s + pos_start
            abs_end = s + pos_end + 1  # exclusive

            seg_len = pos_end - pos_start + 1
            seg_qa = np.mean(sq[abs_start:abs_end])
            seg_fa = np.mean(sf[abs_start:abs_end])
            seg_md = np.mean(sm[abs_start:abs_end])
            seg_ad = np.mean(sa[abs_start:abs_end])
            seg_rd = np.mean(sr[abs_start:abs_end])

            results.append([roi1, roi2, seg_len, seg_qa, seg_fa,
                            seg_md, seg_ad, seg_rd, t + 1])  # 1-indexed tract

        return np.array(results)

    # ------------------------------------------------------------------
    # Step 3: Build connectivity matrices
    # ------------------------------------------------------------------

    def make_connectivity_matrix(self, edge_list: pd.DataFrame,
                                 sphere_dia: float) -> dict:
        """Aggregate edge list into symmetric connectivity matrices."""
        outdir = self.output / "connectivityIEEG"
        outdir.mkdir(exist_ok=True)
        cache = outdir / f"connectivity_{sphere_dia}mmSph.mat"

        if cache.is_file():
            print(f"  Connectivity matrix ({sphere_dia}mm) already exists — loading")
            return load_mat(str(cache))

        # Load electrode count
        electrodes = pd.read_csv(str(self._path("IEEGdata")))
        electrodes = electrodes[electrodes["roi"] != "outside-brain"].reset_index(drop=True)
        n = len(electrodes)

        metrics = ["count", "len", "qa", "fa", "md", "ad", "rd"]
        conn = {m: np.zeros((n, n)) for m in metrics}

        for _, row in edge_list.iterrows():
            r1 = int(row["roi1"]) - 1  # Back to 0-indexed
            r2 = int(row["roi2"]) - 1
            if r1 >= n or r2 >= n:
                continue
            conn["count"][r1, r2] += 1
            conn["len"][r1, r2] += row["length"]
            conn["qa"][r1, r2] += row["qa"]
            conn["fa"][r1, r2] += row["fa"]
            conn["md"][r1, r2] += row["md"]
            conn["ad"][r1, r2] += row["ad"]
            conn["rd"][r1, r2] += row["rd"]

        # Symmetrise
        for m in metrics:
            conn[m] = conn[m] + conn[m].T

        # Mean (divide by count)
        for m in ["len", "qa", "fa", "md", "ad", "rd"]:
            with np.errstate(divide="ignore", invalid="ignore"):
                conn[m] = np.where(conn["count"] > 0,
                                   conn[m] / conn["count"], 0.0)

        # Half the diagonal of count
        np.fill_diagonal(conn["count"], np.diag(conn["count"]) / 2)

        # Replace NaN with 0
        for m in metrics:
            conn[m] = np.nan_to_num(conn[m], nan=0.0)

        save_mat_v73(str(cache), {"connectivity": conn})
        # Also save electrode info
        electrodes.to_csv(str(outdir / f"electrodes_{sphere_dia}mmSph.csv"), index=False)

        print(f"  Connectivity matrix ({sphere_dia}mm) saved: {n}x{n}")
        return conn
