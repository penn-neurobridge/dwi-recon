#!/usr/bin/env python3
"""Single entry point for the DWI processing and iEEG reconstruction pipeline.

Two subcommands, mirroring the two pipelines:

  dwi   — core DWI pipeline (eddy → register → reconstruct → tracking →
          alignment → atlas). Runs for every subject.
  ieeg  — iEEG structural connectivity. Electrode subjects only.

Each operates on a per-subject dataset directory containing primary/ (raw
BIDS) and derivatives/ (outputs).

Usage:
  uv run run_dwi_recon.py dwi  -i /data/PennEPI000
  uv run run_dwi_recon.py ieeg -i /data/PennEPI001 --sphere-diameters 3,5

In Docker (entrypoint is this script):
  docker run -v /local/PennEPI000:/data dwi-recon dwi  -i /data
  docker run -v /local/PennEPI001:/data dwi-recon ieeg -i /data
"""

from pathlib import Path
from typing import Optional

import typer

from dwi_preprocessing.pipeline import ALL_STEPS

app = typer.Typer(
    add_completion=False,
    help="DWI processing and iEEG reconstruction pipeline",
)


def _datasets(dataset_path: str) -> list[Path]:
    datasets = [Path(p.strip()) for p in dataset_path.split(",") if p.strip()]
    for ds in datasets:
        if not ds.is_dir():
            raise typer.BadParameter(f"Dataset not found: {ds}")
    return datasets


@app.command()
def dwi(
    dataset_path: str = typer.Option(
        ..., "-i", "--dataset-path",
        help="Dataset root(s) with primary/ and derivatives/ (comma-separated)",
    ),
    config: Optional[Path] = typer.Option(
        None, "-c", "--config", exists=True, dir_okay=False,
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
    """Core DWI pipeline (eddy, register, reconstruct, tracking, alignment, atlas)."""
    datasets = _datasets(dataset_path)
    step_list = [s.strip() for s in steps.split(",") if s.strip()]
    invalid = set(step_list) - set(ALL_STEPS)
    if invalid:
        raise typer.BadParameter(f"Invalid steps: {invalid}. Valid: {ALL_STEPS}")

    typer.echo("DWI Preprocessing")
    typer.echo(f"  Datasets:    {[d.name for d in datasets]}")
    typer.echo(f"  Steps:       {step_list}")
    typer.echo(f"  Streamlines: {n_streamlines}")

    from dwi_preprocessing.pipeline import run_dwi_pipeline
    run_dwi_pipeline(
        dataset_paths=datasets, steps=step_list,
        config_path=config, n_streamlines=n_streamlines,
    )
    typer.echo("\nProcessing complete!")


@app.command()
def ieeg(
    dataset_path: str = typer.Option(
        ..., "-i", "--dataset-path",
        help="Dataset root(s) with primary/ and derivatives/ (comma-separated)",
    ),
    config: Optional[Path] = typer.Option(
        None, "-c", "--config", exists=True, dir_okay=False,
        help="Path to setup_environment.json",
    ),
    sphere_diameters: str = typer.Option(
        "3,5", "--sphere-diameters",
        help="Comma-separated sphere diameters in mm",
    ),
    n_streamlines: int = typer.Option(
        2_500_000, "--n-streamlines",
        help="Streamline count (only if DWI tracking needs to re-run)",
    ),
):
    """iEEG structural connectivity (electrode subjects only)."""
    datasets = _datasets(dataset_path)
    try:
        sphere_dias = [float(d.strip()) for d in sphere_diameters.split(",") if d.strip()]
    except ValueError:
        raise typer.BadParameter("Sphere diameters must be numbers (e.g. 3,5,10)")

    typer.echo("iEEG Structural Connectivity")
    typer.echo(f"  Datasets:         {[d.name for d in datasets]}")
    typer.echo(f"  Sphere diameters: {sphere_dias}")

    from dwi_preprocessing.ieeg_pipeline import run_ieeg_pipeline
    run_ieeg_pipeline(
        dataset_paths=datasets, config_path=config,
        sphere_diameters=sphere_dias, n_streamlines=n_streamlines,
    )
    typer.echo("\nProcessing complete!")


if __name__ == "__main__":
    app()
