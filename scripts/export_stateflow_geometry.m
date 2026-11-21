function export_stateflow_geometry(chartPath, outFile)
%EXPORT_STATEFLOW_GEOMETRY Read one R2025b Stateflow chart as JSON.
%
%   export_stateflow_geometry('Controller/Chart', 'chart_geometry.json')
%
% This function does not edit the model. API-readable fields are exported as
% observed values. Fields that are not exposed by R2025b are left empty and
% listed in coverage.limitations so the Python linter can return
% UNVERIFIABLE instead of inventing a pass.

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
limitations = {};

root = sfroot;
charts = find(root, '-isa', 'Stateflow.Chart', 'Path', chartPath);
if isempty(charts)
    allCharts = find(root, '-isa', 'Stateflow.Chart');
    matches = allCharts(strcmp({allCharts.Path}, chartPath));
    if isempty(matches)
        error('export_stateflow_geometry:chartNotFound', ...
            'No Stateflow.Chart object found at %s', chartPath);
    end
    chart = matches(1);
else
    chart = charts(1);
end

chartObject = struct( ...
    'id', objectId('chart', chart), ...
    'name', cleanText(chart.Name), ...
    'path', chartPath, ...
    'decomposition', cleanText(chart.Decomposition), ...
    'action_language', cleanText(chart.ActionLanguage), ...
    'simulink_block_position', readNumeric(chartPath, 'Position'), ...
    'is_locked', logicalValue(chart, 'Locked'));

states = emptyStates();
stateObjects = find(chart, '-isa', 'Stateflow.State');
for k = 1:numel(stateObjects)
    obj = stateObjects(k);
    if ~belongsToChart(obj, chart)
        continue;
    end
    item = oneState();
    [item.parent_kind, item.parent_id] = objectIdentity(obj.Subviewer);
    item.id = objectId('state', obj);
    item.name = cleanText(obj.Name);
    item.label = textValue(obj, 'LabelString');
    item.position = readNumeric(obj, 'Position');
    item.decomposition = cleanText(obj.Decomposition);
    item.type = cleanText(obj.Type);
    item.entry_action = textValue(obj, 'EntryAction');
    item.during_action = textValue(obj, 'DuringAction');
    item.exit_action = textValue(obj, 'ExitAction');
    item.execution_order = readNumeric(obj, 'ExecutionOrder');
    item.is_subchart = logicalValue(obj, 'IsSubchart');
    item.is_grouped = logicalValue(obj, 'IsGrouped');
    states(end + 1) = item; %#ok<AGROW>
end

junctions = emptyJunctions();
junctionObjects = find(chart, '-isa', 'Stateflow.Junction');
for k = 1:numel(junctionObjects)
    obj = junctionObjects(k);
    if ~belongsToChart(obj, chart)
        continue;
    end
    item = oneJunction();
    [item.parent_kind, item.parent_id] = objectIdentity(obj.Subviewer);
    item.id = objectId('junction', obj);
    item.type = cleanText(obj.Type);
    position = readJunctionPosition(obj);
    item.center = position.center;
    item.radius = position.radius;
    item.position_status = position.status;
    junctions(end + 1) = item; %#ok<AGROW>
end

transitions = emptyTransitions();
transitionObjects = find(chart, '-isa', 'Stateflow.Transition');
for k = 1:numel(transitionObjects)
    obj = transitionObjects(k);
    if ~belongsToChart(obj, chart)
        continue;
    end
    item = oneTransition();
    [item.parent_kind, item.parent_id] = objectIdentity(obj.Subviewer);
    item.id = objectId('transition', obj);
    item.label = textValue(obj, 'LabelString');
    item.trigger = textValue(obj, 'Trigger');
    item.condition = textValue(obj, 'Condition');
    item.condition_action = textValue(obj, 'ConditionAction');
    item.transition_action = textValue(obj, 'TransitionAction');
    item.execution_order = readNumeric(obj, 'ExecutionOrder');

    [item.source_kind, item.source_id] = objectIdentity(obj.Source);
    [item.destination_kind, item.destination_id] = objectIdentity(obj.Destination);
    item.is_default = strcmp(item.source_kind, 'none') && ...
        ~strcmp(item.destination_kind, 'none');

    item.source_oclock = readNumeric(obj, 'SourceOClock');
    item.destination_oclock = readNumeric(obj, 'DestinationOClock');
    item.source_endpoint = readNumeric(obj, 'SourceEndpoint');
    item.destination_endpoint = readNumeric(obj, 'DestinationEndpoint');
    item.midpoints = numericPoints(readValue(obj, 'MidPoint'));
    item.label_position = readNumeric(obj, 'LabelPosition');
    item.geometry_status = transitionGeometryStatus(item);
    transitions(end + 1) = item; %#ok<AGROW>
end

data = emptyData();
dataObjects = find(chart, '-isa', 'Stateflow.Data');
for k = 1:numel(dataObjects)
    obj = dataObjects(k);
    if ~belongsToChart(obj, chart)
        continue;
    end
    item = struct();
    item.id = objectId('data', obj);
    item.name = cleanText(obj.Name);
    [item.parent_kind, item.parent_id] = objectIdentity(obj.Subviewer);
    item.scope = textValue(obj, 'Scope');
    item.data_type = textValue(obj, 'DataType');
    item.props = readValue(obj, 'Props');
    data(end + 1) = item; %#ok<AGROW>
end

events = emptyEvents();
eventObjects = find(chart, '-isa', 'Stateflow.Event');
for k = 1:numel(eventObjects)
    obj = eventObjects(k);
    if ~belongsToChart(obj, chart)
        continue;
    end
    item = struct();
    item.id = objectId('event', obj);
    item.name = cleanText(obj.Name);
    [item.parent_kind, item.parent_id] = objectIdentity(obj.Subviewer);
    item.scope = textValue(obj, 'Scope');
    item.trigger = textValue(obj, 'Trigger');
    events(end + 1) = item; %#ok<AGROW>
end

limitations{end + 1} = ...
    'Rendered label bounding boxes are not exposed; jc_0739 requires visual evidence or a separately calibrated renderer.';
limitations{end + 1} = ...
    'Transition geometry is exported from SourceEndpoint, MidPoint and DestinationEndpoint; curves/routes that are not represented there remain unverifiable.';

settings = struct();
settings.no_unconditional_default_transitions = ...
    modelDiagnostic(modelName, 'SFNoUnconditionalDefaultTransitionDiag');
settings.unreachable_execution_path = ...
    modelDiagnostic(modelName, 'SFUnreachableExecutionPathDiag');

payload = struct();
payload.schema_version = 'maab.stateflow_geometry/v1';
payload.standard = 'TARGET_MODELING_GUIDELINE_V5';
payload.matlab_version = ['R' version('-release')];
payload.model = modelName;
payload.chart_path = chartPath;
payload.chart = chartObject;
payload.states = structArrayToCell(states);
payload.transitions = structArrayToCell(transitions);
payload.junctions = structArrayToCell(junctions);
payload.data = structArrayToCell(data);
payload.events = structArrayToCell(events);
payload.settings = settings;
payload.coverage = struct( ...
    'states', numel(states), ...
    'transitions', numel(transitions), ...
    'junctions', numel(junctions), ...
    'data', numel(data), ...
    'events', numel(events), ...
    'limitations', {limitations});

jsonText = jsonencode(payload, 'PrettyPrint', true);
[fid, msg] = fopen(outFile, 'w', 'n', 'UTF-8');
if fid < 0
    error('export_stateflow_geometry:write', 'Cannot write %s: %s', outFile, msg);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s', jsonText);
fprintf( ...
    'wrote chart %s: %d states / %d transitions / %d junctions -> %s\n', ...
    chartPath, numel(states), numel(transitions), numel(junctions), outFile);
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


function [kind, id] = objectIdentity(object)
kind = 'none';
id = '';
if isempty(object)
    return;
end
try
    if isa(object, 'Stateflow.State')
        kind = 'state';
        id = objectId('state', object);
    elseif isa(object, 'Stateflow.Junction')
        kind = 'junction';
        id = objectId('junction', object);
    elseif isa(object, 'Stateflow.Chart')
        kind = 'chart';
        id = objectId('chart', object);
    end
catch
    kind = 'none';
    id = '';
end
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


function position = readJunctionPosition(object)
position = struct('center', [], 'radius', [], 'status', 'unavailable');
try
    raw = object.Position;
    position.center = double(raw.Center(:)');
    position.radius = double(raw.Radius);
    position.status = 'observed';
catch
end
end


function status = transitionGeometryStatus(item)
status = 'complete';
if isempty(item.source_endpoint) || isempty(item.destination_endpoint)
    status = 'missing_endpoints';
elseif isempty(item.midpoints)
    status = 'endpoints_only';
end
end


function points = numericPoints(value)
if isempty(value) || ~isnumeric(value)
    points = {};
    return;
end
if size(value, 2) == 2
    points = num2cell(double(value), 2);
elseif size(value, 1) == 2
    points = num2cell(double(value.'), 2);
elseif numel(value) == 2
    points = {double(value(:)')};
else
    points = {};
end
end


function value = structArrayToCell(value)
if isempty(value)
    value = {};
    return;
end
value = num2cell(value);
end


function setting = modelDiagnostic(modelName, parameter)
setting = struct( ...
    'status', 'unavailable', ...
    'value', '', ...
    'source', ['get_param(model,''' parameter ''')'], ...
    'reason', 'R2025b did not expose a readable value.');
try
    value = get_param(modelName, parameter);
    setting.status = 'observed';
    setting.value = cleanText(value);
    setting.reason = '';
catch ME
    setting.reason = ME.message;
end
end


function value = readNumeric(object, parameter)
raw = readValue(object, parameter);
value = [];
if isnumeric(raw) && ~isempty(raw)
    value = double(raw(:)');
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


function value = cleanText(value)
if isstring(value)
    value = char(value);
end
if ~ischar(value)
    value = '';
end
value = strtrim(value);
end


function value = emptyStates()
value = repmat(oneState(), 0, 1);
end


function value = oneState()
value = struct( ...
    'id', '', ...
    'name', '', ...
    'label', '', ...
    'position', [], ...
    'parent_kind', '', ...
    'parent_id', '', ...
    'decomposition', '', ...
    'type', '', ...
    'entry_action', '', ...
    'during_action', '', ...
    'exit_action', '', ...
    'execution_order', [], ...
    'is_subchart', [], ...
    'is_grouped', []);
end


function value = emptyTransitions()
value = repmat(oneTransition(), 0, 1);
end


function value = oneTransition()
value = struct( ...
    'id', '', ...
    'label', '', ...
    'trigger', '', ...
    'condition', '', ...
    'condition_action', '', ...
    'transition_action', '', ...
    'execution_order', [], ...
    'source_kind', '', ...
    'source_id', '', ...
    'destination_kind', '', ...
    'destination_id', '', ...
    'parent_kind', '', ...
    'parent_id', '', ...
    'is_default', false, ...
    'source_oclock', [], ...
    'destination_oclock', [], ...
    'source_endpoint', [], ...
    'destination_endpoint', [], ...
    'midpoints', zeros(0, 2), ...
    'label_position', [], ...
    'geometry_status', '');
end


function value = emptyJunctions()
value = repmat(oneJunction(), 0, 1);
end


function value = oneJunction()
value = struct( ...
    'id', '', ...
    'type', '', ...
    'parent_kind', '', ...
    'parent_id', '', ...
    'center', [], ...
    'radius', [], ...
    'position_status', '');
end


function value = emptyData()
value = repmat(struct( ...
    'id', '', ...
    'name', '', ...
    'parent_kind', '', ...
    'parent_id', '', ...
    'scope', '', ...
    'data_type', '', ...
    'props', ''), 0, 1);
end


function value = emptyEvents()
value = repmat(struct( ...
    'id', '', ...
    'name', '', ...
    'parent_kind', '', ...
    'parent_id', '', ...
    'scope', '', ...
    'trigger', ''), 0, 1);
end
