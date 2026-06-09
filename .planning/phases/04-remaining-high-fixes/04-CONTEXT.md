# Phase 04: Remaining HIGH Fixes - Context

**Gathered:** 2026-06-09

## Decisions

### 1. HARDEN-02 — `_DECLARATIONS` 全局状态修复

**方案 A — 最小改动（1 行）**: 在 `import_all_assertions()` 函数开头加 `_DECLARATIONS.clear()`。

**理由**: 当前代码路径中，`import_all_assertions()` 每次被调用时，`for member in members` 循环会覆盖 `_DECLARATIONS`，最后一个 `InstanceBody` 的声明会覆盖之前的。在当前架构中只调用一次，所以实际上不触发 bug。这是**防御性修复** — 1 行代码，零回归风险，为未来的多文件处理做好准备。

**不改方案 B**: 将全局变量改为函数级局部变量需要改动 `_expand_named_sequence()` 的函数签名（它直接访问 `_DECLARATIONS`），以及在多处调用链中传递此状态。对于硬化的 v1.1，这种重构的回归风险与收益不匹配。

### 2. HARDEN-03 — `rep_consecutive` 边界处理

**修复两项边界**: `rep_min > rep_max` + `[*0]` 拒绝。

**修复 A — `rep_min > rep_max`**: 在 `_build_seq_repetition()` (ast_importer.py ~L540) 中添加验证：
```python
if rep_min > rep_max:
    raise SvaCompileError(
        f"Invalid repetition range: [*{rep_min}:{rep_max}] — min must be <= max",
        source_loc=source_loc
    )
```
这与 `_build_seq_concat()` 中已有的延迟验证模式一致。

**修复 B — `[*0]` 拒绝**: `[*0]` 在 IEEE 1800 中表示空匹配（零次重复），但硬件实现没有意义 — 空匹配即"始终通过"，与 SVA 语义中的 vacuous pass 混淆。已在模板层处理 `[*0]` 会产生模糊的 RTL 输出。决定：在 ast_importer 中将其作为不支持的操作符拒绝，使用 `SvaCompileError` 并附上源位置。

**不处理**: `[*0:0]` — `rep_min=0, rep_max=0`，这被前面的 `[*0]` 检查自然拒绝。`[*1]` 已由 normalizer 移除。`rep_min=0, rep_max>0`（如 `[*0:3]`）是合法的 — 允许零次到多次重复匹配，模板已能正确处理。

### 3. HARDEN-04 — `_collect_signals` 信号名保留

**最简修复**: 将 `composer.py:751` 的 `return tuple((name, name) for name in seen)` 改为保留第一个匹配到的原始 `(port_name, sig_name)` 对：

```python
# Before (buggy):
return tuple((name, name) for name in seen)

# After (fixed):
result = {}
for child in children:
    for port_name, sig_name in child.observed_signals:
        if port_name not in result:
            result[port_name] = sig_name
return tuple((p, s) for p, s in result.items())
```

**不改 `extract_signals`**: 它从布尔表达式语法树中提取信号，port_name 和 sig_name 始终相同，`(name, name)` 是正确的行为。

**测试验证**: 添加一个测试用例，其中子 checker 的 `observed_signals` 包含 `port_name != sig_name` 的情况，验证 `_collect_signals` 的输出保留了原始映射。

## Claude's Discretion

以下细节由 plan-phase 和 execute-phase 自行决定：

- HARDEN-02 的测试用例设计（是否需要多断言的集成测试，或单元测试即可验证 `.clear()` 被调用）
- HARDEN-03 的 `[*0]` 错误消息文本
- HARDEN-04 测试用例的具体信号命名场景
- 三个修复是否需要放在同一个 plan 还是分成独立 plans（建议一个 plan 包含所有三个修复，它们互相独立）

## Deferred Ideas

以下想法超出 Phase 4 范围：

- **全局状态彻底消除**: 将所有模块级可变状态（`_DECLARATIONS` 及其他）迁移到不可变上下文对象 → v2 架构重构
- **`[*0]` 的完整硬件实现**: 实现空序列的正确硬件语义 → 需要 formal 验证，v2+
- **信号重命名的完整 bind 支持**: 允许用户通过 CLI 指定信号映射 → v2 feature
- **rep_consecutive 的 formal 验证**: 对重复计数器的正确性进行形式化验证 → v2

---

*Context gathered for phase planning*
