# SATK 外观布局建模与验证工作流

本文件是本次模型修改、几何检查和视觉复核的唯一执行契约。目标是让模型的外观、布局、连线和标签可读且符合目标建模规范（v5）相关要求，不是执行第 3/4 章全量规则审查。

## 1. 职责与顺序

| 工作 | 唯一责任方 |
| --- | --- |
| 库/块策略门槛 | `building-simulink-models` |
| 建块、连线、参数和层级 | `model_read` / `model_edit` |
| 移动、局部布局、完整布局和精确坐标 | `arranging-simulink-layouts` / `model_edit` |
| 坐标预规划 | `layout_plan.py` |
| Simulink 几何验证 | `export_all_geometry.m` + `layout_lint.py --manifest`；修复定位时可用 `export_geometry.m` + 单 scope lint |
| Stateflow 几何验证 | `export_stateflow_geometry.m` + `stateflow_lint.py` |
| 编辑器图面复核 | `render_check.m` |

```text
已有模型 baseline 几何（新建模型跳过）
→ spec.json → plan JSON → model_edit → 布局 → model_check
→ Simulink 全层级几何 manifest → 汇总 lint / 项目外观门禁
→ 初版 PNG 渲染与逐图检查 → 迭代修复
→ Stateflow 导出/lint → 最终 PNG 渲染与逐图复核
→ 外观布局结论
```

初次视觉检查用于尽早发现拥挤、交叉和错误分组，不能等到最后才看图。最终渲染必须再次发生在所有结构和 Stateflow lint 修复之后；否则 Chart 或图面证据可能已过期。禁止维护替代 SATK 的 MATLAB 建模型脚本。本闭环不判定功能正确性、数据语义或完整目标规范合规。

目标规范合格与项目视觉质量分开判断：`db_0032-a1/a2` 可以通过 `Line Hop` 满足显示要求，但只要 `appearance_quality` 仍报告交叉，项目外观结论就不能写成通过（仅极小残留豁免全部条件满足并获准时例外）。

规则只按“是否影响图面/可读性”或“是否使图面关系无法可靠判定”纳入。结构前提帮助判断层级和块关系，但不能被扩展成功能正确性或完整目标规范合规的证明。

## 2. 从规格到 SATK

`spec.json` 至少记录功能、真实端口、数据类型、参数来源、层级边界、信号流和目标 scope。`layout_plan.py` 输出 plan JSON，不修改模型。

plan 必须包含 schema、目标建模规范 v5、NA-MAAB/JMAAB、R2025b、逻辑块、端口、连接、建议位置、分叉树和反馈边。同一物理输出端口连接多个消费者时共享一个端点。

执行前先读取 `building-simulink-models` 并完成库/块策略门槛。把 plan 映射为 `model_edit`：

1. 新块在同一次调用中用 `ref` 和 `#ref`。
2. 跨调用使用响应返回的 `blk_X`，不得拼块路径。
3. 连接使用 `blk_X.yN -> blk_Y.uN`。
4. 复杂层级一次只编辑一个 scope。
5. 返回 `partial` 时立即执行 `model_read` 和 `model_check`。

若当前 `model_edit` 无法表达计划，缩小 scope、拆分调用或回到计划阶段；不得用 `evaluate_matlab_code` 绕过。

## 3. 布局

读取 `arranging-simulink-layouts` 后再操作：

- 新建空 scope 可使用 `layout_mode="full"`。
- 已有模型默认使用增量布局。
- 已有图的整图重排会移动所有块，必须先取得用户同意。
- 已有模型在第一次布局修改前，先导出全层级 baseline manifest；baseline 导出后不得继续沿用更早的版本。
- 精确位置通过 `model_edit.configure` 设置。
- 布局后运行 `model_check`，只以悬空端口、缺少目标、结构无法更新等会影响图面判定的错误作为本轮阻断项；其他诊断记录为未覆盖范围。

最终版面以实际模型为准，不以 plan 或自动布局响应中的建议坐标为准。

处理交叉时每次只改一条候选路径，通过功能分区、端口对齐、块顺序、专用走廊或重走正交线解决。`Goto/From` 只允许在第 4 节残留裁决阶段按预算和证据使用。若修改后第一优先指标 `crossing_events` 没有下降，不得批量复制同一方案。

## 4. Simulink 几何检查

全模型检查先导出所有有直接 Simulink 图面内容的 scope。`export_all_geometry.m` 会打开模型以确保 R2025b 的 `Points` 已反映真实路由，逐 scope 写入几何 JSON 和 `manifest.json`：

```matlab
export_all_geometry('Model', fullfile(pwd, 'geometry_current'))
```

然后按层级汇总，不混合不同 scope 的坐标：

```text
python scripts/layout_lint.py --manifest geometry_current/manifest.json \
  --out geometry_current/model_lint.json
```

已有模型必须同时提供修改前的全层级 manifest：

```text
python scripts/layout_lint.py --manifest geometry_current/manifest.json \
  --mode existing --baseline geometry_before/manifest.json \
  --out geometry_current/model_lint.json
```

manifest 列出每个有直接块/线的 scope，Chart 内部等没有 Simulink 直接图面的 scope 记入 `skipped_scopes`，由 Stateflow 检查负责。任一 scope 导出失败、文件缺失、scope/model 不匹配或坐标帧不合法时，全模型结论保持 `INVALID`。

单 scope 检查仍用于定位与修复，一次只处理一个 scope 的直接子块与线，使用 scope-local 坐标：

```text
export_geometry('Model/Subsystem', 'Subsystem_geometry.json')
```

JSON 必须包含标准、MATLAB 版本、scope、块 Position/类型/朝向/名称位置/阴影、原始端口连接、线点集、源/目标块与端口、反馈标记、line-crossing 设置状态、覆盖与忽略项。缺字段或 scope 混合时不得推断通过。

```text
python scripts/layout_lint.py <current_geometry.json> --mode new --json
python scripts/layout_lint.py <current_geometry.json> --mode existing \
  --baseline <baseline_geometry.json> --json
```

- `0`：无自动 `VIOLATION`、无阻断性 `UNVERIFIABLE`，且 `appearance_quality=PASS`；可仍有 `MANUAL` 项，必须逐张检查当前 PNG 后才能交付。
- `1`：存在规则 `VIOLATION` 或 `appearance_quality=FAIL`。
- `2`：schema 无效、仍有阻断性的 `UNVERIFIABLE` 或 `appearance_quality=INVALID`；已有模型未提供有效 baseline 也属于这一类。
- 自动化不得把 `2` 当作通过。
- 退出码 `0` 只表示几何门禁可进入视觉签核，不表示全部 `MANUAL` 项已经关闭。

`--manifest` 输出 `appearance_quality.summary` 的全模型汇总：

- `line_count`、`total_length`、`total_bends`、`max_bends`；
- `crossing_events`、`crossing_pairs`、`overlap_events`、`through_block_events`、`diagonal_segments`、`goto_from_blocks`；
- `hotspots` 与 `repair_order`，默认先修交叉最多的 scope；
- 每个热点 scope 的 `top_crossing_groups` 和 `next_actions`。

`--out` 同时写出全局报告及 `*.scopes/` 下的逐 scope lint 报告；逐 scope 报告包含每条线的顶点数、折弯数和坐标长度。不同层级只汇总计数，不跨 scope 比较坐标。

R2025b 的 line crossing style 是 Simulink 编辑器全局偏好，不是模型参数。导出器通过 `get_param(0,'EditorPathXStyle')` 读取实际值：`hop` 对应 `Line Hop`，`grad_pin` 对应 `Tunnel`，`none` 对应 `None`。存在交叉时，只有实际值为 `hop` 才满足 `db_0032-a2`；`layout-profile.json` 的值不能代替该读取结果。该设置只影响规范兜底显示，项目外观门禁仍因交叉而失败。

`layout_lint.py` 同时输出两套结论：

- `overall/profile_summary/items`：目标规范覆盖项结论。
- `appearance_quality`：项目外观几何门禁，包含 `crossing_events`、`crossing_pairs`、`overlap_events`、`through_block_events`、`diagonal_segments`、`goto_from_blocks`、交叉线对、坐标、Goto/From 预算、配对违规与转换候选。

新 scope 的四个硬指标均须为 0。已有模型还必须提供同 model、同 scope 的修改前 baseline，四个硬指标仍须为 0 且相对 baseline 不得增加。Goto/From 按 `goto_from_policy` 预算与证据门禁判定：超预算、未配对、非 local 可见性、Inport 直连 Goto、From→Goto 链式、每 tag From 超过 2 个或缺少新增 tag 裁决证据均 FAIL；baseline 中已存在的 tag 免证据。缺失、无效或不匹配的 baseline 使结果保持 `INVALID`。

`layout_lint.py` 为每条导出信号线输出顶点数、方向变化次数（折弯数）和折线坐标长度。处理原则如下：

| 诊断 | 判定意义 | 处理 |
| --- | --- | --- |
| 交叉点 | 报告交叉的两条线及交叉坐标；共享端点不冒充交叉；`Line Hop` 不减少计数 | 移动输入/输出块、调整功能分区与端口、分配专用走廊或重走正交线；几何手段穷尽后按残留裁决阶段受限转换 Goto/From，仍无法消除时按极小豁免条件处理或报告遗留项 |
| 共线重叠 | 不同信号线共享同一线段，直接违反 `db_0032-b` | 移动块或重走线路，必须分开；`Line hop` 不能修复重叠 |
| 折弯数 | 线段方向变化次数，忽略重复点和共线冗余顶点 | 不按固定数字自动判违规；检查绕行和冗余转折并重新布局。例：5 次折弯先定位其来源，简化到保持语义和端口关系所需的最少转折，再重新导出、lint 和渲染 |
| 折线长度 | 坐标单位下的路径总长，不是目标规范阈值 | 只用于前后对比和发现异常绕行；不能单独证明合规或违规 |

检测到交叉后按以下闭环处理：

1. 先处理 `hotspots` 中交叉最多的 scope，再处理其中 `top_crossing_groups` 事件最多的端点组。同一对子系统反复交叉通常意味着端口顺序或功能分区错误。
2. 每次只改一组相关交叉：优先调整 Inport/Outport 与子系统端口的纵向顺序、同一功能列内块顺序、输出块位置、专用走廊或反馈走廊；超过两路的分支改为显式分支树。
3. 对同一对子系统的大量并行信号，评估语义一致的 Bus 或显式接口子系统；只有不改变功能的布局调整属于本 Skill 的默认权限，架构变更需单独说明。
4. 修改后重新导出受影响 scope，再运行全模型 manifest lint；当前 `crossing_events` 未下降则撤销本组方案。连续 3 轮无净改善时进入残留裁决阶段，不得继续无限重排。
5. 残留裁决阶段：按 `goto_conversion_candidates` 逐簇转换（先 1 条再 2 条），每对写入 `maab.goto_justification/v1` 证据并随 `--goto-justification` 提交；预算耗尽后仍残留 ≤2 处/≤2 线交叉且实际为 hop 时，可申请极小豁免（证据中 `geometry_exhausted=true` + `residual_waiver.claimed=true` + reason），门禁 PASS 但附 MANUAL PNG 复核。不满足条件则停止并报告受阻线对和端口。大面积 Line Hop 禁止。

比较一次布局修改时使用项目 profile 的 `acceptance_order`：先看 `crossing_events`，再看重叠、穿块、斜线和 `goto_from_blocks`，最后用折弯数和长度判断是否存在异常绕行。前一指标没有改善时，不能接受仅把交叉转移到更差位置、超预算新增 `Goto/From` 或让线路更长的修改。

`Goto/From` 是受限的最后手段，不是默认布局工具。不要因为目标规范允许 `Inport → Goto`、`jc_0171-a` 有 Goto/From 例外或其他模型使用了该写法，就绕过预算与证据新增 `Goto/From`；本项目禁止 Inport 直连 Goto。新 scope 同样受预算约束（预算按功能块数计算，不是无条件为零）；已有模型 baseline 中既有 tag 可保留，新增 tag 必须有裁决证据。

如果消除交叉需要跨功能区域分发信号，优先调整端口、功能分区、子系统边界、分支树或显式接口，并重新渲染检查。几何方案穷尽后才按残留裁决阶段转换 Goto/From；预算耗尽仍无法关闭时，按极小豁免条件处理或停止本轮布局修改并报告具体交叉线对和受阻原因。

任何重走线路都通过 `arranging-simulink-layouts` 和 `model_edit` 完成。修复后必须重新导出几何、运行 lint 并生成最终 PNG，不能沿用修复前的图面证据。

`db_0097` 的标签重叠只按项目字号估算，可能漏报。估算未发现冲突也不能关闭视觉规则，必须执行第 6 节的渲染复核。

## 5. Stateflow

Chart 内部修改使用 `model_edit` 的 Stateflow scope：

1. `model_read` 获取 Chart 和 `sf_X` scope。
2. 使用无端口 transition 操作编辑状态、转移、参数和标签。
3. 不使用 Simulink `Position` 表示 Chart 内部几何。
4. 运行 `export_stateflow_geometry.m`，再运行 `stateflow_lint.py`。

Stateflow lint 退出码含义：

- `0`：自动覆盖项合规。
- `1`：`NON_COMPLIANT`。
- `2`：`INVALID` 或 `INCOMPLETE`。
- `3`：只剩已登记 `MANUAL` 项，仍需逐图或人工复核。

项目偏离只从 [../assets/project-deviations.json](../assets/project-deviations.json) 读取。`MANUAL` 不是自动通过状态，结论必须明确保留对应检查结果。

API 可读取项必须由导出器证明。文字包围盒、隐藏路由等不可可靠读取项必须保留为 `UNVERIFIABLE` 或 `MANUAL`，并补视觉证据。

## 6. 视觉复核

视觉规则包括标签重叠、块可辨识性、名称位置和参数显示。执行 Agent 必须在初版布局后主动查看一次渲染图，在交付前再查看所有修复后的当前图。只查看几何 JSON、lint 退出码或自动布局响应不算视觉复核。

从模型所在目录运行，或先把模型目录加入 MATLAB 路径：

```matlab
files = render_check('Model', 'renders');
```

脚本输出根层、每个 SubSystem 和 Chart 的 PNG。执行 Agent 必须逐张检查：

- 块名、信号名、端口标签和参数是否遮挡、裁切或越界；
- 线条是否交叉、重叠、穿块或产生无必要的折弯；
- 块图标和端口是否可辨识；
- 信号流、并行关系和反馈走廊是否清楚；
- Stateflow 状态框、转移和标签是否符合规则。

对线密集区域应同时查看完整 scope 图和必要的局部放大图；缩略图看不清交叉不等于没有交叉。发现问题时先通过 SATK 修复，再重新导出、lint 和渲染。任何图面修改后都不得继续引用旧 PNG。

连续 3 轮没有实质改善时停止改动，报告阻塞原因和未关闭项，不得把未改善结果写成通过。

如果执行环境无法读取 PNG，必须把渲染职责和文件路径交给能读图的责任人，并将相关结论保持 `UNVERIFIABLE`；不得假装已经看过。

MATLAB 无法生成可读 Chart 图时，可用：

```text
python scripts/render_chart.py chart_geometry.json -o chart.render.png
```

该图由导出几何重绘，适合检查状态/转移/标签关系，但不等同于 Stateflow 编辑器最终渲染。

## 7. 失败处理

| 失败 | 处理 |
| --- | --- |
| SATK 不可用 | 停止结构修改；不得改用 MATLAB 脚本建模型 |
| `model_edit` partial | 仅修失败 scope，再执行 `model_read` + `model_check` |
| plan 端口不匹配 | 回计划阶段修正；不得猜端口 |
| 几何或 schema 失败 | fail-closed，修导出器/输入后重跑 |
| `EditorPathXStyle` 读取失败或值无法识别 | 相关交叉保持未验证，提交渲染图复核 |
| 渲染失败 | 修复渲染或转交责任人；相关视觉规则不得通过 |
| Model Advisor/Model Check 未运行 | 相关规则保持 `UNVERIFIABLE` |
| 修复循环无进展 | 停止并报告，不带着已知缺陷交付 |

## 8. 交付

模型修改完成后至少提供：

- 模型路径、修改的 scope 和主要块/连接变化；
- `model_read` / `model_check` 结果；
- 每个 scope 的几何 JSON 与 `layout_lint` 退出码；
- 新增 Goto/From 的裁决证据文件（`maab.goto_justification/v1`）与预算使用情况；获准残留豁免的 scope 列出残留线对；
- Stateflow 几何/lint（如有）；
- 每个 scope 的最终 PNG 路径和逐图发现；
- 未关闭项、工具限制和未覆盖范围。

只有最终 PNG 已实际检查、每个 scope 的 lint 无未处理违规，且 `appearance_quality=PASS` 时，才可写“外观布局符合目标建模规范 v5 相关要求”。已有模型还须证明 baseline 有效且无退化。不得写成“完全符合目标建模规范 v5”，也不得用截图代替编译、仿真或功能验证；反过来，与外观无关的功能诊断也不得被扩大为阻断外观结论的理由。
