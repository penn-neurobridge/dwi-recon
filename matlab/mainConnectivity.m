function mainConnectivity(sub, fileloc_path, BIDS_path, dwi_repo_path)

% Read file locations and subject information
fileloc = readtable(fileloc_path, 'Delimiter', 'comma');
rid = fileloc.sub{sub};

% Add necessary paths
addpath(genpath(dwi_repo_path));

% Create preprocessDWI object
subject = preprocessDWI;
subject.fmapReversed = fileloc.topup{sub};
subject.dwi = fileloc.dwi{sub};
subject.bval = fileloc.bval{sub};
subject.bvec = fileloc.bvec{sub};
subject.t1mri = fileloc.T1w{sub};
subject.output = fullfile(BIDS_path, rid, 'derivatives');
subject.freeSurferDir = fullfile(subject.output, 'freesurfer');

data_for_tracking.dwi_eddy = fullfile(subject.output, ...
'preprocessDWI', 'topupEddy', 'dwi_eddy.nii.gz');
mustBeFile(data_for_tracking.dwi_eddy);

data_for_tracking.dwi_eddy_bvec = fullfile(subject.output, ...
'preprocessDWI', 'topupEddy', 'dwi_eddy.eddy_rotated_bvecs');
mustBeFile(data_for_tracking.dwi_eddy_bvec);

% 1. Register DWI data to T1-weighted MRI
data_for_tracking = subject.registerEPI2t1(data_for_tracking);

% 2. Convert NIFTI format to SRC for tractography
data_for_tracking = subject.nifti2src(data_for_tracking);

% 3. Convert SRC to GQI - a specific diffusion data format
data_for_tracking = subject.src2gqi(data_for_tracking);

% 4. Run fiber tracking algorithms
data_for_tracking.nStreamlines = 2500000; % Set the number of streamlines
data_for_tracking = subject.fiberTracking(data_for_tracking);

% 5. Load Atlas and Get ROI Coordinates
atlas_name = 'aparc+aseg';
lookupTable = 'atlas_lookuptable/desikanKilliany.csv';
data_for_tracking = subject.getROICord(data_for_tracking, atlas_name, lookupTable);

% 6. Create Connectivity Matrix
atlas_name = 'desikanKilliany';
atlas_file = [subject.freeSurferDir '/mri/aparc+aseg.nii.gz'];
lookupTable = 'atlas_lookuptable/desikanKilliany.csv';
data_for_tracking = subject.atlasConnectivity(data_for_tracking, atlas_name, atlas_file, lookupTable);

% This DSI because it has load rois with parcel numbers 
subject.dsiStudio = 'singularity exec -B /var,/run -B /project/davis_group_1/nishants /project/davis_group_1/nishants/dsistudio_latest.sif  dsi_studio';

% Lausanne2018: Scale1
atlas_name = 'lausanne2018scale1';
atlas_file = [subject.freeSurferDir '/mri/lausanne2018.scale1.nii.gz'];
lookupTable = 'atlas_lookuptable/lausanne2018scale1.csv';
data_for_tracking = subject.atlasConnectivity(data_for_tracking, atlas_name, atlas_file, lookupTable);

% Lausanne2018: Scale2
atlas_name = 'lausanne2018scale2';
atlas_file = [subject.freeSurferDir '/mri/lausanne2018.scale2.nii.gz'];
lookupTable = 'atlas_lookuptable/lausanne2018scale2.csv';
data_for_tracking = subject.atlasConnectivity(data_for_tracking, atlas_name, atlas_file, lookupTable);

% Lausanne2018: Scale3
atlas_name = 'lausanne2018scale3';
atlas_file = [subject.freeSurferDir '/mri/lausanne2018.scale3.nii.gz'];
lookupTable = 'atlas_lookuptable/lausanne2018scale3.csv';
data_for_tracking = subject.atlasConnectivity(data_for_tracking, atlas_name, atlas_file, lookupTable);

% Lausanne2018: Scale4
atlas_name = 'lausanne2018scale4';
atlas_file = [subject.freeSurferDir '/mri/lausanne2018.scale4.nii.gz'];
lookupTable = 'atlas_lookuptable/lausanne2018scale4.csv';
data_for_tracking = subject.atlasConnectivity(data_for_tracking, atlas_name, atlas_file, lookupTable);

% Lausanne2018: Scale5
atlas_name = 'lausanne2018scale5';
atlas_file = [subject.freeSurferDir '/mri/lausanne2018.scale5.nii.gz'];
lookupTable = 'atlas_lookuptable/lausanne2018scale5.csv';
data_for_tracking = subject.atlasConnectivity(data_for_tracking, atlas_name, atlas_file, lookupTable);

end