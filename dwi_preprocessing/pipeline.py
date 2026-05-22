"""DWI preprocessing pipeline orchestrator.

Core DWI pipeline that runs for EVERY subject. Full chain:
  eddy -> register -> reconstruct -> tracking -> alignment -> atlas

Raw inputs are read from a "primary" BIDS root; all outputs are written
to a separate "derivatives" root. FreeSurfer recon-all output is expected
to already exist under the derivatives root.

This pipeline does NOT include iEEG connectivity — that is a separate
pipeline in ieeg_pipeline.py for subjects with implanted electrodes.
"""

from pathlib import Path
from timeit import default_timer as timer

from dwi_preprocessing.config import Config

# Steps in canonical execution order
ALL_STEPS = ["eddy", "register", "reconstruct", "tracking", "alignment", "atlas"]


class DWIPipeline:
    """Orchestrates per-subject DWI preprocessing and atlas connectivity.

    Parameters
    ----------
    primary_path : Path
        BIDS "primary" root containing <subject>/ses-preimplant/{dwi,fmap,anat}.
    derivatives_path : Path
        Derivatives root containing <subject>/{freesurfer,preprocessDWI,...}.
    cfg : Config
        Pipeline configuration (tool paths, env vars).
    """

    def __init__(
        self,
        primary_path: Path,
        derivatives_path: Path,
        cfg: Config | None = None,
    ):
        self.primary_path = Path(primary_path)
        self.derivatives_path = Path(derivatives_path)
        self.cfg = cfg or Config()

    def run(
        self,
        subject: str,
        steps: list[str] | None = None,
        n_streamlines: int = 2_500_000,
    ) -> dict:
        """Run the DWI pipeline for a single subject.

        Parameters
        ----------
        subject : str
            Subject ID (e.g. "sub-PennEPIxxx").
        steps : list of str, optional
            Steps to execute. Default: all steps.
            Valid: eddy, register, reconstruct, tracking, alignment, atlas.
        n_streamlines : int
            Total number of streamlines for fiber tracking.

        Returns
        -------
        dict of accumulated step outputs (paths threaded between steps).
        """
        if steps is None:
            steps = list(ALL_STEPS)

        paths = SubjectPaths(self.primary_path, self.derivatives_path, subject)

        # Threaded data dict (mirrors MATLAB data_for_tracking)
        data: dict = {"n_streamlines": n_streamlines}

        if "eddy" in steps:
            data.update(self._run_eddy(paths))
        if "register" in steps:
            data.update(self._run_register(paths, data))
        if "reconstruct" in steps:
            data.update(self._run_reconstruct(paths, data))
        if "tracking" in steps:
            data.update(self._run_tracking(paths, data))
        if "alignment" in steps:
            data.update(self._run_alignment(paths, data))
        if "atlas" in steps:
            data.update(self._run_atlas(paths, data))

        return data

    # ── Step runners ──────────────────────────────────────────────────

    def _run_eddy(self, paths: "SubjectPaths") -> dict:
        from dwi_preprocessing.eddy import prepare_acqparams, topup_eddy

        print("  [eddy] topup + eddy correction...")
        start = timer()
        acqparams = prepare_acqparams(paths.dwi_json, paths.topup_eddy_dir)
        b02b0 = self.cfg.repo_root / "matlab" / "dependencies" / "b02b0_1.cnf"
        result = topup_eddy(
            cfg=self.cfg,
            dwi=paths.dwi,
            dwi_reversed=paths.fmap_reversed,
            bval=paths.bval,
            bvec=paths.bvec,
            acqparams=acqparams,
            b02b0_config=b02b0,
            output_dir=paths.topup_eddy_dir,
        )
        print(f"  [eddy] done in {timer() - start:.1f}s")
        return result

    def _run_register(self, paths: "SubjectPaths", data: dict) -> dict:
        from dwi_preprocessing.registration import register_epi2t1

        print("  [register] EPI-to-T1 (BBR)...")
        start = timer()
        dwi_eddy = data.get("dwi_eddy", paths.dwi_eddy)
        result = register_epi2t1(
            cfg=self.cfg,
            dwi_eddy=dwi_eddy,
            freesurfer_dir=paths.freesurfer_dir,
            output_dir=paths.bbr_dir,
        )
        print(f"  [register] done in {timer() - start:.1f}s")
        return result

    def _run_reconstruct(self, paths: "SubjectPaths", data: dict) -> dict:
        from dwi_preprocessing.reconstruction import nifti2src, src2gqi

        print("  [reconstruct] NIFTI -> SRC -> GQI...")
        start = timer()
        dwi_eddy = data.get("dwi_eddy", paths.dwi_eddy)
        dwi_eddy_bvec = data.get("dwi_eddy_bvec", paths.dwi_eddy_bvec)
        brain_mask = data.get("b0_brain_mask", paths.b0_brain_mask)

        dwi_src = nifti2src(
            cfg=self.cfg, dwi_eddy=dwi_eddy, bval=paths.bval,
            bvec=dwi_eddy_bvec, output_dir=paths.dsi_studio_dir,
        )
        fib = src2gqi(
            cfg=self.cfg, dwi_src=dwi_src, brain_mask=brain_mask,
            output_dir=paths.dsi_studio_dir,
        )
        print(f"  [reconstruct] done in {timer() - start:.1f}s")
        return {"dwi_src": dwi_src, **fib}

    def _run_tracking(self, paths: "SubjectPaths", data: dict) -> dict:
        from dwi_preprocessing.tracking import fiber_tracking_ittr

        print("  [tracking] fiber_tracking_ittr (trk + trksubVox)...")
        start = timer()
        fib = data.get("fib") or paths.find_fib()
        result = fiber_tracking_ittr(
            cfg=self.cfg,
            fib=fib,
            output_dir=paths.dsi_studio_dir,
            n_streamlines=data.get("n_streamlines", 2_500_000),
            save_trksubvox=True,
        )
        print(f"  [tracking] done in {timer() - start:.1f}s")
        return result

    def _run_alignment(self, paths: "SubjectPaths", data: dict) -> dict:
        from dwi_preprocessing.alignment import align_tracts_to_t1

        print("  [alignment] align_tracts_to_t1...")
        start = timer()
        fib = data.get("fib") or paths.find_fib()
        result = align_tracts_to_t1(
            freesurfer_dir=paths.freesurfer_dir,
            dwi_to_t1=data.get("dwi_to_t1", paths.dwi_to_t1),
            fa_nii=Path(f"{fib}.dti_fa.nii.gz"),
            trk_h5=data.get("trk", paths.trk_h5),
            output_dir=paths.tracts_to_t1_dir,
        )
        print(f"  [alignment] done in {timer() - start:.1f}s")
        return result

    def _run_atlas(self, paths: "SubjectPaths", data: dict) -> dict:
        from dwi_preprocessing.atlas_connectivity import get_roi_coords, atlas_connectivity
        from dwi_preprocessing.tracking import fiber_tracking

        print("  [atlas] atlas connectivity...")
        start = timer()
        atlas_dir = self.cfg.repo_root / "atlas_lookuptable"
        fib = data.get("fib") or paths.find_fib()

        # Ensure .trk.gz exists
        trk_gz = fiber_tracking(self.cfg, fib)

        # Desikan-Killiany
        lut = atlas_dir / "desikanKilliany.csv"
        out = paths.deriv / "connectivityDWI" / "desikanKilliany"
        get_roi_coords(paths.freesurfer_dir, "aparc+aseg", lut, out, self.cfg)

        atlas_file = paths.freesurfer_dir / "mri" / "aparc+aseg.nii.gz"
        atlas_connectivity(
            self.cfg, fib, trk_gz, paths.freesurfer_dir,
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
                    self.cfg, fib, trk_gz, paths.freesurfer_dir,
                    name, atlas_file, lut, out,
                )

        print(f"  [atlas] done in {timer() - start:.1f}s")
        return {"trk_gz": trk_gz, "atlas": paths.deriv / "connectivityDWI"}


class SubjectPaths:
    """Resolves raw inputs (primary root) and outputs (derivatives root).

    Layout::

        <primary_root>/<subject>/ses-preimplant/{dwi,fmap,anat}/...
        <derivatives_root>/<subject>/{freesurfer,preprocessDWI,connectivityDWI}/...
    """

    def __init__(self, primary_root: Path, deriv_root: Path, subject: str,
                 session: str = "ses-preimplant"):
        self.subject = subject
        self.primary = Path(primary_root) / subject / session
        self.deriv = Path(deriv_root) / subject

        # ── Raw inputs (primary) ──
        self.dwi = self._one(self.primary / "dwi", "*_dwi.nii.gz")
        self.bval = self._one(self.primary / "dwi", "*_dwi.bval")
        self.bvec = self._one(self.primary / "dwi", "*_dwi.bvec")
        self.dwi_json = self._one(self.primary / "dwi", "*_dwi.json")
        self.fmap_reversed = self._one(self.primary / "fmap", "*dir-AP_epi.nii.gz")
        self.t1 = self._one(self.primary / "anat", "*_T1w.nii.gz")

        # ── Derivative directories ──
        self.freesurfer_dir = self.deriv / "freesurfer"
        self.topup_eddy_dir = self.deriv / "preprocessDWI" / "topupEddy"
        self.dsi_studio_dir = self.deriv / "preprocessDWI" / "dsiStudio"
        self.bbr_dir = self.deriv / "connectivityDWI" / "bbr2freesurferT1"
        self.tracts_to_t1_dir = self.deriv / "connectivityDWI" / "tracts_to_T1"

        # ── Expected output products ──
        self.dwi_eddy = self.topup_eddy_dir / "dwi_eddy.nii.gz"
        self.dwi_eddy_bvec = self.topup_eddy_dir / "dwi_eddy.eddy_rotated_bvecs"
        self.dwi_to_t1 = self.bbr_dir / "dwi_to_t1.txt"
        self.b0_brain_mask = self.bbr_dir / "dwi_eddy.b0.gz.brain_mask.nii.gz"
        self.trk_h5 = self.dsi_studio_dir / "whole_brain_trk.h5"
        self.subvox_h5 = self.dsi_studio_dir / "whole_brain_trksubVox.h5"
        self.surfras_txt = self.tracts_to_t1_dir / "trk_to_t1surfRAS.txt"

        # ── iEEG (used by ieeg_pipeline) ──
        self.electrodes_csv = self.deriv / "ieeg_recon" / "module3" / "electrodes2ROI.csv"

    def find_fib(self) -> Path:
        """Locate the GQI fib.gz in the dsiStudio directory."""
        matches = sorted(self.dsi_studio_dir.glob("*gqi*fib.gz"))
        assert matches, f"No fib.gz found in {self.dsi_studio_dir}"
        return matches[0]

    @property
    def fa_nii(self) -> Path:
        return Path(f"{self.find_fib()}.dti_fa.nii.gz")

    @staticmethod
    def _one(directory: Path, pattern: str) -> Path:
        """Return the single file matching pattern (raises if 0 or many)."""
        matches = sorted(directory.glob(pattern))
        if not matches:
            raise FileNotFoundError(f"No file matching {pattern} in {directory}")
        return matches[0]


def run_dwi_pipeline(
    subjects: list[str],
    primary_path: Path,
    derivatives_path: Path,
    steps: list[str] | None = None,
    config_path: Path | None = None,
    n_streamlines: int = 2_500_000,
) -> dict[str, dict]:
    """Run the core DWI pipeline for multiple subjects.

    Parameters
    ----------
    subjects : list of str
        Subject IDs (e.g. ["sub-PennEPIxxx", "sub-PennEPIyyy"]).
    primary_path : Path
        BIDS primary root (raw inputs).
    derivatives_path : Path
        Derivatives root (outputs).
    steps : list of str, optional
        Steps to execute. Default: all six.
    config_path : Path, optional
        Path to setup_environment.json.
    n_streamlines : int
        Total streamlines for fiber tracking.

    Returns
    -------
    dict mapping subject IDs to their output dicts.
    """
    cfg = Config(config_path) if config_path else Config()
    pipeline = DWIPipeline(primary_path, derivatives_path, cfg)
    all_results: dict[str, dict] = {}

    for i, rid in enumerate(subjects):
        print(f"\n{'=' * 60}")
        print(f"Processing {rid} ({i + 1}/{len(subjects)})")
        print(f"{'=' * 60}")

        all_results[rid] = pipeline.run(rid, steps, n_streamlines)

        print(f"  Done: {rid}")

    print(f"\n{'=' * 60}")
    print("All subjects complete")
    print(f"{'=' * 60}")

    return all_results
