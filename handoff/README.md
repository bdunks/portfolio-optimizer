# Overnight Build Handoff

## Launch

Start the primary agent in the repository root and paste:

```text
Read handoff/program-prompt.md and execute the approved five-phase backlog
program for this project. You are authorized to delegate phase orchestrators,
which may delegate implementation and read-only review workers. Use
handoff/workflow-prompt.md and the configured Sol/Luna profiles (Luna Max for
implementation). Only the program supervisor selects and completes backlog
work, after verification. Follow existing prerequisite/acceptance gates;
keep Draft alternatives deferred. Work unattended within the approved scope..
Do not connect to E*TRADE, including OAuth, reads, previews or submissions.
Implement/test all broker behavior offline; keep live writes disabled.
```

The approved program is stored in the existing `portfolio-optimizer` backlog project. Run `backlog task next --json` from this repository to retrieve eligible work with all task/milestone/project instructions. Five Ready phase milestones contain 16 Ready tasks linked by explicit prerequisites; a separate Draft MILP task is not eligible. Do not recreate these items on startup. Completion of the approved plan is authorized only after checks pass.

## Sources of truth

- **Backlog:** tasks, milestone instructions, prerequisites, done-when criteria, completion and useful handoffs. Supervisor owns task selection and completion; no CLI claim/in-progress state exists.
- `program-prompt.md`: Tier 1 sequencing, acceptance and safety policy.
- `workflow-prompt.md`: Tier 2 delegation; Tier 3 workers cannot redelegate.
- `decisions.md`: approved solver/endpoint/deadline decisions and deferred acceptance.
- **Task handoffs:** active child run IDs, worktrees/refs, checkpoint, partial work, retries and next recovery action. Save before interruption and verify against the actual checkout/run state on resume.
- `kickoff_prompt.md`: historical Phase 1 detail, not the current launcher.

## Operational limits

These documents do not launch a build or prove configured nested delegation works; preflight verifies it. The backlog database is user-local and not stored in this Git repository. On another machine, reconcile project/work-directory/IDs or restore a proper backup; never automatically initialize/reset/recreate work. Keep sensitive account data out of backlog handoffs.

Offline completion requires actual automated test/build/benchmark evidence, not live acceptance or permission to trade. Actual OAuth/account validation, subjective human visual/usability review and live release are deferred. Missing mandatory automated gates block completion; no promise that all phases finish overnight.
