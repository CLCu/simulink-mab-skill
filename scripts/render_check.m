function files = render_check(scopePath, outDir)
%RENDER_CHECK Render every scope of a model to PNG for visual target-spec review.
%
%   render_check('MyModel')
%   render_check('MyModel', 'renders')
%   files = render_check(...)
%
% Target-spec v5 rules such as db_0097 (label overlap), jm_0002 (block
% recognizability), db_0142 (name position) and db_0140 (parameter display)
% cannot be verified from exported coordinates alone: the line-label
% bounding boxes are not exposed by the R2025b API. This script is the
% deterministic render step that closes that gap:
%
%   1. Render the root canvas.
%   2. Render every non-virtual SubSystem one level per scope set.
%   3. Render every Stateflow Chart.
%
% Output PNGs land in outDir (default: <pwd>/renders) named
% <model>__<scope-with-underscores>.png. Inspect each PNG (agent first,
% human sign-off second) and cite it as evidence for the visual rules.
% A lint verdict of "no VIOLATION" never replaces this step.

if nargin < 1 || isempty(scopePath)
    error('render_check:missingScope', 'scopePath is required');
end
modelName = strtok(scopePath, '/');
load_system(modelName);
scopePath = strtrim(regexprep(scopePath, '/+$', ''));

if nargin < 2 || isempty(outDir)
    outDir = fullfile(pwd, 'renders');
end
if ~exist(outDir, 'dir')
    mkdir(outDir);
end

% Collect scopes: root, subsystems, charts. Skip reference/linked blocks.
% NOTE: find_system wants search options (LookUnderMasks, FollowLinks)
% BEFORE parameter constraints (BlockType, MaskType), otherwise R2025b
% warns and the constraint is misparsed. Stateflow charts report
% BlockType 'SubSystem' in R2025b, so detect them via MaskType.
subsystems = find_system(scopePath, 'LookUnderMasks', 'all', ...
    'FollowLinks', 'off', 'BlockType', 'SubSystem');
subsystems = filterByParentDepth(subsystems, scopePath);

charts = [];
try
    charts = find_system(scopePath, 'LookUnderMasks', 'all', ...
        'FollowLinks', 'off', 'MaskType', 'Stateflow');
catch
end
if isempty(charts)
    try
        charts = find_system(scopePath, 'LookUnderMasks', 'all', ...
            'FollowLinks', 'off', 'BlockType', 'Chart');
    catch
        charts = [];
    end
end

scopes = [{scopePath}, subsystems(:)', charts(:)'];
scopes = unique(scopes, 'stable');

files = {};
for k = 1:numel(scopes)
    scope = strtrim(scopes{k});
    if isempty(scope) || ~strcmp(strtok(scope, '/'), modelName)
        continue;
    end
    base = strrep(scope, '/', '__');
    outFile = fullfile(outDir, [base '.png']);
    ok = renderScope(scope, outFile);
    if ok
        files{end + 1} = outFile; %#ok<AGROW>
        fprintf('rendered %s -> %s\n', scope, outFile);
    else
        fprintf('FAILED to render %s\n', scope);
    end
end
if isempty(files)
    error('render_check:noRender', ...
        'No scope of %s could be rendered; check the model loads cleanly.', scopePath);
end
fprintf('render_check: %d PNG file(s) in %s\n', numel(files), outDir);
end


function ok = renderScope(scope, outFile)
% Render one scope. Always open the scope first: closed-system print
% works for plain subsystems but yields a degenerate 104x104 canvas for
% Stateflow charts, whose extent is only computed once opened.
opened = false;
try
    open_system(scope);
    opened = true;
catch
    % Closed systems still print for plain subsystems; keep going.
end
try
    print(['-s' scope], '-dpng', '-r100', outFile);
    ok = exist(outFile, 'file') > 0;
catch ME
    fprintf('render %s failed: %s\n', scope, ME.message);
    ok = false;
end
% Close the subsystem window this call opened (never the root model).
if opened && ~strcmp(scope, strtok(scope, '/'))
    try
        close_system(scope, 0);
    catch
    end
end
end


function keep = filterByParentDepth(systems, scopePath)
% find_system returns block paths (cellstr) when given a system path.
% Keep every descendant path; each subsystem canvas gets its own PNG,
% which is what a reviewer needs (one file per diagram).
keep = {};
prefix = [scopePath '/'];
for k = 1:numel(systems)
    path = char(strtrim(systems{k}));
    if ~isempty(path) && strncmp(path, prefix, numel(prefix))
        keep{end + 1} = path; %#ok<AGROW>
    end
end
end
