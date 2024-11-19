classdef iEEGsc

    properties
        whole_brain_trk
        whole_brain_trksubVox
        trk_to_t1surfRAS
        freeSurferDir
        output
        IEEGdata
    end

    methods

        function electrodes = iEEGgrey2white(obj)

            outdir = fullfile(obj.output, 'connectivityIEEG');
            mkdir(outdir)

            try
                mustBeFile([outdir '/electrodes_surf_proj.mat'])
                load([outdir '/electrodes_surf_proj.mat'],'electrodes');

            catch


                electrodes = readtable(obj.IEEGdata);

                % remove the electodes outside the brain
                outside = ismember(electrodes.roi,'outside-brain');
                electrodes(outside,:) = [];

                % Find contacts in the grey matter contex only
                in_cortex =  electrodes.roiNum>999;
                in_cortexID = find(in_cortex);

                electrodes_surf = [electrodes.surfmm_x(in_cortex), electrodes.surfmm_y(in_cortex), electrodes.surfmm_z(in_cortex)];

                [lpv, lpf] = read_surf([obj.freeSurferDir '/surf/lh.pial']);
                [lwv, lwf] = read_surf([obj.freeSurferDir '/surf/lh.white']);

                [rpv, rpf] = read_surf([obj.freeSurferDir '/surf/rh.pial']);
                [rwv, rwf] = read_surf([obj.freeSurferDir '/surf/rh.white']);

                % find if elecs are outside of WM surface
                lWM.faces=lwf+1;
                lWM.vertices=lwv;
                in_left = inpolyhedron(lWM,electrodes_surf);

                rWM.faces=rwf+1;
                rWM.vertices=rwv;
                in_right = inpolyhedron(rWM,electrodes_surf);

                out=~in_left & ~in_right;
                out_id=find(out);

                %for the electrodes outside WM, find nearest GM surface point
                vids=zeros(length(out_id),1);
                sides=cell(length(out_id),1);
                for k=1:length(out_id)
                    [mindl_id,mindl] = knnsearch(lpv,electrodes_surf(out_id(k),:));
                    [mindr_id,mindr] = knnsearch(rpv,electrodes_surf(out_id(k),:));

                    if mindl<mindr
                        vids(k)=mindl_id;
                        sides{k}='l';
                    else
                        vids(k)=mindr_id;
                        sides{k}='r';
                    end
                end

                % build up all the output variables:
                l=size(electrodes_surf,1);
                elecs_type=cell(l,1);
                elecs_side=cell(l,1);
                elecs_GMSurfxyz=zeros(l,3);
                elecs_WMSurfxyz=zeros(l,3);
                for k=1:l
                    kid=find(out_id==k);
                    if length(kid)==1%if is outside of WM
                        elecs_type{k}='OutsideWM';
                        elecs_side{k}=sides{kid};
                        if sides{kid}=='l'
                            elecs_GMSurfxyz(k,:)=lpv(vids(kid),:);
                            elecs_WMSurfxyz(k,:)=lwv(vids(kid),:);
                        else
                            elecs_GMSurfxyz(k,:)=rpv(vids(kid),:);
                            elecs_WMSurfxyz(k,:)=rwv(vids(kid),:);
                        end
                    else % if inside of WM
                        elecs_type{k}='InsideWM';
                        if in_left(k)
                            elecs_side{k}='l';

                        else
                            elecs_side{k}='r';
                        end
                        elecs_GMSurfxyz(k,:)=[NaN NaN NaN];
                        elecs_WMSurfxyz(k,:)=[NaN NaN NaN];
                    end
                end

                in_cortexIDGM = in_cortexID(out_id);

                electrodes.surfmm_x(in_cortexIDGM) = elecs_WMSurfxyz(out_id,1);
                electrodes.surfmm_y(in_cortexIDGM) = elecs_WMSurfxyz(out_id,2);
                electrodes.surfmm_z(in_cortexIDGM) = elecs_WMSurfxyz(out_id,3);

                save([outdir '/electrodes_surf_proj.mat'],"electrodes")
            end

        end


        function edgeList = makeEdgeList(obj,electrodes,sphereDia,varargin)

            outdir = fullfile(obj.output, 'connectivityIEEG');
            mkdir(outdir)

            try

                mustBeFile([outdir '/edgeList_' num2str(sphereDia) 'mmSph.mat'])
                load([outdir '/edgeList_' num2str(sphereDia) 'mmSph.mat'],"edgeList");

            catch

                iEEGprojected = [electrodes.surfmm_x, electrodes.surfmm_y, electrodes.surfmm_z];
                edgeList = [];

                load(obj.whole_brain_trk,"trk");
                fieldsToKeep = {'length','cord','startEnd'};
                trk = rmfield(trk,setdiff(fieldnames(trk), fieldsToKeep));
                xform.trk_to_t1surfRAS = readmatrix(obj.trk_to_t1surfRAS);
                trk.cord = xform.trk_to_t1surfRAS * trk.cord; % Transform tracts to surface space

                load(obj.whole_brain_trksubVox,"trksubVox");
                trk.subVoxQA = trksubVox.qa;
                trk.subVoxFA = trksubVox.fa;
                trk.subVoxMD = trksubVox.md;
                trk.subVoxAD = trksubVox.ad;
                trk.subVoxRD = trksubVox.rd;
                clear trksubVox

                % this is only to speed up by diving the data in small bins
                nBins = transpose(histcounts(1:numel(trk.length),1000));
                tBinEnd= cumsum(nBins);
                tBinStart=[1; 1+tBinEnd];
                tBinStart = tBinStart(1:end-1);
                trkPosition = [0;tBinEnd(1:end-1)];
                for tBin = 1:numel(tBinStart)
                    trkBin.length = trk.length(tBinStart(tBin):tBinEnd(tBin));

                    trkBinEnds=(cumsum(double(trkBin.length)));
                    trkBinStarts=[1; 1+trkBinEnds];
                    trkBin.startEnd = [trkBinStarts(1:end-1),trkBinEnds];

                    trkBin.cord = trk.cord(:,trk.startEnd(tBinStart(tBin),1):trk.startEnd(tBinEnd(tBin),2));
                    trkBin.subVoxQA = trk.subVoxQA(:,trk.startEnd(tBinStart(tBin),1):trk.startEnd(tBinEnd(tBin),2));
                    trkBin.subVoxFA = trk.subVoxFA(:,trk.startEnd(tBinStart(tBin),1):trk.startEnd(tBinEnd(tBin),2));
                    trkBin.subVoxMD = trk.subVoxMD(:,trk.startEnd(tBinStart(tBin),1):trk.startEnd(tBinEnd(tBin),2));
                    trkBin.subVoxAD = trk.subVoxAD(:,trk.startEnd(tBinStart(tBin),1):trk.startEnd(tBinEnd(tBin),2));
                    trkBin.subVoxRD = trk.subVoxRD(:,trk.startEnd(tBinStart(tBin),1):trk.startEnd(tBinEnd(tBin),2));

                    trkBin.tPosition = trkPosition(tBin);

                    % do par for here
                    parfor t=1:numel(trkBin.length)
                        [~,d] = knnsearch(trkBin.cord(1:3,trkBin.startEnd(t,1):trkBin.startEnd(t,2))',iEEGprojected);

                        if sum(d<sphereDia) > 1

                            connectedElecs = find(d <= sphereDia);
                            trkProp = iEEGsc.getTrkMetricsPass(trkBin,t,iEEGprojected,connectedElecs,sphereDia);
                            edgeList = [edgeList;trkProp];

                        end
                    end
                    clear trkBin
                end

                edgeList = array2table(edgeList,'VariableNames',{'roi1','roi2','length',...
                    'qa','fa','md','ad','rd','trkindx'});

                save([outdir '/edgeList_' num2str(sphereDia) 'mmSph.mat'],"edgeList");
            end

        end

        function connectivity = makeConnectivityMatrix(obj,edgeList,sphereDia)

            outdir = fullfile(obj.output, 'connectivityIEEG');
            mkdir(outdir)

            try

                mustBeFile([outdir '/connectivity_' num2str(sphereDia) 'mmSph.mat']);
                load([outdir '/connectivity_' num2str(sphereDia) 'mmSph.mat'],"connectivity")
            
            catch

                electrodes = readtable(obj.IEEGdata);
                % remove the electodes outside the brain
                outside = ismember(electrodes.roi,'outside-brain');
                electrodes(outside,:) = [];

                connectivity.count=zeros(size(electrodes,1));
                connectivity.len=zeros(size(electrodes,1));
                connectivity.qa=zeros(size(electrodes,1));
                connectivity.fa=zeros(size(electrodes,1));
                connectivity.md=zeros(size(electrodes,1));
                connectivity.ad=zeros(size(electrodes,1));
                connectivity.rd=zeros(size(electrodes,1));

                for i=1:size(edgeList,1)

                    roi1 = edgeList.roi1(i);
                    roi2 = edgeList.roi2(i);

                    connectivity.count(roi1,roi2) = connectivity.count(roi1,roi2)+1;
                    connectivity.len(roi1,roi2)= connectivity.len(roi1,roi2)+ edgeList.length(i);
                    connectivity.qa(roi1,roi2)=connectivity.qa(roi1,roi2) + edgeList.qa(i);
                    connectivity.fa(roi1,roi2)=connectivity.fa(roi1,roi2) + edgeList.fa(i);
                    connectivity.md(roi1,roi2)=connectivity.md(roi1,roi2) + edgeList.md(i);
                    connectivity.ad(roi1,roi2)=connectivity.ad(roi1,roi2) + edgeList.ad(i);
                    connectivity.rd(roi1,roi2)=connectivity.rd(roi1,roi2) + edgeList.rd(i);

                end

                %% Make adjacency matrix symmetric
                connectivity.count = connectivity.count'+connectivity.count;
                connectivity.len = connectivity.len' + connectivity.len;
                connectivity.qa = connectivity.qa' + connectivity.qa;
                connectivity.fa = connectivity.fa' + connectivity.fa;
                connectivity.md = connectivity.md' + connectivity.md;
                connectivity.ad = connectivity.ad' + connectivity.ad;
                connectivity.rd = connectivity.rd' + connectivity.rd;

                %% Take the mean of length, qa, gfa, md, fa
                connectivity.len = connectivity.len./connectivity.count;
                connectivity.qa = connectivity.qa./connectivity.count;
                connectivity.fa = connectivity.fa./connectivity.count;
                connectivity.md = connectivity.md./connectivity.count;
                connectivity.ad = connectivity.ad./connectivity.count;
                connectivity.rd = connectivity.rd./connectivity.count;

                %% Half the diagonal of count
                connectivity.count(1:size(connectivity.count,1)+1:end)=connectivity.count(1:size(connectivity.count,1)+1:end)/2;

                connectivity.len(isnan(connectivity.len)) = 0;
                connectivity.qa(isnan(connectivity.qa)) = 0;
                connectivity.fa(isnan(connectivity.fa)) = 0;
                connectivity.md(isnan(connectivity.md)) = 0;
                connectivity.ad(isnan(connectivity.ad)) = 0;
                connectivity.rd(isnan(connectivity.rd)) = 0;

                save([outdir '/connectivity_' num2str(sphereDia) 'mmSph.mat'],"connectivity","electrodes");

            end
        end

    end



    methods (Static)  % Notice the Static attribute here

        function [trkProp,cordTrk] = getTrkMetricsPass(trk,t,roiCord,connectedElecs,sphereDist)

            trkIntrst = trk.cord(1:3,trk.startEnd(t,1):trk.startEnd(t,2))';
            elecCord = roiCord(connectedElecs,:);

            % For each electrode find the index of the nearest point on the tract
            for elec = 1:numel(connectedElecs)
                elecOnTrk.electrode(elec,:) = connectedElecs(elec);
                [~,dtrk] = knnsearch(elecCord(elec,:),trkIntrst);
                elecOnTrk.atTractPos(elec,:) = find(dtrk<=sphereDist,1);
            end

            elecOnTrk = struct2table(elecOnTrk);
            elecOnTrk = sortrows(elecOnTrk,'atTractPos','ascend');
            roiPairs = combnk(elecOnTrk.electrode,2);
            cordTrk = [];
            for roiList = 1:size(roiPairs,1)

                posStart = elecOnTrk.atTractPos(elecOnTrk.electrode == roiPairs(roiList,1));
                posEnd = elecOnTrk.atTractPos(elecOnTrk.electrode == roiPairs(roiList,2));
                startEnd = trk.startEnd(t,1):trk.startEnd(t,2);

                roi1(roiList,:) = roiPairs(roiList,1);
                roi2(roiList,:) = roiPairs(roiList,2);
                lengthTrk(roiList,:) = numel(startEnd(posStart):startEnd(posEnd));
                qaTrk(roiList,:) = mean(trk.subVoxQA(startEnd(posStart):startEnd(posEnd)));
                faTrk(roiList,:) = mean(trk.subVoxFA(startEnd(posStart):startEnd(posEnd)));
                mdTrk(roiList,:) = mean(trk.subVoxMD(startEnd(posStart):startEnd(posEnd)));
                adTrk(roiList,:) = mean(trk.subVoxAD(startEnd(posStart):startEnd(posEnd)));
                rdTrk(roiList,:) = mean(trk.subVoxRD(startEnd(posStart):startEnd(posEnd)));


                cordTrk = [cordTrk; trkIntrst(posStart:posEnd,:)];
            end

            trkProp = [roi1,roi2,lengthTrk,qaTrk,faTrk,mdTrk,adTrk,rdTrk,repmat(t+trk.tPosition,size(roiPairs,1),1)];

        end

    end
end

