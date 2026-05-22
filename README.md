# DWI Processing and iEEG Reconstruction Pipeline

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

## Running with Docker (recommended — self-contained, AWS-ready)

The easiest and most portable way to run the pipeline is the prebuilt
Docker image. It bundles **everything** — FSL (eddy/topup/bet/flirt),
DSI Studio, and the Python project — so there are no local installs and no
docker-in-docker. FreeSurfer is **not** required at runtime (`.mgz` volumes
are read with nibabel; you supply existing `recon-all` output as input).

```bash
# Build (amd64; on Apple Silicon add --platform linux/amd64)
docker build -t dwi-recon .

# Run the DWI pipeline on a dataset (mount the dataset at /data)
docker run --rm -v /local/path/PennEPI000:/data dwi-recon dwi  -i /data

# Run iEEG connectivity (electrode subjects)
docker run --rm -v /local/path/PennEPI001:/data dwi-recon ieeg -i /data
```

The image's entrypoint is `run_dwi_recon.py` with two subcommands, `dwi`
and `ieeg` (run `docker run --rm dwi-recon --help`). A dataset is a directory
containing `primary/` and `derivatives/` (see [layout](#expected-directory-layout)).

The image is **amd64-only** (DSI Studio ships x86_64) — it runs natively on
AWS/x86 and under emulation on Apple Silicon.

Notes:
- **Memory**: the full 2.5M-streamline run holds the whole-brain tracts in
  memory during HDF5 assembly (~8–10 GB peak). Give the container/instance
  ≥ 16 GB, or lower `--n-streamlines`.
- **Alignment QC**: both the interactive `check_alignment.html` and the
  static `check_alignment.png` are produced. The image bundles Google Chrome
  (~0.24 GB) so plotly/kaleido can render the PNG headless; kaleido launches
  Chrome with `--no-sandbox` automatically, which is what containers need.

### On AWS

Build/push to a registry (ECR or Docker Hub) and run on EC2, ECS, or AWS Batch:

```bash
docker build -t <account>.dkr.ecr.<region>.amazonaws.com/dwi-recon:latest .
docker push <account>.dkr.ecr.<region>.amazonaws.com/dwi-recon:latest
# On the instance / Batch job (mount the dataset, e.g. from EFS or an S3 sync):
docker run --rm -v /mnt/data/PennEPI000:/data <image> dwi -i /data
```

For AWS Batch, point the job's command at `dwi -i /data` (or `ieeg -i /data`)
and mount the dataset volume at `/data`. Each job processes one subject dataset.

## Installation (local, without Docker)

### Prerequisites

| Software | Version | Purpose |
|---|---|---|
| [FSL](https://fsl.fmrib.ox.ac.uk/fsl/) | 6.0+ | Eddy correction, registration, brain extraction |
| [Docker](https://www.docker.com/) | Latest | Runs DSI Studio when not using the bundled image |
| DSI Studio | `dsistudio/dsistudio:hou-2026-05-17` (pinned) or a local binary | GQI reconstruction, fiber tracking, connectivity |
| Python | 3.13+ | Pipeline runtime |
| [uv](https://docs.astral.sh/uv/) | Latest | Package manager |

> FreeSurfer is **not** required — `.mgz` volumes are read with nibabel. You
> provide existing FreeSurfer `recon-all` output as a pipeline input.
>
> For local (non-Docker) runs, **DSI Studio runs via its own Docker image**
> by default (pinned `dsistudio/dsistudio:hou-2026-05-17`, set in `config.py`;
> auto `linux/amd64` on Apple Silicon). To use a local DSI Studio binary set
> `"dsiStudioMode": "local"` and `"dsiStudio": "/path/to/dsi_studio"` in
> `setup_environment.json`.

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
dwi-recon/
  Dockerfile                    # self-contained image (DSI Studio + FSL + project)
  .dockerignore                 # build-context excludes
  dev.env                       # INPUT_DIR / OUTPUT_DIR mount points
  setup_environment.docker.json # container config (FSL @ /opt/conda, DSI local)
  run_dwi_recon.py              # single entrypoint: subcommands `dwi`, `ieeg`
  run_dwi_preprocessing.py      # CLI: dwi-preprocess (DWI pipeline)
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
      io.py                     # HDF5 I/O, .mat loading, mgz→nii (nibabel)
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
