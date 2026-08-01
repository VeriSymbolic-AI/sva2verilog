# sva2verilog 项目进展报告

> 更新日期：2026-08-01
> 仓库：public GitHub repository
> 当前版本：v1.7.1

## 当前状态

sva2verilog 是一个开源的 SystemVerilog Assertion (SVA) 到可综合 RTL
监控器编译器。v1.7.1 已于 2026-07-31 发布，修复了 v1.7.0 的完整契约语义
缺陷。当前本地 `main` 基于远端 `243b839`，并包含尚未推送的 Linux
Verilator 安装修复；因此本地结果不能替代下一次同提交远端运行。

- 发布状态：tag `v1.7.1` 指向 `8b5c063`；远端 `main` 为 `243b839`
- 当前远端 CI：run `30649226848` 的 lint、formal smoke、coverage、Python
  3.14/package、四个 Icarus 轴和两个 macOS Verilator 轴通过；三个 Ubuntu
  Verilator 相关 job 在安装阶段因缺少 `FlexLexer.h` 失败
- 远端测试实数：Ubuntu Python 3.12 Icarus 为 1292 passed / 183 skipped；
  macOS Python 3.12 Verilator 为 169 passed / 1 skipped；coverage 86.25%；
  Python 3.14 非仿真轴为 1122 passed / 126 skipped
- F-01 本地修复：Ubuntu 安装器补充 `libfl-dev` 并在源码编译前检查
  `/usr/include/FlexLexer.h`；尚需新 SHA 的 Ubuntu Actions 证实
- 形式化验证：同 SHA formal smoke 3/3 通过；当前本地 Full Formal 文件集
  为 125 passed / 1 个严格 liveness xfail，不能冒充当前远端 Full Formal
- nightly / Full Formal：最近运行仍停在旧提交 `8e7af87`，且 job 因账户
  payment/spending-limit 限制未启动；当前 SHA 没有可用的 nightly/full 证据
- 当前本地验证：完整 Icarus 1473 passed / 1 skipped / 1 xfailed，branch
  coverage 86.31%，generated RTL 133 passed，Python 3.14 广泛轴 1247 passed /
  1 xfailed；wheel/sdist 分别在 Python 3.12 和 3.14 仓库外冒烟通过
- 变异与差分：当前分支 Python mutation 260/301（86.4%，另有 31 个未覆盖
  候选）、RTL template mutation 11/11；Icarus/Verilator fast 各 16 passed，
  date-seeded slow 各 1 passed（每项 64 examples）；scheduled evidence 仍缺失
- 支持状态权威：`SUPPORT_MATRIX.md` 记录逐构造支持边界、证据完整度和降级原因；README / SUPPORTED_CONSTRUCTS 只作概览和解释
- 工业级验证缺口：已记录在 `INDUSTRIAL_VALIDATION_GAPS.md`，包含当前进展、P0/P1/P2 严重度、修复计划和 fully-supported 定义标准

## 2026-08-01 v1.7.1 发布后资格审计

最新代码与远端 `main` 已核对一致。当前 CI 失败根因不是 RTL 回归，而是
Ubuntu 24.04 将 Verilator 所需的 C++ Flex header 放在推荐包 `libfl-dev`；
仅安装 `flex` 会得到可执行文件，却没有 `<FlexLexer.h>`。本地 F-01 修复
同时增加静态依赖回归和 header fail-fast 探针。

这次审计也确认 v1.7.1 是“已发布的语义修复版本”，不是“已完成远端资格
闭环的工业基线”。在 Linux Verilator、generated RTL、nightly differential
和 Full Formal 对同一修复 SHA 全绿前，支持矩阵保持 0 个 Fully supported。
多时钟电平同步器的事件丢失/合并风险仍是独立的架构级 Trusted boundary。

### 当前本地资格证据（2026-08-01）

本地在 F-01/F-02 修复分支上重新执行了完整门禁，而不是沿用 2026-07-26
数字：ruff、mypy strict、冻结 lock、工作流 YAML、安装脚本语法和覆盖率下限
均通过；Icarus 全套为 1473 passed / 1 skipped / 1 xfailed，generated RTL
为 133 passed，Full Formal 为 125 passed / 1 个已记录的 strict-liveness
xfail。Python 3.14 非仿真广泛轴为 1247 passed / 1 xfailed。双后端差分
fast 各 16 passed，日期 seed `20260801` 的 slow 各 1 passed，每项内部运行
64 个 Hypothesis examples。branch coverage 为 86.31%。v1.7.1 wheel/sdist
在仓库外分别用 Python 3.12、3.14 安装、调用 CLI、生成 RTL 并通过 Icarus。

当前分支重新执行的 Python mutation 为 260/301 killed（86.4%）：
`bool_semantics.py` 15/15、`behavioral_oracle.py` 112/130、`composer.py`
41/48、`ast_importer.py` 92/108；另有 31 个未覆盖候选不计入分母，41 个
有效变异仍存活。RTL 模板 mutation 为 11/11。门槛通过不等于没有测试债务，
存活变异和未覆盖候选应作为后续定向回归输入。

## 2026-07-26 完整契约与发布门禁加固（历史快照）

以下数字和远端状态记录的是 2026-07-26 当日证据，不代表 2026-08-01
当前分支；最新结论以前一节为准。

本轮从“测试是否真的覆盖可信度契约”而不是测试总数出发，修复了 5 组问题：

- 多时钟 top 恢复统一 `start/disable_i/attempt_fired/disabled_o` 接口，不再
  永久启动；外部 disable 同时清空 per-domain checker 和 2-DFF 状态。
- 普通 `|->` / `|=>` 的 `attempt_fired` 改为记录 top-level `start`，即使
  antecedent 为假也不会被误报为“从未尝试”；独立 full-contract formal
  reference 同步纠正。
- source differential 扩展为完整输出契约，外部 `disable_i` 进入 deterministic
  和 Hypothesis 刺激域；schema-v1 历史 replay 仍可读取，但新 live trace
  必须实际采集完整信号。
- push/PR CI、nightly 和 Full Formal 读取 JUnit outcome，分别约束最低
  passed 数和最大 skip/xfail 数，防止缺工具或错误选择测试导致的空绿灯。
- 新增 Python 3.14 广泛兼容轴；真实构建 wheel/sdist，source archive 排除
  `tests/tools/.github/.planning/.gsd`，并在仓库外全新 venv 安装 wheel、
  调用 CLI、生成 RTL、通过 Icarus。

Fresh 本地证据：Python 3.12 full Icarus 1466 passed / 1 skipped /
1 xfailed，branch coverage 86.31%；Verilator simulation 169 passed /
1 个已知 Icarus-only skip；generated RTL 133 passed；Full Formal
125 passed / 1 个严格 liveness xfail；Python 3.14 非仿真广泛轴
1240 passed / 1 xfailed；Icarus/Verilator differential fast 各 16 passed，
slow 各 1 passed（64 examples）；wheel/sdist 仓库外安装冒烟通过。

这些都是本地、当前工作树证据，不是远端同提交证据。2026-07-26 最新
scheduled nightly run `30191482973` 的三个 job 因 GitHub 账户账单/额度限制
未启动；origin/main 仍是旧提交 `8e7af87`。因此支持矩阵继续保持 0 个
Fully supported，不能把本地结果或历史绿色 run 替代 current-commit
Ubuntu/macOS CI、scheduled nightly 和 Full Formal。

多时钟仍有一个明确的高风险边界：当前 2-DFF 是电平同步器，不是带确认的
脉冲传输协议；窄 token 可能在异步时钟比下漏采，多事件也可能合并。本轮只
修复 top contract、start/disable 传播和工具接受度，不宣称 CDC 功能完备。
在 handshake/toggle 方案、异步 clock-ratio 双仿真和 CDC sign-off 完成前，
该行保持 `Trusted boundary`。

## 2026-07-22 发布加固

### 深度审计修复（当前工作树，待远端证据）

- 七个组合模板的 `disabled_o` 改为直接反映外部 `disable_i`，并新增
  Icarus/Verilator 全契约回归。
- sequence `or` 新增左右不等长、早失败保持、晚通过/晚失败与 disable
  清状态测试；RTL 模板 mutation 从 5 个扩为 7 个并全部杀死。
- 差分参考模型完全移除对生产 `behavioral_oracle` 的导入，样本函数扩展到
  `$rose/$fell/$stable/$changed/$past`，固定延迟覆盖到 `##8`；当前生成器如实
  限定为一层时间算子，未再声称未实现的三层递归生成。
- 有效 mutation 审计发现并修复范围延迟 NFA 提前完成边越界：所有转换现在
  强制落在 `[0, states)`，`##[2:4]` 的最早/最晚退出边均进入真实接受态。
- push/PR CI 新增真实 branch coverage 与关键模块下限；nightly 同时保留固定
  历史 seed 和每日轮换 seed，失败时上传 sanitized replay artifact。
- GitHub Actions 固定到不可变 commit；Slang 11.0 与 Verilator 5.028 下载均
  校验 SHA-256；依赖安装全部使用冻结 lock。
- 包版本、`uv.lock`、支持文档和 BSL Licensed Work 已统一为 1.7.0，并有
  自动一致性测试。

最终 fresh 验证（Python 3.12）：完整 Icarus 轴 1428 passed / 1 skipped /
1 xfailed，branch coverage 86.29%；完整 Verilator simulation 轴 167 passed /
1 skipped；固定 seed `20260722` 的 slow differential 在 Icarus 与 Verilator
各 64 个生成例均通过；generated RTL synthesis + strict lint 107 passed；
Full Formal 125 passed / 1 xfailed。ruff、mypy strict、lock、工作流 YAML、
安装脚本语法与关键覆盖率下限均通过。所有上述命令 0 failed。未推送前仍无
current-commit 远端 Ubuntu/macOS、scheduled nightly 或 Full Formal 证据。

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

以下是第一次发布加固阶段的历史快照，不是当前工作树的最终数字；其中
mutation 数字来自旧 runner，包含后来被识别为无效或未覆盖的候选，不能与
当前 mutation 分数直接比较：1344 tests collected；Python 3.12 与 3.13 的完整本机
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

以下是 P1 提交形成时的历史快照，不是本轮深度审计后的最终数字；其中
mutation 数字来自旧 runner：ruff 全通过；mypy strict 15 个源码文件 0 error；
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
- 多时钟 CDC 与事件交付尚未闭环：当前 2-DFF 电平同步器可能漏采窄脉冲
  或合并连续事件，必须通过明确的 handshake/toggle 与速率/overflow 契约解决
- K-state budget (>32) 和 CDC 边界是 NFA 引擎仅存的拒绝路径
- 本机 Verilator 5.028 已安装并完成双 Python 版本 simulation、generated lint 与 differential；仍需同一提交的远端 Ubuntu/macOS CI 记录

## 未来规划

### 短期（发布加固闭环）

1. 推送 F-01 `libfl-dev` 修复并确认 Ubuntu Verilator 与 generated RTL job
   在同一 SHA 上实际执行通过。
2. 解除 GitHub payment/spending-limit 阻塞，在同一 SHA 上触发
   differential nightly 与 Full Formal。
3. 只有所有远端门控在同一 commit 上通过后，记录 run ID 并逐行重评
   `SUPPORT_MATRIX.md`；不得沿用历史 run 替代 current-commit 证据。
4. `v1.7.1` 已发布且 tag 不改写；发布资格证据应追加到新的修复 SHA，不能
   倒推声称 tag 本身已经通过后来才运行的门禁。

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
