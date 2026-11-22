---
name: mab-modeling-guidelines
description: 在 MATLAB R2025b 中搭建、修改或新建 Simulink/Stateflow 模型，按照目标建模规范（v5）第 3/4 章的相关要求优化图面，并执行零交叉、零重叠、零穿块、零斜线的项目外观质量门禁。适用于用户要求模型“布局规范”、“外观好看”、“看起来符合目标建模规范”或“MAB建模规范”的建模任务；当用户提出“搭建模型”或“搭建Simulink模型”时也应触发；不用于全量规则合规审查、功能正确性验证或对已有模型做独立复查。
metadata:
  author: luchao
  date: "2026-11-21"
  version: "1.4.0"
---

# Simulink / Stateflow 外观布局（目标建模规范 v5）

## 触发条件

- 用户要求搭建、修改或新建 Simulink/Stateflow 模型时触发。
- 用户明确提出“搭建模型”或“搭建Simulink模型”时触发。
- 用户要求模型“布局规范”、“MAB建模规范”或图面外观与可读性符合目标建模规范时触发。
- 仅要求复查已有模型、不要求修改或调整布局时，不进入本 Skill 的执行主链。

## 目标与边界

- 本 Skill 的核心交付是整洁、可读、连线清楚并符合目标建模规范外观/布局相关规则的实际模型。
- 项目外观门禁比“规范允许 Line Hop”更严格：新建或修改后的 scope 必须满足零交叉、零共线重叠、零穿块、零斜线；不得用“不可避免”作为未经验证的例外。
- 标准：目标建模规范（v5）第 3 章 Simulink、第 4 章 Stateflow 中与图面、布局、连线、标签和可读性相关的条目。
- NA-MAAB 与 JMAAB 有差异时，按当前模型对象采用对应要求；不维护 121 条规则的全量判定矩阵。
- 纳入规则的条件：规则直接影响图面/可读性，或违反后会使图面关系无法可靠判定。纯数据语义、时序、代码生成和功能诊断只用于说明限制，不作为外观合规证据。
- 环境：MATLAB/Simulink/Stateflow R2025b。
- 修改模型：SATK `building-simulink-models`、`arranging-simulink-layouts` 和 `model_edit`。
- 来源与哈希：[assets/source-manifest.json](assets/source-manifest.json)；术语有歧义时读 [references/glossary.md](references/glossary.md)。
- 项目参数：[assets/layout-profile.json](assets/layout-profile.json)。
- 项目偏离：[assets/project-deviations.json](assets/project-deviations.json)。

本 Skill 不证明模型满足全部目标规范语义、数据、配置、代码生成或功能要求，也不提供已有模型的独立复查入口。完成时只能表述为“外观布局符合目标建模规范 v5 相关要求”，不能写成“完全符合目标建模规范 v5”。

## 工作路径

| 任务 | 必须读取 | 执行重点 |
| --- | --- | --- |
| 搭建、修改或调整模型布局 | [satk-workflow.md](references/satk-workflow.md)、[layout-simulink.md](references/layout-simulink.md) | 规格与 plan → SATK 建结构 → 布局 → 全层级 manifest 几何门禁与 PNG 检查 → 按热点迭代修复 → 最终全层级复核 |
| 涉及 Stateflow Chart | 再读 [layout-stateflow.md](references/layout-stateflow.md) | Chart 内部用 Stateflow scope 编辑，导出、lint 并检查最终 PNG |

若请求仅要求复查已有模型，应停止并说明本 Skill 不覆盖该任务。已有模型只可在用户明确要求修改或调整布局时进入主链。

## 不可违反的约束

- `layout_plan.py` 只输出 JSON；不得生成或执行 `_build.m`、`add_block`、`add_line` 或 `set_param Position` 脚本。
- 不得用 `evaluate_matlab_code` 绕过 `model_edit` 创建或修改模型结构，不得手工拼接块路径，不得用 `set_param` 移动块。
- `model_edit` 的 `ref`/`#ref` 只在同一次调用内有效；跨调用使用返回的 `blk_X`，连接使用 `blk_X.yN -> blk_Y.uN`。
- 一个逻辑输出端口连接多个消费者时共享同一个物理输出端点，不得生成 `S/2`、`S/3` 等伪端口。
- `Goto/From` 只是几何手段穷尽后的受限最后手段：每 scope 预算为功能块 ≤20→1 对、≤60→2 对、>60→3 对（硬上限 3 对）；每个新增 tag 必须绑定 `maab.goto_justification/v1` 交叉裁决证据（reason + eliminated_crossings）；`TagVisibility=local`、tag 用信号名、Goto 紧贴源块、From 紧贴消费者块、每 tag 的 From ≤2；禁止 Inport 直连 Goto、From→Goto 链式连接和未配对 Goto/From。禁止大面积使用 Goto/From 或用其隐藏扇出。
- 大面积 `Line Hop` 禁止。仅当残留交叉 ≤2 处且涉及 ≤2 条线、实际 crossing style 为 hop、Goto 预算已耗尽且有书面裁决时，才可条件放行并逐张 PNG 复核；预算内仍无法完成布局时，停止并报告具体交叉线对、受约束端口和需要调整的功能分区。
- 已有模型默认使用增量布局；整图重排会移动所有块，必须先取得用户同意。
- 已有模型开始修改前，先用 `export_all_geometry.m` 导出全层级 baseline manifest；修改后的全模型 lint 必须使用该 baseline manifest 比较退化。
- 最终 Simulink 几何结论以全模型 `layout_lint.py --manifest` 的汇总结果和各 scope lint 报告为准；单个 scope 通过不能证明其他层级通过。
- Stateflow 状态、转移、junction 和标签的修改使用 `model_edit` 的 Stateflow scope，不用 Simulink `Position` 表示 Chart 内部几何。
- 新建或修改后的 scope 必须通过 `layout-profile.json` 中的 `appearance_quality`；`Line Hop` 本身不能关闭项目外观门禁，仅当极小残留豁免的全部条件满足并获准时例外。
- 自动检查未运行、schema 无效、scope 坐标混合或 API 值不可读取时不得写成通过；`VIOLATION`、`UNVERIFIABLE`、`appearance_quality=FAIL/INVALID` 和未关闭的 `MANUAL` 都必须处理或明确报告。

## 执行合同

建模、修改、几何检查、Stateflow 检查、最终渲染和失败处理只有一个权威：[satk-workflow.md](references/satk-workflow.md)。外观规则细节分别见 [layout-simulink.md](references/layout-simulink.md) 和 [layout-stateflow.md](references/layout-stateflow.md)。

## 完成标准

只有同时满足以下条件，才可写“外观布局符合目标建模规范 v5 相关要求”：

1. `model_check` 已执行，且不存在悬空端口、缺少目标、模型结构无法更新等会阻断图面判定的错误；与外观无关的类型、参数或功能诊断不阻断外观结论，但必须列为未覆盖范围。
2. 全模型 manifest lint 已完成，每个 Simulink scope 均无 `VIOLATION`、无阻断性 `UNVERIFIABLE`，且全局及各 scope 的 `appearance_quality=PASS`；全模型汇总包含所有层级的总线长、总折点和零交叉。Goto/From 对数在各 scope 预算内，每个新增 tag（含已有模型相对 baseline manifest 的新增 tag）都有裁决证据；获准残留豁免的 scope 必须在交付报告列出残留线对。`MANUAL` 项由第 4 条最终 PNG 复核关闭。
3. Stateflow lint 无 `VIOLATION`；人工项已完成，`UNVERIFIABLE` 已关闭或明确列为遗留项。
4. 初次布局后和所有修复完成后都生成当前 scope PNG；最终 PNG 由执行 Agent 逐张实际检查，且不存在明显交叉、重叠、穿块、裁切、错误朝向或冗余折弯。几何门禁通过不能替代该检查。
5. 遗留项、外观质量未关闭项、工具限制和未覆盖范围已报告，不据此宣称完整目标规范合规。

否则写“外观布局部分完成”或“存在未关闭项”，列出具体 scope、交叉线对和坐标。不得把 `db_0032-a2=COMPLIANT` 或全局 `Line Hop` 写成“外观质量通过”。不得用功能编译、仿真或测试代替外观判断，它们也不属于本 Skill 的完成条件。
