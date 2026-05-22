# DWI Minimum Preprocessing Pipeline

A Python pipeline for diffusion-weighted imaging (DWI) preprocessing, whole-brain fiber tracking, and structural connectivity analysis with specialized support for intracranial EEG (iEEG) electrode-level connectivity.

## Overview

This pipeline takes raw DWI data through eddy/distortion correction, GQI reconstruction, whole-brain tractography, and connectivity analysis at both atlas and electrode levels. It wraps **FSL**, **FreeSurfer**, and **DSI Studio** command-line tools in a reproducible Python workflow.

See [PIPELINE.md](PIPELINE.md) for detailed flowcharts of each processing stage.

## Features

- Eddy current and susceptibility distortion correction (FSL topup + eddy)
- EPI-to-T1 boundary-based registration (FSL epi_reg)
- GQI reconstruction and whole-brain fiber tracking (DSI Studio)
- Iterative tractography with per-streamline diffusion metrics (QA, FA, MD, AD, RD)
- Atlas-based structural connectivity (Desikan-Killiany, Lausanne 2018 scales 1-5)
- iEEG electrode-level structural connectivity with grey-to-white matter projection

## Installation

### Prerequisites

| Software | Version | Purpose |
|---|---|---|
| [FSL](https://fsl.fmrib.ox.ac.uk/fsl/) | 6.0+ | Eddy correction, registration, brain extraction |
| [FreeSurfer](https://surfer.nmr.mgh.harvard.edu/) | 7.0+ (8.1.0 recommended) | Surface reconstruction, parcellation |
| [DSI Studio](https://dsi-studio.labsolver.org/) | 2022+ | GQI reconstruction, fiber tracking |
| Python | 3.13+ | Pipeline runtime |
| [uv](https://docs.astral.sh/uv/) | Latest | Package manager |

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
    "dsiStudio": "/path/to/dsi_studio",
    "FS_LICENSE": "/path/to/freesurfer/license.txt",
    "SURFER_FRONTDOOR": "1",
    "dockerSynb0disco": "sudo /usr/local/bin/docker",
    "singularityLoc": " "
}
```

## Usage

### Command Line

```bash
# Run iEEG connectivity for one subject
uv run dwi-connectivity \
    --subjects sub-RID1171 \
    --bids-path /path/to/bids \
    --steps ieeg

# Run full pipeline (tracking + alignment + atlas + iEEG)
uv run dwi-connectivity \
    --subjects sub-RID0445,sub-RID1046,sub-RID1081 \
    --bids-path /path/to/bids \
    --steps tracking,alignment,atlas,ieeg

# Custom streamline count and sphere diameters
uv run dwi-connectivity \
    --subjects sub-RID1171 \
    --bids-path /path/to/bids \
    --steps tracking,alignment,ieeg \
    --n-streamlines 5000000 \
    --sphere-diameters 3,5,10
```

### Pipeline Steps

| Step | Flag | Description |
|---|---|---|
| `tracking` | `--steps tracking` | Iterative fiber tracking (10 x 250K streamlines) with per-point metric export |
| `alignment` | `--steps alignment` | Compute tract-to-T1 surface RAS transformation |
| `atlas` | `--steps atlas` | Atlas-based connectivity matrices (Desikan-Killiany + Lausanne) |
| `ieeg` | `--steps ieeg` | Electrode-level connectivity with grey-to-white projection |

Steps can be combined: `--steps tracking,alignment,ieeg`

### Python API

```python
from dwi_preprocessing.config import Config
from dwi_preprocessing.preprocess_dwi import PreprocessDWI
from dwi_preprocessing.ieeg_sc import IEEGsc

cfg = Config()  # loads setup_environment.json from repo root
subject = PreprocessDWI(cfg)
subject.output = "/path/to/bids/sub-RID1171/derivatives"
subject.freesurfer_dir = f"{subject.output}/freesurfer"

# Run fiber tracking
data = {"nStreamlines": 2500000, "dwi_fib": "/path/to/fib.gz"}
data = subject.fiber_tracking_ittr(data, save_trksubvox=True)
data = subject.align_tracts_to_t1(data)

# iEEG connectivity
ieeg = IEEGsc(subject.output)
electrodes = ieeg.ieeg_grey2white()
edge_list = ieeg.make_edge_list(electrodes, sphere_dia=5.0)
connectivity = ieeg.make_connectivity_matrix(edge_list, sphere_dia=5.0)
```

## Expected Directory Layout

The pipeline expects a BIDS-like directory structure:

```
<BIDS_path>/
  sub-RID1171/
    derivatives/
      freesurfer/           # FreeSurfer recon-all output
        mri/                # T1.mgz, wm.mgz, brain.mgz, aparc+aseg.mgz
        surf/               # lh.pial, rh.pial, lh.white, rh.white
      preprocessDWI/
        topupEddy/          # Eddy-corrected DWI
        dsiStudio/          # SRC, fib.gz, whole_brain_trk.mat, whole_brain_trksubVox.mat
      connectivityDWI/
        bbr2freesurferT1/   # DWI-to-T1 registration (dwi_to_t1.txt)
        tracts_to_T1/       # trk_to_t1surfRAS.txt transform
        desikanKilliany/    # Atlas connectivity matrices
        lausanne2018scale*/
      ieeg_recon/
        module3/
          electrodes2ROI.csv  # Electrode coordinates + ROI assignments
      connectivityIEEG/     # Output: edge lists, connectivity matrices
```

## Output Files

### Fiber Tracking
- `whole_brain_trk.mat` — Tract coordinates (4 x N), per-tract mean QA/FA/MD/AD/RD
- `whole_brain_trksubVox.mat` — Per-point QA/FA/MD/AD/RD along each streamline

### Atlas Connectivity
- `connectivity.mat` — Symmetric NxN matrices for count, FA, MD, AD, RD, QA, mean length

### iEEG Connectivity
- `electrodes_surf_proj.csv` — Electrodes with grey-to-white matter projected coordinates
- `edgeList_{d}mmSph.csv` — Per-tract edges between electrode pairs within d mm sphere
- `connectivity_{d}mmSph.mat` — Symmetric NxN connectivity matrices (count, length, QA, FA, MD, AD, RD)

## Repository Structure

```
dwi_minimum_preprocessing/
  dwi_preprocessing/          # Python package (primary)
    __init__.py
    config.py                 # Configuration loader (setup_environment.json)
    preprocess_dwi.py         # PreprocessDWI class — eddy, registration, tracking
    ieeg_sc.py                # IEEGsc class — electrode connectivity
    run_connectivity.py       # CLI entry point (dwi-connectivity)
    utils/
      io.py                   # .mat file I/O (v5 + v7.3/HDF5)
      surfaces.py             # FreeSurfer surface + coordinate utilities
      geometry.py             # Point-in-mesh tests (trimesh)
  matlab/                     # Legacy MATLAB implementation
    preprocessDWI.m           # Original preprocessing class
    iEEGsc.m                  # Original iEEG connectivity class
    mainConnectivity.m        # Full pipeline wrapper
    mainConnectivityIEEG.m    # iEEG-specific wrapper
    mainEddy.m                # Eddy correction wrapper
    dependencies/             # MATLAB helper functions
  atlas_lookuptable/          # Parcellation lookup tables + annotation files
  pyproject.toml              # uv / pip project configuration
  uv.lock                     # Locked dependency versions
  setup_environment.json      # Machine-specific tool paths (gitignored)
  PIPELINE.md                 # Pipeline flowcharts and documentation
  LICENSE                     # MIT License
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
