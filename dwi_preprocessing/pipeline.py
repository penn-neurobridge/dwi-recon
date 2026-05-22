"""DWI preprocessing pipeline orchestrator.

Coordinates the full processing chain from eddy correction through
iEEG structural connectivity. Each step delegates to its own module.
"""

from pathlib import Path
from timeit import default_timer as timer

from dwi_preprocessing.config import Config


class DWIPipeline:
    """Orchestrates per-subject DWI preprocessing and connectivity.

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
        steps: list[str],
        n_streamlines: int = 2_500_000,
        sphere_diameters: list[float] | None = None,
    ) -> dict[str, Path]:
        """Run the pipeline for a single subject.

        Parameters
        ----------
        subject : str
            Subject ID (e.g. "sub-RID1171").
        steps : list of str
            Steps to execute: "tracking", "alignment", "atlas", "ieeg".
        n_streamlines : int
            Total number of streamlines for fiber tracking.
        sphere_diameters : list of float
            Sphere diameters for iEEG connectivity (default: [3, 5]).

        Returns
        -------
        dict mapping step names to output Paths.
        """
        if sphere_diameters is None:
            sphere_diameters = [3.0, 5.0]

        deriv = self.bids_path / subject / "derivatives"
        assert deriv.is_dir(), f"Derivatives not found: {deriv}"

        paths = SubjectPaths(deriv, self.cfg)
        results: dict[str, Path] = {}

        if "tracking" in steps:
            results.update(self._run_tracking(paths, n_streamlines))

        if "alignment" in steps:
            results.update(self._run_alignment(paths))

        if "atlas" in steps:
            results.update(self._run_atlas(paths))

        if "ieeg" in steps:
            results.update(self._run_ieeg(paths, n_streamlines, sphere_diameters))

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

    def _run_ieeg(
        self,
        paths: "SubjectPaths",
        n_streamlines: int,
        sphere_diameters: list[float],
    ) -> dict[str, Path]:
        from dwi_preprocessing.ieeg_connectivity import (
            ieeg_grey2white,
            make_edge_list,
            make_connectivity_matrix,
        )
        from dwi_preprocessing.tracking import fiber_tracking_ittr
        from dwi_preprocessing.alignment import align_tracts_to_t1

        ieeg_csv = paths.electrodes_csv
        if not ieeg_csv.is_file():
            print("  Skipping iEEG — electrodes2ROI.csv not found")
            return {}

        # Ensure tracking + alignment
        if not paths.trk_h5.is_file() or not paths.subvox_h5.is_file():
            print("  Running fiber tracking (trk + trksubVox)...")
            fiber_tracking_ittr(
                self.cfg, paths.fib, paths.dsi_studio_dir,
                n_streamlines=n_streamlines, save_trksubvox=True,
            )

        if not paths.surfras_txt.is_file():
            print("  Running tract-to-T1 alignment...")
            align_tracts_to_t1(
                paths.freesurfer_dir, paths.dwi_to_t1,
                paths.fa_nii, paths.trk_h5, paths.tracts_to_t1_dir,
            )

        print("  [ieeg] iEEG connectivity...")
        start = timer()
        ieeg_dir = paths.deriv / "connectivityIEEG"

        electrodes = ieeg_grey2white(paths.freesurfer_dir, ieeg_csv, ieeg_dir)

        conn_h5 = None
        for dia in sphere_diameters:
            edge_list = make_edge_list(
                electrodes, dia,
                paths.trk_h5, paths.subvox_h5, paths.surfras_txt,
                ieeg_dir,
            )
            conn_h5 = make_connectivity_matrix(
                edge_list, dia, ieeg_csv, ieeg_dir,
            )

        print(f"  [ieeg] done in {timer() - start:.1f}s")
        return {"ieeg_connectivity": conn_h5} if conn_h5 else {}


class SubjectPaths:
    """Resolves standard file paths within a subject's derivatives directory."""

    def __init__(self, deriv: Path, cfg: Config):
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

        # iEEG
        self.electrodes_csv = deriv / "ieeg_recon" / "module3" / "electrodes2ROI.csv"


def run_pipeline(
    subjects: list[str],
    bids_path: Path,
    steps: list[str],
    config_path: Path | None = None,
    n_streamlines: int = 2_500_000,
    sphere_diameters: list[float] | None = None,
) -> dict[str, dict[str, Path]]:
    """Run the full pipeline for multiple subjects.

    Parameters
    ----------
    subjects : list of str
        Subject IDs (e.g. ["sub-RID0445", "sub-RID1171"]).
    bids_path : Path
        Root BIDS directory.
    steps : list of str
        Steps to execute.
    config_path : Path, optional
        Path to setup_environment.json.
    n_streamlines : int
        Total streamlines for fiber tracking.
    sphere_diameters : list of float, optional
        Sphere diameters for iEEG connectivity.

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

        results = pipeline.run(rid, steps, n_streamlines, sphere_diameters)
        all_results[rid] = results

        print(f"  Done: {rid}")

    print(f"\n{'=' * 60}")
    print("All subjects complete")
    print(f"{'=' * 60}")

    return all_results
