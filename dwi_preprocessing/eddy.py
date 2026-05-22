"""Eddy current and susceptibility distortion correction.

Wraps FSL topup + eddy_openmp to correct for eddy currents, motion,
and susceptibility-induced distortions in DWI data.
"""

from pathlib import Path

import numpy as np

from dwi_preprocessing.config import Config
from dwi_preprocessing.utils.shell import run


def topup_eddy(
    cfg: Config,
    dwi: Path,
    dwi_reversed: Path,
    bval: Path,
    bvec: Path,
    acqparams: Path,
    b02b0_config: Path,
    output_dir: Path,
) -> dict[str, Path]:
    """Apply TOPUP and Eddy correction for DWI data.

    Parameters
    ----------
    cfg : Config
        Pipeline configuration with tool paths.
    dwi : Path
        Raw DWI volume (AP phase encoding).
    dwi_reversed : Path
        Reversed phase-encode b0 volume.
    bval, bvec : Path
        Gradient b-values and directions.
    acqparams : Path
        Acquisition parameters file for topup.
    b02b0_config : Path
        TOPUP configuration file (b02b0_1.cnf).
    output_dir : Path
        Output directory (e.g. derivatives/preprocessDWI/topupEddy).

    Returns
    -------
    dict with keys: dwi_eddy, dwi_eddy_bvec
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dwi_eddy = output_dir / "dwi_eddy.nii.gz"
    dwi_eddy_bvec = output_dir / "dwi_eddy.eddy_rotated_bvecs"

    if dwi_eddy.is_file() and dwi_eddy_bvec.is_file():
        print("  topupEddy already complete — skipping")
        return {"dwi_eddy": dwi_eddy, "dwi_eddy_bvec": dwi_eddy_bvec}

    # Extract b0 volumes
    nodif = output_dir / "nodif"
    _fslroi(cfg, dwi, nodif, 0, 1)

    nodif_PA = output_dir / "nodif_PA"
    _fslroi(cfg, dwi_reversed, nodif_PA, 0, 1)

    # Merge AP + PA b0
    ap_pa_b0 = output_dir / "AP_PA_b0"
    run([cfg.fsl("fslmerge"), "-t", ap_pa_b0, nodif, nodif_PA])

    # TOPUP
    topup_out = output_dir / "topup_AP_PA_b0"
    topup_iout = output_dir / "topup_AP_PA_b0_iout"
    topup_fout = output_dir / "topup_AP_PA_b0_fout"
    run([
        cfg.fsl("topup"),
        f"--imain={ap_pa_b0}",
        f"--datain={acqparams}",
        f"--config={b02b0_config}",
        f"--out={topup_out}",
        f"--iout={topup_iout}",
        f"--fout={topup_fout}",
        "--verbose",
    ])

    # Mean of corrected b0
    hifi_nodif = output_dir / "hifi_nodif"
    run([cfg.fsl("fslmaths"), topup_iout, "-Tmean", hifi_nodif])

    # Brain mask
    hifi_brain = output_dir / "hifi_nodif_brain"
    run([cfg.fsl("bet"), hifi_nodif, hifi_brain, "-m", "-f", "0.2"])

    # Index file (one per volume)
    bvals = np.loadtxt(str(bval))
    idx = np.ones(len(bvals), dtype=int)
    idx_file = output_dir / "index.txt"
    np.savetxt(str(idx_file), idx, fmt="%d")

    # Eddy
    run([
        cfg.fsl("eddy_openmp"),
        f"--imain={dwi}",
        f"--mask={hifi_brain}_mask",
        f"--index={idx_file}",
        f"--acqp={acqparams}",
        f"--bvecs={bvec}",
        f"--bvals={bval}",
        "--fwhm=10,0,0,0,0",
        f"--topup={topup_out}",
        "--flm=quadratic",
        f"--out={output_dir / 'dwi_eddy'}",
        "--repol",
        "--cnr_maps",
        "--estimate_move_by_susceptibility",
        "--verbose",
    ])

    assert dwi_eddy.is_file(), f"Eddy failed: {dwi_eddy} not found"
    assert dwi_eddy_bvec.is_file(), f"Eddy failed: {dwi_eddy_bvec} not found"
    return {"dwi_eddy": dwi_eddy, "dwi_eddy_bvec": dwi_eddy_bvec}


# ── Private helpers ───────────────────────────────────────────────────

def _fslroi(cfg: Config, src: Path, dst: Path, t_min: int, t_size: int) -> None:
    """Extract a sub-volume with fslroi."""
    run([cfg.fsl("fslroi"), src, dst, str(t_min), str(t_size)])
