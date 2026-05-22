"""Atlas-based structural connectivity via DSI Studio.

Computes region-to-region connectivity matrices using atlas parcellations
(Desikan-Killiany, Lausanne 2018 scales 1-5) and whole-brain tractography.
"""

import shutil
from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd

from dwi_preprocessing.config import Config
from dwi_preprocessing.utils.dsi import run_dsi
from dwi_preprocessing.utils.io import load_mat, mgz_to_nii, save_h5
from dwi_preprocessing.utils.surfaces import vox2ras_tkreg, vox2ras_0to1


def get_roi_coords(
    freesurfer_dir: Path,
    atlas_name: str,
    lookup_table: Path,
    output_dir: Path,
    cfg: Config | None = None,
) -> Path:
    """Extract ROI coordinates from a FreeSurfer atlas in surface RAS.

    Parameters
    ----------
    freesurfer_dir : Path
        FreeSurfer subject directory.
    atlas_name : str
        Atlas name (e.g. "aparc+aseg").
    lookup_table : Path
        CSV with columns roiNum, roi.
    output_dir : Path
        Output directory for atlas.h5.
    cfg : Config, optional
        Unused (kept for backward compatibility).

    Returns
    -------
    Path to atlas.h5
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    atlas_h5 = output_dir / "atlas.h5"

    if atlas_h5.is_file():
        print(f"  Atlas {atlas_name} already loaded — skipping")
        return atlas_h5

    # Convert atlas .mgz → .nii.gz if needed (nibabel, no FreeSurfer binary)
    mri_dir = freesurfer_dir / "mri"
    atlas_nii = mri_dir / f"{atlas_name}.nii.gz"
    if not atlas_nii.is_file():
        mgz_to_nii(mri_dir / f"{atlas_name}.mgz", atlas_nii)

    atlas_img = nib.load(str(atlas_nii))
    atlas_data = np.asarray(atlas_img.dataobj)
    lut = pd.read_csv(str(lookup_table))

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
    shape = atlas_img.shape[:3]
    zooms = atlas_img.header.get_zooms()[:3]
    tk_ras = vox2ras_0to1(vox2ras_tkreg(shape, zooms))

    coords_homo = np.hstack([voxels[:, :3], np.ones((len(voxels), 1))])
    surface_ras = (tk_ras @ coords_homo.T).T
    surface_ras[:, 3] = voxels[:, 3]  # Replace homogeneous coord with ROI number

    save_h5(atlas_h5, {
        "surfaceRAS": surface_ras,
        "lut_roiNum": lut["roiNum"].values,
        "lut_roi": np.array(lut["roi"].tolist(), dtype=object),
    })

    return atlas_h5


def atlas_connectivity(
    cfg: Config,
    fib: Path,
    trk_gz: Path,
    freesurfer_dir: Path,
    atlas_name: str,
    atlas_file: Path,
    lookup_table: Path,
    output_dir: Path,
) -> Path:
    """Run DSI Studio connectivity analysis for an atlas.

    Parameters
    ----------
    cfg : Config
        Pipeline configuration.
    fib : Path
        GQI fib (.fz) file.
    trk_gz : Path
        Whole-brain tract file (.tt.gz).
    freesurfer_dir : Path
        FreeSurfer subject directory.
    atlas_name : str
        Atlas identifier (e.g. "desikanKilliany").
    atlas_file : Path
        Atlas NIfTI volume.
    lookup_table : Path
        CSV with columns roiNum, roi.
    output_dir : Path
        Output directory for this atlas.

    Returns
    -------
    Path to connectivity.h5
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    conn_h5 = output_dir / "connectivity.h5"

    if conn_h5.is_file():
        print(f"  Atlas connectivity ({atlas_name}) already complete — skipping")
        return conn_h5

    lut = pd.read_csv(str(lookup_table))
    lut["label"] = lut["roi"]
    if "lausanne2018" in atlas_name:
        lut["roi"] = ["lausanne2018_" + str(n) for n in lut["roiNum"]]

    t1_nii = freesurfer_dir / "mri" / "T1.nii.gz"
    run_dsi(cfg, [
        "--action=ana",
        f"--source={fib}",
        f"--tract={trk_gz}",
        # Atlas (FreeSurfer T1 space) is registered to the FIB (DWI space)
        # using this reference volume. (Hou renamed --t1t2 to --other_slices.)
        f"--other_slices={t1_nii}",
        f"--connectivity={atlas_file}",
        # NB: the connectivity (ana) metrics use 'dti_fa', unlike exp/trk
        # which use 'fa'.
        "--connectivity_value=dti_fa,md,ad,rd,count,mean_length,qa",
        "--connectivity_type=end",
    ])

    # Move the combined connectivity .mat to raw_export
    fib_dir = fib.parent
    raw_dir = output_dir / "raw_export"
    raw_dir.mkdir(exist_ok=True)

    for f in fib_dir.glob("*.txt"):
        f.unlink()
    for f in fib_dir.glob("*connectivity*"):
        dest = raw_dir / f.name
        if dest.exists():
            dest.unlink()  # idempotent: overwrite leftovers from a prior run
        shutil.move(str(f), str(dest))

    # Parse and build connectivity matrices
    connectivity = _parse_dsi_studio_output(raw_dir, lut)
    save_h5(conn_h5, connectivity)

    return conn_h5


# ── Private helpers ───────────────────────────────────────────────────

# Map our metric names to DSI Studio "Hou" region-to-region matrix keys.
_R2R_KEYS = {
    "count": "number of tracts r2r",
    "length": "mean length(mm) r2r",
    "fa": "dti_fa r2r",
    "md": "md r2r",
    "ad": "ad r2r",
    "rd": "rd r2r",
    "qa": "qa r2r",
}


def _parse_dsi_studio_output(raw_dir: Path, lut: pd.DataFrame) -> dict:
    """Parse the combined DSI Studio connectivity .mat into metric matrices.

    The Hou release writes a single ``*.connectivity.mat`` containing, for
    each metric, a region-to-region matrix ``"<metric> r2r"`` and a
    tract-to-region vector ``"<metric> t2r"``, plus a ``name`` field (uint8
    byte array of region labels). We select and reorder rows/columns to
    match the lookup-table ROIs.
    """
    matches = sorted(raw_dir.glob("*connectivity*.mat"))
    assert matches, f"No connectivity .mat in {raw_dir}"
    d = load_mat(matches[0])

    labels = _decode_labels(d.get("name"))
    count_mat = np.asarray(d[_R2R_KEYS["count"]])

    if labels:
        idx = np.array(
            [labels.index(r) for r in lut["roi"] if r in labels], dtype=int
        )
    else:
        idx = np.array([], dtype=int)

    if idx.size == 0:
        # Fall back to the leading NxN block if labels could not be matched
        n = min(len(lut), count_mat.shape[0])
        idx = np.arange(n, dtype=int)

    result = {}
    for metric, key in _R2R_KEYS.items():
        mat = np.asarray(d[key])
        result[metric] = mat[np.ix_(idx, idx)]
    return result


def _decode_labels(names) -> list[str] | None:
    """Decode a DSI Studio ``name`` field into a list of region labels.

    The field may be a uint8 byte array (ASCII text), a string, bytes, or
    a string/object ndarray. Returns None if no names are available.
    """
    if names is None:
        return None

    if isinstance(names, np.ndarray):
        if names.dtype.kind in ("u", "i"):  # uint8/int byte array → ASCII text
            text = bytes(int(b) for b in names.ravel() if int(b) != 0).decode(
                "ascii", "replace"
            )
        else:  # already a string/object array
            return [str(n).strip() for n in names.ravel() if str(n).strip()]
    elif isinstance(names, (bytes, bytearray)):
        text = bytes(names).decode("ascii", "replace")
    elif isinstance(names, str):
        text = names
    else:
        return [str(n) for n in names]

    return [t for t in text.replace("\n", " ").split() if t and t != "\x00"]
