function mainEddy(sub, fileloc_path, BIDS_path, dwi_repo_path)
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
    
    % Read JSON metadata
    json.dwi = json_read(string(fileloc.json{sub}));
    
    % Determine phase encoding information
    try
        [vec, vec_neg] = charToCartesian(json.dwi.PhaseEncodingDirection);
    catch
        [vec, vec_neg] = charToCartesian(json.dwi.PhaseEncodingAxis);
    end
    
    % Determine total readout time
    try
        totalReadoutTime = json.dwi.TotalReadoutTime;
    catch
        totalReadoutTime = json.dwi.EstimatedTotalReadoutTime;
    end
    
    % Handle different cases based on fmapReversed and other conditions
    preprocessDir = fullfile(subject.output, 'preprocessDWI');
    if isfile(subject.fmapReversed)
        % Case 1: Topup correction using fmapReversed
        prepareAcqParams(preprocessDir, vec, vec_neg, totalReadoutTime);
        data_for_eddy = prepareDataForEddy(dwi_repo_path, preprocessDir);
        subject.topupEddy(data_for_eddy);
    elseif isfile(subject.fmapMag) && isfile(subject.fmapPhase)
        % Case 2: Field map correction
        prepareAcqParams(preprocessDir, vec, [], totalReadoutTime);
        data_for_eddy = subject.fieldmap;
        % subject.eddyFSL(data_for_eddy); % Uncomment if needed
    else
        % Case 3: Synthetic fieldmap and topup
        prepareAcqParams(preprocessDir, vec, vec_neg, totalReadoutTime);
        data_for_eddy = prepareDataForEddy(dwi_repo_path, preprocessDir);
        data_for_eddy = subject.synth_fieldmap_singularity(data_for_eddy);
        subject.synth_topupEddy(data_for_eddy);
    end
end

%% Helper Functions
function prepareAcqParams(preprocessDir, vec, vec_neg, totalReadoutTime)
    % Prepare acquisition parameters for eddy correction
    if ~exist(preprocessDir, 'dir')
        mkdir(preprocessDir);
    end
    if isempty(vec_neg)
        acq = [vec, totalReadoutTime];
    else
        acq = [vec, totalReadoutTime; vec_neg, totalReadoutTime];
    end
    writematrix(acq, fullfile(preprocessDir, 'acqparams.txt'), 'Delimiter', 'space');
end

function data_for_eddy = prepareDataForEddy(dwi_repo_path, preprocessDir)
    % Prepare data structure for eddy correction
    data_for_eddy.acqparams = fullfile(preprocessDir, 'acqparams.txt');
    data_for_eddy.b02b0 = fullfile(dwi_repo_path, 'matlab', 'dependencies', 'b02b0.cnf');
    data_for_eddy.b02b0_1 = fullfile(dwi_repo_path, 'matlab', 'dependencies', 'b02b0_1.cnf');
end
