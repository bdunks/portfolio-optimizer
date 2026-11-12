<template>
  <section class="transition-panel tw:min-w-0 tw:space-y-4" aria-labelledby="transition-title">
    <header
      class="panel-heading tw:flex tw:min-w-0 tw:flex-col tw:items-start tw:justify-between tw:gap-3"
    >
      <div class="tw:min-w-0">
        <h2 id="transition-title" class="transition-title tw:m-0">US Equities Transition</h2>
        <p class="panel-description tw:m-0">
          {{ transition?.label ?? 'US sleeve' }} · API-reported values; percentages identify both
          within-sleeve and whole-portfolio units.
        </p>
      </div>
      <Badge variant="secondary" class="tw:h-auto tw:whitespace-normal tw:text-center">
        Within US sleeve + whole portfolio
      </Badge>
    </header>

    <Alert v-if="showNoCurrentBasket" role="status" aria-live="polite" class="transition-notice">
      <AlertDescription>
        No current proposed basket from a matching current optimizer run. Values shown below come
        only from the portfolio API; historical or stale runs are not overlaid.
      </AlertDescription>
    </Alert>

    <Alert
      v-if="transition && transition.transition_destination_sleeve_key === null"
      role="status"
      aria-live="polite"
      class="transition-notice"
    >
      <AlertDescription>
        No transition destination is designated in this policy; progress is unavailable and no ETF
        or ticker is inferred.
      </AlertDescription>
    </Alert>

    <Empty v-if="!transition" role="status" aria-live="polite" class="transition-empty">
      <EmptyHeader class="transition-empty-header">
        <EmptyTitle class="transition-empty-title" role="heading" aria-level="2">
          US transition data unavailable
        </EmptyTitle>
        <EmptyDescription class="transition-empty-description">
          US transition data is unavailable from the portfolio API.
        </EmptyDescription>
      </EmptyHeader>
    </Empty>

    <div v-else class="state-grid">
      <article v-for="state in states" :key="state.key" class="state-card" :data-state="state.key">
        <Card class="transition-state-card tw:h-full">
          <CardHeader class="transition-state-header">
            <CardTitle class="transition-state-title" role="heading" aria-level="3">
              {{ state.title }}
            </CardTitle>
            <CardDescription>
              {{
                state.key === 'target'
                  ? 'Policy target percentages; dollar values and progress are unavailable.'
                  : 'Portfolio API values.'
              }}
            </CardDescription>
          </CardHeader>
          <CardContent class="transition-state-content">
            <dl class="state-summary tw:m-0">
              <div class="state-summary-row tw:pb-2">
                <dt>US sleeve value</dt>
                <dd class="tw:m-0">{{ formatUsd(state.snapshot?.us_sleeve_value_usd) }}</dd>
              </div>
              <div class="state-summary-row tw:pb-2">
                <dt>US sleeve share of portfolio</dt>
                <dd class="tw:m-0">
                  {{
                    formatPercent(
                      state.snapshot?.us_sleeve_whole_portfolio_pct ??
                        state.target?.us_sleeve_whole_portfolio_pct,
                    )
                  }}
                </dd>
              </div>
              <div class="state-summary-row tw:pb-2">
                <dt>Transition destination progress within US sleeve</dt>
                <dd class="tw:m-0">{{ formatPercent(state.snapshot?.etf_progress_pct) }}</dd>
              </div>
            </dl>

            <h4 class="component-heading tw:mt-4 tw:mb-2">US sleeve components</h4>
            <ul v-if="childKeys.length" class="component-list tw:m-0 tw:p-0">
              <li v-for="childKey in childKeys" :key="childKey" class="tw:py-2">
                <strong>{{ labels[childKey] ?? childKey }}</strong>
                <span>
                  {{ formatPercent(childWithinSleeve(state, childKey)) }} within US sleeve
                </span>
                <span>
                  {{ formatPercent(childWholePortfolio(state, childKey)) }} of whole portfolio
                </span>
                <span>{{ formatUsd(childValue(state, childKey)) }}</span>
              </li>
            </ul>
            <Empty v-else role="status" aria-live="polite" class="component-empty tw:p-0">
              <EmptyHeader class="component-empty-header">
                <EmptyTitle role="heading" aria-level="5">No US sleeve component values</EmptyTitle>
                <EmptyDescription>No US sleeve component values were returned.</EmptyDescription>
              </EmptyHeader>
            </Empty>
          </CardContent>
        </Card>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty';
import { formatPercent, formatUsd } from '@/utils/display-values';
import type {
  TransitionSnapshotResponse,
  TransitionTargetResponse,
  USTransitionResponse,
} from '@/types/api';

type TransitionState = {
  key: 'current' | 'proposed' | 'target';
  title: string;
  snapshot: TransitionSnapshotResponse | null;
  target: TransitionTargetResponse | null;
};

const props = withDefaults(
  defineProps<{
    transition: USTransitionResponse | null;
    labels?: Record<string, string>;
    showNoCurrentBasket?: boolean;
  }>(),
  { labels: () => ({}), showNoCurrentBasket: false },
);

const labels = computed(() => props.labels);
const states = computed<TransitionState[]>(() => {
  if (!props.transition) return [];
  return [
    { key: 'current', title: 'Current', snapshot: props.transition.current, target: null },
    {
      key: 'proposed',
      title: 'Proposed basket',
      snapshot: props.transition.proposed_basket,
      target: null,
    },
    { key: 'target', title: 'Policy target', snapshot: null, target: props.transition.target },
  ];
});
const childKeys = computed(() => {
  if (!props.transition) return [];
  return [
    ...new Set([
      ...Object.keys(props.transition.current.children),
      ...Object.keys(props.transition.proposed_basket.children),
      ...Object.keys(props.transition.target.children),
    ]),
  ];
});

function childWithinSleeve(state: TransitionState, childKey: string): string | null {
  return (
    state.snapshot?.children[childKey]?.within_us_sleeve_pct ??
    state.target?.children[childKey]?.within_us_sleeve_pct ??
    null
  );
}

function childWholePortfolio(state: TransitionState, childKey: string): string | null {
  return (
    state.snapshot?.children[childKey]?.whole_portfolio_pct ??
    state.target?.children[childKey]?.whole_portfolio_pct ??
    null
  );
}

function childValue(state: TransitionState, childKey: string): string | null {
  return state.snapshot?.children[childKey]?.value_usd ?? null;
}
</script>

<style scoped>
.transition-title {
  color: var(--foreground);
  font-size: var(--tw-text-lg);
  font-weight: var(--tw-font-weight-semibold);
  line-height: var(--tw-text-lg--line-height);
  letter-spacing: var(--tw-tracking-tight);
}

.panel-description {
  max-width: 52rem;

  color: var(--muted-foreground);
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
}

.transition-notice {
  min-width: 0;
}

.transition-empty {
  min-width: 0;
  border: 1px dashed var(--border);
}

.transition-empty-header,
.component-empty-header {
  max-width: none;
  align-items: flex-start;
}

.transition-empty-title {
  color: var(--foreground);
  font-size: var(--tw-text-base);
  font-weight: var(--tw-font-weight-semibold);
  line-height: var(--tw-text-base--line-height);
}

.transition-empty-description {
  text-align: left;
}

/* negative-margin gutters distort grid tracks; native grid gap preserves widths. */
.state-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
}

.state-card {
  min-width: 0;
}

.transition-state-card {
  min-width: 0;
}

.transition-state-title {
  color: var(--foreground);
  font-size: var(--tw-text-base);
  font-weight: var(--tw-font-weight-semibold);
  line-height: var(--tw-text-base--line-height);
  letter-spacing: var(--tw-tracking-tight);
}

.state-summary {
  display: grid;
  gap: 8px;
}

.state-summary-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: baseline;
  gap: 8px;
  border-bottom: 1px solid var(--border);
}

.state-summary dt {
  color: var(--muted-foreground);
  font-size: var(--tw-text-xs);
  line-height: var(--tw-text-xs--line-height);
}

.state-summary dd {
  text-align: right;
  font-size: var(--tw-text-sm);
  font-weight: var(--tw-font-weight-semibold);
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}

.component-heading {
  color: var(--foreground);
  font-size: var(--tw-text-sm);
  font-weight: var(--tw-font-weight-semibold);
  line-height: var(--tw-text-sm--line-height);

  text-transform: uppercase;
}

.component-list {
  list-style: none;
}

.component-list li {
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-top: 1px solid var(--border);

  overflow-wrap: anywhere;
  font-size: var(--tw-text-sm);
}

.component-list strong {
  color: var(--foreground);
  font-size: var(--tw-text-sm);
  font-weight: var(--tw-font-weight-semibold);
}

.component-list span {
  color: var(--muted-foreground);
  font-variant-numeric: tabular-nums;
}

.component-empty {
  min-width: 0;
  gap: 8px;
  border: 0;

  text-align: left;
  align-items: flex-start;
}

.component-empty [data-slot='empty-title'] {
  color: var(--foreground);
  font-size: var(--tw-text-sm);
  font-weight: var(--tw-font-weight-medium);
  line-height: var(--tw-text-sm--line-height);
}

.component-empty [data-slot='empty-description'] {
  text-align: left;
}

@media (min-width: 901px) {
  .panel-heading {
    flex-direction: row;
  }

  .state-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
