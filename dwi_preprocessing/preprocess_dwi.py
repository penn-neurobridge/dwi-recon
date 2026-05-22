"""PreprocessDWI — Python port of preprocessDWI.m

Wraps FSL, FreeSurfer and DSI Studio CLI tools for DWI preprocessing,
fiber tracking, tract-to-T1 alignment, and atlas-based connectivity.
"""

import glob
import os
import shutil
import subprocess
from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd

from dwi_preprocessing.config import Config
from dwi_preprocessing.utils.surfaces import read_surf, vox2ras_tkreg, vox2ras_0to1
from dwi_preprocessing.utils.io import load_mat, save_mat_v73


def _run(cmd: str):
    """Run a shell command, printing it and raising on failure."""
    print(f"  >> {cmd}")
    subprocess.run(cmd, shell=True, check=True)


def _exists(path: str | Path) -> bool:
    """Check if a file exists (equivalent to MATLAB mustBeFile in try block)."""
    return Path(path).is_file()


def _exists_dir(path: str | Path) -> bool:
    return Path(path).is_dir()


class PreprocessDWI:
    """DWI preprocessing pipeline.

    Attributes mirror the MATLAB class properties. Tool paths come from
    setup_environment.json via Config.
    """

    def __init__(self, config: Config | None = None):
        if config is None:
            config = Config()
        self.cfg = config

        # These are set by the caller per-subject
        self.fmap_mag: str = ""
        self.fmap_phase: str = ""
        self.fmap_reversed: str = ""
        self.dwi: str = ""
        self.bval: str = ""
        self.bvec: str = ""
        self.t1mri: str = ""
        self.output: str = ""
        self.freesurfer_dir: str = ""

    # ------------------------------------------------------------------
    # Eddy / distortion correction
    # ------------------------------------------------------------------

    def topup_eddy(self, data_for_eddy: dict) -> dict:
        """Apply TOPUP and Eddy correction for DWI data."""
        outdir = os.path.join(self.output, "preprocessDWI", "topupEddy")
        os.makedirs(outdir, exist_ok=True)

        dwi_eddy = os.path.join(outdir, "dwi_eddy.nii.gz")
        dwi_eddy_bvec = os.path.join(outdir, "dwi_eddy.eddy_rotated_bvecs")

        if _exists(dwi_eddy) and _exists(dwi_eddy_bvec):
            print("  topupEddy already complete — skipping")
            return {"dwi_eddy": dwi_eddy, "dwi_eddy_bvec": dwi_eddy_bvec}

        # Extract b0 from DWI
        nodif = os.path.join(outdir, "nodif")
        _run(f"{self.cfg.fsl('fslroi')} {self.dwi} {nodif} 0 1")

        # Extract b0 from reversed fieldmap
        nodif_PA = os.path.join(outdir, "nodif_PA")
        _run(f"{self.cfg.fsl('fslroi')} {self.fmap_reversed} {nodif_PA} 0 1")

        # Merge AP and PA b0
        AP_PA_b0 = os.path.join(outdir, "AP_PA_b0")
        _run(f"{self.cfg.fsl('fslmerge')} -t {AP_PA_b0} {nodif} {nodif_PA}")

        # TOPUP
        topup_out = os.path.join(outdir, "topup_AP_PA_b0")
        topup_iout = os.path.join(outdir, "topup_AP_PA_b0_iout")
        topup_fout = os.path.join(outdir, "topup_AP_PA_b0_fout")
        _run(
            f"{self.cfg.fsl('topup')}"
            f" --imain={AP_PA_b0}"
            f" --datain={data_for_eddy['acqparams']}"
            f" --config={data_for_eddy['b02b0_1']}"
            f" --out={topup_out}"
            f" --iout={topup_iout}"
            f" --fout={topup_fout}"
            f" --verbose"
        )

        # Mean of corrected b0
        hifi_nodif = os.path.join(outdir, "hifi_nodif")
        _run(f"{self.cfg.fsl('fslmaths')} {topup_iout} -Tmean {hifi_nodif}")

        # Brain mask
        hifi_brain = os.path.join(outdir, "hifi_nodif_brain")
        _run(f"{self.cfg.fsl('bet')} {hifi_nodif} {hifi_brain} -m -f 0.2")

        # Index file
        bvals = np.loadtxt(self.bval)
        idx = np.ones(len(bvals), dtype=int)
        idx_file = os.path.join(outdir, "index.txt")
        np.savetxt(idx_file, idx, fmt="%d")

        # Eddy
        dwi_eddy_base = os.path.join(outdir, "dwi_eddy")
        _run(
            f"{self.cfg.fsl('eddy_openmp')}"
            f" --imain={self.dwi}"
            f" --mask={hifi_brain}_mask"
            f" --index={idx_file}"
            f" --acqp={data_for_eddy['acqparams']}"
            f" --bvecs={self.bvec}"
            f" --bvals={self.bval}"
            f" --fwhm=10,0,0,0,0"
            f" --topup={topup_out}"
            f" --flm=quadratic"
            f" --out={dwi_eddy_base}"
            f" --repol"
            f" --cnr_maps"
            f" --estimate_move_by_susceptibility"
            f" --verbose"
        )

        assert _exists(dwi_eddy), f"Eddy failed: {dwi_eddy} not found"
        assert _exists(dwi_eddy_bvec), f"Eddy failed: {dwi_eddy_bvec} not found"
        return {"dwi_eddy": dwi_eddy, "dwi_eddy_bvec": dwi_eddy_bvec}

    # ------------------------------------------------------------------
    # EPI-to-T1 registration (BBR)
    # ------------------------------------------------------------------

    def register_epi2t1(self, data_for_tracking: dict) -> dict:
        """Register EPI (DWI b0) to FreeSurfer T1 using epi_reg."""
        outdir = os.path.join(self.output, "connectivityDWI", "bbr2freesurferT1")
        os.makedirs(outdir, exist_ok=True)

        dwi_to_t1_txt = os.path.join(outdir, "dwi_to_t1.txt")
        b0 = os.path.join(outdir, "dwi_eddy.b0.gz.nii.gz")
        b0_brain = os.path.join(outdir, "dwi_eddy.b0.gz.brain.nii.gz")
        b0_brain_mask = os.path.join(outdir, "dwi_eddy.b0.gz.brain_mask.nii.gz")

        if _exists(dwi_to_t1_txt) and _exists(b0) and _exists(b0_brain) and _exists(b0_brain_mask):
            print("  EPI-to-T1 registration already complete — skipping")
            data_for_tracking["dwi_to_freesurferT1"] = dwi_to_t1_txt
            data_for_tracking["dwi_eddy_b0"] = b0
            data_for_tracking["dwi_eddy_b0_brain"] = b0_brain
            data_for_tracking["dwi_eddy_b0_brain_mask"] = b0_brain_mask
            return data_for_tracking

        # Extract b0
        _run(f"{self.cfg.fsl('fslroi')} {data_for_tracking['dwi_eddy']} {b0} 0 1")

        # Brain extraction
        _run(f"{self.cfg.fsl('bet')} {b0} {b0_brain} -m -f 0.1")

        # Convert FreeSurfer volumes to nifti
        for vol in ["wm", "T1", "brain"]:
            mgz = os.path.join(self.freesurfer_dir, "mri", f"{vol}.mgz")
            nii = os.path.join(self.freesurfer_dir, "mri", f"{vol}.nii.gz")
            if not _exists(nii):
                _run(f"{self.cfg.fs('mri_convert')} {mgz} {nii}")

        wm_nii = os.path.join(self.freesurfer_dir, "mri", "wm.nii.gz")
        t1_nii = os.path.join(self.freesurfer_dir, "mri", "T1.nii.gz")
        brain_nii = os.path.join(self.freesurfer_dir, "mri", "brain.nii.gz")

        # Binarise WM
        wmbin = os.path.join(outdir, "wmbin.nii.gz")
        _run(f"{self.cfg.fsl('fslmaths')} {wm_nii} -bin {wmbin}")

        # epi_reg
        dwi_to_t1_base = os.path.join(outdir, "dwi_to_t1")
        _run(
            f"{self.cfg.fsl('epi_reg')}"
            f" --epi={b0}"
            f" --t1={t1_nii}"
            f" --t1brain={brain_nii}"
            f" --out={dwi_to_t1_base}"
            f" --wmseg={wmbin}"
            f" -v"
        )

        # Copy .mat -> .txt
        shutil.copy2(f"{dwi_to_t1_base}.mat", dwi_to_t1_txt)

        data_for_tracking["dwi_to_freesurferT1"] = dwi_to_t1_txt
        data_for_tracking["dwi_eddy_b0"] = b0
        data_for_tracking["dwi_eddy_b0_brain"] = b0_brain
        data_for_tracking["dwi_eddy_b0_brain_mask"] = b0_brain_mask
        return data_for_tracking

    # ------------------------------------------------------------------
    # DSI Studio: NIFTI -> SRC
    # ------------------------------------------------------------------

    def nifti2src(self, data_for_tracking: dict) -> dict:
        """Convert eddy-corrected DWI to DSI Studio SRC format."""
        outdir = os.path.join(self.output, "preprocessDWI", "dsiStudio")
        os.makedirs(outdir, exist_ok=True)

        dwi_src = os.path.join(outdir, "dwi_eddy.src.gz")

        if _exists(dwi_src):
            print("  SRC already exists — skipping")
            data_for_tracking["dwi_src"] = dwi_src
            return data_for_tracking

        _run(
            f"{self.cfg.dsi_studio}"
            f" --action=src"
            f" --source={data_for_tracking['dwi_eddy']}"
            f" --bval={self.bval}"
            f" --bvec={data_for_tracking['dwi_eddy_bvec']}"
            f" --output={dwi_src}"
        )

        assert _exists(dwi_src), f"SRC creation failed: {dwi_src}"
        data_for_tracking["dwi_src"] = dwi_src
        return data_for_tracking

    # ------------------------------------------------------------------
    # DSI Studio: SRC -> GQI reconstruction
    # ------------------------------------------------------------------

    def src2gqi(self, data_for_tracking: dict) -> dict:
        """Reconstruct GQI fib file from SRC."""
        outdir = os.path.join(self.output, "preprocessDWI", "dsiStudio")

        fib_pattern = os.path.join(outdir, "*gqi*fib.gz")
        fib_matches = glob.glob(fib_pattern)

        if fib_matches:
            dwi_fib = fib_matches[0]
            fa_nii = f"{dwi_fib}.dti_fa.nii.gz"
            if _exists(dwi_fib) and _exists(fa_nii):
                print("  GQI fib already exists — skipping")
                data_for_tracking["dwi_fib"] = dwi_fib
                data_for_tracking["dwi_fib_qa"] = f"{dwi_fib}.qa.nii.gz"
                data_for_tracking["dwi_fib_fa"] = fa_nii
                data_for_tracking["dwi_fib_md"] = f"{dwi_fib}.md.nii.gz"
                data_for_tracking["dwi_fib_ad"] = f"{dwi_fib}.ad.nii.gz"
                data_for_tracking["dwi_fib_rd"] = f"{dwi_fib}.rd.nii.gz"
                return data_for_tracking

        _run(
            f"{self.cfg.dsi_studio}"
            f" --action=rec"
            f" --source={data_for_tracking['dwi_src']}"
            f" --method=4"
            f" --param0=1.25"
            f" --check_btable=1"
            f" --align_acpc=0"
            f" --mask={data_for_tracking['dwi_eddy_b0_brain_mask']}"
            f" --record_odf=0"
        )

        fib_matches = glob.glob(fib_pattern)
        assert fib_matches, "GQI reconstruction failed — no fib.gz found"
        dwi_fib = fib_matches[0]

        # Export scalar maps
        _run(
            f"{self.cfg.dsi_studio}"
            f" --action=exp"
            f" --source={dwi_fib}"
            f" --export=qa,dti_fa,md,ad,rd"
        )

        data_for_tracking["dwi_fib"] = dwi_fib
        data_for_tracking["dwi_fib_qa"] = f"{dwi_fib}.qa.nii.gz"
        data_for_tracking["dwi_fib_fa"] = f"{dwi_fib}.dti_fa.nii.gz"
        data_for_tracking["dwi_fib_md"] = f"{dwi_fib}.md.nii.gz"
        data_for_tracking["dwi_fib_ad"] = f"{dwi_fib}.ad.nii.gz"
        data_for_tracking["dwi_fib_rd"] = f"{dwi_fib}.rd.nii.gz"
        return data_for_tracking

    # ------------------------------------------------------------------
    # DSI Studio: fiber tracking (single run, .trk.gz output)
    # ------------------------------------------------------------------

    def fiber_tracking(self, data_for_tracking: dict) -> dict:
        """Run whole-brain fiber tracking (single pass)."""
        dwi_fib = data_for_tracking["dwi_fib"]
        trk_gz = f"{dwi_fib}.trk.gz"

        if _exists(trk_gz):
            print("  Fiber tracking (.trk.gz) already complete — skipping")
            data_for_tracking["dwi_trk"] = trk_gz
            return data_for_tracking

        n = data_for_tracking.get("nStreamlines", 2500000)
        _run(
            f"{self.cfg.dsi_studio}"
            f" --action=trk"
            f" --source={dwi_fib}"
            f" --fiber_count={n}"
            f" --method=1"
            f" --trim=1"
            f" --min_length=30"
            f" --max_length=300"
            f" --random_seed=0"
            f" --step_size=1"
            f" --output={trk_gz}"
        )

        data_for_tracking["dwi_trk"] = trk_gz
        return data_for_tracking

    # ------------------------------------------------------------------
    # DSI Studio: iterative fiber tracking with per-point metric export
    # ------------------------------------------------------------------

    def fiber_tracking_ittr(self, data_for_tracking: dict,
                            save_trksubvox: bool = False) -> dict:
        """Run fiber tracking in 10 iterations, concatenate, and save.

        Produces whole_brain_trk.mat and optionally whole_brain_trksubVox.mat.
        """
        outdir = os.path.join(self.output, "preprocessDWI", "dsiStudio")
        os.makedirs(outdir, exist_ok=True)
        dwi_tt = os.path.join(outdir, "whole_brain")

        trk_file = f"{dwi_tt}_trk.mat"
        subvox_file = f"{dwi_tt}_trksubVox.mat"

        trk_exists = _exists(trk_file)
        subvox_exists = _exists(subvox_file)
        need_tracking = (not trk_exists) or (save_trksubvox and not subvox_exists)

        if not need_tracking:
            print("  whole_brain_trk.mat and trksubVox.mat already exist — skipping")
            data_for_tracking["dwi_tt_trk"] = trk_file
            if save_trksubvox:
                data_for_tracking["dwi_tt_trksubVox"] = subvox_file
            return data_for_tracking

        if trk_exists and save_trksubvox and not subvox_exists:
            print("  whole_brain_trk.mat exists but trksubVox.mat is missing"
                  " — re-running tractography to capture per-point metrics")

        n = data_for_tracking.get("nStreamlines", 2500000)
        dwi_fib = data_for_tracking["dwi_fib"]

        # Run 10 iterations
        for ittr in range(1, 11):
            out_mat = f"{dwi_tt}_ittr{ittr}.mat"
            _run(
                f"{self.cfg.dsi_studio}"
                f" --action=trk"
                f" --source={dwi_fib}"
                f" --fiber_count={n // 10}"
                f" --method=1"
                f" --trim=1"
                f" --min_length=30"
                f" --max_length=300"
                f" --random_seed=1"
                f" --thread_count=16"
                f" --step_size=1"
                f" --export=qa.mat,dti_fa.mat,md.mat,ad.mat,rd.mat"
                f" --output={out_mat}"
            )

        # Concatenate all iterations
        all_cord, all_len = [], []
        all_qa, all_fa, all_md, all_ad, all_rd = [], [], [], [], []

        for ittr in range(1, 11):
            base = f"{dwi_tt}_ittr{ittr}.mat"
            d = load_mat(base)
            all_cord.append(d["tracts"].astype(np.float32))
            all_len.append(d["length"].astype(np.float32).ravel())

            all_qa.append(load_mat(f"{base}.qa.mat", "data").astype(np.float32).ravel())
            all_fa.append(load_mat(f"{base}.dti_fa.mat", "data").astype(np.float32).ravel())
            all_md.append(load_mat(f"{base}.md.mat", "data").astype(np.float32).ravel())
            all_ad.append(load_mat(f"{base}.ad.mat", "data").astype(np.float32).ravel())
            all_rd.append(load_mat(f"{base}.rd.mat", "data").astype(np.float32).ravel())

        cord = np.concatenate(all_cord, axis=1)  # (3, N_points)
        # Add homogeneous row
        cord = np.vstack([cord, np.ones((1, cord.shape[1]), dtype=np.float32)])
        length = np.concatenate(all_len)  # (N_tracts,)

        qa = np.concatenate(all_qa)
        fa = np.concatenate(all_fa)
        md = np.concatenate(all_md)
        ad = np.concatenate(all_ad)
        rd = np.concatenate(all_rd)

        # Compute start/end indices
        ends = np.cumsum(length.astype(np.int64))
        starts = np.concatenate([[0], ends[:-1]])
        start_end = np.column_stack([starts, ends - 1])  # 0-indexed, inclusive

        # Per-tract mean metrics
        n_tracts = len(length)
        qa_trk = np.zeros(n_tracts, dtype=np.float32)
        fa_trk = np.zeros(n_tracts, dtype=np.float32)
        md_trk = np.zeros(n_tracts, dtype=np.float32)
        ad_trk = np.zeros(n_tracts, dtype=np.float32)
        rd_trk = np.zeros(n_tracts, dtype=np.float32)

        for i in range(n_tracts):
            s, e = int(starts[i]), int(ends[i])
            qa_trk[i] = np.mean(qa[s:e])
            fa_trk[i] = np.mean(fa[s:e])
            md_trk[i] = np.mean(md[s:e])
            ad_trk[i] = np.mean(ad[s:e])
            rd_trk[i] = np.mean(rd[s:e])

        # Save trk — using MATLAB-compatible 1-indexed startEnd
        trk_data = {
            "length": length,
            "cord": cord,
            "startEnd": (start_end + 1).astype(np.float64),  # 1-indexed for MATLAB compat
            "qaTrk": qa_trk,
            "faTrk": fa_trk,
            "mdTrk": md_trk,
            "adTrk": ad_trk,
            "rdTrk": rd_trk,
        }
        save_mat_v73(trk_file, {"trk": trk_data})

        # Cleanup iteration files
        for ittr in range(1, 11):
            for f in glob.glob(f"{dwi_tt}_ittr{ittr}*"):
                os.remove(f)

        data_for_tracking["dwi_trk"] = f"{dwi_fib}.trk.gz"
        data_for_tracking["dwi_tt_trk"] = trk_file

        if save_trksubvox:
            print("  Saving trksubVox")
            subvox_data = {
                "qa": qa, "fa": fa, "md": md, "ad": ad, "rd": rd,
            }
            save_mat_v73(subvox_file, {"trksubVox": subvox_data})
            data_for_tracking["dwi_tt_trksubVox"] = subvox_file
        else:
            print("  Not saving trksubVox")

        return data_for_tracking

    # ------------------------------------------------------------------
    # Align tracts to T1 surface RAS
    # ------------------------------------------------------------------

    def align_tracts_to_t1(self, data_for_tracking: dict) -> dict:
        """Compute and save the tract-to-T1-surfaceRAS transform."""
        outdir = os.path.join(self.output, "connectivityDWI", "tracts_to_T1")
        os.makedirs(outdir, exist_ok=True)

        surfras_file = os.path.join(outdir, "trk_to_t1surfRAS.txt")
        vox_file = os.path.join(outdir, "trk_to_t1Vox.txt")

        if _exists(surfras_file) and _exists(vox_file):
            print("  Tract-to-T1 alignment already complete — skipping")
            data_for_tracking["trk_to_t1surfRAS"] = surfras_file
            data_for_tracking["trk_to_t1Vox"] = vox_file
            return data_for_tracking

        # Load T1 header
        t1_nii_path = os.path.join(self.freesurfer_dir, "mri", "T1.nii.gz")
        t1_img = nib.load(t1_nii_path)
        t1_shape = t1_img.shape[:3]
        t1_zooms = t1_img.header.get_zooms()[:3]
        t1surfRAS = vox2ras_0to1(vox2ras_tkreg(t1_shape, t1_zooms))

        # Load DWI FA header (for voxel dims / image size)
        fa_img = nib.load(data_for_tracking["dwi_fib_fa"])
        fa_shape = fa_img.shape[:3]
        fa_zooms = fa_img.header.get_zooms()[:3]

        # Load DWI-to-T1 registration matrix
        dwi_to_t1 = np.loadtxt(data_for_tracking["dwi_to_freesurferT1"])

        # Build transformation chain (same as MATLAB)
        T_AP = np.eye(4)
        T_AP[1, 1] = -1
        T_AP[1, 3] = fa_shape[1] - 1  # Flip Anterior-Posterior

        sizeMat = np.diag([fa_zooms[0], fa_zooms[1], fa_zooms[2], 1.0])
        sizeMatT1 = np.diag([1.0 / t1_zooms[0], 1.0 / t1_zooms[1], 1.0 / t1_zooms[2], 1.0])

        trk_to_t1Vox = sizeMatT1 @ dwi_to_t1 @ sizeMat @ T_AP
        trk_to_t1surfRAS = t1surfRAS @ trk_to_t1Vox

        # Save
        np.savetxt(vox_file, trk_to_t1Vox, fmt="%.10f")
        np.savetxt(surfras_file, trk_to_t1surfRAS, fmt="%.10f")

        # QC plot
        try:
            import matplotlib.pyplot as plt

            trk_data = load_mat(data_for_tracking["dwi_tt_trk"])
            # Handle nested struct from h5py
            if "trk" in trk_data:
                trk = trk_data["trk"]
                if isinstance(trk, dict):
                    cord = trk["cord"]
                else:
                    cord = trk_data["trk"]
            else:
                cord = trk_data.get("cord", None)

            if cord is not None:
                transformed = trk_to_t1surfRAS @ cord
                lpv, _ = read_surf(os.path.join(self.freesurfer_dir, "surf", "lh.pial"))
                rpv, _ = read_surf(os.path.join(self.freesurfer_dir, "surf", "rh.pial"))

                fig = plt.figure(figsize=(10, 8))
                ax = fig.add_subplot(111, projection="3d")
                ax.scatter(lpv[::50, 0], lpv[::50, 1], lpv[::50, 2],
                           s=0.1, alpha=0.1, c="gray")
                ax.scatter(rpv[::50, 0], rpv[::50, 1], rpv[::50, 2],
                           s=0.1, alpha=0.1, c="gray")
                step = max(1, transformed.shape[1] // 5000)
                ax.scatter(transformed[0, ::step], transformed[1, ::step],
                           transformed[2, ::step], s=0.3, alpha=0.3, c="blue")
                ax.set_title("Tract-to-T1 alignment QC")
                plt.savefig(os.path.join(outdir, "check_alignment.png"), dpi=150)
                plt.close()
        except Exception as e:
            print(f"  QC plot skipped: {e}")

        data_for_tracking["trk_to_t1surfRAS"] = surfras_file
        data_for_tracking["trk_to_t1Vox"] = vox_file
        return data_for_tracking

    # ------------------------------------------------------------------
    # Atlas ROI coordinates
    # ------------------------------------------------------------------

    def get_roi_cord(self, data_for_tracking: dict,
                     atlas_name: str, lookup_table: str) -> dict:
        """Get ROI coordinates from a FreeSurfer atlas in surface RAS."""
        outdir = os.path.join(self.output, "connectivityDWI", atlas_name)
        os.makedirs(outdir, exist_ok=True)

        atlas_mat = os.path.join(outdir, "atlas.mat")
        if _exists(atlas_mat):
            print(f"  Atlas {atlas_name} already loaded — skipping")
            data_for_tracking["atlas"] = atlas_mat
            return data_for_tracking

        # Convert atlas from mgz to nii
        atlas_mgz = os.path.join(self.freesurfer_dir, "mri", f"{atlas_name}.mgz")
        atlas_nii = os.path.join(self.freesurfer_dir, "mri", f"{atlas_name}.nii.gz")
        if not _exists(atlas_nii):
            _run(f"{self.cfg.fs('mri_convert')} {atlas_mgz} {atlas_nii}")

        atlas_img = nib.load(atlas_nii)
        atlas_data = np.asarray(atlas_img.dataobj)
        lut = pd.read_csv(lookup_table)

        # Get voxel coordinates for each ROI
        voxels = []
        for _, row in lut.iterrows():
            roi_num = row["roiNum"]
            vox = np.argwhere(atlas_data == roi_num)
            if len(vox) > 0:
                roi_col = np.full((len(vox), 1), roi_num)
                voxels.append(np.hstack([vox, roi_col]))
        voxels = np.vstack(voxels)

        # Convert to surface RAS
        hdr = atlas_img.header
        shape = atlas_img.shape[:3]
        zooms = hdr.get_zooms()[:3]
        tk_ras = vox2ras_0to1(vox2ras_tkreg(shape, zooms))

        coords_homo = np.hstack([voxels[:, :3], np.ones((len(voxels), 1))])
        surface_ras = (tk_ras @ coords_homo.T).T
        surface_ras[:, 3] = voxels[:, 3]  # Replace homogeneous coord with ROI number

        save_mat_v73(atlas_mat, {
            "surfaceRAS": surface_ras,
            "lut_roiNum": lut["roiNum"].values,
            "lut_roi": np.array(lut["roi"].tolist(), dtype=object),
        })

        data_for_tracking["atlas"] = atlas_mat
        return data_for_tracking

    # ------------------------------------------------------------------
    # DSI Studio atlas connectivity
    # ------------------------------------------------------------------

    def atlas_connectivity(self, data_for_tracking: dict,
                           atlas_name: str, atlas_file: str,
                           lookup_table: str) -> dict:
        """Run DSI Studio connectivity analysis for an atlas."""
        outdir = os.path.join(self.output, "connectivityDWI", atlas_name)
        os.makedirs(outdir, exist_ok=True)

        conn_mat = os.path.join(outdir, "connectivity.mat")
        if _exists(conn_mat):
            print(f"  Atlas connectivity ({atlas_name}) already complete — skipping")
            data_for_tracking["atlasConnectivity"] = conn_mat
            return data_for_tracking

        lut = pd.read_csv(lookup_table)
        lut["label"] = lut["roi"]
        if "lausanne2018" in atlas_name:
            lut["roi"] = ["lausanne2018_" + str(n) for n in lut["roiNum"]]

        _run(
            f"{self.cfg.dsi_studio}"
            f" --action=ana"
            f" --source={data_for_tracking['dwi_fib']}"
            f" --tract={data_for_tracking['dwi_trk']}"
            f" --t1t2={os.path.join(self.freesurfer_dir, 'mri', 'T1.nii.gz')}"
            f" --connectivity={atlas_file}"
            f" --connectivity_value=dti_fa,md,ad,rd,count,mean_length,qa"
            f" --connectivity_type=end"
            f" --connectivity_threshold=0"
        )

        # Move connectivity files to atlas dir
        fib_dir = os.path.dirname(data_for_tracking["dwi_fib"])
        raw_dir = os.path.join(outdir, "raw_export")
        os.makedirs(raw_dir, exist_ok=True)

        # Remove txt files from fib dir
        for f in glob.glob(os.path.join(fib_dir, "*.txt")):
            os.remove(f)

        # Move connectivity files
        for f in glob.glob(os.path.join(fib_dir, "*connectivity*")):
            shutil.move(f, raw_dir)

        # Parse DSI Studio output and build connectivity struct
        def _load_conn(pattern):
            matches = glob.glob(os.path.join(raw_dir, pattern))
            assert matches, f"No file matching {pattern} in {raw_dir}"
            d = load_mat(matches[0])
            return d["connectivity"], d.get("name", None)

        count_mat, names = _load_conn("*count*")
        if names is not None:
            # Parse label names from DSI Studio output
            if isinstance(names, np.ndarray):
                labels = [str(n).strip() for n in names.ravel()]
            elif isinstance(names, str):
                labels = names.split()
            else:
                labels = list(names)
            idx = [labels.index(r) if r in labels else -1 for r in lut["roi"]]
            idx = np.array([i for i in idx if i >= 0])
        else:
            idx = np.arange(min(len(lut), count_mat.shape[0]))

        connectivity = {
            "count": count_mat[np.ix_(idx, idx)],
        }

        for metric, pattern in [("fa", "*dti_fa*"), ("length", "*mean_length*"),
                                ("md", "*md*"), ("ad", "*ad*"),
                                ("rd", "*rd*"), ("qa", "*qa*")]:
            mat, _ = _load_conn(pattern)
            connectivity[metric] = mat[np.ix_(idx, idx)]

        save_mat_v73(conn_mat, {"connectivity": connectivity})
        data_for_tracking["atlasConnectivity"] = conn_mat
        return data_for_tracking
