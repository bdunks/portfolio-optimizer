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
- Each worker implements directly in its assigned checkout or worktree. Iterate through local edits and checks without committing every attempt; commit a coherent increment after its required checks pass. Create an explicitly unvalidated recovery commit only when preserving substantial unfinished work before a handoff/interruption or risky operation—not merely because validation is next. Status updates and failed checks belong in the durable task checkpoint, not separate Git commits.
- Optionally use one feature branch per coherent deliverable or tightly coupled task group, especially when isolation or squash integration is useful; do not create branches for individual fixes/check cycles. After validation and fresh review, the branch may be squash-merged into one meaningful commit. Do not rewrite shared history without explicit approval.
- Run only one subagent at a time, including implementation workers and reviewers. Validate and commit each coherent increment before fresh review; review its complete diff against the task base, not each intermediate commit. Finish review and fixes before starting the next task.
- Validate complete caller and user paths, persistence round trips, and compatibility—not only isolated helpers or components. Add regressions for reported failures before declaring fixes complete.
- A fresh subagent reviews each bounded change, connected code, integration, and test evidence:
  - Broad and complex change: `gpt-6.1-sol` with `thinking: medium`
  - Simple change or narrow fix review: `gpt-6-luna` with `thinking: max`
- Delegate fixes back to implementation workers in coherent increments. Integrate tested changes and rerun relevant integration checks before proceeding; do not equate passing tests with review acceptance.
- Treat failing tests, lint and typechecks as implementation feedback, not worker failures. Allow up to three local fix/check cycles within the assigned scope; run strict typing early, including tests, and explicitly type heterogeneous fixtures/empty containers and narrow optional values. Never relax checks or add suppressions to hide failures. Stop and report ambiguous semantics, scope/security/environment blockers, repeated failures without progress, or exhausted cycles. On an actual worker/runtime failure, report it, inspect preserved changes and checkpoints, and use only an authorized, bounded recovery; restart a maximum of two times.
- Minimize redundant context, handoffs, repeated reviews, and repeated validation of unchanged revisions. Preserve exact revisions, actual check outcomes, remaining risks, and the next action in durable checkpoints.
- Continue through full implementation and verification, not just planning or scaffolding. Do not mark work complete while required checks or review findings remain unresolved.

### Task
$ARGUMENTS
