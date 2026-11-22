function manifestFile = export_all_geometry(modelArg, outDir)
%EXPORT_ALL_GEOMETRY Export every Simulink scope of a model plus a manifest.
%
%   export_all_geometry('Controller', 'geometry_current')
%
% Each scope JSON holds only its direct children in scope-local coordinates.
% Chart interiors have no Simulink geometry and are listed in skipped_scopes
% for the Stateflow visual chain. Any export failure keeps status=INVALID.

if nargin < 1 || isempty(modelArg)
    error('export_all_geometry:missingModel', 'modelArg is required');
end
if nargin < 2 || isempty(outDir)
    outDir = fullfile(pwd, 'model_geometry');
end
modelArg = char(modelArg);
outDir = char(outDir);
[modelName, modelFile] = resolveModel(modelArg);
if ~isfolder(outDir)
    [ok, msg] = mkdir(outDir);
    if ~ok
        error('export_all_geometry:mkdir', 'Cannot create %s: %s', outDir, msg);
    end
end
try
    open_system(modelName);
catch ME
    error('export_all_geometry:open', 'Cannot open %s: %s', modelName, ME.message);
end

scopePaths = [{modelName}; cellstr(find_system(modelName, ...
    'LookUnderMasks', 'all', 'FollowLinks', 'off', ...
    'Type', 'block', 'BlockType', 'SubSystem'))];
scopePaths = unique(scopePaths, 'stable');

entries = {};
skipped = {};
exportErrors = {};
for k = 1:numel(scopePaths)
    scopePath = scopePaths{k};
    entry = struct('scope', scopePath, 'geometry_file', '', 'status', '', 'error', '');
    try
        if unreadableLines(scopePath) > 0
            error('export_all_geometry:points', ...
                'lines without routed Points; open the scope and retry');
        end
        geometryName = sprintf('scope_%03d.json', k);
        export_geometry(scopePath, fullfile(outDir, geometryName));
        decoded = jsondecode(fileread(fullfile(outDir, geometryName)));
        nBlocks = countOf(decoded.blocks);
        nLines = countOf(decoded.lines);
        if nBlocks == 0 && nLines == 0
            entry.status = 'SKIPPED_EMPTY';
            entry.error = 'No direct Simulink geometry (e.g. Chart interior).';
            skipped{end + 1} = entry; %#ok<AGROW>
            delete(fullfile(outDir, geometryName));
            continue;
        end
        entry.geometry_file = geometryName;
        entry.status = 'EXPORTED';
        entries{end + 1} = entry; %#ok<AGROW>
    catch ME
        entry.status = 'FAILED';
        entry.error = ME.message;
        entries{end + 1} = entry; %#ok<AGROW>
        exportErrors{end + 1} = sprintf('%s: %s', scopePath, ME.message); %#ok<AGROW>
    end
end

payload = struct();
payload.schema_version = 'maab.simulink_geometry_manifest/v2';
payload.model = modelName;
payload.model_file = modelFile;
payload.status = ternary(isempty(exportErrors), 'COMPLETE', 'INVALID');
payload.scope_count = numel(entries);
% entries/skipped are cell arrays, so jsonencode emits JSON arrays even for
% a single scope (a 1x1 struct array would encode as an object).
payload.scopes = entries;
payload.skipped_scopes = skipped;
payload.coverage = struct('all_hierarchy', true, ...
    'coordinate_frames_mixed', false, 'export_errors', {exportErrors});
manifestFile = fullfile(outDir, 'manifest.json');
writeJson(manifestFile, payload);
fprintf('wrote manifest %s: %d exported / %d skipped / %d errors / status=%s\n', ...
    manifestFile, numel(entries), numel(skipped), numel(exportErrors), payload.status);
if ~isempty(exportErrors)
    error('export_all_geometry:incomplete', 'Export incomplete; see %s', manifestFile);
end
end

function [modelName, modelFile] = resolveModel(modelArg)
if ~isempty(regexp(modelArg, '\.(slx|mdl)$', 'once', 'ignorecase')) || exist(modelArg, 'file') == 2
    supplied = modelArg;
    if ~isfile(supplied)
        supplied = which(modelArg);
    end
    if ~isfile(supplied)
        error('export_all_geometry:notFound', 'Model file not found: %s', modelArg);
    end
    info = dir(supplied);
    modelFile = fullfile(info.folder, info.name);
    [~, modelName] = fileparts(modelFile);
    if ~bdIsLoaded(modelName)
        load_system(modelFile);
    end
else
    modelName = strtok(modelArg, '/');
    if ~bdIsLoaded(modelName)
        load_system(modelName);
    end
    modelFile = char(get_param(modelName, 'FileName'));
    if ~isfile(modelFile)
        error('export_all_geometry:noFile', 'Cannot resolve file for %s', modelName);
    end
end
end

function count = unreadableLines(scopePath)
count = 0;
lines = find_system(scopePath, 'SearchDepth', 1, 'FindAll', 'on', 'Type', 'line');
for k = 1:numel(lines)
    try
        pts = get_param(lines(k), 'Points');
        ok = isnumeric(pts) && size(pts, 2) == 2 && size(pts, 1) >= 2;
    catch
        ok = false;
    end
    if ~ok
        count = count + 1;
    end
end
end

function n = countOf(value)
if iscell(value) || isstruct(value)
    n = numel(value);
else
    n = 0;
end
end

function value = ternary(condition, whenTrue, whenFalse)
if condition, value = whenTrue; else, value = whenFalse; end
end

function writeJson(filePath, payload)
jsonText = jsonencode(payload, 'PrettyPrint', true);
[fid, msg] = fopen(filePath, 'w', 'n', 'UTF-8');
if fid < 0
    error('export_all_geometry:write', 'Cannot write %s: %s', filePath, msg);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s', jsonText);
end
