#!/usr/bin/env python3
"""CLI entry point for the core DWI preprocessing pipeline.

Runs for ALL subjects: fiber tracking, tract-to-T1 alignment, and
atlas-based structural connectivity.

Usage:
  # Full DWI pipeline (default: all steps)
  uv run dwi-preprocess -s sub-RID0445,sub-RID1046 -b /path/to/bids

  # Only tracking + alignment (skip atlas)
  uv run dwi-preprocess -s sub-RID1171 -b /path/to/bids --steps tracking,alignment

  # Custom streamline count
  uv run dwi-preprocess -s sub-RID1171 -b /path/to/bids --n-streamlines 5000000
"""

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(add_completion=False)


@app.command()
def main(
    subjects: str = typer.Option(
        ..., "-s", "--subjects",
        help="Comma-separated subject IDs (e.g. sub-RID0445,sub-RID1046)",
    ),
    bids_path: Path = typer.Option(
        ..., "-b", "--bids-path",
        exists=True, file_okay=False, dir_okay=True,
        help="Root BIDS directory containing subject folders",
    ),
    config: Optional[Path] = typer.Option(
        None, "-c", "--config",
        exists=True, dir_okay=False,
        help="Path to setup_environment.json",
    ),
    steps: str = typer.Option(
        "tracking,alignment,atlas", "--steps",
        help="Comma-separated steps: tracking, alignment, atlas",
    ),
    n_streamlines: int = typer.Option(
        2_500_000, "--n-streamlines",
        help="Total number of streamlines for fiber tracking",
    ),
):
    """DWI preprocessing pipeline (tracking, alignment, atlas connectivity)."""
    subject_list = [s.strip() for s in subjects.split(",") if s.strip()]
    step_list = [s.strip() for s in steps.split(",") if s.strip()]

    valid_steps = {"tracking", "alignment", "atlas"}
    invalid = set(step_list) - valid_steps
    if invalid:
        raise typer.BadParameter(f"Invalid steps: {invalid}. Valid: {valid_steps}")

    typer.echo("DWI Preprocessing Pipeline")
    typer.echo(f"  Subjects:     {subject_list}")
    typer.echo(f"  BIDS path:    {bids_path}")
    typer.echo(f"  Steps:        {step_list}")
    typer.echo(f"  Streamlines:  {n_streamlines}")

    from dwi_preprocessing.pipeline import run_dwi_pipeline

    run_dwi_pipeline(
        subjects=subject_list,
        bids_path=bids_path,
        steps=step_list,
        config_path=config,
        n_streamlines=n_streamlines,
    )

    typer.echo("\nProcessing complete!")


if __name__ == "__main__":
    app()
