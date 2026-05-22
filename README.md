# DWI Minimum Preprocessing Pipeline

A MATLAB-based pipeline for preprocessing diffusion-weighted imaging (DWI) data, with specialized support for iEEG integration and connectivity analysis.

## Core Components

### Main Processing Scripts
- `preprocessDWI.m`: Core preprocessing class implementing field map generation, eddy current correction, registration, and connectivity analysis methods
- `mainEddy.m`: Streamlined pipeline for correcting eddy currents, motion, and susceptibility-induced distortions in DWI data
- `mainConnectivity.m`: End-to-end pipeline for structural connectivity analysis, including tractography and connectivity matrix generation
- `iEEGsc.m`: Specialized class for iEEG-DWI integration, electrode processing, and connectivity analysis
- `preprocessDWI.py`: Python implementation of the preprocessing pipeline (in development)

### Dependencies
- `charToCartesian.m`: Converts phase encoding directions between different coordinate systems
- `vox2ras_tkreg.m`: Transforms voxel coordinates to RAS space using FreeSurfer convention
- `vox2ras_0to1.m`: Converts between 0-based and 1-based voxel coordinate systems
- `read_surf.m`: Reads FreeSurfer surface files for visualization and analysis
- `plotinMultipleViews.m`: Creates multi-view visualizations of brain data
- `json_read.m`: Parses BIDS-compliant JSON metadata files
- `inpolyhedron.m`: Tests if points lie within a 3D polyhedron for electrode localization
- `fread3.m`: Reads FreeSurfer binary file format
- `b02b0.cnf`, `b02b0_1.cnf`: Configuration files for FSL's TOPUP distortion correction

### Atlas Support
- Desikan-Killiany Atlas (`desikanKilliany.csv`): 68-region cortical parcellation
- Lausanne 2018 Atlas (Scales 2-5): Multi-scale cortical parcellation
  - `lausanne2018.scale2.annot`: ~250 regions
  - `lausanne2018.scale3.annot`: ~500 regions
  - `lausanne2018.scale4.annot`: ~1000 regions
  - `lausanne2018.scale5.annot`: ~2000 regions

## Software Dependencies

### Required Software
- MATLAB (R2019b or newer)
  - Statistics and Machine Learning Toolbox
  - Parallel Computing Toolbox (recommended)

### External Software
- FSL (6.0 or newer)
  - Required components: topup, eddy_openmp, bet, flirt
  - Environment variables: FSLDIR, FSLOUTPUTTYPE

- FreeSurfer (7.0 or newer)
  - Required for surface reconstruction and registration
  - Environment variables: FREESURFER_HOME, SUBJECTS_DIR

- DSI Studio (latest version)
  - Required for fiber tracking and connectivity analysis
  - Supports both GUI and command-line operations

### Optional Software
- Docker (latest stable version)
  - Required for Synb0-DisCo container
  - Used for synthetic b0 generation

- Singularity (3.0 or newer)
  - Alternative to Docker for HPC environments
  - Required for synthetic field map generation

## Author
Nishant Sinha

## Contact
nishants@seas.upenn.edu

## License
MIT License - See LICENSE file for details

## Core Class Methods (preprocessDWI.m)

### Constructor
- `preprocessDWI()`: Initializes preprocessing environment and loads configurations from setup_environment.json

### Field Map Processing
- `synth_fieldmap()`: Generates synthetic field maps using Docker-based Synb0-DisCo
- `synth_fieldmap_singularity()`: Alternative synthetic field map generation using Singularity
- `fieldmap()`: Processes traditional field maps from magnitude and phase images

### Eddy Current & Motion Correction
- `topupEddy()`: Applies FSL's TOPUP and eddy correction using reversed phase-encode pairs
- `synth_topupEddy()`: Combines synthetic field maps with eddy correction
- `eddyFSL()`: Performs standard FSL eddy current correction

### Registration & Format Conversion
- `registerEPI2t1()`: Registers DWI data to T1-weighted structural space using boundary-based registration
- `nifti2src()`: Converts NIFTI format to DSI Studio's SRC format
- `src2gqi()`: Converts SRC format to GQI reconstruction

### Tractography
- `fiberTracking()`: Performs whole-brain fiber tractography
- `fiberTracking_ittr()`: Iterative fiber tracking with advanced options
- `alligntracts2T1()`: Aligns computed tracts to T1 space

### ROI & Connectivity Analysis
- `getROICord()`: Extracts ROI coordinates from atlas data
- `filterTractsbyAtlas()`: Filters tractography based on atlas ROIs
- `atlasConnectivity()`: Generates connectivity matrices using atlas parcellation
- `connectROI()`: Creates detailed connectivity metrics between ROIs

### Quality Assurance
Each method includes built-in validation checks and generates quality control outputs where applicable.