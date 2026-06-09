# Phase 05: Phase 06 HIGH CLI Fixes - Context

**Gathered:** 2026-06-09

## Decisions

### 1. HARDEN-05 — Multi-property `--dump-tree` shows all checkers + `--dump-ir` 同步修复

**修复范围**: 同时修复 `--dump-tree` 和 `--dump-ir` 在多属性路径中的两个问题：

1. **`--dump-tree`**: 为每个断言计算独立的 `unoptimized_checker`（当前硬编码为 `None`）。将 `compute_hash_map` + `format_dump_tree` 的调用移到循环外部是不可能的 — 每个断言有独立的 checker/hash_map/unoptimized。重构为在循环内处理但确保每个断言都被正确处理。

2. **`--dump-ir`**: 当前多属性路径中 `--dump-ir` 在第一个断言后 `return`（第 192 行），导致后续断言不被处理。改为收集所有 IR 输出后再统一输出。

两个问题在同一条 `for` 循环中（`cli.py` ~L196-219），一并修复避免两次改动同一区域。

### 2. HARDEN-06 — `--property` 三种匹配模式

**匹配优先级**: 基于 success criteria 中的用例，按格式推断匹配模式：

| 格式 | 匹配模式 | 示例 |
|------|---------|------|
| 纯数字 | 断言索引（1-based） | `--property 3` → 第 3 个断言 |
| `@N` | 源文件行号 | `--property "@42"` → 第 42 行的断言 |
| 其他 | 标签名 exact match | `--property my_label` → 标签为 `my_label` 的断言 |

**边界处理**:
- 索引超出范围 → `PropertyNotFound` with available count
- 源行号不匹配任何断言 → `PropertyNotFound` with available source lines
- 标签名以 `@` 开头但非数字 → 标签匹配（不尝试行号匹配）
- `assertions` 列表中保留 `label=None` 的条目以便索引和行号匹配

**与现有行为兼容**: 标签匹配的语义不变（`label == property_name`），仅增加索引和行号路径。无标签断言现在可以通过索引或行号定位。

### 3. HARDEN-07 — `--output` 显式模式检测

**检测逻辑**: 在确定 `--output` 含义时，使用以下优先级：

1. 如果 `--output` 路径以 `/` 结尾 → 强制目录模式
2. 如果 `--output` 路径包含已知文件扩展名（`.sv`, `.v`, `.svh`）→ 强制文件模式
3. 否则 → 根据属性数量自动推断：
   - 单属性 → 文件模式
   - 多属性 → 目录模式（如果指定了看起来像文件名的路径，报错）

**错误处理**:
- 多属性 + 看起来像文件的输出 → `SvaCompileError: "--output looks like a file path but input has N properties; use a directory instead"`
- 目录模式 + 路径已存在且是文件 → `IsADirectoryError` → 清晰的错误消息

**`write_output_dir` 防御性修复**: 在调用 `write_output_dir` 之前检查目标是否存在且是文件，提前报错而不是静默失败。

### 4. HARDEN-08 — `--verilog` + `--dump-*` → 报错

**方案 B — 硬拒绝**: 拒绝 `--verilog` 与任何 `--dump-*` 标志的组合，抛出清晰的错误消息。

**理由**:
- 将 `verilog_mode` 传入 `debug.py` 需要改造 `format_dump_ir` / `format_dump_tree` 的函数签名（方案 C = scope creep）
- Warning（方案 A）容易被 CI/脚本忽略，不符合 HIGH severity
- 用户可以通过运行两次命令获得两种输出：先 `--dump-tree` 再 `--dump-tree --verilog`（如果未来支持的话）

**实施**: 在 `cli.py` 参数解析后，如果检测到 `verilog` 和任一 `--dump-*` 同时为真，抛出：
```
SvaCompileError: "--verilog cannot be combined with --dump-ast/--dump-ir/--dump-tree.
To see V2001-style output, run --verilog separately without dump flags."
```

## Claude's Discretion

以下细节由 execute-phase 自行决定：

- HARDEN-06 的索引/行号匹配的具体实现（辅助函数 vs 内联循环）
- HARDEN-07 的"看起来像文件"的启发式规则（除扩展名外是否需要额外检查）
- 四个修复的提交粒度（一个 commit 还是四个独立 commits）
- 是否需要新增测试 fixture（如多属性 `.sv` 文件、无标签断言的 fixture）

## Deferred Ideas

超出 Phase 5 范围：

- `--dump-tree` 支持彩色/格式化输出 → v2
- `--property` 支持正则表达式匹配 → v2
- `--output` 的 `--stdout` 模式（直接输出到 stdout）→ v2
- `--verilog` + `--dump-*` 的组合支持（方案 C）→ 后续 Phase 6 或 v2

---

*Context gathered for phase planning*
