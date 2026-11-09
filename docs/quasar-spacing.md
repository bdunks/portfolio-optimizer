# Quasar-first spacing review

## Scope and outcome

Reviewed all **278 approved layout/spacing candidates** in the saved `docs/quasar-audit/inventory.json` / `dispositions.json`, then checked current source and shared stylesheet consumers rather than trusting old line numbers. The count includes responsive layout rules and two inline typography/opacity findings in `ErrorNotFound.vue`; those two are not spacing and were left unchanged.

- Replaced custom margins/padding with `q-m*` / `q-p*`, flex alignment with Quasar helpers, and simple vertical stacks with `column no-wrap q-gutter-y-*`.
- Used default gutters rather than trying to preserve custom fractional-rem gaps. Removed competing margin utilities on gutter axes.
- Removed custom control padding/min-height and deep card-section padding overrides, including mobile overrides. Quasar controls, banners, card sections and expansion headers now retain framework spacing.
- Removed the hard-coded viewport/header-height subtraction; `QLayout` / `QPage` already calculate available height.
- Shared policy CSS changes reach all four editor sections and `PolicyPage.vue`. Application scripts, financial logic, dependencies and saved review decisions were not changed.

### Reviewed baseline candidates

Paths below are relative to `frontend/src/`.

| File | Approved candidates |
| --- | ---: |
| `components/AllocationTargets.vue` | 7 |
| `components/ApiActionError.vue` | 1 |
| `components/RecommendationLegDetails.vue` | 6 |
| `components/ResourceFreshnessNotice.vue` | 1 |
| `components/RunSummary.vue` | 23 |
| `components/SellLotAttribution.vue` | 4 |
| `components/TradeGroup.vue` | 20 |
| `components/USAllocationTransition.vue` | 17 |
| `components/WorkspaceEmptyState.vue` | 3 |
| `components/WorkspacePageHeader.vue` | 3 |
| `components/WorkspacePagination.vue` | 1 |
| `components/policy-editor-sections.css` | 41 |
| `css/app.scss` | 8 |
| `layouts/MainLayout.vue` | 12 |
| `pages/ActivityPage.vue` | 24 |
| `pages/DevelopmentPendingPage.vue` | 5 |
| `pages/ErrorNotFound.vue` | 2 |
| `pages/IndexPage.vue` | 27 |
| `pages/RecommendationsPage.vue` | 30 |
| `pages/TaxLotsPage.vue` | 25 |
| `pages/WashSalesPage.vue` | 18 |

## Defaults and justified exceptions

The installed Quasar 2.35.2 sources are authoritative: `src/css/variables.sass` defines `none/xs/sm/md/lg/xl` as **0/4/8/16/24/48px**; `core/size.sass` generates spacing utilities and `core/flex.sass` implements gutters with negative parent margins and positive child margins. No spacing variables were overridden. Fractional/rem values were normalized to this scale, not described as pixel-equivalent. Fluid panel padding now uses `q-pa-md` even where this changes the old appearance.

Remaining spacing CSS has specific functional reasons, also noted at its source:

- **Grid track gaps:** responsive multi-column/auto-fit metric and policy grids retain native `gap`, now exclusively on Quasar's default pixel scale. Margin/padding gutters do not create space between grid tracks and can enlarge fixed tracks or collide with nested metric-card spacing. Single-column overflow-constraining `minmax(0, 1fr)` grids remain where they constrain wide financial tables.
- **Screen-reader-only content:** clipped 1px captions/headings retain zero padding and, where needed, -1px margin. Hiding them with a display utility would remove accessible table/region names.
- **Anchor scroll clearance:** recommendation legs retain `scroll-margin-top: 16px`; ordinary Quasar margins do not affect anchor scrolling.
- **Responsive direction/track rules and minimum widths:** retain financial table scrolling and readable controls at constrained widths; these are layout constraints rather than a second spacing utility system.

Typography, borders, branding and non-spacing dimensions are outside this normalization. This is not authorization for new custom spacing helpers.

## Verification

- `npm --prefix frontend test`: **144 tests passed** in 30 files, including two source-wide spacing-policy checks.
- `npm --prefix frontend run test:integration`: **1 isolated FakeBroker integration test passed**.
- `npm --prefix frontend run test:e2e`: **3 Chromium tests passed**. The new spacing test visits all six routes at 1440px and 768px, checks page spacing/overflow, and compares actual button/banner/card-section padding with framework-only reference elements in the same browser.
- `npm --prefix frontend run typecheck`, `lint:check`, `build`, and `git diff --check`: passed.
- Existing workflow tests were updated for the already-migrated `QSelect`, `QExpansionItem` and nested `QInput` markup; no assertions of policy/lot behavior were removed.

The configured Quasar MCP server could not resolve the nested frontend packages, so defaults were checked directly against installed framework source and rendered CSS. LSP routing produced no usable TypeScript diagnostics; `vue-tsc` and ESLint supplied the checks.

Saved inventory/dispositions were deliberately preserved as approval evidence. Their old source hashes/locations are now stale; regenerate and reconcile before another review, not as an implicit approval of newly generated findings. Other browsers, exhaustive visual/accessibility review and the full backend suite were not run. The isolated demo tests used no credentials or live broker traffic.
