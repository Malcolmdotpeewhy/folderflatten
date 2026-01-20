## 2026-01-20 – Unify core logic for GUI/tests
**Learning:** GUI embedded its own core logic, which drifted from the shared module and left tests outdated.
**Action:** Centralize behavior in `folder_flattener_core` and expose move records to enable safe undo workflows.
