<template>
  <section
    class="transition-panel tw:min-w-0 tw:space-y-3"
    :aria-labelledby="showHeading ? 'transition-title' : 'transition-status-label'"
  >
    <header class="transition-heading">
      <div class="tw:min-w-0">
        <h2 v-if="showHeading" id="transition-title" class="transition-title tw:m-0">
          US Equities Transition Policy
        </h2>
        <span v-else id="transition-status-label" class="tw:sr-only">
          US allocation transition status
        </span>
        <p class="panel-description tw:mt-1">
          Configured targets guide a gradual, tax-constrained transition; they are not instructions
          to liquidate immediately.
        </p>
      </div>
      <Badge variant="secondary" class="tw:h-auto tw:whitespace-normal tw:text-center">
        {{ provenanceLabel }}
      </Badge>
    </header>

    <Alert
      v-if="snapshotStatus !== 'confirmed' && snapshotStatus !== 'saved'"
      role="status"
      aria-live="polite"
      class="transition-notice"
    >
      <AlertDescription>{{ snapshotStatusMessage }}</AlertDescription>
    </Alert>
    <Alert
      v-if="basketStatus !== 'confirmed' && basketStatus !== 'saved'"
      role="status"
      aria-live="polite"
      class="transition-notice"
    >
      <AlertDescription>{{ basketStatusMessage }}</AlertDescription>
    </Alert>
    <Alert
      v-if="
        transition && transition.transition_destination_sleeve_key === null && hasConfirmedSnapshot
      "
      role="status"
      aria-live="polite"
      class="transition-notice"
    >
      <AlertDescription>
        No transition destination is designated; progress is unavailable and no ETF, ticker, or
        sleeve name is inferred.
      </AlertDescription>
    </Alert>

    <div class="transition-headline tw:gap-x-4 tw:gap-y-2 tw:p-3" aria-live="polite">
      <strong
        v-if="
          transition &&
          transition.transition_destination_sleeve_key === null &&
          hasConfirmedSnapshot
        "
      >
        Set up US transition
      </strong>
      <strong v-else-if="transition && transition.transition_destination_sleeve_key === null"
        >Destination status unverified</strong
      >
      <strong v-else-if="transition && hasConfirmedSnapshot">Currently in new holdings</strong>
      <strong v-else-if="transition">Destination configured · progress unconfirmed</strong>
      <strong v-else>US transition data unavailable</strong>
      <span v-if="transition && transition.transition_destination_sleeve_key !== null">
        {{ displaySnapshotPercent(transition.current.etf_progress_pct) }} within US sleeve
      </span>
      <span
        v-else-if="
          transition &&
          transition.transition_destination_sleeve_key === null &&
          hasConfirmedSnapshot
        "
        >Designate a transition destination to make progress available.</span
      >
      <span v-else-if="transition"
        >Destination status is unavailable until current data is confirmed.</span
      >
      <span v-else>Current transition progress is unavailable.</span>
    </div>

    <div class="whole-portfolio-summary" aria-label="US sleeve share of whole portfolio">
      <div
        v-for="summary in wholePortfolioSummaries"
        :key="summary.key"
        class="tw:gap-1 tw:p-2.5 tw:px-3"
      >
        <span class="summary-label">{{ summary.label }}</span>
        <strong>{{ summary.value }}</strong>
      </div>
    </div>

    <div
      class="transition-table-region"
      role="region"
      aria-label="US allocation transition comparison"
      tabindex="0"
    >
      <table class="transition-table">
        <caption class="tw:px-3 tw:py-2">
          Current, after selected trades, and configured target percentages within the US sleeve
        </caption>
        <thead>
          <tr>
            <th class="tw:px-3 tw:py-2.5" scope="col">Allocation sleeve</th>
            <th class="tw:px-3 tw:py-2.5" scope="col">Current</th>
            <th class="tw:px-3 tw:py-2.5" scope="col">After selected trades</th>
            <th class="tw:px-3 tw:py-2.5" scope="col">Target</th>
          </tr>
        </thead>
        <tbody v-if="childKeys.length">
          <tr v-for="childKey in childKeys" :key="childKey">
            <th class="tw:px-3 tw:py-2.5" scope="row">
              <span>{{ labels[childKey] ?? childKey }}</span>
              <Badge
                v-if="roleLabel(childKey)"
                variant="outline"
                class="role-badge tw:mt-1 tw:ml-1"
              >
                {{ roleLabel(childKey) }}
              </Badge>
            </th>
            <td class="tw:px-3 tw:py-2.5">
              <strong>{{
                displaySnapshotPercent(transition?.current.children[childKey]?.within_us_sleeve_pct)
              }}</strong>
              <span class="unit-label tw:mt-1">within US sleeve</span>
            </td>
            <td class="tw:px-3 tw:py-2.5" :aria-label="basketCellAriaLabel(childKey)">
              <strong>{{ displayBasketPercent(childKey) }}</strong>
              <span v-if="hasBasketValues" class="unit-label tw:mt-1">within US sleeve</span>
            </td>
            <td class="tw:px-3 tw:py-2.5">
              <strong>{{
                displaySnapshotPercent(transition?.target.children[childKey]?.within_us_sleeve_pct)
              }}</strong>
              <span class="unit-label tw:mt-1">within US sleeve</span>
            </td>
          </tr>
        </tbody>
        <tbody v-else>
          <tr>
            <th class="tw:px-3 tw:py-2.5" scope="row">US allocation components</th>
            <td class="tw:px-3 tw:py-2.5" colspan="3">
              {{
                transition
                  ? 'No US allocation component values were returned.'
                  : 'US transition data unavailable.'
              }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { formatPercent, formatUsd } from '@/utils/display-values';
import type { USTransitionResponse } from '@/types/api';

type SnapshotStatus = 'confirmed' | 'saved' | 'pending' | 'stale' | 'unverified' | 'unavailable';
type BasketStatus =
  'confirmed' | 'saved' | 'no-selection' | 'pending' | 'stale' | 'unverified' | 'unavailable';
type TransitionRoleIdentity = {
  containerKey: string | null;
  legacyKey: string | null;
  destinationKey: string | null;
};

const props = withDefaults(
  defineProps<{
    transition: USTransitionResponse | null;
    labels?: Record<string, string>;
    snapshotStatus?: SnapshotStatus;
    basketStatus?: BasketStatus;
    roleIdentity?: TransitionRoleIdentity | null;
    provenance?: 'current_portfolio' | 'current_run' | 'saved_run';
    showHeading?: boolean;
  }>(),
  {
    labels: () => ({}),
    snapshotStatus: 'confirmed',
    basketStatus: 'no-selection',
    roleIdentity: null,
    provenance: 'current_portfolio',
    showHeading: true,
  },
);

const labels = computed(() => props.labels);
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
const hasConfirmedSnapshot = computed(
  () => props.snapshotStatus === 'confirmed' || props.snapshotStatus === 'saved',
);
const hasBasketValues = computed(
  () =>
    hasConfirmedSnapshot.value &&
    (props.basketStatus === 'confirmed' || props.basketStatus === 'saved'),
);
const provenanceLabel = computed(() => {
  if (props.provenance === 'saved_run') return 'Saved run · frozen context · read-only';
  if (props.provenance === 'current_run') return 'Current selected-basket API context';
  return 'Current portfolio API context';
});
const snapshotStatusMessage = computed(() => {
  switch (props.snapshotStatus) {
    case 'pending':
      return 'Current US transition data is pending confirmation; values are withheld.';
    case 'stale':
      return 'Current US transition data is stale; values are withheld. Review the freshness notice.';
    case 'unverified':
      return 'Current US transition provenance is unverified; values are withheld.';
    case 'unavailable':
      return 'Current US transition data is unavailable from the API.';
    default:
      return '';
  }
});
const basketStatusMessage = computed(() => {
  switch (props.basketStatus) {
    case 'no-selection':
      return 'No trades selected. Proposed values are not shown.';
    case 'pending':
      return 'Selected-trade effects are pending API confirmation; prior proposed values are withheld.';
    case 'stale':
      return 'Selected-trade effects are stale; no proposed values are shown.';
    case 'unverified':
      return 'Selected-trade context is unverified; no proposed values are shown.';
    case 'unavailable':
      return 'Selected-trade effects are unavailable; no proposed values are shown.';
    default:
      return '';
  }
});
const wholePortfolioSummaries = computed(() => {
  const transition = props.transition;
  return [
    {
      key: 'current',
      label: 'Current US sleeve · of whole portfolio',
      value: transition
        ? `${displaySnapshotUsd(transition.current.us_sleeve_value_usd)} · ${displaySnapshotPercent(transition.current.us_sleeve_whole_portfolio_pct)}`
        : 'Unavailable',
    },
    {
      key: 'proposed',
      label: 'After selected trades · of whole portfolio',
      value: transition
        ? hasBasketValues.value
          ? `${displayBasketUsd()} · ${displayBasketWholePortfolioPercent()}`
          : basketStatusMessage.value || 'Unavailable'
        : 'Unavailable',
    },
    {
      key: 'target',
      label: 'Target US sleeve · of whole portfolio',
      value: transition
        ? `${displaySnapshotPercent(transition.target.us_sleeve_whole_portfolio_pct)} · dollar value unavailable`
        : 'Unavailable',
    },
  ];
});

function roleLabel(childKey: string): string | null {
  const identity = props.roleIdentity;
  const transition = props.transition;
  if (!identity || !transition || identity.containerKey !== transition.sleeve_key) return null;
  if (
    identity.destinationKey !== null &&
    identity.destinationKey === transition.transition_destination_sleeve_key &&
    childKey === identity.destinationKey
  ) {
    return 'New holdings';
  }
  if (identity.legacyKey !== null && childKey === identity.legacyKey) return 'Legacy holdings';
  return null;
}

function snapshotStatusValue(): string {
  if (props.snapshotStatus === 'confirmed' || props.snapshotStatus === 'saved') return '';
  if (props.snapshotStatus === 'pending') return 'Pending';
  if (props.snapshotStatus === 'stale') return 'Unavailable (stale data)';
  if (props.snapshotStatus === 'unverified') return 'Unavailable (unverified data)';
  return 'Unavailable';
}

function displaySnapshotPercent(value: string | null | undefined): string {
  if (snapshotStatusValue()) return snapshotStatusValue();
  return formatPercent(value);
}

function displaySnapshotUsd(value: string | null | undefined): string {
  if (snapshotStatusValue()) return snapshotStatusValue();
  return formatUsd(value);
}

function displayBasketPercent(childKey: string): string {
  if (hasBasketValues.value && props.transition) {
    return formatPercent(props.transition.proposed_basket.children[childKey]?.within_us_sleeve_pct);
  }
  if (props.basketStatus === 'no-selection') return '—';
  if (props.basketStatus === 'pending') return 'Pending';
  if (props.basketStatus === 'stale') return 'Unavailable (stale effects)';
  if (props.basketStatus === 'unverified') return 'Unavailable (unverified effects)';
  return 'Unavailable';
}

function basketCellAriaLabel(childKey: string): string {
  if (hasBasketValues.value && props.transition) {
    return `${formatPercent(props.transition.proposed_basket.children[childKey]?.within_us_sleeve_pct)} within US sleeve`;
  }
  return basketStatusMessage.value || 'Selected-trade value unavailable';
}

function displayBasketUsd(): string {
  if (!props.transition || snapshotStatusValue()) return snapshotStatusValue() || 'Unavailable';
  return formatUsd(props.transition.proposed_basket.us_sleeve_value_usd);
}

function displayBasketWholePortfolioPercent(): string {
  if (!props.transition || snapshotStatusValue()) return snapshotStatusValue() || 'Unavailable';
  return formatPercent(props.transition.proposed_basket.us_sleeve_whole_portfolio_pct);
}
</script>

<style scoped>
/* Grid gaps use the shared 4px spacing scale; negative-margin gutters distort grid tracks. */
.transition-heading {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

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

.transition-headline {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: baseline;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--muted);
}

.transition-headline strong {
  color: var(--foreground);
  font-size: var(--tw-text-base);
}

.transition-headline span {
  color: var(--muted-foreground);
  font-size: var(--tw-text-sm);
  font-variant-numeric: tabular-nums;
}

.whole-portfolio-summary {
  display: grid;
  min-width: 0;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 13rem), 1fr));
  gap: 8px;
}

.whole-portfolio-summary > div {
  display: grid;
  min-width: 0;
  gap: 4px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.summary-label,
.unit-label {
  color: var(--muted-foreground);
  font-size: var(--tw-text-xs);
  line-height: 1.4;
}

.whole-portfolio-summary strong {
  overflow-wrap: anywhere;
  color: var(--foreground);
  font-size: var(--tw-text-sm);
  font-variant-numeric: tabular-nums;
}

.transition-table-region {
  min-width: 0;
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.transition-table-region:focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 2px;
}

.transition-table {
  width: 100%;
  min-width: 42rem;
  border-collapse: collapse;
  text-align: left;
  font-size: var(--tw-text-sm);
}

.transition-table caption {
  color: var(--muted-foreground);
  text-align: left;
  font-size: var(--tw-text-xs);
}

.transition-table th,
.transition-table td {
  border-top: 1px solid var(--border);
  vertical-align: top;
}

.transition-table thead th {
  color: var(--muted-foreground);
  font-weight: var(--tw-font-weight-medium);
}

.transition-table tbody th {
  min-width: 10rem;
  color: var(--foreground);
  font-weight: var(--tw-font-weight-medium);
}

.transition-table td strong {
  display: block;
  color: var(--foreground);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.unit-label {
  display: block;
}

.role-badge {
  display: inline-flex;
  min-height: 1.25rem;
  vertical-align: middle;
}

@media (max-width: 640px) {
  .transition-heading {
    flex-direction: column;
  }
}
</style>
