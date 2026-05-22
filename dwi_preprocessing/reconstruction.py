"""GQI reconstruction via DSI Studio.

Converts eddy-corrected DWI to SRC format, then reconstructs a GQI
fib file with scalar maps (QA, FA, MD, AD, RD).

Uses the DSI Studio "Hou" (2026+) file formats and CLI:
  SRC = .sz, FIB = .gqi.fz, scalar maps = <fib>.<metric>.nii.gz.
The diffusivity metrics (fa, ad, rd, md) are only stored in the fib when
requested via --other_output at reconstruction time.
"""

from pathlib import Path

from dwi_preprocessing.config import Config
from dwi_preprocessing.utils.dsi import run_dsi

# Scalar metrics stored in the fib and exported as NIfTI
_METRICS = ("fa", "ad", "rd", "md", "qa")


def nifti2src(
    cfg: Config,
    dwi_eddy: Path,
    bval: Path,
    bvec: Path,
    output_dir: Path,
) -> Path:
    """Convert eddy-corrected DWI to DSI Studio SRC format (.sz).

    Returns
    -------
    Path to the created .sz file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    dwi_src = output_dir / "dwi_eddy.sz"

    if dwi_src.is_file():
        print("  SRC already exists — skipping")
        return dwi_src

    run_dsi(cfg, [
        "--action=src",
        f"--source={dwi_eddy}",
        f"--bval={bval}",
        f"--bvec={bvec}",
        f"--output={dwi_src}",
    ])

    matches = sorted(output_dir.glob("dwi_eddy*.sz"))
    assert matches, f"SRC creation failed: no .sz in {output_dir}"
    return matches[0]


def src2gqi(
    cfg: Config,
    dwi_src: Path,
    brain_mask: Path,
    output_dir: Path,
) -> dict[str, Path]:
    """Reconstruct GQI fib (.fz) from SRC and export scalar maps.

    Returns
    -------
    dict with keys: fib, qa, fa, md, ad, rd
    """
    fib_matches = sorted(output_dir.glob("*.fz"))

    if fib_matches:
        fib = fib_matches[0]
        fa = Path(f"{fib}.fa.nii.gz")
        if fib.is_file() and fa.is_file():
            print("  GQI fib already exists — skipping")
            return _fib_paths(fib)

    run_dsi(cfg, [
        "--action=rec",
        f"--source={dwi_src}",
        "--method=4",
        "--param=1.25",
        f"--mask={brain_mask}",
        f"--other_output={','.join(_METRICS)}",
        "--record_odf=0",
    ])

    fib_matches = sorted(output_dir.glob("*.fz"))
    assert fib_matches, "GQI reconstruction failed — no .fz found"
    fib = fib_matches[0]

    # Export scalar maps as NIfTI
    run_dsi(cfg, [
        "--action=exp",
        f"--source={fib}",
        f"--export={','.join(_METRICS)}",
    ])

    return _fib_paths(fib)


# ── Private helpers ───────────────────────────────────────────────────

def _fib_paths(fib: Path) -> dict[str, Path]:
    """Build the dict of scalar map paths from a fib file."""
    return {
        "fib": fib,
        "qa": Path(f"{fib}.qa.nii.gz"),
        "fa": Path(f"{fib}.fa.nii.gz"),
        "md": Path(f"{fib}.md.nii.gz"),
        "ad": Path(f"{fib}.ad.nii.gz"),
        "rd": Path(f"{fib}.rd.nii.gz"),
    }
