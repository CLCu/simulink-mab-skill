function export_stateflow_geometry(chartPath, outFile)
%EXPORT_STATEFLOW_GEOMETRY Read one Stateflow chart's appearance geometry (read-only).
%
%   export_stateflow_geometry('Controller/Chart', 'chart_geometry.json')
%
% Exports only what chart visual review and advisory metrics need: state
% rects, junction centers, transition endpoints/midpoint/label position and
% the parent chain. Transition polylines are a 3-point sample of possibly
% curved routes; the editor PNG remains the authority.

if nargin < 1 || isempty(chartPath)
    error('export_stateflow_geometry:missingChart', 'chartPath is required');
end
if nargin < 2 || isempty(outFile)
    [~, chartName] = fileparts(chartPath);
    outFile = [chartName '_stateflow_geometry.json'];
end
modelName = strtok(chartPath, '/');
load_system(modelName);
chartPath = regexprep(strtrim(chartPath), '/+$', '');

root = sfroot;
charts = find(root, '-isa', 'Stateflow.Chart', 'Path', chartPath);
if isempty(charts)
    allCharts = find(root, '-isa', 'Stateflow.Chart');
    charts = allCharts(strcmp({allCharts.Path}, chartPath));
    if isempty(charts)
        error('export_stateflow_geometry:notFound', 'No Stateflow.Chart at %s', chartPath);
    end
end
chart = charts(1);

% NOTE: use indexed loops over Stateflow object arrays. `for obj = sfArray`
% iterates ONCE with obj bound to the whole array, so obj.Prop expands to a
% comma-separated list ("too many input arguments") and items get dropped.
stateObjects = find(chart, '-isa', 'Stateflow.State');
states = {};
for k = 1:numel(stateObjects)
    obj = stateObjects(k);
    if ~belongsToChart(obj, chart), continue; end
    rawPos = readNumeric(obj, 'Position');
    pos = [];
    if numel(rawPos) == 4
        pos = [rawPos(1), rawPos(2), rawPos(1) + rawPos(3), rawPos(2) + rawPos(4)];
    end
    sub = obj.Subviewer;
    name = obj.Name;
    grouped = logicalValue(obj, 'IsGrouped');
    [~, parentId] = identity(sub);
    states{end + 1} = struct('id', objectId('state', obj), 'name', cleanText(name), ...
        'parent_id', parentId, 'position', pos, 'is_grouped', grouped); %#ok<AGROW>
end

junctionObjects = find(chart, '-isa', 'Stateflow.Junction');
junctions = {};
for k = 1:numel(junctionObjects)
    obj = junctionObjects(k);
    if ~belongsToChart(obj, chart), continue; end
    center = [];
    radius = [];
    try
        jpos = obj.Position;
        center = double(jpos.Center(:)');
        radius = double(jpos.Radius);
    catch
    end
    sub = obj.Subviewer;
    [~, parentId] = identity(sub);
    junctions{end + 1} = struct('id', objectId('junction', obj), 'parent_id', parentId, ...
        'center', center, 'radius', radius); %#ok<AGROW>
end

transitionObjects = find(chart, '-isa', 'Stateflow.Transition');
transitions = {};
for k = 1:numel(transitionObjects)
    obj = transitionObjects(k);
    if ~belongsToChart(obj, chart), continue; end
    srcObj = obj.Source;
    dstObj = obj.Destination;
    [sk, sid] = identity(srcObj);
    [dk, did] = identity(dstObj);
    label = textValue(obj, 'LabelString');
    srcEnd = readNumeric(obj, 'SourceEndpoint');
    dstEnd = readNumeric(obj, 'DestinationEndpoint');
    midRaw = readValue(obj, 'MidPoint');
    labelPos = readNumeric(obj, 'LabelPosition');
    transitions{end + 1} = struct('id', objectId('transition', obj), ...
        'label', label, ...
        'source_kind', sk, 'source_id', sid, 'destination_kind', dk, 'destination_id', did, ...
        'is_default', strcmp(sk, 'none') && ~strcmp(dk, 'none'), ...
        'source_endpoint', srcEnd, 'destination_endpoint', dstEnd, ...
        'midpoints', numericPoints(midRaw), 'label_position', labelPos); %#ok<AGROW>
end

payload = struct();
payload.schema_version = 'maab.stateflow_geometry/v2';
payload.model = modelName;
payload.chart_path = chartPath;
payload.chart = struct('id', objectId('chart', chart), 'path', chartPath);
payload.states = states;
payload.junctions = junctions;
payload.transitions = transitions;
payload.coverage = struct('states', numel(states), 'junctions', numel(junctions), ...
    'transitions', numel(transitions), 'limitations', { ...
    'Transition polylines are SourceEndpoint+MidPoint+DestinationEndpoint samples; curved or hidden routes are not fully represented. Editor PNG is authoritative.'});
jsonText = jsonencode(payload, 'PrettyPrint', true);
[fid, msg] = fopen(outFile, 'w', 'n', 'UTF-8');
if fid < 0
    error('export_stateflow_geometry:write', 'Cannot write %s: %s', outFile, msg);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s', jsonText);
fprintf('wrote chart %s: %d states / %d junctions / %d transitions -> %s\n', ...
    chartPath, numel(states), numel(junctions), numel(transitions), outFile);
end

function tf = belongsToChart(object, chart)
tf = false;
try
    tf = isequal(object.Chart, chart);
catch
    try
        ancestor = object.Subviewer;
        for k = 1:32
            if isa(ancestor, 'Stateflow.Chart')
                tf = isequal(ancestor, chart);
                return;
            end
            ancestor = ancestor.Subviewer;
        end
    catch
        tf = false;
    end
end
end

function [kind, id] = identity(object)
kind = 'none';
id = '';
if isempty(object)
    return;
end
if isa(object, 'Stateflow.State')
    kind = 'state';
elseif isa(object, 'Stateflow.Junction')
    kind = 'junction';
elseif isa(object, 'Stateflow.Chart')
    kind = 'chart';
else
    return;
end
id = objectId(kind, object);
end

function id = objectId(kind, object)
raw = readValue(object, 'Id');
if isempty(raw)
    raw = readValue(object, 'SSIdNumber');
end
if isempty(raw)
    id = [kind '_unknown'];
else
    id = sprintf('%s_%d', kind, double(raw(1)));
end
end

function value = readValue(object, parameter)
try
    value = getfield(object, parameter); %#ok<GFLD>
catch
    try
        value = get_param(object, parameter);
    catch
        value = [];
    end
end
end

function value = readNumeric(object, parameter)
raw = readValue(object, parameter);
if isnumeric(raw) && ~isempty(raw)
    value = double(raw(:)');
else
    value = [];
end
end

function value = textValue(object, parameter)
raw = readValue(object, parameter);
if ischar(raw)
    value = raw;
elseif isstring(raw) && isscalar(raw)
    value = char(raw);
else
    value = '';
end
end

function value = logicalValue(object, parameter)
raw = readValue(object, parameter);
if islogical(raw) || (isnumeric(raw) && isscalar(raw))
    value = logical(raw);
else
    value = [];
end
end

function points = numericPoints(value)
if isempty(value) || ~isnumeric(value)
    points = {};
elseif size(value, 2) == 2
    points = num2cell(double(value), 2);
elseif numel(value) == 2
    points = {double(value(:)')};
else
    points = {};
end
end

function value = cleanText(value)
if isstring(value), value = char(value); end
if ~ischar(value), value = ''; end
value = strtrim(value);
end
