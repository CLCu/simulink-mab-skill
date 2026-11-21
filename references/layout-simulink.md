# Simulink 外观与布局规则（目标建模规范 v5 第 3 章相关项）

基线：目标建模规范（v5）、NA-MAAB + JMAAB、MATLAB R2025b。

本文件只覆盖与模型外观、布局、连线、标签、层级可读性直接相关的规则。执行顺序见 [satk-workflow.md](satk-workflow.md)。这里不是第 3 章全量规则清单，结论不得扩展为完整配置、数据语义或功能合规。

`db_0143`、`db_0144`、`jc_0171`、`jc_0653` 等结构前提用于解释合法的层级和块关系；相关判断服务于图面可读性，不单独证明功能或语义正确。

## 检查口径

- 几何 JSON、实际属性值和已执行结构检查只能证明导出时实际读取到的对象和值。
- `render_check.m` 生成的当前 scope PNG 加逐图观察记录是视觉结论的主要依据；`layout_lint.py` 对 `db_0097` 的字号估算不是最终通过证据。
- `layout-profile.json` 只提供项目决定值，不证明环境已采用。R2025b 用 `get_param(0,'EditorPathXStyle')` 读取全局编辑器偏好；只有读取成功且值为 `hop` 才表示 `Line Hop`。读取失败或值无法识别时，相关交叉保持 `UNVERIFIABLE`。
- 同一逻辑输出端点的多个消费者共享物理源端口；这是 `db_0032` 分支证据的一部分，不得生成 `S/1`、`S/2` 之类伪端口。
- `layout_lint.py` 从每条线的 `Points` 计算方向变化次数和折线坐标长度。折弯数是确定性诊断量；“无必要”仍需结合信号语义和最终图面判断。目标规范没有线长数值上限，线长不能单独作为通过或违规依据。

## na_0004 — Simulink model appearance settings

**适用** NA-MAAB: 无；JMAAB: a。

模型外观设置须符合项目设置。外观是项目参数，不是目标规范固定模板。

**动作** 从 `layout-profile.json` 读取 `appearance`、网格和显示选项；先确认 profile 是实际项目配置。未提供 profile 时使用明确标注的暂定值，结论中写“按项目暂定参数”，不能写目标规范强制符合。

**验证** 对比模型实际显示设置、profile 和报告记录。

## db_0043 — Model font and font size

**适用** NA-MAAB: a,b,c,d；JMAAB: a,b,c,d。

- a：块名、信号名的字体和字体样式符合项目设置。
- b：块名、信号名的字号符合项目设置。
- c：状态/框名称、转移标签和注释的字体样式符合项目设置。
- d：状态/框名称、转移标签和注释的字号符合项目设置。

**动作** 字体与字号从项目 profile 读取。不得把 Arial 10 写成目标规范强制值。

**验证** 查询模型默认/实际字体属性，抽查块名、信号名、状态和转移标签；无法读取的显示项转人工。

## jm_0002 — Block resizing

**适用** NA-MAAB: a；JMAAB: a。

块尺寸须使图标可见、可辨识。

**动作** 保持图标、端口和文字可识别，避免过度压缩。

**验证** 采用当前 scope 的 E2 图面证据。项目可定义建议尺寸，但该数值不是 `jm_0002` 原文，不能据此自动生成违规。

## db_0142 — Position of block names

**适用** NA-MAAB: a；JMAAB: a。

块名须位于块下方。

**动作** 检查实际 `NamePlacement`。Simulink 常用值为 `normal`/`alternate`；不要依赖自行猜测的别名。

**验证** 综合实际 `NamePlacement`（E1）和当前 scope PNG（E2）确认。

## db_0140 — Display of block parameters

**适用** NA-MAAB: 无；JMAAB: a。

块 annotation 须显示项目定义的块参数。

**动作** 参数显示集合来自项目设置。未给出项目参数时不得自行决定显示全部参数。

**验证** 对比批准 profile、实际 `AttributesFormatString`（E1）和截图（E2）。

## jc_0604 — Using Block Shadow

**适用** NA-MAAB: a；JMAAB: a。

不得启用块阴影。

**动作** 复制模型后重新检查阴影。使用 R2025b 实际支持的 property；查询失败必须 `UNVERIFIABLE`，不能默认 `false`。

**验证** 检查模型中块的实际阴影属性。

## db_0081 — Unconnected signals / blocks

**适用** NA-MAAB: a,b；JMAAB: a,b。

- a：不得存在未连接的信号线。
- b：不得存在未连接的子系统或基本块。

**动作** 悬空端口必须连接，或按模型语义使用 Terminator/Ground 明确终止。外部 Inport/Outport 是否允许未连接，应按具体上下文和 v5 原文判断，不得一律豁免。

**验证** 结合 `model_check`、PortConnectivity 和线的端点。端口类型无法解释时 fail-closed。

## db_0032 — Signal line connections

**适用** NA-MAAB: a1,a2,b,c,e；JMAAB: a1,a2,b,c,d,e。

- a1：水平与垂直信号线不得交叉。
- a2：确实必须交叉时，Simulink 编辑器偏好须为 `Line hop`。
- b：信号线不得与其他信号线重叠。
- c：信号线不得穿过块。
- d：单个分支点不得分出超过两条支线（JMAAB）。
- e：信号线应按布局需要水平或垂直拉伸。

**动作** 采用正交走线、分层左→右、分支树、Goto/From 或明确子系统接口。Mux 只组合不同信号，不能把同一标量复制到多个目标。

**验证** 由单层几何检查 a1、b、c、d、e。a2 从 R2025b 根对象读取 `EditorPathXStyle`：`hop` 为 `Line Hop`，`grad_pin` 为 `Tunnel`，`none` 为 `None`；读取失败或值无法识别时保持 `UNVERIFIABLE`。

### 交叉路由策略（项目策略，不属于 MAAB v5 独立规则）

本策略服务于 `db_0032-a1/a2`，不新增规则 ID，也不把 `Goto/From` 变成所有交叉问题的强制替代方案。

1. 先调整 Inport/Outport 的纵向位置、块顺序和分支树，或重新正交走线。`db_0042-a/b` 允许移动输入/输出块以避免交叉。
2. 交叉仍存在时，可按参与交叉数、折线长度和折弯数排序，逐条评估将候选线改为 `Goto/From`。不要固定为“最多改两条”；每次只改一条并重新导出、lint 和检查 PNG。
3. 只有交叉减少且整体可读性有净收益时才转换下一条。若 `Goto/From` 增加追踪困难、标签复杂度或没有净收益，应停止该策略。
4. 无法消除的剩余交叉才使用全局 `Line Hop`，并按 a2 复核实际设置和最终图面。

转换为 `Goto/From` 时必须保持原信号拓扑和消费者集合，并满足相关规则：

- Goto 的 tag visibility 须为 `Local`（`na_0011-a`），对应 From 与 Goto 位于同一层级。
- Goto tag、From tag、信号名及相关端口/元素名按 `jc_0602-a` 保持一致；连接到 Goto 的线按 `na_0008-b` 显示必要标签。
- 不得把两个 structural subsystem 之间唯一要求的直接信号连接替换成 `Goto/From`，否则可能与 `jc_0171-a` 冲突。
- 不得改变信号语义、执行依赖或分叉关系；转换后必须重新运行几何检查和最终渲染。

MAAB v5 允许 `Inport → Goto` 直接连接，不得把这种连接本身判为违规。若项目另有禁止要求，应作为项目自定义约束明确登记，不能归因于 MAAB v5。

## db_0141 — Signal flow in Simulink models

**适用** NA-MAAB: 无；JMAAB: a,b,c。

- a：信号从左向右流动；反馈环可从右向左。
- b：并行块或子系统从上到下排列。
- c：信号线不得有不必要的多次折弯。

**动作** 主数据流分层左→右，并行项纵向排列；反馈使用单独走廊。反馈识别必须有拓扑证据。

**验证** 反向线只有在可证明属于反馈环时才能使用例外；b 可通过行序和连线关系检查，c 需结合折弯数和图形确认。

折点数为 5 只表示该线发生了 5 次方向变化，不等于规范给出“不得超过 5”的阈值。处理时先寻找可消除的绕行、重复转折和不合理走廊；在不破坏反馈路径、分支树、端口关系和可读间距的前提下，将线路简化为实际所需的最少转折。若 5 次转折均由模型结构或必须保留的反馈走廊造成，应保留并记录视觉证据，不能仅按数量自动判违规。

线长是各段折线长度之和，单位与几何 JSON 的坐标单位一致。它可用于比较布局修改前后的绕行变化、定位异常拉线，但不对应目标规范中的数值门槛。不得以“线较长”直接生成 `VIOLATION`。

## jc_0110 — Direction of block

**适用** NA-MAAB: a；JMAAB: a。

块输出须朝右。反馈环内 Delay 的输出可以朝左。

**动作** 不通过旋转块凑线。反馈 Delay 例外必须有反馈环证据。

**验证** 检查实际 `Orientation` 和 `in_feedback`；缺少反馈信息时，Delay 例外保持 `UNVERIFIABLE`。

## jc_0171 — Connections between structural subsystems

**适用** NA-MAAB: 无；JMAAB: a,b。

- a：两个 structural subsystem 至少有一条信号线；双向关系时每个方向至少一条。Goto/From 建总线或接 Merge 有例外。
- b：子系统内部未使用的信号应作为外部输入关系处理，不得经其他子系统或基本块输出。

**动作** 先识别 structural subsystem，再检查接口方向。不能把 virtual subsystem、Chart 或 MATLAB Function 误当成同一类结构块。

**验证** 读取层级拓扑和端口用途；必要时人工确认功能归属。

## db_0143 — Usable block types in model hierarchy

**适用** NA-MAAB: a；JMAAB: a。

层级只能使用该层定义允许的块类型。

**动作** 在建模前声明层级角色：

- 数据流层只放允许的基本块。
- 非数据流层可包含 structural subsystem 及允许的跨层块。
- 根层不得使用 action port；v5 对 Enable 的版本限制按原文保留。

允许块清单以 v5 原文和项目层定义为准。

**验证** 读取每层块类型与层定义；无层定义时 `UNVERIFIABLE`。

## db_0144 — Use of subsystems

**适用** NA-MAAB: a,b；JMAAB: a,b。

- a：按算法功能、行为变体或时序划分块，不得仅为节省图面空间分组。
- b：无需考虑执行顺序和代码生成时使用 virtual subsystem。

**动作** 子系统边界对应功能边界。用于可读性的打包优先 virtual subsystem；atomic/conditional subsystem 只用于需要执行语义时。

**验证** 人工审查功能边界；报告说明每个子系统的作用。

## jc_0653 — Delay block layout in feedback loops

**适用** NA-MAAB: a；JMAAB: a。

跨子系统反馈环中的 Delay 须位于描述该反馈环的层级。

**动作** 先识别环和环所属层级，再放 Delay；不要放入更深的被调用子系统。

**验证** 依赖跨层环分析。未证明环所属层级时 `UNVERIFIABLE`。

## db_0146 — Block layout in conditional subsystems

**适用** NA-MAAB: a,b；JMAAB: a,b。

- a：条件输入块位于子系统顶部。
- b：For Each、For Iterator、While Iterator 的位置由项目布局规定。

**动作** 条件输入块先放顶部；迭代器位置从项目设置读取。

**验证** a 可通过同一 scope 几何检查；b 对照项目参数。

## db_0097 — Position of labels for signals and buses

**适用** NA-MAAB: a,b,c；JMAAB: a,b,c。

- a：信号/总线标签不得与其他标签、线或块重叠。
- b：标签位于信号线下方。
- c：标签位于连接起点。

**动作** 拉开空间，标签以信号源为定位基准；避免只靠移动线解决重叠。

**验证** linter 按项目字号估算标签 bbox，只能提示潜在重叠且可能漏报；a、b、c 均由当前 scope 的 E2 逐图证据关闭。

## na_0008 — Display of labels on signals

**适用** NA-MAAB: a,b；JMAAB: 不支持。

- a：指定来源块输出线显示标签，块图标已显示标签时有例外。
- b：连接到指定目标块的线显示标签，包括直接连线或经非变换基本块。

**动作** 按来源/目标类型清单检查。例外必须给出块图标或规范依据。

**验证** 读取线 Name 和块类型；无法判断“非变换”时必须人工确认。

## jc_0602 — Consistency in model element names

**适用** NA-MAAB: 无；JMAAB: a。

直接相连时，Inport/Outport、structural subsystem 端口标签、Goto/From tag 和信号名须一致。库链接子系统、可复用子系统和有统一前后缀的端口有例外。

**动作** 从连接两端读取实际名称和 tag，不要按块显示路径猜测。

**验证** 对相连端点对比字符串；例外需有结构证据。

## 范围边界

本文件仅用于改善和检查模型外观布局。配置参数、数据类型、运算语义、代码生成和功能正确性不在本 Skill 的完成判定内。
