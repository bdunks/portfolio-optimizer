<template>
  <section class="transition-panel" aria-labelledby="transition-title">
    <header class="panel-heading">
      <div>
        <h2 id="transition-title">US Equities Transition</h2>
        <p>
          {{ transition?.label ?? 'US sleeve' }} · API-reported values; percentages identify both
          within-sleeve and whole-portfolio units.
        </p>
      </div>
      <span class="unit-badge">Within US sleeve + whole portfolio</span>
    </header>

    <p v-if="showNoCurrentBasket" class="comparison-note" role="status">
      No current proposed basket from a matching current optimizer run. Values shown below come only
      from the portfolio API; historical or stale runs are not overlaid.
    </p>

    <p
      v-if="transition && transition.transition_destination_sleeve_key === null"
      class="comparison-note"
      role="status"
    >
      No transition destination is designated in this policy; progress is unavailable and no ETF or
      ticker is inferred.
    </p>

    <p v-if="!transition" class="empty-state">
      US transition data is unavailable from the portfolio API.
    </p>

    <div v-else class="state-grid">
      <article v-for="state in states" :key="state.key" class="state-card" :data-state="state.key">
        <h3>{{ state.title }}</h3>
        <dl class="state-summary">
          <div>
            <dt>US sleeve value</dt>
            <dd>{{ displayMoney(state.snapshot?.us_sleeve_value_usd) }}</dd>
          </div>
          <div>
            <dt>US sleeve share of portfolio</dt>
            <dd>
              {{
                displayPercent(
                  state.snapshot?.us_sleeve_whole_portfolio_pct ??
                    state.target?.us_sleeve_whole_portfolio_pct,
                )
              }}
            </dd>
          </div>
          <div>
            <dt>Transition destination progress within US sleeve</dt>
            <dd>{{ displayPercent(state.snapshot?.etf_progress_pct) }}</dd>
          </div>
        </dl>

        <h4>US sleeve components</h4>
        <ul v-if="childKeys.length" class="component-list">
          <li v-for="childKey in childKeys" :key="childKey">
            <strong>{{ labels[childKey] ?? childKey }}</strong>
            <span>{{ displayPercent(childWithinSleeve(state, childKey)) }} within US sleeve</span>
            <span
              >{{ displayPercent(childWholePortfolio(state, childKey)) }} of whole portfolio</span
            >
            <span>{{ displayMoney(childValue(state, childKey)) }}</span>
          </li>
        </ul>
        <p v-else class="empty-state">No US sleeve component values were returned.</p>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
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

function displayMoney(value: string | null | undefined): string {
  return value == null || value === '' ? 'Unavailable' : `${value} USD`;
}

function displayPercent(value: string | null | undefined): string {
  return value == null || value === '' ? 'Unavailable' : `${value}%`;
}

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
.transition-panel {
  display: grid;
  gap: 1rem;
}

.panel-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.panel-heading h2 {
  margin: 0;
  color: #10263d;
  font-size: 1.2rem;
}

.panel-heading p {
  margin: 0.3rem 0 0;
  color: #61798a;
  line-height: 1.5;
}

.unit-badge {
  flex: 0 0 auto;
  border-radius: 999px;
  background: #e4f5f2;
  color: #086f6e;
  padding: 0.35rem 0.65rem;
  font-size: 0.72rem;
  font-weight: 700;
}

.comparison-note {
  margin: 0;
  border-left: 3px solid #d19536;
  background: #fff7e9;
  color: #765016;
  padding: 0.75rem 0.9rem;
  line-height: 1.5;
}

.state-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.8rem;
}

.state-card {
  min-width: 0;
  border: 1px solid #dce6eb;
  border-radius: 0.75rem;
  padding: 1rem;
  background: #fff;
  box-shadow: 0 4px 20px rgb(18 55 77 / 4.5%);
}

.state-card h3 {
  margin: 0 0 0.8rem;
  color: #056b70;
  font-size: 0.95rem;
}

.state-summary {
  margin: 0;
  display: grid;
  gap: 0.45rem;
}

.state-summary div {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  border-bottom: 1px solid #eaf0f3;
  padding-bottom: 0.35rem;
}

.state-summary dt {
  color: #607889;
  font-size: 0.75rem;
}

.state-summary dd {
  margin: 0;
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-size: 0.8rem;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.state-card h4 {
  margin: 0.9rem 0 0.4rem;
  color: #526c7c;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.component-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.component-list li {
  display: grid;
  gap: 0.18rem;
  padding: 0.55rem 0;
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
  margin: 0;
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
