function export_geometry(scopePath, outFile)
%EXPORT_GEOMETRY Export one Simulink scope's appearance geometry (read-only).
%
%   export_geometry('Controller')
%   export_geometry('Controller/Algo', 'algo_geometry.json')
%
% Only direct children of the scope are exported, in scope-local coordinates.
% Fields are limited to what the appearance metrics need: block rects/types,
% Goto/From tags, line polylines and endpoints, and the editor crossing style.

if nargin < 1 || isempty(scopePath)
    error('export_geometry:missingScope', 'scopePath is required');
end
if nargin < 2 || isempty(outFile)
    [~, scopeName] = fileparts(scopePath);
    outFile = [scopeName '_geometry.json'];
end

modelName = strtok(scopePath, '/');
load_system(modelName);
scopePath = regexprep(strtrim(scopePath), '/+$', '');
limitations = {};

blockHandles = find_system(scopePath, 'SearchDepth', 1, 'FindAll', 'on', 'Type', 'Block');
blocks = {};
for k = 1:numel(blockHandles)
    bh = blockHandles(k);
    path = cleanText(getfullname(bh));
    if ~strcmp(parentOf(path), scopePath)
        continue;
    end
    b = struct('path', path, 'type', cleanText(get_param(bh, 'BlockType')), ...
        'position', numericRow(get_param(bh, 'Position')), ...
        'goto_tag', '', 'goto_tag_visibility', '');
    if strcmp(b.type, 'Goto') || strcmp(b.type, 'From')
        b.goto_tag = cleanText(get_param(bh, 'GotoTag'));
        if strcmp(b.type, 'Goto')
            b.goto_tag_visibility = cleanText(get_param(bh, 'TagVisibility'));
        end
    end
    blocks{end + 1} = b; %#ok<AGROW>
end

lineHandles = directLines(scopePath);
lines = {};
for k = 1:numel(lineHandles)
    lh = lineHandles(k);
    if ~ishandle(lh)
        continue;
    end
    points = get_param(lh, 'Points');
    if ~isnumeric(points) || size(points, 2) ~= 2 || size(points, 1) < 2
        limitations{end + 1} = sprintf('line %d has no readable Points', k); %#ok<AGROW>
        continue;
    end
    if all(all(diff(points, 1, 1) == 0, 2))
        % Zero-length stub handle (R2025b branch connector): not a signal line.
        continue;
    end
    [srcBlock, srcPort] = resolveEnd(lh, 'SrcBlockHandle', 'SrcPortHandle', 'Outport');
    [dstBlock, dstPort] = resolveEnd(lh, 'DstBlockHandle', 'DstPortHandle', 'Inport');
    lines{end + 1} = struct('id', sprintf('line_%d', k), 'points', points, ...
        'src_block', srcBlock, 'src_port', srcPort, ...
        'dst_block', dstBlock, 'dst_port', dstPort); %#ok<AGROW>
end

payload = struct();
payload.schema_version = 'maab.simulink_geometry/v2';
payload.model = modelName;
payload.scope = scopePath;
payload.coordinate_frame = 'scope-local';
payload.blocks = blocks;
payload.lines = lines;
payload.source_settings = struct('line_crossing', readCrossingStyle());
payload.coverage = struct('direct_blocks', numel(blocks), ...
    'direct_lines', numel(lines), 'limitations', {limitations});
writeJson(outFile, payload);
fprintf('wrote scope %s: %d blocks / %d lines / %d limitations -> %s\n', ...
    scopePath, numel(blocks), numel(lines), numel(limitations), outFile);
end

function handles = directLines(scopePath)
handles = [];
try
    handles = double(get_param(scopePath, 'Lines'));
catch
    % Root models do not expose 'Lines'; find_system covers them.
end
try
    searched = find_system(scopePath, 'SearchDepth', 1, 'FindAll', 'on', 'Type', 'line');
    handles = unique([handles(:); double(searched(:))]);
catch ME
    error('export_geometry:lines', 'Cannot enumerate lines of %s: %s', scopePath, ME.message);
end
handles = handles(isfinite(handles) & handles > 0);
end

function [blockPath, portIndex] = resolveEnd(lh, blockParam, portParam, portKind)
% Branch lines report -1 handles; walk LineParent to the trunk like the
% editor does, so branches keep the true source port (same-net identity).
blockPath = '';
portIndex = 0;
h = handleOf(lh, blockParam);
p = handleOf(lh, portParam);
depth = 0;
while (h <= 0 || p <= 0) && depth < 32
    parent = handleOf(lh, 'LineParent');
    if parent <= 0 || ~ishandle(parent)
        break;
    end
    lh = parent;
    if h <= 0, h = handleOf(lh, blockParam); end
    if p <= 0, p = handleOf(lh, portParam); end
    depth = depth + 1;
end
if h > 0 && ishandle(h)
    blockPath = cleanText(getfullname(h));
end
if h > 0 && p > 0
    try
        ports = get_param(h, 'PortHandles');
        candidates = ports.(portKind);
        idx = find(double(candidates(:)) == double(p), 1);
        if ~isempty(idx)
            portIndex = idx;
        end
    catch
        portIndex = 0;
    end
end
end

function value = handleOf(objectHandle, parameter)
value = -1;
try
    raw = get_param(objectHandle, parameter);
    if ~isempty(raw)
        value = double(raw(1));
    end
catch
end
end

function setting = readCrossingStyle()
setting = struct('status', 'unavailable', 'value', '', 'reason', '');
try
    raw = char(string(get_param(0, 'EditorPathXStyle')));
    if isempty(strtrim(raw))
        setting.reason = 'EditorPathXStyle returned empty';
    else
        setting.status = 'observed';
        setting.value = raw;
    end
catch ME
    setting.reason = ME.message;
end
end

function parent = parentOf(path)
slash = strfind(path, '/');
if isempty(slash)
    parent = '';
else
    parent = path(1:slash(end) - 1);
end
end

function value = cleanText(value)
if isstring(value), value = char(value); end
if ~ischar(value), value = ''; end
value = strtrim(strrep(value, newline, ''));
end

function value = numericRow(value)
if isempty(value) || ~isnumeric(value)
    value = [];
else
    value = double(value(:)');
end
end

function writeJson(outFile, payload)
jsonText = jsonencode(payload, 'PrettyPrint', true);
[fid, msg] = fopen(outFile, 'w', 'n', 'UTF-8');
if fid < 0
    error('export_geometry:write', 'Cannot write %s: %s', outFile, msg);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s', jsonText);
end
