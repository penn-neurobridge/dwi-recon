# API Reference

Python API for the `dwi_preprocessing` package. All paths are
`pathlib.Path`. See [PIPELINE.md](PIPELINE.md) for the conceptual flow and
[README.md](README.md) for installation and CLI usage.

## Contents

- [Quick start](#quick-start)
- [Top-level](#top-level)
  - [`Config`](#config)
  - [`DWIPipeline`](#dwipipeline) / [`run_dwi_pipeline`](#run_dwi_pipeline)
  - [`IEEGPipeline`](#ieegpipeline) / [`run_ieeg_pipeline`](#run_ieeg_pipeline)
  - [`SubjectPaths`](#subjectpaths)
- [Processing modules](#processing-modules)
  - [`eddy`](#eddy) · [`registration`](#registration) · [`reconstruction`](#reconstruction)
  - [`tracking`](#tracking) · [`alignment`](#alignment)
  - [`atlas_connectivity`](#atlas_connectivity) · [`ieeg_connectivity`](#ieeg_connectivity)
- [Utilities](#utilities)
  - [`utils.dsi`](#utilsdsi) · [`utils.io`](#utilsio) · [`utils.surfaces`](#utilssurfaces)
  - [`utils.geometry`](#utilsgeometry) · [`utils.shell`](#utilsshell)

---

## Quick start

```python
from pathlib import Path
from dwi_preprocessing import (
    Config, DWIPipeline, IEEGPipeline, run_dwi_pipeline, run_ieeg_pipeline,
)

# Run the full DWI pipeline on a dataset
run_dwi_pipeline(dataset_paths=[Path("/data/PennEPI000")])

# Run iEEG connectivity (electrode subjects only)
run_ieeg_pipeline(dataset_paths=[Path("/data/PennEPI001")], sphere_diameters=[3, 5])

# Or drive a single subject with the class API
cfg = Config()
DWIPipeline(cfg).run(Path("/data/PennEPI000"), steps=["tracking", "alignment"])
```

A **dataset** directory contains `primary/sub-<ID>/ses-preimplant/...` (raw
BIDS inputs) and `derivatives/...` (outputs, written directly — not nested
under the subject).

---

## Top-level

Importable from `dwi_preprocessing`:
`Config`, `DWIPipeline`, `IEEGPipeline`, `run_dwi_pipeline`, `run_ieeg_pipeline`.

### `Config`

`dwi_preprocessing.config.Config`

Loads `setup_environment.json` and sets FSL/FreeSurfer environment variables
on construction.

```python
Config(config_path: str | Path | None = None)
```

- **config_path** — path to `setup_environment.json`. Defaults to
  `<repo_root>/setup_environment.json`.

**Methods**

| Method | Returns | Description |
|---|---|---|
| `fsl(tool: str) -> str` | path | Full path to an FSL tool, e.g. `cfg.fsl("topup")` |
| `fs(tool: str) -> str` | path | Full path to a FreeSurfer tool, e.g. `cfg.fs("mri_convert")` |

**Key attributes**

| Attribute | Description |
|---|---|
| `repo_root` | Directory containing the config file |
| `fsl_loc`, `freesurfer_loc` | Tool `bin` directories |
| `dsi_use_docker` | `True` if DSI Studio runs via Docker (default) |
| `dsi_studio_image` | Pinned Docker image (default `DEFAULT_DSI_STUDIO_IMAGE`) |
| `dsi_studio` | Local DSI Studio binary path (when `dsiStudioMode="local"`) |
| `docker_cmd` | Docker executable (default `"docker"`) |
| `docker_platform` | e.g. `"linux/amd64"` (auto on Apple Silicon) |

Module constant: `DEFAULT_DSI_STUDIO_IMAGE = "dsistudio/dsistudio:hou-2026-05-17"`.

Config keys (all DSI Studio keys optional): `FSLDIR`, `FSLOUTPUTTYPE`,
`FREESURFER_HOME`, `SUBJECTS_DIR`, `freeSurferLoc`, `fslLoc`, `FS_LICENSE`,
`dsiStudioMode` (`docker`|`local`), `dsiStudioDocker`, `dsiStudio`,
`dockerCmd`, `dockerPlatform`.

---

### `DWIPipeline`

`dwi_preprocessing.pipeline.DWIPipeline`

Orchestrates the core DWI pipeline for one subject dataset.

```python
DWIPipeline(cfg: Config | None = None)

.run(dataset_path: Path,
     steps: list[str] | None = None,
     n_streamlines: int = 2_500_000) -> dict
```

- **dataset_path** — dataset root (contains `primary/` and `derivatives/`).
- **steps** — subset of
  `["eddy", "register", "reconstruct", "tracking", "alignment", "atlas"]`
  (default: all). Available as `dwi_preprocessing.pipeline.ALL_STEPS`.
- **n_streamlines** — total streamlines for fiber tracking (10 iterations).
- **Returns** — dict of accumulated step outputs (paths), threaded between
  steps.

### `run_dwi_pipeline`

```python
run_dwi_pipeline(dataset_paths: list[Path],
                 steps: list[str] | None = None,
                 config_path: Path | None = None,
                 n_streamlines: int = 2_500_000) -> dict[str, dict]
```

Convenience wrapper: builds a `Config` and runs `DWIPipeline` over each
dataset. Returns `{dataset_name: result_dict}`.

---

### `IEEGPipeline`

`dwi_preprocessing.ieeg_pipeline.IEEGPipeline`

Electrode-level structural connectivity for one subject dataset. Requires
the DWI pipeline to have produced `whole_brain_trk.h5`,
`whole_brain_trksubVox.h5`, and `trk_to_t1surfRAS.txt`. Missing DWI
prerequisites are run automatically.

```python
IEEGPipeline(cfg: Config | None = None)

.run(dataset_path: Path,
     sphere_diameters: list[float] | None = None,  # default [3.0, 5.0]
     n_streamlines: int = 2_500_000) -> dict[str, Path]
```

Datasets without `derivatives/ieeg_recon/module3/electrodes2ROI.csv` are
skipped (returns `{}`). Otherwise returns `{"connectivity": <connectivity.h5>}`.

### `run_ieeg_pipeline`

```python
run_ieeg_pipeline(dataset_paths: list[Path],
                  config_path: Path | None = None,
                  sphere_diameters: list[float] | None = None,
                  n_streamlines: int = 2_500_000) -> dict[str, dict[str, Path]]
```

---

### `SubjectPaths`

`dwi_preprocessing.pipeline.SubjectPaths`

Resolves all input/output paths within a dataset. The single `sub-*`
directory under `primary/` is auto-detected.

```python
SubjectPaths(dataset_path: Path, session: str = "ses-preimplant")
```

**Methods / properties**

| Member | Description |
|---|---|
| `find_fib() -> Path` | Locate the GQI fib (`*.fz`) in `dsiStudio/` |
| `fa_nii` (property) | `<fib>.fa.nii.gz` |

**Resolved attributes**

| Attribute | Path |
|---|---|
| `subject` | auto-detected `sub-<ID>` |
| `dwi`, `bval`, `bvec`, `dwi_json` | `primary/sub-<ID>/<session>/dwi/*` |
| `fmap_reversed` | `…/fmap/*dir-AP_epi.nii.gz` |
| `t1` | `…/anat/*_T1w.nii.gz` |
| `deriv` | `<dataset>/derivatives` |
| `freesurfer_dir` | `derivatives/freesurfer` |
| `topup_eddy_dir`, `dsi_studio_dir` | `derivatives/preprocessDWI/{topupEddy,dsiStudio}` |
| `bbr_dir`, `tracts_to_t1_dir` | `derivatives/connectivityDWI/{bbr2freesurferT1,tracts_to_T1}` |
| `dwi_eddy`, `dwi_eddy_bvec` | eddy outputs |
| `dwi_to_t1`, `b0_brain_mask` | registration outputs |
| `trk_h5`, `subvox_h5`, `surfras_txt` | tracking/alignment outputs |
| `electrodes_csv` | `derivatives/ieeg_recon/module3/electrodes2ROI.csv` |

---

## Processing modules

Each stage is a standalone function so it can be called directly. All
DSI Studio calls route through [`utils.dsi.run_dsi`](#utilsdsi).

### `eddy`

`dwi_preprocessing.eddy`

```python
prepare_acqparams(dwi_json: Path, output_dir: Path) -> Path
```
Writes `acqparams.txt` from the DWI JSON `PhaseEncodingDirection` +
`TotalReadoutTime`. Returns the file path.

```python
topup_eddy(cfg: Config, dwi: Path, dwi_reversed: Path,
           bval: Path, bvec: Path, acqparams: Path,
           b02b0_config: Path, output_dir: Path) -> dict[str, Path]
```
FSL TOPUP + eddy. The eddy binary is auto-detected
(`eddy_cpu`/`eddy_openmp`/`eddy`). Returns
`{"dwi_eddy", "dwi_eddy_bvec"}`.

### `registration`

`dwi_preprocessing.registration`

```python
register_epi2t1(cfg: Config, dwi_eddy: Path,
                freesurfer_dir: Path, output_dir: Path) -> dict[str, Path]
```
EPI-to-T1 boundary-based registration (FSL `epi_reg`). Returns
`{"dwi_to_t1", "b0", "b0_brain", "b0_brain_mask"}`.

### `reconstruction`

`dwi_preprocessing.reconstruction`

```python
nifti2src(cfg: Config, dwi_eddy: Path, bval: Path, bvec: Path,
          output_dir: Path) -> Path
```
DWI → DSI Studio SRC (`.sz`). Returns the `.sz` path.

```python
src2gqi(cfg: Config, dwi_src: Path, brain_mask: Path,
        output_dir: Path) -> dict[str, Path]
```
SRC → GQI fib (`.gqi.fz`) + scalar maps. Returns
`{"fib", "qa", "fa", "md", "ad", "rd"}`.

### `tracking`

`dwi_preprocessing.tracking`

```python
fiber_tracking(cfg: Config, fib: Path,
               n_streamlines: int = 2_500_000) -> Path
```
Single-pass whole-brain tracking. Returns the `.tt.gz` path (used by atlas
connectivity).

```python
fiber_tracking_ittr(cfg: Config, fib: Path, output_dir: Path,
                    n_streamlines: int = 2_500_000,
                    save_trksubvox: bool = False) -> dict[str, Path]
```
10-iteration tracking with per-point metric export; concatenates and saves
`whole_brain_trk.h5` (and `whole_brain_trksubVox.h5` if `save_trksubvox`).
Returns `{"trk", "trksubvox"?}`.

### `alignment`

`dwi_preprocessing.alignment`

```python
align_tracts_to_t1(freesurfer_dir: Path, dwi_to_t1: Path, fa_nii: Path,
                   trk_h5: Path, output_dir: Path) -> dict[str, Path]
```
Computes the tract→T1-surface-RAS transform and writes a plotly QC
(`check_alignment.html` + `.png`). Returns `{"surfras", "vox"}`.

### `atlas_connectivity`

`dwi_preprocessing.atlas_connectivity`

```python
get_roi_coords(freesurfer_dir: Path, atlas_name: str, lookup_table: Path,
               output_dir: Path, cfg: Config | None = None) -> Path
```
Extracts ROI surface-RAS coordinates from a FreeSurfer atlas → `atlas.h5`.

```python
atlas_connectivity(cfg: Config, fib: Path, trk_gz: Path, freesurfer_dir: Path,
                   atlas_name: str, atlas_file: Path, lookup_table: Path,
                   output_dir: Path) -> Path
```
Runs DSI Studio `--action=ana`, parses the combined `.connectivity.mat`, and
writes `connectivity.h5` with `{count, fa, md, ad, rd, qa, length}` matrices.

### `ieeg_connectivity`

`dwi_preprocessing.ieeg_connectivity`

```python
ieeg_grey2white(freesurfer_dir: Path, electrodes_csv: Path,
                output_dir: Path) -> pandas.DataFrame
```
Projects cortical electrodes onto the white-matter surface. Caches/returns
the projected electrode table (`electrodes_surf_proj.csv`).

```python
make_edge_list(electrodes: DataFrame, sphere_dia: float, trk_h5: Path,
               subvox_h5: Path, surfras_txt: Path, output_dir: Path) -> DataFrame
```
Finds tracts within `sphere_dia` of electrode pairs (multiprocess over tract
chunks; large arrays memory-mapped across workers). Columns:
`roi1, roi2, length, qa, fa, md, ad, rd, trkindx`.

```python
make_connectivity_matrix(edge_list: DataFrame, sphere_dia: float,
                         electrodes_csv: Path, output_dir: Path) -> Path
```
Aggregates the edge list into symmetric per-metric matrices and writes them
into `connectivity.h5` under group `ieeg-sc-{int(sphere_dia)}mmSph`
(alongside `ieeg/` and `ieeg-atlas-dkt/`). Returns the `connectivity.h5` path.

---

## Utilities

### `utils.dsi`

`dwi_preprocessing.utils.dsi`

```python
run_dsi(cfg: Config, args: list[str], extra_mounts: list[Path] | None = None) -> None
```
Runs a DSI Studio command, either as a local binary or in the pinned Docker
image. `args` are the DSI Studio arguments only (no executable), e.g.
`["--action=src", "--source=/abs/path", ...]`. In Docker mode, host
directories referenced in `args` are bind-mounted at identical paths; pass
`extra_mounts` for directories not referenced directly.

### `utils.io`

`dwi_preprocessing.utils.io`

```python
save_h5(path: Path, data: dict) -> None
```
Save a (one-level-nested) dict to HDF5. Top-level dict values become groups;
numpy arrays become datasets (string/object arrays stored as variable-length
UTF-8).

```python
load_h5(path: Path, group: str | None = None) -> dict
```
Load an HDF5 file (or a single `group`) into a nested dict of numpy arrays.

```python
load_mat(path: Path, variable: str | None = None)
```
Load a `.mat` file (auto-detects v5 via scipy and v7.3/HDF5 via h5py). Used
for DSI Studio `.mat` exports. Returns a dict (or a single `variable`).

### `utils.surfaces`

`dwi_preprocessing.utils.surfaces`

```python
read_surf(surf_path: str) -> tuple[np.ndarray, np.ndarray]   # (vertices, faces)
vox2ras_tkreg(image_size: tuple, pixel_dims: tuple) -> np.ndarray   # 4x4
vox2ras_0to1(M: np.ndarray) -> np.ndarray                          # 4x4
```
FreeSurfer surface reading (via nibabel) and tkreg voxel→RAS matrices used by
the tract alignment.

### `utils.geometry`

`dwi_preprocessing.utils.geometry`

```python
inpolyhedron(vertices: np.ndarray, faces: np.ndarray,
             points: np.ndarray) -> np.ndarray   # (P,) bool
```
Point-in-mesh test via `trimesh` (requires `rtree`). Used to decide whether
electrodes lie inside the white-matter surface.

### `utils.shell`

`dwi_preprocessing.utils.shell`

```python
run(cmd: list[str | Path], log_path: Path | None = None, **kwargs) -> None
```
Run an external command as an argument list (never `shell=True`), logging the
command. Path objects are stringified. `kwargs` are forwarded to
`subprocess.run`.
