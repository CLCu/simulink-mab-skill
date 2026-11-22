function [total, X, perSys] = slx_crossings(arg)
%SLX_CROSSINGS 全层级信号线交叉检测：总数 + 交叉对 + 交叉点
% 输入: 'model' | 'model/Sub' | './x.slx' | 'x.mdl'
arg = char(arg);
if ~isempty(regexp(arg,'\.(slx|mdl)$','once')) || exist(arg,'file')==2
    [~,mdl] = fileparts(arg);
    if ~bdIsLoaded(mdl), open_system(arg); end
else
    mdl = strtok(arg,'/');
    if ~bdIsLoaded(mdl), load_system(mdl); end
end
systems = [{mdl}; find_system(mdl,'LookUnderMasks','all','FollowLinks','on', ...
            'Type','block','BlockType','SubSystem')];

tol = 1e-6;
total = 0;
X = struct('system',{},'lineA',{},'lineB',{},'srcA',{},'dstA',{}, ...
           'srcB',{},'dstB',{},'point',{});
perSys = struct('system',{},'count',{});

for s = 1:numel(systems)
    sys = systems{s};
    try, lh = find_system(sys,'SearchDepth',1,'FindAll','on','Type','line');
    catch, continue; end

    % 拆线段并分类 H/V
    S = struct('li',{},'a',{},'b',{},'ori',{});
    for i = 1:numel(lh)
        pts = get_param(lh(i),'Points');
        for k = 1:size(pts,1)-1
            a = pts(k,:); b = pts(k+1,:);
            if isequal(a,b), continue; end
            if a(2)==b(2), ori='H';
            elseif a(1)==b(1), ori='V';
            else, ori='D'; end          % 斜线：正交假设外，跳过
            S(end+1) = struct('li',i,'a',a,'b',b,'ori',ori);
        end
    end

    cnt = 0; keys = {};
    for i = 1:numel(S)
        for j = i+1:numel(S)
            if S(i).li == S(j).li, continue; end        % 同线自交不算
            if S(i).ori=='D' || S(j).ori=='D', continue; end
            if S(i).ori == S(j).ori, continue; end      % 同向=重叠另计
            p = orth_cross(S(i), S(j), tol);
            if isempty(p), continue; end
            key = sprintf('%d_%d_%.3f_%.3f', min(S(i).li,S(j).li), ...
                          max(S(i).li,S(j).li), p(1), p(2));
            if ismember(key, keys), continue; end       % 同对同点去重
            keys{end+1} = key;
            cnt = cnt + 1;
            [sA,dA] = endpoints(lh(S(i).li));
            [sB,dB] = endpoints(lh(S(j).li));
            X(end+1) = struct('system',sys,'lineA',lh(S(i).li),'lineB',lh(S(j).li), ...
                'srcA',sA,'dstA',dA,'srcB',sB,'dstB',dB,'point',p);
        end
    end
    total = total + cnt;
    perSys(end+1) = struct('system',sys,'count',cnt);
end
end

% ---- 局部函数 ----
function p = orth_cross(u, v, tol)
if u.ori=='V', t=u; u=v; v=t; end      % u=H, v=V
hy = u.a(2); vx = v.a(1);
hx = [min(u.a(1),u.b(1)) max(u.a(1),u.b(1))];
vy = [min(v.a(2),v.b(2)) max(v.a(2),v.b(2))];
if vx > hx(1)+tol && vx < hx(2)-tol && hy > vy(1)+tol && hy < vy(2)-tol
    p = [vx hy];                        % 严格内部相交=真交叉
else
    p = [];                             % 端点/分支挂接=连接，不算
end
end

function [s,d] = endpoints(lh)
sp = firstval(get_param(lh,'SrcPortHandle')); p = lh;
while sp <= 0
    par = firstval(get_param(p,'LineParent'));
    if par <= 0, break; end
    p = par; sp = firstval(get_param(p,'SrcPortHandle'));
end
dp = firstval(get_param(lh,'DstPortHandle'));
s = pstr(sp); d = pstr(dp);
end

function t = pstr(h)
if isempty(h)||~isnumeric(h)||h<=0, t='<branch>'; return; end
try, parent = tostr(get_param(h,'Parent')); catch, parent='?'; end
try, pn = tostr(get_param(h,'PortNumber')); catch, pn='?'; end
t = [parent '/' pn];
end

function v = firstval(v)
if isempty(v), v=-1; else v=v(1); end
end

function s = tostr(v)
if isempty(v), s='';
elseif iscell(v), s=strjoin(cellfun(@tostr,v,'UniformOutput',false),',');
elseif ischar(v), s=v;
elseif isstring(v), s=char(v);
elseif isnumeric(v), s=num2str(v);
else, s='<obj>'; end
end