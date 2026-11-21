# 术语表（目标建模规范 v5 第 6 章）

判定前先对齐定义。这些术语决定了规则的适用边界，例如 `structural subsystem` 与 `basic block` 的分界直接影响 db_0143、jc_0171 等第 3 章规则。

本文件来自所附建模规范 v5，不用于解释目标规范 v6 的新增或改写条目。

**Atomic Subsystem**

A subsystem block that executes the structural subsystem as a single unit. Conditional subsystems, Stateflow Chart, and MATLAB Function blocks are considered atomic subsystems.

**Basic Blocks**

Built-in blocks in the standard Simulink library. Blocks with undefined internal processing, such as subsystems, are not considered basic blocks

Basic blocks can include:

  - Inport
  - Outport
  - Ground
  - Terminator
  - Constant
  - Scope
  - Saturation
  - Unit Delay
  - Delay
  - Discrete-Time Integrator
  - Switch
  - Gain
  - Product
  - Relational Operator
  - Logical Operator

**Block**

All blocks (type=block), including:

  - Subsystems
  - Models
  - Charts (unless otherwise stated).

Standard Simulink library blocks are divided into two categories:

  - Basic blocks
  - Structural subsystems

### C

**Built-in MATLAB functions**

MATLAB functions and scripts.

**Combined State Action Type**

A combination of two or more of these basic state action types:

  - entry ( en ), during ( du )
  - during ( du ), exit ( ex )
  - entry ( en ), exit ( ex )
  - entry ( en ), during ( du ), exit ( ex )

**Conditional Input Block**

Includes Trigger, Enable, Function-Call Subsystem, Reset blocks.

**Conditional Subsystem**

A subsystem with conditional input ports.

**Delay Block**

Two meanings:

1 The previous value reference block that is placed in the loop route to specify the execution order in an algebraic loop (circular reference). Uses Unit Delay and Memory blocks.

(As of R2021b and later) The Delay block can also be used

2 A block that retains past values. Uses Unit Delay, Memory, Delay, and Tapped Delay blocks.

**Calculation Block**

Blocks whose block type is "sum" that carry out addition and subtraction operations. Includes Add, Subtract, Sum, Sum of Elements blocks.

**Flow Chart**

The part of a model that describes the action for the transition condition by using transition conditions and condition actions. The start point is the default transition line or internal transition line. The end point is the connective junction. Does not include states that are between the start and end points. Graphical functions and the inside of states can be modeled as flow charts.

**Machine Level**

The root subsystem of a Simulink model with Stateflow blocks.

**Multiplication and Division Block**

Blocks whose block type is "product" that carry out division and multiplication operations. Includes Product, Divide, and Product of Elements blocks.

**Parameters**

When modifications have not been made, this term refers to constants that are defined in the base workspace and/or model workspace.

**Port Label Name**

The input and output port labels of a structural subsystem.

The names of Inport and Outport blocks are placed in a subsystem by default. Names of Stateflow input and output data are displayed by default.

The display option can be changed when masking a subsystem.

**Reserved MATLAB words**

MATLAB keywords and built-in MATLAB functions.

**State**

An atomic subchart is considered a state.

**State Action Type**

Basic state action types and combined state action types.

**Stateflow Block**

Includes Chart, State Transition Table, and Truth Table blocks.

**Subsystem**

A subsystem that can be internally modeled by using Simulink.

Even when the block type is "subsystem", blocks that describe the inside (other than Simulink) of a model, such as Chart, MATLAB Function blocks, are not included. The Model block also is not included.
