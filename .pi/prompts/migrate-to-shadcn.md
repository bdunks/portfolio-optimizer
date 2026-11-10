---
description: Migrate the frontend to shadcn-vue through the execution workflow
---

# Migrate the frontend to shadcn-vue

Start the frontend migration now. Invoking `/migrate-to-shadcn` authorizes execution of the requirements below, not just planning or acknowledgment; do not wait for a second invocation or additional approval to begin.

Read `.pi/prompts/execution-workflow.md` and apply its orchestration instructions to this migration as the approved task. A slash-command reference in this prompt does not automatically expand another template: load and follow that file explicitly. The parent owns architecture and sequencing, delegates serial, bounded implementation-worker subtasks, and obtains a fresh independent review after each bounded change. Delegate fixes back to an implementation-worker and validate each change before proceeding. Continue through implementation and verification, stopping only for a concrete blocker or a decision requiring user input. If the workflow or its required capabilities are unavailable, report the blocker rather than silently bypassing them.

## Target stack

Use the following target stack as one coherent frontend architecture:

- shadcn-vue components
- Tailwind CSS 4
- TanStack Table
- TanStack Form with Zod validation
- TanStack Charts
- TanStack Query for server state
- Pinia for UI state
- Lucide Vue icons

Resolve exact package names, supported versions, APIs, and installation commands from current upstream metadata, the installed shadcn-vue skill/MCP, and current CLI documentation at execution time. Do not infer or fabricate package names, APIs, Vue adapters, or maturity claims. If a required tool or supported integration is unavailable, stop and report the blocker instead of silently substituting another library.

## Target source structure

Use this structure under `frontend/src/` as a responsibility map, not a requirement to create empty directories or move unrelated code:

```text
src/
├── components/
│   ├── ui/                 # CLI-managed shadcn-vue primitives
│   ├── charts/             # Reusable TanStack Charts compositions
│   ├── tables/             # Reusable TanStack Table compositions
│   └── portfolio/          # Portfolio-specific UI
├── layouts/                # Application shell
├── pages/                  # Route-level views
├── router/                 # Route definitions and initialization
├── composables/
│   ├── queries/            # TanStack Query keys and query composables
│   └── mutations/          # Mutations and server-cache invalidation
├── forms/                  # TanStack Form compositions and Zod schemas
├── stores/                 # Pinia: client UI state only
├── services/               # Existing typed FastAPI client
├── types/                  # Shared application/API types
└── styles/                 # Tailwind CSS 4 entry and standard theme tokens
```

Keep `App.vue` and the Vite entry at the source root. Keep tests alongside the code they exercise and preserve dedicated integration/E2E suites. Retain useful existing `utils/`, `assets/`, and other modules; move files only when their migration requires it, updating imports, aliases, and tests together.

Keep remote fetching and cache policy in query/mutation composables, transport and API error handling in `services/`, and client-only UI state in Pinia. Prefer feature-local code until reuse justifies a shared chart, table, form, or component; do not introduce generic wrappers merely to fill this tree. Resolve shadcn-vue CLI aliases to these destinations rather than duplicating generated components. Consolidate migrated global styling in `styles/` and retire legacy `css/` only after its consumers are migrated.

## Design and migration boundaries

- Prefer standard shadcn-vue components, documented variants, and semantic design tokens. Do not create a custom visual design, bespoke theme, or unnecessary component styling.
- Keep work limited to the frontend migration. Preserve existing product behavior, financial meaning, backend/API contracts, routes, and tests; do not introduce live brokerage access or unrelated features.
- Use the installed `shadcn-vue` skill and its focused rules. Consult the installed shadcn-vue MCP, current CLI documentation, and current upstream documentation/metadata before depending on component APIs or versions. If an expected MCP or capability is unavailable, report it as a blocker.
- Run `frontend/scripts/quasar-inventory.mjs` at discovery and repeat its candidate audit as shared code and feature slices migrate and before removing Quasar. Treat its findings as candidates for review, not proof of completeness.

## Preserve application contracts

Use `frontend/quasar.config.ts` as the authoritative source for current runtime behavior while replacing its tooling. Preserve:

- Local-only binding to `127.0.0.1`, port `9000`, and strict port selection.
- `PORTFOLIO_API_TARGET` behavior, including the default target `http://127.0.0.1:8000`, and `/api/v1` plus `/health` proxies.
- Hash-based Vue Router behavior and the production `dist/spa` output contract.
- Existing environment handling, entry/router/store initialization, and functional development and production serving.

Plan CSS coexistence explicitly while Quasar and migrated code temporarily run together. Identify and control resets, global styles, CSS variables, fonts, and utility collisions; verify that both migrated and not-yet-migrated views remain functional at every intermediate step.

## Implementation sequence and technical requirements

1. **Audit and verify compatibility.** Read the migration and shadcn-vue skill instructions, inspect the current app and tests, and verify documentation, MCP availability, package-manager metadata, and upstream support for the target stack. In particular, assess TanStack Charts' current Vue support, maintenance, and maturity before any installation. Report a blocker rather than replacing it if the required Vue integration is not suitable.
2. **Establish shared foundations first.** Migrate shared application shell, navigation, styling, data/query boundaries, and reusable components before coherent route-level feature slices. Keep TanStack Query responsible for remote/server state and Pinia responsible for UI state; do not duplicate server cache state in Pinia.
3. **Preserve financial and form semantics.** Use TanStack Form with Zod for typed form state and validation. Preserve existing financial `Decimal` precision for money, tax, and cash decisions; do not convert exact financial checks to floating-point `Number` arithmetic.
4. **Preserve interactive data tables.** Use TanStack Table for required table state and behavior, including sorting, filtering, pagination, and selection, while retaining accessible labels, clear empty/loading/error states, and usable narrow-screen layouts.
5. **Preserve accessible chart behavior.** Use TanStack Charts only after verified Vue compatibility. Provide accessible text summaries or equivalent non-visual data, handle container resizing, and clean up observers/listeners on unmount.
6. **Remove Quasar only after audits.** Replace remaining framework-dependent code, tests, helpers, styles, generated types, configuration, and documentation. Repeat the inventory audit, inspect every remaining candidate, and confirm no active Quasar runtime or dependency remains before uninstalling its packages and deleting obsolete setup.

## Completion and evidence

The migration is complete only when all of the following are verified and recorded with actual outcomes:

- No active Quasar dependency, runtime API, generated setup, stylesheet, or tooling remains.
- A clean dependency installation, local development startup, production build and serving, lint, typecheck, unit, integration, and E2E checks pass as applicable.
- Every route is reviewed in a browser at desktop and mobile sizes, including keyboard/focus behavior, navigation, financial tables, and charts. Compilation and automated tests alone are not visual approval.
- The final handoff records resolved package versions, significant compatibility decisions, commands and results, and any remaining issues.
