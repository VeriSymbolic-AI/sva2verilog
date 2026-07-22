# sva2verilog 项目进展报告

> 更新日期：2026-07-22
> 仓库：public GitHub repository
> 当前版本：v1.7.0

## 当前状态

sva2verilog 是一个开源的 SystemVerilog Assertion (SVA) 到可综合 RTL
监控器编译器。v1.7.0 已发布；当前工作树处于发布后加固状态，基于
本地发布加固提交 `3f580cd` 与后续 P1 提交均只存在本机、尚未推送，
不能作为新的远端证据基线。

- 测试套件：本轮最终本地结果见下方“2026-07-22 发布加固”；所有已运行门控 0 failed
- 代码质量：mypy --strict 0 errors，ruff 0 errors
- 形式化验证：本地核心/契约/k-induction 集合与 NFA BMC 均通过；已知 1 个 liveness xfail 保留
- 生成 RTL：本地 Yosys synthesis 与固定 Verilator 5.028 strict lint gate 均通过
- 随机差分：Icarus slow sweep 与 Verilator smoke/fast differential 均在本机通过；每次 Verilator example 使用独立构建目录
- 变异测试：门禁会先验证测试基线、隔离 Python bytecode cache，并按模块在低于 85% 时失败；当前 bool semantics 15/15、behavioral oracle 131/150（87.3%）、composer 53/55（96.4%）、ast importer 116/116，另有 RTL 模板定向变异 5/5
- 覆盖度：约 95%+ 的实际断言场景；coverage 门控 fail_under=82（当前实测 82.82%）
- 支持状态权威：`SUPPORT_MATRIX.md` 记录逐构造支持边界、证据完整度和降级原因；README / SUPPORTED_CONSTRUCTS 只作概览和解释
- 工业级验证缺口：已记录在 `INDUSTRIAL_VALIDATION_GAPS.md`，包含当前进展、P0/P1/P2 严重度、修复计划和 fully-supported 定义标准

## 2026-07-22 发布加固

本轮关闭了审计发现的发布阻塞项：

- wheel/sdist 现在包含全部 35 个运行时模板；干净的仓库外安装可编译
  SystemVerilog、Verilog-2001 和包含 NFA fragment 的构造，并通过 Icarus。
- Icarus、Verilator、generated-RTL 和 nightly 共用固定 v5.028 的 Verilator
  安装脚本；Linux/macOS 源构建依赖完整，模板注释不再误触 Verilator
  metacomment 解析。
- push/PR formal smoke 与 Full Formal 统一使用固定日期的 OSS CAD Suite；
  重型 NFA implication miters 拆为独立分片，避免 6 个超时串行累积。
- Verilator 差分后端为每次 Hypothesis example 使用独立构建目录，消除
  macOS 上由于 make 复用旧 `wrapper.o` 造成的 flaky trace。
- named sequence 声明表改为每次导入/每个模块隔离的 ContextVar，避免
  并发编译和多模块 AST 之间串扰。
- `.planning` 明确为唯一实时 GSD 状态，legacy `.gsd` 改为兼容指针；
  Phase 01/13 计划—摘要计数恢复为 39/39，Phase 13 verification 已补齐。
- 文档已纠正 `##0`、优化器、支持等级和历史/current-HEAD 证据混用。

本轮最终本地验证：1344 tests collected；Python 3.12 与 3.13 的完整本机
Icarus/default suite 均为 1341 passed / 2 skipped / 1 xfailed / 0 failed；
两个 Python 版本的 Verilator simulation 轴均为 141 passed / 1 skipped；
generated RTL synthesis + strict lint 107 passed；Full Formal 119 passed /
1 xfailed；nightly differential 为 Icarus slow 1 passed、Verilator fast 2
passed；mutation 为 composer 53/55、ast_importer 115/115。远端 Ubuntu/macOS
矩阵、scheduled nightly 与 Full Formal 仍只有在本轮工作树提交并推送后
才能形成 current-commit 远端证据，因此当前支持矩阵保持
0 个 Fully supported。

## 2026-07-22 P1 可信度闭环

本轮在第一笔发布加固提交 `3f580cd` 之后，针对验证独立性、形式化缺口和
mutation 检出能力继续加固：

- 差分测试不再从 composer `CheckerNode` 计算期望结果；新增 typed
  source-reference 模型，编译器与参考模型从同一生成规格走两条独立路径。
- deterministic catalog 扩大到 10 类；fast 为 10 个 Hypothesis example；
  slow 为每个 backend 64 个固定种子 example，刺激长度扩大到 8-24 cycles。
- 提交一个真实发现问题的 sanitized replay：overlapping start repetition。
- 新增 named `a ##1 b` 与 simple sequence `and/or` 的 6 个独立 pass/fail
  BMC，修正 support matrix 中 property `not`、`if...else`、bounded liveness
  已有 BMC 却被错误标成 missing 的陈旧记录。
- 独立证据共发现并修复 3 个真实语义缺陷：slang v11 顶层 consecutive
  repetition 静默退化、repetition oracle overlapping-start 状态错误、
  sequence `or` 在单边成功时同时发出 fail。
- nightly mutation 从两个 Python 模块扩展到四个核心语义模块，并新增
  RTL template 的边界、状态、宽度和端口连线定向突变门禁。

当前工作树最终本地证据：ruff 全通过；mypy strict 15 个源码文件 0 error；
coverage 82.82%（门槛 82%）；
完整默认/Icarus 轴 1371 passed / 1 skipped / 1 xfailed；完整 Verilator
simulation + fast differential 轴 151 passed / 1 skipped；Icarus 与 Verilator
fast differential 均 12 passed，两个 seeded slow sweep 均 1 passed（每个含
64 个生成例）；Full Formal 125 passed / 1 xfailed；Yosys synthesis +
Verilator strict lint 107 passed；四个 Python mutation 模块均超过 85%，
RTL 模板定向突变 5/5。所有上述命令 0 failed。

## v1.7.0 语言表面闭合（2026-07-10）

v1.7.0 关闭了最后已知的行为缺口：

- LANG-01 `##0` fusion：BoolExpr `a ##0 b` 自动重写为 `(a) && (b)`，复杂 `##0` 拒绝报错
- LANG-02 NFA SeqOr：union construction 通过 `_lift_to_nfa`，`(a or b) intersect c` 现在可编译
- LANG-03 NFA 范围延迟/重复：`##[M:N]` 非确定性延迟展开 + `[*M:N]` 多接受 NFA 状态
- LANG-04 NFA goto/nonconsecutive：`[->N]` 自环计数 NFA + `[=N]` relaxed-tail NFA
- Slang 双约定兼容：slang v11+ 延迟解析 prefix/suffix 约定自动检测
- Oracle boolean fallback 修复：`_tick_bool_expr_semantic` 默认值修正

NFA 引擎唯一的拒绝路径是 K 状态预算 >32。

## v1.7 证据链加固（2026-07-11，HEAD ed170cc）

在 v1.7 语言表面闭合后完成了全面证据链加固：

- P0-1：修复序列前件蕴含断言崩溃（路由层 + 防御层转 UnsupportedConstruct）
- P0-2：恢复绿色基线（ruff+mypy 0 error，快速套件 0 failed）
- P1-1：补齐 12 个真实 `.sv` 源 fixture + 13 个 E2E 测试
- P1-2：新增 Verilator 差分 nightly workflow（`differential-nightly.yml`）
- P1-3：4 个关键模块变异杀死率全部 >85%（bool_semantics 100%, behavioral_oracle 88.9%, composer 91%, ast_importer 93.3%）
- P2-1：k-induction 从 8 扩展到 11 个证明目标（10 passed + 1 xfail liveness 边界）
- P2-2：治理收尾（ROADMAP 修正、tools/audit README、v1.2.0 tag 记录）
- 遗留-1：4 处裸 assert 全部转为防御性 UnsupportedConstruct
- 遗留-2：slang v11 `DisableIff` / `AssertionInstance` AST 兼容
- 遗留-6：coverage 门控 fail_under 从 78 提升到 82

## v1.5.2/v1.6 历史修复回顾

### 里程碑历程

从 2026-05-25 启动至 2026-07-11，约 47 天内完成 v1.0 到 v1.7 全系列里程碑：

v1.0 MVP（6/1）交付编译器核心。v1.1-v1.2 加固。v1.3（6/22）交付 Tier 2 算子。v1.3.2 引入真正的 SVA↔RTL 形式化等价验证。v1.4（6/30）交付有界活性和多时钟。v1.5.0 关闭 RISK-02。v1.5.1（7/2）交付 NFA 组合引擎。v1.5.2（7/6）扩展形式化验证到全部算子、修复 first_match bug、mypy 清零、推送到 GitHub。v1.7.0（7/10）语言表面闭合。7/11 证据链加固完成。

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
- `tests/test_generated_lint.py`：实现 `verilator --lint-only -Wall --top-module <top>` generated-module gate；固定 Verilator 5.028 已在本机执行，预期 ABI/诊断类 warning 显式豁免，其余 `-Wall` warning 保持 fatal。
- `.github/workflows/ci.yml`：新增 `generated-rtl` job，在 Ubuntu 上显式安装 Yosys 和 Verilator，并运行 bounded generated RTL synthesis/lint gate。
- 2026-07-22 本地命令 `pytest tests/test_synthesis_gates.py tests/test_generated_lint.py -q --timeout=180` 记录为 `107 passed`，Yosys 与 Verilator gate 均实际执行。
- 多时钟 synchronizer 仍是 trusted boundary：Yosys 接受生成结构不等于 CDC/metastability proof。

### Phase 12 随机差分测试更新

Phase 12 增加的是证据深度，而不是新增 SVA 语法范围。本地目标验证记录：

- `tests/differential_cases.py`：生成 bounded SVA source module，并通过 slang、importer、normalizer、composer、optimizer 的正常路径编译；生成器限定在已支持 finite-state 子集。
- `tests/test_differential_cases.py` / `tests/test_differential_oracle.py`：验证 source generator、stimulus generator、Python oracle trace normalization 和 mismatch 诊断。
- `tests/test_differential.py`：对 bounded generated source cases 运行 oracle vs simulator differential；本机 Icarus fast path 通过。
- `tests/test_differential_regressions.py` 和 `tests/differential/regressions/`：提供 sanitized failure artifact schema 与 promoted fixture replay 入口；当前没有真实 promoted failure fixture，因此 replay 入口 skip，不算通过证据。
- 本地命令 `uv run pytest tests/test_differential_cases.py tests/test_differential_oracle.py tests/test_differential_regressions.py -q` 记录为 `28 passed, 1 skipped`。
- 本地命令 `uv run pytest tests/test_differential.py -q --simulator=iverilog` 记录为 `2 passed, 1 skipped`；skip 是 opt-in slow sweep。
- 2026-07-22 nightly 原命令记录：Icarus `differential_slow` 1 passed；Verilator `not differential_slow` 2 passed / 1 deselected。
- 首次 differential run 发现并修复 single-cycle implication false antecedent 的 Python oracle routing bug；已在 `tests/test_behavioral_oracle.py` 增加回归。

### GitHub 发布

推送到公开 GitHub 仓库，干净历史（orphan branch），无私人身份或内部资料。

## 遇到的问题

1. first_match posedge bug：存在多版本未发现，因为该算子缺仿真和形式化测试。教训：每个算子必须有 RTL 编译验证 + 形式化等价。
2. mypy 49 errors：CI lint job 一直失败但未处理。教训：CI 红就必须立即修。
3. 形式化参考时序对齐：写 BMC miter 参考监控器时，寄存延迟必须与 RTL 模板精确对齐。5/6 新参考需要时序迭代。教训：时序对齐是形式化等价验证中最耗时的部分。
4. GitHub workflow 权限与 CI 时长：此前 GitHub workflow 权限不足，CI 文件无法推送；后续全量 formal 放在 push/PR CI 中又导致超时。本轮已切分为快速 push/PR baseline 与 manual/scheduled `Full Formal`，并确认 run `28931676000` 绿灯。

## 验证体系

六层验证金字塔：

1. 行为预言机（纯 Python IEEE 模型，与 RTL 结构独立）
2. iverilog/Verilator 仿真交叉验证（逐周期 pass/fail 比对）
3. SymbiYosys BMC 形式化等价（历史全算子基线 62 证明；Phase 10 56 个 BMC/契约测试）：独立 IEEE 1800 参考监控器 + sby BMC miter
4. SymbiYosys k-induction 完备证明（10 个证明目标 + 1 xfail liveness 边界）：Tier-A 核心监控器加 `##1`、simple `|->`、`[*3]`、`##[1:5]`、`[*2:5]`、`s_eventually[1:3]`
5. Generated RTL 工具接受度（Phase 11）：Yosys synthesis + Verilator strict lint 共 107 passed
6. Source-level differential testing（Phase 12）：bounded SVA source + generated stimulus，Python oracle 分别与 Icarus/Verilator 逐周期比较；本机 nightly 两轴均通过

RISK-01 纪律：预言机和参考监控器必须与 RTL 实现结构独立。曾两次发现被循环证明掩盖的真实缺陷（BUG-DELAY-01、BUG-IMPL-01）。

## 已知限制

- 1 xfail：`s_eventually[1:3]` k-induction induction step 不收敛（liveness 边界，诚实记录）
- SUPPORT_MATRIX 中 0 个构造行达到 Fully supported，全部为 Bounded evidence（仍缺 current-commit 远端矩阵证据或全契约 formal proof）
- 全算子等价证明仍以 BMC 有界为主；k-induction 当前覆盖 10 个小状态目标，尚未扩展到全部算子、复杂 NFA、liveness 或 CDC 边界
- 多时钟形式化等价永久排除（行业通用限制）
- K-state budget (>32) 和 CDC 边界是 NFA 引擎仅存的拒绝路径
- 本机 Verilator 5.028 已安装并完成双 Python 版本 simulation、generated lint 与 differential；仍需同一提交的远端 Ubuntu/macOS CI 记录

## 未来规划

### 短期（发布加固闭环）

1. 评审并提交 2026-07-22 hardening 工作树。
2. 推送后触发完整 CI（lint + Icarus/Verilator 双矩阵 + formal smoke +
   generated RTL），并手动触发 differential nightly 与 Full Formal。
3. 只有所有远端门控在同一 commit 上通过后，记录 run ID 并逐行重评
   `SUPPORT_MATRIX.md`；不得沿用历史 run 替代 current-commit 证据。
4. 不改写已有 `v1.7.0` tag；远端全绿后以 `v1.7.1` 修复版发布，并让
   package version、`__version__`、tag、release notes 和 GitHub Release
   指向同一已验证 commit。

### 中期（Phase 2：证据链闭合，2-3 周）

4. 选择 5-8 个核心构造（bool、$rose/$fell/$stable/$changed、##1、simple |->、[*3]、first_match、disable iff），补齐 current-HEAD 证据链，逐行升级为 Fully supported
5. wheel 构建和 clean-install smoke 验证
6. SUPPORT_MATRIX 中核心 rows 证据从 missing/pending 升级为 present

### 长期（按需求拉动）

7. FPGA 原型（FUT-03）：与 OSS CAD Suite 集成，记录面积/时序/资源基线
8. 真实设计 corpus：至少 2 个非玩具设计端到端流程
9. C++ 重写 v2（FUT-04）：仅在 Python 性能基线明确成为瓶颈后启动
10. 社区采用与学术发表：DVCon 投稿（多层验证方法论 + k-induction + NFA 组合引擎）

## 风险登记册

语言实现风险 RISK-00 至 RISK-06 已闭环或降级。本轮新增的制品完整性、
CI 工具漂移、差分构建缓存和状态文档漂移均已在本地修复；唯一未闭环项
是“远端 current-commit 复验”，它是证据门禁，不应被描述成已经通过。

## 竞争定位

sva2verilog 在"可综合 SVA 监控器"赛道（对标商用 emulator Palladium/ZeBu）覆盖约 95%+ 实际断言场景。开源世界几乎无对手，学术界唯一系统性同类是 MBAC（Boulé & Zilic）。永久边界：无界活性（理论不可综合）、CDC 结构验证（独立工具品类）、多线程局部变量（ROI 为负）。
