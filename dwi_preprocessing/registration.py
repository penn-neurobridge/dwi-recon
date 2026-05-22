"""EPI-to-T1 registration via boundary-based registration.

Wraps FSL epi_reg to register DWI b0 to FreeSurfer T1 space.
"""

import shutil
from pathlib import Path

from dwi_preprocessing.config import Config
from dwi_preprocessing.utils.io import mgz_to_nii
from dwi_preprocessing.utils.shell import run


def register_epi2t1(
    cfg: Config,
    dwi_eddy: Path,
    freesurfer_dir: Path,
    output_dir: Path,
) -> dict[str, Path]:
    """Register EPI (DWI b0) to FreeSurfer T1 using epi_reg.

    Parameters
    ----------
    cfg : Config
        Pipeline configuration with tool paths.
    dwi_eddy : Path
        Eddy-corrected DWI volume.
    freesurfer_dir : Path
        FreeSurfer subject directory (containing mri/, surf/).
    output_dir : Path
        Output directory (e.g. derivatives/connectivityDWI/bbr2freesurferT1).

    Returns
    -------
    dict with keys: dwi_to_t1, b0, b0_brain, b0_brain_mask
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dwi_to_t1 = output_dir / "dwi_to_t1.txt"
    b0 = output_dir / "dwi_eddy.b0.gz.nii.gz"
    b0_brain = output_dir / "dwi_eddy.b0.gz.brain.nii.gz"
    b0_brain_mask = output_dir / "dwi_eddy.b0.gz.brain_mask.nii.gz"

    if all(p.is_file() for p in [dwi_to_t1, b0, b0_brain, b0_brain_mask]):
        print("  EPI-to-T1 registration already complete — skipping")
        return {
            "dwi_to_t1": dwi_to_t1,
            "b0": b0,
            "b0_brain": b0_brain,
            "b0_brain_mask": b0_brain_mask,
        }

    # Extract b0
    run([cfg.fsl("fslroi"), dwi_eddy, b0, "0", "1"])

    # Brain extraction
    run([cfg.fsl("bet"), b0, b0_brain, "-m", "-f", "0.1"])

    # Convert FreeSurfer volumes to NIfTI
    mri_dir = freesurfer_dir / "mri"
    for vol in ("wm", "T1", "brain"):
        mgz_to_nii(mri_dir / f"{vol}.mgz", mri_dir / f"{vol}.nii.gz")

    wm_nii = mri_dir / "wm.nii.gz"
    t1_nii = mri_dir / "T1.nii.gz"
    brain_nii = mri_dir / "brain.nii.gz"

    # Binarise white matter
    wmbin = output_dir / "wmbin.nii.gz"
    run([cfg.fsl("fslmaths"), wm_nii, "-bin", wmbin])

    # BBR registration
    dwi_to_t1_base = output_dir / "dwi_to_t1"
    run([
        cfg.fsl("epi_reg"),
        f"--epi={b0}",
        f"--t1={t1_nii}",
        f"--t1brain={brain_nii}",
        f"--out={dwi_to_t1_base}",
        f"--wmseg={wmbin}",
        "-v",
    ])

    # Copy .mat → .txt
    shutil.copy2(str(dwi_to_t1_base) + ".mat", str(dwi_to_t1))

    return {
        "dwi_to_t1": dwi_to_t1,
        "b0": b0,
        "b0_brain": b0_brain,
        "b0_brain_mask": b0_brain_mask,
    }
