---
name: backlog-authoring
description: >-
  Use when creating, editing, reordering, or completing tasks with the `backlog`
  CLI so task instructions, Done-when criteria, and handoffs follow repository
  formatting conventions and safe shell quoting.
---

# Backlog Authoring & CLI Reference

Run `backlog` commands from the repository root.

## Common commands

- `backlog task next --json` — find eligible work with task, milestone, and project context, including instructions. No follow-up `task show` is required to start work.
- `backlog task show <id> --json` — inspect a specific task and its context when needed (`task <id>` is not a command).
- `backlog task list --milestone <id> --json` — inspect tasks and their order before changing a milestone.
- `backlog milestone list --json` — inspect milestones before adding or moving work.
- `backlog task create --milestone <id> --title TEXT --instructions TEXT --done-when TEXT --state Draft --json` — create a draft task and capture its ID.
- `backlog task move <id> --milestone <id> --position N` — move a task to a zero-based position.
- `backlog task done <id> [--handoff TEXT]` — complete eligible work; include a handoff for useful outcomes, decisions, deviations, or context for subsequent work. Omit it when there is nothing useful to pass on.
- `backlog --help` and `backlog <command> --help` — see all commands and flags.

## Author readable tasks

Write instructions, Done-when criteria, and handoffs as Markdown for humans reading the browser:

- Keep titles plain text.
- For multi-part instructions, use descriptive `##` headings and short paragraphs or lists. Include goal, scope, and constraints where useful; omit empty sections.
- Put each independent Done-when criterion on its own `-` bullet.
- Use backticks for paths, commands, and identifiers; use fenced code blocks for multiline code.
- Submit actual newlines, not literal `\n` text. Leave blank lines between paragraphs and before lists.
- When editing, preserve existing requirements and useful structure; update the relevant section rather than appending another prose block.
- For useful handoffs, separate outcomes, checks, and remaining issues where needed. Do not claim checks that were not run; omit a handoff when there is nothing useful to pass on.
- Short, single-purpose fields need no unnecessary headings. GFM tables, task lists, strikethrough, and bare URL links are supported; checklist boxes are read-only recorded text, not task-state controls.

## Quoted-heredoc example

Set `milestone_id` to the inspected destination milestone ID first. Creating a `Draft` task is not approval to execute:

```bash
backlog task create --milestone "$milestone_id" \
  --title "Explain blocked tasks" \
  --instructions "$(cat <<'MD'
## Goal
Make blocked tasks understandable without changing eligibility.

## Scope
- Show the direct prerequisites preventing execution.
- Reuse existing task-detail components.

## Constraints
- Do not introduce another persisted state.
MD
)" \
  --done-when "$(cat <<'MD'
- Blocked tasks identify their incomplete prerequisites.
- Eligible tasks retain their existing behavior.
- Focused tests cover both cases.
MD
)" \
  --state Draft --json
```

The quoted `MD` delimiters prevent shell expansion of Markdown backticks and `$` expressions. Use the same quoted-heredoc pattern with `task edit --instructions`, `--done-when`, or `task done --handoff`.
