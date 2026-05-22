"""Tract-to-T1 surface RAS alignment.

Computes the 4x4 transformation matrix that maps DSI Studio tract
coordinates into FreeSurfer T1 surface RAS space.
"""

from pathlib import Path

import nibabel as nib
import numpy as np

from dwi_preprocessing.utils.io import load_h5
from dwi_preprocessing.utils.surfaces import read_surf, vox2ras_tkreg, vox2ras_0to1


def align_tracts_to_t1(
    freesurfer_dir: Path,
    dwi_to_t1: Path,
    fa_nii: Path,
    trk_h5: Path,
    output_dir: Path,
) -> dict[str, Path]:
    """Compute and save the tract-to-T1-surfaceRAS transform.

    Parameters
    ----------
    freesurfer_dir : Path
        FreeSurfer subject directory.
    dwi_to_t1 : Path
        4x4 DWI-to-T1 registration matrix (.txt).
    fa_nii : Path
        DWI FA NIfTI (for voxel dimensions).
    trk_h5 : Path
        whole_brain_trk.h5 (for QC plot).
    output_dir : Path
        Output directory (e.g. connectivityDWI/tracts_to_T1).

    Returns
    -------
    dict with keys: surfras, vox
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    surfras_file = output_dir / "trk_to_t1surfRAS.txt"
    vox_file = output_dir / "trk_to_t1Vox.txt"

    if surfras_file.is_file() and vox_file.is_file():
        print("  Tract-to-T1 alignment already complete — skipping")
        return {"surfras": surfras_file, "vox": vox_file}

    # Load T1 geometry
    t1_nii_path = freesurfer_dir / "mri" / "T1.nii.gz"
    t1_img = nib.load(str(t1_nii_path))
    t1_shape = t1_img.shape[:3]
    t1_zooms = t1_img.header.get_zooms()[:3]
    t1surfRAS = vox2ras_0to1(vox2ras_tkreg(t1_shape, t1_zooms))

    # Load DWI FA geometry
    fa_img = nib.load(str(fa_nii))
    fa_shape = fa_img.shape[:3]
    fa_zooms = fa_img.header.get_zooms()[:3]

    # Load registration matrix
    dwi2t1 = np.loadtxt(str(dwi_to_t1))

    # Build transformation chain
    trk_to_t1Vox, trk_to_t1surfRAS = _build_transform(
        fa_shape, fa_zooms, t1_zooms, dwi2t1, t1surfRAS
    )

    np.savetxt(str(vox_file), trk_to_t1Vox, fmt="%.10f")
    np.savetxt(str(surfras_file), trk_to_t1surfRAS, fmt="%.10f")

    # QC plot
    _make_qc_plot(trk_h5, trk_to_t1surfRAS, freesurfer_dir, output_dir)

    return {"surfras": surfras_file, "vox": vox_file}


# ── Private helpers ───────────────────────────────────────────────────

def _build_transform(
    fa_shape: tuple,
    fa_zooms: tuple,
    t1_zooms: tuple,
    dwi2t1: np.ndarray,
    t1surfRAS: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Build the full tract-to-T1 transformation chain."""
    # Flip anterior-posterior axis
    T_AP = np.eye(4)
    T_AP[1, 1] = -1
    T_AP[1, 3] = fa_shape[1] - 1

    # Scale by voxel dimensions
    sizeMat = np.diag([fa_zooms[0], fa_zooms[1], fa_zooms[2], 1.0])
    sizeMatT1 = np.diag([1.0 / t1_zooms[0], 1.0 / t1_zooms[1], 1.0 / t1_zooms[2], 1.0])

    trk_to_t1Vox = sizeMatT1 @ dwi2t1 @ sizeMat @ T_AP
    trk_to_t1surfRAS = t1surfRAS @ trk_to_t1Vox

    return trk_to_t1Vox, trk_to_t1surfRAS


def _make_qc_plot(
    trk_h5: Path,
    xform: np.ndarray,
    freesurfer_dir: Path,
    output_dir: Path,
) -> None:
    """Generate a QC overlay of transformed tracts on pial surfaces."""
    try:
        import matplotlib.pyplot as plt

        trk_data = load_h5(trk_h5, group="trk")
        cord = trk_data["cord"]
        transformed = xform @ cord

        lpv, _ = read_surf(str(freesurfer_dir / "surf" / "lh.pial"))
        rpv, _ = read_surf(str(freesurfer_dir / "surf" / "rh.pial"))

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

        plt.savefig(str(output_dir / "check_alignment.png"), dpi=150)
        plt.close()
    except Exception as e:
        print(f"  QC plot skipped: {e}")
