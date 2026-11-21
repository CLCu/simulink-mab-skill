# Stateflow 图面与可读性规则（目标建模规范 v5 第 4 章相关项）

基线：目标建模规范（v5）、NA-MAAB + JMAAB、MATLAB/Simulink/Stateflow R2025b。

本文件只覆盖 Chart 的状态、转移、标签、命名和几何可读性。Chart 编辑、导出、lint、视觉复核和失败处理统一见 [satk-workflow.md](satk-workflow.md)。本文件不是第 4 章全部 54 条规则的审查矩阵。

`db_0137`、`jc_0721`、`jc_0797` 等结构前提用于保证层级和转移关系可读、可判定；它们不用于证明 Stateflow 行为、时序或功能正确。

## 检查口径

- API 导出的实际对象、几何、标签和属性用于自动检查；当前 Chart 的渲染 PNG 加逐图观察记录用于关闭视觉项。
- 每个结论保留相关规则 ID、子项、适用 profile、Chart scope 和对象；不需要建立全量规则矩阵。
- API 不可读取的视觉项必须保持 `UNVERIFIABLE` 或按登记流程人工检查；profile 值、字符数公式和默认行为都不能替代实际 Chart 证据。
- 项目偏离只读取 [../assets/project-deviations.json](../assets/project-deviations.json)。若某子项登记为 `MANUAL`，执行对应人工检查并记录结果。

## db_0129 — Stateflow transition appearance

NA-MAAB 与 JMAAB 都覆盖 a～e：

- a：转移线不交叉。
- b：转移线不互相重叠。
- c：转移线不穿过状态。
- d：一般转移线水平或垂直；flow chart 可使用斜线。
- e：不得使用仅有一条入转移和一条出转移、可由直线替代的冗余 junction。

**d 的人工项** 当前项目偏离资产登记了 `db_0129-d`；原因、人工检查步骤、关闭条件和 owner 只以该资产为准，不在本文复制。`stateflow_lint.py` 必须从资产读取该项并报告 `MANUAL`。`a`、`b`、`c`、`e` 仍为自动判定项。

校验使用 `SourceEndpoint + MidPoint + DestinationEndpoint` 的导出几何。导出器只提供这些 API 字段时，无法表示的曲线或隐藏路由必须 `UNVERIFIABLE`，不能声称已检查全部连线。

## jc_0531 — Default transition

NA-MAAB 与 JMAAB 都覆盖 a～g：

- a：Chart 为 OR 时默认转移接在 Chart 顶部；OR 状态为容器时接在父状态内、直接子元素上方。
- b：Parallel (AND) 层级不得连接默认转移。
- c：同一层级最多一条默认转移。
- d：默认转移直接、纵向连接到目标状态或 junction 的上部。
- e：默认转移目标位于同层左上区域。
- f：默认转移不得越过父状态边界。
- g：模型参数 `SFNoUnconditionalDefaultTransitionDiag` 对应的 `No unconditional default transitions` 须为 `Error`。

## db_0137 — States in state machines

Chart 或 grouped state 的分解方式为 OR (Exclusive) 时，该层级至少有两个状态。检查层级所有者的直接状态数量；junction 不计入“两个状态”。只有单一状态的容器应合并或重新设计。

R2025b 对普通原子状态也返回 `EXCLUSIVE_OR`，因此 lint 只把 Chart 或 `is_grouped=true` 的状态当作该规则所称的层级所有者；原子状态是否应改为容器属于结构设计判断，不是用“零个子状态”自动判违规。

## jc_0721 — Usage of parallel states

Parallel 状态的子状态不得再次设为 Parallel。嵌套并发需要改变层次或使用扁平并发设计；不能仅靠移动几何解决。

## jc_0797 — Unconnected transitions / states / junctions

原文只要求：

- a：Chart 不得有未连接转移。
- b：不得有缺少转移来源的 OR 状态，或缺少来源的 connective junction。

不得把规则错误改写成“每个状态都必须有出转移”。终止状态的合法性由功能语义和本条原文共同判断；lint 只检查转移是否有可连接目标，以及 OR 状态/junction 是否有入转移。

## jc_0760 — Starting point of internal transition

内部转移（源和目标为同一状态）的起点须在状态左边缘。`stateflow_lint.py` 比较实际 `SourceEndpoint` 与状态 `Position` 的左边；缺少任一几何时返回 `UNVERIFIABLE`。

## jc_0736 — Uniform indentations in Stateflow blocks

该规则只有 JMAAB a～c：

- a：状态动作类型行首不得有空格；可执行语句行首恰有一个单字节空格。
- b：转移条件 `[`、条件动作 `{`、转移动作 `/` 之前不得有空格。
- c：转移动作的 `/` 之后至少有一个单字节空格。

正确模板示例：

```text
A
en:
 x = 1;
```

```text
[x]/ y = 1;
```

注意：`/` 前不留空格，`/` 后至少一个空格；TAB 不算“半角空格”。注释、字符串和 `[]`/`{}` 内部的除法不等同于转移动作分隔符。

## jc_0501 — Line breaks in state labels

动作语句不得和动作类型写在同一行。以下表达式是违规：

```text
en: x = 1;
du: count = count + 1;
```

正确形式是动作类型单独一行，语句在下一行。

## jc_0731 — State name format

状态名后面的首行不得包含 `/`。`A\nen:\n x = 1;` 通过；`A/en:` 或把状态名和动作类型放在同一行不通过。只有状态名且没有动作的原子状态不做不必要的“强制换行”推断。

## jc_0739 — Describing text inside states

状态内文字不得越出状态边界。R2025b 的对象 API 不提供可靠的渲染文字包围盒，因此不得把字符数经验公式冒充目标规范阈值。linter 返回 `UNVERIFIABLE`，必须由当前 Chart 的 E2 逐图证据关闭。

## jc_0770 — Position of transition label

该规则只有 JMAAB a1/a2：

- a1：标签位于转移线起点。
- a2：标签位于转移线中部附近。

同一 Chart 必须在 a1 或 a2 中择一并保持一致。lint 使用 `LabelPosition` 与起终点/中点距离做证据；几何缺失或无法区分时保持 `UNVERIFIABLE`。

## jc_0730 — Unique state name

同一 Stateflow block 内状态名须唯一。lint 对导出 Chart 的状态名查重；linked atomic subchart 的可独立范围按 v5 原文处理。

## jc_0732 — Distinction between state, data and event names

同一 Chart 内状态名、数据名和事件名不得互相混淆。导出器读取 Stateflow.Data 与 Stateflow.Event 的 `Name` 后做跨命名空间检查。

## R2025b API 限制与证据

- 可读取：状态/转移/junction 几何、Parent/Subviewer、分解方式、标签字符串、来源/目标、执行顺序、MidPoint、LabelPosition 和上述模型诊断参数。
- 不可靠读取：渲染文字包围盒、隐藏路由的完整折线、某些显示层属性。
- API 读取成功不等于规则一定通过；规则语义、例外和人工图面仍需检查。
- API 读取失败时必须写 `UNVERIFIABLE`，不能自动降级为 profile 推测值。

## 范围边界

`stateflow_lint.py` 只覆盖与 Chart 图面和可读性有关的确定性检查。动作语义、事件广播、类型转换、除法、时序和功能正确性不在本 Skill 的完成判定内。
