# Phase 07: Release v1.1.0 Tag + Notes + Smoke — Context

**Gathered:** 2026-06-11

## Decisions

### 1. PyPI 发布范围

仅本地验证安装流程（`pip install .` + `uv pip install .`），不实际发布到 PyPI。项目目前是内部/本地工具，PyPI 发布在 v1.2 或更晚的里程碑考虑。

### 2. Release Notes 语言

英文。与项目 README、CLAUDE.md、SUPPORTED_CONSTRUCTS.md 语言一致。

### 3. 标签类型

Annotated tag (`git tag -a v1.1.0 -m "..."`)。包含 tagger、date、message。ROADMAP 明确要求 annotated。

### 4. CI 触发顺序

最终确认 CI 全绿 → 打 tag → tag push 触发 CI 自动运行。不在 Phase 7 内等待 CI 结果（异步验证）。

### 5. 里程碑归档

Phase 7 完成后不自动运行 `complete-milestone`。用户自行决定归档时机。

---

## Release Notes 覆盖范围

基于 Phase 1-6 的变更总结，Release Notes 使用用户语言覆盖：

- **HARDEN-01**: `disable iff` 下的 `attempt_fired` 现在正确 latch，不会被 disable 清零
- **HARDEN-02/03/04**: 内部健壮性修复（全局状态清理、重复边界校验、信号名保留）
- **HARDEN-05/06/07/08**: CLI 改进 — `--dump-tree` 正确处理多属性、`--property` 支持 index/行号匹配、`--output` 模式检测、`--verilog` 与 `--dump-*` 互斥
- **REFACTOR-01/02/03**: 11 个 RTL 模板共享 Jinja2 macro，消除 SystemVerilog/Verilog-2001 重复代码（净减少 289 行）
- **VALIDATE-02/03/04**: Verilator 作为第二仿真 oracle，CI 矩阵扩展为 2 OS × 2 Python × 2 仿真器
- **POLISH-01**: 版本同步至 1.1.0
- **Nyquist Baselines**: 为所有 6 个 v1.0 阶段生成了 Nyquist 覆盖报告

## Claude's Discretion

- Release notes 的具体措辞和结构
- 是否在 release notes 中包含 "Upgrading from v1.0" 章节
- Smoke test 的具体命令
