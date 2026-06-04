# Phase 02: Verilator Parity + CI Expansion - Context

**Gathered:** 2026-06-04

## Decisions

### 1. Verilator 版本与安装策略

- **CI 安装方式**: 跟随现有模式 — `sudo apt-get install -y verilator` (Ubuntu), `brew install verilator` (macOS)。与 iverilog 安装方式一致。
- **版本**: 不固定版本，使用包管理器提供的最新稳定版。Verilator 向后兼容性好，固定版本会增加维护负担（参考 slang v7.0 固定导致的 JSON fixture 同步问题）。
- **本地开发**: 不添加 pre-commit hook。Verilator 作为 CI 门控即可；本地开发用 iverilog 快速迭代。
- **CI 检测**: `tests/simulation/conftest.py` 已有的 autouse skip 模式（`shutil.which("iverilog")`）扩展为同时检测 `verilator`，通过 `--simulator` CLI flag 或环境变量 `SVA2RTL_SIMULATOR` 切换。

### 2. 对等性测试范围

- **仅对 `simulation` 标记的测试运行 Verilator**: 其他 658 个测试是纯 Python 单元/集成测试，不涉及仿真器，在 Verilator 轴上重新运行毫无意义。
- **扩展 `test_verilator_lint_clean`**: 现有的 `tests/test_sequential.py::test_verilator_lint_clean` 是对生成 RTL 进行 `verilator --lint-only` 的 lint 测试，应从 skip 升级为在 Verilator 轴上运行。
- **标记精确性**: 确认 `pytest -m simulation` 精确覆盖所有需要仿真器的测试（目前约 65 个，全部在 `tests/simulation/` 下）。
- **不引入 Verilator 单元测试轴**: 运行非仿真测试浪费 CI 时间。

### 3. 仿真后端架构

- **方案 B — `--binary` + 最小 C++ wrapper**: 不使用完整 C++ testbench。Verilator 的 `--binary` 模式允许在命令行中将 DUT 编译为可执行文件；搭配一个极简 C++ wrapper（~50 行）驱动相同的 per-cycle stimulus/check 逻辑。
- **tb_generator.py 重构**: 抽取 `run_simulation_iverilog()` 和新增 `run_simulation_verilator()`，共享 stimulus generation 逻辑。接口统一为 `run_simulation(module_name, stimuli, simulator="iverilog")`。
- **不生成完整 C++ testbench**: 避免维护两套 testbench 模板。
- **Verilator 编译命令**: `verilator --binary --timing -Wall --top-module <dut> <dut.sv> <wrapper.cpp> -o <sim>`。
- **Wrapper 职责**: 驱动 clk/rst_n/start/disable_i 信号按 stimulus 时序，每个 posedge 读取 pass/fail/active/attempt_fired 输出并与 expected 对比。

### 4. CI 矩阵设计

- **扩展现有 `test` job matrix**: 在现有的 `os × python-version` 矩阵上增加 `simulator` 维度。结果: `{ubuntu, macos} × {3.12, 3.13} × {iverilog, verilator}` = 8 jobs。
- **`lint` job 不变**: ruff + mypy 本身不依赖仿真器。
- **条件安装**: 每个 job 根据 `matrix.simulator` 安装对应工具（iverilog 或 verilator），slang 在所有 job 中都安装。
- **测试命令区分**: `iverilog` job 运行 `pytest tests/ -m simulation --simulator=iverilog`；`verilator` job 运行 `pytest tests/ -m simulation --simulator=verilator`。
- **`fail-fast: false`** 保持现有设置，一个平台的失败不阻塞其他平台。
- **不使用 soft-fail**: 对等性是 Phase 2 的核心交付物 — 任何差异都是需要在本阶段修复的 bug。不引入 `xfail_verilator` 标记。

### 5. 差异处理机制

- **CI 差异 = 失败**: Verilator 与 iverilog 结果不一致时，对应 Verilator job 直接失败（红色）。
- **调试辅助**: `run_simulation()` 函数在结果不匹配时输出 diff（cycle-by-cycle expected vs actual），与现有的 golden 对比模式一致。
- **修复优先级**: 先修 sva2rtl 代码生成 bug（可能两边都错但表现不同）→ 再修复 Verilator wrapper 或 timing 假设差异 → 最后才考虑标记为已知差异（目前不希望走到这一步）。
- **Phase 2 内部修复**: 所有对等性差异都在 Phase 2 内修复。Phase 2 结束时，Verilator job 必须全绿。

### 6. 文档更新范围

- **README.md**: 在 "Simulation" 或 "Getting Started" 章节添加 Verilator 安装说明和 `--simulator` flag 用法。
- **SUPPORTED_CONSTRUCTS.md**: 无需更新（对等性不影响支持的构造列表）。
- **CLAUDE.md**: 更新验证约束，明确双 oracle 合约。

## Claude's Discretion

以下细节由 plan-phase 和 execute-phase 自行决定：

- `wrapper.cpp` 的具体实现（时钟周期数、信号名硬编码 vs 模板生成）
- tb_generator.py 重构的具体函数签名和模块拆分
- CI YAML 中 `matrix.simulator` 的具体语法
- `--simulator` pytest flag 是通过 conftest.py 的 `pytest_addoption` 还是环境变量实现
- Verilator `--timing` flag 是否需要（取决于生成的 DUT 中是否有 `#delay`）
- 仿真超时时间：iverilog 现有的 120s 是否足以覆盖 Verilator 编译 + 运行

## Deferred Ideas

以下想法超出 Phase 2 范围，已记录供未来参考：

- **Verilator code coverage**: 在仿真中收集 Verilator 覆盖率数据 → v1.2 或独立 phase
- **Verilator waveform dump (VCD/FST)**: 面向调试用途 → v1.2
- **Formal equivalence check (yosys-sby)**: `--no-optimize` vs optimized 输出之间的形式化等价性验证 → v2
- **Pre-commit hook 中的 Verilator lint**: 本地提交前自动运行 `verilator --lint-only` → 后续 phase 或独立 PR

---

*Context gathered for phase planning*
