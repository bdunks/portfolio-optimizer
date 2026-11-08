<template>
  <q-page class="overview-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Workspace overview</p>
        <h1>Overview</h1>
        <p class="page-subtitle">
          Current account state and API-supplied allocation context for a single local workspace.
        </p>
      </div>
      <div class="page-actions">
        <q-btn
          outline
          color="primary"
          icon="sync"
          label="Sync portfolio"
          no-caps
          :loading="store.actionState.syncPortfolio.pending"
          :disable="store.actionState.syncPortfolio.pending"
          @click="syncPortfolio"
        />
        <q-btn
          unelevated
          color="primary"
          icon="play_arrow"
          label="Run DEMO recommendations"
          no-caps
          :loading="store.actionState.runOptimizer.pending"
          :disable="!canRunOptimizer"
          @click="runOptimizer"
        />
      </div>
    </header>

    <p v-if="!canRunOptimizer" class="run-help">
      Recommendations require a ready portfolio snapshot and a valid active policy. Nothing runs
      automatically.
    </p>

    <div class="error-stack" aria-label="Workspace request errors">
      <ApiActionError
        :error="store.actionState.loadHealth.error"
        title="Application health could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.loadPortfolio.error"
        title="Portfolio data could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.loadPolicy.error"
        title="Allocation policy could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.syncPortfolio.error"
        title="Portfolio sync or refresh failed"
      />
      <ApiActionError
        :error="store.actionState.runOptimizer.error"
        title="Recommendation run failed"
      />
    </div>

    <q-banner class="overview-demo-banner" rounded>
      <strong>DEMO analysis only.</strong> Recommendations are non-actionable; no broker calls,
      OAuth, live writes, or orders are available.
    </q-banner>

    <section class="summary-grid" aria-label="Current portfolio summary">
      <q-card flat bordered class="summary-card">
        <q-card-section>
          <p class="summary-label">Portfolio value</p>
          <p class="summary-value">{{ displayMoney(portfolio?.portfolio_total_usd) }}</p>
          <p class="summary-foot">Value returned by the portfolio API</p>
        </q-card-section>
      </q-card>
      <q-card flat bordered class="summary-card">
        <q-card-section>
          <p class="summary-label">Cash</p>
          <p class="summary-value">{{ displayMoney(portfolio?.cash_usd) }}</p>
          <p class="summary-foot">Cash balance returned by the portfolio API</p>
        </q-card-section>
      </q-card>
      <q-card flat bordered class="summary-card">
        <q-card-section>
          <p class="summary-label">Positions</p>
          <p class="summary-value">{{ positionCount }}</p>
          <p class="summary-foot">Current API position count</p>
        </q-card-section>
      </q-card>
      <q-card flat bordered class="summary-card">
        <q-card-section>
          <p class="summary-label">Risk tracking</p>
          <p class="summary-value summary-value-small">Not calculated</p>
          <p class="summary-foot">No risk estimate is available from this workflow</p>
        </q-card-section>
      </q-card>
    </section>

    <section class="content-grid">
      <q-card flat bordered class="workspace-card account-card">
        <q-card-section>
          <div class="section-heading">
            <div>
              <h2>Portfolio data</h2>
              <p class="section-subtitle">Source status and coverage from the backend API</p>
            </div>
            <q-badge
              :color="portfolio?.status === 'ready' ? 'positive' : 'warning'"
              text-color="dark"
            >
              {{ portfolioStatusLabel }}
            </q-badge>
          </div>

          <dl class="data-list">
            <div>
              <dt>Account</dt>
              <dd>{{ accountLabel }}</dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>{{ portfolio?.status === 'ready' ? portfolio.source : 'Unavailable' }}</dd>
            </div>
            <div>
              <dt>Data as of</dt>
              <dd>{{ portfolio?.as_of ?? 'Unavailable' }}</dd>
            </div>
            <div>
              <dt>Sync generation</dt>
              <dd>{{ portfolio ? String(portfolio.sync.generation) : 'Unavailable' }}</dd>
            </div>
            <div>
              <dt>Last completed sync</dt>
              <dd>{{ portfolio?.sync.completed_at ?? 'Unavailable' }}</dd>
            </div>
            <div>
              <dt>Last sync error</dt>
              <dd>
                <template v-if="portfolio?.sync.last_error_code">
                  {{ portfolio.sync.last_error_code }}:
                  {{ portfolio.sync.last_error_summary ?? 'No summary returned' }}
                </template>
                <template v-else>None reported</template>
              </dd>
            </div>
          </dl>

          <p v-if="portfolio?.status === 'not_synced'" class="empty-note">
            The current portfolio snapshot has not been synchronized. Use Sync portfolio to request
            the configured local demo snapshot.
          </p>

          <div class="coverage-block">
            <h3>Data coverage</h3>
            <p v-if="coverageEntries.length === 0" class="empty-note">
              Coverage is unavailable until portfolio data loads.
            </p>
            <ul v-else class="coverage-list">
              <li v-for="[key, covered] in coverageEntries" :key="key">
                <span>{{ key }}</span>
                <strong :class="covered ? 'coverage-yes' : 'coverage-no'">{{
                  covered ? 'Available' : 'Unavailable'
                }}</strong>
              </li>
            </ul>
          </div>
        </q-card-section>
      </q-card>

      <q-card flat bordered class="workspace-card run-card">
        <q-card-section>
          <div class="section-heading">
            <div>
              <h2>Latest recommendations</h2>
              <p class="section-subtitle">
                Metrics are shown only for a run matching this current portfolio and active policy.
              </p>
            </div>
            <q-badge v-if="currentRunMatches" color="warning" text-color="dark"
              >DEMO · non-actionable</q-badge
            >
          </div>

          <p v-if="!currentRunMatches" class="empty-note">
            No current matching recommendation run. Saved or stale runs are not used as current
            portfolio comparisons.
          </p>
          <dl v-else class="data-list run-metrics">
            <div>
              <dt>Realized short-term P/L (estimated)</dt>
              <dd>{{ displayMoney(store.currentRun?.estimated_realized_st_usd) }}</dd>
            </div>
            <div>
              <dt>Realized long-term P/L (estimated)</dt>
              <dd>{{ displayMoney(store.currentRun?.estimated_realized_lt_usd) }}</dd>
            </div>
            <div>
              <dt>Estimated tax benefit</dt>
              <dd>{{ displayMoney(store.currentRun?.estimated_tax_benefit_usd) }}</dd>
            </div>
            <div>
              <dt>Lots sold / positions exited</dt>
              <dd>
                {{ displayCount(store.currentRun?.lots_sold_count) }} /
                {{ displayCount(store.currentRun?.positions_exited_count) }}
              </dd>
            </div>
            <div>
              <dt>Orders in recommendation</dt>
              <dd>{{ displayCount(store.currentRun?.orders_count) }}</dd>
            </div>
            <div>
              <dt>Cash before / after</dt>
              <dd>
                {{ displayMoney(store.currentRun?.cash_before_usd) }} /
                {{ displayMoney(store.currentRun?.cash_after_usd) }}
              </dd>
            </div>
            <div>
              <dt>Tax estimate status</dt>
              <dd>{{ store.currentRun?.estimated_tax_benefit_status ?? 'Unavailable' }}</dd>
            </div>
          </dl>
        </q-card-section>
      </q-card>

      <q-card flat bordered class="workspace-card allocation-card">
        <q-card-section>
          <AllocationTargets
            :allocation="allocation"
            :labels="policyLabels"
            :show-no-current-basket="!currentRunAllocationAvailable"
          />
        </q-card-section>
      </q-card>

      <q-card flat bordered class="workspace-card transition-card">
        <q-card-section>
          <USAllocationTransition
            :transition="usTransition"
            :labels="policyLabels"
            :show-no-current-basket="!currentRunTransitionAvailable"
          />
        </q-card-section>
      </q-card>

      <q-card flat bordered class="workspace-card policy-card">
        <q-card-section>
          <div class="section-heading">
            <div>
              <h2>Active allocation policy</h2>
              <p class="section-subtitle">
                Policy settings and allowed securities supplied by the API
              </p>
            </div>
            <q-badge :color="activePolicy ? 'positive' : 'warning'" text-color="dark">
              {{ activePolicy ? `Revision ${activePolicy.revision_number}` : 'No active policy' }}
            </q-badge>
          </div>

          <p v-if="!activePolicy" class="empty-note">No active policy has been returned.</p>
          <template v-else>
            <h3>Enabled sleeves and targets</h3>
            <ul v-if="enabledSleeves.length" class="policy-list">
              <li v-for="sleeve in enabledSleeves" :key="sleeve.sleeve_key">
                <span>{{ sleeve.display_name }}</span>
                <strong>{{ sleeve.target_pct }}%</strong>
              </li>
            </ul>
            <p v-else class="empty-note">No enabled sleeves were returned.</p>

            <h3 class="policy-subhead">Allowed securities</h3>
            <ul v-if="enabledSecurities.length" class="security-list">
              <li
                v-for="security in enabledSecurities"
                :key="`${security.sleeve_key}:${security.ticker}`"
              >
                <strong>{{ security.ticker }}</strong>
                <span>{{ policyLabels[security.sleeve_key] ?? security.sleeve_key }}</span>
              </li>
            </ul>
            <p v-else class="empty-note">No enabled allowed securities were returned.</p>
          </template>
        </q-card-section>
      </q-card>
    </section>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AllocationTargets from '@/components/AllocationTargets.vue';
import ApiActionError from '@/components/ApiActionError.vue';
import USAllocationTransition from '@/components/USAllocationTransition.vue';
import { useWorkspaceStore } from '@/stores/workspace-store';
import { displayCount, displayMoney, isMatchingCurrentRun } from './overview-state';

const store = useWorkspaceStore();
const router = useRouter();
const portfolio = computed(() => store.portfolio);
const activePolicy = computed(() => store.policy?.active ?? null);
const currentRunMatches = computed(() =>
  isMatchingCurrentRun(
    portfolio.value?.status === 'ready' ? portfolio.value : null,
    store.currentRun,
    store.currentRunView,
    store.proposedRunIsStale,
  ),
);
const currentRunAllocationAvailable = computed(
  () => currentRunMatches.value && store.currentRun?.portfolio_effects?.allocation != null,
);
const currentRunTransitionAvailable = computed(
  () => currentRunMatches.value && store.currentRun?.portfolio_effects?.us_transition != null,
);
const policyLabels = computed(() =>
  Object.fromEntries(
    (activePolicy.value?.sleeves ?? []).map((sleeve) => [sleeve.sleeve_key, sleeve.display_name]),
  ),
);
const allocation = computed(() => {
  if (currentRunAllocationAvailable.value) {
    return store.currentRun?.portfolio_effects?.allocation ?? null;
  }
  return portfolio.value?.allocation ?? null;
});
const usTransition = computed(() => {
  if (currentRunTransitionAvailable.value) {
    return store.currentRun?.portfolio_effects?.us_transition ?? null;
  }
  return portfolio.value?.us_transition ?? null;
});
const coverageEntries = computed(() => Object.entries(portfolio.value?.coverage ?? {}));
const positionCount = computed(() => {
  const value = portfolio.value;
  if (!value) return 'Unavailable';
  return displayCount(value.status === 'ready' ? value.position_count : value.positions.length);
});
const accountLabel = computed(() => {
  const value = portfolio.value;
  if (!value) return 'Unavailable';
  return value.status === 'ready' ? value.account.display_name : 'No synchronized account';
});
const portfolioStatusLabel = computed(() => {
  const value = portfolio.value;
  if (!value) return 'Loading';
  return value.status === 'ready' ? 'Snapshot ready' : 'Not synchronized';
});
const enabledSleeves = computed(() =>
  (activePolicy.value?.sleeves ?? []).filter((sleeve) => sleeve.enabled),
);
const enabledSecurities = computed(() =>
  (activePolicy.value?.allowed_securities ?? []).filter((security) => security.enabled),
);
const canRunOptimizer = computed(
  () =>
    portfolio.value?.status === 'ready' &&
    portfolio.value.sync.complete &&
    store.health?.status === 'ok' &&
    store.health.schema_ready &&
    activePolicy.value !== null &&
    portfolio.value.active_policy_revision_id === activePolicy.value.id &&
    (activePolicy.value.activation_errors?.length ?? 0) === 0 &&
    !store.actionState.syncPortfolio.pending &&
    !store.actionState.runOptimizer.pending,
);

function loadInitialWorkspace(): void {
  const requests: Promise<unknown>[] = [];
  if (!store.health) requests.push(store.loadHealth());
  if (!store.portfolio) requests.push(store.loadPortfolio());
  if (!store.policy) requests.push(store.loadPolicy());
  void Promise.allSettled(requests);
}

async function syncPortfolio(): Promise<void> {
  try {
    await store.syncPortfolio();
  } catch {
    // The store retains a structured ApiError for visible presentation in this page.
  }
}

async function runOptimizer(): Promise<void> {
  if (!canRunOptimizer.value) return;
  try {
    await store.runOptimizer({});
    await router.push('/recommendations');
  } catch {
    // The store retains a structured ApiError for visible presentation in this page.
  }
}

onMounted(loadInitialWorkspace);
</script>

<style scoped>
.overview-page {
  display: grid;
  gap: 1.1rem;
  max-width: 1800px;
  margin: 0 auto;
  padding: clamp(1rem, 2.5vw, 2rem);
}

.page-header,
.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.page-header h1 {
  margin: 0;
  color: #10263d;
  font-size: clamp(1.7rem, 3vw, 2rem);
  letter-spacing: -0.04em;
}

.eyebrow {
  margin: 0 0 0.25rem;
  color: #087f7d;
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.page-subtitle,
.section-subtitle {
  margin: 0.3rem 0 0;
  color: #637b8a;
  font-size: 0.82rem;
  line-height: 1.5;
}

.page-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.55rem;
}

.run-help,
.empty-note {
  margin: 0;
  color: #657d8b;
  font-size: 0.8rem;
  line-height: 1.55;
}

.run-help {
  padding-left: 0.8rem;
  border-left: 3px solid #d4a24f;
}

.error-stack {
  display: grid;
  gap: 0.55rem;
}

.overview-demo-banner {
  border: 1px solid #f2dcad;
  background: #fff7e8;
  color: #765016;
  font-size: 0.82rem;
  line-height: 1.5;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.8rem;
}

.summary-card,
.workspace-card {
  min-width: 0;
  border-color: #dce6eb;
  border-radius: 0.8rem;
  background: #fff;
  box-shadow: 0 4px 20px rgb(18 55 77 / 4.5%);
}

.summary-card {
  min-height: 7.2rem;
}

.summary-card :deep(.q-card__section) {
  padding: 1rem 1.1rem;
}

.summary-label {
  margin: 0;
  color: #466779;
  font-size: 0.75rem;
  font-weight: 750;
}

.summary-value {
  margin: 0.45rem 0 0;
  color: #172e41;
  font-size: clamp(1.1rem, 2vw, 1.45rem);
  font-weight: 820;
  letter-spacing: -0.04em;
  overflow-wrap: anywhere;
}

.summary-value-small {
  font-size: 1rem;
}

.summary-foot {
  margin: 0.3rem 0 0;
  color: #748894;
  font-size: 0.68rem;
  line-height: 1.4;
}

.content-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.85rem;
  align-items: start;
}

.workspace-card :deep(.q-card__section) {
  padding: clamp(1rem, 2vw, 1.25rem);
}

.section-heading {
  align-items: center;
  margin-bottom: 1rem;
}

.section-heading h2 {
  margin: 0;
  color: #10263d;
  font-size: 1.08rem;
  letter-spacing: -0.025em;
}

.section-heading .section-subtitle {
  max-width: 40rem;
  font-size: 0.76rem;
}

.account-card,
.run-card,
.allocation-card,
.transition-card,
.policy-card {
  grid-column: span 1;
}

.transition-card {
  grid-column: 1 / -1;
}

.data-list {
  display: grid;
  gap: 0;
  margin: 0;
}

.data-list > div {
  display: grid;
  grid-template-columns: minmax(10rem, 0.8fr) minmax(0, 1.2fr);
  gap: 0.7rem;
  padding: 0.6rem 0;
  border-bottom: 1px solid #eaf0f3;
}

.data-list dt {
  color: #647c8b;
  font-size: 0.75rem;
}

.data-list dd {
  margin: 0;
  color: #29475a;
  font-size: 0.78rem;
  font-weight: 650;
  overflow-wrap: anywhere;
}

.run-metrics > div {
  grid-template-columns: minmax(11rem, 1fr) minmax(0, 1fr);
}

.coverage-block {
  margin-top: 1.1rem;
}

.coverage-block h3,
.policy-card h3 {
  margin: 0 0 0.5rem;
  color: #526c7c;
  font-size: 0.76rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.coverage-list,
.policy-list,
.security-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.coverage-list li,
.policy-list li,
.security-list li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.7rem;
  padding: 0.55rem 0;
  border-bottom: 1px solid #edf2f4;
  color: #405f71;
  font-size: 0.76rem;
  overflow-wrap: anywhere;
}

.coverage-yes,
.coverage-no {
  font-size: 0.7rem;
}

.coverage-yes {
  color: #137a60;
}

.coverage-no {
  color: #9b6060;
}

.policy-list strong {
  color: #067777;
  white-space: nowrap;
}

.policy-subhead {
  margin-top: 1.1rem !important;
}

.security-list li {
  justify-content: flex-start;
}

.security-list strong {
  min-width: 5rem;
  color: #087574;
}

@media (max-width: 980px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .content-grid {
    grid-template-columns: 1fr;
  }

  .account-card,
  .run-card,
  .allocation-card,
  .transition-card,
  .policy-card {
    grid-column: auto;
  }
}

@media (max-width: 620px) {
  .page-header,
  .section-heading {
    flex-direction: column;
    align-items: stretch;
  }

  .page-actions {
    justify-content: flex-start;
  }

  .page-actions :deep(.q-btn) {
    flex: 1 1 auto;
  }

  .summary-grid {
    grid-template-columns: 1fr 1fr;
    gap: 0.55rem;
  }

  .summary-card {
    min-height: 6.5rem;
  }

  .summary-card :deep(.q-card__section) {
    padding: 0.75rem;
  }

  .data-list > div,
  .run-metrics > div {
    grid-template-columns: 1fr;
    gap: 0.25rem;
  }
}
</style>
