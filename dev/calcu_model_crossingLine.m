[t, X, ps] = slx_crossings('./untitled.slx');
fprintf('全层级交叉总数 = %d\n', t);
for i = 1:numel(ps)
    fprintf('  [%s] %d\n', ps(i).system, ps(i).count);
end
for i = 1:numel(X)
    fprintf('#%d [%s] %s->%s  ×  %s->%s  @(%g,%g)\n', i, X(i).system, ...
        X(i).srcA, X(i).dstA, X(i).srcB, X(i).dstB, X(i).point);
end