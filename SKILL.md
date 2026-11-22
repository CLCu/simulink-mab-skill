---
name: mab-modeling-guidelines
description: 在 MATLAB R2025b 中搭建、修改或新建 Simulink/Stateflow 模型时，把图面布局做干净：零交叉、零共线重叠、零穿块、零斜线的外观度量 + 渲染 PNG 逐张目视复核的闭环。适用于用户要求“布局规范”“外观好看”“看起来符合建模规范”或提出“搭建模型/搭建Simulink模型”的建模任务；不做规则合规审计、功能验证或已有模型的独立复查。
metadata:
  author: luchao
  date: "2026-11-22"
  version: "2.0.0"
---

# Simulink / Stateflow 外观布局

## 触发与边界

- 搭建、修改、新建 Simulink/Stateflow 模型，或用户要求图面好看/布局规范时触发。
- 仅要求复查已有模型而不修改时，不进入执行主链。
- 交付目标是**好看的图**：连线清楚、无交叉/重叠/穿块/斜线、标签与块可辨识。
- 本 Skill 不证明任何建模规范合规，不判定功能/数据/代码生成正确性。完成时只描述外观结果，不写“符合 XX 规范”。

## 工作路径

| 步骤 | 工具 | 要点 |
| --- | --- | --- |
| 1 规格与预规划 | `scripts/layout_plan.py` | spec.json → plan JSON（只输出数据，不建模型） |
| 2 建结构 | SATK `building-simulink-models` + `model_edit` | 先过库/块策略门槛；`ref`/`#ref` 仅同调用内有效 |
| 3 布局 | SATK `arranging-simulink-layouts` + `model_edit` | 新建可 full；已有模型默认增量，整图重排须用户同意 |
| 4 度量 | `export_all_geometry.m` + `layout_metrics.py --manifest` | 已有模型修改前先导出 baseline manifest |
| 5 目视 | `render_check.m` → 逐张看 PNG | 初版布局后看一次；每次修复后重渲染再看 |
| 6 修复循环 | `repair_suggest.py` 生成 ops → SATK 应用一条 → 重导出+度量裁判；辅以 [layout-craft.md](references/layout-craft.md) | 每轮只改一组；连续 3 轮无净改善即停止并报告 |
| 7 Stateflow（如有） | `export_stateflow_geometry.m` + `chart_metrics.py`（仅参考）+ Chart PNG | Chart 内部用 `model_edit` 的 Stateflow scope 编辑 |
| 8 交付 | 最终全模型度量 + 最终 PNG 逐张复核 | 见完成标准 |

## 不可违反的约束

- 建模型/改结构/移动块只走 SATK `model_edit` 与 `arranging-simulink-layouts`；不得用 `evaluate_matlab_code`、生成脚本 `add_block/add_line` 或 `set_param Position` 绕过。
- `layout_plan.py` 只输出 JSON plan；最终版面以实际模型重新导出的度量为准，不以 plan 坐标为准。
- 一个物理输出端口供多个消费者时共享同一端点，不得造 `S/2`、`S/3` 伪端口。
- Goto/From 是几何手段穷尽后的受限最后手段：每 scope 预算按功能块数 ≤20→1 对、≤60→2 对、>60→3 对（硬上限 3）；`TagVisibility=local`、tag 用信号名、Goto 紧贴源、From 紧贴消费者、每 tag From ≤2；禁止 Inport 直连 Goto、From→Goto 链、未配对 Goto/From。不得用其隐藏扇出或大面积刷零交叉。
- `repair_suggest.py` 的结构级建议（`restructure_branch_tree`、`goto_from_conversion`，带 `requires_consent:true`）必须先取得用户明确同意再经 SATK 应用；坐标/端口级建议（phase 1）可直接应用但仍每轮一条+度量裁判。
- 已有模型：第一次布局修改前导出全层级 baseline；修改后四计数与 Goto 对数相对 baseline 不得增加。
- 度量未运行、导出失败或 schema 无效（退出码 2）时不得写成通过；修导出器/输入后重跑。
- 执行环境读不了 PNG 时，把渲染与目视职责转交能读图的责任人，相关结论保持未关闭；不得假装看过。

## 完成标准

同时满足才可交付“外观布局干净”：

1. 全模型 `layout_metrics.py --manifest` 退出码 0；或四计数中仅 `crossing_events` ≤2 且涉及 ≤2 条线、其余为零、Goto 与 baseline 无问题，且该残留已在交付报告书面列出线对与实际 editor crossing style（`residual.eligible=true` 时允许）。
2. 每个 scope（含 Chart）的最终 PNG 已由执行 Agent 逐张实际检查：无明显交叉/重叠/穿块/裁切、标签不遮挡、块与端口可辨识、信号流与反馈走廊清楚。度量通过不能替代目视。
3. 遗留项、工具限制与未覆盖范围（功能/语义/合规）已报告。

否则写“外观部分完成/存在未关闭项”，列出具体 scope、线对与坐标。不得用编译、仿真或测试代替外观判断。

## 交付清单

模型路径与修改 scope；`model_check` 结果；全模型度量 JSON 与退出码（含 baseline 对比）；Goto/From 使用与预算；每个 scope 最终 PNG 路径与逐张发现；书面残留（如有）；未覆盖范围。

参数默认值见 [assets/layout-profile.json](assets/layout-profile.json)（项目可调手艺数值，非规范强制值）；布局手艺与修复 cookbook 见 [references/layout-craft.md](references/layout-craft.md)。
