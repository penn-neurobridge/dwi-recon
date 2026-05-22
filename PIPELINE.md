# Pipeline Documentation

This document describes the full DWI preprocessing and connectivity pipeline,
from raw inputs through to electrode-level structural connectivity matrices.

Each subject is a **self-contained dataset** (Penn-Neurobridge layout):

```
<dataset>/                       e.g. PennEPI000
  primary/sub-<ID>/ses-preimplant/{anat,dwi,fmap}    raw BIDS inputs
  derivatives/{freesurfer,preprocessDWI,connectivityDWI,connectivityIEEG,ieeg_recon}
```

Derivatives sit **directly** under `derivatives/` (no per-subject nesting).
Tools: **FSL** and **FreeSurfer** run locally; **DSI Studio** runs from a
pinned Docker image (`dsistudio/dsistudio:hou-2026-05-17`). All pipeline
outputs are **HDF5** (`.h5`).

The pipeline has a single entry point, `dwi-recon` (`run_dwi_recon.py`),
with two subcommands:

| Command | Stages | Runs on |
|---|---|---|
| `dwi-recon dwi -i <dataset>` | eddy → register → reconstruct → tracking → alignment → atlas | every subject |
| `dwi-recon ieeg -i <dataset>` | grey→white → edge list → connectivity | electrode subjects only |

## High-Level Overview

```
                        DWI Preprocessing & Connectivity Pipeline
                        ==========================================

  RAW INPUTS                    PROCESSING                         OUTPUTS
  ----------                    ----------                         -------

  DWI         ──┐
  fmap (rev PE) ┤              ┌─────────────┐
  bval/bvec ────┼────────────> │  1. TOPUP +  │
  dwi.json ─────┘              │     EDDY     │ (FSL)
                               └──────┬───────┘
                                      │
  T1 (FreeSurfer) ──┐                │
                     │         ┌──────▼───────┐
                     ├───────> │ 2. EPI-to-T1 │ (FSL epi_reg)
                     │         │ Registration │
                     │         └──────┬───────┘
                     │                │
                     │         ┌──────▼───────┐     whole_brain_trk.h5
                     │         │ 3. GQI Recon │     whole_brain_trksubVox.h5
                     │         │  + Tracking  ├──>  (2.5M streamlines,
                     │         │ (DSI Studio) │      per-point QA/FA/MD/AD/RD)
                     │         └──────┬───────┘
                     │                │
                     │         ┌──────▼───────┐     trk_to_t1surfRAS.txt
                     ├───────> │ 4. Tract-T1  ├──>  check_alignment.{html,png}
                     │         │  Alignment   │
                     │         └──────┬───────┘
                     │                │
  Atlas parcels ─────┤         ┌──────▼───────┐     <atlas>/connectivity.h5
                     ├───────> │ 5. Atlas     ├──>  (NxN: count, fa, md,
                     │         │ Connectivity │      ad, rd, qa, length)
                     │         └──────────────┘
                     │
  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│─ ─ ─ separate pipeline (electrode subjects) ─ ─ ─ ─ ─
                     │
  electrodes2ROI.csv─┤         ┌──────────────┐     connectivityIEEG/
  (ieeg_recon mod 3) ├───────> │ 6. iEEG      ├──>  connectivity.h5
                     │         │ Connectivity │      (ieeg-sc-{3,5}mmSph/...)
                     │         └──────────────┘
```

---

## Stage 1: Distortion & Eddy Current Correction

**Module:** `eddy.py` — `prepare_acqparams()`, `topup_eddy()`
**Tools:** FSL (`fslroi`, `fslmerge`, `topup`, `bet`, auto-detected eddy binary:
`eddy_cpu` / `eddy_openmp` / `eddy`)

```
  DWI                                   ┌──────────────────┐
  fmap (reversed PE b0) ─────────────>  │  FSL TOPUP        │
  acqparams.txt (from dwi.json PE +     │  Estimate field   │
                 TotalReadoutTime)      └────────┬─────────┘
  b02b0_1.cnf                                    │
                                        ┌────────▼─────────┐
  DWI (full volume)                     │  FSL EDDY         │
  bval / bvec          ──────────────>  │  motion + eddy +  │
  Brain mask (from BET on hifi b0)      │  susceptibility   │
                                        └────────┬─────────┘
                                                 ▼
                                        dwi_eddy.nii.gz
                                        dwi_eddy.eddy_rotated_bvecs
```

`acqparams.txt` is generated from the DWI JSON `PhaseEncodingDirection`
(e.g. `j-` → `0 -1 0`) and `TotalReadoutTime`; the reversed row is the
negated vector.

**Inputs:** `ses-preimplant/dwi/*_dwi.{nii.gz,bval,bvec,json}`,
`ses-preimplant/fmap/*dir-AP_epi.nii.gz`
**Outputs:** `preprocessDWI/topupEddy/dwi_eddy.nii.gz`,
`dwi_eddy.eddy_rotated_bvecs`

---

## Stage 2: EPI-to-T1 Registration

**Module:** `registration.py` — `register_epi2t1()`
**Tools:** FSL (`fslroi`, `bet`, `fslmaths`, `epi_reg`); `.mgz`→`.nii.gz` via nibabel

```
  dwi_eddy.nii.gz ──> fslroi ──> b0 ──> bet ──> b0_brain (+ mask)
                                                    │
  FreeSurfer T1/wm/brain.mgz ──> nibabel ──> .nii.gz   (no FreeSurfer binary)
                                                    │
                                          ┌─────────▼──────────┐
                                          │  FSL epi_reg (BBR)  │
                                          └─────────┬──────────┘
                                                    ▼
                                          dwi_to_t1.txt (4x4 affine)
                                          dwi_eddy.b0.gz.brain_mask.nii.gz
```

**Outputs:** `connectivityDWI/bbr2freesurferT1/dwi_to_t1.txt`,
`dwi_eddy.b0.gz.brain_mask.nii.gz`

---

## Stage 3: GQI Reconstruction & Fiber Tracking

**Modules:** `reconstruction.py` (`nifti2src`, `src2gqi`),
`tracking.py` (`fiber_tracking_ittr`)
**Tool:** DSI Studio (Docker)

```
  dwi_eddy.nii.gz  ──> dsi_studio --action=src ──> dwi_eddy.sz
  bval, rotated bvec                                     │
                                                         │
  Brain mask        ──> dsi_studio --action=rec ──> dwi_eddy.gqi.fz
                        --param=1.25                     │  + scalar maps
                        --other_output=fa,ad,rd,md,qa    │  (.fa/.ad/.rd/.md/.qa.nii.gz)
                                                         │
                    ┌────────────────────────────────────┘
                    ▼
             ┌──────────────┐   Each iteration: --tract_count=250000
             │  10 Tracking  │   --export=qa.mat,fa.mat,md.mat,ad.mat,rd.mat
             │  Iterations   │   min_length=30, max_length=300, step_size=1
             └───────┬───────┘
                     │  concatenate iterations, then save HDF5
                     ▼
             ┌──────────────────────────────────────────────┐
             │ whole_brain_trk.h5   group "trk":              │
             │   cord       (4 x N_points) homogeneous coords │
             │   length     (N_tracts,)                       │
             │   start_idx  (N_tracts,)  end_idx (N_tracts,)  │
             │   qa fa md ad rd  (N_tracts,) per-tract means  │
             ├──────────────────────────────────────────────┤
             │ whole_brain_trksubVox.h5   group "trksubVox":  │
             │   qa fa md ad rd  (N_points,) per-point values │
             └──────────────────────────────────────────────┘
```

**Notes (DSI Studio "Hou" formats/CLI):**
- SRC = `.sz`, FIB = `.gqi.fz`, tracts = `.tt.gz`
- `--param` (not `--param0`); `--tract_count` (not `--fiber_count`)
- DTI metrics must be requested at rec via `--other_output`; `exp`/`trk`
  export them as `fa/ad/rd/md/qa` (the `ana` step uses `dti_fa`)
- 2,500,000 total streamlines (10 × 250,000); GQI sampling length = 1.25

**Outputs:** `preprocessDWI/dsiStudio/whole_brain_trk.h5`,
`whole_brain_trksubVox.h5` (plus `dwi_eddy.sz`, `dwi_eddy.gqi.fz`, scalar maps)

---

## Stage 4: Tract-to-T1 Alignment

**Module:** `alignment.py` — `align_tracts_to_t1()`

Computes the 4×4 transform mapping DSI Studio tract coordinates into
FreeSurfer T1 surface-RAS space.

```
  ┌──────────────────────────────────────────────────────┐
  │  T_AP        flip anterior-posterior axis             │
  │  sizeMat     scale by DWI voxel dimensions            │
  │  dwi_to_t1   EPI-to-T1 registration (Stage 2)         │
  │  sizeMatT1   scale by T1 voxel dimensions (inverse)   │
  │  t1surfRAS   FreeSurfer tkRAS transform               │
  │                                                       │
  │  trk_to_t1surfRAS = t1surfRAS · sizeMatT1 ·           │
  │                     dwi_to_t1 · sizeMat · T_AP        │
  └──────────────────────────────────────────────────────┘
```

A QC render (plotly, ieeg-recon style) overlays a subsample of the
transformed tracts on the FreeSurfer pial surfaces.

**Outputs:** `connectivityDWI/tracts_to_T1/trk_to_t1surfRAS.txt`,
`trk_to_t1Vox.txt`, `check_alignment.html`, `check_alignment.png`

---

## Stage 5: Atlas-Based Connectivity

**Module:** `atlas_connectivity.py` — `get_roi_coords()`, `atlas_connectivity()`
**Tool:** DSI Studio `--action=ana` (Docker)

```
  Parcellation atlas (aparc+aseg, lausanne) ──┐
  Lookup table (.csv)                       ──┼──> dsi_studio --action=ana
  GQI fib (.gqi.fz) + tracts (.tt.gz)       ──┤    --connectivity=<atlas>
  T1.nii.gz (--other_slices, registers       ─┘    --connectivity_value=
            atlas→FIB space)                         dti_fa,md,ad,rd,count,
                                                     mean_length,qa
                          │
                          ▼
             one combined *.connectivity.mat  (keys "<metric> r2r" / "t2r")
                          │  parse + reorder to lookup-table ROIs
                          ▼
             ┌────────────────────────────┐
             │ <atlas>/connectivity.h5     │
             │   count  (R x R)            │
             │   fa md ad rd qa length     │
             └────────────────────────────┘
```

**Supported atlases:** Desikan-Killiany (`aparc+aseg`) and Lausanne 2018
scales 1–5 (each Lausanne scale runs only if its NIfTI exists in
`freesurfer/mri/`).

**Outputs:** `connectivityDWI/<atlas>/connectivity.h5` — symmetric R×R
matrices for `count, fa, md, ad, rd, qa, length`.

---

## Stage 6: iEEG Electrode-Level Connectivity

**Module:** `ieeg_connectivity.py` — `ieeg_grey2white()`, `make_edge_list()`,
`make_connectivity_matrix()` (the `dwi-recon ieeg` subcommand)

Requires Stage 3 + 4 outputs and `derivatives/ieeg_recon/module3/electrodes2ROI.csv`.

### Step 6a: Grey-to-White Matter Projection

```
  electrodes2ROI.csv
         │
         ▼
  For each cortical electrode (roiNum > 999):
    1. test if inside the WM surface (trimesh point-in-mesh; needs rtree)
    2. if in grey matter: nearest pial vertex (KDTree) → corresponding WM vertex
    3. update electrode coordinate
         │
         ▼
  electrodes_surf_proj.csv   (all contacts on the WM surface)
```

### Step 6b: Build Edge List (parallel, parpool-equivalent)

```
  whole_brain_trk.h5 + trksubVox.h5 + trk_to_t1surfRAS.txt + electrodes
         │
         ▼
  Tracts split into n_cpu*4 chunks, processed by separate worker
  PROCESSES (joblib loky backend). Large arrays (cord, qa/fa/md/ad/rd)
  are memory-mapped and shared read-only across workers.

  For each tract:
    1. KDTree of tract points; query electrodes within sphere_dia
    2. for each connected electrode pair (sorted along the tract):
         - segment between them; mean QA/FA/MD/AD/RD over the segment
         - record (roi1, roi2, length, qa, fa, md, ad, rd, trkindx)
         │
         ▼
  edgeList_{d}mmSph.csv   (one row per electrode-pair-tract)
```

### Step 6c: Aggregate Connectivity Matrices

```
  edgeList_{d}mmSph.csv
         │  sum per electrode pair; mean metrics; symmetrize M = M + M'
         ▼
  connectivity.h5   (per-subject; one group per sphere diameter)
    ieeg/                coordinate (3 x E), labels (1 x E)
    ieeg-atlas-dkt/      roi (1 x E), roi_fsnum (1 x E)
    ieeg-sc-3mmSph/      ad count fa length md qa rd   (each E x E)
    ieeg-sc-5mmSph/      ad count fa length md qa rd   (each E x E)
```

**Sphere diameters:** default 3mm and 5mm. Larger spheres capture more
tracts but reduce spatial specificity.

---

## Complete File Flow

```
RAW DATA  (primary/sub-<ID>/ses-preimplant)
  dwi.nii.gz + bval/bvec + dwi.json + fmap (reversed PE)
  anat/T1w  (also FreeSurfer recon-all under derivatives/freesurfer)
  derivatives/ieeg_recon/module3/electrodes2ROI.csv   (iEEG subjects)

         │
  ┌──────▼──────────────────────────────────────────────────────────────┐
  │  derivatives/preprocessDWI/topupEddy/                               │
  │    dwi_eddy.nii.gz                   corrected DWI                  │
  │    dwi_eddy.eddy_rotated_bvecs       rotated gradients             │
  ├─────────────────────────────────────────────────────────────────────┤
  │  derivatives/preprocessDWI/dsiStudio/                               │
  │    dwi_eddy.sz                       DSI Studio source             │
  │    dwi_eddy.gqi.fz (+ scalar maps)   GQI reconstruction            │
  │    whole_brain_trk.h5                tract coords + per-tract means │
  │    whole_brain_trksubVox.h5          per-point diffusion metrics    │
  ├─────────────────────────────────────────────────────────────────────┤
  │  derivatives/connectivityDWI/bbr2freesurferT1/dwi_to_t1.txt         │
  │  derivatives/connectivityDWI/tracts_to_T1/                          │
  │    trk_to_t1surfRAS.txt, trk_to_t1Vox.txt, check_alignment.{html,png}│
  │  derivatives/connectivityDWI/<atlas>/connectivity.h5                │
  ├─────────────────────────────────────────────────────────────────────┤
  │  derivatives/connectivityIEEG/        (iEEG subjects)               │
  │    electrodes_surf_proj.csv           GM→WM projected electrodes    │
  │    edgeList_{3,5}mmSph.csv            per-tract edges               │
  │    connectivity.h5                    ieeg-sc-{3,5}mmSph matrices   │
  └─────────────────────────────────────────────────────────────────────┘
```

---

## Diffusion Metrics

| Metric | Full Name | Description |
|---|---|---|
| **QA** | Quantitative Anisotropy | DSI Studio's orientation-specific diffusion measure |
| **FA** | Fractional Anisotropy | Degree of diffusion directionality (0 = isotropic, 1 = fully directional) |
| **MD** | Mean Diffusivity | Average rate of water diffusion |
| **AD** | Axial Diffusivity | Diffusion rate along the primary fiber direction |
| **RD** | Radial Diffusivity | Diffusion rate perpendicular to the primary fiber direction |

These metrics are computed at two levels:
1. **Per-tract mean** (`whole_brain_trk.h5`) — average across all points in each streamline
2. **Per-point** (`whole_brain_trksubVox.h5`) — value at each point along each streamline, used for segment-level metrics between electrode pairs
