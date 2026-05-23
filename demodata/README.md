# Demo data

`PennEPI00049/` is an **example dataset** showing the expected on-disk
layout (Penn-Neurobridge format) that the pipeline consumes:

```
PennEPI00049/
├── primary/sub-PennEPI00049/
│   ├── ses-preimplant/{anat,dwi,fmap,func,eeg}
│   ├── ses-postimplant/{ct,ieeg}
│   └── ses-postsurgery/anat
└── derivatives/
    ├── freesurfer/         (recon-all output: mri/, surf/, label/)
    ├── ieeg_recon/         (module1-4; module3/electrodes2ROI.csv)
    ├── post_to_pre/
    └── voxtool_ct/
```

Notes:
- These are **Pennsieve placeholder stubs**, not real imaging volumes — use
  this to understand the directory/naming structure, not to run the pipeline.
- The iEEG **MEF** recordings (`*_ieeg-mef/`) are intentionally **excluded**.
- The DWI here is **multi-shell** (`acq-b300/b700/b2000`); the pipeline's
  single-shell entry point expects one `*_dwi.nii.gz` (see the main README's
  "Input Data Organization").
