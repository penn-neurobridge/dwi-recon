#!/usr/bin/env python3
"""CLI entry point for the core DWI preprocessing pipeline.

Runs for ALL subjects: fiber tracking, tract-to-T1 alignment, and
atlas-based structural connectivity.

Usage:
  # Full DWI pipeline (default: all steps)
  uv run dwi-preprocess -s sub-RID0445,sub-RID1046 \\
      -b /path/to/bids

  # Only tracking + alignment (skip atlas)
  uv run dwi-preprocess -s sub-RID1171 \\
      -b /path/to/bids --steps tracking,alignment

  # Custom streamline count
  uv run dwi-preprocess -s sub-RID1171 \\
      -b /path/to/bids --n-streamlines 5000000
"""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="DWI preprocessing pipeline (tracking, alignment, atlas connectivity)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "-s", "--subjects", type=str, required=True,
        help="Comma-separated subject IDs (e.g. sub-RID0445,sub-RID1046)",
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
        "--steps", type=str, default="tracking,alignment,atlas",
        help="Comma-separated steps: tracking, alignment, atlas",
    )
    parser.add_argument(
        "--n-streamlines", type=int, default=2_500_000,
        help="Total number of streamlines for fiber tracking",
    )

    args = parser.parse_args()

    subjects = [s.strip() for s in args.subjects.split(",")]
    steps = [s.strip() for s in args.steps.split(",")]
    bids_path = Path(args.bids_path)
    config_path = Path(args.config) if args.config else None

    valid_steps = {"tracking", "alignment", "atlas"}
    invalid = set(steps) - valid_steps
    if invalid:
        parser.error(f"Invalid steps: {invalid}. Valid: {valid_steps}")

    if not bids_path.is_dir():
        parser.error(f"BIDS path not found: {bids_path}")

    print("DWI Preprocessing Pipeline")
    print(f"  Subjects:     {subjects}")
    print(f"  BIDS path:    {bids_path}")
    print(f"  Steps:        {steps}")
    print(f"  Streamlines:  {args.n_streamlines}")

    from dwi_preprocessing.pipeline import run_dwi_pipeline

    run_dwi_pipeline(
        subjects=subjects,
        bids_path=bids_path,
        steps=steps,
        config_path=config_path,
        n_streamlines=args.n_streamlines,
    )

    print("\nProcessing complete!")


if __name__ == "__main__":
    main()
