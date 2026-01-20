## 2026-01-20 – Unify core logic for GUI/tests
**Learning:** GUI embedded its own core logic, which drifted from the shared module and left tests outdated.
**Action:** Centralize behavior in `folder_flattener_core` and expose move records to enable safe undo workflows.

## 2026-01-20 – Filter parity between preview and execution
**Learning:** Preview analysis and execution paths can diverge when filters are only applied in one path.
**Action:** Share filter logic through core scan helpers and validate filter inputs before preview or execution.

## 2026-01-20 – Directory pruning for large scans
**Learning:** Excluding directories and bounding depth reduces scan overhead and improves preview clarity.
**Action:** Add directory filters and depth limits to scanning plus GUI controls for safe targeting.
