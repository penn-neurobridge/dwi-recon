%% FSL Setup

setenv( 'FSLDIR', '/usr/local/fsl' );
setenv('FSLOUTPUTTYPE', 'NIFTI_GZ');
fsldir = getenv('FSLDIR');
fsldirmpath = sprintf('%s/etc/matlab',fsldir);
path(path, fsldirmpath);
clear fsldir fsldirmpath;

%% Add dependencies

addpath(genpath('/Users/nishant/Dropbox/Sinha/Lab/Research/dwi_preprocess/dependencies'));

%% Freesurfer setup

setenv( 'FREESURFER_HOME', '/Applications/freesurfer/7.3.2/' );
setenv('SUBJECTS_DIR', '/Users/nishant/Dropbox/Database/UPenn/Epilepsy/');
FREESURFER_HOME = getenv('FREESURFER_HOME');
freesurferdirmpath = sprintf('%s/SetUpFreeSurfer.sh',FREESURFER_HOME);
system(['sh ' freesurferdirmpath],'-echo');
clear freesurferdirmpath FREESURFER_HOME;