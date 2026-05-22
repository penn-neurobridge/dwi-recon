#!/usr/bin/env python3
"""CLI entry point for the iEEG structural connectivity pipeline.

Operates on per-subject dataset directories (primary/ + derivatives/).
Only for datasets with implanted electrodes (electrodes2ROI.csv from
ieeg_recon module 3). Datasets without electrode data are auto-skipped.

Requires the DWI pipeline to have run first (tracking + alignment).

Usage:
  # Default (3mm + 5mm spheres)
  uv run dwi-ieeg-connectivity -i /path/to/PennEPI001

  # Multiple datasets, custom sphere diameters
  uv run dwi-ieeg-connectivity -i /path/to/PennEPI001,/path/to/PennEPI004 \\
      --sphere-diameters 3,5,10
"""

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(add_completion=False)


@app.command()
def main(
    dataset_path: str = typer.Option(
        ..., "-i", "--dataset-path",
        help="Dataset root(s) containing primary/ and derivatives/ "
             "(comma-separated for multiple)",
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
    datasets = [Path(p.strip()) for p in dataset_path.split(",") if p.strip()]

    try:
        sphere_dias = [float(d.strip()) for d in sphere_diameters.split(",") if d.strip()]
    except ValueError:
        raise typer.BadParameter("Sphere diameters must be numbers (e.g. 3,5,10)")

    for ds in datasets:
        if not ds.is_dir():
            raise typer.BadParameter(f"Dataset not found: {ds}")

    typer.echo("iEEG Structural Connectivity Pipeline")
    typer.echo(f"  Datasets:          {[d.name for d in datasets]}")
    typer.echo(f"  Sphere diameters:  {sphere_dias}")

    from dwi_preprocessing.ieeg_pipeline import run_ieeg_pipeline

    run_ieeg_pipeline(
        dataset_paths=datasets,
        config_path=config,
        sphere_diameters=sphere_dias,
        n_streamlines=n_streamlines,
    )

    typer.echo("\nProcessing complete!")


if __name__ == "__main__":
    app()
