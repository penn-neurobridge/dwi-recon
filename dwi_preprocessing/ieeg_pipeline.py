"""iEEG structural connectivity pipeline.

Separate pipeline for subjects with implanted electrodes. Requires
the core DWI pipeline to have already run (tracking + alignment).

This pipeline:
  1. Projects cortical electrodes from grey to white matter surface
  2. Builds per-tract edge lists between electrode pairs
  3. Aggregates into symmetric connectivity matrices (per sphere diameter)
"""

from pathlib import Path
from timeit import default_timer as timer

from dwi_preprocessing.config import Config
from dwi_preprocessing.pipeline import SubjectPaths


class IEEGPipeline:
    """Orchestrates iEEG structural connectivity for a single subject dataset.

    Parameters
    ----------
    cfg : Config
        Pipeline configuration (tool paths, env vars).
    """

    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or Config()

    def run(
        self,
        dataset_path: Path,
        sphere_diameters: list[float] | None = None,
        n_streamlines: int = 2_500_000,
    ) -> dict[str, Path]:
        """Run iEEG connectivity for a single subject dataset.

        Prerequisites: the core DWI pipeline must have produced
        whole_brain_trk.h5, whole_brain_trksubVox.h5, and
        trk_to_t1surfRAS.txt for this subject.

        Parameters
        ----------
        dataset_path : Path
            Dataset root containing primary/ and derivatives/.
        sphere_diameters : list of float
            Sphere diameters in mm (default: [3, 5]).
        n_streamlines : int
            Used only if tracking needs to be re-run.

        Returns
        -------
        dict with key "connectivity" → Path to connectivity.h5
        """
        if sphere_diameters is None:
            sphere_diameters = [3.0, 5.0]

        paths = SubjectPaths(dataset_path)

        # Validate: electrodes must exist
        if not paths.electrodes_csv.is_file():
            print(f"  SKIP {paths.subject} — no electrodes2ROI.csv")
            return {}

        # Validate: DWI pipeline must have run
        self._ensure_dwi_outputs(paths, n_streamlines)

        return self._run_ieeg(paths, sphere_diameters)

    # ── Internal ──────────────────────────────────────────────────────

    def _ensure_dwi_outputs(self, paths: SubjectPaths, n_streamlines: int) -> None:
        """Check that required DWI outputs exist, run them if missing."""
        from dwi_preprocessing.tracking import fiber_tracking_ittr
        from dwi_preprocessing.alignment import align_tracts_to_t1

        if not paths.trk_h5.is_file() or not paths.subvox_h5.is_file():
            print("  DWI tracking outputs missing — running fiber_tracking_ittr...")
            fiber_tracking_ittr(
                self.cfg, paths.find_fib(), paths.dsi_studio_dir,
                n_streamlines=n_streamlines, save_trksubvox=True,
            )

        if not paths.surfras_txt.is_file():
            print("  Tract-to-T1 alignment missing — running align_tracts_to_t1...")
            align_tracts_to_t1(
                paths.freesurfer_dir, paths.dwi_to_t1,
                paths.fa_nii, paths.trk_h5, paths.tracts_to_t1_dir,
            )

    def _run_ieeg(
        self,
        paths: SubjectPaths,
        sphere_diameters: list[float],
    ) -> dict[str, Path]:
        from dwi_preprocessing.ieeg_connectivity import (
            ieeg_grey2white,
            make_edge_list,
            make_connectivity_matrix,
        )

        print("  [ieeg] iEEG structural connectivity...")
        start = timer()

        ieeg_dir = paths.deriv / "connectivityIEEG"
        electrodes = ieeg_grey2white(
            paths.freesurfer_dir, paths.electrodes_csv, ieeg_dir,
        )

        conn_h5 = None
        for dia in sphere_diameters:
            edge_list = make_edge_list(
                electrodes, dia,
                paths.trk_h5, paths.subvox_h5, paths.surfras_txt,
                ieeg_dir,
            )
            conn_h5 = make_connectivity_matrix(
                edge_list, dia, paths.electrodes_csv, ieeg_dir,
            )

        print(f"  [ieeg] done in {timer() - start:.1f}s")
        return {"connectivity": conn_h5} if conn_h5 else {}


def run_ieeg_pipeline(
    dataset_paths: list[Path],
    config_path: Path | None = None,
    sphere_diameters: list[float] | None = None,
    n_streamlines: int = 2_500_000,
) -> dict[str, dict[str, Path]]:
    """Run iEEG connectivity for one or more subject datasets.

    Datasets without electrodes2ROI.csv are automatically skipped.

    Parameters
    ----------
    dataset_paths : list of Path
        Dataset roots, each containing primary/ and derivatives/.
    config_path : Path, optional
        Path to setup_environment.json.
    sphere_diameters : list of float, optional
        Sphere diameters in mm (default: [3, 5]).
    n_streamlines : int
        Streamline count if tracking needs to re-run.

    Returns
    -------
    dict mapping subject IDs to their output paths.
    """
    cfg = Config(config_path) if config_path else Config()
    pipeline = IEEGPipeline(cfg)
    all_results: dict[str, dict[str, Path]] = {}

    for i, ds in enumerate(dataset_paths):
        ds = Path(ds)
        print(f"\n{'=' * 60}")
        print(f"iEEG connectivity: {ds.name} ({i + 1}/{len(dataset_paths)})")
        print(f"{'=' * 60}")

        all_results[ds.name] = pipeline.run(ds, sphere_diameters, n_streamlines)

        print(f"  Done: {ds.name}")

    print(f"\n{'=' * 60}")
    print("All datasets complete")
    print(f"{'=' * 60}")

    return all_results
