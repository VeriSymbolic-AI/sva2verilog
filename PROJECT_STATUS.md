# sva2verilog 项目进展报告

> 更新日期：2026-07-09
> 仓库：public GitHub repository
> 当前版本：v1.5.2 + current main hardening

## 当前状态

sva2verilog 是一个开源的 SystemVerilog Assertion (SVA) 到可综合 RTL 监控器编译器。项目已完成 v1.5.2 发布并推送到 GitHub。当前状态：

- 测试套件：1094 passed, 4 skipped, 1 xfailed, 0 failed
- 代码质量：mypy --strict 0 errors, ruff 0 errors
- 形式化验证：历史基线为 62 个非循环 BMC 等价证明（覆盖所有已支持算子）+ 5 个 Tier-A k-induction 完备证明；Phase 10 本地目标文件当前为 56 个 BMC/契约测试 + 8 个 k-induction 证明目标
- 生成 RTL 综合/静态检查：Phase 11 本地 Yosys generated-RTL smoke gate 通过；Verilator lint-only gate 已实现并加入 CI，但本机因未安装 Verilator 跳过，不能算作通过证据
- 覆盖度：约 95%+ 的实际断言场景
- 支持状态权威：`SUPPORT_MATRIX.md` 记录逐构造支持边界、证据完整度和降级原因；README / SUPPORTED_CONSTRUCTS 只作概览和解释
- 工业级验证缺口：已记录在 `INDUSTRIAL_VALIDATION_GAPS.md`，包含当前进展、P0/P1/P2 严重度、修复计划和 fully-supported 定义标准

## 当前 main 新增修复（2026-07-07）

本轮修复了 `[->N]` / `[=N]` 的单拍 `start` 语义缺口：`start` 作为“开始一次 property evaluation”的触发后，RTL 现在会用内部 `running_q` 持续追踪后续非连续 occurrence，直到第 N 次 occurrence 完成并锁定 `pass`。此前模板只在 `start` 为真时计数，单拍启动后会漏掉后续 occurrence；原形式化 reference 也按 RTL timing 编写，存在同构证明风险。

已补强：

- `goto_rep` / `nonconsec_rep` RTL 模板：增加 armed/running 状态，单拍启动后继续计数。
- behavioral oracle：同步为单拍启动后持续尝试的语义模型。
- simulation tests：新增 `[->3]`、`[=5]` 单拍 start 后跨 gap 计数的 RTL-vs-oracle 回归。
- formal miter references：改为独立语义 reference，不再按旧 RTL start gating 复制实现。
- importer hardening：`[->M:N]` / `[=M:N]` 反向范围、非正/无界范围，以及当前未实现的 ranged count（`M<N`）现在明确报 `SVA-E002`。v1 只支持固定 `[->N]` / `[=N]`。

## 里程碑历程

从 2026-05-25 启动至 2026-07-06，约 42 天内完成 13 个里程碑：

v1.0 MVP（6/1）交付编译器核心。v1.1-v1.2 加固。v1.3（6/22）交付 Tier 2 算子。v1.3.2 引入真正的 SVA↔RTL 形式化等价验证。v1.4（6/30）交付有界活性和多时钟。v1.5.0 关闭 RISK-02。v1.5.1（7/2）交付 NFA 组合引擎。v1.5.2（7/6）扩展形式化验证到全部算子、修复 first_match bug、mypy 清零、推送到 GitHub。

## v1.5.2 完成的工作

### Bug 修复

first_match posedge 参数 bug：模板把 `posedge`（SV 关键字）作为裸参数传递给子模块，导致 yosys/iverilog 语法错误。自 v1.3 存在但从未被发现（缺仿真和形式化测试覆盖）。已修复。

disable_iff oracle 泄漏：`simulate_checker_hierarchy` 不传播 disable 信号到组合节点的叶子，导致 fail 事件泄漏。已修复（`_reset_subtree()` + `effective_disable`）。

### 形式化验证扩展（55→62 BMC 证明）

6 个之前只有仿真覆盖的算子补齐了非循环 BMC 等价证明：disable iff、[*N]、$past、first_match、[->N]、[=N]。每个用独立 IEEE 1800 参考监控器（移位寄存器/计数器结构，与 sva2rtl 生成的单热 NFA 结构独立）。

### CI 强化

CI workflow 已重新纳入版本控制，恢复 lint、8 轴仿真矩阵（`{ubuntu,macos} × {3.12,3.13} × {iverilog,verilator}`）和 push/PR `formal smoke` job。完整形式化证明 sweep 已移入 manual/scheduled `Full Formal` workflow，避免 push/PR CI 超时。lint job mypy --strict 通过。

## Remote CI Baseline Ledger

**Target commit:** `674cea1adf15dade7b664b76912b015c8da04614`

**Run URL:** [GitHub Actions run 28931676000](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/28931676000)

**Run ID:** `28931676000`

**Completed:** `2026-07-08T09:31:34Z`

**State:** confirmed green for the restored push/PR CI baseline workflow

| Axis | Required evidence | Current result |
|------|-------------------|----------------|
| lint | GitHub Actions `lint` job with ruff and mypy | success in run `28931676000` |
| Icarus | GitHub Actions test matrix jobs with `simulator=iverilog` | success across all four `{ubuntu,macos} x {3.12,3.13}` axes in run `28931676000` |
| Verilator | GitHub Actions test matrix jobs with `simulator=verilator`, not skipped | success across all four `{ubuntu,macos} x {3.12,3.13}` axes in run `28931676000` |
| formal | GitHub Actions `formal smoke` job with Yosys, sby, and slang installed | success in run `28931676000`; representative smoke only |

This closes the Phase 8 remote reproducibility gate for the restored push/PR CI
workflow. The complete SymbiYosys proof sweep is still intentionally outside the
push/PR baseline and belongs to the manual/scheduled `Full Formal` workflow; do
not describe run `28931676000` as a full formal proof publication.

Local skips for Verilator, Yosys, or `sby` are developer-environment skips; a
local skip is not evidence pass. BASE-02/BASE-03 are satisfied by the remote run
above for the push/PR baseline, while broader full-formal and synthesis evidence
remain tracked in `SUPPORT_MATRIX.md`.

### k-induction 完备证明

新增 `tests/test_formal_kinduction.py`，对 `bool_expr`、`$rose`、`$fell`、`$stable`、`$changed` 5 个 Tier-A 核心监控器运行 SymbiYosys `prove` 模式（BMC basecase + induction step）。本轮修复 `$stable` / `$changed` reference 的反向错误，并收紧 xfail 判定：只有 induction 未收敛/超时才 xfail，真实 counterexample 必须失败。

### Phase 10 形式化深度更新

Phase 10 扩展的是形式化 harness 深度，而不是新增 SVA 语言范围。本地目标验证记录：

- `tests/test_formal_harness_modes.py`：8 个 harness 文本契约测试，覆盖 `continuous`、`single_shot`、`arbitrary_start`、`arbitrary_disable`、`reset_recovery`、full-contract 输出集合、cover probe 和 reference `disable_i` 连接。
- `tests/test_formal_sva_equiv.py`：56 个 BMC/契约测试，新增代表性 `arbitrary_start`、`arbitrary_disable`、`reset_recovery` 和 full-contract miter slice。具体深度记录在 `SUPPORT_MATRIX.md` 的 Phase 10 formal evidence ledger。
- `tests/test_formal_kinduction.py`：8 个 k-induction proof 目标，除了原 5 个 Tier-A leaf/sampled-value 目标，新增 `##1` fixed delay、simple `|->` overlap implication、`[*3]` fixed consecutive repetition。
- full-contract 证据是代表性子集：bool、`$rose`、simple overlap implication、fixed consecutive repetition；`disable iff` 当前提升为 variable-disable pass/fail BMC，不单独宣称 full-contract bundle 已闭环。
- 仍不把 Phase 10 本地目标验证等同于 remote full formal sweep、Yosys synthesis gate 或随机差分测试。

### Phase 11 生成 RTL 综合/ lint 更新

Phase 11 增加的是生成 RTL 工具接受度证据，而不是新增 SVA 语言范围或语义证明。本地目标验证记录：

- `tests/generated_rtl_cases.py`：集中维护代表性 generated monitor catalog，覆盖 boolean、sampled value、fixed/ranged/zero delay、overlap/non-overlap implication、consecutive/goto/nonconsecutive repetition、first_match、disable iff、named sequence、property composition、bounded liveness、NFA generic composition 和 multi-clock trusted-boundary。
- `tests/test_synthesis_gates.py`：写出 `emit_all()` 生成的 `.sv` 模块并通过 Yosys 执行 `read_verilog -sv`、`hierarchy -check -top`、`proc`、`opt`、`check`、`synth -run coarse`、`check`。
- `tests/test_generated_lint.py`：实现 `verilator --lint-only -Wall --top-module <top>` generated-module gate；本机未安装 Verilator，因此 lint cases 跳过，不能记为 pass evidence。
- `.github/workflows/ci.yml`：新增 `generated-rtl` job，在 Ubuntu 上显式安装 Yosys 和 Verilator，并运行 bounded generated RTL synthesis/lint gate。
- 本地命令 `UV_CACHE_DIR=.uv-cache uv run --no-sync pytest tests/test_synthesis_gates.py tests/test_generated_lint.py -q --timeout=180` 记录为 `81 passed, 26 skipped`；skip 来自本机 Verilator 缺失。Yosys 本地 smoke cases 全部通过。
- 多时钟 synchronizer 仍是 trusted boundary：Yosys 接受生成结构不等于 CDC/metastability proof。

### GitHub 发布

推送到公开 GitHub 仓库，干净历史（orphan branch），无私人身份或内部资料。

## 遇到的问题

1. first_match posedge bug：存在多版本未发现，因为该算子缺仿真和形式化测试。教训：每个算子必须有 RTL 编译验证 + 形式化等价。
2. mypy 49 errors：CI lint job 一直失败但未处理。教训：CI 红就必须立即修。
3. 形式化参考时序对齐：写 BMC miter 参考监控器时，寄存延迟必须与 RTL 模板精确对齐。5/6 新参考需要时序迭代。教训：时序对齐是形式化等价验证中最耗时的部分。
4. GitHub workflow 权限与 CI 时长：此前 GitHub workflow 权限不足，CI 文件无法推送；后续全量 formal 放在 push/PR CI 中又导致超时。本轮已切分为快速 push/PR baseline 与 manual/scheduled `Full Formal`，并确认 run `28931676000` 绿灯。

## 验证体系

四层验证金字塔：

1. 行为预言机（950 单元测试）：纯 Python IEEE 模型，与 RTL 结构独立
2. iverilog/Verilator 仿真交叉验证（129 测试）：逐周期 pass/fail 比对
3. SymbiYosys BMC 形式化等价（历史全算子基线 62 证明；Phase 10 目标文件当前 56 个 BMC/契约测试）：独立 IEEE 1800 参考监控器 + sby BMC miter
4. SymbiYosys k-induction 完备证明（Phase 10 当前 8 个证明目标）：Tier-A 核心监控器加 `##1`、simple `|->`、`[*3]` 代表性小状态模板
5. Generated RTL 工具接受度（Phase 11）：Yosys synthesis-oriented smoke gate 本地通过；Verilator lint-only gate 已配置在 CI，本机 skip 不算 pass evidence

RISK-01 纪律：预言机和参考监控器必须与 RTL 实现结构独立。曾两次发现被循环证明掩盖的真实缺陷（BUG-DELAY-01、BUG-IMPL-01）。

## 已知限制

- 1 xfail：`bool_expr` 叶子不独立产生 fail 的结构性见证，fail 语义来自蕴含父节点
- ##0 fusion 保留 +1；当前 main 对 boolean `##0` 发 warning，并建议用 `a && b` 替代。自动 rewrite/reject 仍是后续语义迁移工作
- 全算子等价证明仍以 BMC 有界为主（历史 depth=15-30）；k-induction 当前覆盖 8 个小状态目标，尚未扩展到全部算子、复杂 NFA、liveness 或 CDC 边界
- 多时钟形式化等价永久排除（行业通用限制）
- NFA 仍拒绝：范围延迟操作数、intersect 内 SeqOr/goto/nonconsec

## 未来规划

### 短期（1-2 周）

1. 继续维护远端 CI baseline ledger，必要时单独运行 manual/scheduled `Full Formal`
2. 代码覆盖率提升到 95%+（ast_importer 81.4%、composer 87.7%、behavioral_oracle 86.6%）
3. 嵌套 NFA BMC 深度从 15 增加到 25-30

### 中期（1-2 月）

4. 变异测试（mutmut）：验证测试套件区分力，目标变异杀死率 >85%
5. 差分测试框架：随机生成 SVA → 编译 → 仿真 → 比对，发现未知组合 bug
6. 继续扩展 k-induction：Phase 10 已从 5 个 Tier-A 核心证明扩大到 8 个小状态目标；下一步需要为更多 BMC-only 家族补 invariants/cutpoints 或明确保留 bounded 边界
7. v1.6 决策：单线程局部变量 / 多时钟×NFA / FPGA 原型（需求拉动）

### 长期

8. 社区采用：文档、示例、教程
9. 学术发表：DVCon 或会议论文（三层验证方法）
10. C++ 重写（v2）：大规模设计性能优化

## 风险登记册

所有已识别风险（RISK-00 至 RISK-06）均已闭环或降级。无新增风险。

## 竞争定位

sva2verilog 在"可综合 SVA 监控器"赛道（对标商用 emulator Palladium/ZeBu）覆盖约 95%+ 实际断言场景。开源世界几乎无对手，学术界唯一系统性同类是 MBAC（Boulé & Zilic）。永久边界：无界活性（理论不可综合）、CDC 结构验证（独立工具品类）、多线程局部变量（ROI 为负）。
