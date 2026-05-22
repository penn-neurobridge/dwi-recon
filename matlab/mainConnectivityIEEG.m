function mainConnectivityIEEG(subjects, BIDS_path, dwi_repo_path)
% mainConnectivityIEEG  Generate iEEG structural connectivity for subjects
%   that already have completed DWI preprocessing (eddy, src2gqi, fiberTracking,
%   EPI-to-T1 registration). Runs only the steps needed for iEEG connectivity:
%     1. fiberTracking_ittr  (whole_brain_trk.mat + whole_brain_trksubVox.mat)
%     2. alligntracts2T1     (trk_to_t1surfRAS.txt)
%     3. iEEGsc pipeline     (connectivityIEEG/)
%
% Usage (test with one subject first):
%   subjects = {'sub-PennEPIxxx'};
%   BIDS_path = '/path/to/bids';
%   dwi_repo_path = '/path/to/dwi_minimum_preprocessing';
%   mainConnectivityIEEG(subjects, BIDS_path, dwi_repo_path);
%
% Multiple subjects:
%   subjects = {'sub-PennEPIxxx','sub-PennEPIyyy','sub-PennEPIzzz'};
%   mainConnectivityIEEG(subjects, BIDS_path, dwi_repo_path);

addpath(genpath(dwi_repo_path));

for s = 1:numel(subjects)
    rid = subjects{s};
    fprintf('\n========== Processing %s (%d/%d) ==========\n', rid, s, numel(subjects));

    output = fullfile(BIDS_path, rid, 'derivatives');

    %% Verify prerequisites
    mustBeFolder(fullfile(output, 'freesurfer'));
    mustBeFolder(fullfile(output, 'preprocessDWI', 'dsiStudio'));
    mustBeFile(fullfile(output, 'ieeg_recon', 'module3', 'electrodes2ROI.csv'));

    %% Create preprocessDWI object (loads config from setup_environment.json)
    subject = preprocessDWI;
    subject.output = output;
    subject.freeSurferDir = fullfile(output, 'freesurfer');

    %% Populate data_for_tracking from existing preprocessed files
    data_for_tracking = struct();

    % GQI fib file
    dwi_fib_info = dir(fullfile(output, 'preprocessDWI', 'dsiStudio', '*gqi*fib.gz'));
    assert(~isempty(dwi_fib_info), 'No fib.gz found for %s', rid);
    data_for_tracking.dwi_fib = fullfile(dwi_fib_info.folder, dwi_fib_info.name);

    % FA map (needed by alligntracts2T1)
    data_for_tracking.dwi_fib_fa = [data_for_tracking.dwi_fib '.dti_fa.nii.gz'];
    mustBeFile(data_for_tracking.dwi_fib_fa);

    % EPI-to-T1 registration matrix
    data_for_tracking.dwi_to_freesurferT1 = fullfile(output, ...
        'connectivityDWI', 'bbr2freesurferT1', 'dwi_to_t1.txt');
    mustBeFile(data_for_tracking.dwi_to_freesurferT1);

    % Tractography settings
    data_for_tracking.nStreamlines = 2500000;

    %% Step 1: Generate whole_brain_trk.mat and whole_brain_trksubVox.mat
    fprintf('  [1/3] fiberTracking_ittr (trk + trksubVox)...\n');
    data_for_tracking = subject.fiberTracking_ittr(data_for_tracking, 'saveTrksubVox');

    %% Step 2: Align tracts to T1 surface RAS
    fprintf('  [2/3] alligntracts2T1...\n');
    data_for_tracking = subject.alligntracts2T1(data_for_tracking);

    %% Step 3: iEEG electrode-level structural connectivity
    fprintf('  [3/3] iEEG connectivity (grey2white, edgeList, matrix)...\n');
    sub_IEEGDWI = iEEGsc(output);

    electrodes = sub_IEEGDWI.iEEGgrey2white;

    sphereDia = 3;
    edgeList = sub_IEEGDWI.makeEdgeList(electrodes, sphereDia);
    sub_IEEGDWI.makeConnectivityMatrix(edgeList, sphereDia);

    sphereDia = 5;
    edgeList = sub_IEEGDWI.makeEdgeList(electrodes, sphereDia);
    sub_IEEGDWI.makeConnectivityMatrix(edgeList, sphereDia);

    fprintf('  Done: %s\n', rid);
end

fprintf('\n========== All subjects complete ==========\n');

end
