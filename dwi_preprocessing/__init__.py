"""DWI minimum preprocessing pipeline.

Two separate pipelines:
  - DWIPipeline / run_dwi_pipeline:   core DWI (all subjects)
  - IEEGPipeline / run_ieeg_pipeline: iEEG connectivity (electrode subjects only)
"""

from dwi_preprocessing.config import Config
from dwi_preprocessing.pipeline import DWIPipeline, run_dwi_pipeline
from dwi_preprocessing.ieeg_pipeline import IEEGPipeline, run_ieeg_pipeline
