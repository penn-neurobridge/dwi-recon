#!/usr/bin/env python3
"""CLI entry point for the iEEG structural connectivity pipeline.

Separate from the core DWI pipeline. Only for subjects with implanted
electrodes (electrodes2ROI.csv from ieeg_recon module 3). Subjects
without electrode data are automatically skipped.

Requires the DWI pipeline to have run first (tracking + alignment).

Usage:
  # Default (3mm + 5mm spheres)
  uv run dwi-ieeg-connectivity -s sub-PennEPIxxx -b /path/to/bids

  # Multiple iEEG subjects
  uv run dwi-ieeg-connectivity \\
      -s sub-PennEPIxxx,sub-PennEPIyyy,sub-PennEPIzzz \\
      -b /path/to/bids

  # Custom sphere diameters
  uv run dwi-ieeg-connectivity -s sub-PennEPIxxx -b /path/to/bids --sphere-diameters 3,5,10
"""

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(add_completion=False)


@app.command()
def main(
    subjects: str = typer.Option(
        ..., "-s", "--subjects",
        help="Comma-separated subject IDs (e.g. sub-PennEPIxxx,sub-PennEPIyyy)",
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
    sphere_diameters: str = typer.Option(
        "3,5", "--sphere-diameters",
        help="Comma-separated sphere diameters in mm",
    ),
    n_streamlines: int = typer.Option(
        2_500_000, "--n-streamlines",
        help="Streamline count (only used if DWI tracking needs to re-run)",
    ),
):
    """iEEG structural connectivity pipeline (electrode-level SC from DWI)."""
    subject_list = [s.strip() for s in subjects.split(",") if s.strip()]

    try:
        sphere_dias = [float(d.strip()) for d in sphere_diameters.split(",") if d.strip()]
    except ValueError:
        raise typer.BadParameter("Sphere diameters must be numbers (e.g. 3,5,10)")

    typer.echo("iEEG Structural Connectivity Pipeline")
    typer.echo(f"  Subjects:          {subject_list}")
    typer.echo(f"  BIDS path:         {bids_path}")
    typer.echo(f"  Sphere diameters:  {sphere_dias}")

    from dwi_preprocessing.ieeg_pipeline import run_ieeg_pipeline

    run_ieeg_pipeline(
        subjects=subject_list,
        bids_path=bids_path,
        config_path=config,
        sphere_diameters=sphere_dias,
        n_streamlines=n_streamlines,
    )

    typer.echo("\nProcessing complete!")


if __name__ == "__main__":
    app()
