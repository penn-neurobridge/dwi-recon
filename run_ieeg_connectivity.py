#!/usr/bin/env python3
"""CLI entry point for the iEEG structural connectivity pipeline.

Separate from the core DWI pipeline. Only for subjects with implanted
electrodes (electrodes2ROI.csv from ieeg_recon module 3). Subjects
without electrode data are automatically skipped.

Requires the DWI pipeline to have run first (tracking + alignment).

Usage:
  # Default (3mm + 5mm spheres)
  uv run dwi-ieeg-connectivity -s sub-RID1171 \\
      -b /path/to/bids

  # All 5 iEEG subjects
  uv run dwi-ieeg-connectivity \\
      -s sub-RID0445,sub-RID1046,sub-RID1081,sub-RID1116,sub-RID1171 \\
      -b /path/to/bids

  # Custom sphere diameters
  uv run dwi-ieeg-connectivity -s sub-RID1171 \\
      -b /path/to/bids --sphere-diameters 3,5,10
"""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="iEEG structural connectivity pipeline (electrode-level SC from DWI)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "-s", "--subjects", type=str, required=True,
        help="Comma-separated subject IDs (e.g. sub-RID1171,sub-RID0445)",
    )
    parser.add_argument(
        "-b", "--bids-path", type=str, required=True,
        help="Root BIDS directory containing subject folders",
    )
    parser.add_argument(
        "-c", "--config", type=str, default=None,
        help="Path to setup_environment.json",
    )
    parser.add_argument(
        "--sphere-diameters", type=str, default="3,5",
        help="Comma-separated sphere diameters in mm",
    )
    parser.add_argument(
        "--n-streamlines", type=int, default=2_500_000,
        help="Streamline count (only used if DWI tracking needs to re-run)",
    )

    args = parser.parse_args()

    subjects = [s.strip() for s in args.subjects.split(",")]
    sphere_dias = [float(d.strip()) for d in args.sphere_diameters.split(",")]
    bids_path = Path(args.bids_path)
    config_path = Path(args.config) if args.config else None

    if not bids_path.is_dir():
        parser.error(f"BIDS path not found: {bids_path}")

    print("iEEG Structural Connectivity Pipeline")
    print(f"  Subjects:          {subjects}")
    print(f"  BIDS path:         {bids_path}")
    print(f"  Sphere diameters:  {sphere_dias}")

    from dwi_preprocessing.ieeg_pipeline import run_ieeg_pipeline

    run_ieeg_pipeline(
        subjects=subjects,
        bids_path=bids_path,
        config_path=config_path,
        sphere_diameters=sphere_dias,
        n_streamlines=args.n_streamlines,
    )

    print("\nProcessing complete!")


if __name__ == "__main__":
    main()
