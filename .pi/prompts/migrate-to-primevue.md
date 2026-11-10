---
description: Migrate Quasar to PrimeVue unattended through execution-workflow
---

# Quasar → PrimeVue

Execute this migration unattended using `/execution-workflow` for implementation subtasks and reviews. This prompt approves the migration, including layout and build-tooling changes. Let the orchestrator and workers resolve implementation details without routine approval pauses.

## Target stack and design direction

- **PrimeVue latest stable** at execution start, with **Aura** in styled mode.
- **`@primeicons/vue`** for icons.
- **Apache ECharts** for advanced charts.
- **Tailwind** only for layout needs not reasonably covered by PrimeVue; minimize utility-heavy markup in application templates.

Fully adopt standard PrimeVue components and default Aura styling. Preserve product functionality, not the existing visual identity. Do not add custom CSS, theme overrides, or bespoke visual treatments in this pass; use Tailwind only where necessary for layout.

The existing app has never been visually tested and is not a visual baseline. Verify usability, responsive layout, and readable financial tables against standard PrimeVue behavior. Matching `docs/portfolio_tax_optimizer_reference.html` is explicitly deferred to a second pass, not part of this migration.

## Execution stages

Use the installed **PrimeVue MCP** for current documentation, component discovery, examples, and usage validation. Start each distinct PrimeVue task with **`primevue-router`**, then load its focused skill; the stage-specific names below identify the intended routes, not a requirement to load every skill together.

Use `node frontend/scripts/quasar-inventory.mjs` for discovery and repeat audits during migration and before Quasar removal. Its read-only findings are candidates for review, not proof of completeness; enhance the script's patterns and coverage as migration needs evolve.

### 1. Install and bootstrap

Skill: **`primevue-setup-installation`**.

First implementation task: install PrimeVue latest stable, Aura's supported theme package, and `@primeicons/vue`. Configure PrimeVue and verify a themed component renders. Add Tailwind integration and ECharts where needed. Resolve package versions against current documentation and retain Quasar temporarily so migration can proceed incrementally.

### 2. Replace the application shell and tooling

Skills, by task: **`primevue-component-implementation`**, **`primevue-theming-customization`**.

Replace Quasar CLI scaffolding with standard Vue/Vite tooling. Carry over router/store initialization, environment handling, API proxies, dev-server settings, and production output contracts from `frontend/quasar.config.ts`.

Rework `frontend/src/layouts/MainLayout.vue` and its dependent views: PrimeVue is not a drop-in replacement for QLayout/QHeader/QDrawer/QPage. Prefer PrimeVue navigation and overlay components, with semantic structure and Tailwind only for necessary layout. Handle temporary Quasar/PrimeVue CSS coexistence explicitly.

### 3. Migrate components and feature views

Skill: **`primevue-component-implementation`**; use **`primevue-theming-customization`** only for standard Aura/Tailwind integration, not visual customization and **`primevue-accessibility-icons`** for icon/accessibility tasks.

Inventory Quasar components, services, composables, directives, utility classes, and icons. Migrate shared dependencies first, then coherent feature slices, updating affected tests alongside them. Choose components by required behavior rather than matching names. Preserve validation, financial formatting, table interactions, dialogs, notifications, and loading/error/empty states.

Use ECharts for advanced chart requirements, including responsive resizing, lifecycle cleanup, and accessible summaries. Validate each migrated view in the browser at desktop and mobile sizes; do not treat compilation or existing tests as visual approval.

### 4. Audit, then uninstall Quasar

Skills, in separate tasks: **`primevue-audit-troubleshooting`**, **`primevue-accessibility-icons`**.

Before removal, replace remaining Quasar-dependent tests/helpers, audit scripts, styles, fonts, generated types, and configuration. Check runtime APIs and hidden dependencies such as `$q`, `useQuasar`, `#q-app`, `.quasar` paths, Sass variables, and utility classes.

Finally uninstall `quasar`, `@quasar/app-vite`, `@quasar/extras`, and other Quasar-only dependencies. Remove obsolete files and hooks, and update active development/deployment documentation. Historical migration references may remain.

## Completion

Verify a clean dependency installation, development startup, production build/serving, and applicable lint, type, unit, integration, and E2E checks. Exercise critical demo workflows and review every migrated route visually, including keyboard/focus behavior, mobile navigation, table overflow, and chart presentation.

Finish with resolved package versions, significant design/tooling decisions, actual check results, and remaining issues. Completion requires a functional, visually reviewed PrimeVue application with no active Quasar dependency—not merely replaced tags or a passing build.
