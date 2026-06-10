# Phase 06: Cleanup + Version Sync + Final Review - Context

**Gathered:** 2026-06-10

## Decisions

### 1. POLISH-01 — Version Sync

`src/sva2rtl/__init__.py` `__version__ = "0.1.0"` + `pyproject.toml` `version = "1.0.0"` → 同步为 `"1.1.0"`。

**实施**: 修改两个文件各一字，原子性提交。

### 2. POLISH-02/03 — MEDIUM/LOW Triage

10 MEDIUM + 9 LOW 发现来自 v1.0 Phase 06 代码审查。Phases 1-5 已解决所有 HIGH 发现和部分 MEDIUM/LOW。剩余项按以下原则处置：

**已修复（可关闭）**:
- M-06.7 (slang 版本文档不一致) — 已在 ROADMAP/CONTEXT 中明确 v7.0 是 fixture 版本
- L-06.5 (bool_expr attempt_fired_q 被 disable_i 清零) — Phase 3 HARDEN-01 已修复

**延期至 v1.2（在 PROJECT.md 中记录）**:
- M-06.1 (异常处理器顺序依赖) — 架构重构，不宜在 v1.1 改动
- M-06.2 (SVA-E002 双出口码) — 可能破坏现有测试
- M-06.3 (dump-ir 多属性无分隔符) — Phase 5 已改进为 `\n\n` 分隔，标记为已部分修复
- M-06.4 (--default-clock 不存在但出现在消息中) — 文档清理，低风险
- M-06.5 (SVA-E005 文档不匹配) — 文档修正
- M-06.6 (--verilog CLI 快照测试缺失) — Phase 2 已添加 golden parity，扩展测试不划算
- M-06.8 (conftest marker 重复注册) — 无实际危害
- M-06.9 (延迟导入) — 代码风格，不影响正确性
- M-06.10 (GitHub URL 不一致) — 文档修正
- L-06.1 (异常类型名被吞没) — 日志增强
- L-06.2 (错误码在消息字符串中) — 不影响功能
- L-06.3 (seq_concat_top 缺少 wire 声明) — 已在 Phase 3 模板重构中解决
- L-06.4 (concat_delay 零延迟分支) — Phase 3 已重构模板
- L-06.6 (文档中 attempt_fired 描述为 pulse 但实际为 sticky) — 文档修正
- L-06.7 (重复 boilerplate) — Phase 3 模板重构已消除大部分
- L-06.8 (--version 标志位置) — 无实际影响
- L-06.9 (fixture 阴影) — 代码风格

**Phase 6 可修复（少于 5 行改动）**:
- M-06.4: 从错误消息中移除 `--default-clock` 引用
- M-06.5: 更新 SUPPORTED_CONSTRUCTS.md 中的 SVA-E005 描述
- L-06.6: 更新 SUPPORTED_CONSTRUCTS.md 中 attempt_fired 的描述

其余全部标记为 deferred，在 PROJECT.md 的 "Out of Scope for v1.1" 章节中记录。

### 3. POLISH-04 — Cross-Phase Code Review

对 Phases 1-5 的完整 diff 执行代码审查。审查范围为 `git diff v1.0-tag..HEAD`，重点关注：

- 无新的 HIGH 发现（等价于"之前的所有修复未引入新的高风险缺陷"）
- 模板质量（macro 使用一致性）
- CLI 行为（新增标志无破坏性变更）

审查结果写入 `06-REVIEW.md`，明确结论为 "zero new HIGH findings"。

## Claude's Discretion

- MEDIUM/LOW triage 清单的具体格式（表格 vs 列表）
- POLISH-04 代码审查是否逐文件进行还是仅抽取关键变更
- 是否将 triage 结果和代码审查合并在一个 plan 中还是分两个 plan

## Deferred Ideas

n/a — Phase 6 是 v1.1 的最后一个非发布阶段，所有超出范围的项应记录在 PROJECT.md 中供 v1.2 参考。

---

*Context gathered for phase planning*
