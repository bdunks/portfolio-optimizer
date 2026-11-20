---
description: Execute approved tasks sequentially with workers, review, validation, and human handoffs
argument-hint: "<approved task IDs, requirements, or @requirements-file>"
---

Execute the approved tasks sequentially through implementation, validation, and fresh review. Ask before starting if scope, approval, or acceptance criteria are missing.

### 1. External contracts (when applicable)
When a task touches an external API or file format, verify the real contract before delegating:
- Use authoritative documentation, a schema, or a sanitized real capture with known provenance—never invent a wire schema or rely on unverified examples.
- If the contract or requirements are missing or conflict, stop and ask the user. Do not make live requests unless authorized.
- Offline tests may mock transport, but representative success fixtures must match the real contract.
- Include the contract source (and any evidence limits) in both worker and reviewer briefs so the reviewer can check against it. Report offline verification separately from live verification.

### 2. Roles and delegation
- **Parent (you):** Own planning, task decomposition, interface definitions, sequencing, delegation, and integration verification. Never write implementation code directly (including patches or temporary scripts under `/tmp`).
- **Workers and reviewers:** Run one subagent at a time. Subagents cannot redelegate.
- **Briefs:** Keep each worker brief concise and focused on the current state: goal, owned files, interface contracts, contract sources, relevant decision IDs (per `AGENTS.md`), and acceptance checks.

**Models:**
- **Implementation (`implementation-worker`):** `gpt-6-luna` — `thinking: max` (complex), `high` (average), `medium` (simple).
- **Fresh review (`reviewer`):** `gpt-6.2-sol` with `thinking: medium` (broad/complex), or `gpt-6-luna` with `thinking: max` (narrow/simple).

### 3. Build, validate, and review
- Workers edit files directly in the working tree and **do not commit**. They should run relevant tests, lint, and typechecks early and report environment or scope blockers immediately.
- Validate real caller and user paths, persistence round trips, and compatibility—not only isolated helpers. Add regression tests for fixed bugs.
- Never weaken checks or add suppressions to hide failures. Treat failing tests, lint, and typechecks as normal feedback to fix within scope; stop and report if blocked, requirements are ambiguous, or retries make no progress.
- Once checks pass, run a fresh reviewer against the full working-tree diff from the task base. Passing tests do not substitute for review acceptance.
- Delegate review fixes back to an implementation worker and re-verify until both checks and review pass. Do not mark work complete while required checks or review findings remain open.

### Task
$ARGUMENTS
