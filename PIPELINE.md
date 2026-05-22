# Pipeline Documentation

This document describes the full DWI preprocessing and connectivity pipeline, from raw inputs through to electrode-level structural connectivity matrices.

## High-Level Overview

```
                        DWI Preprocessing & Connectivity Pipeline
                        ==========================================

  RAW INPUTS                    PROCESSING                         OUTPUTS
  ----------                    ----------                         -------

  DWI (AP)  ──┐
  DWI (PA)  ──┤                ┌─────────────┐
  bval/bvec ──┼──────────────> │  1. TOPUP +  │
  fieldmaps ──┘                │     EDDY     │
                               └──────┬───────┘
                                      │
  T1 (FreeSurfer) ──┐                │
                     │         ┌──────▼───────┐
                     ├───────> │ 2. EPI-to-T1 │
                     │         │ Registration │
                     │         └──────┬───────┘
                     │                │
                     │         ┌──────▼───────┐     whole_brain_trk.mat
                     │         │ 3. GQI Recon │     whole_brain_trksubVox.mat
                     │         │  + Tracking  ├──>  (2.5M streamlines,
                     │         └──────┬───────┘      per-point QA/FA/MD/AD/RD)
                     │                │
                     │         ┌──────▼───────┐     trk_to_t1surfRAS.txt
                     ├───────> │ 4. Tract-T1  ├──>  (4x4 transform matrix)
                     │         │  Alignment   │
                     │         └──────┬───────┘
                     │                │
  Atlas parcels ─────┤         ┌──────▼───────┐     connectivity.mat
                     ├───────> │ 5. Atlas     ├──>  (NxN: count, FA, MD,
                     │         │ Connectivity │      AD, RD, QA, length)
                     │         └──────────────┘
                     │                │
  Electrode coords ──┤         ┌──────▼───────┐     edgeList_{d}mmSph.csv
  (electrodes2ROI)   ├───────> │ 6. iEEG      ├──>  connectivity_{d}mmSph.mat
                     │         │ Connectivity │      (NxN per metric)
                     │         └──────────────┘
```

---

## Stage 1: Distortion & Eddy Current Correction

**Class:** `PreprocessDWI.topup_eddy()`
**Tools:** FSL (`fslroi`, `fslmerge`, `topup`, `bet`, `eddy_openmp`)

```
  DWI (AP direction)
  DWI (PA direction)                    ┌──────────────────┐
  Acquisition params   ──────────────>  │  FSL TOPUP        │
  b02b0 config                          │  Estimate field   │
                                        └────────┬─────────┘
                                                 │
                                        ┌────────▼─────────┐
  DWI (full volume)                     │  FSL EDDY         │
  bval / bvec          ──────────────>  │  Correct motion,  │
  Brain mask (from BET)                 │  eddy currents,   │
                                        │  susceptibility   │
                                        └────────┬─────────┘
                                                 │
                                                 ▼
                                        dwi_eddy.nii.gz
                                        dwi_eddy.eddy_rotated_bvecs
```

**Input files:**
- `dwi.nii.gz` — Raw DWI volume (AP phase encoding)
- `dwi_PA.nii.gz` — Reversed phase-encode b0 volume
- `dwi.bval`, `dwi.bvec` — b-values and gradient directions
- `acqparams.txt` — Acquisition parameters for topup

**Output files:**
- `preprocessDWI/topupEddy/dwi_eddy.nii.gz` — Corrected DWI volume
- `preprocessDWI/topupEddy/dwi_eddy.eddy_rotated_bvecs` — Rotated gradient directions

---

## Stage 2: EPI-to-T1 Registration

**Class:** `PreprocessDWI.register_epi2t1()`
**Tools:** FSL (`fslroi`, `bet`, `fslmaths`, `epi_reg`), FreeSurfer (`mri_convert`)

```
  dwi_eddy.nii.gz ──> fslroi ──> b0 ──> bet ──> b0_brain
                                                    │
  FreeSurfer T1.mgz ──> mri_convert ──> T1.nii.gz  │
  FreeSurfer wm.mgz ──> mri_convert ──> wm.nii.gz  │
  FreeSurfer brain.mgz ──> mri_convert ──> brain    │
                                                    │
                                          ┌─────────▼──────────┐
                                          │  FSL epi_reg (BBR)  │
                                          │  Boundary-Based     │
                                          │  Registration       │
                                          └─────────┬──────────┘
                                                    │
                                                    ▼
                                          dwi_to_t1.txt (4x4 affine)
```

**Input files:**
- Eddy-corrected DWI from Stage 1
- FreeSurfer `recon-all` outputs (T1.mgz, wm.mgz, brain.mgz)

**Output files:**
- `connectivityDWI/bbr2freesurferT1/dwi_to_t1.txt` — 4x4 affine registration matrix

---

## Stage 3: GQI Reconstruction & Fiber Tracking

**Class:** `PreprocessDWI.nifti2src()`, `PreprocessDWI.src2gqi()`, `PreprocessDWI.fiber_tracking_ittr()`
**Tools:** DSI Studio

```
  dwi_eddy.nii.gz  ──> dsi_studio --action=src ──> dwi_eddy.src.gz
  bval, bvec                                             │
                                                         │
  Brain mask        ──> dsi_studio --action=rec ──> *.gqi*.fib.gz
                        (GQI, param0=1.25)               │
                                                         │
                    ┌────────────────────────────────────┘
                    │
                    ▼
             ┌──────────────┐
             │  10 Tracking  │   Each iteration: 250K streamlines
             │  Iterations   │   --export=qa.mat,dti_fa.mat,md.mat,ad.mat,rd.mat
             │               │   min_length=30, max_length=300, step_size=1
             └───────┬───────┘
                     │
                     ▼  Concatenate all iterations
             ┌───────────────────┐
             │ whole_brain_trk   │   cord:     (4 x N_points) homogeneous coordinates
             │ .mat              │   length:   (N_tracts,) streamline lengths
             │                   │   startEnd: (N_tracts, 2) start/end indices
             │                   │   qaTrk:    (N_tracts,) mean QA per tract
             │                   │   faTrk:    (N_tracts,) mean FA per tract
             │                   │   mdTrk, adTrk, rdTrk: same for MD, AD, RD
             └───────────────────┘
             ┌───────────────────┐
             │ whole_brain       │   qa: (N_points,) per-point QA
             │ _trksubVox.mat   │   fa: (N_points,) per-point FA
             │                   │   md, ad, rd: same
             └───────────────────┘
```

**Parameters:**
- 2,500,000 total streamlines (10 iterations x 250,000)
- GQI reconstruction with diffusion sampling length ratio = 1.25
- Tracking: method=1 (streamline), trim=1, random_seed=1, thread_count=16

**Output files:**
- `preprocessDWI/dsiStudio/whole_brain_trk.mat` — Tract coordinates + per-tract mean metrics
- `preprocessDWI/dsiStudio/whole_brain_trksubVox.mat` — Per-point metrics along each streamline

---

## Stage 4: Tract-to-T1 Alignment

**Class:** `PreprocessDWI.align_tracts_to_t1()`

Computes a 4x4 transformation matrix that maps DSI Studio tract coordinates into FreeSurfer T1 surface RAS space.

```
  DSI Studio tracts (voxel space)
         │
         ▼
  ┌──────────────────────────────────────────────────────┐
  │  T_AP        Flip anterior-posterior axis             │
  │  sizeMat     Scale by DWI voxel dimensions           │
  │  dwi_to_t1   EPI-to-T1 registration (from Stage 2)  │
  │  sizeMatT1   Scale by T1 voxel dimensions (inverse)  │
  │  t1surfRAS   FreeSurfer tkRAS transform               │
  │                                                       │
  │  trk_to_t1surfRAS = t1surfRAS x sizeMatT1 x          │
  │                      dwi_to_t1 x sizeMat x T_AP       │
  └──────────────────────────────────────────────────────┘
         │
         ▼
  Tracts in T1 surface RAS coordinates
  (aligned with FreeSurfer pial/white surfaces)
```

**Output files:**
- `connectivityDWI/tracts_to_T1/trk_to_t1surfRAS.txt` — 4x4 tract-to-surface-RAS transform
- `connectivityDWI/tracts_to_T1/trk_to_t1Vox.txt` — 4x4 tract-to-T1-voxel transform
- `connectivityDWI/tracts_to_T1/check_alignment.png` — QC visualization

---

## Stage 5: Atlas-Based Connectivity

**Class:** `PreprocessDWI.get_roi_cord()`, `PreprocessDWI.atlas_connectivity()`
**Tools:** DSI Studio (`--action=ana`)

```
  Parcellation atlas    ──┐
  (aparc+aseg, lausanne)  │
                          │    ┌───────────────────────┐
  Lookup table (.csv)   ──┼──> │  DSI Studio            │
                          │    │  --action=ana           │
  fib.gz + trk.gz      ──┤    │  --connectivity=atlas   │
                          │    │  --connectivity_value=  │
  T1.nii.gz             ──┘    │    dti_fa,md,ad,rd,     │
                               │    count,mean_length,qa │
                               └───────────┬────────────┘
                                           │
                                           ▼
                               ┌────────────────────────┐
                               │  connectivity.mat       │
                               │    count:  (R x R)      │
                               │    fa:     (R x R)      │
                               │    md:     (R x R)      │
                               │    ad:     (R x R)      │
                               │    rd:     (R x R)      │
                               │    qa:     (R x R)      │
                               │    length: (R x R)      │
                               └────────────────────────┘
```

**Supported atlases:**
| Atlas | Regions | File |
|---|---|---|
| Desikan-Killiany | 68 cortical | `desikanKilliany.csv` |
| Lausanne 2018 Scale 1 | ~100 | `lausanne2018scale1.csv` |
| Lausanne 2018 Scale 2 | ~250 | `lausanne2018scale2.csv` |
| Lausanne 2018 Scale 3 | ~500 | `lausanne2018scale3.csv` |
| Lausanne 2018 Scale 4 | ~1000 | `lausanne2018scale4.csv` |
| Lausanne 2018 Scale 5 | ~2000 | `lausanne2018scale5.csv` |

**Output files:**
- `connectivityDWI/<atlas>/connectivity.mat` — Symmetric RxR matrices per metric

---

## Stage 6: iEEG Electrode-Level Connectivity

**Class:** `IEEGsc`

This is the main use case for the pipeline: computing structural connectivity between intracranial EEG electrode contacts.

### Step 6a: Grey-to-White Matter Projection

```
  electrodes2ROI.csv
  (from ieeg_recon module 3)
         │
         ▼
  ┌──────────────────────────────────────┐
  │  For each cortical electrode:         │
  │    1. Test if inside WM surface       │
  │       (trimesh point-in-mesh)         │
  │    2. If in grey matter:              │
  │       - Find nearest pial vertex      │
  │         (KDTree nearest-neighbor)     │
  │       - Map to corresponding WM       │
  │         vertex                        │
  │    3. Update electrode coordinates    │
  └──────────────────────┬───────────────┘
                         │
                         ▼
              electrodes_surf_proj.csv
              (all contacts on WM surface)
```

### Step 6b: Build Edge List

```
  whole_brain_trk.mat     ──┐
  whole_brain_trksubVox.mat ┤
  trk_to_t1surfRAS.txt   ──┤
  electrodes (projected)  ──┘
         │
         ▼
  ┌────────────────────────────────────────────────────┐
  │  For each tract (parallelized with joblib):         │
  │    1. Transform tract to surface RAS                │
  │    2. Build KDTree of tract points                  │
  │    3. Query: which electrodes within sphere_dia?    │
  │    4. For each pair of connected electrodes:        │
  │       - Extract tract segment between them          │
  │       - Compute mean QA, FA, MD, AD, RD of segment │
  │       - Record: (roi1, roi2, length, metrics,       │
  │                  tract_index)                        │
  └────────────────────────────────┬───────────────────┘
                                   │
                                   ▼
                     edgeList_{d}mmSph.csv
                     (one row per electrode-pair-tract)
```

### Step 6c: Aggregate Connectivity Matrices

```
  edgeList_{d}mmSph.csv
         │
         ▼
  ┌──────────────────────────────────┐
  │  For each electrode pair (i,j):   │
  │    count[i,j] = number of tracts  │
  │    fa[i,j]  = mean FA across all  │
  │               connecting tracts   │
  │    (same for QA, MD, AD, RD,      │
  │     length)                       │
  │                                   │
  │  Symmetrize: M = M + M'          │
  └──────────────────┬───────────────┘
                     │
                     ▼
         connectivity_{d}mmSph.mat
         ┌─────────────────────────┐
         │  count: (E x E)         │
         │  fa:    (E x E)         │
         │  qa:    (E x E)         │
         │  md:    (E x E)         │
         │  ad:    (E x E)         │
         │  rd:    (E x E)         │
         │  len:   (E x E)         │
         │                         │
         │  E = number of          │
         │      electrodes         │
         └─────────────────────────┘
```

**Sphere diameters:** By default, connectivity is computed for 3mm and 5mm spheres around each electrode. Larger spheres capture more tracts but may reduce spatial specificity.

---

## Complete File Flow

```
RAW DATA
  dwi.nii.gz + bval/bvec + fieldmaps + T1 (FreeSurfer recon-all)
  electrodes2ROI.csv (from ieeg_recon)

         │
  ┌──────▼──────────────────────────────────────────────────────────────┐
  │  preprocessDWI/topupEddy/                                           │
  │    dwi_eddy.nii.gz                   Corrected DWI volume          │
  │    dwi_eddy.eddy_rotated_bvecs       Rotated gradients             │
  ├─────────────────────────────────────────────────────────────────────┤
  │  preprocessDWI/dsiStudio/                                           │
  │    dwi_eddy.src.gz                   DSI Studio source file        │
  │    *.gqi*.fib.gz                     GQI reconstruction            │
  │    whole_brain_trk.mat               Tract coordinates + metrics   │
  │    whole_brain_trksubVox.mat         Per-point diffusion metrics    │
  ├─────────────────────────────────────────────────────────────────────┤
  │  connectivityDWI/bbr2freesurferT1/                                  │
  │    dwi_to_t1.txt                     DWI-to-T1 registration        │
  ├─────────────────────────────────────────────────────────────────────┤
  │  connectivityDWI/tracts_to_T1/                                      │
  │    trk_to_t1surfRAS.txt              Tract-to-surface transform    │
  │    trk_to_t1Vox.txt                  Tract-to-T1-voxel transform   │
  │    check_alignment.png               QC overlay                    │
  ├─────────────────────────────────────────────────────────────────────┤
  │  connectivityDWI/desikanKilliany/                                   │
  │    connectivity.mat                  68-region atlas connectivity   │
  ├─────────────────────────────────────────────────────────────────────┤
  │  connectivityIEEG/                                                  │
  │    electrodes_surf_proj.csv          GM-to-WM projected electrodes │
  │    edgeList_3mmSph.csv               Edge list (3mm sphere)        │
  │    edgeList_5mmSph.csv               Edge list (5mm sphere)        │
  │    connectivity_3mmSph.mat           Connectivity matrix (3mm)     │
  │    connectivity_5mmSph.mat           Connectivity matrix (5mm)     │
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
1. **Per-tract mean** (`whole_brain_trk.mat`) — average across all points in each streamline
2. **Per-point** (`whole_brain_trksubVox.mat`) — value at each point along each streamline, used for computing segment-level metrics between electrode pairs
