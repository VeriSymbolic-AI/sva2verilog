# tools/audit — Development Probe Scripts

These are one-off diagnostic scripts used during development to investigate
specific behavioral questions (delay spacing, CSE naming, liveness AST shape,
implication timing, etc.). They are **not** part of the build or test suite.

## Scripts

| Script | Purpose |
|--------|---------|
| `probe_delay_gap.py` | Non-circular probe: for `a ##N b`, which a→b gap makes pass fire? |
| `probe_delay_formal.py` | FPV-grade (SymbiYosys) confirmation of the `##N` spacing defect |
| `probe_delay_range.py` | Probe `a ##[2:5] b` monitor pass timing under single start |
| `probe_bitvec_impl.py` | Probe BV_WIDTH>1 sequence-consequent implication timing |
| `probe_con_seq.py` | Probe standalone consequent sequence `a ##[2:5] b` |
| `probe_cse_names.py` | Check module-name consistency before/after CSE |
| `probe_equiv_plan.py` | Print structure of candidate fixtures for equiv proof authoring |
| `probe_ifelse.py` | Probe if/else monitor fail expression |
| `probe_liveness_ast.py` | Dump slang AST shape for bounded-liveness SVA forms |
| `probe_liveness_nested.py` | Probe liveness operators nested under implication |

## Usage

```bash
uv run python tools/audit/probe_delay_gap.py
```

Each script is self-contained and writes only to stdout or `/tmp`.
