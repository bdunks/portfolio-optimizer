<template>
  <q-page class="workspace-page overview-page q-my-none q-mx-auto q-pa-md">
    <WorkspacePageHeader
      eyebrow="Workspace overview"
      title="Overview"
      title-id="overview-title"
      subtitle="Current account state and API-supplied allocation context for a single local workspace."
    >
      <template #actions>
        <q-btn
          outline
          color="primary"
          icon="sync"
          class="overview-page-action"
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
          class="overview-page-action"
          label="Run DEMO recommendations"
          no-caps
          :loading="store.actionState.runOptimizer.pending"
          :disable="!canRunOptimizer"
          @click="runOptimizer"
        />
      </template>
    </WorkspacePageHeader>

    <p v-if="!canRunOptimizer" class="run-help q-ma-none q-pl-md">
      Recommendations require a ready portfolio snapshot and a valid active policy. Nothing runs
      automatically.
    </p>

    <div class="error-stack column no-wrap q-gutter-y-sm" aria-label="Workspace request errors">
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

    <ResourceFreshnessNotice />
    <q-banner
      v-if="portfolioLabelContext.revisionMismatch"
      dense
      rounded
      class="q-my-sm bg-blue-grey-1 text-blue-grey-10"
      role="status"
    >
      Portfolio effects use policy revision
      {{ portfolioLabelContext.portfolioRevisionId ?? 'unavailable' }}; the active policy is
      {{ portfolioLabelContext.policyRevisionId ?? 'unavailable' }}. Cached values remain visible
      with API sleeve keys until matching policy labels are confirmed.
    </q-banner>
    <WorkspaceCapabilityNotice label="DEMO analysis only.">
      Recommendations are non-actionable; no broker calls, OAuth, live writes, or orders are
      available.
    </WorkspaceCapabilityNotice>

    <section class="summary-grid" aria-label="Current portfolio summary">
      <q-card flat bordered class="summary-card">
        <q-card-section>
          <p class="q-ma-none text-caption text-weight-bold text-blue-grey-8">Portfolio value</p>
          <p class="q-mt-sm q-mb-none q-mx-none text-h6 text-weight-bold text-blue-grey-10">
            {{ formatUsd(portfolio?.portfolio_total_usd) }}
          </p>
          <p class="q-mt-xs q-mb-none q-mx-none text-caption text-blue-grey-6">
            Value returned by the portfolio API
          </p>
        </q-card-section>
      </q-card>
      <q-card flat bordered class="summary-card">
        <q-card-section>
          <p class="q-ma-none text-caption text-weight-bold text-blue-grey-8">Cash</p>
          <p class="q-mt-sm q-mb-none q-mx-none text-h6 text-weight-bold text-blue-grey-10">
            {{ formatUsd(portfolio?.cash_usd) }}
          </p>
          <p class="q-mt-xs q-mb-none q-mx-none text-caption text-blue-grey-6">
            Cash balance returned by the portfolio API
          </p>
        </q-card-section>
      </q-card>
      <q-card flat bordered class="summary-card">
        <q-card-section>
          <p class="q-ma-none text-caption text-weight-bold text-blue-grey-8">Positions</p>
          <p class="q-mt-sm q-mb-none q-mx-none text-h6 text-weight-bold text-blue-grey-10">
            {{ positionCount }}
          </p>
          <p class="q-mt-xs q-mb-none q-mx-none text-caption text-blue-grey-6">
            Current API position count
          </p>
        </q-card-section>
      </q-card>
      <q-card flat bordered class="summary-card">
        <q-card-section>
          <p class="q-ma-none text-caption text-weight-bold text-blue-grey-8">Risk tracking</p>
          <p class="q-mt-sm q-mb-none q-mx-none text-subtitle1 text-weight-bold text-blue-grey-10">
            Not calculated
          </p>
          <p class="q-mt-xs q-mb-none q-mx-none text-caption text-blue-grey-6">
            No risk estimate is available from this workflow
          </p>
        </q-card-section>
      </q-card>
    </section>

    <section class="content-grid items-start">
      <q-card flat bordered class="workspace-card account-card">
        <q-card-section>
          <div class="section-heading row justify-between q-gutter-md items-center q-mb-md">
            <div>
              <h2 class="q-ma-none text-subtitle1 text-blue-grey-10">Portfolio data</h2>
              <p class="section-subtitle q-mt-sm q-mb-none q-mx-none">
                Source status and coverage from the backend API
              </p>
            </div>
            <q-badge
              :color="portfolio?.status === 'ready' ? 'positive' : 'warning'"
              text-color="dark"
            >
              {{ portfolioStatusLabel }}
            </q-badge>
          </div>

          <dl class="data-list q-ma-none column no-wrap q-gutter-y-none">
            <div class="q-py-sm q-px-none">
              <dt>Account</dt>
              <dd class="q-ma-none">{{ accountLabel }}</dd>
            </div>
            <div class="q-py-sm q-px-none">
              <dt>Source</dt>
              <dd class="q-ma-none">
                {{ portfolio?.status === 'ready' ? portfolio.source : 'Unavailable' }}
              </dd>
            </div>
            <div class="q-py-sm q-px-none">
              <dt>Data as of</dt>
              <dd class="q-ma-none">{{ portfolio?.as_of ?? 'Unavailable' }}</dd>
            </div>
            <div class="q-py-sm q-px-none">
              <dt>Sync generation</dt>
              <dd class="q-ma-none">
                {{ portfolio ? String(portfolio.sync.generation) : 'Unavailable' }}
              </dd>
            </div>
            <div class="q-py-sm q-px-none">
              <dt>Last completed sync</dt>
              <dd class="q-ma-none">{{ portfolio?.sync.completed_at ?? 'Unavailable' }}</dd>
            </div>
            <div class="q-py-sm q-px-none">
              <dt>Last sync error</dt>
              <dd class="q-ma-none">
                <template v-if="portfolio?.sync.last_error_code">
                  {{ portfolio.sync.last_error_code }}:
                  {{ portfolio.sync.last_error_summary ?? 'No summary returned' }}
                </template>
                <template v-else>None reported</template>
              </dd>
            </div>
          </dl>

          <p v-if="portfolio?.status === 'not_synced'" class="empty-note q-ma-none">
            The current portfolio snapshot has not been synchronized. Use Sync portfolio to request
            the configured local demo snapshot.
          </p>

          <div class="coverage-block q-mt-md">
            <h3 class="q-mt-none q-mb-sm q-mx-none text-subtitle2 text-blue-grey-8 text-uppercase">
              Data coverage
            </h3>
            <p v-if="coverageEntries.length === 0" class="empty-note q-ma-none">
              Coverage is unavailable until portfolio data loads.
            </p>
            <ul v-else class="coverage-list q-ma-none q-pa-none">
              <li
                class="row no-wrap justify-between items-center q-gutter-sm q-py-sm q-px-none"
                v-for="[key, covered] in coverageEntries"
                :key="key"
              >
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
          <div class="section-heading row justify-between q-gutter-md items-center q-mb-md">
            <div>
              <h2 class="q-ma-none text-subtitle1 text-blue-grey-10">Latest recommendations</h2>
              <p class="section-subtitle q-mt-sm q-mb-none q-mx-none">
                Metrics are shown only for a run matching this current portfolio and active policy.
              </p>
            </div>
            <q-badge v-if="currentRunMatches" color="warning" text-color="dark"
              >DEMO · non-actionable</q-badge
            >
          </div>

          <p v-if="!currentRunMatches" class="empty-note q-ma-none">
            No current matching recommendation run. Saved or stale runs are not used as current
            portfolio comparisons.
          </p>
          <RunSummary
            v-if="store.currentRun || store.currentRunSummary"
            mode="overview"
            :run="store.currentRun"
            :summary="store.currentRunSummary"
            :context="runDisplayContext"
            :pending="runPresentation.reviewMutationPending"
            :show-metrics="currentRunMatches"
            :view="store.currentRunView"
          />
        </q-card-section>
      </q-card>

      <q-card flat bordered class="workspace-card allocation-card">
        <q-card-section>
          <AllocationTargets
            :allocation="allocation"
            :labels="effectLabels"
            :show-no-current-basket="!currentRunAllocationAvailable"
          />
        </q-card-section>
      </q-card>

      <q-card flat bordered class="workspace-card transition-card">
        <q-card-section>
          <USAllocationTransition
            :transition="usTransition"
            :labels="effectLabels"
            :show-no-current-basket="!currentRunTransitionAvailable"
          />
        </q-card-section>
      </q-card>

      <q-card flat bordered class="workspace-card policy-card">
        <q-card-section>
          <div class="section-heading row justify-between q-gutter-md items-center q-mb-md">
            <div>
              <h2 class="q-ma-none text-subtitle1 text-blue-grey-10">Active allocation policy</h2>
              <p class="section-subtitle q-mt-sm q-mb-none q-mx-none">
                Policy settings and allowed securities supplied by the API
              </p>
            </div>
            <q-badge :color="activePolicy ? 'positive' : 'warning'" text-color="dark">
              {{ activePolicy ? `Revision ${activePolicy.revision_number}` : 'No active policy' }}
            </q-badge>
          </div>

          <p v-if="!activePolicy" class="empty-note q-ma-none">
            No active policy has been returned.
          </p>
          <template v-else>
            <h3 class="q-mt-none q-mb-sm q-mx-none text-subtitle2 text-blue-grey-8 text-uppercase">
              Enabled sleeves and targets
            </h3>
            <ul v-if="enabledSleeves.length" class="policy-list q-ma-none q-pa-none">
              <li
                class="row no-wrap justify-between items-center q-gutter-sm q-py-sm q-px-none"
                v-for="sleeve in enabledSleeves"
                :key="sleeve.sleeve_key"
              >
                <span>{{ sleeve.display_name }}</span>
                <strong>{{ formatPercent(sleeve.target_pct) }}</strong>
              </li>
            </ul>
            <p v-else class="empty-note q-ma-none">No enabled sleeves were returned.</p>

            <h3
              class="policy-subhead q-mt-md q-mb-sm q-mx-none text-subtitle2 text-blue-grey-8 text-uppercase"
            >
              Allowed securities
            </h3>
            <ul v-if="enabledSecurities.length" class="security-list q-ma-none q-pa-none">
              <li
                class="row no-wrap items-center q-gutter-sm justify-start q-py-sm q-px-none"
                v-for="security in enabledSecurities"
                :key="`${security.sleeve_key}:${security.ticker}`"
              >
                <strong>{{ security.ticker }}</strong>
                <span>{{ policyLabels[security.sleeve_key] ?? security.sleeve_key }}</span>
              </li>
            </ul>
            <p v-else class="empty-note q-ma-none">No enabled allowed securities were returned.</p>
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
import RunSummary from '@/components/RunSummary.vue';
import WorkspacePageHeader from '@/components/WorkspacePageHeader.vue';
import WorkspaceCapabilityNotice from '@/components/WorkspaceCapabilityNotice.vue';
import { formatPercent, formatUsd } from '@/utils/display-values';
import USAllocationTransition from '@/components/USAllocationTransition.vue';
import { useWorkspaceStore } from '@/stores/workspace-store';
import { displayCount } from './overview-state';

import { completeFrozenRunSleeveLabels } from './run-context';
import {
  selectPortfolioLabelContext,
  selectRunPresentation,
  selectWorkspaceReadiness,
} from '@/stores/workspace-selectors';
import ResourceFreshnessNotice from '@/components/ResourceFreshnessNotice.vue';

const store = useWorkspaceStore();
const router = useRouter();
const portfolio = computed(() => store.portfolio);
const activePolicy = computed(() => store.policy?.active ?? null);
const runPresentation = computed(() =>
  selectRunPresentation({
    run: store.currentRun,
    summary: store.currentRunSummary,
    view: store.currentRunView,
    proposedRunIsStale: store.proposedRunIsStale,
    health: store.health,
    portfolio: portfolio.value,
    activePolicy: activePolicy.value,
    resourceFreshness: store.resourceFreshness,

    resourceReadsPending: store.workspaceResourceLoadPending,
    reviewMutationPending: store.reviewMutationPending,
  }),
);
const runDisplayContext = computed(() => runPresentation.value.displayContext);
const currentRunMatches = computed(() => runPresentation.value.currentRunMatches);

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
const portfolioLabelContext = computed(() => {
  const allocation = portfolio.value?.allocation;
  const transition = portfolio.value?.us_transition;
  const sleeveKeys = [
    ...Object.keys(allocation?.current?.sleeve_weights_pct ?? {}),
    ...Object.keys(allocation?.proposed?.sleeve_weights_pct ?? {}),
    ...Object.keys(allocation?.target?.sleeve_weights_pct ?? {}),
    ...(transition
      ? [
          transition.sleeve_key,
          ...(transition.transition_destination_sleeve_key
            ? [transition.transition_destination_sleeve_key]
            : []),
          ...Object.keys(transition.current.children),
          ...Object.keys(transition.proposed_basket.children),
          ...Object.keys(transition.target.children),
        ]
      : []),
  ];
  return selectPortfolioLabelContext({
    portfolio: portfolio.value,
    activePolicy: activePolicy.value,
    sleeveKeys,
  });
});
const runContextLabels = computed(() => {
  const run = store.currentRun;
  const allocation = run?.portfolio_effects?.allocation;
  const transition = run?.portfolio_effects?.us_transition;
  const sleeveKeys = [
    ...(run?.groups.map((group) => group.sleeve_key) ?? []),
    ...Object.keys(allocation?.current?.sleeve_weights_pct ?? {}),
    ...Object.keys(allocation?.proposed?.sleeve_weights_pct ?? {}),
    ...Object.keys(allocation?.target?.sleeve_weights_pct ?? {}),
    ...(transition
      ? [
          transition.sleeve_key,
          ...(transition.transition_destination_sleeve_key
            ? [transition.transition_destination_sleeve_key]
            : []),
          ...Object.keys(transition.current.children),
          ...Object.keys(transition.proposed_basket.children),
          ...Object.keys(transition.target.children),
        ]
      : []),
  ];
  return completeFrozenRunSleeveLabels(runDisplayContext.value, sleeveKeys);
});
const effectLabels = computed(() =>
  currentRunMatches.value ? runContextLabels.value : portfolioLabelContext.value.labels,
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
const workspaceReadiness = computed(() =>
  selectWorkspaceReadiness({
    health: store.health,
    portfolio: portfolio.value,
    activePolicy: activePolicy.value,
    resourceFreshness: store.resourceFreshness,

    resourceReadsPending: store.workspaceResourceLoadPending,
    syncPending: store.actionState.syncPortfolio.pending,
    runPending: store.actionState.runOptimizer.pending,
  }),
);
const canRunOptimizer = computed(() => workspaceReadiness.value.canRunOptimizer);

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

onMounted(() => {
  void store.ensureInitialWorkspace();
});
</script>

<style scoped>
/* Grid gaps use Quasar's spacing scale; negative-margin gutters distort grid tracks. */
.run-help,
.empty-note {
  color: #657d8b;
  font-size: 0.8rem;
  line-height: 1.55;
}

.run-help {
  border-left: 3px solid #d4a24f;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.summary-card,
.workspace-card {
  min-width: 0;
}

.summary-card {
  min-height: 7.2rem;
}

.content-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.section-heading .section-subtitle {
  max-width: 40rem;
}

.transition-card {
  grid-column: 1 / -1;
}

.data-list > div {
  display: grid;
  grid-template-columns: minmax(10rem, 0.8fr) minmax(0, 1.2fr);
  gap: 8px;
  border-bottom: 1px solid #eaf0f3;
}

.data-list dt {
  color: #647c8b;
  font-size: 0.75rem;
}

.data-list dd {
  color: #29475a;
  font-size: 0.78rem;
  font-weight: 650;
  overflow-wrap: anywhere;
}

.coverage-list,
.policy-list,
.security-list {
  list-style: none;
}

.coverage-list li,
.policy-list li,
.security-list li {
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
}

@media (max-width: 620px) {
  .section-heading {
    flex-direction: column;
    align-items: stretch;
  }

  .page-actions {
    justify-content: flex-start;
  }

  .page-actions :deep(.overview-page-action) {
    flex: 1 1 auto;
  }

  .summary-grid {
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }

  .summary-card {
    min-height: 6.5rem;
  }

  .data-list > div {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
</style>
