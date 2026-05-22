#!/usr/bin/env python3
"""CLI entry point for the core DWI preprocessing pipeline.

Runs for ALL subjects. Full chain:
  eddy -> register -> reconstruct -> tracking -> alignment -> atlas

Raw inputs are read from a "primary" BIDS root; outputs are written to a
separate "derivatives" root (where FreeSurfer recon-all output already lives).

Usage:
  # Full DWI pipeline (default: all steps)
  uv run dwi-preprocess -s sub-PennEPIxxx -p /path/to/primary -d /path/to/derivatives

  # Skip eddy (e.g. eddy outputs already copied in), start at registration
  uv run dwi-preprocess -s sub-PennEPIxxx -p /path/to/primary -d /path/to/derivatives \\
      --steps register,reconstruct,tracking,alignment,atlas
"""

from pathlib import Path
from typing import Optional

import typer

from dwi_preprocessing.pipeline import ALL_STEPS

app = typer.Typer(add_completion=False)


@app.command()
def main(
    subjects: str = typer.Option(
        ..., "-s", "--subjects",
        help="Comma-separated subject IDs (e.g. sub-PennEPIxxx,sub-PennEPIyyy)",
    ),
    primary_path: Path = typer.Option(
        ..., "-p", "--primary-path",
        exists=True, file_okay=False, dir_okay=True,
        help="BIDS primary root (raw inputs: <subject>/ses-preimplant/...)",
    ),
    derivatives_path: Path = typer.Option(
        ..., "-d", "--derivatives-path",
        exists=True, file_okay=False, dir_okay=True,
        help="Derivatives root (outputs: <subject>/freesurfer, preprocessDWI, ...)",
    ),
    config: Optional[Path] = typer.Option(
        None, "-c", "--config",
        exists=True, dir_okay=False,
        help="Path to setup_environment.json",
    ),
    steps: str = typer.Option(
        ",".join(ALL_STEPS), "--steps",
        help="Comma-separated steps: " + ", ".join(ALL_STEPS),
    ),
    n_streamlines: int = typer.Option(
        2_500_000, "--n-streamlines",
        help="Total number of streamlines for fiber tracking",
    ),
):
    """DWI preprocessing pipeline (eddy, register, reconstruct, tracking, alignment, atlas)."""
    subject_list = [s.strip() for s in subjects.split(",") if s.strip()]
    step_list = [s.strip() for s in steps.split(",") if s.strip()]

    invalid = set(step_list) - set(ALL_STEPS)
    if invalid:
        raise typer.BadParameter(f"Invalid steps: {invalid}. Valid: {ALL_STEPS}")

    typer.echo("DWI Preprocessing Pipeline")
    typer.echo(f"  Subjects:      {subject_list}")
    typer.echo(f"  Primary:       {primary_path}")
    typer.echo(f"  Derivatives:   {derivatives_path}")
    typer.echo(f"  Steps:         {step_list}")
    typer.echo(f"  Streamlines:   {n_streamlines}")

    from dwi_preprocessing.pipeline import run_dwi_pipeline

    run_dwi_pipeline(
        subjects=subject_list,
        primary_path=primary_path,
        derivatives_path=derivatives_path,
        steps=step_list,
        config_path=config,
        n_streamlines=n_streamlines,
    )

    typer.echo("\nProcessing complete!")


if __name__ == "__main__":
    app()
