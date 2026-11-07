---
description: Execute approved tasks sequentially with workers, review, validation, and human handoffs
argument-hint: "<approved task IDs, requirements, or @requirements-file>"
---


Execute the supplied, approved tasks sequentially through implementation, review, and validation. Ask before starting if scope, approval, or testable acceptance criteria are missing.


### Orchestration
The parent is the architect and orchestrator, delegating implementation to `implementation-worker` pi-subagents.

- The parent owns architecture, task decomposition, interface definitions, sequencing, delegation, and integration review.
- The parent must never write implementation code, including patches or temporary files under /tmp. Delegate implementation directly rather than generating code for Luna to apply.
- Delegate bounded, incremental tasks to Luna Max `implementation-worker` subagents. Each subagent writes code directly into its assigned project checkout or worktree and runs relevant tests.
- Allow only one writer per working directory or worktree. Parallelize independent implementation tasks in separate worktrees, avoiding conflicting changes. Read-only review may run in parallel in a shared checkout.
- A new sub-agent conducts a code peer review and verifies integration and tests.  That subagent may be spawned at one of two types of models and thinking levels based on complexity:
  - Broad and complex change: `gpt-6.1-sol` with `thinking: medium` 
  - Simple change or narrow: `gpt-6-luna` with `thinking: max`
- Delegate any required fixes back to `implementation-worker`
- Minimize redundant context, unnecessary handoffs, and repeated work across agents.
- Continue through full implementation and verification, not just planning or scaffolding.
- If the required model or thinking level is unavailable, stop and report the blocker rather than silently substituting.

### Task
$ARGUMENTS
