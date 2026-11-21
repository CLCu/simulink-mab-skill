# SATK 外观布局建模与验证工作流

本文件是本次模型修改、几何检查和视觉复核的唯一执行契约。目标是让模型的外观、布局、连线和标签可读且符合目标建模规范（v5）相关要求，不是执行第 3/4 章全量规则审查。

## 1. 职责与顺序

| 工作 | 唯一责任方 |
| --- | --- |
| 库/块策略门槛 | `building-simulink-models` |
| 建块、连线、参数和层级 | `model_read` / `model_edit` |
| 移动、局部布局、完整布局和精确坐标 | `arranging-simulink-layouts` / `model_edit` |
| 坐标预规划 | `layout_plan.py` |
| Simulink 几何验证 | `export_geometry.m` + `layout_lint.py` |
| Stateflow 几何验证 | `export_stateflow_geometry.m` + `stateflow_lint.py` |
| 编辑器图面复核 | `render_check.m` |

```text
spec.json → plan JSON → model_edit → 布局 → model_check
→ Simulink 单层几何导出/lint → Stateflow 导出/lint → 最终 PNG 渲染与逐图复核
→ 外观布局结论
```

最终渲染必须发生在所有结构和 Stateflow lint 修复之后；否则 Chart 或图面证据可能已过期。禁止维护替代 SATK 的 MATLAB 建模型脚本。本闭环不判定功能正确性、数据语义或完整目标规范合规。

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
- 精确位置通过 `model_edit.configure` 设置。
- 布局后运行 `model_check`，只以悬空端口、缺少目标、结构无法更新等会影响图面判定的错误作为本轮阻断项；其他诊断记录为未覆盖范围。

最终版面以实际模型为准，不以 plan 或自动布局响应中的建议坐标为准。

## 4. Simulink 几何检查

`export_geometry.m` 每次只导出一个 scope 的直接子块与线，使用 scope-local 坐标：

```text
export_geometry('Model/Subsystem', 'Subsystem_geometry.json')
```

JSON 必须包含标准、MATLAB 版本、scope、块 Position/类型/朝向/名称位置/阴影、原始端口连接、线点集、源/目标块与端口、反馈标记、line-crossing 设置状态、覆盖与忽略项。缺字段或 scope 混合时不得推断通过。

```text
python scripts/layout_lint.py <scope_geometry.json>
```

- `0`：本次覆盖项全部合规。
- `1`：存在 `VIOLATION`。
- `2`：schema 无效或仍有 `UNVERIFIABLE`。
- 自动化不得把 `2` 当作通过。

R2025b 的 line crossing style 是 Simulink 编辑器全局偏好，不是模型参数。导出器通过 `get_param(0,'EditorPathXStyle')` 读取实际值：`hop` 对应 `Line Hop`，`grad_pin` 对应 `Tunnel`，`none` 对应 `None`。存在交叉时，只有实际值为 `hop` 才满足 `db_0032-a2`；`layout-profile.json` 的值不能代替该读取结果。最终 PNG 仍需确认交叉确实存在且显示清楚。

`layout_lint.py` 为每条导出信号线输出顶点数、方向变化次数（折弯数）和折线坐标长度。处理原则如下：

| 诊断 | 判定意义 | 处理 |
| --- | --- | --- |
| 交叉点 | 报告交叉的两条线及交叉坐标；共享端点不冒充交叉 | 先移动输入/输出块、块顺序或重走正交线；仍有交叉时按 [layout-simulink.md](layout-simulink.md) 的项目策略逐条评估 `Goto/From`；最后才用 `Line Hop` 兜底 |
| 共线重叠 | 不同信号线共享同一线段，直接违反 `db_0032-b` | 移动块或重走线路，必须分开；`Line hop` 不能修复重叠 |
| 折弯数 | 线段方向变化次数，忽略重复点和共线冗余顶点 | 不按固定数字自动判违规；检查绕行和冗余转折并重新布局。例：5 次折弯先定位其来源，简化到保持语义和端口关系所需的最少转折，再重新导出、lint 和渲染 |
| 折线长度 | 坐标单位下的路径总长，不是目标规范阈值 | 只用于前后对比和发现异常绕行；不能单独证明合规或违规 |

`Goto/From` 是交叉治理的项目路由策略，不是新增的 MAAB 规则。每次转换一条候选线后都要重新导出、lint 和渲染；只有交叉与整体可读性均有净改善时，才继续评估下一条。必须检查 `na_0011-a` 的 Local 可见性、`jc_0602-a` 的名称一致性、`na_0008-b` 的标签要求，并避免破坏 `jc_0171-a` 要求的 structural subsystem 直接连接。`Inport → Goto` 本身允许，不得自动判违规。

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

视觉规则包括标签重叠、块可辨识性、名称位置和参数显示。执行 Agent 必须在交付前主动查看渲染图。

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

发现问题时先通过 SATK 修复，再重新导出、lint 和渲染。连续 3 轮没有实质改善时停止改动，报告阻塞原因和未关闭项，不得把未改善结果写成通过。

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
- Stateflow 几何/lint（如有）；
- 每个 scope 的最终 PNG 路径和逐图发现；
- 未关闭项、工具限制和未覆盖范围。

只有最终 PNG 已实际检查且 lint 无未处理违规时，才可写“外观布局符合目标建模规范 v5 相关要求”。不得写成“完全符合目标建模规范 v5”，也不得用截图代替编译、仿真或功能验证；反过来，与外观无关的功能诊断也不得被扩大为阻断外观结论的理由。
