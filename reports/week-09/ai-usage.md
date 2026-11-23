# AI usage — Week 09

## 2026-11-22 — Repair failed Windows checks for #77

- Tool: Codex.
- Work: Inspected the latest Windows CI failures, mapped the 21 failed pytest cases, and corrected the isolated Windows subprocess environment and a platform-dependent path assertion in tests/test_smoke_codex.py.
- Verification: Ran only the 21 cases that failed in the latest Windows CI run; all 21 passed locally in 8.36 seconds. Ruff formatting and lint checks passed for the changed test file. The full suite was not run.
- Boundary: Test-only changes; no product behavior or customer data changed. The Windows CI workflow has not yet rerun on this local change.
- Team assessment: TODO