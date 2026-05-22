#!/usr/bin/env python3
"""CLI entry point for the DWI preprocessing pipeline.

Usage examples:

  # iEEG connectivity for one subject:
  uv run dwi-connectivity --subjects sub-RID1171 \\
      --bids-path /path/to/bids --steps ieeg

  # Full pipeline:
  uv run dwi-connectivity --subjects sub-RID0445,sub-RID1046 \\
      --bids-path /path/to/bids --steps tracking,alignment,atlas,ieeg

  # Custom sphere diameters:
  uv run dwi-connectivity --subjects sub-RID1171 \\
      --bids-path /path/to/bids --steps ieeg --sphere-diameters 3,5,10
"""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="DWI preprocessing and structural connectivity pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Required
    parser.add_argument(
        "-s", "--subjects", type=str, required=True,
        help="Comma-separated subject IDs (e.g. sub-RID0445,sub-RID1046)",
    )
    parser.add_argument(
        "-b", "--bids-path", type=str, required=True,
        help="Root BIDS directory containing subject folders",
    )

    # Optional
    parser.add_argument(
        "-c", "--config", type=str, default=None,
        help="Path to setup_environment.json (default: repo_root/setup_environment.json)",
    )
    parser.add_argument(
        "--steps", type=str, default="ieeg",
        help="Comma-separated steps: tracking,alignment,atlas,ieeg",
    )
    parser.add_argument(
        "--n-streamlines", type=int, default=2_500_000,
        help="Total number of streamlines for fiber tracking",
    )
    parser.add_argument(
        "--sphere-diameters", type=str, default="3,5",
        help="Comma-separated sphere diameters in mm for iEEG connectivity",
    )

    args = parser.parse_args()

    # Parse inputs
    subjects = [s.strip() for s in args.subjects.split(",")]
    steps = [s.strip() for s in args.steps.split(",")]
    sphere_dias = [float(d.strip()) for d in args.sphere_diameters.split(",")]
    bids_path = Path(args.bids_path)
    config_path = Path(args.config) if args.config else None

    # Validate
    valid_steps = {"tracking", "alignment", "atlas", "ieeg"}
    invalid = set(steps) - valid_steps
    if invalid:
        parser.error(f"Invalid steps: {invalid}. Valid: {valid_steps}")

    if not bids_path.is_dir():
        parser.error(f"BIDS path not found: {bids_path}")

    print("DWI Preprocessing Pipeline")
    print(f"  Subjects: {subjects}")
    print(f"  BIDS path: {bids_path}")
    print(f"  Steps: {steps}")
    print(f"  Streamlines: {args.n_streamlines}")
    print(f"  Sphere diameters: {sphere_dias}")

    # Run
    from dwi_preprocessing.pipeline import run_pipeline

    run_pipeline(
        subjects=subjects,
        bids_path=bids_path,
        steps=steps,
        config_path=config_path,
        n_streamlines=args.n_streamlines,
        sphere_diameters=sphere_dias,
    )

    print("\nProcessing complete!")


if __name__ == "__main__":
    main()
