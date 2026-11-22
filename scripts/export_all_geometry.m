function manifestFile = export_all_geometry(modelArg, outDir)
%EXPORT_ALL_GEOMETRY Export every Simulink scope in a model plus a manifest.
%
%   manifestFile = export_all_geometry('Controller', 'geometry')
%   manifestFile = export_all_geometry('C:\models\Controller.slx', 'geometry')
%
%   Each exported JSON contains only direct children of one scope. The
%   manifest records the complete hierarchy so layout_lint.py can aggregate
%   line length, bend counts, crossings and project appearance gates without
%   mixing coordinates from different scopes.
%
%   The model is opened read-only for geometry inspection. Some never-rendered
%   R2025b diagrams can expose line handles before Points describe the actual
%   routed picture, so each direct line is checked and unreadable geometry
%   fails closed instead of being counted as zero crossings.

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
        error('export_all_geometry:mkdir', ...
            'Cannot create output directory %s: %s', outDir, msg);
    end
end

try
    open_system(modelName);
catch ME
    error('export_all_geometry:openModel', ...
        'Cannot open %s for geometry inspection: %s', modelName, ME.message);
end

scopePaths = discoverScopes(modelName);
if isempty(scopePaths)
    error('export_all_geometry:noScopes', ...
        'No Simulink scopes were found in %s', modelName);
end

entries = repmat(emptyScopeEntry(), 0, 1);
skippedScopes = repmat(emptyScopeEntry(), 0, 1);
exportErrors = {};
exportIndex = 0;
for k = 1:numel(scopePaths)
    scopePath = scopePaths{k};
    entry = emptyScopeEntry();
    entry.index = k;
    entry.scope = scopePath;
    entry.scope_type = ternary(strcmp(scopePath, modelName), 'model', 'subsystem');
    entry.direct_blocks = directBlockCount(scopePath);
    entry.direct_lines = directLineCount(scopePath);

    try
        unreadableLines = unreadableDirectLineCount(scopePath);
        if unreadableLines > 0
            error('export_all_geometry:unreadablePoints', ...
                '%d direct line(s) have no routed Points; open the model and retry', ...
                unreadableLines);
        end
        exportIndex = exportIndex + 1;
        geometryName = sprintf('scope_%03d.json', exportIndex);
        geometryFile = fullfile(outDir, geometryName);
        entry.geometry_file = geometryName;
        export_geometry(scopePath, geometryFile);
        decoded = jsondecode(fileread(geometryFile));
        entry.direct_blocks = numel(decoded.blocks);
        entry.direct_lines = numel(decoded.lines);
        if entry.direct_blocks == 0 && entry.direct_lines == 0
            entry.status = 'SKIPPED_EMPTY';
            entry.error = ...
                'No direct Simulink blocks or lines; generated or Stateflow internals are handled separately.';
            skippedScopes(end + 1) = entry; %#ok<AGROW>
            delete(geometryFile);
            continue;
        end
        entry.status = 'EXPORTED';
        entry.error = '';
    catch ME
        entry.status = 'FAILED';
        entry.error = ME.message;
        exportErrors{end + 1} = sprintf('%s: %s', scopePath, ME.message); %#ok<AGROW>
    end
    entries(end + 1) = entry; %#ok<AGROW>
end

status = ternary(isempty(exportErrors), 'COMPLETE', 'INVALID');
payload = struct();
payload.schema_version = 'maab.simulink_geometry_manifest/v1';
payload.standard = 'TARGET_MODELING_GUIDELINE_V5';
payload.matlab_version = ['R' version('-release')];
payload.model = modelName;
payload.model_file = modelFile;
payload.status = status;
payload.discovered_scope_count = numel(scopePaths);
payload.scope_count = numel(entries);
payload.scopes = entries;
payload.skipped_scopes = skippedScopes;
payload.coverage = struct( ...
    'all_hierarchy', true, ...
    'scope_discovery', ...
        'LookUnderMasks=all; FollowLinks=off; active variants', ...
    'editor_geometry_initialized', true, ...
    'coordinate_frames_mixed', false, ...
    'skipped_empty_scope_count', numel(skippedScopes), ...
    'export_errors', {exportErrors});

manifestFile = fullfile(outDir, 'manifest.json');
writeUtf8Json(manifestFile, payload);

fprintf( ...
    'wrote manifest %s: %d exported scopes / %d empty scopes / %d errors / status=%s\n', ...
    manifestFile, numel(entries), numel(skippedScopes), ...
    numel(exportErrors), status);
if ~isempty(exportErrors)
    error('export_all_geometry:incomplete', ...
        'Geometry export incomplete; see %s', manifestFile);
end
end


function [modelName, modelFile] = resolveModel(modelArg)
isFile = exist(modelArg, 'file') == 2 || ...
    ~isempty(regexp(modelArg, '\.(slx|mdl)$', 'once', 'ignorecase'));
if isFile
    supplied = modelArg;
    if ~isfile(supplied) && exist(supplied, 'file') == 2
        supplied = which(supplied);
    end
    if ~isfile(supplied)
        error('export_all_geometry:modelNotFound', ...
            'Model file does not exist: %s', modelArg);
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
    if isempty(modelFile)
        error('export_all_geometry:modelFile', ...
            'Cannot resolve the file for loaded model %s', modelName);
    end
    if ~isfile(modelFile)
        resolved = which(modelFile);
        if ~isempty(resolved)
            modelFile = resolved;
        end
    end
    if ~isfile(modelFile)
        error('export_all_geometry:modelFile', ...
            'Cannot resolve model file %s', modelFile);
    end
    info = dir(modelFile);
    modelFile = fullfile(info.folder, info.name);
end
end


function scopePaths = discoverScopes(modelName)
subsystems = find_system(modelName, ...
    'LookUnderMasks', 'all', ...
    'FollowLinks', 'off', ...
    'Type', 'block', ...
    'BlockType', 'SubSystem');
scopePaths = unique([{modelName}; cellstr(subsystems(:))], 'stable');
end


function count = directBlockCount(scopePath)
blocks = find_system(scopePath, 'SearchDepth', 1, 'FindAll', 'on', ...
    'Type', 'Block');
count = numel(blocks);
end


function count = directLineCount(scopePath)
lines = find_system(scopePath, 'SearchDepth', 1, 'FindAll', 'on', ...
    'Type', 'line');
count = numel(lines);
end


function count = unreadableDirectLineCount(scopePath)
count = 0;
lines = find_system(scopePath, 'SearchDepth', 1, 'FindAll', 'on', ...
    'Type', 'line');
for k = 1:numel(lines)
    try
        points = get_param(lines(k), 'Points');
        readable = isnumeric(points) && size(points, 2) == 2 && ...
            size(points, 1) >= 2;
    catch
        readable = false;
    end
    if ~readable
        count = count + 1;
    end
end
end


function writeUtf8Json(filePath, payload)
jsonText = jsonencode(payload, 'PrettyPrint', true);
[fid, msg] = fopen(filePath, 'w', 'n', 'UTF-8');
if fid < 0
    error('export_all_geometry:write', ...
        'Cannot write %s: %s', filePath, msg);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s', jsonText);
end


function value = emptyScopeEntry()
value = struct( ...
    'index', [], ...
    'scope', '', ...
    'scope_type', '', ...
    'geometry_file', '', ...
    'status', '', ...
    'error', '', ...
    'direct_blocks', 0, ...
    'direct_lines', 0);
end


function value = ternary(condition, whenTrue, whenFalse)
if condition
    value = whenTrue;
else
    value = whenFalse;
end
end
