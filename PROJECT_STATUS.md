# sva2verilog 项目进展报告

> 更新日期：2026-07-07
> 仓库：public GitHub repository
> 当前版本：v1.5.2 + current main hardening

## 当前状态

sva2verilog 是一个开源的 SystemVerilog Assertion (SVA) 到可综合 RTL 监控器编译器。项目已完成 v1.5.2 发布并推送到 GitHub。当前状态：

- 测试套件：1094 passed, 4 skipped, 1 xfailed, 0 failed
- 代码质量：mypy --strict 0 errors, ruff 0 errors
- 形式化验证：62 个非循环 BMC 等价证明（覆盖所有已支持算子）+ 5 个 Tier-A k-induction 完备证明
- 覆盖度：约 95%+ 的实际断言场景

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

CI workflow 已重新纳入版本控制，恢复 lint、8 轴仿真矩阵（`{ubuntu,macos} × {3.12,3.13} × {iverilog,verilator}`）和 formal job。formal job 覆盖全部形式化测试 + sby 安装。lint job mypy --strict 通过。

### k-induction 完备证明

新增 `tests/test_formal_kinduction.py`，对 `bool_expr`、`$rose`、`$fell`、`$stable`、`$changed` 5 个 Tier-A 核心监控器运行 SymbiYosys `prove` 模式（BMC basecase + induction step）。本轮修复 `$stable` / `$changed` reference 的反向错误，并收紧 xfail 判定：只有 induction 未收敛/超时才 xfail，真实 counterexample 必须失败。

### GitHub 发布

推送到公开 GitHub 仓库，干净历史（orphan branch），无私人身份或内部资料。

## 遇到的问题

1. first_match posedge bug：存在多版本未发现，因为该算子缺仿真和形式化测试。教训：每个算子必须有 RTL 编译验证 + 形式化等价。
2. mypy 49 errors：CI lint job 一直失败但未处理。教训：CI 红就必须立即修。
3. 形式化参考时序对齐：写 BMC miter 参考监控器时，寄存延迟必须与 RTL 模板精确对齐。5/6 新参考需要时序迭代。教训：时序对齐是形式化等价验证中最耗时的部分。
4. GitHub workflow scope：此前 OAuth token 缺 workflow scope，CI 文件无法推送。本轮 workflow 已进入本地提交，远端推送后需确认 Actions 的 Verilator 轴和 formal 轴实际绿灯。

## 验证体系

四层验证金字塔：

1. 行为预言机（950 单元测试）：纯 Python IEEE 模型，与 RTL 结构独立
2. iverilog/Verilator 仿真交叉验证（129 测试）：逐周期 pass/fail 比对
3. SymbiYosys BMC 形式化等价（62 证明）：独立 IEEE 1800 参考监控器 + sby BMC miter
4. SymbiYosys k-induction 完备证明（5 证明）：Tier-A 核心监控器的无界证明

RISK-01 纪律：预言机和参考监控器必须与 RTL 实现结构独立。曾两次发现被循环证明掩盖的真实缺陷（BUG-DELAY-01、BUG-IMPL-01）。

## 已知限制

- 1 xfail：`bool_expr` 叶子不独立产生 fail 的结构性见证，fail 语义来自蕴含父节点
- ##0 fusion 保留 +1；当前 main 对 boolean `##0` 发 warning，并建议用 `a && b` 替代。自动 rewrite/reject 仍是后续语义迁移工作
- 62 个全算子等价证明仍是 BMC 有界（depth=15-30）；k-induction 已覆盖 5 个 Tier-A 核心监控器，尚未扩展到全部算子
- 多时钟形式化等价永久排除（行业通用限制）
- NFA 仍拒绝：范围延迟操作数、intersect 内 SeqOr/goto/nonconsec

## 未来规划

### 短期（1-2 周）

1. 推送并确认远端 CI workflow，重点检查 Verilator 轴和 formal 轴
2. 代码覆盖率提升到 95%+（ast_importer 81.4%、composer 87.7%、behavioral_oracle 86.6%）
3. 嵌套 NFA BMC 深度从 15 增加到 25-30

### 中期（1-2 月）

4. 变异测试（mutmut）：验证测试套件区分力，目标变异杀死率 >85%
5. 差分测试框架：随机生成 SVA → 编译 → 仿真 → 比对，发现未知组合 bug
6. 扩展 k-induction：从 5 个 Tier-A 核心证明扩大到更多 BMC miter
7. v1.6 决策：单线程局部变量 / 多时钟×NFA / FPGA 原型（需求拉动）

### 长期

8. 社区采用：文档、示例、教程
9. 学术发表：DVCon 或会议论文（三层验证方法）
10. C++ 重写（v2）：大规模设计性能优化

## 风险登记册

所有已识别风险（RISK-00 至 RISK-06）均已闭环或降级。无新增风险。

## 竞争定位

sva2verilog 在"可综合 SVA 监控器"赛道（对标商用 emulator Palladium/ZeBu）覆盖约 95%+ 实际断言场景。开源世界几乎无对手，学术界唯一系统性同类是 MBAC（Boulé & Zilic）。永久边界：无界活性（理论不可综合）、CDC 结构验证（独立工具品类）、多线程局部变量（ROI 为负）。
