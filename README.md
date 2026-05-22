# DWI Minimum Preprocessing Pipeline

A Python pipeline for diffusion-weighted imaging (DWI) preprocessing, whole-brain fiber tracking, and structural connectivity analysis with specialized support for intracranial EEG (iEEG) electrode-level connectivity.

## Overview

This pipeline takes raw DWI data through eddy/distortion correction, GQI reconstruction, whole-brain tractography, and connectivity analysis at both atlas and electrode levels. It wraps **FSL** and **FreeSurfer** command-line tools and the **Dockerized DSI Studio** (pinned version) in a reproducible Python workflow. Each subject is its own dataset (`primary/` raw BIDS + `derivatives/` outputs).

See [PIPELINE.md](PIPELINE.md) for detailed flowcharts of each processing stage, and [API_REFERENCE.md](API_REFERENCE.md) for the Python API.

## Features

- Eddy current and susceptibility distortion correction (FSL topup + eddy)
- EPI-to-T1 boundary-based registration (FSL epi_reg)
- GQI reconstruction and whole-brain fiber tracking via **Dockerized DSI Studio** (pinned, platform-independent)
- Iterative tractography with per-streamline diffusion metrics (QA, FA, MD, AD, RD)
- Atlas-based structural connectivity (Desikan-Killiany, Lausanne 2018 scales 1-5)
- iEEG electrode-level structural connectivity with grey-to-white matter projection
- HDF5 (`.h5`) outputs throughout
- Multiprocess (loky) parallelism for the per-tract iEEG edge search (MATLAB `parpool` equivalent)

## Installation

### Prerequisites

| Software | Version | Purpose |
|---|---|---|
| [FSL](https://fsl.fmrib.ox.ac.uk/fsl/) | 6.0+ | Eddy correction, registration, brain extraction |
| [FreeSurfer](https://surfer.nmr.mgh.harvard.edu/) | 7.0+ (8.1.0 recommended) | Surface reconstruction, parcellation |
| [Docker](https://www.docker.com/) | Latest | Runs DSI Studio (no local install needed) |
| DSI Studio | `dsistudio/dsistudio:hou-2026-05-17` (pinned, auto-pulled) | GQI reconstruction, fiber tracking, connectivity |
| Python | 3.13+ | Pipeline runtime |
| [uv](https://docs.astral.sh/uv/) | Latest | Package manager |

> **DSI Studio runs in Docker** — you do not need a local install. The pinned
> image is `dsistudio/dsistudio:hou-2026-05-17` (set in `config.py`). On Apple
> Silicon it runs under `linux/amd64` emulation automatically. To use a local
> binary instead, set `"dsiStudioMode": "local"` and `"dsiStudio": "/path/to/dsi_studio"`
> in `setup_environment.json`.

### Setup

```bash
# Clone the repository
git clone https://github.com/penn-neurobridge/dwi_minimum_preprocessing.git
cd dwi_minimum_preprocessing

# Install Python dependencies
uv sync

# Configure tool paths
cp setup_environment.json.example setup_environment.json
# Edit setup_environment.json with your local paths (see below)
```

### Configuration

Create `setup_environment.json` in the repository root (this file is gitignored):

```json
{
    "FSLDIR": "/path/to/fsl",
    "FSLOUTPUTTYPE": "NIFTI_GZ",
    "FREESURFER_HOME": "/path/to/freesurfer/8.1.0/",
    "SUBJECTS_DIR": "/path/to/bids/data",
    "freeSurferLoc": "/path/to/freesurfer/8.1.0/bin",
    "fslLoc": "/path/to/fsl/bin",
    "dsiStudioMode": "docker",
    "FS_LICENSE": "/path/to/freesurfer/license.txt",
    "SURFER_FRONTDOOR": "1",
    "dockerSynb0disco": "sudo /usr/local/bin/docker",
    "singularityLoc": " "
}
```

DSI Studio keys (all optional — sensible defaults in `config.py`):

| Key | Default | Meaning |
|---|---|---|
| `dsiStudioMode` | `docker` | `docker` (pinned image) or `local` (binary) |
| `dsiStudioDocker` | `dsistudio/dsistudio:hou-2026-05-17` | image tag when mode=docker |
| `dsiStudio` | — | path to local `dsi_studio` when mode=local |
| `dockerCmd` | `docker` | docker executable |
| `dockerPlatform` | auto (`linux/amd64` on arm64) | platform flag |

## Usage

This repository provides **two separate pipelines**:

| Pipeline | Command | Runs on |
|---|---|---|
| **DWI preprocessing** | `dwi-preprocess` | All subjects (tracking, alignment, atlas connectivity) |
| **iEEG connectivity** | `dwi-ieeg-connectivity` | Only subjects with implanted electrodes |

Each subject is its own **dataset directory** containing `primary/`
(raw BIDS) and `derivatives/` (outputs). Point the tools at the dataset
root with `-i/--dataset-path`.

### 1. DWI Preprocessing (all subjects)

```bash
# Full DWI pipeline on one dataset
uv run dwi-preprocess -i /path/to/PennEPI000

# Multiple datasets (comma-separated)
uv run dwi-preprocess -i /path/to/PennEPI000,/path/to/PennEPI001

# Only tracking + alignment (skip eddy/register/reconstruct/atlas)
uv run dwi-preprocess -i /path/to/PennEPI000 --steps tracking,alignment

# Custom streamline count
uv run dwi-preprocess -i /path/to/PennEPI000 --n-streamlines 5000000
```

| Step | Description |
|---|---|
| `eddy` | TOPUP + eddy distortion/motion correction (FSL) |
| `register` | EPI-to-T1 boundary-based registration (FSL epi_reg) |
| `reconstruct` | NIFTI → SRC → GQI fib (DSI Studio) |
| `tracking` | Iterative fiber tracking (10 x 250K streamlines) with per-point metric export |
| `alignment` | Compute tract-to-T1 surface RAS transformation + QC |
| `atlas` | Atlas-based connectivity matrices (Desikan-Killiany + Lausanne) |

### 2. iEEG Connectivity (electrode datasets only)

Requires the DWI pipeline to have run first. Datasets without
`derivatives/ieeg_recon/module3/electrodes2ROI.csv` are auto-skipped.

```bash
# Default (3mm + 5mm spheres)
uv run dwi-ieeg-connectivity -i /path/to/PennEPI001

# Multiple datasets, custom sphere diameters
uv run dwi-ieeg-connectivity -i /path/to/PennEPI001,/path/to/PennEPI004 \
    --sphere-diameters 3,5,10
```

Run either command with `--help` for the full Typer-generated help.

### Python API

```python
from pathlib import Path
from dwi_preprocessing import Config, DWIPipeline, IEEGPipeline, run_dwi_pipeline, run_ieeg_pipeline

# ── DWI pipeline ──
run_dwi_pipeline(dataset_paths=[Path("/path/to/PennEPI000")])

# ── iEEG pipeline (electrode datasets only) ──
run_ieeg_pipeline(dataset_paths=[Path("/path/to/PennEPI001")], sphere_diameters=[3, 5])

# ── Use individual modules directly ──
from dwi_preprocessing.tracking import fiber_tracking_ittr
from dwi_preprocessing.ieeg_connectivity import ieeg_grey2white, make_edge_list

cfg = Config()
result = fiber_tracking_ittr(cfg, fib=Path("..."), output_dir=Path("..."), save_trksubvox=True)
electrodes = ieeg_grey2white(freesurfer_dir=Path("..."), electrodes_csv=Path("..."), output_dir=Path("..."))
```

## Expected Directory Layout

Each subject is a self-contained dataset (Penn-Neurobridge layout): raw
data under `primary/sub-<ID>/`, all pipeline outputs directly under
`derivatives/` (not nested per-subject).

```
<dataset>/                  # e.g. PennEPI000
  primary/
    sub-PennEPIxxx/
      sub-PennEPIxxx_sessions.tsv
      ses-preimplant/
        anat/   # *_T1w.nii.gz, *_T2w, *_FLAIR
        dwi/    # *_dwi.nii.gz, .bval, .bvec, .json
        fmap/   # *_dir-AP_epi (reversed PE), magnitude1/2, phasediff
      ses-postimplant/        # (iEEG subjects) ct/, ieeg/
  derivatives/              # outputs sit directly here (no sub-<ID> layer)
    freesurfer/             # FreeSurfer recon-all output (input)
      mri/                  # T1.mgz, wm.mgz, brain.mgz, aparc+aseg.mgz
      surf/                 # lh.pial, rh.pial, lh.white, rh.white
    preprocessDWI/
      topupEddy/            # Eddy-corrected DWI
      dsiStudio/            # dwi_eddy.sz, *.gqi.fz, whole_brain_trk.h5, whole_brain_trksubVox.h5
    connectivityDWI/
      bbr2freesurferT1/     # DWI-to-T1 registration (dwi_to_t1.txt)
      tracts_to_T1/         # trk_to_t1surfRAS.txt transform + check_alignment.png
      desikanKilliany/      # Atlas connectivity matrices (connectivity.h5)
      lausanne2018scale*/
    ieeg_recon/             # (iEEG subjects) electrode reconstruction
      module3/
        electrodes2ROI.csv  # Electrode coordinates + ROI assignments
    connectivityIEEG/       # Output: edge lists, connectivity matrices
```

## Output Files (HDF5)

All outputs use HDF5 format (`.h5`) for efficient storage and cross-language compatibility.

### Fiber Tracking
- `whole_brain_trk.h5` — `trk/{cord, length, start_idx, end_idx, qa, fa, md, ad, rd}`
- `whole_brain_trksubVox.h5` — `trksubVox/{qa, fa, md, ad, rd}` per-point along each streamline

### Atlas Connectivity
- `connectivity.h5` — `{count, fa, md, ad, rd, qa, length}` as NxN matrices

### iEEG Connectivity
- `electrodes_surf_proj.csv` — Electrodes with grey-to-white matter projected coordinates
- `edgeList_{d}mmSph.csv` — Per-tract edges between electrode pairs within d mm sphere
- `connectivity.h5` — Per-subject HDF5 with groups:
  - `ieeg/{coordinate, labels}` — Electrode metadata
  - `ieeg-atlas-dkt/{roi, roi_fsnum}` — Atlas ROI assignments
  - `ieeg-sc-{d}mmSph/{ad, count, fa, length, md, qa, rd}` — NxN connectivity matrices

## Repository Structure

```
dwi_minimum_preprocessing/
  run_dwi_preprocessing.py      # CLI: dwi-preprocess (all subjects)
  run_ieeg_connectivity.py      # CLI: dwi-ieeg-connectivity (electrode subjects)
  dwi_preprocessing/            # Python package (primary)
    __init__.py                 # Exports: DWIPipeline, IEEGPipeline, run_*, Config
    config.py                   # Config loader; pinned DSI Studio Docker image
    pipeline.py                 # DWIPipeline: eddy→register→reconstruct→tracking→alignment→atlas; SubjectPaths
    ieeg_pipeline.py            # IEEGPipeline: electrode-level connectivity
    eddy.py                     # Eddy/distortion correction + acqparams (FSL)
    registration.py             # EPI-to-T1 BBR registration (FSL epi_reg)
    reconstruction.py           # NIFTI → SRC(.sz) → GQI(.gqi.fz) (DSI Studio)
    tracking.py                 # Fiber tracking: single + iterative (DSI Studio)
    alignment.py                # Tract-to-T1 surface RAS alignment + plotly QC
    atlas_connectivity.py       # Atlas-based structural connectivity
    ieeg_connectivity.py        # iEEG connectivity (multiprocess edge search)
    utils/
      dsi.py                    # DSI Studio runner (Docker or local binary)
      shell.py                  # Subprocess helper (list-style commands)
      io.py                     # HDF5 I/O + legacy .mat loading
      surfaces.py               # FreeSurfer surface + coordinate utilities
      geometry.py               # Point-in-mesh tests (trimesh)
  matlab/                       # Legacy MATLAB implementation
    preprocessDWI.m             # Original preprocessing class
    iEEGsc.m                    # Original iEEG connectivity class
    mainConnectivity.m          # Full pipeline wrapper
    mainConnectivityIEEG.m      # iEEG-specific wrapper
    mainEddy.m                  # Eddy correction wrapper
    dependencies/               # MATLAB helper functions
  atlas_lookuptable/            # Parcellation lookup tables + annotation files
  pyproject.toml                # uv / pip project configuration
  uv.lock                       # Locked dependency versions
  setup_environment.json        # Machine-specific tool paths (gitignored)
  PIPELINE.md                   # Pipeline flowcharts and documentation
  LICENSE                       # MIT License
```

## MATLAB (Legacy)

The original MATLAB implementation is preserved in `matlab/`. To use it:

```matlab
addpath('matlab');
addpath('matlab/dependencies');

% Load configuration
subject = preprocessDWI();

% Run full pipeline
mainConnectivity(subjects, BIDS_path, dwi_repo_path);

% Run iEEG connectivity only
mainConnectivityIEEG(subjects, BIDS_path, dwi_repo_path);
```

Requires MATLAB R2019b+ with Statistics and Machine Learning Toolbox and Parallel Computing Toolbox.

## Author

Nishant Sinha

## License

MIT License - See [LICENSE](LICENSE) for details.
