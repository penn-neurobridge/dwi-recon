"""GQI reconstruction via DSI Studio.

Converts eddy-corrected DWI to SRC format, then reconstructs a GQI
fib file with scalar maps (QA, FA, MD, AD, RD).
"""

import glob
from pathlib import Path

from dwi_preprocessing.config import Config
from dwi_preprocessing.utils.shell import run


def nifti2src(
    cfg: Config,
    dwi_eddy: Path,
    bval: Path,
    bvec: Path,
    output_dir: Path,
) -> Path:
    """Convert eddy-corrected DWI to DSI Studio SRC format.

    Returns
    -------
    Path to the created .src.gz file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    dwi_src = output_dir / "dwi_eddy.src.gz"

    if dwi_src.is_file():
        print("  SRC already exists — skipping")
        return dwi_src

    run([
        cfg.dsi_studio,
        "--action=src",
        f"--source={dwi_eddy}",
        f"--bval={bval}",
        f"--bvec={bvec}",
        f"--output={dwi_src}",
    ])

    assert dwi_src.is_file(), f"SRC creation failed: {dwi_src}"
    return dwi_src


def src2gqi(
    cfg: Config,
    dwi_src: Path,
    brain_mask: Path,
    output_dir: Path,
) -> dict[str, Path]:
    """Reconstruct GQI fib file from SRC.

    Returns
    -------
    dict with keys: fib, qa, fa, md, ad, rd
    """
    fib_matches = sorted(output_dir.glob("*gqi*fib.gz"))

    if fib_matches:
        fib = fib_matches[0]
        fa = Path(f"{fib}.dti_fa.nii.gz")
        if fib.is_file() and fa.is_file():
            print("  GQI fib already exists — skipping")
            return _fib_paths(fib)

    run([
        cfg.dsi_studio,
        "--action=rec",
        f"--source={dwi_src}",
        "--method=4",
        "--param0=1.25",
        "--check_btable=1",
        "--align_acpc=0",
        f"--mask={brain_mask}",
        "--record_odf=0",
    ])

    fib_matches = sorted(output_dir.glob("*gqi*fib.gz"))
    assert fib_matches, "GQI reconstruction failed — no fib.gz found"
    fib = fib_matches[0]

    # Export scalar maps
    run([
        cfg.dsi_studio,
        "--action=exp",
        f"--source={fib}",
        "--export=qa,dti_fa,md,ad,rd",
    ])

    return _fib_paths(fib)


# ── Private helpers ───────────────────────────────────────────────────

def _fib_paths(fib: Path) -> dict[str, Path]:
    """Build the dict of scalar map paths from a fib file."""
    return {
        "fib": fib,
        "qa": Path(f"{fib}.qa.nii.gz"),
        "fa": Path(f"{fib}.dti_fa.nii.gz"),
        "md": Path(f"{fib}.md.nii.gz"),
        "ad": Path(f"{fib}.ad.nii.gz"),
        "rd": Path(f"{fib}.rd.nii.gz"),
    }
