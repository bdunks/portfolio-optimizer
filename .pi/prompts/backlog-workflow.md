---
description: Execute the approved backlog sequentially with review, validation, and progress tracking
argument-hint: "[task IDs or stopping point]"
---

Execute approved Ready backlog work sequentially, within any supplied scope. Invoking this prompt authorizes implementation and verified backlog completion, not Draft promotion or live trading.

### Workflow
- Read `AGENTS.md`, `README.md`, the authoritative specifications, and `docs/decisions.md`. Preserve existing work and the recorded offline acceptance boundaries; use FakeBroker/fake transport only, with live writes disabled.
- Follow `.pi/prompts/execution-workflow.md` for implementation, delegation, fresh review, and validation. The parent selects and completes backlog work; workers and reviewers do not select tasks, complete them, or redelegate.
- From the repository root, use `backlog task next --json` for eligible work and its task, milestone, and project context. To resume a specified task, use `backlog task show <id> --json` and verify its state, prerequisites, and checkout before continuing.
- Execute each task through review and its done-when checks. Phase acceptance requires independent integration verification against the applicable specification gates, not only worker reports. Never mark partial or failing work Done.
- After verification, use `backlog task done <id> --handoff TEXT` with concise outcomes, actual checks/results, checkpoint, and useful next context. Complete a milestone only after all its tasks and acceptance gates pass. Continue to the next eligible approved task unless the supplied stopping point is reached.
- Keep progress and recovery notes in the selected task's instructions, preserving its requirements: active child run IDs, working directories/refs, checkpoint, partial work, retries, and next action. Do not create a parallel progress ledger.
- On an unresolved blocker or before interruption, account for active writers, save those notes, and stop rather than selecting around the blocker. Ask before changing financial semantics, cross-phase contracts, or approved scope.

### Final response
Report completed task/milestone IDs, actual validation results, checkpoint, blockers or active work, and the next action. Offline acceptance is not live-trading release authorization.

### Scope
$ARGUMENTS
