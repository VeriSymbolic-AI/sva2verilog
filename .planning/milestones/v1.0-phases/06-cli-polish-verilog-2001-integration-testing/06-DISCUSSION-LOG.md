# Phase 6 Discussion Log

**Phase:** 06 - CLI Polish + Verilog-2001 + Integration Testing
**Date:** 2026-05-28
**Duration:** ~5 minutes
**Mode:** default (all areas selected)

---

## Areas Discussed

### 1. Verilog-2001 转换策略
**Options presented:**
1. Jinja2 条件分支（推荐） — 单模板 + `{% if verilog_mode %}` 守卫
2. Jinja2 自定义 filter — 用 filter 函数包装类型声明
3. 双模板集 — 维护两套独立模板

**User selected:** Option 1 — Jinja2 条件分支
**Notes:** 用户选择单一事实源方案，接受模板可读性的轻微下降换取维护便利性。

---

### 2. --dump-ir 输出格式
**Options presented:**
1. 缩进树（推荐） — 每节点类型+参数+位置，2空格缩进
2. S-expression — Lisp 风格紧凑表示
3. 表格形式 — 平铺表格

**User selected:** Option 1 — 缩进树
**Notes:** 与 --dump-tree 保持风格一致，适合人类调试阅读。

---

### 3. --property 选择 + 多 property 文件处理
**Options presented:**
1. 全部编译 + 可选过滤（推荐） — 默认编译所有，--property 精确过滤
2. 默认单个 + 显式全部 — 保守默认
3. 全部 + 单文件输出 — 合并到一个 .sv

**User selected:** Option 1 — 全部编译 + 可选过滤
**Notes:** 最符合编译器工具惯例。无匹配时列出可用 label 是良好 UX。

---

### 4. 集成测试 + CI + 发布打包
**Options presented:**
1. GitHub Actions（推荐） — ubuntu + macOS 矩阵, Python 3.12/3.13, Icarus
2. 本地优先，CI 延后 — 减少 Phase 6 工作量
3. 简化 CI（无 Icarus） — 只跑 pytest + mypy

**User selected:** Option 1 — GitHub Actions
**Notes:** 完整 CI 矩阵，确保跨平台兼容性。

---

### 5. README 文档语言
**Options presented:**
1. 完整 README（中英双语） — 单文件双语
2. 英文主 + 中文副本 — README.md + README_zh.md
3. 纯英文 — 国际化标准

**User selected:** Option 2 — 英文主 + 中文副本
**Notes:** 开源项目国际化标准，同时覆盖中文用户群体。

---

## Deferred Ideas

None captured during this session.

## Claude's Discretion Items

- --dump-ast 实现细节
- 集成测试组织方式
- SUPPORTED_CONSTRUCTS.md 结构
- 错误代码表格式
- pyproject.toml 元数据
- --version 实现方式
- Golden file 锁定策略
