function export_geometry(scopePath, outFile)
%EXPORT_GEOMETRY Export one Simulink scope for fail-closed target-spec v5 linting.
%
%   export_geometry('Controller')
%   export_geometry('Controller/ControlAlgorithm', 'control_geometry.json')
%
% The function is read-only: it loads the model if needed, reads only direct
% children of the requested scope, and writes scope-local geometry JSON.
% Nested subsystem contents are intentionally excluded.

if nargin < 1 || isempty(scopePath)
    error('export_geometry:missingScope', 'scopePath is required');
end
if nargin < 2 || isempty(outFile)
    [~, scopeName] = fileparts(scopePath);
    outFile = [scopeName '_geometry.json'];
end

modelName = strtok(scopePath, '/');
load_system(modelName);
scopePath = strtrim(scopePath);
scopePath = regexprep(scopePath, '/+$', '');

limitations = {};

% Direct blocks only. Do not use recursive coordinates from nested subsystems.
blockHandles = find_system(scopePath, 'SearchDepth', 1, 'FindAll', 'on', ...
    'Type', 'Block');
blockHandles = filterDirectBlocks(blockHandles, scopePath);

blocks = emptyBlocks();
for k = 1:numel(blockHandles)
    bh = blockHandles(k);
    b = oneBlock();
    try
        b.path = cleanText(getfullname(bh));
        b.type = cleanText(get_param(bh, 'BlockType'));
        b.position = numericRow(get_param(bh, 'Position'));
        [b.orientation, b.orientation_status] = observedText(bh, 'Orientation');
        b.shadow = observedLogical(bh, 'DropShadow');
        if isempty(b.shadow)
            b.shadow = observedLogical(bh, 'Shadow');
        end
        [b.name_placement, b.name_placement_status] = ...
            observedText(bh, 'NamePlacement');
        [ports, limitations] = readPorts(bh, limitations);
        b.ports = structArrayToCell(ports);
        b.block_type = b.type;
        blocks(end + 1) = b; %#ok<AGROW>
    catch ME
        error('export_geometry:blockRead', ...
            'Cannot export direct block %s: %s', getfullname(bh), ME.message);
    end
end

% Lines directly in the selected scope. Include branches and deduplicate handles.
try
    lineHandles = handleNumbers(get_param(scopePath, 'Lines'));
catch
    lineHandles = [];
    limitations{end + 1} = 'get_param(scope,''Lines'') did not return direct lines.';
end
try
    searched = handleNumbers(find_system(scopePath, 'SearchDepth', 1, ...
        'FindAll', 'on', 'Type', 'line'));
    lineHandles = unique([lineHandles(:); searched(:)]);
catch ME
    limitations{end + 1} = sprintf('Line search limitation: %s', ME.message);
end
lineHandles = lineHandles(isfinite(lineHandles) & lineHandles > 0);

lines = emptyLines();
for k = 1:numel(lineHandles)
    lh = lineHandles(k);
    if ~ishandle(lh)
        continue;
    end
    L = oneLine();
    L.id = sprintf('line_%d', k);
    try
        points = get_param(lh, 'Points');
        if isnumeric(points) && size(points, 2) == 2
            L.points = points;
        else
            L.points = zeros(0, 2);
            limitations{end + 1} = sprintf('%s has no readable Points.', L.id); %#ok<AGROW>
        end

        srcHandle = handleValue(lh, 'SrcBlockHandle');
        if srcHandle <= 0
            srcHandle = parentSourceHandle(lh, 0);
        end
        dstHandle = handleValue(lh, 'DstBlockHandle');
        srcPortHandle = handleValue(lh, 'SrcPortHandle');
        dstPortHandle = handleValue(lh, 'DstPortHandle');

        [L.src_block, srcIndex] = resolveEndpoint(srcHandle, srcPortHandle, 'out');
        [L.dst_block, dstIndex] = resolveEndpoint(dstHandle, dstPortHandle, 'in');
        L.src_port = srcIndex;
        L.dst_port = dstIndex;
        [L.name, ~] = observedText(lh, 'Name');
        parent = handleValue(lh, 'LineParent');
        if parent > 0
            L.parent_line_id = sprintf('line_%d', find(lineHandles == parent, 1));
        end
        L.point_frame = 'scope-local';
        lines(end + 1) = L; %#ok<AGROW>
    catch ME
        error('export_geometry:lineRead', ...
            'Cannot export line handle %g: %s', lh, ME.message);
    end
end

setting = readLineCrossingSetting(modelName);
payload = struct();
payload.schema_version = 'maab.simulink_geometry/v1';
payload.standard = 'TARGET_MODELING_GUIDELINE_V5';
payload.matlab_version = ['R' version('-release')];
payload.model = modelName;
payload.scope = scopePath;
payload.scope_type = ternary(strcmp(scopePath, modelName), 'model', 'subsystem');
payload.coordinate_frame = 'scope-local';
payload.blocks = structArrayToCell(blocks);
payload.lines = structArrayToCell(lines);
payload.source_settings = struct('line_crossing', setting);
payload.coverage = struct( ...
    'direct_blocks', numel(blocks), ...
    'direct_lines', numel(lines), ...
    'nested_content_exported', false, ...
    'limitations', {limitations});

jsonText = jsonencode(payload, 'PrettyPrint', true);
[fid, msg] = fopen(outFile, 'w', 'n', 'UTF-8');
if fid < 0
    error('export_geometry:write', 'Cannot write %s: %s', outFile, msg);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s', jsonText);
fprintf( ...
    'wrote scope %s: %d direct blocks / %d direct lines / %d limitations -> %s\n', ...
    scopePath, numel(blocks), numel(lines), numel(limitations), outFile);
end


function handles = filterDirectBlocks(handles, scopePath)
keep = false(size(handles));
for k = 1:numel(handles)
    try
        path = cleanText(getfullname(handles(k)));
        slash = strfind(path, '/');
        parent = '';
        if ~isempty(slash)
            parent = path(1:slash(end) - 1);
        end
        keep(k) = strcmp(parent, scopePath);
    catch
        keep(k) = false;
    end
end
handles = handles(keep);
end


function [ports, limitations] = readPorts(blockHandle, limitations)
ports = emptyPorts();
try
    counts = get_param(blockHandle, 'Ports');
catch
    counts = [0 0];
end
inputCount = 0;
outputCount = 0;
if isnumeric(counts) && numel(counts) >= 2
    inputCount = counts(1);
    outputCount = counts(2);
end
try
    connectivity = get_param(blockHandle, 'PortConnectivity');
catch ME
    limitations{end + 1} = sprintf( ...
        'PortConnectivity unavailable for %s: %s', ...
        getfullname(blockHandle), ME.message);
    return;
end
for p = 1:numel(connectivity)
    item = onePort();
    item.number = p;
    item.index = p;
    item.type_code = cleanText(connectivity(p).Type);
    if p <= inputCount
        item.direction = 'in';
    elseif p <= inputCount + outputCount
        item.direction = 'out';
    else
        item.direction = 'control';
    end
    item.position = numericRow(connectivity(p).Position);
    srcBlocks = handleListNames(connectivity(p).SrcBlock);
    dstBlocks = handleListNames(connectivity(p).DstBlock);
    item.src_blocks = srcBlocks;
    item.dst_blocks = dstBlocks;
    item.src_port = numericRow(connectivity(p).SrcPort);
    item.dst_port = numericRow(connectivity(p).DstPort);
    item.connected = ~isempty(srcBlocks) || ~isempty(dstBlocks);
    ports(end + 1) = item; %#ok<AGROW>
end
end


function [blockPath, portIndex] = resolveEndpoint(blockHandle, portHandle, kind)
blockPath = '';
portIndex = [];
if blockHandle > 0 && ishandle(blockHandle)
    try
        blockPath = cleanText(getfullname(blockHandle));
    catch
        blockPath = '';
    end
end
if blockHandle > 0 && ~isempty(portHandle) && portHandle > 0
    try
        portIndex = portNumber(blockHandle, portHandle, kind);
    catch
        portIndex = [];
    end
end
end


function index = portNumber(blockHandle, portHandle, kind)
try
    handles = get_param(blockHandle, 'PortHandles');
    if strcmp(kind, 'in')
        candidates = handles.Inport;
    else
        candidates = handles.Outport;
    end
    index = find(double(candidates(:)) == double(portHandle), 1);
    if isempty(index)
        index = [];
    end
catch
    index = [];
end
end


function handle = parentSourceHandle(lineHandle, depth)
handle = -1;
if depth > 32 || ~ishandle(lineHandle)
    return;
end
source = handleValue(lineHandle, 'SrcBlockHandle');
if source > 0 && ishandle(source)
    handle = source;
    return;
end
try
    parent = get_param(lineHandle, 'LineParent');
catch
    parent = -1;
end
if parent > 0 && ishandle(parent)
    handle = parentSourceHandle(parent, depth + 1);
end
end


function names = handleListNames(values)
names = {};
if isempty(values)
    return;
end
for k = 1:numel(values)
    h = double(values(k));
    if h > 0 && ishandle(h)
        try
            names{end + 1} = cleanText(getfullname(h)); %#ok<AGROW>
        catch
        end
    end
end
end


function value = handleValue(objectHandle, parameter)
value = -1;
try
    raw = get_param(objectHandle, parameter);
    if ~isempty(raw)
        value = double(raw(1));
    end
catch
end
end


function [value, status] = observedText(objectHandle, parameter)
value = '';
status = 'unavailable';
try
    raw = get_param(objectHandle, parameter);
    if ischar(raw)
        value = raw;
        status = 'observed';
    elseif isstring(raw) && isscalar(raw)
        value = char(raw);
        status = 'observed';
    end
catch
end
end


function value = observedLogical(objectHandle, parameter)
value = [];
try
    raw = get_param(objectHandle, parameter);
    if islogical(raw) || isnumeric(raw)
        value = logical(raw(1));
    elseif ischar(raw) || (isstring(raw) && isscalar(raw))
        value = any(strcmpi(char(raw), {'on', 'true', '1'}));
    end
catch
end
end


function value = cleanText(value)
if isstring(value)
    value = char(value);
end
if ~ischar(value)
    value = '';
end
value = strrep(value, newline, '');
value = strtrim(value);
end


function value = numericRow(value)
if isempty(value) || ~isnumeric(value)
    value = [];
else
    value = double(value(:)');
end
end


function handles = handleNumbers(value)
handles = [];
if isempty(value)
    return;
end
if isnumeric(value)
    handles = double(value(:));
    return;
end
if iscell(value)
    values = zeros(numel(value), 1);
    for k = 1:numel(value)
        item = value{k};
        if isnumeric(item) || islogical(item)
            values(k) = double(item(1));
        elseif isobject(item)
            values(k) = double(item);
        else
            error('export_geometry:handleType', ...
                'Unsupported line handle type in cell: %s', class(item));
        end
    end
    handles = values;
    return;
end
if isobject(value)
    handles = double(value(:));
    return;
end
error('export_geometry:handleType', 'Unsupported line handle type: %s', class(value));
end


function value = structArrayToCell(value)
if isempty(value)
    value = {};
    return;
end
value = num2cell(value);
end


function setting = readLineCrossingSetting(modelName)
% R2025b does not expose the canvas line-crossing style programmatically.
% Verified dead ends (do not re-guess): Simulink.Preferences.get,
% get_param(model|root,'LineCrossingStyle'), and the settings tree
% (settings.Simulink.* has no LineCrossingStyle entry).
% Therefore lint must keep db_0032-a2 UNVERIFIABLE on any crossing.
setting = struct( ...
    'status', 'unavailable', ...
    'value', '', ...
    'source', '', ...
    'reason', ['R2025b 无编程接口读取 line-crossing style；' ...
        '已验证无效路径: Simulink.Preferences.get / get_param(model|root) / settings 树。' ...
        '存在交叉时 db_0032-a2 保持 UNVERIFIABLE，用 render_check 截图供人工签核。']);
for k = 1:3
    try
        switch k
            case 1
                value = Simulink.Preferences.get('LineCrossingStyle');
            case 2
                value = get_param(modelName, 'LineCrossingStyle');
            case 3
                value = get_param(0, 'LineCrossingStyle');
        end
        if ~isempty(value)
            setting.status = 'observed';
            setting.value = char(string(value));
            setting.source = sprintf('candidate_%d', k);
            setting.reason = '';
            return;
        end
    catch
        % Fail closed: keep probing remaining candidates.
    end
end
end


function value = ternary(condition, whenTrue, whenFalse)
if condition
    value = whenTrue;
else
    value = whenFalse;
end
end


function value = emptyBlocks()
value = repmat(struct( ...
    'path', '', ...
    'type', '', ...
    'block_type', '', ...
    'position', [], ...
    'orientation', '', ...
    'orientation_status', '', ...
    'shadow', [], ...
    'name_placement', '', ...
    'name_placement_status', '', ...
    'ports', emptyPorts()), 0, 1);
end


function value = oneBlock()
value = struct( ...
    'path', '', ...
    'type', '', ...
    'block_type', '', ...
    'position', [], ...
    'orientation', '', ...
    'orientation_status', '', ...
    'shadow', [], ...
    'name_placement', '', ...
    'name_placement_status', '', ...
    'ports', emptyPorts());
end


function value = emptyPorts()
value = repmat(struct( ...
    'number', [], ...
    'index', [], ...
    'type_code', '', ...
    'direction', '', ...
    'position', [], ...
    'src_blocks', {{}}, ...
    'dst_blocks', {{}}, ...
    'src_port', [], ...
    'dst_port', [], ...
    'connected', []), 0, 1);
end


function value = onePort()
value = struct( ...
    'number', [], ...
    'index', [], ...
    'type_code', '', ...
    'direction', '', ...
    'position', [], ...
    'src_blocks', {{}}, ...
    'dst_blocks', {{}}, ...
    'src_port', [], ...
    'dst_port', [], ...
    'connected', []);
end


function value = emptyLines()
value = repmat(struct( ...
    'id', '', ...
    'points', [], ...
    'src_block', '', ...
    'src_port', [], ...
    'dst_block', '', ...
    'dst_port', [], ...
    'name', '', ...
    'parent_line_id', '', ...
    'point_frame', ''), 0, 1);
end


function value = oneLine()
value = struct( ...
    'id', '', ...
    'points', [], ...
    'src_block', '', ...
    'src_port', [], ...
    'dst_block', '', ...
    'dst_port', [], ...
    'name', '', ...
    'parent_line_id', '', ...
    'point_frame', '');
end
