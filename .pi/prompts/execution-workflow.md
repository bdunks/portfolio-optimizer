---
description: Execute approved tasks sequentially with workers, review, validation, and human handoffs
argument-hint: "<approved task IDs, requirements, or @requirements-file>"
---


Execute the supplied, approved tasks sequentially through implementation, review, and validation. Ask before starting if scope, approval, or testable acceptance criteria are missing.


### Orchestration
The parent is the architect and orchestrator, delegating directly to implementation-worker and fresh reviewer pi-subagents. Do not introduce an intermediate orchestration agent. Workers and reviewers cannot redelegate.

- The parent owns architecture, task decomposition, interface definitions, sequencing, delegation, and integration review.
- The parent must never write implementation code, including patches or temporary files under /tmp. Delegate implementation directly rather than generating code for Luna to apply.
- Delegate bounded, incremental tasks to Luna `implementation-worker` subagents
- Launch `implementation-workers` at the appropriate thinking levels for tax complexity, erring on the side of higher thinking if unsure:
  - Complex task: `gpt-6-luna` with `thinking: max`
  - Average task: `gpt-6-luna` with `thinking: high`
  - Low complexity: `gpt-6-luna` with `thinking: medium`
- Each subagent writes code directly into its assigned project checkout or worktree and runs relevant tests.
- Allow only one writer per working directory or worktree. Parallelize independent implementation tasks in separate worktrees, avoiding conflicting changes. Read-only review may run in parallel in a shared checkout.
- A new sub-agent conducts a code peer review and verifies integration and tests.  That subagent may be spawned at one of two types of models and thinking levels based on complexity:
  - Broad and complex change: `gpt-6.1-sol` with `thinking: max` 
  - Simple change or narrow: `gpt-6-luna` with `thinking: medium`
- Delegate any required fixes back to `implementation-worker`
- Minimize redundant context, unnecessary handoffs, and repeated work across agents.
- Continue through full implementation and verification, not just planning or scaffolding.
- If the required model or thinking level is unavailable, stop and report the blocker rather than silently substituting.

### Task
$ARGUMENTS
