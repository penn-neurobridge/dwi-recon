"""DWI preprocessing pipeline orchestrator.

Core DWI pipeline that runs for EVERY subject: eddy correction,
registration, GQI reconstruction, fiber tracking, tract alignment,
and atlas-based structural connectivity.

This pipeline does NOT include iEEG connectivity — that is a separate
pipeline in ieeg_pipeline.py for subjects with implanted electrodes.
"""

from pathlib import Path
from timeit import default_timer as timer

from dwi_preprocessing.config import Config


class DWIPipeline:
    """Orchestrates per-subject DWI preprocessing and atlas connectivity.

    Parameters
    ----------
    bids_path : Path
        Root BIDS directory containing subject folders.
    cfg : Config
        Pipeline configuration (tool paths, env vars).
    """

    def __init__(self, bids_path: Path, cfg: Config | None = None):
        self.bids_path = Path(bids_path)
        self.cfg = cfg or Config()

    def run(
        self,
        subject: str,
        steps: list[str] | None = None,
        n_streamlines: int = 2_500_000,
    ) -> dict[str, Path]:
        """Run the DWI pipeline for a single subject.

        Parameters
        ----------
        subject : str
            Subject ID (e.g. "sub-RID1171").
        steps : list of str, optional
            Steps to execute. Default: all steps.
            Valid: "tracking", "alignment", "atlas".
        n_streamlines : int
            Total number of streamlines for fiber tracking.

        Returns
        -------
        dict mapping step names to output Paths.
        """
        if steps is None:
            steps = ["tracking", "alignment", "atlas"]

        deriv = self.bids_path / subject / "derivatives"
        assert deriv.is_dir(), f"Derivatives not found: {deriv}"

        paths = SubjectPaths(deriv)
        results: dict[str, Path] = {}

        if "tracking" in steps:
            results.update(self._run_tracking(paths, n_streamlines))

        if "alignment" in steps:
            results.update(self._run_alignment(paths))

        if "atlas" in steps:
            results.update(self._run_atlas(paths))

        return results

    # ── Step runners ──────────────────────────────────────────────────

    def _run_tracking(self, paths: "SubjectPaths", n_streamlines: int) -> dict[str, Path]:
        from dwi_preprocessing.tracking import fiber_tracking_ittr

        print("  [tracking] fiber_tracking_ittr (trk + trksubVox)...")
        start = timer()
        result = fiber_tracking_ittr(
            cfg=self.cfg,
            fib=paths.fib,
            output_dir=paths.dsi_studio_dir,
            n_streamlines=n_streamlines,
            save_trksubvox=True,
        )
        print(f"  [tracking] done in {timer() - start:.1f}s")
        return result

    def _run_alignment(self, paths: "SubjectPaths") -> dict[str, Path]:
        from dwi_preprocessing.alignment import align_tracts_to_t1

        print("  [alignment] align_tracts_to_t1...")
        start = timer()
        result = align_tracts_to_t1(
            freesurfer_dir=paths.freesurfer_dir,
            dwi_to_t1=paths.dwi_to_t1,
            fa_nii=paths.fa_nii,
            trk_h5=paths.trk_h5,
            output_dir=paths.tracts_to_t1_dir,
        )
        print(f"  [alignment] done in {timer() - start:.1f}s")
        return result

    def _run_atlas(self, paths: "SubjectPaths") -> dict[str, Path]:
        from dwi_preprocessing.atlas_connectivity import get_roi_coords, atlas_connectivity
        from dwi_preprocessing.tracking import fiber_tracking

        print("  [atlas] atlas connectivity...")
        start = timer()
        atlas_dir = self.cfg.repo_root / "atlas_lookuptable"

        # Ensure .trk.gz exists
        trk_gz = fiber_tracking(self.cfg, paths.fib)

        # Desikan-Killiany
        lut = atlas_dir / "desikanKilliany.csv"
        out = paths.deriv / "connectivityDWI" / "desikanKilliany"
        get_roi_coords(paths.freesurfer_dir, "aparc+aseg", lut, out, self.cfg)

        atlas_file = paths.freesurfer_dir / "mri" / "aparc+aseg.nii.gz"
        atlas_connectivity(
            self.cfg, paths.fib, trk_gz, paths.freesurfer_dir,
            "desikanKilliany", atlas_file, lut, out,
        )

        # Lausanne scales
        for scale in range(1, 6):
            name = f"lausanne2018scale{scale}"
            atlas_file = paths.freesurfer_dir / "mri" / f"lausanne2018.scale{scale}.nii.gz"
            lut = atlas_dir / f"{name}.csv"
            if atlas_file.is_file() and lut.is_file():
                out = paths.deriv / "connectivityDWI" / name
                atlas_connectivity(
                    self.cfg, paths.fib, trk_gz, paths.freesurfer_dir,
                    name, atlas_file, lut, out,
                )

        print(f"  [atlas] done in {timer() - start:.1f}s")
        return {"atlas": paths.deriv / "connectivityDWI"}


class SubjectPaths:
    """Resolves standard file paths within a subject's derivatives directory."""

    def __init__(self, deriv: Path):
        self.deriv = deriv
        self.freesurfer_dir = deriv / "freesurfer"
        self.dsi_studio_dir = deriv / "preprocessDWI" / "dsiStudio"
        self.tracts_to_t1_dir = deriv / "connectivityDWI" / "tracts_to_T1"

        # Find fib file
        fib_matches = sorted(self.dsi_studio_dir.glob("*gqi*fib.gz"))
        assert fib_matches, f"No fib.gz found in {self.dsi_studio_dir}"
        self.fib = fib_matches[0]
        self.fa_nii = Path(f"{self.fib}.dti_fa.nii.gz")

        # Registration
        self.dwi_to_t1 = deriv / "connectivityDWI" / "bbr2freesurferT1" / "dwi_to_t1.txt"

        # Tracking outputs
        self.trk_h5 = self.dsi_studio_dir / "whole_brain_trk.h5"
        self.subvox_h5 = self.dsi_studio_dir / "whole_brain_trksubVox.h5"

        # Alignment
        self.surfras_txt = self.tracts_to_t1_dir / "trk_to_t1surfRAS.txt"

        # iEEG (used by ieeg_pipeline, not by DWIPipeline)
        self.electrodes_csv = deriv / "ieeg_recon" / "module3" / "electrodes2ROI.csv"


def run_dwi_pipeline(
    subjects: list[str],
    bids_path: Path,
    steps: list[str] | None = None,
    config_path: Path | None = None,
    n_streamlines: int = 2_500_000,
) -> dict[str, dict[str, Path]]:
    """Run the core DWI pipeline for multiple subjects.

    Parameters
    ----------
    subjects : list of str
        Subject IDs (e.g. ["sub-RID0445", "sub-RID1171"]).
    bids_path : Path
        Root BIDS directory.
    steps : list of str, optional
        Steps to execute. Default: ["tracking", "alignment", "atlas"].
    config_path : Path, optional
        Path to setup_environment.json.
    n_streamlines : int
        Total streamlines for fiber tracking.

    Returns
    -------
    dict mapping subject IDs to their output paths.
    """
    cfg = Config(config_path) if config_path else Config()
    pipeline = DWIPipeline(bids_path, cfg)
    all_results: dict[str, dict[str, Path]] = {}

    for i, rid in enumerate(subjects):
        print(f"\n{'=' * 60}")
        print(f"Processing {rid} ({i + 1}/{len(subjects)})")
        print(f"{'=' * 60}")

        results = pipeline.run(rid, steps, n_streamlines)
        all_results[rid] = results

        print(f"  Done: {rid}")

    print(f"\n{'=' * 60}")
    print("All subjects complete")
    print(f"{'=' * 60}")

    return all_results
