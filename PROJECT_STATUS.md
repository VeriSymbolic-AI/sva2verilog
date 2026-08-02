# sva2verilog 项目进展报告

> 更新日期：2026-08-02
> 仓库：public GitHub repository
> 当前版本：v1.7.1

## 当前状态

sva2verilog 是一个开源的 SystemVerilog Assertion (SVA) 到可综合 RTL
监控器编译器。v1.7.1 已于 2026-07-31 发布，修复了 v1.7.0 的完整契约语义
缺陷。发布后的首个可执行代码与工作流基线 `b055105` 已完成同提交远端资格
闭环；后续高优先级加固与 F-11 真实工程 frontend 远端基线已经推进到
`de3f697`。本地候选 `92a3b5a` 又关闭了 F-15/F-16/F-18/F-19，但尚未获准
推送，因此不能将 `de3f697` 的远端运行倒推为该候选的证明。后续纯文档提交
也只记录可执行基线，不把文档 SHA 倒推为新的证明对象。

- 发布状态：tag `v1.7.1` 指向 `8b5c063`；发布后资格基线为 `b055105`
- 当前许可证：Apache License 2.0（SPDX：`Apache-2.0`）；根目录
  `LICENSE`、README 与包元数据保持一致
- 主 CI：run `30683023280` 全部 13 个 job 通过，包括 8 个
  `{ubuntu,macos} × {3.12,3.13} × {iverilog,verilator}` 仿真轴、generated
  RTL、formal smoke、coverage、lint、Python 3.14 与仓库外安装包验证
- F-01 已远端关闭：两个 Ubuntu Verilator 轴及 generated RTL job 均越过
  `FlexLexer.h` 探针并实际完成测试，证明 `libfl-dev` 修复有效
- Full Formal：run `30683026438` 的 6 个分片全部通过；这是一组针对
  `b055105` 的远端完整工作流证据，不等同于对所有语言构造的无界证明
- nightly differential：run `30683026683` 的 Icarus、Verilator 与完整
  mutation 三个 job 全部通过；干净 checkout 暴露的 `.artifacts` 父目录
  缺失问题已先由回归测试复现，再在同一基线中修复并远端验证
- 最新同提交资格：`1841ed4` 的主 CI run `30686814681` 全部 13 个 job
  通过；nightly run `30686818970` 的三个 job 通过；Full Formal run
  `30686820029` 的六个分片通过。该组运行实际使用 Node.js 24 actions，
  并覆盖最新 CDC 注入、oracle mutation 与测试隔离修复
- 最新本地候选：`92a3b5a`；完整 Icarus 1579 passed / 1 skipped /
  1 个动态分类的 bounded-liveness xfail，完整 Verilator simulation 174
  passed / 1 个已审查 skip，branch coverage 88.12%，generated RTL 133
  passed，Full Formal 126 passed / 1 个相同 xfail；ruff 与 strict mypy 通过
- 变异与差分：候选的四个 Python mutation 面为 317/317（100%，另有 32 个
  未覆盖候选不进入分母）、RTL template mutation 12/12；Icarus/Verilator
  fixed-seed fast 各 16 passed，date-seeded slow 各 1 passed。远端基线
  `de3f697` 的同提交 CI
  run `30709818712` 13/13、nightly run `30709827239` 3/3、Full Formal
  run `30709832382` 6/6 全部通过；`92a3b5a` 尚无远端证据
- 支持状态权威：`SUPPORT_MATRIX.md` 记录逐构造支持边界、证据完整度和降级原因；README / SUPPORTED_CONSTRUCTS 只作概览和解释
- 工业级验证缺口：已记录在 `INDUSTRIAL_VALIDATION_GAPS.md`，包含当前进展、P0/P1/P2 严重度、修复计划和 fully-supported 定义标准

## 2026-08-02 F-15/F-16/F-18/F-19 可信度闭环（本地候选）

- F-15：移除 k-induction 整类测试的 blanket xfail。只有日志同时表明
  basecase 通过、induction 未收敛或超时才动态 xfail；basecase 反例、普通
  counterexample 和工具错误全部硬失败。CI 与 Full Formal 的 JUnit 门禁只
  白名单该精确原因。
- F-16：三条 GitHub Actions workflow 的 10 个 `setup-uv` 入口均显式固定
  uv 0.12.1，避免 action 固定而运行时 CLI 漂移。
- F-18：为 slang v11 标签传递、属性运算符分派、NFA 路由和 disable 归一化
  增加 mutation-sensitive 回归，并删除合法输入域内不可观察的重复判断。
  四模块当前覆盖有效突变为 16/16、135/135、51/51、115/115。
- F-19：新增两套版本化小型 project corpus，覆盖参数专化与 library
  directory/extension 解析；参数项目同时保存手工推导的 cycle-exact 期望
  trace，RTL 必须先匹配源语义真值，再与 Python oracle 比较。
- 本地 Full Formal 为 126 passed + 1 个受控边界，证明分类单元测试 5/5；
  该结果仍是有界、按 harness/assumption/tool 列明的证据，不是芯片正确性或
  所有 SVA 构造完备性的证明。

## 2026-08-02 F-11 真实工程 frontend 闭环

- `dfe35bb` 新增不可变 `SlangCompilationContext` 与结构化 CLI：多源文件、
  `-F` filelist、`-I` include、`-D` define、top、`-G` parameter、library
  file/directory/extension/order 和 single-unit 均经类型、路径、标识符与控制
  字符校验后以 argv 传递；不提供任意 `--slang-arg`，也不使用 shell。
- slang 超时、缺失/畸形 AST 均转为明确编译错误；编译器自有的
  `--ast-json` 参数最后追加，不能被调用方覆盖。
- importer 递归进入 elaborated `InstanceBody`，按实例体维护声明上下文并
  去重缓存体；两态 parameter 常量折叠为 IR 常量，不再被错误暴露为运行时
  monitor 输入；四态 X/Z 继续 fail-closed。
- `de3f697` 增加双 oracle 真实项目回归：用 filelist/include/define/top/`-G`
  编译嵌套实例，完成 import → compose → optimize → emit，并在 Icarus 和
  Verilator 上将 `active/pass/fail` 与独立 behavioral oracle 逐周期比较。

F-11 的“缺少结构化项目上下文”已关闭，但这不是工业工程兼容性证明。
filelist 内容仍是可信编译配置；escaped identifier、同标签的多参数化实例、
复杂 library 解析冲突、工具专属参数和大型真实项目 corpus 尚未覆盖。

## 2026-08-01 深度审查后续高优先级修复

本轮以“是否仍可能出现不可置信 PASS、静默丢失或验证门禁空绿”为判断标准，
继续关闭了五组问题：

- `9a240bd`：NFA 接受线程及时释放；死亡 attempt 只失败一次；满槽新请求不再
  静默丢弃，而是置位 sticky `overflow_flag` 并 fail-closed。
- `eba6e12`：sampled-value 函数仅接受普通标量标识符，向量、选择表达式、
  复杂表达式、可选 sampled 参数和非法 `$past` 深度均明确拒绝；保留端口名
  通过确定性 `dut_*` 别名隔离。
- `3e7f9e8`：行为预言机在层次入口统一处理 `disable_i`，递归清空叶子和组合
  状态，避免外部 disable 后旧状态泄漏到新 attempt。
- `253137c`：CI 通过/跳过预算按真实隔离环境校准，skip 原因采用白名单；
  未知原因导致门禁失败，Formal 选择由显式 marker 保证可审计。
- `79db15d`：新增语义路由、状态保持、层次 implication、NFA 分配和多时钟
  边沿等 mutation-sensitive 回归；四个模块分别执行 100%/95%/90%/86%
  的独立变异下限，禁止总分掩盖单模块薄弱。

完整本地证据采集于可执行提交 `79db15d`：Icarus 1535 passed / 1 skipped /
1 xfailed；Verilator 173 passed / 1 backend-specific skipped；Full Formal
126 passed / 1 bounded-liveness xfailed；generated RTL 133/133；coverage
86.70%；Python 3.14 1179/1179；双后端 nightly differential fast/slow 全部
通过；Python mutation 296/318，RTL template mutation 12/12；ruff、strict
mypy、发行包隔离 smoke 和 whitespace 检查通过。

截至 `79db15d` 没有新发现的本地可复现 P0；该时点尚未关闭的 structured
frontend 已在上方 2026-08-02 F-11 基线中实现。当前高优先级风险收敛为
multi-clock acknowledged event-transfer 协议、工业 project corpus、
逐构造证据链和剩余 mutation 债务。`SUPPORT_MATRIX.md` 因此继续保持
0 个 Fully supported。

## 2026-08-01 v1.7.1 发布后资格审计

审计先定位并修复 Ubuntu Verilator 的 C++ Flex header 依赖，又在真实
nightly 干净 checkout 中发现 pytest 嵌套 `--basetemp` 缺少父目录，以及
隐藏 `.artifacts` 默认不会上传的问题。新增的 CI workflow 回归同时约束
父目录创建和隐藏 artifact 上传配置；最终三条远端工作流在 `b055105` 上
全部通过。

这完成了“远端资格是否实际执行”的闭环，但不是“工业级完备”的宣告。
支持矩阵仍保持 0 个 Fully supported，原因已从缺少同提交远端证据收敛为
逐构造的真实 source、独立 oracle、formal 深度/无界性与拒绝边界缺口。
多时钟电平同步器的事件丢失/合并风险仍是独立的架构级 Trusted boundary。

### 后续高优先级审计修复（本地与同提交远端均已验证）

- 修正可选 CDC 亚稳态注入器：由 LFSR 最低位导致的约 1/2 周期翻转，改为
  最大长度 255 周期非零序列中仅一次脉冲；零 seed 也被强制映射到非零状态。
- GitHub Actions 的 checkout 与 uv setup 均迁移到固定提交的 Node.js 24
  原生版本，并显式保留原有 cache pruning；三条 workflow 同时收窄为
  `contents: read` 最小 token 权限。
- `behavioral_oracle.py` 新增 liveness 上下界、提前命中、property/sequence
  NFA dead-end 与 attempt 边界回归。该模块 mutation 从 112/130 提升为
  118/131；四模块总计从 260/301 提升为 266/302。
- 多时钟 frontend/composition 测试改为每次调用独占临时目录，并加入路径
  唯一性与清理回归，消除并行 pytest 进程共享固定 `/tmp` 文件的竞态。
- RTL template mutation 新增 CDC one-shot 注入反变异，严格门禁为 12/12。

最新本地门禁全部通过：ruff、mypy strict、冻结 lock 与 workflow YAML；
完整 Icarus 1484 passed / 1 skipped / 1 xfailed；完整 Verilator simulation
169 passed / 1 skipped；branch coverage 86.31%；generated RTL 133 passed；
Full Formal 125 passed / 1 个已记录 strict-liveness xfail。同一基线
`1841ed4` 的远端 CI `30686814681`、nightly `30686818970` 与 Full Formal
`30686820029` 也全部通过。该证据补充而不倒推改写 `b055105` 的历史记录，
也不自动升级任何 Fully supported 行。

### `1841ed4` 本地资格证据（历史基线）

本节数字对应后续 `79db15d` 之前的历史基线；最新本地证据以上方“深度审查
后续高优先级修复”为准。

本地在最新高优先级修复分支上重新执行了完整门禁，而不是沿用 2026-07-26
数字：ruff、mypy strict、冻结 lock、工作流 YAML、安装脚本语法和覆盖率下限
均通过；Icarus 全套为 1484 passed / 1 skipped / 1 xfailed，generated RTL
为 133 passed，Full Formal 为 125 passed / 1 个已记录的 strict-liveness
xfail。Python 3.14 非仿真广泛轴为 1247 passed / 1 xfailed。双后端差分
fast 各 16 passed，日期 seed `20260801` 的 slow 各 1 passed，每项内部运行
64 个 Hypothesis examples。branch coverage 为 86.31%。v1.7.1 wheel/sdist
在仓库外分别用 Python 3.12、3.14 安装、调用 CLI、生成 RTL 并通过 Icarus。

当前分支重新执行的 Python mutation 为 266/302 killed（88.1%）：
`bool_semantics.py` 15/15、`behavioral_oracle.py` 118/131、`composer.py`
41/48、`ast_importer.py` 92/108；另有 30 个未覆盖候选不计入分母，36 个
有效变异仍存活。RTL 模板 mutation 为 12/12。门槛通过不等于没有测试债务，
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
- SUPPORT_MATRIX 中 0 个构造行达到 Fully supported；同提交远端矩阵已闭环，
  但逐构造仍存在真实 source、独立 oracle、formal 深度/无界性或拒绝边界缺口
- 全算子等价证明仍以 BMC 有界为主；k-induction 当前覆盖 10 个小状态目标，尚未扩展到全部算子、复杂 NFA、liveness 或 CDC 边界
- 多时钟 CDC 与事件交付尚未闭环：当前 2-DFF 电平同步器可能漏采窄脉冲
  或合并连续事件，必须通过明确的 handshake/toggle 与速率/overflow 契约解决
- K-state budget (>32) 和 CDC 边界是 NFA 引擎仅存的拒绝路径
- 本机与远端均已使用 Verilator 5.028 完成 simulation、generated lint 与
  differential；workflow actions 已迁移到固定提交的 Node.js 24 原生版本，
  并已在 `1841ed4` 的三条远端工作流中执行通过
- GitHub 托管 runner 仍会报告并行 uv cache reservation 冲突和预置
  Homebrew tap trust 提示；二者未影响本轮 job 结论，但属于待降噪的 P2 CI
  可维护性问题
- F-11 已支持结构化多文件工程上下文，但大型真实工程、嵌套 filelist 变体、
  library 冲突和多参数化实例标签消歧仍缺少公开、可复现的 corpus 证据

## 未来规划

### 短期（发布加固闭环）

1. F-01、同提交 CI、differential nightly 与 Full Formal 已在 `b055105`
   上执行通过，run ID 已写入本报告与支持矩阵。
2. 逐行重评 `SUPPORT_MATRIX.md`，只在完整证据链闭合后升级；流水线全绿
   本身不自动等于 `Fully supported`。
3. Node.js 24 原生 pinned actions 与最小 token 权限已落地，并在
   `1841ed4` 的三条同提交远端 workflow 中通过。
4. `v1.7.1` 已发布且 tag 不改写；发布资格证据应追加到新的修复 SHA，不能
   倒推声称 tag 本身已经通过后来才运行的门禁。

### 中期（Phase 2：证据链闭合，2-3 周）

4. 选择 5-8 个核心构造（bool、$rose/$fell/$stable/$changed、##1、simple |->、[*3]、first_match、disable iff），补齐逐构造证据链，再逐行升级为 Fully supported
5. 继续将剩余 21 个有效 mutation survivors 和 36 个未覆盖候选转为定向回归，
   优先处理仍有 14 个 survivor 的 importer
6. 为 multi-clock 引入 acknowledged handshake/toggle、异步时钟比仿真与 CDC sign-off

### 长期（按需求拉动）

7. FPGA 原型（FUT-03）：与 OSS CAD Suite 集成，记录面积/时序/资源基线
8. 真实设计 corpus：至少 2 个非玩具设计端到端流程
9. C++ 重写 v2（FUT-04）：仅在 Python 性能基线明确成为瓶颈后启动
10. 社区采用与学术发表：DVCon 投稿（多层验证方法论 + k-induction + NFA 组合引擎）

## 风险登记册

语言实现风险 RISK-00 至 RISK-06 已闭环或降级。本轮新增的制品完整性、
CI 工具漂移、差分构建缓存、状态文档漂移和 nightly 干净 checkout 问题
均已修复并取得同提交远端证据。最新审计又完成 Node.js 24 迁移、最小权限、
测试隔离和部分 mutation 债务收敛，且已取得 `1841ed4` 的同提交远端证据。
架构上仍未闭环的是逐构造证据链、21 个 mutation survivors、
bounded-liveness 证明边界、真实工程 corpus，以及 multi-clock CDC 事件
交付协议；此外还有非阻断的 cache/tap runner 注释需要降噪。

## 竞争定位

sva2verilog 聚焦“可综合 SVA 监控器”这一窄赛道，但当前没有公开、可复现
的工业 assertion corpus，不能量化声称覆盖 95% 的真实断言场景，也不应
声称“唯一同类”。可审计的定位应以 `SUPPORT_MATRIX.md` 的逐构造边界为准。
明确边界包括无界活性、CDC/亚稳态、复杂局部变量与未建模的 IEEE 1800
语义；商业工具对比需要独立 corpus 和交叉工具结果后再下结论。
