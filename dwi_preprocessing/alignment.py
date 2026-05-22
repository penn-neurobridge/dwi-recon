"""Tract-to-T1 surface RAS alignment.

Computes the 4x4 transformation matrix that maps DSI Studio tract
coordinates into FreeSurfer T1 surface RAS space.
"""

from pathlib import Path

import nibabel as nib
import numpy as np

from dwi_preprocessing.utils.surfaces import vox2ras_tkreg, vox2ras_0to1


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
    n_points: int = 8000,
) -> None:
    """Render transformed tracts over the FreeSurfer pial surface.

    Produces an interactive ``check_alignment.html`` and a static
    ``check_alignment.png``. The pial surfaces (lh/rh) and the transformed
    tract coordinates share the same FreeSurfer surface-RAS space.

    Uses plotly Mesh3d for the surfaces (same style as ieeg-recon) and
    Scatter3d for a subsample of tract points.
    """
    try:
        import h5py
        import plotly.graph_objects as go
        from nibabel.freesurfer.io import read_geometry

        # Subsampled tract points — read strided directly to stay low-memory
        with h5py.File(str(trk_h5), "r") as f:
            cord_ds = f["trk"]["cord"]
            n_cols = cord_ds.shape[1]
            step = max(1, n_cols // n_points)
            cord_sub = cord_ds[:, ::step]  # (4, ~n_points)
        pts = xform @ cord_sub  # (4, ~n_points), in surface RAS

        # Pial surfaces (native endianness for plotly)
        lpv, lpf = read_geometry(str(freesurfer_dir / "surf" / "lh.pial"))
        rpv, rpf = read_geometry(str(freesurfer_dir / "surf" / "rh.pial"))

        fig = go.Figure()
        for verts, faces, name in [(lpv, lpf, "Left pial"), (rpv, rpf, "Right pial")]:
            verts = np.asarray(verts, dtype=np.float64)
            faces = np.asarray(faces, dtype=np.int64)
            fig.add_trace(go.Mesh3d(
                x=verts[:, 0], y=verts[:, 1], z=verts[:, 2],
                i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
                color="#b0b0b0", opacity=0.25, flatshading=False,
                lighting=dict(ambient=0.45, diffuse=0.8, specular=0.2, roughness=0.6),
                lightposition=dict(x=100, y=200, z=150),
                name=name, showscale=False, hoverinfo="skip",
            ))

        fig.add_trace(go.Scatter3d(
            x=pts[0], y=pts[1], z=pts[2],
            mode="markers",
            marker=dict(size=1.5, color="#1f77b4", opacity=0.5),
            name="Tracts", hoverinfo="skip",
        ))

        fig.update_layout(
            title="Tract-to-T1 alignment QC",
            scene=dict(
                xaxis=dict(visible=False, showgrid=False, showbackground=False),
                yaxis=dict(visible=False, showgrid=False, showbackground=False),
                zaxis=dict(visible=False, showgrid=False, showbackground=False),
                aspectmode="data",
                camera=dict(
                    up=dict(x=0, y=1, z=0),
                    center=dict(x=0, y=0, z=0),
                    eye=dict(x=0, y=0, z=2.2),  # superior (top-down) view
                ),
                bgcolor="white",
            ),
            paper_bgcolor="white",
            margin=dict(r=0, l=0, b=0, t=30),
            showlegend=True,
        )

        fig.write_html(str(output_dir / "check_alignment.html"))
        try:
            fig.write_image(
                str(output_dir / "check_alignment.png"),
                width=900, height=800, scale=2,
            )
        except Exception as e:
            print(f"  PNG export skipped (needs kaleido): {e}")
    except Exception as e:
        print(f"  QC plot skipped: {e}")
