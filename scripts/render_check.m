function files = render_check(scopePath, outDir, dpi)
%RENDER_CHECK Render every scope of a model to PNG for visual review.
%
%   render_check('MyModel')
%   render_check('MyModel', 'renders', 300)   % higher dpi for dense diagrams
%
% One PNG per diagram: root, every subsystem, every Stateflow chart /
% State Transition Table / Truth Table. The executing agent must look at
% each PNG; metrics alone never close readability. Windows opened here are
% left open (never close a window the user may already be using).

if nargin < 1 || isempty(scopePath)
    error('render_check:missingScope', 'scopePath is required');
end
if nargin < 2 || isempty(outDir)
    outDir = fullfile(pwd, 'renders');
end
if nargin < 3 || isempty(dpi)
    dpi = 150;
end
modelName = strtok(scopePath, '/');
load_system(modelName);
scopePath = strtrim(regexprep(scopePath, '/+$', ''));
if ~exist(outDir, 'dir')
    mkdir(outDir);
end

subsystems = find_system(scopePath, 'LookUnderMasks', 'all', 'FollowLinks', 'off', ...
    'BlockType', 'SubSystem');
prefix = [scopePath '/'];
subsystems = subsystems(startsWith(string(subsystems), prefix));

charts = {};
for mask = {'Stateflow', 'State Transition Table', 'Truth Table'}
    try
        found = find_system(scopePath, 'LookUnderMasks', 'all', 'FollowLinks', 'off', ...
            'MaskType', mask{1});
        charts = [charts; cellstr(found)]; %#ok<AGROW>
    catch
    end
end

scopes = unique([{scopePath}; cellstr(subsystems); charts], 'stable');
files = {};
for k = 1:numel(scopes)
    scope = strtrim(scopes{k});
    if isempty(scope) || ~strcmp(strtok(scope, '/'), modelName)
        continue;
    end
    outFile = fullfile(outDir, [strrep(scope, '/', '__') '.png']);
    try
        open_system(scope);
        print(['-s' scope], '-dpng', sprintf('-r%d', dpi), outFile);
        if exist(outFile, 'file')
            files{end + 1} = outFile; %#ok<AGROW>
            fprintf('rendered %s -> %s\n', scope, outFile);
        else
            fprintf('FAILED to render %s (no file)\n', scope);
        end
    catch ME
        fprintf('FAILED to render %s: %s\n', scope, ME.message);
    end
end
if isempty(files)
    error('render_check:noRender', 'No scope of %s could be rendered', scopePath);
end
fprintf('render_check: %d PNG file(s) in %s (dpi=%d)\n', numel(files), outDir, dpi);
end
