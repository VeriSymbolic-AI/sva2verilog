# sva2rtl 项目综合分析（2026-07-11）

> 证据截止时间：2026-07-11 19:04–19:11（Asia/Shanghai）
> 当前分支：`main`
> 当前 HEAD：`65c051d1a4aaa2acd45f3f1ac63b371ee0f7c535`
> 分析原则：当前命令与代码事实优先；历史记录只证明其记录时点；本地缺工具、skip 和未跟踪草稿均不等于通过。

## 执行摘要

sva2rtl 已经形成一条可工作的 SVA 到可综合 RTL 编译主链，并围绕 slang 真实源解析、冻结 IR、归一化、token/NFA 组合、优化、Jinja2 发射、Icarus 仿真、独立 Python behavioral oracle、SymbiYosys/Yosys 形式化与综合检查建立了多层验证体系。当前代码成熟度明显高于原型：本次从 HEAD 收集到 1321 个测试项；非 simulation、非慢差分套件为 `1146 passed, 31 skipped, 143 deselected, 1 xfailed`，Icarus simulation 为 `142 passed, 1 skipped`，专门的 BMC 文件为 `56 passed`，k-induction 为 `10 passed, 1 xfailed`，Yosys synthesis gate 为 `54 passed`，ruff 与 mypy strict 均通过。

但项目还不能据此宣称“工业完成”或“v1.7 已一致发布”。最严重的问题是发布身份分裂：HEAD 和 [v1.7 release notes](RELEASE-v1.7.0.md) 表明 v1.7 language-surface closure 已完成，而 [pyproject.toml](pyproject.toml)、[运行时版本](src/sva2rtl/__init__.py)、最新 Git tag、[PROJECT_STATUS.md](PROJECT_STATUS.md) 与 [SUPPORTED_CONSTRUCTS.md](SUPPORTED_CONSTRUCTS.md) 仍停留在 `1.5.2`；本次 `sva2rtl --version` 也输出 `1.5.2`。此外，本机没有 Verilator，因此当前 HEAD 的 dual-oracle parity、generated RTL Verilator lint 和 Verilator differential 均为“本次未验证”；仓库记录的远端绿灯来自 2026-07-08 的旧 commit `674cea1`，不能替代 HEAD `65c051d` 的远端证据。

[SUPPORT_MATRIX.md](SUPPORT_MATRIX.md) 是当前最接近权威的支持证据账本，但其主表仍是：`0` 个 Fully supported、`19` 个 Bounded evidence、`1` 个 Trusted boundary、`5` 个 Unsupported / rejected。结论应是：**核心实现和本地验证基线健康，v1.6/v1.7 功能工作基本落地；发布治理、HEAD 远端证据、逐构造证据闭环、真实设计/FPGA 反馈和规模性能基线仍未完成。** 下一步应先停止扩大支持声明，先统一版本与事实源，再为核心构造闭合 current-HEAD 证据，最后才按用户需求扩语言或考虑 C++ 重写。

## 分析范围与证据方法

### 证据等级

| 等级 | 定义 | 本报告用法 |
|---|---|---|
| 已由本次核验确认 | 2026-07-11 在当前工作树实际运行的 Git、测试、静态检查或工具命令 | 可作为 current local 事实，但不能自动外推到其他 OS、Python 或 Verilator |
| 仅由仓库文档记录 | 受跟踪文档或 CI YAML 中带 commit、日期或 run ID 的记录 | 作为 remote-recorded / historical，不等于本次重跑 |
| 尚未核验 | 缺少本机工具、网络、当前远端 run、真实硬件或独立复现实验 | 必须保留为 pending，不用旧数字填补 |
| 草稿线索 | 五个用户自有脏/未跟踪分析文件中的观点 | 只用于寻找候选问题；结论必须回到代码、Git 或本次命令复核 |

### 来源优先级与边界

1. 本次命令输出、当前 Git HEAD 和实际源代码。
2. 当前 HEAD 的受跟踪测试、[CI 配置](.github/workflows/ci.yml)和 [support matrix](SUPPORT_MATRIX.md)。
3. [PROJECT_STATUS.md](PROJECT_STATUS.md)、[SUPPORTED_CONSTRUCTS.md](SUPPORTED_CONSTRUCTS.md) 与 [v1.7 release notes](RELEASE-v1.7.0.md) 等受跟踪状态文档。
4. [.planning/STATE.md](.planning/STATE.md)、[.planning/ROADMAP.md](.planning/ROADMAP.md)、[.planning/PROJECT.md](.planning/PROJECT.md) 与 [.planning/REQUIREMENTS.md](.planning/REQUIREMENTS.md) 的历史里程碑声明。
5. `INDUSTRIAL_VALIDATION_GAPS.md` 和四个未跟踪分析草稿，仅作 secondary input；本任务用 SHA-256 前后校验保证不改动它们。

本报告没有联网查询 PyPI、GitHub Release 或最新 Actions 状态，因此不声明 v1.7 已发布到包仓库，也不声明 HEAD 已通过远端 CI。`uv build` 尝试因离线环境无法获取 `hatchling` 而失败，这只说明“本次未验证发行包”，不能推断包必然损坏或正常。

## 当前项目快照

| 维度 | 当前事实 | 证据等级 |
|---|---|---|
| 分支 / HEAD | `main` / `65c051d1a4aaa2acd45f3f1ac63b371ee0f7c535` | 已由本次核验确认 |
| 最近提交 | `65c051d release: v1.7 evidence chain closure and quality hardening`；前一 release commit 为 `217d82f release: v1.7.0 Language Surface Closure` | 已由本次核验确认 |
| 最新可见 tag | `v1.5.2`；HEAD 没有 point-at tag；`git describe` 为 `65c051d-dirty` | 已由本次核验确认 |
| 包 / 运行时版本 | [pyproject.toml](pyproject.toml) 与 [src/sva2rtl/__init__.py](src/sva2rtl/__init__.py) 均为 `1.5.2`；CLI 输出 `sva2rtl, version 1.5.2` | 已由本次核验确认 |
| 里程碑状态 | [.planning/STATE.md](.planning/STATE.md) 标记 v1.7、Phase 14–18 complete；[.planning/ROADMAP.md](.planning/ROADMAP.md) 仍以 v1.6 为主，Phase 8–13 complete | 文档记录，且存在代际漂移 |
| 代码规模 | `15` 个 `src/sva2rtl/*.py` 模块，共 `10678` 行；`33` 个 RTL Jinja2 templates | 已由本次核验确认 |
| 测试资产 | `71` 个 Python test 文件、`98` 个 `.sv` 文件、`3` 个 workflow 文件；收集 `1321` 项 | 已由本次核验确认 |
| 本地工具 | slang 11.0.0、Icarus 12.0、Yosys 0.66、SBY 0.65 可用；Verilator 缺失 | 已由本次核验确认 |
| 本地 Python | `uv run --no-sync python --version` 为 Python 3.12.4；宿主 `python3` 是 3.14.5，但本次项目命令使用 uv 环境 | 已由本次核验确认 |

### 当前本地验证结果

| 检查 | 结果 | 解释 |
|---|---|---|
| collection | `1321 tests collected in 1.77s` | 当前收集规模，不代表全部执行通过 |
| fast/non-simulation | `1146 passed, 31 skipped, 143 deselected, 1 xfailed` | 通过；排除了 simulation 与 `differential_slow` |
| Icarus simulation | `142 passed, 1 skipped, 1178 deselected` | 当前 Icarus backend 通过；1 skip 不算 pass |
| BMC 专项 | `56 passed` | [tests/test_formal_sva_equiv.py](tests/test_formal_sva_equiv.py) 当前本地通过 |
| k-induction 专项 | `10 passed, 1 xfailed` | xfail 是仍保留的边界，不应写成 11 passed |
| synthesis gate | `54 passed` | [tests/test_synthesis_gates.py](tests/test_synthesis_gates.py) 当前 Yosys 通过 |
| ruff | `All checks passed!` | 当前 `src/`、`tests/` 通过 |
| mypy strict | `Success: no issues found in 15 source files` | 当前 `src/` 通过 |
| Verilator | executable 缺失 | 本次未验证：simulation、generated lint、differential parity |
| wheel/sdist | 因离线无法解析 build-system 的 `hatchling` | 本次未验证：发行物内容和 clean-install smoke |

## 当前进展

### v1.6 证据链工作

- **仅由仓库文档记录：** [.planning/REQUIREMENTS.md](.planning/REQUIREMENTS.md) 将 v1.6 的 27 个 BASE/MATRIX/BOOL/FORMAL/SYNTH/DIFF requirements 全部标为 complete；[.planning/ROADMAP.md](.planning/ROADMAP.md) 将 Phase 8–13 标为 complete。
- **已由本次核验确认其实现仍在：** 当前仓库有 [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md)、structured boolean semantics、formal harness modes、Yosys synthesis gates、generated lint tests、source-level differential harness、coverage/mutation 配置和三条 CI workflow。
- **证据边界：** 本次没有逐条重新审计 27 个 requirement 的全部历史验收，也没有运行 mutation full sweep、Verilator 或远端矩阵；因此“27/27 complete”是规划账本状态，不等于本次重新完成 27 项独立验收。

### v1.7 language-surface closure

- **已由本次代码与测试核验确认：** [normalizer](src/sva2rtl/normalizer.py) 的 `_handle_fusion_delay` 会把 BoolExpr `a ##0 b` 重写为 `&&`，复杂 operand 会报错；[composer](src/sva2rtl/composer.py) 已包含 SeqOr、ranged delay/repetition、goto/nonconsecutive 的 NFA lift 路径和 `K <= 32` 预算防线。
- **仅由仓库文档记录：** [RELEASE-v1.7.0.md](RELEASE-v1.7.0.md) 把 LANG-01..04 标为完成，日期为 2026-07-10；[.planning/STATE.md](.planning/STATE.md) 将 Phase 14–18 标为 complete。
- **本次核验补强：** 1321 项收集、fast suite、Icarus simulation、56 个 BMC、10 个成功 k-induction 和 54 个 synthesis gate 与当前 HEAD 相容。

### 最新质量加固

HEAD `65c051d` 在 v1.7 release commit 之后增加了 31 个文件的证据链加固，包括 [differential nightly workflow](.github/workflows/differential-nightly.yml)、12 个 real-source fixture、[test_sv_fixture_e2e.py](tests/test_sv_fixture_e2e.py)、额外 k-induction、mutation runner 改进、slang v11 AST 兼容和 support matrix 更新。这个提交体现了正确的工程方向：把“实现了”推进到“有真实源、模拟、形式化、综合或明确拒绝证据”。

### 发布、tag 与包版本状态

当前只能确认“代码仓库内存在 v1.7 release notes 和 release-named commits”，不能确认“v1.7 一致发布”：

- `pyproject.toml`、运行时 `__version__` 和 CLI 仍是 `1.5.2`；
- 最新 tag 仍是 `v1.5.2`；
- [PROJECT_STATUS.md](PROJECT_STATUS.md) 与 [SUPPORTED_CONSTRUCTS.md](SUPPORTED_CONSTRUCTS.md) 标题仍称 `v1.5.2 current main`；
- 本次未联网验证 PyPI/GitHub Release，也未完成 clean wheel install smoke；
- 因此 v1.7 应视为“代码/里程碑已落地但 release identity 未闭环”，而不是已完成的可消费发布。

## 架构与实现现状

### 实际主链

| 阶段 | 当前实现 | 输出 / 责任 |
|---|---|---|
| Source → slang JSON | [frontend.py](src/sva2rtl/frontend.py) 调用 `slang --ast-json`，使用临时文件、60 秒 timeout、无 `shell=True` | elaborated AST JSON；slang 是明确的 parser trust boundary |
| JSON → IR | [ast_importer.py](src/sva2rtl/ast_importer.py) 遍历 assertion、named sequence、clock、operator AST | [ir.py](src/sva2rtl/ir.py) 中的冻结 dataclass SVA/Bool nodes |
| Normalize | [normalizer.py](src/sva2rtl/normalizer.py) bottom-up canonicalize、flatten、`[*1]`、`##0` rewrite/reject | 规范化 IR，避免 emitter 承担语言语义修补 |
| Compose | [composer.py](src/sva2rtl/composer.py) 把 IR 映射成 `CheckerNode` tree；简单算子用 token/template，复杂时序用 custom NFA lift/product | 标准 monitor interface、子模块依赖、NFA transitions/state budget |
| Optimize | [optimizer.py](src/sva2rtl/optimizer.py) 固定顺序执行 constant fold、concat merge、CSE、counter merge、dead node，最多两轮收敛 | 优化后的 CheckerNode tree |
| Emit | [emitter.py](src/sva2rtl/emitter.py) 用项目根目录 [templates](templates/) 渲染 SystemVerilog 或 Verilog-2001 | children-first 模块集合与最终 RTL |
| CLI orchestration | [cli.py](src/sva2rtl/cli.py) 串联 import-all、property filter、normalize、compose、optimize、emit，并提供 dump/verify 入口 | 用户可执行编译流程与错误码 |

### 验证旁路关系

- [behavioral_oracle.py](src/sva2rtl/behavioral_oracle.py) 独立按 tick 模拟 simple checker 和 hierarchy，structured boolean 通过 [bool_semantics.py](src/sva2rtl/bool_semantics.py) 求值；它是差分验证的重要 oracle，但与实现共享 IR/部分序列化格式，仍需 formal reference 与真实 simulator 防止共同盲点。
- [formal_equiv.py](src/sva2rtl/formal_equiv.py) 构造 BMC/k-induction harness，支持 start/disable/reset/contract modes；[formal.py](src/sva2rtl/formal.py) 验证优化前后 RTL。
- [tests/simulation](tests/simulation/) 通过 Icarus 或 Verilator backend 比较动态时序；项目的 dual-oracle contract 要求两者均通过，不能用一端替代另一端。
- [tests/test_synthesis_gates.py](tests/test_synthesis_gates.py) 用 Yosys 对 generated RTL 做 read/hierarchy/proc/opt/check/synth smoke；[tests/test_generated_lint.py](tests/test_generated_lint.py) 为 Verilator lint gate。
- [ci.yml](.github/workflows/ci.yml) 包含 OS × Python × simulator 矩阵、generated RTL 和 formal smoke；[formal-full.yml](.github/workflows/formal-full.yml) 周期/手工跑完整 formal shards；[differential-nightly.yml](.github/workflows/differential-nightly.yml) 配置 Icarus slow sweep、Verilator differential 和部分 full mutation。

### 架构优势

1. **语义层次明确。** parser、IR、normalize、compose、optimize、emit 分离，错误可以在比 RTL 更高的层次被诚实拒绝。
2. **冻结 IR 与结构哈希。** frozen dataclass 和 CheckerNode structural hash 适合 CSE、可重复生成与测试。
3. **验证不只依赖同构 golden。** behavioral、formal、simulator、synthesis、negative tests 形成多条证据链，历史上也确实暴露过时序/语义问题。
4. **边界显式化。** K-state、CDC、unbounded liveness、local variables 等不是静默降级，而是有 rejection/trusted-boundary 设计。
5. **模板可审阅。** RTL 结构在 [templates](templates/) 中独立存在，便于 RTL 工程师审查 wire/logic、端口和状态机。

### 耦合热点与维护债务

- [composer.py](src/sva2rtl/composer.py) 2828 行、[ast_importer.py](src/sva2rtl/ast_importer.py) 1860 行、[behavioral_oracle.py](src/sva2rtl/behavioral_oracle.py) 1572 行；三者合计 6260 行，是语义扩展、错误处理和回归风险最集中的区域。应先按 operator family / NFA algebra / harness adapter 提取内部边界，再谈语言扩展。
- importer 用 module-level `_DECLARATIONS` 缓存，并注明 single-threaded compiler；当前 CLI 串行下可接受，但若未来并行编译多文件，需改为显式 import context，避免共享状态污染。
- [README.md](README.md) 把 optimize 描述成 “DFA minimization (Hopcroft)” 并称 `--no-optimize` 跳过 DFA minimization；实际 [optimizer.py](src/sva2rtl/optimizer.py) 没有 Hopcroft，依赖中也没有 AGENTS stack 所写的 `automata-lib`/`networkx`。这是“旧架构设想污染当前事实”的具体例子。
- [normalizer.py](src/sva2rtl/normalizer.py) 文件顶部 docstring 仍描述 `##0 warning` 和 `+1 cycle separation`，而实现已 rewrite/reject；注释债务会误导维护者。
- emitter 首选仓库根目录 [templates](templates/)，fallback 才是 package 内 `templates`；本次因离线无法构建 wheel，尚未证明 wheel 中模板被正确打包。发布前必须用 clean artifact smoke 验证，不能仅以 editable checkout 测试替代。

## 支持范围与验证证据

### 权威边界

[SUPPORT_MATRIX.md](SUPPORT_MATRIX.md) 应继续作为构造级权威账本。对其 Main Matrix 本次直接统计：

| 状态 | 行数 | 当前含义 |
|---|---:|---|
| Fully supported | 0 | 尚无构造完成 matrix 定义的完整证据链 |
| Bounded evidence | 19 | 有实现和多类证据，但缺 real-source、current Verilator、formal depth、lint/synthesis 或全契约中的至少一环 |
| Trusted boundary | 1 | multi-clock path-one 的 2-DFF synchronizer；CDC/metastability 不在本项目证明域 |
| Unsupported / rejected | 5 | ranged goto、ranged nonconsecutive、超 K/CDC NFA、unbounded liveness、local variables/unsupported system functions 等明确拒绝域 |

这里的 0 Fully supported 与“README 列出很多 supported constructs”并不矛盾：前者是证据成熟度，后者是语言实现概览。对外沟通必须同时给出 subset boundary 和 evidence status，不能把“可编译”写成“工业级完整证明”。

### 已有证据

- **real-source：** 测试树中有 98 个 `.sv` 文件；support matrix 已列出 core delay/implication、repetition、sampled-value、first_match、disable iff、named sequence 等真实源证据。
- **Icarus：** 本次 simulation marker 142 passed；这是 current local 的正证据。
- **Verilator：** 仓库记录 CI run `28931676000` 在 commit `674cea1` 上通过 matrix；这是 remote-recorded historical。当前 HEAD 本地无 Verilator，且 tracked docs 没有记录 `65c051d` 的对应 run，因此 current-HEAD parity 尚未核验。
- **BMC / k-induction：** 本次 BMC 专项 56 passed；k-induction 10 passed、1 xfailed。BMC 是有界证据，k-induction 也只覆盖列出的 targets；二者都不能自动扩张为所有构造/所有参数的无界证明。
- **Yosys / lint：** 本次 Yosys synthesis 54 passed；Verilator generated lint 本次未验证。
- **differential / mutation：** harness、nightly YAML 和 mutation runner 已存在；本次没有运行 `differential_slow`、Verilator differential 或 mutation full sweep。草稿中记录的 mutation 比例不升级为本次事实。

### 必须保留的边界

- `K > 32` 的 NFA 组合拒绝是规模/资源防线，不能为扩大语法覆盖而绕过。
- multi-clock path-one 只信任同步器结构；没有 CDC/metastability proof，也没有本次动态 clock-ratio/FPGA 证据。
- unbounded liveness / infinite-state forms 不应伪装为有限可综合 monitor；继续明确拒绝。
- local variables、ranged `[->M:N]`/`[=M:N]` 和未支持 system functions 属需求驱动扩展，不是当前 release blocker，前提是诊断稳定且有 negative tests。
- named sequence、sequence `and/or`、property `not/if...else`、bounded liveness 和复杂 NFA rows 仍有 matrix 明示的 formal 或 real-source/remote 缺口，不应整体升级为 Fully supported。

## 文档冲突与陈旧声明

| 主题 | 当前证据 | 冲突来源 | 建议权威源 |
|---|---|---|---|
| v1.7 vs 1.5.2 | HEAD 有 v1.7 commits/notes，STATE 为 v1.7；但 package/runtime/CLI/tag 都是 1.5.2 | [RELEASE-v1.7.0.md](RELEASE-v1.7.0.md)、[.planning/STATE.md](.planning/STATE.md) vs [pyproject.toml](pyproject.toml)、[src/sva2rtl/__init__.py](src/sva2rtl/__init__.py)、Git tag、[PROJECT_STATUS.md](PROJECT_STATUS.md)、[SUPPORTED_CONSTRUCTS.md](SUPPORTED_CONSTRUCTS.md) | 发布后以 `pyproject.toml` + generated runtime version + signed/tagged release manifest 为机器权威；release notes 由同一发布命令生成/校验 |
| 里程碑漂移 | STATE 已到 v1.7 Phase 18 complete；ROADMAP/PROJECT/REQUIREMENTS 仍主要描述 v1.6 | [.planning/STATE.md](.planning/STATE.md) vs [.planning/ROADMAP.md](.planning/ROADMAP.md)、[.planning/PROJECT.md](.planning/PROJECT.md)、[.planning/REQUIREMENTS.md](.planning/REQUIREMENTS.md) | 每个 milestone 单独归档；顶层 STATE 只链接 active milestone 和完成 manifest |
| 历史测试数字 | release notes 为 905/6，STATE 写 1070/31，本次为 1321 collected、fast 1146/31/1 xfail | [RELEASE-v1.7.0.md](RELEASE-v1.7.0.md)、[.planning/STATE.md](.planning/STATE.md)、多个草稿 | 只在带 commit、命令、marker expression、simulator 和日期的 evidence manifest 中写数字 |
| support 状态 | README 以“Supported”概览列构造；matrix 明确 0 Fully supported、19 Bounded | [README.md](README.md) vs [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md) | `SUPPORT_MATRIX.md` 是构造边界和证据成熟度唯一权威；README 只链接和摘要 |
| optimizer 架构 | 代码为 5 个 CheckerNode passes；无 Hopcroft/automata-lib/networkx | [optimizer.py](src/sva2rtl/optimizer.py)、[pyproject.toml](pyproject.toml) vs [README.md](README.md)、[AGENTS.md](AGENTS.md) | 从代码自动生成/校验 architecture inventory；研究设想单列为 proposed |
| `##0` 语义 | 实现为 BoolExpr rewrite、复杂 operand reject | [normalizer.py](src/sva2rtl/normalizer.py) 实现 vs 同文件顶部旧 docstring | 实现 + regression tests 为事实；docstring 与 release notes 同步校验 |
| remote evidence | 旧 run `28931676000` 只覆盖 `674cea1`；HEAD 为 `65c051d` | [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md) 的 baseline ledger vs 当前 Git | 每次 release 生成 HEAD-pinned CI evidence manifest，包含 run URL/job conclusion/tool versions |

## 主要问题与风险

| 优先级 | 问题 | 证据位置 | 影响 | 建议动作 | 可测退出标准 |
|---|---|---|---|---|---|
| P0 | 发布身份不一致：v1.7 代码/文档与 1.5.2 package/runtime/tag 分裂 | [pyproject.toml](pyproject.toml)、[src/sva2rtl/__init__.py](src/sva2rtl/__init__.py)、[RELEASE-v1.7.0.md](RELEASE-v1.7.0.md)、Git tag | 用户无法判断安装到的版本和支持边界；release notes 不可追溯到发行物 | 选择真实版本；同步 package/runtime/docs；构建 sdist/wheel；从 clean env 安装并跑 CLI + fixture smoke；再创建 tag/release | 单一版本检查脚本全绿；wheel metadata、`sva2rtl --version`、tag、release title 相同；tag 指向通过 CI 的 commit；clean-install fixture 可生成 RTL |
| P0 | 当前 HEAD 没有已记录的 dual-oracle/remote release evidence | 本次 Verilator missing；[SUPPORT_MATRIX.md](SUPPORT_MATRIX.md) 只记录 `674cea1` run；HEAD 为 `65c051d` | current local green 不能证明 Verilator、OS/Python matrix 或 remote lint | 在 HEAD 或 release candidate 上运行完整 [ci.yml](.github/workflows/ci.yml)、[formal-full.yml](.github/workflows/formal-full.yml) 与必要 nightly；固化 run IDs | release commit 的 Icarus/Verilator 轴、generated RTL、formal shards 全部 conclusion=success；无 unexpected skip；manifest 可由 SHA 校验 |
| P1 | 支持声明超过证据成熟度，0 个 matrix row 为 Fully supported | [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md) Main Matrix / Downgrade Summary | “支持”容易被外部理解为全链路工业验证；复杂构造风险被平均化 | 选 5–8 个核心 construct profiles，逐 row 补 current real-source、双 simulator、oracle、formal classification、Yosys/lint 和 negative tests | 目标 rows 的所有 required cells 为 present/current；reviewer 能从 row 复现；只有达标 row 升级 Fully supported |
| P1 | 发行物可安装性与模板打包本次未验证 | [emitter.py](src/sva2rtl/emitter.py) 使用根 [templates](templates/)；`uv build` 因离线 hatchling 获取失败 | editable checkout 通过但 wheel 可能漏模板；`pip install sva2rtl` 的核心路径存在发布风险 | 在联网 CI 先 build artifact，再建立完全隔离的 wheel install test，枚举 template resources 并编译 real `.sv` | wheel 内容包含全部 required templates；无仓库源码目录时 CLI 编译/emit/Verilog mode 通过；artifact smoke 为 release required job |
| P1 | formal/differential 深度仍是分片和有界证据 | [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md)、[formal-full.yml](.github/workflows/formal-full.yml)、[differential-nightly.yml](.github/workflows/differential-nightly.yml) | 参数组合、NFA 嵌套、disable/reset/start 交互仍可能有状态空间盲区 | 建立 construct × mode × parameter coverage map；增加 metamorphic/differential seeds、失败最小化与 current Verilator replay；优先历史 bug families | 每个 core row 有明确 proof class/depth；nightly 两 backend 有非零执行；失败自动保存最小 regression；连续 N 次无 infrastructure skip |
| P1 | 文档没有单一事实源，且当前文件内也有陈旧实现描述 | [README.md](README.md)、[normalizer.py](src/sva2rtl/normalizer.py)、[.planning](.planning/) | 维护者和用户会基于错误架构/测试数字决策 | 定义 version/support/evidence/milestone 四类 authority；从 manifest 生成 README/release 状态片段；CI 加 drift checks | CI 能检测版本、tag、test manifest、support link 和 architecture pass list 漂移；无手写重复精确数字 |
| P2 | semantic hotspots 规模大、共享状态限制未来并发 | [composer.py](src/sva2rtl/composer.py)、[ast_importer.py](src/sva2rtl/ast_importer.py)、[behavioral_oracle.py](src/sva2rtl/behavioral_oracle.py) | 新 operator 容易跨 importer/composer/oracle/formal 多点修改；并行编译可能受 `_DECLARATIONS` 共享状态影响 | 先做 characterization tests；逐步提取 ImportContext、NFA algebra、operator registry 和 oracle adapters，不做一次性重写 | 行为/RTL golden 不变；各模块依赖方向单向；并行多文件隔离测试通过；热点复杂度/变更扇出下降 |
| P2 | 缺少真实设计、FPGA 和规模性能基线 | [.planning/REQUIREMENTS.md](.planning/REQUIREMENTS.md) 的 FUT-03/FUT-04；matrix multi-clock boundary | 单元/形式化通过不等于时序收敛、面积可控或真实用户可用；无法判断 C++ rewrite 是否必要 | 建立开源 design corpus、FPGA prototype、compile/runtime/RTL area/fmax benchmarks 和用户反馈闭环 | 至少 2 个非玩具设计端到端；记录 compile time、peak RSS、RTL cells、fmax、资源增长；形成可复现 baseline 和 regression threshold |
| P2 | 开源采用与贡献门槛尚未被当前证据证明 | [README.md](README.md) 主要覆盖安装/CLI，缺少证据贡献和 release reproduction 流程 | 外部贡献者难以补 operator evidence，项目容易依赖单一维护者 | 增加 CONTRIBUTING、operator evidence checklist、最小新构造模板、troubleshooting 和可复现 release guide | 新贡献者按文档可新增一个 fixture + matrix row + dual-backend test；CI 在文档步骤下可复现；issue templates 收集真实需求 |

本表没有把未跟踪草稿中的市场占有率、竞争格局或“全部遗留问题完成”升级为确定事实。它们若要进入项目声明，需要外部来源或 current executable evidence。

## 未来建议与分阶段路线图

### 决策原则与依赖顺序

**先停止扩大声明 → 再统一发布与事实源 → 再闭合 current-HEAD 证据 → 再用真实设计验证价值 → 最后按需求扩语言或重写。**

依赖顺序如下：

1. Release identity 和 artifact smoke 是所有外部验证的输入。
2. HEAD-pinned CI/evidence manifest 是 support row 升级的前置条件。
3. Core rows 闭环后，真实设计/FPGA 才能给出可信的面积、时序和采用反馈。
4. 性能基线证明 Python 确实成为瓶颈后，才评估 C++ rewrite；不能因“可能更快”提前重写。

### 近期：发布与事实源治理、证据闭环（建议 1–2 个迭代）

| 工作 | 目标 | 前置条件 | 交付物 | 验证方式 | 退出标准 |
|---|---|---|---|---|---|
| R1 版本/发行物收敛 | 明确 1.5.2、1.7.0 与下一 RC 的真实关系 | maintainer 决定是否补发 1.7.0 或升补丁版 | version policy、同步版本、artifact、tag/release checklist | clean wheel install + CLI/fixture smoke | 版本四点一致，artifact job 必过 |
| R2 evidence manifest | 把测试数字从散文移入 SHA-pinned 机器记录 | R1 release candidate | JSON/Markdown manifest：commit、commands、tools、runs、skips | CI 生成并校验 schema | 每个 release claim 可定位到 run/job/tool version |
| R3 current HEAD dual-oracle | 关闭本机无 Verilator 的证据缺口 | RC commit 固定 | Icarus/Verilator matrix + generated lint + differential result | GitHub Actions/current Verilator host | 两 backend 对相同 simulation corpus 全绿；unexpected skip=0 |
| R4 core support profiles | 从 0 Fully supported 推进一组高价值 rows | R2/R3 | 5–8 个 construct profile 的完整 matrix cells | row-by-row review/replay | 每 row 满足 matrix 定义，缺口不能用 N/A 隐藏 |
| R5 文档 drift gate | 消除版本、架构、测试数字漂移 | R2 | authority map、generated snippets、CI checks | 故意制造 drift，测试必须失败 | README/notes/STATE 不再手工重复无来源数字 |

### 中期：正式验证、差分、FPGA 原型与用户反馈（建议 2–4 个迭代）

| 工作 | 目标 | 前置条件 | 交付物 | 验证方式 | 退出标准 |
|---|---|---|---|---|---|
| M1 formal coverage map | 将“56 BMC/10 induction”转成构造/模式覆盖模型 | core profiles 稳定 | construct × start/reset/disable/overflow × proof class 表 | automated report + missing-cell fail | 每个核心构造有显式 proven/bounded/trusted classification |
| M2 differential campaign | 扩大组合空间并保证可复现 | dual backend 稳定 | seeded nightly、metamorphic cases、minimized regression corpus | Icarus + Verilator + oracle 三方比较 | nightly 非零执行、失败自动最小化、历史 bug seeds 永久保留 |
| M3 FPGA/真实设计 prototype | 证明可综合、面积/时序和集成价值 | artifact 和 core profiles 稳定 | board design、monitor insertion flow、2+ design corpus | synth/P&R/on-board trace 与 reference 对比 | 资源/fmax/功能结果公开可复现；已知 CDC 边界显式列出 |
| M4 performance baseline | 为优化和 v2 决策提供数据 | design corpus | compile time/RSS/RTL size/state count benchmark dashboard | pinned host + regression thresholds | 可定位热点；性能回归自动报警；无数据不立 C++ 项目 |
| M5 community feedback loop | 用真实需求决定 local variables、ranged repetition、multi-clock×NFA | 可安装 release | contribution guide、support request template、sample gallery | 首次外部复现/issue/PR | 至少若干真实 properties 被归类为 supported/rejected/gap，并进入 roadmap |

### 需求驱动长期：语言扩展与可能的 C++ rewrite

| 候选 | 启动条件 | 建议策略 | 完成定义 |
|---|---|---|---|
| single-thread local variables | 多个真实设计给出不能用现有 subset 表达的最小案例 | 先限定 single-thread、静态类型/有限宽度 subset；从 slang IR 到 formal/differential 一次闭环 | 独立语义、negative boundary、dual backend、formal classification、synthesis 全齐 |
| multi-clock × NFA | 真实 CDC use case 且 system-level ownership 明确 | 保持 synchronizer/CDC trust boundary，不把结构检查包装成 metastability proof | 动态 clock-ratio tests、CDC tool report、FPGA evidence、边界文档 |
| ranged `[->M:N]` / `[=M:N]` | 用户价值高于状态/面积复杂度 | 先 reference semantics 和 state-budget cost model，再实现 | 不再下界折叠；全链路证据和面积上限明确 |
| C++ rewrite | benchmark 显示 Python 在目标 workload 上持续违反已同意 SLO，且 profile 指向可重写核心 | 优先 FFI/局部热点原型；保留 slang JSON contract 与 Python reference oracle；逐算子 differential migration | 输出 byte/semantic parity、全 evidence suite、明确倍数收益、维护成本可接受；否则停止 |

## 项目完成定义

“测试全绿”只是必要条件，不是工业完成标准。建议 release/industrial readiness 同时满足：

1. **版本发布一致性：** package metadata、runtime、CLI、tag、release notes 和 support manifest 完全一致；artifact 可从 clean environment 安装。
2. **逐构造证据：** 每个对外支持的 construct profile 有真实 `.sv`、正常 pipeline、Icarus、Verilator、独立 behavioral/reference、formal classification、Yosys/lint 和 unsupported negative tests；缺项则明确 Bounded。
3. **dual-oracle contract：** 两 simulator 对同一 simulation/differential corpus 均执行且通过；没有因缺工具造成的意外 skip。
4. **形式化诚实性：** 每项标明 BMC depth、k-induction target 或 trusted/excluded boundary；cover 不能冒充 proof，BMC 不能冒充无界证明。
5. **综合与发行物可重复：** generated RTL 可被 Yosys/Verilator lint；wheel 安装后无需仓库根目录即可找到 templates 并生成 SV/V2001。
6. **拒绝边界稳定：** K-state、CDC、unbounded liveness、local-variable 等边界有明确错误码、source location、workaround 和 regression tests。
7. **文档一致性：** support matrix 是支持权威；evidence manifest 是测试数字权威；STATE/ROADMAP 指向单一 active milestone；CI 可检测 drift。
8. **真实环境验证：** 至少两个非玩具设计和一个 FPGA/原型流程证明集成、面积、时序与运行行为；multi-clock 声明经过适当 CDC 工具/边界审查。
9. **性能基线：** compile time、peak memory、generated modules/cells/state count 有版本化基线和 regression threshold；重写由数据触发。
10. **可维护与可贡献：** hotspot 有明确内部 API/characterization tests；外部贡献者能按文档复现 release、补一个 construct evidence row 并通过 CI。

当且仅当目标 release 的所有必选 profile 达到上述定义，才应使用“工业级完成/fully supported”；其他情况继续使用“bounded evidence”“trusted boundary”或“unsupported/rejected”。

## 附录：证据与复现命令

### 本次实际运行的关键命令

采集窗口：2026-07-11 19:04–19:11（Asia/Shanghai），HEAD `65c051d1a4aaa2acd45f3f1ac63b371ee0f7c535`。

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git log -8 --date=iso-strict --pretty=format:'%h%x09%ad%x09%s'
git tag --sort=-version:refname
git tag --points-at HEAD
git describe --tags --always --dirty

rg --files src/sva2rtl -g '*.py'
rg --files templates -g '*.j2'
rg --files tests -g '*.py'
rg --files tests -g '*.sv'
rg --files .github/workflows

UV_CACHE_DIR=.uv-cache uv run --no-sync pytest --collect-only -q
UV_CACHE_DIR=.uv-cache uv run --no-sync pytest -q -m 'not simulation and not differential_slow' --timeout=120
UV_CACHE_DIR=.uv-cache uv run --no-sync pytest -q -m simulation --simulator=iverilog --timeout=120
UV_CACHE_DIR=.uv-cache uv run --no-sync pytest -q tests/test_formal_sva_equiv.py --timeout=120
UV_CACHE_DIR=.uv-cache uv run --no-sync pytest -q tests/test_formal_kinduction.py --timeout=120
UV_CACHE_DIR=.uv-cache uv run --no-sync pytest -q tests/test_synthesis_gates.py --timeout=120
UV_CACHE_DIR=.uv-cache uv run --no-sync ruff check src/ tests/
UV_CACHE_DIR=.uv-cache uv run --no-sync mypy --strict src/
UV_CACHE_DIR=.uv-cache uv run --no-sync sva2rtl --version

command -v slang iverilog verilator yosys sby
slang --version
iverilog -V
yosys -V
sby --version

UV_CACHE_DIR=.uv-cache uv build --out-dir /tmp/260711-qbb-dist
```

最后一条 build 命令因离线环境无法从 PyPI 解析 `hatchling` 而失败；它被记录为“本次未验证”，不是项目 test failure，也不是 artifact pass。

### 结果摘要

```text
collection:       1321 collected
fast/local:       1146 passed, 31 skipped, 143 deselected, 1 xfailed
Icarus simulation:142 passed, 1 skipped, 1178 deselected
formal BMC file:  56 passed
k-induction file: 10 passed, 1 xfailed
Yosys synthesis:  54 passed
ruff:             all checks passed
mypy --strict:    no issues in 15 source files
Verilator:        MISSING — current local evidence unavailable
artifact build:   NOT VERIFIED — offline hatchling resolution failure
```

### 工具可用性

| 工具 | 本次状态 | 版本 / 备注 |
|---|---|---|
| uv | available | 0.10.12 |
| project Python | available | 3.12.4 |
| slang | available | 11.0.0+7ddf405 |
| Icarus | available | 12.0 stable |
| Verilator | missing | 本次所有 Verilator 结论均未验证 |
| Yosys | available | 0.66 |
| SBY | available | 0.65 |

### 关键来源

- 支持边界与证据状态：[SUPPORT_MATRIX.md](SUPPORT_MATRIX.md)
- 当前代码里程碑：[.planning/STATE.md](.planning/STATE.md)
- v1.6 路线与需求：[.planning/ROADMAP.md](.planning/ROADMAP.md)、[.planning/REQUIREMENTS.md](.planning/REQUIREMENTS.md)、[.planning/PROJECT.md](.planning/PROJECT.md)
- v1.7 变更记录：[RELEASE-v1.7.0.md](RELEASE-v1.7.0.md)
- 包版本与质量配置：[pyproject.toml](pyproject.toml)、[src/sva2rtl/__init__.py](src/sva2rtl/__init__.py)
- 编译主链：[frontend.py](src/sva2rtl/frontend.py)、[ast_importer.py](src/sva2rtl/ast_importer.py)、[ir.py](src/sva2rtl/ir.py)、[normalizer.py](src/sva2rtl/normalizer.py)、[composer.py](src/sva2rtl/composer.py)、[optimizer.py](src/sva2rtl/optimizer.py)、[emitter.py](src/sva2rtl/emitter.py)
- 独立/旁路验证：[behavioral_oracle.py](src/sva2rtl/behavioral_oracle.py)、[formal_equiv.py](src/sva2rtl/formal_equiv.py)、[tests/simulation](tests/simulation/)、[ci.yml](.github/workflows/ci.yml)、[formal-full.yml](.github/workflows/formal-full.yml)、[differential-nightly.yml](.github/workflows/differential-nightly.yml)
