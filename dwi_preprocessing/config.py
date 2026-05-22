"""Configuration loader for DWI preprocessing pipeline.

Reads setup_environment.json from the repository root and sets up
environment variables for FSL, FreeSurfer, and DSI Studio.
"""

import json
import os
from pathlib import Path


class Config:
    """Loads setup_environment.json and exposes tool paths."""

    def __init__(self, config_path: str | Path | None = None):
        if config_path is None:
            # Default: repo_root/setup_environment.json
            # __file__ is dwi_preprocessing/config.py -> parent.parent = repo root
            repo_root = Path(__file__).resolve().parent.parent
            config_path = repo_root / "setup_environment.json"

        config_path = Path(config_path)
        if not config_path.is_file():
            raise FileNotFoundError(f"Config not found: {config_path}")

        with open(config_path) as f:
            self._data = json.load(f)

        self.repo_root = config_path.parent

        # Tool locations
        self.fsl_loc = self._data["fslLoc"]
        self.freesurfer_loc = self._data["freeSurferLoc"]
        self.dsi_studio = self._data["dsiStudio"]
        self.docker_synb0disco = self._data.get("dockerSynb0disco", "")
        self.singularity_loc = self._data.get("singularityLoc", "").strip()

        # Set environment variables
        self._setup_env()

    def _setup_env(self):
        """Set FSL and FreeSurfer environment variables."""
        os.environ["FSLDIR"] = self._data["FSLDIR"]
        os.environ["FSLOUTPUTTYPE"] = self._data["FSLOUTPUTTYPE"]
        os.environ["FREESURFER_HOME"] = self._data["FREESURFER_HOME"]
        os.environ["SUBJECTS_DIR"] = self._data["SUBJECTS_DIR"]

        if "FS_LICENSE" in self._data:
            os.environ["FS_LICENSE"] = self._data["FS_LICENSE"]
        if "SURFER_FRONTDOOR" in self._data:
            os.environ["SURFER_FRONTDOOR"] = self._data["SURFER_FRONTDOOR"]

    def fsl(self, tool: str) -> str:
        """Return full path to an FSL tool, e.g. config.fsl('flirt')."""
        return os.path.join(self.fsl_loc, tool)

    def fs(self, tool: str) -> str:
        """Return full path to a FreeSurfer tool, e.g. config.fs('mri_convert')."""
        return os.path.join(self.freesurfer_loc, tool)
