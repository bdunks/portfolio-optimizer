---
description: Execute approved tasks sequentially with workers, review, validation, and human handoffs
argument-hint: "<approved task IDs, requirements, or @requirements-file>"
---

Execute the supplied, approved tasks sequentially through implementation, review, and validation. Ask before starting if scope, approval, or testable acceptance criteria are missing.

### Orchestration
The parent is the architect and orchestrator, delegating directly to implementation-worker and fresh reviewer pi-subagents. Do not introduce an intermediate orchestration agent. Workers and reviewers cannot redelegate.

- The parent owns architecture, task decomposition, interface definitions, sequencing, delegation, and integration review.
- The parent must never write implementation code, including patches or temporary files under /tmp. Delegate implementation directly rather than generating code for Luna to apply.
- Follow `AGENTS.md` decision-record rules: resolve relevant assumptions and log decisions before dependent work; include applicable decision IDs in tasks and worker briefs.
- Delegate small, bounded, independently testable increments to Luna `implementation-worker` subagents. Split large implementations or review-fix lists into coherent changes with explicit dependencies and acceptance checks.
- Launch implementation workers at the appropriate thinking levels for task complexity, erring higher if unsure:
  - Complex task: `gpt-6-luna` with `thinking: max`
  - Average task: `gpt-6-luna` with `thinking: high`
  - Low complexity: `gpt-6-luna` with `thinking: medium`
- Give each worker a concise brief: goal, owned files, interface contracts, dependency commits, acceptance checks, and unresolved decisions. Maintain one current checkpoint rather than accumulating overlapping instructions or forwarding orchestration history.
- Each worker first verifies its checkout, dependencies, and relevant test commands using the project environment. Report blockers immediately; do not defer environment discovery until handoff or treat unrun checks as passing.
- Each worker implements directly in its assigned checkout or worktree and commits a recoverable checkpoint after each coherent change, before lengthy validation or polishing. Clearly distinguish unvalidated checkpoints from verified results.
- Run only one subagent at a time, including implementation workers and reviewers. Commit and validate each change before review; finish review and fixes before starting the next task.
- Validate complete caller and user paths, persistence round trips, and compatibility—not only isolated helpers or components. Add regressions for reported failures before declaring fixes complete.
- A fresh subagent reviews each bounded change, connected code, integration, and test evidence:
  - Broad and complex change: `gpt-6.1-sol` with `thinking: max`
  - Simple change or narrow fix review: `gpt-6-luna` with `thinking: medium`
- Delegate fixes back to implementation workers in coherent increments. Integrate tested changes and rerun relevant integration checks before proceeding; do not equate passing tests with review acceptance.
- Prepare performance tooling independently when useful, but defer final representative benchmarks until correctness fixes are integrated. Keep provisional measurements separate from acceptance evidence.
- On worker failure, report it, inspect preserved changes and checkpoints, and use only an authorized, bounded recovery. Stop after a failed recovery rather than silently relaunching or changing models.
- Minimize redundant context, handoffs, repeated reviews, and repeated validation of unchanged revisions. Preserve exact revisions, actual check outcomes, remaining risks, and the next action in durable checkpoints.
- Continue through full implementation and verification, not just planning or scaffolding. Do not mark work complete while required checks or review findings remain unresolved.
- If the required model or thinking level is unavailable, stop and report the blocker rather than silently substituting.

### Task
$ARGUMENTS
