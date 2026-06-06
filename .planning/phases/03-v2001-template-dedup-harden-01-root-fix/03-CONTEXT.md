# Phase 03: V2001 Template Dedup + HARDEN-01 Root Fix - Context

**Gathered:** 2026-06-06

## Decisions

### 1. Macro 策略 — 多 macro 文件，共享 + 专用

不使用单个巨型 macro。创建 `templates/_macros.sv.j2` 作为共享 macro 文件，包含三个通用 macro：

- **`port_type(verilog_mode)`** — 返回 `"reg"` / `"wire"`（V2001）或 `"logic"`（SV）。消除所有模板中 `{% if verilog_mode %}input clk{% else %}input logic clk{% endif %}` 模式。
- **`always_block_header(verilog_mode)`** — 返回 `"always @(posedge clk)"`（V2001）或 `"always_ff @(posedge clk)"`（SV）。消除 always 关键字重复。
- **`zero_literal(verilog_mode)`** — 返回 `"0"`（V2001）或 `"'0"`（SV）。消除零填充差异。

每个模板保持其自己独特的 always-block 过程体，但通过 `{% from '_macros.sv.j2' import port_type, always_block_header, zero_literal %}` 导入共享 macro 来消除 SV/V2001 分支。

**额外创建**: `templates/_attempt_fired_macro.sv.j2` — 专门处理 `attempt_fired_q` 的 HARDEN-01 修复。

**重构前**（`bool_expr.sv.j2` 中的典型模式）:
```jinja2
{% if verilog_mode %}
reg active_q, pass_q, fail_q, attempt_fired_q;
always @({{ clock_edge }} {{ clock_signal }})
    if (!rst_n || disable_i) begin
        ...
        attempt_fired_q <= 1'b0;
    end else begin
        ...
        attempt_fired_q <= attempt_fired_q | start;
    end
{% else %}
logic active_q, pass_q, fail_q, attempt_fired_q;
always_ff @({{ clock_edge }} {{ clock_signal }})
    if (!rst_n || disable_i) begin
        ...
        attempt_fired_q <= 1'b0;
    end else begin
        ...
        attempt_fired_q <= attempt_fired_q | start;
    end
{% endif %}
```

**重构后**:
```jinja2
{% from '_macros.sv.j2' import signal_type, always_block_header with context %}
{{ signal_type(verilog_mode) }} active_q, pass_q, fail_q;
{{ signal_type(verilog_mode) }} attempt_fired_q;

{{ always_block_header(verilog_mode, clock_edge, clock_signal) }}
    if (!rst_n || disable_i) begin
        active_q <= 1'b0;
        pass_q   <= 1'b0;
        fail_q   <= 1'b0;
    end else begin
        active_q <= start;
        pass_q   <= start &  bool_result;
        fail_q   <= start & ~bool_result;
    end

// HARDEN-01: attempt_fired_q is never cleared by disable_i
{% from '_attempt_fired_macro.sv.j2' import attempt_fired_logic with context %}
{{ attempt_fired_logic(verilog_mode, clock_edge, clock_signal) }}
```

### 2. 迁移顺序 — 分波渐进

分两波，按模板复杂度排序：

**Wave 1 — Plan 01: 创建 macro 文件 + 迁移简单模板**
- 创建 `templates/_macros.sv.j2` 和 `templates/_attempt_fired_macro.sv.j2`
- 迁移: `bool_expr.sv.j2`, `rose.sv.j2`, `fell.sv.j2`, `stable.sv.j2`, `past.sv.j2`
- 这些模板是单寄存器/移位寄存器，always-block 体简单，验证风险最低
- 通过: SV 字节一致（golden 对比）+ V2001 行为等价（golden parity）

**Wave 2 — Plan 02: 迁移复杂模板**
- 迁移: `concat_delay.sv.j2`, `overlap_bitvec.sv.j2`, `nonoverlap.sv.j2`, `rep_consecutive.sv.j2`, `disable_iff_top.sv.j2`, `seq_concat_top.sv.j2`
- 这些模板包含计数器、bit-vector 线程跟踪或 FSM 逻辑
- 通过: 全量 736 测试 + 65 仿真 oracle

### 3. HARDEN-01 修复详细设计

**问题**: 每个模板在 `if (!rst_n || disable_i)` 分支中将 `attempt_fired_q` 与 `active_q`/`pass_q`/`fail_q` 一起清零。

**修复基础**（适用于所有模板的 `_attempt_fired_macro.sv.j2`）:

```jinja2
{% macro attempt_fired_logic(verilog_mode, clock_edge, clock_signal) %}
{% from '_macros.sv.j2' import always_block_header with context %}
{{ always_block_header(verilog_mode, clock_edge, clock_signal) }}
    if (!rst_n) begin
        attempt_fired_q <= {{ zero_literal(verilog_mode) }};
    end else if (start) begin
        attempt_fired_q <= 1'b1;  // sticky — never cleared by disable_i
    end
{% endmacro %}
```

**关键点**:
- `attempt_fired_q` 在 `!rst_n` 时清零（复位），但 `disable_i` 时**不清零**
- 使用 `if (start)` 而不是 `attempt_fired_q | start` — 功能等价但更清晰的意图
- 分支内部仍然是 `<= 1'b1`（不是 `<= 1'b0`），确保粘滞行为
- 所有 11 个模板使用相同的 macro — HARDEN-01 修复在一次 macro 定义中完成

**对于 `disable_iff_top.sv.j2`（特殊情况）**:
- 此模板没有 always block — `attempt_fired` 从子 checker 直通
- 当前行为：子 checker 收到 `effective_disable = disable_i | cond_result` 作为其 `disable_i`，子 checker 在 disable 时将 `attempt_fired_q` 清零
- 修复后：子 checker 不再在 `disable_i` 时清零 `attempt_fired_q`，但可以在自己的复位逻辑中处理
- **不需要额外工作** — `disable_iff_top` 本身保持不变；修复由 macro 在所有子 checker 中生效

### 4. 验证策略 — 双轨同步

每个 wave 结束后必须通过两项门控：

| 门控 | 检查项 | 命令 |
|------|--------|------|
| SV 字节一致 | Golden 文件对比（所有已迁移的模板零差异） | `pytest tests/ -k "golden"` |
| V2001 行为等价 | Iverilog golden parity（SV 与 V2001 输出相同结果） | `pytest tests/ -m simulation --simulator=iverilog` |
| 全量回归 | 736 测试通过 | `pytest tests/ -v --timeout=120` |

**执行顺序**:
1. 迁移模板 → 运行 SV golden 对比 → 修复差异直到字节一致
2. 运行 V2001 golden parity → 修复行为差异
3. 运行全量回归 → 确认无回归
4. 提交

每波独立验证 — Wave 1 完成后才进入 Wave 2。

## Claude's Discretion

以下细节由 execute-phase 执行时自行决定：

- `_macros.sv.j2` 中 `signal_type` macro 的具体实现（是否需要单独的 `port_type` 变体处理 port 声明中的 `input`/`output` 前缀）
- 模板中 port 声明部分的重构粒度（是否也为 port 列表提取 macro）
- 每个模板的 body-only 重写顺序（在 wave 内部并行处理）
- `attempt_fired_q` 在 bit-vector 模板（`overlap_bitvec`/`nonoverlap`）中的 `ant_pass_w` 触发信号处理
- Golden 文件更新：`tests/golden/` 下的 `.sv` 文件是否需要重新生成（如果重构后的输出与原 golden 完全一致则不需要）

## Deferred Ideas

以下想法超出 Phase 3 范围：

- **模板继承（`{% extends %}`）**: 使用 Jinja2 模板继承创建基础 checker 骨架 → v2
- **端口声明统一化**: 为所有 11 个模板的标准端口（clk/rst_n/start/disable_i 等）创建统一 macro → Phase 6（POLISH 阶段）
- **`disable_i` 语义重构**: 将 `disable_i` 从每个 always-block 内的 reset 分支中提取出来，改为组合 gating → 架构变更，需要 formal 验证
- **Verilator 行为等价验证**: 对重构后的 V2001 输出运行 Verilator 仿真 → Phase 2 已就绪，可在 Phase 3 CI 中自动验证

---

*Context gathered for phase planning*
