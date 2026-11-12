<template>
  <section
    class="workspace-page overview-page tw:mx-auto tw:w-full tw:max-w-[1800px] tw:gap-4 tw:px-4 tw:py-4"
    aria-labelledby="overview-title"
  >
    <WorkspacePageHeader
      eyebrow="Workspace overview"
      title="Overview"
      title-id="overview-title"
      subtitle="Current account state and API-supplied allocation context for a single local workspace."
    >
      <template #actions>
        <Button
          type="button"
          variant="outline"
          class="overview-page-action tw:min-w-0 tw:whitespace-normal"
          :disabled="store.actionState.syncPortfolio.pending"
          :aria-busy="store.actionState.syncPortfolio.pending"
          @click="syncPortfolio"
        >
          <LoaderCircle
            v-if="store.actionState.syncPortfolio.pending"
            aria-hidden="true"
            data-icon="inline-start"
            class="tw:animate-spin"
          />
          <RefreshCw v-else aria-hidden="true" data-icon="inline-start" />
          {{ store.actionState.syncPortfolio.pending ? 'Syncing portfolio…' : 'Sync portfolio' }}
        </Button>
        <Button
          type="button"
          variant="default"
          class="overview-page-action tw:min-w-0 tw:whitespace-normal"
          :disabled="!canRunOptimizer"
          :aria-busy="store.actionState.runOptimizer.pending"
          @click="runOptimizer"
        >
          <LoaderCircle
            v-if="store.actionState.runOptimizer.pending"
            aria-hidden="true"
            data-icon="inline-start"
            class="tw:animate-spin"
          />
          <Play v-else aria-hidden="true" data-icon="inline-start" />
          {{
            store.actionState.runOptimizer.pending
              ? 'Running recommendations…'
              : 'Run DEMO recommendations'
          }}
        </Button>
      </template>
    </WorkspacePageHeader>

    <Alert v-if="!canRunOptimizer" role="status" aria-live="polite" class="tw:border-border">
      <AlertDescription>
        Recommendations require a ready portfolio snapshot and a valid active policy. Nothing runs
        automatically.
      </AlertDescription>
    </Alert>

    <div class="tw:grid tw:gap-2" aria-label="Workspace request errors">
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
    <Alert
      v-if="portfolioLabelContext.revisionMismatch"
      role="status"
      aria-live="polite"
      class="tw:border-border"
    >
      <AlertDescription>
        Portfolio effects use policy revision
        {{ portfolioLabelContext.portfolioRevisionId ?? 'unavailable' }}; the active policy is
        {{ portfolioLabelContext.policyRevisionId ?? 'unavailable' }}. Cached values remain visible
        with API sleeve keys until matching policy labels are confirmed.
      </AlertDescription>
    </Alert>
    <WorkspaceCapabilityNotice label="DEMO analysis only.">
      Recommendations are non-actionable; no broker calls, OAuth, live writes, or orders are
      available.
    </WorkspaceCapabilityNotice>

    <section
      class="summary-grid overview-summary-grid tw:grid tw:grid-cols-1 tw:gap-4 tw:sm:grid-cols-2 tw:xl:grid-cols-4"
      aria-label="Current portfolio summary"
    >
      <Card class="summary-card tw:min-w-0">
        <CardHeader class="tw:gap-1 tw:pb-2">
          <CardTitle
            role="heading"
            aria-level="2"
            class="tw:text-sm tw:font-medium tw:text-muted-foreground"
          >
            Portfolio value
          </CardTitle>
        </CardHeader>
        <CardContent class="tw:grid tw:gap-1">
          <p class="tw:m-0! tw:text-2xl tw:font-semibold tw:tracking-tight tw:tabular-nums">
            {{ formatUsd(portfolio?.portfolio_total_usd) }}
          </p>
          <CardDescription>Value returned by the portfolio API</CardDescription>
        </CardContent>
      </Card>
      <Card class="summary-card tw:min-w-0">
        <CardHeader class="tw:gap-1 tw:pb-2">
          <CardTitle
            role="heading"
            aria-level="2"
            class="tw:text-sm tw:font-medium tw:text-muted-foreground"
          >
            Cash
          </CardTitle>
        </CardHeader>
        <CardContent class="tw:grid tw:gap-1">
          <p class="tw:m-0! tw:text-2xl tw:font-semibold tw:tracking-tight tw:tabular-nums">
            {{ formatUsd(portfolio?.cash_usd) }}
          </p>
          <CardDescription>Cash balance returned by the portfolio API</CardDescription>
        </CardContent>
      </Card>
      <Card class="summary-card tw:min-w-0">
        <CardHeader class="tw:gap-1 tw:pb-2">
          <CardTitle
            role="heading"
            aria-level="2"
            class="tw:text-sm tw:font-medium tw:text-muted-foreground"
          >
            Positions
          </CardTitle>
        </CardHeader>
        <CardContent class="tw:grid tw:gap-1">
          <p class="tw:m-0! tw:text-2xl tw:font-semibold tw:tracking-tight tw:tabular-nums">
            {{ positionCount }}
          </p>
          <CardDescription>Current API position count</CardDescription>
        </CardContent>
      </Card>
      <Card class="summary-card tw:min-w-0">
        <CardHeader class="tw:gap-1 tw:pb-2">
          <CardTitle
            role="heading"
            aria-level="2"
            class="tw:text-sm tw:font-medium tw:text-muted-foreground"
          >
            Risk tracking
          </CardTitle>
        </CardHeader>
        <CardContent class="tw:grid tw:gap-1">
          <p class="tw:m-0! tw:text-2xl tw:font-semibold tw:tracking-tight">Not calculated</p>
          <CardDescription>No risk estimate is available from this workflow</CardDescription>
        </CardContent>
      </Card>
    </section>

    <section class="content-grid tw:grid tw:items-start tw:gap-4 tw:lg:grid-cols-2">
      <Card class="workspace-card account-card tw:min-w-0">
        <CardHeader
          class="tw:gap-3 tw:md:flex tw:md:flex-row tw:md:items-start tw:md:justify-between"
        >
          <div class="tw:grid tw:gap-2">
            <h2 class="tw:m-0! tw:text-lg! tw:font-semibold! tw:leading-tight!">Portfolio data</h2>
            <CardDescription>Source status and coverage from the backend API</CardDescription>
          </div>
          <Badge as="span" variant="secondary" class="tw:shrink-0">
            {{ portfolioStatusLabel }}
          </Badge>
        </CardHeader>
        <CardContent class="tw:grid tw:gap-4">
          <dl class="data-list tw:m-0! tw:grid tw:gap-0">
            <div
              class="tw:grid tw:grid-cols-1 tw:gap-1 tw:border-b tw:border-border tw:py-3 tw:sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] tw:sm:gap-2"
            >
              <dt class="tw:text-sm tw:text-muted-foreground">Account</dt>
              <dd class="tw:m-0! tw:break-words tw:text-sm tw:font-medium">{{ accountLabel }}</dd>
            </div>
            <div
              class="tw:grid tw:grid-cols-1 tw:gap-1 tw:border-b tw:border-border tw:py-3 tw:sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] tw:sm:gap-2"
            >
              <dt class="tw:text-sm tw:text-muted-foreground">Application status</dt>
              <dd class="tw:m-0! tw:break-words tw:text-sm tw:font-medium">
                {{ store.health?.status ?? 'Unavailable' }}
              </dd>
            </div>
            <div
              class="tw:grid tw:grid-cols-1 tw:gap-1 tw:border-b tw:border-border tw:py-3 tw:sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] tw:sm:gap-2"
            >
              <dt class="tw:text-sm tw:text-muted-foreground">Database schema</dt>
              <dd class="tw:m-0! tw:break-words tw:text-sm tw:font-medium">
                {{
                  store.health ? (store.health.schema_ready ? 'Ready' : 'Not ready') : 'Unavailable'
                }}
              </dd>
            </div>
            <div
              class="tw:grid tw:grid-cols-1 tw:gap-1 tw:border-b tw:border-border tw:py-3 tw:sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] tw:sm:gap-2"
            >
              <dt class="tw:text-sm tw:text-muted-foreground">Source</dt>
              <dd class="tw:m-0! tw:break-words tw:text-sm tw:font-medium">
                {{ portfolio?.status === 'ready' ? portfolio.source : 'Unavailable' }}
              </dd>
            </div>
            <div
              class="tw:grid tw:grid-cols-1 tw:gap-1 tw:border-b tw:border-border tw:py-3 tw:sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] tw:sm:gap-2"
            >
              <dt class="tw:text-sm tw:text-muted-foreground">Data as of</dt>
              <dd class="tw:m-0! tw:break-words tw:text-sm tw:font-medium">
                {{ portfolio?.as_of ?? 'Unavailable' }}
              </dd>
            </div>
            <div
              class="tw:grid tw:grid-cols-1 tw:gap-1 tw:border-b tw:border-border tw:py-3 tw:sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] tw:sm:gap-2"
            >
              <dt class="tw:text-sm tw:text-muted-foreground">Sync generation</dt>
              <dd class="tw:m-0! tw:break-words tw:text-sm tw:font-medium">
                {{ portfolio ? String(portfolio.sync.generation) : 'Unavailable' }}
              </dd>
            </div>
            <div
              class="tw:grid tw:grid-cols-1 tw:gap-1 tw:border-b tw:border-border tw:py-3 tw:sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] tw:sm:gap-2"
            >
              <dt class="tw:text-sm tw:text-muted-foreground">Last completed sync</dt>
              <dd class="tw:m-0! tw:break-words tw:text-sm tw:font-medium">
                {{ portfolio?.sync.completed_at ?? 'Unavailable' }}
              </dd>
            </div>
            <div
              class="tw:grid tw:grid-cols-1 tw:gap-1 tw:border-b tw:border-border tw:py-3 tw:sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] tw:sm:gap-2"
            >
              <dt class="tw:text-sm tw:text-muted-foreground">Last sync error</dt>
              <dd class="tw:m-0! tw:break-words tw:text-sm tw:font-medium">
                <template v-if="portfolio?.sync.last_error_code">
                  {{ portfolio.sync.last_error_code }}:
                  {{ portfolio.sync.last_error_summary ?? 'No summary returned' }}
                </template>
                <template v-else>None reported</template>
              </dd>
            </div>
          </dl>

          <Alert v-if="portfolio?.status === 'not_synced'" role="status" aria-live="polite">
            <AlertDescription>
              The current portfolio snapshot has not been synchronized. Use Sync portfolio to
              request the configured local demo snapshot.
            </AlertDescription>
          </Alert>

          <section class="coverage-block tw:grid tw:gap-3" aria-labelledby="coverage-title">
            <h3
              id="coverage-title"
              class="tw:m-0! tw:text-sm! tw:font-semibold! tw:leading-tight! tw:uppercase tw:tracking-wide"
            >
              Data coverage
            </h3>
            <Empty
              v-if="coverageEntries.length === 0"
              role="status"
              aria-live="polite"
              class="tw:border-border tw:p-4"
            >
              <EmptyHeader class="tw:max-w-none">
                <EmptyTitle role="heading" aria-level="4">Coverage unavailable</EmptyTitle>
                <EmptyDescription
                  >Coverage is unavailable until portfolio data loads.</EmptyDescription
                >
              </EmptyHeader>
            </Empty>
            <ul v-else class="coverage-list tw:m-0! tw:grid tw:list-none tw:gap-0 tw:p-0!">
              <li
                v-for="[key, covered] in coverageEntries"
                :key="key"
                class="tw:flex tw:min-w-0 tw:flex-wrap tw:items-center tw:justify-between tw:gap-2 tw:border-b tw:border-border tw:py-3"
              >
                <span class="tw:min-w-0 tw:break-all tw:text-sm">{{ key }}</span>
                <Badge as="span" :variant="covered ? 'secondary' : 'outline'" class="tw:shrink-0">
                  {{ covered ? 'Available' : 'Unavailable' }}
                </Badge>
              </li>
            </ul>
          </section>
        </CardContent>
      </Card>

      <Card class="workspace-card run-card tw:min-w-0">
        <CardHeader
          class="tw:gap-3 tw:md:flex tw:md:flex-row tw:md:items-start tw:md:justify-between"
        >
          <div class="tw:grid tw:gap-2">
            <h2 class="tw:m-0! tw:text-lg! tw:font-semibold! tw:leading-tight!">
              Latest recommendations
            </h2>
            <CardDescription>
              Metrics are shown only for a run matching this current portfolio and active policy.
            </CardDescription>
          </div>
          <Badge v-if="currentRunMatches" as="span" variant="outline" class="tw:shrink-0">
            DEMO · non-actionable
          </Badge>
        </CardHeader>
        <CardContent class="tw:grid tw:gap-4">
          <Empty
            v-if="!currentRunMatches"
            role="status"
            aria-live="polite"
            class="tw:border-border tw:p-4"
          >
            <EmptyHeader class="tw:max-w-none">
              <EmptyTitle role="heading" aria-level="3"
                >No current matching recommendation run</EmptyTitle
              >
              <EmptyDescription>
                Saved or stale runs are not used as current portfolio comparisons.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
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
        </CardContent>
      </Card>

      <Card class="workspace-card allocation-card tw:min-w-0">
        <CardContent class="tw:pt-4">
          <AllocationTargets
            :allocation="allocation"
            :labels="effectLabels"
            :show-no-current-basket="!currentRunAllocationAvailable"
          />
        </CardContent>
      </Card>

      <Card class="workspace-card transition-card tw:min-w-0 tw:lg:col-span-full">
        <CardContent class="tw:pt-4">
          <USAllocationTransition
            :transition="usTransition"
            :labels="effectLabels"
            :show-no-current-basket="!currentRunTransitionAvailable"
          />
        </CardContent>
      </Card>

      <Card class="workspace-card policy-card tw:min-w-0">
        <CardHeader
          class="tw:gap-3 tw:md:flex tw:md:flex-row tw:md:items-start tw:md:justify-between"
        >
          <div class="tw:grid tw:gap-2">
            <h2 class="tw:m-0! tw:text-lg! tw:font-semibold! tw:leading-tight!">
              Active allocation policy
            </h2>
            <CardDescription
              >Policy settings and allowed securities supplied by the API</CardDescription
            >
          </div>
          <Badge as="span" :variant="activePolicy ? 'secondary' : 'outline'" class="tw:shrink-0">
            {{ activePolicy ? `Revision ${activePolicy.revision_number}` : 'No active policy' }}
          </Badge>
        </CardHeader>
        <CardContent class="tw:grid tw:gap-4">
          <Empty
            v-if="!activePolicy"
            role="status"
            aria-live="polite"
            class="tw:border-border tw:p-4"
          >
            <EmptyHeader class="tw:max-w-none">
              <EmptyTitle role="heading" aria-level="3">No active policy returned</EmptyTitle>
              <EmptyDescription
                >Allocation targets are unavailable until a policy loads.</EmptyDescription
              >
            </EmptyHeader>
          </Empty>
          <template v-else>
            <section class="tw:grid tw:gap-3" aria-labelledby="enabled-sleeves-title">
              <h3
                id="enabled-sleeves-title"
                class="tw:m-0! tw:text-sm! tw:font-semibold! tw:leading-tight! tw:uppercase tw:tracking-wide"
              >
                Enabled sleeves and targets
              </h3>
              <ul
                v-if="enabledSleeves.length"
                class="policy-list tw:m-0! tw:grid tw:list-none tw:gap-0 tw:p-0!"
              >
                <li
                  v-for="sleeve in enabledSleeves"
                  :key="sleeve.sleeve_key"
                  class="tw:flex tw:min-w-0 tw:flex-wrap tw:items-center tw:justify-between tw:gap-2 tw:border-b tw:border-border tw:py-3"
                >
                  <span class="tw:min-w-0 tw:break-words tw:text-sm">{{
                    sleeve.display_name
                  }}</span>
                  <span class="tw:shrink-0 tw:font-medium tw:tabular-nums">{{
                    formatPercent(sleeve.target_pct)
                  }}</span>
                </li>
              </ul>
              <Empty v-else role="status" aria-live="polite" class="tw:border-border tw:p-4">
                <EmptyHeader class="tw:max-w-none">
                  <EmptyTitle role="heading" aria-level="4">No enabled sleeves returned</EmptyTitle>
                </EmptyHeader>
              </Empty>
            </section>

            <section class="tw:grid tw:gap-3" aria-labelledby="allowed-securities-title">
              <h3
                id="allowed-securities-title"
                class="policy-subhead tw:m-0! tw:text-sm! tw:font-semibold! tw:leading-tight! tw:text-muted-foreground tw:uppercase tw:tracking-wide"
              >
                Allowed securities
              </h3>
              <ul
                v-if="enabledSecurities.length"
                class="security-list tw:m-0! tw:grid tw:list-none tw:gap-0 tw:p-0!"
              >
                <li
                  v-for="security in enabledSecurities"
                  :key="`${security.sleeve_key}:${security.ticker}`"
                  class="tw:flex tw:min-w-0 tw:flex-wrap tw:items-center tw:gap-2 tw:border-b tw:border-border tw:py-3"
                >
                  <strong class="tw:min-w-20 tw:font-semibold">{{ security.ticker }}</strong>
                  <span class="tw:min-w-0 tw:break-words tw:text-sm">
                    {{ policyLabels[security.sleeve_key] ?? security.sleeve_key }}
                  </span>
                </li>
              </ul>
              <Empty v-else role="status" aria-live="polite" class="tw:border-border tw:p-4">
                <EmptyHeader class="tw:max-w-none">
                  <EmptyTitle role="heading" aria-level="4">
                    No enabled allowed securities returned
                  </EmptyTitle>
                </EmptyHeader>
              </Empty>
            </section>
          </template>
        </CardContent>
      </Card>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty';
import { LoaderCircle, Play, RefreshCw } from '@lucide/vue';
import { useRouter } from 'vue-router';
import AllocationTargets from '@/components/AllocationTargets.vue';
import ApiActionError from '@/components/ApiActionError.vue';
import RunSummary from '@/components/RunSummary.vue';
import WorkspacePageHeader from '@/components/WorkspacePageHeader.vue';
import WorkspaceCapabilityNotice from '@/components/WorkspaceCapabilityNotice.vue';
import { formatPercent, formatUsd } from '@/utils/display-values';
import USAllocationTransition from '@/components/USAllocationTransition.vue';
import { useWorkspace } from '@/composables/use-workspace';
import { displayCount } from './overview-state';

import { completeFrozenRunSleeveLabels } from './run-context';
import {
  selectPortfolioLabelContext,
  selectRunPresentation,
  selectWorkspaceReadiness,
} from '@/stores/workspace-selectors';
import ResourceFreshnessNotice from '@/components/ResourceFreshnessNotice.vue';

const store = useWorkspace();
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
