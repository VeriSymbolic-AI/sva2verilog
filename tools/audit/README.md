# tools/audit

Audit harness for the sva2rtl v1.1 Retroactive Nyquist Baseline phase.

## seed_validation_skeletons.py

Walks `.planning/milestones/v1.0-phases/0N-*/` (six directories) and seeds one
`0N-VALIDATION.md` skeleton per phase directory, filled from
`.planning/research/VALIDATION-TEMPLATE.md`.

```
python tools/audit/seed_validation_skeletons.py --dry-run   # list targets, no writes
python tools/audit/seed_validation_skeletons.py --check     # verify all 6 exist
python tools/audit/seed_validation_skeletons.py             # write skeletons (idempotent)
```

Read-only contract: never writes to `src/` or `tests/`.
