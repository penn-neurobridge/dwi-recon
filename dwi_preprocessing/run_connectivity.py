#!/usr/bin/env python
"""CLI entry point for DWI connectivity pipeline.

Usage examples:

  # iEEG connectivity only (for subjects with completed preprocessing):
  dwi-connectivity --subjects sub-RID1171 \\
      --bids-path /Users/nishant/Documents/Neurobridge/Data/Epilepsy/Penn \\
      --steps ieeg

  # Full pipeline from eddy-corrected data:
  dwi-connectivity --subjects sub-RID1171 \\
      --bids-path /path/to/bids \\
      --steps tracking,alignment,atlas,ieeg

  # All 5 subjects:
  dwi-connectivity --subjects sub-RID0445,sub-RID1046,sub-RID1081,sub-RID1116,sub-RID1171 \\
      --bids-path /Users/nishant/Documents/Neurobridge/Data/Epilepsy/Penn \\
      --steps ieeg
"""

import argparse
import glob
import os
import sys
from pathlib import Path

import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(
        description="DWI preprocessing and structural connectivity pipeline"
    )
    parser.add_argument(
        "-s", "--subjects",
        required=True,
        help="Comma-separated subject IDs (e.g. sub-RID0445,sub-RID1046)"
    )
    parser.add_argument(
        "-b", "--bids-path",
        required=True,
        help="Root BIDS directory containing subject folders"
    )
    parser.add_argument(
        "-c", "--config",
        default=None,
        help="Path to setup_environment.json (default: repo_root/setup_environment.json)"
    )
    parser.add_argument(
        "--steps",
        default="ieeg",
        help="Comma-separated steps to run: tracking,alignment,atlas,ieeg (default: ieeg)"
    )
    parser.add_argument(
        "--n-streamlines",
        type=int,
        default=2500000,
        help="Number of streamlines for fiber tracking (default: 2500000)"
    )
    parser.add_argument(
        "--sphere-diameters",
        default="3,5",
        help="Comma-separated sphere diameters in mm for iEEG connectivity (default: 3,5)"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Lazy imports so --help is fast
    from dwi_preprocessing.config import Config
    from dwi_preprocessing.preprocess_dwi import PreprocessDWI
    from dwi_preprocessing.ieeg_sc import IEEGsc

    subjects = [s.strip() for s in args.subjects.split(",")]
    steps = [s.strip() for s in args.steps.split(",")]
    sphere_dias = [float(d.strip()) for d in args.sphere_diameters.split(",")]

    cfg = Config(args.config) if args.config else Config()

    for i, rid in enumerate(subjects):
        print(f"\n{'='*60}")
        print(f"Processing {rid} ({i+1}/{len(subjects)})")
        print(f"{'='*60}")

        output = os.path.join(args.bids_path, rid, "derivatives")
        assert os.path.isdir(output), f"Derivatives not found: {output}"

        subject = PreprocessDWI(cfg)
        subject.output = output
        subject.freesurfer_dir = os.path.join(output, "freesurfer")

        # Populate data_for_tracking from existing files
        data_for_tracking = {"nStreamlines": args.n_streamlines}

        # Find fib file
        fib_pattern = os.path.join(output, "preprocessDWI", "dsiStudio", "*gqi*fib.gz")
        fib_matches = glob.glob(fib_pattern)
        assert fib_matches, f"No fib.gz found for {rid}"
        data_for_tracking["dwi_fib"] = fib_matches[0]
        data_for_tracking["dwi_fib_fa"] = f"{fib_matches[0]}.dti_fa.nii.gz"

        # Registration matrix
        dwi_to_t1 = os.path.join(output, "connectivityDWI", "bbr2freesurferT1", "dwi_to_t1.txt")
        if os.path.isfile(dwi_to_t1):
            data_for_tracking["dwi_to_freesurferT1"] = dwi_to_t1

        # .trk.gz for atlas connectivity
        trk_gz = f"{fib_matches[0]}.trk.gz"
        if os.path.isfile(trk_gz):
            data_for_tracking["dwi_trk"] = trk_gz

        # ---- Step: fiber tracking (iterative, with subvox export) ----
        if "tracking" in steps:
            print(f"  [tracking] fiberTracking_ittr (trk + trksubVox)...")
            data_for_tracking = subject.fiber_tracking_ittr(
                data_for_tracking, save_trksubvox=True
            )

        # ---- Step: tract-to-T1 alignment ----
        if "alignment" in steps:
            print(f"  [alignment] align_tracts_to_t1...")
            data_for_tracking = subject.align_tracts_to_t1(data_for_tracking)

        # ---- Step: atlas connectivity (DSI Studio) ----
        if "atlas" in steps:
            print(f"  [atlas] atlas connectivity...")
            atlas_dir = os.path.join(
                str(cfg.repo_root), "atlas_lookuptable"
            )

            # Desikan-Killiany
            atlas_name = "aparc+aseg"
            lut = os.path.join(atlas_dir, "desikanKilliany.csv")
            data_for_tracking = subject.get_roi_cord(data_for_tracking, atlas_name, lut)

            atlas_name = "desikanKilliany"
            atlas_file = os.path.join(subject.freesurfer_dir, "mri", "aparc+aseg.nii.gz")
            data_for_tracking = subject.atlas_connectivity(
                data_for_tracking, atlas_name, atlas_file, lut
            )

            # Lausanne scales
            for scale in range(1, 6):
                atlas_name = f"lausanne2018scale{scale}"
                atlas_file = os.path.join(
                    subject.freesurfer_dir, "mri", f"lausanne2018.scale{scale}.nii.gz"
                )
                lut = os.path.join(atlas_dir, f"{atlas_name}.csv")
                if os.path.isfile(atlas_file) and os.path.isfile(lut):
                    data_for_tracking = subject.atlas_connectivity(
                        data_for_tracking, atlas_name, atlas_file, lut
                    )

        # ---- Step: iEEG electrode-level connectivity ----
        if "ieeg" in steps:
            ieeg_csv = os.path.join(output, "ieeg_recon", "module3", "electrodes2ROI.csv")
            if not os.path.isfile(ieeg_csv):
                print(f"  Skipping iEEG — electrodes2ROI.csv not found")
                continue

            # Ensure tracking + alignment are done
            trk_mat = os.path.join(output, "preprocessDWI", "dsiStudio", "whole_brain_trk.mat")
            subvox_mat = os.path.join(output, "preprocessDWI", "dsiStudio", "whole_brain_trksubVox.mat")

            if not os.path.isfile(trk_mat) or not os.path.isfile(subvox_mat):
                print(f"  Running fiber tracking (trk + trksubVox)...")
                data_for_tracking = subject.fiber_tracking_ittr(
                    data_for_tracking, save_trksubvox=True
                )

            surfras = os.path.join(output, "connectivityDWI", "tracts_to_T1", "trk_to_t1surfRAS.txt")
            if not os.path.isfile(surfras):
                print(f"  Running tract-to-T1 alignment...")
                data_for_tracking = subject.align_tracts_to_t1(data_for_tracking)

            print(f"  [ieeg] iEEG connectivity...")
            sub_ieeg = IEEGsc(output)
            electrodes = sub_ieeg.ieeg_grey2white()

            for dia in sphere_dias:
                edge_list = sub_ieeg.make_edge_list(electrodes, dia)
                sub_ieeg.make_connectivity_matrix(edge_list, dia)

        print(f"  Done: {rid}")

    print(f"\n{'='*60}")
    print("All subjects complete")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
