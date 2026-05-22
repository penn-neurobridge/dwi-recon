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
from dwi_preprocessing.utils.io import load_mat, save_h5
from dwi_preprocessing.utils.shell import run
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
        For mri_convert (only needed if .mgz → .nii.gz conversion required).

    Returns
    -------
    Path to atlas.h5
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    atlas_h5 = output_dir / "atlas.h5"

    if atlas_h5.is_file():
        print(f"  Atlas {atlas_name} already loaded — skipping")
        return atlas_h5

    # Convert atlas if needed
    mri_dir = freesurfer_dir / "mri"
    atlas_nii = mri_dir / f"{atlas_name}.nii.gz"
    if not atlas_nii.is_file() and cfg is not None:
        atlas_mgz = mri_dir / f"{atlas_name}.mgz"
        run([cfg.fs("mri_convert"), atlas_mgz, atlas_nii])

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
        GQI fib.gz file.
    trk_gz : Path
        Whole-brain .trk.gz file.
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
    run([
        cfg.dsi_studio,
        "--action=ana",
        f"--source={fib}",
        f"--tract={trk_gz}",
        f"--t1t2={t1_nii}",
        f"--connectivity={atlas_file}",
        "--connectivity_value=dti_fa,md,ad,rd,count,mean_length,qa",
        "--connectivity_type=end",
        "--connectivity_threshold=0",
    ])

    # Move raw DSI Studio output files
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

def _parse_dsi_studio_output(raw_dir: Path, lut: pd.DataFrame) -> dict:
    """Parse DSI Studio connectivity exports into a dict of matrices.

    DSI Studio writes one .connectivity.mat per metric, each containing
    a square ``connectivity`` matrix and a ``name`` field. The ``name``
    field is a uint8 byte array of newline/space-separated region labels.
    We select and order the rows/columns to match the lookup table ROIs.
    """

    def _load_conn(pattern: str):
        matches = sorted(raw_dir.glob(pattern))
        assert matches, f"No file matching {pattern} in {raw_dir}"
        d = load_mat(matches[0])
        return d["connectivity"], d.get("name", None)

    count_mat, names = _load_conn("*.count.*")
    labels = _decode_labels(names)

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

    result = {"count": count_mat[np.ix_(idx, idx)]}

    for metric, pattern in [
        ("fa", "*.dti_fa.*"),
        ("length", "*.mean_length.*"),
        ("md", "*.md.*"),
        ("ad", "*.ad.*"),
        ("rd", "*.rd.*"),
        ("qa", "*.qa.*"),
    ]:
        mat, _ = _load_conn(pattern)
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
