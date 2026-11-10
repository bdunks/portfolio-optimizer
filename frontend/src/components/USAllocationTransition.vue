<template>
  <section class="transition-panel column no-wrap q-gutter-y-md" aria-labelledby="transition-title">
    <header class="panel-heading row no-wrap justify-between items-start q-gutter-md">
      <div>
        <h2 class="q-ma-none text-h6" id="transition-title">US Equities Transition</h2>
        <p class="q-mt-xs q-mb-none q-mx-none text-body2">
          {{ transition?.label ?? 'US sleeve' }} · API-reported values; percentages identify both
          within-sleeve and whole-portfolio units.
        </p>
      </div>
      <q-chip dense :clickable="false" color="teal-1" text-color="teal-10" class="q-ma-none">
        Within US sleeve + whole portfolio
      </q-chip>
    </header>

    <q-banner
      v-if="showNoCurrentBasket"
      dense
      rounded
      class="q-my-sm bg-amber-1 text-brown-10"
      role="status"
    >
      No current proposed basket from a matching current optimizer run. Values shown below come only
      from the portfolio API; historical or stale runs are not overlaid.
    </q-banner>

    <q-banner
      v-if="transition && transition.transition_destination_sleeve_key === null"
      dense
      rounded
      class="q-my-sm bg-amber-1 text-brown-10"
      role="status"
    >
      No transition destination is designated in this policy; progress is unavailable and no ETF or
      ticker is inferred.
    </q-banner>

    <p v-if="!transition" class="empty-state q-mr-none q-mb-none q-ml-none">
      US transition data is unavailable from the portfolio API.
    </p>

    <div v-else class="state-grid">
      <q-card
        tag="article"
        v-for="state in states"
        :key="state.key"
        class="state-card q-pa-md"
        :data-state="state.key"
      >
        <h3 class="q-mt-none q-mb-md q-mx-none text-subtitle1">{{ state.title }}</h3>
        <dl class="state-summary q-mr-none q-mb-none q-ml-none column no-wrap q-gutter-y-sm">
          <div class="row no-wrap justify-between q-gutter-md q-pb-xs">
            <dt>US sleeve value</dt>
            <dd class="q-mr-none q-mb-none">
              {{ formatUsd(state.snapshot?.us_sleeve_value_usd) }}
            </dd>
          </div>
          <div class="row no-wrap justify-between q-gutter-md q-pb-xs">
            <dt>US sleeve share of portfolio</dt>
            <dd class="q-mr-none q-mb-none">
              {{
                formatPercent(
                  state.snapshot?.us_sleeve_whole_portfolio_pct ??
                    state.target?.us_sleeve_whole_portfolio_pct,
                )
              }}
            </dd>
          </div>
          <div class="row no-wrap justify-between q-gutter-md q-pb-xs">
            <dt>Transition destination progress within US sleeve</dt>
            <dd class="q-mr-none q-mb-none">
              {{ formatPercent(state.snapshot?.etf_progress_pct) }}
            </dd>
          </div>
        </dl>

        <h4 class="q-mt-md q-mb-sm q-mx-none text-caption text-uppercase">US sleeve components</h4>
        <ul v-if="childKeys.length" class="component-list q-ma-none q-pa-none">
          <li
            class="q-py-sm q-px-none column no-wrap q-gutter-y-xs"
            v-for="childKey in childKeys"
            :key="childKey"
          >
            <strong>{{ labels[childKey] ?? childKey }}</strong>
            <span>{{ formatPercent(childWithinSleeve(state, childKey)) }} within US sleeve</span>
            <span
              >{{ formatPercent(childWholePortfolio(state, childKey)) }} of whole portfolio</span
            >
            <span>{{ formatUsd(childValue(state, childKey)) }}</span>
          </li>
        </ul>
        <p v-else class="empty-state q-ma-none">No US sleeve component values were returned.</p>
      </q-card>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
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
/* Grid gaps use Quasar's spacing scale; negative-margin gutters distort grid tracks. */

.state-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.state-card {
  min-width: 0;
}

.state-summary div {
  border-bottom: 1px solid #eaf0f3;
}

.state-summary dt {
  color: #607889;
  font-size: 0.75rem;
}

.state-summary dd {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-size: 0.8rem;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.component-list {
  list-style: none;
}

.component-list li {
  border-top: 1px solid #eff3f5;
  font-size: 0.72rem;
}

.component-list strong {
  color: #213e50;
  font-size: 0.8rem;
}

.component-list span {
  color: #637c8b;
  font-variant-numeric: tabular-nums;
}

.empty-state {
  color: #718795;
  font-size: 0.82rem;
}

@media (max-width: 900px) {
  .state-grid {
    grid-template-columns: 1fr;
  }

  .panel-heading {
    flex-direction: column;
  }
}
</style>
