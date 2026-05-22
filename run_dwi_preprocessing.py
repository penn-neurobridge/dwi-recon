#!/usr/bin/env python3
"""CLI entry point for the core DWI preprocessing pipeline.

Operates on per-subject dataset directories (Penn-Neurobridge layout):
each dataset root contains primary/ (raw BIDS) and derivatives/ (outputs).
Full chain: eddy -> register -> reconstruct -> tracking -> alignment -> atlas.

Usage:
  # Full DWI pipeline on one dataset
  uv run dwi-preprocess -i /path/to/PennEPI000

  # Multiple datasets (comma-separated)
  uv run dwi-preprocess -i /path/to/PennEPI000,/path/to/PennEPI001

  # Skip eddy (e.g. eddy outputs already present), start at registration
  uv run dwi-preprocess -i /path/to/PennEPI000 \\
      --steps register,reconstruct,tracking,alignment,atlas
"""

from pathlib import Path
from typing import Optional

import typer

from dwi_preprocessing.pipeline import ALL_STEPS

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
    datasets = [Path(p.strip()) for p in dataset_path.split(",") if p.strip()]
    step_list = [s.strip() for s in steps.split(",") if s.strip()]

    invalid = set(step_list) - set(ALL_STEPS)
    if invalid:
        raise typer.BadParameter(f"Invalid steps: {invalid}. Valid: {ALL_STEPS}")

    for ds in datasets:
        if not ds.is_dir():
            raise typer.BadParameter(f"Dataset not found: {ds}")
        if not (ds / "primary").is_dir():
            raise typer.BadParameter(f"No primary/ under {ds}")

    typer.echo("DWI Preprocessing Pipeline")
    typer.echo(f"  Datasets:     {[d.name for d in datasets]}")
    typer.echo(f"  Steps:        {step_list}")
    typer.echo(f"  Streamlines:  {n_streamlines}")

    from dwi_preprocessing.pipeline import run_dwi_pipeline

    run_dwi_pipeline(
        dataset_paths=datasets,
        steps=step_list,
        config_path=config,
        n_streamlines=n_streamlines,
    )

    typer.echo("\nProcessing complete!")


if __name__ == "__main__":
    app()
