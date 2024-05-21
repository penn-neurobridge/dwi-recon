clc, clear, close all

for s = 1:5

    % get subcortical from desikan killiany atlas
    dkt = readtable('desikanKilliany.csv');

    [~,~,lhscale] = read_annotation(['lh.lausanne2018.scale' num2str(s) '.annot']);
    lhctx_roiNum = [0:size(lhscale.struct_names,1)-1]' + 1000;
    lhctx_roi = deblank(lhscale.struct_names);
    % remove unknown
    lhctx_roiNum(1) = [];
    lhctx_roi(1) = [];
    lhctx_roi = strcat('ctx-lh-', lhctx_roi);

    [~,~,rhscale] = read_annotation(['rh.lausanne2018.scale' num2str(s) '.annot']);
    rhctx_roiNum = [0:size(rhscale.struct_names,1)-1]' + 2000;
    rhctx_roi = deblank(rhscale.struct_names);
    % remove unknown
    rhctx_roiNum(1) = [];
    rhctx_roi(1) = [];
    rhctx_roi = strcat('ctx-rh-', rhctx_roi);


    roi = [dkt.roi(1:14); lhctx_roi; rhctx_roi];
    isSideLeft = [dkt.isSideLeft(1:14); ...
        ones(size(lhctx_roi,1),1); zeros(size(lhctx_roi,1),1)];

    roiNum = [dkt.roiNum(1:14); lhctx_roiNum; rhctx_roiNum];

    snum = [1:size(roi,1)]';

    T = table(snum,roi,isSideLeft,roiNum);

    writetable(T, ['lausanne2018scale' num2str(s) '.csv'])

   clearvars -except s

end
