classdef preprocessDWI
    %preprocessDWI Class for preprocessing diffusion-weighted imaging (DWI) data.
    % This class includes methods for generating and applying field maps, 
    % running eddy current corrections, and aligning tractography data 
    % with structural MRI. It is designed to support various stages of DWI 
    % data processing in neuroimaging research.

     properties
        % Properties to store file paths and other relevant parameters.
        fmapMag = ''                % Field map magnitude [optional]
        fmapPhase = ''              % Field map phase [optional]
        fmapReversed          % Reversed field map for TOPUP
        dwi                          % Diffusion-weighted imaging data
        bval                         % B-values for DWI data
        bvec                        % B-vectors for DWI data
        t1mri                       % T1-weighted MRI data
        output                     % Output directory path
        freeSurferDir           % FreeSurfer directory path
        freeSurferLoc          % FreeSurfer executable location
        fslLoc                      % FSL executable location
        dsiStudio                 % DSI Studio executable location
        dockerSynb0disco   % Docker location for Synb0-DisCo
        singularityLoc      % singularity executable location
        
    end
    
    methods
        % Methods for different stages of DWI data processing.

        function obj = preprocessDWI()
            % Load JSON configuration
            configFile = fullfile(fileparts(pwd), 'setup_environment.json');
            configData = jsondecode(fileread(configFile));

            % Assign properties from JSON
            obj.freeSurferLoc = configData.freeSurferLoc;
            obj.fslLoc = configData.fslLoc;
            obj.dsiStudio = configData.dsiStudio;
            obj.dockerSynb0disco = configData.dockerSynb0disco;
            obj.singularityLoc = configData.singularityLoc;

            % FSL Setup
            setenv('FSLDIR', configData.FSLDIR);
            setenv('FSLOUTPUTTYPE', configData.FSLOUTPUTTYPE);
            fsldir = getenv('FSLDIR');
            fsldirmpath = sprintf('%s/etc/matlab', fsldir);
            path(path, fsldirmpath);
            clear fsldir fsldirmpath;

            % Add dependencies
            addpath(genpath(configData.DEPENDENCIES_PATH));

            % Freesurfer setup
            setenv('FREESURFER_HOME', configData.FREESURFER_HOME);
            setenv('SUBJECTS_DIR', configData.SUBJECTS_DIR);
            FREESURFER_HOME = getenv('FREESURFER_HOME');
            freesurferdirmpath = sprintf('%s/SetUpFreeSurfer.sh', FREESURFER_HOME);
            system(['sh ' freesurferdirmpath], '-echo');
            clear freesurferdirmpath FREESURFER_HOME;
        end
 

        function data_for_eddy = synth_fieldmap(obj,data_for_eddy)
            % Generates a synthetic field map for DWI data.
            try

                mustBeFile(fullfile(obj.output, 'preprocessDWI/synthetic_fmap/OUTPUTS/b0_u.nii.gz'));
                data_for_eddy.synthb0undistorted = fullfile(obj.output, 'preprocessDWI/synthetic_fmap/OUTPUTS/b0_u.nii.gz');

            catch

                mkdir(obj.output, 'preprocessDWI/synthetic_fmap/INPUTS');
                mkdir(obj.output, 'preprocessDWI/synthetic_fmap/OUTPUTS');

                % Extract a b0 volume from dwi
                b0 = fullfile(obj.output, 'preprocessDWI/synthetic_fmap/INPUTS/b0');
                cmd = [obj.fslLoc '/fslroi ' obj.dwi ' ' b0 ' 0 1'];
                system(cmd, '-echo');

                copyfile(obj.t1mri, fullfile(obj.output, 'preprocessDWI/synthetic_fmap/INPUTS/T1.nii.gz'));
                copyfile(data_for_eddy.acqparams, fullfile(obj.output, 'preprocessDWI/synthetic_fmap/INPUTS/acqparams.txt'));

                cmd = [obj.dockerSynb0disco ...
                    ' run --rm' ...
                    ' -v ' [obj.output, '/preprocessDWI/synthetic_fmap/INPUTS/:/INPUTS/'] ...
                    ' -v ' [obj.output, '/preprocessDWI/synthetic_fmap/OUTPUTS/:/OUTPUTS/'] ...
                    ' -v ' [fileparts(obj.freeSurferLoc) '/license.txt:/extra/freesurfer/license.txt'] ...
                    ' --user $(id -u):$(id -g)' ...
                    ' leonyichencai/synb0-disco:v3.0' ...
                    ' --notopup'];

                system(cmd, '-echo');

                data_for_eddy.synthb0undistorted = fullfile(obj.output, 'preprocessDWI/synthetic_fmap/OUTPUTS/b0_u.nii.gz');

            end

        end


        function data_for_eddy = synth_fieldmap_singularity(obj,data_for_eddy)
            % Alternative method to generate a synthetic field map using singularity.

            try

                mustBeFile(fullfile(obj.output, 'preprocessDWI/synthetic_fmap/OUTPUTS/b0_u.nii.gz'));
                data_for_eddy.synthb0undistorted = fullfile(obj.output, 'preprocessDWI/synthetic_fmap/OUTPUTS/b0_u.nii.gz');

            catch

                mkdir(obj.output, 'preprocessDWI/synthetic_fmap/INPUTS');
                mkdir(obj.output, 'preprocessDWI/synthetic_fmap/OUTPUTS');

                % Extract a b0 volume from dwi
                b0 = fullfile(obj.output, 'preprocessDWI/synthetic_fmap/INPUTS/b0');
                cmd = [obj.fslLoc '/fslroi ' obj.dwi ' ' b0 ' 0 1'];
                system(cmd, '-echo');

                copyfile(obj.t1mri, fullfile(obj.output, 'preprocessDWI/synthetic_fmap/INPUTS/T1.nii.gz'));
                copyfile(data_for_eddy.acqparams, fullfile(obj.output, 'preprocessDWI/synthetic_fmap/INPUTS/acqparams.txt'));

                cmd = [obj.singularityLoc '/singularity run -e --env SURFER_FRONTDOOR=1 ' ...
                    ' -B ' [obj.output, '/preprocessDWI/synthetic_fmap/OUTPUTS:/scratch'] ...
                    ' -B ' [obj.output, '/preprocessDWI/synthetic_fmap/INPUTS:/INPUTS'] ...
                    ' -B ' [obj.output, '/preprocessDWI/synthetic_fmap/OUTPUTS:/OUTPUTS'] ...
                    ' -B ' [fileparts(obj.freeSurferLoc) '/license.txt:/extra/freesurfer/license.txt '] ...
                    obj.dockerSynb0disco ...
                    ' --notopup'];

                system(cmd, '-echo');

                data_for_eddy.synthb0undistorted = fullfile(obj.output, 'preprocessDWI/synthetic_fmap/OUTPUTS/b0_u.nii.gz');

            end

        end

        function data_for_tracking = synth_topupEddy(obj, data_for_eddy)
            % Applies TOPUP and Eddy correction using synthetic field map.

            mkdir(obj.output, 'preprocessDWI/topupEddy');

            try

                mustBeFile(fullfile(obj.output, 'preprocessDWI/topupEddy/dwi_eddy.nii.gz'));
                mustBeFile(fullfile(obj.output, 'preprocessDWI/topupEddy/dwi_eddy.eddy_rotated_bvecs'));

                data_for_tracking.dwi_eddy = fullfile(obj.output, 'preprocessDWI/topupEddy/dwi_eddy.nii.gz');
                data_for_tracking.dwi_eddy_bvec = fullfile(obj.output, 'preprocessDWI/topupEddy/dwi_eddy.eddy_rotated_bvecs');

            catch
                %% Extract a b0 volume from dwi                
                nodif = fullfile(obj.output, 'preprocessDWI/topupEddy/nodif');
                cmd = [obj.fslLoc '/fslroi ' obj.dwi ' ' nodif ' 0 1'];
                system(cmd, '-echo');

                %% Copy undistorted B0 from synth_fieldmap

                copyfile(data_for_eddy.synthb0undistorted, fullfile(obj.output, 'preprocessDWI/topupEddy/nodif_PA.nii.gz'))
                nodif_PA = fullfile(obj.output, 'preprocessDWI/topupEddy/nodif_PA');
%                 cmd = [obj.fslLoc '/fslroi ' obj.fmapReversed ' ' nodif_PA ' 0 1'];
%                 system(cmd, '-echo');

                %% Megre distorted and undistorted b0 into a single image
                AP_PA_b0 = fullfile(obj.output, 'preprocessDWI/topupEddy/AP_PA_b0');
                cmd = [obj.fslLoc '/fslmerge -t ' AP_PA_b0 ' ' nodif ' ' nodif_PA];
                system(cmd, '-echo');

                %% Apply topup

                topup_AP_PA_b0 = [obj.output '/preprocessDWI/topupEddy/topup_AP_PA_b0'];
                topup_AP_PA_b0_iout = [obj.output '/preprocessDWI/topupEddy/topup_AP_PA_b0_iout'];
                topup_AP_PA_b0_fout = [obj.output '/preprocessDWI/topupEddy/topup_AP_PA_b0_fout'];

                cmd = [obj.fslLoc '/topup' ...
                    ' --imain=' AP_PA_b0 ...
                    ' --datain=' data_for_eddy.acqparams ...
                    ' --config=' data_for_eddy.b02b0_1 ...
                    ' --out=' topup_AP_PA_b0 ...
                    ' --iout=' topup_AP_PA_b0_iout ...
                    ' --fout=' topup_AP_PA_b0_fout ...
                    ' --verbose'];

                system(cmd, '-echo');

                %% Make average image of the corrected b0 volumes

                hifi_nodif = [obj.output '/preprocessDWI/topupEddy/hifi_nodif'];
                cmd = [obj.fslLoc '/fslmaths ' topup_AP_PA_b0_iout ' -Tmean ' hifi_nodif];
                system(cmd, '-echo');

                %% Generate a brain mask using the corrected b0
                hifi_nodif_brain = [obj.output '/preprocessDWI/topupEddy/hifi_nodif_brain'];

                cmd = [obj.fslLoc '/bet ' hifi_nodif ' ' hifi_nodif_brain ' -m -f 0.2'];
                system(cmd, '-echo');

                %% Run Eddy
                dwi_eddy = [obj.output '/preprocessDWI/topupEddy/dwi_eddy'];

                idx = importdata(obj.bval);
                idx = ones(numel(idx), 1);
                writematrix(idx, [obj.output '/preprocessDWI/topupEddy/index.txt'], 'Delimiter', 'space');
                data_for_eddy.index = [obj.output '/preprocessDWI/topupEddy/index.txt'];

                cmd = [obj.fslLoc '/eddy_openmp' ...
                    ' --imain=' obj.dwi ...
                    ' --mask=' hifi_nodif_brain '_mask' ...
                    ' --index=' data_for_eddy.index ...
                    ' --acqp=' data_for_eddy.acqparams ...
                    ' --bvecs=' obj.bvec ...
                    ' --bvals=' obj.bval ...
                    ' --fwhm=10,0,0,0,0' ...
                    ' --topup=' topup_AP_PA_b0 ...
                    ' --flm=quadratic' ...
                    ' --out=' dwi_eddy ...
                    ' --repol' ...
                    ' --cnr_maps' ...
                    ' --estimate_move_by_susceptibility' ...
                    ' --verbose'];

                system(cmd, '-echo');

                mustBeFile(fullfile(obj.output, 'preprocessDWI/topupEddy/dwi_eddy.nii.gz'));
                mustBeFile(fullfile(obj.output, 'preprocessDWI/topupEddy/dwi_eddy.eddy_rotated_bvecs'));

                data_for_tracking.dwi_eddy = fullfile(obj.output, 'preprocessDWI/topupEddy/dwi_eddy.nii.gz');
                data_for_tracking.dwi_eddy_bvec = fullfile(obj.output, 'preprocessDWI/topupEddy/dwi_eddy.eddy_rotated_bvecs');

            end

        end

    function data_for_eddy = fieldmap(obj)
        % Prepares and processes field map for Eddy correction.

        mkdir(obj.output, 'preprocessDWI/fieldmap');

        try

            mustBeFile(fullfile(obj.output, 'preprocessDWI/fieldmap/dwiB0.nii.gz'));

            mustBeFile(fullfile(obj.output, 'preprocessDWI/fieldmap/magnitude_brain.nii.gz'));
            mustBeFile(fullfile(obj.output, 'preprocessDWI/fieldmap/magnitude_brain_mask.nii.gz'));
            mustBeFile(fullfile(obj.output, 'preprocessDWI/fieldmap/magnitude_to_dwiB0.nii.gz'));
            mustBeFile(fullfile(obj.output, 'preprocessDWI/fieldmap/magnitude_to_dwiB0_xform.txt'));
            mustBeFile(fullfile(obj.output, 'preprocessDWI/fieldmap/magnitude_brain_mask_to_dwiB0.nii.gz'));

            mustBeFile(fullfile(obj.output, 'preprocessDWI/fieldmap/fieldmap.nii.gz'));
            mustBeFile(fullfile(obj.output, 'preprocessDWI/fieldmap/fieldmap_masked.nii.gz'));
            mustBeFile(fullfile(obj.output, 'preprocessDWI/fieldmap/fieldmap_masked_s4.nii.gz'));
            mustBeFile(fullfile(obj.output, 'preprocessDWI/fieldmap/fieldmap_masked_s4_to_dwiB0.nii.gz'));
            mustBeFile(fullfile(obj.output, 'preprocessDWI/fieldmap/fieldmap_masked_s4_to_dwiB0_Hz.nii.gz'));

            fieldmap_for_eddy = fullfile(obj.output, 'preprocessDWI/fieldmap/fieldmap_masked_s4_to_dwiB0_Hz');
            fieldmap_mask_for_eddy = fullfile(obj.output, 'preprocessDWI/fieldmap/magnitude_brain_mask_to_dwiB0.nii.gz');

            data_for_eddy.fieldmap = fieldmap_for_eddy;
            data_for_eddy.fieldmap_mask = fieldmap_mask_for_eddy;

        catch
            %% Brain extraction from fieldmap magnitude [imp: leave no nonbrain tissue]

            cmd = [obj.fslLoc '/bet ' obj.fmapMag ' ' ...
                obj.output '/preprocessDWI/fieldmap/magnitude_brain -m -f 0.7 -R -v'];

            system(cmd, '-echo');

            %% Prepare fieldmap

            cmd = [obj.fslLoc '/fsl_prepare_fieldmap' ...
                ' SIEMENS' ...
                ' ' obj.fmapPhase ...
                ' ' obj.output '/preprocessDWI/fieldmap/magnitude_brain' ...
                ' ' obj.output '/preprocessDWI/fieldmap/fieldmap' ...
                ' 2.46'];

            system(cmd, '-echo');

            %% Apply brain mask to fieldmap

            cmd = [obj.fslLoc '/fslmaths' ...
                ' ' obj.output '/preprocessDWI/fieldmap/fieldmap' ...
                ' -mas' ...
                ' ' obj.output '/preprocessDWI/fieldmap/magnitude_brain_mask' ...
                ' ' obj.output '/preprocessDWI/fieldmap/fieldmap_masked'];

            system(cmd, '-echo');

            %% Smooth fieldmap

            cmd = [obj.fslLoc '/fugue' ...
                ' --loadfmap=' obj.output '/preprocessDWI/fieldmap/fieldmap_masked' ...
                ' -s 4' ...
                ' --savefmap=' obj.output '/preprocessDWI/fieldmap/fieldmap_masked_s4'];

            system(cmd, '-echo');

            %% register magnitude image to dtidata and apply transform to fieldmap

            % extract b0 from dwi
            cmd = [obj.fslLoc '/fslroi ' obj.dwi ' ' obj.output '/preprocessDWI/fieldmap/dwiB0 0 1'];
            system(cmd, '-echo');

            % register  fmapMag with first element of dwi b0
            cmd = [obj.fslLoc '/flirt' ...
                ' -cost mutualinfo' ... % can also use the default corratio
                ' -dof 6' ...
                ' -v' ...
                ' -in ' obj.fmapMag ...
                ' -ref ' fullfile(obj.output, 'preprocessDWI/fieldmap/dwiB0') ...
                ' -out ' fullfile(obj.output, 'preprocessDWI/fieldmap/magnitude_to_dwiB0.nii.gz') ...
                ' -omat ' fullfile(obj.output, 'preprocessDWI/fieldmap/magnitude_to_dwiB0_xform.txt')];

            system(cmd, '-echo');

            % apply transform to fieldmap
            cmd = [obj.fslLoc '/flirt' ...
                ' -v' ...
                ' -in ' fullfile(obj.output, 'preprocessDWI/fieldmap/fieldmap_masked_s4') ...
                ' -ref ' fullfile(obj.output, 'preprocessDWI/fieldmap/dwiB0') ...
                ' -applyxfm' ...
                ' -init ' fullfile(obj.output, 'preprocessDWI/fieldmap/magnitude_to_dwiB0_xform.txt') ...
                ' -out ' fullfile(obj.output, 'preprocessDWI/fieldmap/fieldmap_masked_s4_to_dwiB0.nii.gz')];

            system(cmd, '-echo');

            % apply transform to corrected fieldmap mask
            cmd = [obj.fslLoc '/flirt' ...
                ' -v' ...
                ' -in ' fullfile(obj.output, 'preprocessDWI/fieldmap/magnitude_brain_mask') ...
                ' -ref ' fullfile(obj.output, 'preprocessDWI/fieldmap/dwiB0') ...
                ' -applyxfm' ...
                ' -init ' fullfile(obj.output, 'preprocessDWI/fieldmap/magnitude_to_dwiB0_xform.txt') ...
                ' -out ' fullfile(obj.output, 'preprocessDWI/fieldmap/magnitude_brain_mask_to_dwiB0.nii.gz')];

            system(cmd, '-echo');

            %% Save the filedmap in Hz for input in --field option of eddy

            cmd = [obj.fslLoc '/fslmaths' ...
                ' ' fullfile(obj.output, 'preprocessDWI/fieldmap/fieldmap_masked_s4_to_dwiB0.nii.gz') ...
                ' -div 6.28 ' ...
                ' ' fullfile(obj.output, 'preprocessDWI/fieldmap/fieldmap_masked_s4_to_dwiB0_Hz.nii.gz')];

            system(cmd, '-echo');

            %% Return file location of the field map in Hz for eddy

            fieldmap_for_eddy = fullfile(obj.output, 'preprocessDWI/fieldmap/fieldmap_masked_s4_to_dwiB0_Hz');
            fieldmap_mask_for_eddy = fullfile(obj.output, 'preprocessDWI/fieldmap/magnitude_brain_mask_to_dwiB0.nii.gz');

            data_for_eddy.fieldmap = fieldmap_for_eddy;
            data_for_eddy.fieldmap_mask = fieldmap_mask_for_eddy;

        end

    end

    function data_for_tracking = eddyFSL(obj, data_for_eddy)
        % Performs Eddy current correction using FSL.

        mkdir(obj.output, 'preprocessDWI/eddy');

        try

            mustBeFile(fullfile(obj.output, 'preprocessDWI/eddy/dwi_eddy.nii.gz'));
            mustBeFile(fullfile(obj.output, 'preprocessDWI/eddy/dwi_eddy.eddy_rotated_bvecs'));

            data_for_tracking.dwi_eddy = fullfile(obj.output, 'preprocessDWI/eddy/dwi_eddy.nii.gz');
            data_for_tracking.dwi_eddy_bvec = fullfile(obj.output, 'preprocessDWI/eddy/dwi_eddy.eddy_rotated_bvecs');

        catch
            %% Make index file

            idx = importdata(obj.bval);
            idx = ones(numel(idx), 1);
            writematrix(idx, [obj.output '/preprocessDWI/eddy/index.txt'], 'Delimiter', 'space');
            data_for_eddy.index = [obj.output '/preprocessDWI/eddy/index.txt'];

            %% Run eddy

            cmd = [obj.fslLoc '/eddy_openmp' ...
                ' --imain=' obj.dwi ...
                ' --mask=' data_for_eddy.fieldmap_mask ...
                ' --index=' data_for_eddy.index ...
                ' --acqp=' data_for_eddy.acqparams ...
                ' --bvecs=' obj.bvec ...
                ' --bvals=' obj.bval ...
                ' --fwhm=10,0,0,0,0' ...
                ' --field=' data_for_eddy.fieldmap ...
                ' --flm=quadratic' ...
                ' --out=' fullfile(obj.output, 'preprocessDWI/eddy/dwi_eddy') ...
                ' --repol' ...
                ' --cnr_maps' ...
                ' --estimate_move_by_susceptibility' ...
                ' --verbose'];

            system(cmd, '-echo');

            mustBeFile(fullfile(obj.output, 'preprocessDWI/eddy/dwi_eddy.nii.gz'));
            mustBeFile(fullfile(obj.output, 'preprocessDWI/eddy/dwi_eddy.eddy_rotated_bvecs'));

            data_for_tracking.dwi_eddy = fullfile(obj.output, 'preprocessDWI/eddy/dwi_eddy.nii.gz');
            data_for_tracking.dwi_eddy_bvec = fullfile(obj.output, 'preprocessDWI/eddy/dwi_eddy.eddy_rotated_bvecs');

        end

    end

    function data_for_tracking = topupEddy(obj, data_for_eddy)
        % Applies TOPUP and Eddy correction for DWI data.

        mkdir(obj.output, 'preprocessDWI/topupEddy');

        try

            mustBeFile(fullfile(obj.output, 'preprocessDWI/topupEddy/dwi_eddy.nii.gz'));
            mustBeFile(fullfile(obj.output, 'preprocessDWI/topupEddy/dwi_eddy.eddy_rotated_bvecs'));

            data_for_tracking.dwi_eddy = fullfile(obj.output, 'preprocessDWI/topupEddy/dwi_eddy.nii.gz');
            data_for_tracking.dwi_eddy_bvec = fullfile(obj.output, 'preprocessDWI/topupEddy/dwi_eddy.eddy_rotated_bvecs');

        catch
            %% Extract a b0 volume from dwi
            nodif = fullfile(obj.output, 'preprocessDWI/topupEddy/nodif');
            cmd = [obj.fslLoc '/fslroi ' obj.dwi ' ' nodif ' 0 1'];
            system(cmd, '-echo');

            %% Extract b0 from fmap
            nodif_PA = fullfile(obj.output, 'preprocessDWI/topupEddy/nodif_PA');
            cmd = [obj.fslLoc '/fslroi ' obj.fmapReversed ' ' nodif_PA ' 0 1'];
            system(cmd, '-echo');

            %% Megre AP and PA into a single image
            AP_PA_b0 = fullfile(obj.output, 'preprocessDWI/topupEddy/AP_PA_b0');
            cmd = [obj.fslLoc '/fslmerge -t ' AP_PA_b0 ' ' nodif ' ' nodif_PA];
            system(cmd, '-echo');

            %% Apply topup

            topup_AP_PA_b0 = [obj.output '/preprocessDWI/topupEddy/topup_AP_PA_b0'];
            topup_AP_PA_b0_iout = [obj.output '/preprocessDWI/topupEddy/topup_AP_PA_b0_iout'];
            topup_AP_PA_b0_fout = [obj.output '/preprocessDWI/topupEddy/topup_AP_PA_b0_fout'];

            cmd = [obj.fslLoc '/topup' ...
                ' --imain=' AP_PA_b0 ...
                ' --datain=' data_for_eddy.acqparams ...
                ' --config=' data_for_eddy.b02b0_1 ...
                ' --out=' topup_AP_PA_b0 ...
                ' --iout=' topup_AP_PA_b0_iout ...
                ' --fout=' topup_AP_PA_b0_fout ...
                ' --verbose'];

            system(cmd, '-echo');

            %% Make average image of the corrected b0 volumes

            hifi_nodif = [obj.output '/preprocessDWI/topupEddy/hifi_nodif'];
            cmd = [obj.fslLoc '/fslmaths ' topup_AP_PA_b0_iout ' -Tmean ' hifi_nodif];
            system(cmd, '-echo');

            %% Generate a brain mask using the corrected b0
            hifi_nodif_brain = [obj.output '/preprocessDWI/topupEddy/hifi_nodif_brain'];

            cmd = [obj.fslLoc '/bet ' hifi_nodif ' ' hifi_nodif_brain ' -m -f 0.2'];
            system(cmd, '-echo');

            %% Run Eddy
            dwi_eddy = [obj.output '/preprocessDWI/topupEddy/dwi_eddy'];

            idx = importdata(obj.bval);
            idx = ones(numel(idx), 1);
            writematrix(idx, [obj.output '/preprocessDWI/topupEddy/index.txt'], 'Delimiter', 'space');
            data_for_eddy.index = [obj.output '/preprocessDWI/topupEddy/index.txt'];

            cmd = [obj.fslLoc '/eddy_openmp' ...
                ' --imain=' obj.dwi ...
                ' --mask=' hifi_nodif_brain '_mask' ...
                ' --index=' data_for_eddy.index ...
                ' --acqp=' data_for_eddy.acqparams ...
                ' --bvecs=' obj.bvec ...
                ' --bvals=' obj.bval ...
                ' --fwhm=10,0,0,0,0' ...
                ' --topup=' topup_AP_PA_b0 ...
                ' --flm=quadratic' ...
                ' --out=' dwi_eddy ...
                ' --repol' ...
                ' --cnr_maps' ...
                ' --estimate_move_by_susceptibility' ...
                ' --verbose'];

            system(cmd, '-echo');

            mustBeFile(fullfile(obj.output, 'preprocessDWI/topupEddy/dwi_eddy.nii.gz'));
            mustBeFile(fullfile(obj.output, 'preprocessDWI/topupEddy/dwi_eddy.eddy_rotated_bvecs'));

            data_for_tracking.dwi_eddy = fullfile(obj.output, 'preprocessDWI/topupEddy/dwi_eddy.nii.gz');
            data_for_tracking.dwi_eddy_bvec = fullfile(obj.output, 'preprocessDWI/topupEddy/dwi_eddy.eddy_rotated_bvecs');

        end

    end

    function data_for_tracking = registerEPI2t1(obj, data_for_tracking)
        % Registers EPI DWI data to T1-weighted structural MRI

        outdir = fullfile(obj.output, 'connectivityDWI/bbr2freesurferT1');

        mkdir(outdir);

        try

            mustBeFile(fullfile(obj.output, 'connectivityDWI/bbr2freesurferT1', 'dwi_to_t1.txt'));
            data_for_tracking.dwi_to_freesurferT1 = fullfile(obj.output, 'connectivityDWI/bbr2freesurferT1', 'dwi_to_t1.txt');

            mustBeFile([outdir '/dwi_eddy.b0.gz.nii.gz']);
            data_for_tracking.dwi_eddy_b0 = [outdir '/dwi_eddy.b0.gz.nii.gz'];

            mustBeFile([outdir '/dwi_eddy.b0.gz.brain.nii.gz']);
            data_for_tracking.dwi_eddy_b0_brain = [outdir '/dwi_eddy.b0.gz.brain.nii.gz'];

            mustBeFile([outdir '/dwi_eddy.b0.gz.brain_mask.nii.gz']);
            data_for_tracking.dwi_eddy_b0_brain_mask = [outdir '/dwi_eddy.b0.gz.brain_mask.nii.gz'];

        catch
            %% Get the b0 volume from dMRI data
            dwi_eddy_b0 = [outdir '/dwi_eddy.b0.gz.nii.gz'];

            cmd = [obj.fslLoc '/fslroi' ...
                ' ' data_for_tracking.dwi_eddy ...
                ' ' dwi_eddy_b0 ...
                ' 0 1'];

            system(cmd, '-echo');

            %% Get the mask from dMRI data
            dwi_eddy_b0_brain = [outdir '/dwi_eddy.b0.gz.brain.nii.gz'];

            cmd = [obj.fslLoc '/bet' ...
                ' ' dwi_eddy_b0 ...
                ' ' dwi_eddy_b0_brain ...
                ' -m -f 0.1'];

            system(cmd, '-echo');

            %% Convert mgz to nii format
            wm_mgz = [obj.freeSurferDir '/mri/wm.mgz'];
            wm_nii = [obj.freeSurferDir '/mri/wm.nii.gz'];
            cmd = [obj.freeSurferLoc '/mri_convert ' wm_mgz ' ' wm_nii];
            system(cmd, '-echo');

            t1_mgz = [obj.freeSurferDir '/mri/T1.mgz'];
            t1_nii = [obj.freeSurferDir '/mri/T1.nii.gz'];
            cmd = [obj.freeSurferLoc '/mri_convert ' t1_mgz ' ' t1_nii];
            system(cmd, '-echo');

            brain_mgz = [obj.freeSurferDir '/mri/brain.mgz'];
            brain_nii = [obj.freeSurferDir '/mri/brain.nii.gz'];
            cmd = [obj.freeSurferLoc '/mri_convert ' brain_mgz ' ' brain_nii];
            system(cmd, '-echo');

            %% Binarise the white matter segementation
            wmbin = [outdir '/wmbin.nii.gz'];
            cmd = [obj.fslLoc '/fslmaths ' wm_nii ' -bin ' wmbin];
            system(cmd, '-echo');

            %% Run epi_reg
            cmd = [obj.fslLoc '/epi_reg' ...
                ' --epi=' dwi_eddy_b0 ...
                ' --t1=' t1_nii ...
                ' --t1brain=' brain_nii ...
                ' --out=' fullfile(outdir, 'dwi_to_t1') ...
                ' --wmseg=' wmbin ...
                ' -v'];

            system(cmd, '-echo');

            %% Copy transformation matrix in a text file
            outputMat = fullfile(outdir, 'dwi_to_t1.mat');
            outputTxt = fullfile(outdir, 'dwi_to_t1.txt');
            cmd = ['cp ' outputMat ' ' outputTxt];
            system(cmd, '-echo');

            data_for_tracking.dwi_to_freesurferT1 = fullfile(outdir, 'dwi_to_t1.txt');
            data_for_tracking.dwi_eddy_b0 = dwi_eddy_b0;
            data_for_tracking.dwi_eddy_b0_brain = dwi_eddy_b0_brain;
            mustBeFile([outdir '/dwi_eddy.b0.gz.brain_mask.nii.gz']);
            data_for_tracking.dwi_eddy_b0_brain_mask = [outdir '/dwi_eddy.b0.gz.brain_mask.nii.gz'];


        end
    end

    function data_for_tracking = nifti2src(obj, data_for_tracking)
         % Converts NIFTI format DWI data to SRC format for tractography.

        try

            mustBeFile(fullfile(obj.output, 'preprocessDWI/dsiStudio/dwi_eddy.src.gz'));
            data_for_tracking.dwi_src = fullfile(obj.output, 'preprocessDWI/dsiStudio/dwi_eddy.src.gz');

        catch


            outdir = fullfile(obj.output, 'preprocessDWI/dsiStudio');
            mkdir(outdir);

            dwi_src = [outdir '/dwi_eddy.src.gz'];

            cmd = [obj.dsiStudio ...
                ' --action=src' ...
                ' --source=' data_for_tracking.dwi_eddy ...
                ' --bval=' obj.bval ...
                ' --bvec=' data_for_tracking.dwi_eddy_bvec ...
                ' --output=' dwi_src];

            system(cmd, '-echo');

            mustBeFile(dwi_src);
            data_for_tracking.dwi_src = dwi_src;

        end

    end

    function data_for_tracking = src2gqi(obj, data_for_tracking)
        % Converts SRC format data to GQI - a specific diffusion data format

        try

            dwi_fib = dir([obj.output, '/preprocessDWI/dsiStudio/*gqi*fib.gz']);
            mustBeFile(fullfile(dwi_fib.folder, dwi_fib.name));
            data_for_tracking.dwi_fib = fullfile(dwi_fib.folder, dwi_fib.name);

            mustBeFile([data_for_tracking.dwi_fib '.qa.nii.gz']);
            data_for_tracking.dwi_fib_qa = [data_for_tracking.dwi_fib '.qa.nii.gz'];

            mustBeFile([data_for_tracking.dwi_fib '.dti_fa.nii.gz']);
            data_for_tracking.dwi_fib_fa = [data_for_tracking.dwi_fib '.dti_fa.nii.gz'];

            mustBeFile([data_for_tracking.dwi_fib '.md.nii.gz']);
            data_for_tracking.dwi_fib_md = [data_for_tracking.dwi_fib '.md.nii.gz'];

            mustBeFile([data_for_tracking.dwi_fib '.ad.nii.gz']);
            data_for_tracking.dwi_fib_ad = [data_for_tracking.dwi_fib '.ad.nii.gz'];

            mustBeFile([data_for_tracking.dwi_fib '.rd.nii.gz']);
            data_for_tracking.dwi_fib_rd = [data_for_tracking.dwi_fib '.rd.nii.gz'];

        catch

            

            cmd = [obj.dsiStudio ...
                ' --action=rec' ...
                ' --source=' data_for_tracking.dwi_src ...
                ' --method=4' ...
                ' --param0=1.25' ...
                ' --check_btable=1' ...
                ' --align_acpc=0' ...
                ' --mask=' data_for_tracking.dwi_eddy_b0_brain_mask ...
                ' --record_odf=0'];

            system(cmd, '-echo');

            dwi_fib = dir([obj.output, '/preprocessDWI/dsiStudio/*gqi*fib.gz']);

            mustBeFile(fullfile(dwi_fib.folder, dwi_fib.name));
            data_for_tracking.dwi_fib = fullfile(dwi_fib.folder, dwi_fib.name);

            cmd = [obj.dsiStudio ...
                ' --action=exp' ...
                ' --source=' data_for_tracking.dwi_fib  ...
                ' --export=qa,dti_fa,md,ad,rd'];

            system(cmd, '-echo');

            mustBeFile([data_for_tracking.dwi_fib '.qa.nii.gz']);
            data_for_tracking.dwi_fib_qa = [data_for_tracking.dwi_fib '.qa.nii.gz'];

            mustBeFile([data_for_tracking.dwi_fib '.dti_fa.nii.gz']);
            data_for_tracking.dwi_fib_fa = [data_for_tracking.dwi_fib '.dti_fa.nii.gz'];

            mustBeFile([data_for_tracking.dwi_fib '.md.nii.gz']);
            data_for_tracking.dwi_fib_md = [data_for_tracking.dwi_fib '.md.nii.gz'];

            mustBeFile([data_for_tracking.dwi_fib '.ad.nii.gz']);
            data_for_tracking.dwi_fib_ad = [data_for_tracking.dwi_fib '.ad.nii.gz'];

            mustBeFile([data_for_tracking.dwi_fib '.rd.nii.gz']);
            data_for_tracking.dwi_fib_rd = [data_for_tracking.dwi_fib '.rd.nii.gz'];

        end

    end

    function data_for_tracking = fiberTracking(obj, data_for_tracking)
        % Performs fiber tractography on processed DWI data.

        outdir = fullfile(obj.output, 'preprocessDWI/dsiStudio');
        mkdir(outdir);

        dwi_tt = [outdir '/whole_brain'];

        try

            mustBeFile([data_for_tracking.dwi_fib '.trk.gz']);
            data_for_tracking.dwi_trk = [data_for_tracking.dwi_fib '.trk.gz'];

        catch

            %% Perform tractography without itterations

            cmd = [obj.dsiStudio ...
                    ' --action=trk' ...
                    ' --source=' data_for_tracking.dwi_fib ...
                    ' --fiber_count=' num2str(data_for_tracking.nStreamlines) ...
                    ' --method=1' ...
                    ' --trim=1' ...
                    ' --min_length=30' ...
                    ' --max_length=300' ...
                    ' --random_seed=0' ...
                    ' --step_size=1' ...
                    ' --output=' data_for_tracking.dwi_fib '.trk.gz'];

                system(cmd, '-echo');

            data_for_tracking.dwi_trk = [data_for_tracking.dwi_fib '.trk.gz'];
   
        end
    end


    function data_for_tracking = fiberTracking_ittr(obj, data_for_tracking, varargin)
        % Performs fiber tractography on processed DWI data.

        outdir = fullfile(obj.output, 'preprocessDWI/dsiStudio');
        mkdir(outdir);

        dwi_tt = [outdir '/whole_brain'];

        % Default value for the optional argument
        save_trksubVox = false;

        % Check if the optional argument was provided
        if ~isempty(varargin)
            save_trksubVox = varargin{1};
        end

        try

            mustBeFile([dwi_tt '_trk.mat']);
            data_for_tracking.dwi_tt_trk = [dwi_tt '_trk.mat'];
            
            % Conditional behavior based on 'save_trksubVox'
            if save_trksubVox
                disp('trksubVox is saved');
                mustBeFile([dwi_tt '_trksubVox.mat']);
                data_for_tracking.dwi_tt_trksubVox = [dwi_tt '_trksubVox.mat'];
            end

        catch

            
            %% Perform tractography in itterations

            for ittr = 1:10
                cmd = [obj.dsiStudio ...
                    ' --action=trk' ...
                    ' --source=' data_for_tracking.dwi_fib ...
                    ' --fiber_count=' num2str(data_for_tracking.nStreamlines/10) ...
                    ' --method=1' ...
                    ' --trim=1' ...
                    ' --min_length=30' ...
                    ' --max_length=300' ...
                    ' --random_seed=1' ...
                    ' --thread_count=16' ...
                    ' --step_size=1' ...
                    ' --export=qa.mat,dti_fa.mat,md.mat,ad.mat,rd.mat' ...
                    ' --output=' dwi_tt '_ittr' num2str(ittr) '.mat'];

                system(cmd, '-echo');
            end

            %% concatenate all tracts together

            len = [];
            cord = [];
            qa = [];
            dti_fa = [];
            md = [];
            ad = [];
            rd = [];

            for ittr = 1:10
                load([dwi_tt '_ittr' num2str(ittr) '.mat'],'tracts','length');

                cord = [cord single(tracts)];
                len = [len single(length)];

                load([dwi_tt '_ittr' num2str(ittr) '.mat.qa.mat'],'data')
                qa = [qa single(data)];

                load([dwi_tt '_ittr' num2str(ittr) '.mat.dti_fa.mat'],'data')
                dti_fa = [dti_fa single(data)];

                load([dwi_tt '_ittr' num2str(ittr) '.mat.md.mat'],'data')
                md = [md single(data)];

                load([dwi_tt '_ittr' num2str(ittr) '.mat.ad.mat'],'data')
                ad = [ad single(data)];

                load([dwi_tt '_ittr' num2str(ittr) '.mat.rd.mat'],'data')
                rd = [rd single(data)];
            end

            cord = [cord; ones(1,size(cord,2))];

            trk.length = len';
            trk.cord = cord;

            trksubVox.qa = qa;
            trksubVox.fa = dti_fa;
            trksubVox.md = md;
            trksubVox.ad = ad;
            trksubVox.rd = rd;

            %% Compute mean dwi metrics across tracts

            ends=(cumsum(double(trk.length)));
            starts=[1; 1+ends];

            trk.startEnd = [starts(1:end-1),ends];

            trk.qaTrk = single(zeros(numel(trk.length),1));
            trk.faTrk = single(zeros(numel(trk.length),1));
            trk.mdTrk = single(zeros(numel(trk.length),1));
            trk.adTrk = single(zeros(numel(trk.length),1));
            trk.rdTrk = single(zeros(numel(trk.length),1));

            for i=1:numel(trk.length)
                trk.qaTrk(i,:) = mean(trksubVox.qa(trk.startEnd(i,1):trk.startEnd(i,2)));
                trk.faTrk(i,:) = mean(trksubVox.fa(trk.startEnd(i,1):trk.startEnd(i,2)));
                trk.mdTrk(i,:) = mean(trksubVox.md(trk.startEnd(i,1):trk.startEnd(i,2)));
                trk.adTrk(i,:) = mean(trksubVox.ad(trk.startEnd(i,1):trk.startEnd(i,2)));
                trk.rdTrk(i,:) = mean(trksubVox.rd(trk.startEnd(i,1):trk.startEnd(i,2)));
            end

            save([dwi_tt '_trk.mat'],'trk','-v7.3');
            delete([dwi_tt '*_ittr*']) ; % remove all temporary files from each itterations

            mustBeFile([dwi_tt '_trk.mat']);

            data_for_tracking.dwi_trk = [data_for_tracking.dwi_fib '.trk.gz'];
            data_for_tracking.dwi_tt_trk = [dwi_tt '_trk.mat'];
           

            if save_trksubVox
                disp('trksubVox is saved');
                save([dwi_tt '_trksubVox.mat'],'trksubVox','-v7.3');
                mustBeFile([dwi_tt '_trksubVox.mat']);
                data_for_tracking.dwi_tt_trksubVox = [dwi_tt '_trksubVox.mat'];
            else
                disp('Not saving trksubVox');
            end

        end
    end

    function data_for_tracking = alligntracts2T1(obj, data_for_tracking)
        % Aligns computed fiber tracts to T1-weighted MRI data.

        
        outdir = fullfile(obj.output, 'connectivityDWI/tracts_to_T1');
        mkdir(outdir);

        try

            mustBeFile([outdir, '/trk_to_t1surfRAS.txt']);
            mustBeFile([outdir, '/trk_to_t1Vox.txt']);

            data_for_tracking.trk_to_t1surfRAS = [outdir, '/trk_to_t1surfRAS.txt'];
            data_for_tracking.trk_to_t1Vox = [outdir, '/trk_to_t1Vox.txt'];

        catch

            t1.hdr = niftiinfo([obj.freeSurferDir '/mri/T1.nii.gz']);
            xform.t1surfRAS = vox2ras_0to1(vox2ras_tkreg(t1.hdr.ImageSize, t1.hdr.PixelDimensions));

            %% Load dwi_eddy info and fiber tracts
            dwi_fib_fa = niftiinfo(data_for_tracking.dwi_fib_fa);
            load(data_for_tracking.dwi_tt_trk,'trk');

            %% Load transformation matrices to put tracts directly into T1 surface space
            xform.dwi_to_t1 = load(data_for_tracking.dwi_to_freesurferT1);

            xform.T_AP = [1 0 0 0;
                0 -1 0 dwi_fib_fa.ImageSize(2)-1;
                0 0 1 0;
                0 0 0 1]; % This is flipping Anterior-Posterior

            xform.T_LR = [-1 0 0 dwi_fib_fa.ImageSize(1)-1;
                0 1 0 0;
                0 0 1 0;
                0 0 0 1]; % This is flipping Left-Right

            xform.sizeMat = [dwi_fib_fa.PixelDimensions(1) 0 0 0;
                0 dwi_fib_fa.PixelDimensions(2) 0 0 ;
                0 0 dwi_fib_fa.PixelDimensions(3) 0;
                0 0 0 1;]; % This is increasing the resolution to match that of Orig

            xform.sizeMatT1 = [1/t1.hdr.PixelDimensions(1) 0 0 0; ...
                0 1/t1.hdr.PixelDimensions(2) 0 0 ; ...
                0 0 1/t1.hdr.PixelDimensions(3) 0; ...
                0 0 0 1];

            xform.trk_to_t1Vox = xform.sizeMatT1*xform.dwi_to_t1*xform.sizeMat*xform.T_AP; % Combining all the transformations
            %trk_to_t1Vox = xform.trk_to_t1Vox*trk.cord; % Transforms tracts to t1voxel space

            xform.trk_to_t1surfRAS = xform.t1surfRAS * xform.trk_to_t1Vox;
            trk_to_t1surfRAS = xform.trk_to_t1surfRAS * trk.cord; % Transform tracts to surface space

            %% Plot to check
            [lpv, lpf] = read_surf([obj.freeSurferDir '/surf/lh.pial']);
            %[lwv, lwf] = read_surf([obj.freeSurferDir '/surf/lh.white']);

            [rpv, rpf] = read_surf([obj.freeSurferDir '/surf/rh.pial']);
            %[rwv, rwf] = read_surf([obj.freeSurferDir '/surf/rh.white']);

            figure;
            hold on

            hl = trisurf(lpf+1,lpv(:,1),lpv(:,2),lpv(:,3));
            hl.EdgeColor = 'none';
            hl.FaceAlpha = 0.1;
            hl.FaceColor = [0.7 0.7 0.7];

            hr = trisurf(rpf+1,rpv(:,1),rpv(:,2),rpv(:,3));
            hr.EdgeColor = 'none';
            hr.FaceAlpha = 0.1;
            hr.FaceColor = [0.7 0.7 0.7];

            scatter3(trk_to_t1surfRAS(1,1:100000:end),...
                trk_to_t1surfRAS(2,1:100000:end),...
                trk_to_t1surfRAS(3,1:100000:end));

            hold off

            writematrix(xform.trk_to_t1Vox, [outdir, '/trk_to_t1Vox.txt'], 'Delimiter','space');
            writematrix(xform.trk_to_t1surfRAS, [outdir, '/trk_to_t1surfRAS.txt'],'Delimiter','space');

            saveas(gca, [outdir, '/check_alignment.fig']);
            saveas(gca, [outdir, '/check_alignment.png']);

            mustBeFile([outdir, '/trk_to_t1surfRAS.txt']);
            mustBeFile([outdir, '/trk_to_t1Vox.txt']);

            data_for_tracking.trk_to_t1surfRAS = [outdir, '/trk_to_t1surfRAS.txt'];
            data_for_tracking.trk_to_t1Vox = [outdir, '/trk_to_t1Vox.txt'];

        end
    end

    function data_for_tracking = getROICord(obj, data_for_tracking, atlas_name, lookupTable)
        % Retrieves Region of Interest (ROI) coordinates from an atlas.

        
        outdir = fullfile(obj.output, 'connectivityDWI', atlas_name);
        mkdir(outdir);

        try

            mustBeFile([outdir '/atlas.mat']);
            data_for_tracking.atlas = [outdir '/atlas.mat'];

        catch
            %% Load atlas
            atlas.mgz = [obj.freeSurferDir '/mri/' atlas_name '.mgz'];
            atlas.nii = [obj.freeSurferDir '/mri/' atlas_name '.nii.gz'];
            cmd = [obj.freeSurferLoc '/mri_convert ' atlas.mgz ' ' atlas.nii];
            system(cmd, '-echo');

            atlas.hdr = niftiinfo(atlas.nii);
            atlas.data = niftiread(atlas.nii);
            atlas.lut = readtable(lookupTable);

            %% Get voxel coordinates from atlas
            atlas.roi = ismember(atlas.data, atlas.lut.roiNum);

            atlas.voxels = [];

            for r = 1:size(atlas.lut,1)

                [vox(:,1),vox(:,2),vox(:,3)] = ind2sub(size(atlas.data),find(atlas.data==atlas.lut.roiNum(r)));
                vox(:,4) = repmat(atlas.lut.roiNum(r),size(vox,1),1);
                atlas.voxels = [atlas.voxels;vox];
                clear vox

            end

            %% Convert voxel coordinates from atlas to surface RAS

            tk_ras = vox2ras_0to1(vox2ras_tkreg(atlas.hdr.ImageSize, atlas.hdr.PixelDimensions));
            atlas.surfaceRAS = transpose(tk_ras * [atlas.voxels(:,1:3), ones(size(atlas.voxels,1),1)]');
            atlas.surfaceRAS(:,4) = atlas.voxels(:,4);
            save([outdir '/atlas.mat'], 'atlas');

            data_for_tracking.atlas = [outdir '/atlas.mat'];
        end
    end

    function data_for_tracking = atlasConnectivity(obj, data_for_tracking, atlas_name, atlas_file, lookupTable)
        % Retrieves Region of Interest (ROI) coordinates from an atlas.

        
        outdir = fullfile(obj.output, 'connectivityDWI', atlas_name);
        mkdir(outdir);

        try

            mustBeFile([outdir '/connectivity.mat'])
            data_for_tracking.atlasConnectivity = [outdir '/connectivity.mat'];

        catch

            atlasLUT = readtable(lookupTable);

             % Due to DSI studio naming convention
            atlasLUT.label = atlasLUT.roi;
            if contains(atlas_name,'lausanne2018')
                for k = 1:size(atlasLUT,1)
                    atlasLUT.roi{k} = ['lausanne2018_' num2str(atlasLUT.roiNum(k))];
                end
            end

            cmd = [obj.dsiStudio ...
                ' --action=ana' ...
                ' --source=' data_for_tracking.dwi_fib ...
                ' --tract=' data_for_tracking.dwi_trk ...
                ' --t1t2=' [obj.freeSurferDir '/mri/T1.nii.gz']...
                ' --connectivity=' atlas_file ...
                ' --connectivity_value=dti_fa,md,ad,rd,count,mean_length,qa' ...
                ' --connectivity_type=end' ...
                ' --connectivity_threshold=0'];

            system(cmd, '-echo');

            % keep directory with DSI Studio files in dwi space clean
            delete([fileparts(data_for_tracking.dwi_fib) '/*.txt'])
            movefile([fileparts(data_for_tracking.dwi_fib) '/*connectivity*'], [outdir, '/raw_export'])

            temp = dir([outdir, '/raw_export/*count*']);
            count = load(fullfile(temp.folder, temp.name));

            labels = textscan(char(count.name),'%s');
            labels = labels{1};
            [~, idx] = ismember(atlasLUT.roi, labels);
            connectivity.count = count.connectivity(idx,idx);

            temp = dir([outdir, '/raw_export/*dti_fa*']);
            dti_fa = load(fullfile(temp.folder, temp.name));
            connectivity.trkmean.fa = dti_fa.connectivity(idx,idx);

            temp = dir([outdir, '/raw_export/*mean_length*']);
            mean_length = load(fullfile(temp.folder, temp.name));
            connectivity.trkmean.length = mean_length.connectivity(idx,idx);

            temp = dir([outdir, '/raw_export/*md*']);
            md = load(fullfile(temp.folder, temp.name));
            connectivity.trkmean.md = md.connectivity(idx,idx);

            temp = dir([outdir, '/raw_export/*ad*']);
            ad = load(fullfile(temp.folder, temp.name));
            connectivity.trkmean.ad = ad.connectivity(idx,idx);

            temp = dir([outdir, '/raw_export/*rd*']);
            rd = load(fullfile(temp.folder, temp.name));
            connectivity.trkmean.rd = rd.connectivity(idx,idx);

            temp = dir([outdir, '/raw_export/*qa*']);
            qa = load(fullfile(temp.folder, temp.name));
            connectivity.trkmean.qa = qa.connectivity(idx,idx);

            connectivity.atlasLUT = atlasLUT;

            save([outdir '/connectivity.mat'], 'connectivity');
            mustBeFile([outdir '/connectivity.mat'])
            data_for_tracking.atlasConnectivity = [outdir '/connectivity.mat'];

        end
    end


    function data_for_tracking = filterTractsbyAtlas(obj, data_for_tracking, atlas_name)
        % Filters tractography data based on atlas-defined ROIs.

        
        outdir = fullfile(obj.output, 'connectivityDWI', atlas_name);
        mkdir(outdir);

        try

            mustBeFile([outdir '/trk_filteredby_atlas.mat'])
            data_for_tracking.trk_filteredby_atlas = [outdir '/trk_filteredby_atlas.mat'];

        catch
            %% Load trk and parameters for edge list
            nPoints = data_for_tracking.nPoints;
            sphereDist = data_for_tracking.roiDia;
            load(data_for_tracking.atlas,'atlas');
            load(data_for_tracking.dwi_tt_trk,'trk');

            % Transform tracts to t1 surface space
            trk_to_t1surfRAS = load(data_for_tracking.trk_to_t1surfRAS);
            trk.cord = trk_to_t1surfRAS * trk.cord;
            trk.cord(4,:) = []; % to save space in memory

            %% get the first start nPoints and last nPoints coordinates of each tract
            trk.startCord=zeros(numel(trk.length),3,nPoints,'single');
            trk.endCord=zeros(numel(trk.length),3,nPoints,'single');

            for i=1:numel(trk.length)
                trk.startCord(i,:,:) = reshape(trk.cord(1:3,...
                    trk.startEnd(i,1):(trk.startEnd(i,1)+nPoints-1)),[1,3,nPoints]);

                trk.endCord(i,:,:) = reshape(trk.cord(1:3,...
                    trk.startEnd(i,2):-1:(trk.startEnd(i,2)-nPoints+1)),[1,3,nPoints]);
            end

            %% Filter tracts by ROI: indentify tracts that either start or end in ROI

            for roi = 1:numel(atlas.lut.roiNum)
                tic

                idx = atlas.surfaceRAS(:,4) == atlas.lut.roiNum(roi);
                roiCord = atlas.surfaceRAS(idx,1:3);
                tPositionStart = [];
                tPositionEnd = [];

                for n = 1:nPoints
                    [~,dStart] = knnsearch(roiCord, trk.startCord(:,:,n));
                    [~,dEnd] = knnsearch(roiCord, trk.endCord(:,:,n));

                    tPositionStart = [tPositionStart; find(dStart <= sphereDist)];
                    tPositionEnd = [tPositionEnd; find(dEnd <= sphereDist)];
                end

                tPositionStart = single(unique(tPositionStart));
                tPositionEnd = single(unique(tPositionEnd));
                atlas.lut.tPositionStart{roi,:} = tPositionStart;
                atlas.lut.tPositionEnd{roi,:} = tPositionEnd;

                elapsedTime = toc;
                disp(['ROI ' atlas.lut.roi{roi} ' took: ' num2str(elapsedTime) 'sec']);
            end

            trk_filteredby_atlas = atlas.lut;
            save([outdir '/trk_filteredby_atlas.mat'], 'trk_filteredby_atlas');
            mustBeFile([outdir '/trk_filteredby_atlas.mat'])
            data_for_tracking.trk_filteredby_atlas = [outdir '/trk_filteredby_atlas.mat'];

        end
    end

    function data_for_tracking = connectROI(obj, data_for_tracking, atlas_name)
        % Generates connectivity matrices based on ROI analysis.

        
        outdir = fullfile(obj.output, 'connectivityDWI', atlas_name);
        mkdir(outdir);

        try

            mustBeFile([outdir '/connectivity.mat'])
            data_for_tracking.connectivity = [outdir '/connectivity.mat'];

        catch

            load(data_for_tracking.atlas, 'atlas');
            load(data_for_tracking.dwi_tt_trk, 'trk');
            load(data_for_tracking.trk_filteredby_atlas, 'trk_filteredby_atlas');

            % Transform tracts to t1 surface space
            trk_to_t1surfRAS = load(data_for_tracking.trk_to_t1surfRAS);
            trk.cord = trk_to_t1surfRAS * trk.cord;
            trk.cord(4,:) = []; % to save space in memory

            for r1 = 1:size(trk_filteredby_atlas,1)
                roi1 = atlas.surfaceRAS(:,4) == trk_filteredby_atlas.roiNum(r1);
                roi1xyz = atlas.surfaceRAS(roi1,1:3);

                for r2 = 1:size(trk_filteredby_atlas,1)

                    roi2 = atlas.surfaceRAS(:,4) == trk_filteredby_atlas.roiNum(r2);
                    roi2xyz = atlas.surfaceRAS(roi2,1:3);

                    % tract should either start in r1 and end in r2 or
                    % start in r2 and end in r1. If tracts that starts in
                    % r1 and r2 and ends elsewhere, they are not valid.
                    % Similarly if the tract ends in r1 and r2 and starts
                    % elsewhere, they are not valid.
                    connectionStartEnd = intersect(trk_filteredby_atlas.tPositionStart{r1}, ...
                        trk_filteredby_atlas.tPositionEnd{r2});
                    connectionEndStart = intersect(trk_filteredby_atlas.tPositionEnd{r1}, ...
                        trk_filteredby_atlas.tPositionStart{r2});

                    connection = unique([connectionStartEnd; connectionEndStart]);

                    %                    % Sanity check plot rois and tracts
                    %                     figure;
                    %                     hold on
                    %                     scatter3(roi1xyz(:,1),roi1xyz(:,2),roi1xyz(:,3));
                    %                     scatter3(roi2xyz(:,1),roi2xyz(:,2),roi2xyz(:,3));
                    %                     for t = 1:numel(connection)
                    %                       cord = trk.cord(:, trk.startEnd(connection(t),1):trk.startEnd(connection(t),2))';
                    %                        line(cord(:,1), cord(:,2), cord(:,3),'Color', [0.5 0.5 0.5]);
                    %                     end

                    connectivity.count (r1,r2) = numel(connection);

                    connectivity.trkmean.fa(r1,r2) = mean(trk.faTrk(connection),'omitnan');
                    connectivity.trkmedian.fa(r1,r2) = median(trk.faTrk(connection),'omitnan');

                    connectivity.trkmean.length(r1,r2) = mean(trk.length(connection),'omitnan');
                    connectivity.trkmedian.length(r1,r2) = median(trk.length(connection),'omitnan');

                    connectivity.trkmean.md(r1,r2) = mean(trk.mdTrk(connection),'omitnan');
                    connectivity.trkmedian.md(r1,r2) = median(trk.mdTrk(connection),'omitnan');

                    connectivity.trkmean.ad(r1,r2) = mean(trk.adTrk(connection),'omitnan');
                    connectivity.trkmedian.ad(r1,r2) = median(trk.adTrk(connection),'omitnan');

                    connectivity.trkmean.rd(r1,r2) = mean(trk.rdTrk(connection),'omitnan');
                    connectivity.trkmedian.rd(r1,r2) = median(trk.rdTrk(connection),'omitnan');

                    connectivity.trkmean.qa(r1,r2) = mean(trk.qaTrk(connection),'omitnan');
                    connectivity.trkmedian.qa(r1,r2) = median(trk.qaTrk(connection),'omitnan');

                end
            end

            connectivity.atlasLUT = atlas.lut;
            connectivity.trkmean.fa(isnan(connectivity.trkmean.fa)) = 0;
            connectivity.trkmean.length(isnan(connectivity.trkmean.length)) = 0;
            connectivity.trkmean.md(isnan(connectivity.trkmean.md)) = 0;
            connectivity.trkmean.ad(isnan(connectivity.trkmean.ad)) = 0;
            connectivity.trkmean.rd(isnan(connectivity.trkmean.rd)) = 0;
            connectivity.trkmean.qa(isnan(connectivity.trkmean.qa)) = 0;

            connectivity.trkmedian.fa(isnan(connectivity.trkmedian.fa)) = 0;
            connectivity.trkmedian.length(isnan(connectivity.trkmedian.length)) = 0;
            connectivity.trkmedian.md(isnan(connectivity.trkmedian.md)) = 0;
            connectivity.trkmedian.ad(isnan(connectivity.trkmedian.ad)) = 0;
            connectivity.trkmedian.rd(isnan(connectivity.trkmedian.rd)) = 0;
            connectivity.trkmedian.qa(isnan(connectivity.trkmedian.qa)) = 0;

            save([outdir '/connectivity.mat'], 'connectivity');
            mustBeFile([outdir '/connectivity.mat'])
            data_for_tracking.connectivity = [outdir '/connectivity.mat'];

        end

    end

end

end
