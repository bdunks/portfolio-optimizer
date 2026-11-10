<template>
  <section
    class="workspace-page recommendations-page q-my-none q-mx-auto q-pa-md"
    aria-labelledby="recommendations-title"
  >
    <WorkspacePageHeader
      eyebrow="Small-batch review"
      title="Recommendations"
      title-id="recommendations-title"
      subtitle="Review ranked groups and API-proposed legs. Group or sell-lot selection requests a backend re-solve; selection is never an order approval."
    >
      <template #actions>
        <q-btn
          unelevated
          no-caps
          type="button"
          class="primary-button"
          color="primary"
          size="sm"
          :disable="!canRunOptimizer"
          @click="runOptimizer"
        >
          {{
            store.actionState.runOptimizer.pending ? 'Running DEMO…' : 'Run DEMO recommendations'
          }}
        </q-btn>
      </template>
    </WorkspacePageHeader>

    <WorkspaceCapabilityNotice label="DEMO ONLY · non-actionable.">
      API demo values are hypothetical. No E*TRADE connection, OAuth, order preview, approval, or
      submission controls exist on this screen.
    </WorkspaceCapabilityNotice>

    <q-card
      tag="section"
      flat
      bordered
      class="run-controls q-pa-md"
      aria-label="Recommendation run controls"
    >
      <label
        class="trade-date-control column no-wrap q-gutter-y-xs text-caption text-weight-bold text-blue-grey-8"
      >
        <span>Proposed trade date (optional)</span>
        <q-input
          outlined
          dense
          hide-bottom-space
          v-model="proposedTradeDate"
          type="date"
          :disable="!canRunOptimizer"
        />
      </label>
      <p class="trade-date-help">
        Blank uses the deterministic DEMO date 2026-11-05. This is a calendar date; no weekend or
        holiday adjustment is applied.
      </p>
      <p v-if="!canRunOptimizer" class="state-message">
        A new run requires a ready synchronized portfolio, healthy local API, and valid active
        policy. Nothing runs automatically.
      </p>
      <form
        class="saved-run-form row items-end q-gutter-sm justify-end"
        @submit.prevent="openSavedRun"
      >
        <label class="column no-wrap q-gutter-y-xs text-caption text-weight-bold text-blue-grey-8">
          <span>Open saved run ID</span>
          <q-input
            outlined
            dense
            hide-bottom-space
            v-model.trim="savedRunId"
            type="text"
            autocomplete="off"
            placeholder="Run ID from Activity"
          />
        </label>
        <q-btn
          no-caps
          type="submit"
          class="secondary-button"
          outline
          color="primary"
          size="sm"
          :disable="
            !savedRunId ||
            store.actionState.openSavedRun.pending ||
            runPresentation.reviewMutationPending
          "
        >
          {{ store.actionState.openSavedRun.pending ? 'Opening saved run…' : 'Open frozen run' }}
        </q-btn>
      </form>
    </q-card>

    <div
      class="error-stack column no-wrap q-gutter-y-sm"
      aria-label="Recommendation request errors"
    >
      <ApiActionError
        :error="store.actionState.loadHealth.error"
        title="Local API health could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.loadPortfolio.error"
        title="Portfolio snapshot could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.loadPolicy.error"
        title="Active policy could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.runOptimizer.error"
        title="Recommendation run failed"
      />
      <ApiActionError
        :error="store.actionState.openSavedRun.error"
        title="Saved run could not be opened"
      />
      <ApiActionError
        :error="store.actionState.recalculateSelection.error"
        title="Selection re-solve failed; the last successful API selection remains in view"
      />
      <ApiActionError
        :error="store.actionState.annotateGroup.error"
        title="Group note or rejection was not saved"
      />
      <ApiActionError
        :error="store.actionState.exportRun.error"
        title="Recommendation export failed"
      />
    </div>

    <ResourceFreshnessNotice />
    <q-banner
      v-if="portfolioLabelContext.revisionMismatch && !currentRunEffectsAreUsable"
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

    <WorkspaceEmptyState
      v-if="!currentRun"
      :title="
        store.actionState.runOptimizer.pending || store.actionState.openSavedRun.pending
          ? 'Loading recommendations'
          : 'No recommendation run loaded'
      "
    >
      <template
        v-if="store.actionState.runOptimizer.pending || store.actionState.openSavedRun.pending"
      >
        The local API is preparing or reopening a run.
      </template>
      <template v-else>
        Run a DEMO analysis from Overview or this page, or reopen a saved run by its API run ID.
      </template>
      <template #details>
        <p v-if="store.actionState.runOptimizer.error || store.actionState.openSavedRun.error">
          The request failed. Retry only after reviewing the API error above.
        </p>
      </template>
    </WorkspaceEmptyState>

    <template v-else>
      <RunSummary
        mode="review"
        :run="currentRun"
        :summary="savedRunSummary"
        :context="runDisplayContext"
        :pending="runPresentation.reviewMutationPending"
        :view="store.currentRunView"
        :provenance-label="provenanceLabel"
      />

      <q-card
        tag="section"
        flat
        bordered
        v-if="!runPresentation.reviewMutationPending"
        class="effects-panel q-pa-md column no-wrap q-gutter-y-md"
        aria-labelledby="effects-title"
      >
        <header class="section-heading row items-start justify-between q-gutter-md">
          <div>
            <h2 class="q-ma-none text-subtitle1 text-blue-grey-10" id="effects-title">
              API allocation effects
            </h2>
            <p class="q-mt-xs q-mb-none q-mx-none text-body2 text-blue-grey-7">
              {{ effectsDescription }}
            </p>
          </div>
        </header>
        <AllocationTargets
          :allocation="effectDisplay.allocation"
          :labels="effectDisplay.labels"
          :show-no-current-basket="showNoCurrentBasket"
        />
        <USAllocationTransition
          :transition="effectDisplay.transition"
          :labels="effectDisplay.labels"
          :show-no-current-basket="showNoCurrentBasket"
        />
      </q-card>

      <q-card
        tag="section"
        flat
        bordered
        v-if="currentRunGroupCount && !runPresentation.reviewMutationPending"
        class="review-panel q-pa-md"
        aria-labelledby="groups-title"
      >
        <header class="section-heading row items-start justify-between q-gutter-md">
          <div>
            <h2 class="q-ma-none text-subtitle1 text-blue-grey-10" id="groups-title">
              Ranked trade groups
            </h2>
            <p class="q-mt-xs q-mb-none q-mx-none text-body2 text-blue-grey-7">
              Priority rank is the API rank, not a precision score. Execution sequence and
              dependencies are shown separately.
            </p>
          </div>
          <span>{{ filteredGroups.length }} shown / {{ currentRunGroupCount }} returned</span>
        </header>

        <q-card
          tag="form"
          flat
          bordered
          aria-label="Recommendation filters"
          class="filter-panel row items-end q-gutter-sm q-pa-sm text-caption text-weight-bold text-blue-grey-8"
          @submit.prevent
        >
          <label
            class="column no-wrap q-gutter-y-xs text-caption text-weight-bold text-blue-grey-8"
          >
            <span>Sleeve</span>
            <q-select
              v-model="filters.sleeve"
              :options="[
                { label: 'All sleeves', value: '' },
                ...sleeveOptions.map((sleeve) => ({
                  label: sleeveLabel(sleeve),
                  value: sleeve,
                })),
              ]"
              emit-value
              map-options
              outlined
              dense
              hide-bottom-space
              aria-label="Sleeve"
            />
          </label>
          <label
            class="column no-wrap q-gutter-y-xs text-caption text-weight-bold text-blue-grey-8"
          >
            <span>Action</span>
            <q-select
              v-model="filters.action"
              :options="[
                { label: 'Any action', value: '' },
                { label: 'SELL', value: 'SELL' },
                { label: 'BUY', value: 'BUY' },
              ]"
              emit-value
              map-options
              outlined
              dense
              hide-bottom-space
              aria-label="Action"
            />
          </label>
          <label
            class="column no-wrap q-gutter-y-xs text-caption text-weight-bold text-blue-grey-8"
          >
            <span>Tax term</span>
            <q-select
              v-model="filters.term"
              :options="[
                { label: 'Any term', value: '' },
                { label: 'Short term', value: 'ST' },
                { label: 'Long term', value: 'LT' },
              ]"
              emit-value
              map-options
              outlined
              dense
              hide-bottom-space
              aria-label="Tax term"
            />
          </label>
          <label
            class="column no-wrap q-gutter-y-xs text-caption text-weight-bold text-blue-grey-8"
          >
            <span>Expected benefit</span>
            <q-select
              v-model="filters.benefit"
              :options="[
                { label: 'Any', value: '' },
                { label: 'Unavailable in API', value: 'unavailable' },
              ]"
              emit-value
              map-options
              outlined
              dense
              hide-bottom-space
              aria-label="Expected benefit"
            />
          </label>
          <label
            class="column no-wrap q-gutter-y-xs text-caption text-weight-bold text-blue-grey-8"
          >
            <span>Warnings</span>
            <q-select
              v-model="filters.warning"
              :options="[
                { label: 'Any', value: '' },
                { label: 'With warnings', value: 'with' },
                { label: 'No warnings returned', value: 'without' },
              ]"
              emit-value
              map-options
              outlined
              dense
              hide-bottom-space
              aria-label="Warnings"
            />
          </label>
          <label
            class="column no-wrap q-gutter-y-xs text-caption text-weight-bold text-blue-grey-8"
          >
            <span>Group type</span>
            <q-select
              v-model="filters.groupType"
              :options="[
                { label: 'Any type', value: '' },
                ...groupTypeOptions.map((type) => ({ label: type, value: type })),
              ]"
              emit-value
              map-options
              outlined
              dense
              hide-bottom-space
              aria-label="Group type"
            />
          </label>
          <label
            class="column no-wrap q-gutter-y-xs text-caption text-weight-bold text-blue-grey-8"
          >
            <span>Sort by API priority rank</span>
            <q-select
              v-model="sortOrder"
              :options="[
                { label: 'Highest priority first (ascending rank)', value: 'rank-ascending' },
                { label: 'Lowest priority first (descending rank)', value: 'rank-descending' },
              ]"
              emit-value
              map-options
              outlined
              dense
              hide-bottom-space
              aria-label="Sort by API priority rank"
            />
          </label>
        </q-card>

        <fieldset
          class="selection-tools row items-end q-gutter-sm q-mb-md q-mr-none q-pa-md"
          :disabled="!canChangeSelection"
        >
          <legend class="q-py-none q-px-xs">Re-solve selected basket</legend>
          <label
            class="top-n-control column no-wrap q-gutter-y-xs text-caption text-weight-bold text-blue-grey-8"
          >
            <span>Top N groups by API rank</span>
            <q-input
              outlined
              dense
              hide-bottom-space
              v-model.number="topN"
              :disable="!canChangeSelection"
              type="number"
              min="1"
              :max="currentRunGroupCount"
            />
          </label>
          <q-btn
            no-caps
            type="button"
            class="secondary-button"
            outline
            color="primary"
            size="sm"
            :disable="!canChangeSelection"
            @click="selectTopGroups"
          >
            Select top N and re-solve
          </q-btn>
          <q-btn
            no-caps
            type="button"
            class="secondary-button"
            outline
            color="primary"
            size="sm"
            :disable="!canChangeSelection"
            @click="clearSelection"
          >
            Clear selected groups and re-solve
          </q-btn>
          <span v-if="!canChangeSelection" class="read-only-note">
            Saved, stale, or unverified run context is read-only. Open/run a current matching run to
            change selection.
          </span>
          <span v-else class="read-only-note">
            Group selection and individual SELL-lot selection re-solve through the API. Shared BUY
            legs cannot be toggled independently.
          </span>
        </fieldset>

        <p v-if="filteredGroups.length === 0" class="empty-inline q-my-xs q-mx-none">
          No returned groups match these filters.
        </p>
        <div v-else class="group-list">
          <TradeGroup
            v-for="group in filteredGroups"
            :key="group.group_id"
            :group="group"
            :legs="groupDetailLegs(group)"
            :leg-references="groupLegReferences(group)"
            :sleeve-label="sleeveLabel(group.sleeve_key)"
            :has-sell-lots="groupSellLotIdsFor(group).length > 0"
            :has-shared-leg="group.leg_ids.some(isSharedLeg)"
            :note-draft="noteDrafts[group.group_id] ?? ''"
            :rejection-draft="rejectionDrafts[group.group_id] ?? ''"
            :can-change-selection="canChangeSelection"
            :pending="runPresentation.reviewMutationPending"
            @group-selection="changeGroupSelection"
            @lot-selection="changeLotSelection"
            @note-draft-change="changeNoteDraft"
            @rejection-draft-change="changeRejectionDraft"
            @save-note="saveNote"
            @reject-group="rejectGroup"
            @restore-group="restoreGroup"
          />
        </div>

        <section
          v-if="visibleSharedLegs.length"
          class="shared-legs q-pt-md column no-wrap q-gutter-y-sm"
          aria-labelledby="shared-legs-title"
        >
          <h3 class="q-mb-none q-mx-none text-subtitle2 text-blue-grey-9" id="shared-legs-title">
            Shared consolidated legs · each canonical leg shown once
          </h3>
          <p class="q-mr-none q-mb-none q-ml-none text-body2 text-blue-grey-8">
            These API legs are referenced by multiple groups. A shared BUY cannot be toggled
            independently.
          </p>
          <article v-for="leg in visibleSharedLegs" :key="leg.leg_id" class="shared-leg-card">
            <RecommendationLegDetails :leg="leg" :id="legAnchor(leg.leg_id)" />
            <p><strong>Linked groups:</strong> {{ leg.group_ids.join(', ') }}</p>
            <p v-if="leg.dependencies.length">
              <strong>Leg dependencies:</strong> {{ leg.dependencies.join(', ') }}
            </p>
          </article>
        </section>
        <q-banner
          v-if="visibleUnlinkedLegs.length"
          dense
          rounded
          class="q-mt-sm bg-amber-1 text-brown-10"
          role="region"
          aria-label="Unlinked API legs"
        >
          <h3 class="q-ma-none text-subtitle2">Unlinked API legs — not executable</h3>
          <article v-for="leg in visibleUnlinkedLegs" :key="leg.leg_id" class="unlinked-leg-card">
            <RecommendationLegDetails :leg="leg" :id="legAnchor(leg.leg_id)" />
            <p>
              API group references are missing or inconsistent. Do not treat this leg as an
              executable recommendation.
            </p>
          </article>
        </q-banner>
      </q-card>

      <q-card
        tag="section"
        flat
        bordered
        v-if="!runPresentation.reviewMutationPending"
        class="export-panel row no-wrap justify-between q-gutter-md items-center q-pa-md"
        aria-label="Recommendation export"
      >
        <div>
          <h2 class="q-ma-none text-subtitle1 text-blue-grey-10">Export this API run</h2>
          <p class="q-mt-xs q-mb-none q-mx-none text-body2 text-blue-grey-7">
            Exports retain the API run, policy, source generation, as-of time, warnings, and
            demo/actionability metadata.
          </p>
        </div>
        <q-btn
          no-caps
          type="button"
          class="secondary-button"
          outline
          color="primary"
          size="sm"
          :disable="store.actionState.exportRun.pending"
          @click="exportRun('csv')"
        >
          Export CSV
        </q-btn>
        <q-btn
          no-caps
          type="button"
          class="secondary-button"
          outline
          color="primary"
          size="sm"
          :disable="store.actionState.exportRun.pending"
          @click="exportRun('json')"
        >
          Export JSON
        </q-btn>
      </q-card>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import ApiActionError from '@/components/ApiActionError.vue';
import WorkspaceCapabilityNotice from '@/components/WorkspaceCapabilityNotice.vue';
import WorkspaceEmptyState from '@/components/WorkspaceEmptyState.vue';
import WorkspacePageHeader from '@/components/WorkspacePageHeader.vue';
import RecommendationLegDetails from '@/components/RecommendationLegDetails.vue';
import RunSummary from '@/components/RunSummary.vue';
import TradeGroup from '@/components/TradeGroup.vue';

import ResourceFreshnessNotice from '@/components/ResourceFreshnessNotice.vue';
import AllocationTargets from '@/components/AllocationTargets.vue';
import USAllocationTransition from '@/components/USAllocationTransition.vue';
import type { ExportFormat } from '@/services/api';
import { useWorkspaceStore } from '@/stores/workspace-store';
import type { RecommendationGroupResponse, RecommendationLegResponse } from '@/types/api';
import type {
  GroupActionIntent,
  GroupNoteIntent,
  GroupRejectIntent,
  GroupSelectionIntent,
  GroupTextIntent,
  LotSelectionIntent,
  TradeGroupLegReference,
} from '@/components/trade-review-types';
import {
  canonicalLegs,
  filterGroups,
  groupLegs,
  groupSellLotIds,
  requestGroupSelection,
  requestLotSelection,
  sharedLegs,
  unlinkedLegs,
  type RecommendationFilters,
} from './recommendations-state';

import { completeFrozenRunSleeveLabels, frozenRunSleeveLabel } from './run-context';
import {
  selectPortfolioLabelContext,
  selectRunPresentation,
  selectWorkspaceReadiness,
} from '@/stores/workspace-selectors';

const store = useWorkspaceStore();
const savedRunId = ref('');
const proposedTradeDate = ref('');
const topN = ref(3);
const sortOrder = ref<'rank-ascending' | 'rank-descending'>('rank-ascending');
const noteDrafts = reactive<Record<string, string>>({});
const rejectionDrafts = reactive<Record<string, string>>({});
const filters = reactive<RecommendationFilters>({
  sleeve: '',
  action: '',
  term: '',
  benefit: '',
  warning: '',
  groupType: '',
});

const currentRun = computed(() => store.currentRun);
const savedRunSummary = computed(() => store.currentRunSummary);
const currentRunGroupCount = computed(() => currentRun.value?.groups.length ?? 0);

const portfolio = computed(() => store.portfolio);
const activePolicy = computed(() => store.policy?.active ?? null);
const runPresentation = computed(() =>
  selectRunPresentation({
    run: currentRun.value,
    summary: savedRunSummary.value,
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
const provenanceLabel = computed(() => runPresentation.value.provenanceLabel);
const currentRunEffectsAreUsable = computed(() => runPresentation.value.effectsAvailable);
const showNoCurrentBasket = computed(
  () => !currentRunMatches.value && store.currentRunView !== 'saved',
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
    openSavedRunPending: store.actionState.openSavedRun.pending,
  }),
);
const canRunOptimizer = computed(() => workspaceReadiness.value.canRunOptimizer);
const canChangeSelection = computed(
  () =>
    currentRunMatches.value &&
    store.currentRunView === 'current' &&
    !store.actionState.syncPortfolio.pending,
);
const runSleeveLabels = computed(() => {
  const run = currentRun.value;
  const allocation = run?.portfolio_effects?.allocation;
  const transition = run?.portfolio_effects?.us_transition;
  return completeFrozenRunSleeveLabels(runDisplayContext.value, [
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
  ]);
});
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
const effectDisplay = computed(() => {
  if (currentRunEffectsAreUsable.value) {
    return {
      allocation: currentRun.value?.portfolio_effects?.allocation ?? null,
      transition: currentRun.value?.portfolio_effects?.us_transition ?? null,
      labels: runSleeveLabels.value,
      source: store.currentRunView === 'saved' ? ('saved_run' as const) : ('current_run' as const),
    };
  }
  return {
    allocation: portfolio.value?.allocation ?? null,
    transition: portfolio.value?.us_transition ?? null,
    labels: portfolioLabelContext.value.labels,
    source: 'current_portfolio' as const,
  };
});
const effectsDescription = computed(() => runPresentation.value.effectsDescription);
const sleeveOptions = computed(() =>
  [...new Set(currentRun.value?.groups.map((group) => group.sleeve_key) ?? [])].sort(),
);
const groupTypeOptions = computed(() =>
  [...new Set(currentRun.value?.groups.map((group) => group.group_type) ?? [])].sort(),
);
const filteredGroups = computed(() =>
  currentRun.value ? filterGroups(currentRun.value, filters, sortOrder.value) : [],
);
const allCanonicalLegs = computed(() => (currentRun.value ? canonicalLegs(currentRun.value) : []));
const allSharedLegs = computed(() => (currentRun.value ? sharedLegs(currentRun.value) : []));
const invalidLegIds = computed(() => new Set(visibleUnlinkedLegs.value.map((leg) => leg.leg_id)));
const visibleSharedLegs = computed(() =>
  allSharedLegs.value.filter((leg) => !invalidLegIds.value.has(leg.leg_id)),
);
const visibleUnlinkedLegs = computed(() =>
  currentRun.value ? unlinkedLegs(currentRun.value) : [],
);

watch(
  currentRun,
  (run, previousRun) => {
    const sameRun = run !== null && previousRun?.run_id === run.run_id;
    if (!sameRun) {
      for (const key of Object.keys(noteDrafts)) delete noteDrafts[key];
      for (const key of Object.keys(rejectionDrafts)) delete rejectionDrafts[key];
    } else {
      const groupIds = new Set(run.groups.map((group) => group.group_id));
      for (const key of Object.keys(noteDrafts)) {
        if (!groupIds.has(key)) delete noteDrafts[key];
      }
      for (const key of Object.keys(rejectionDrafts)) {
        if (!groupIds.has(key)) delete rejectionDrafts[key];
      }
    }

    for (const group of run?.groups ?? []) {
      const previousGroup = sameRun
        ? previousRun?.groups.find((item) => item.group_id === group.group_id)
        : undefined;
      if (!previousGroup || noteDrafts[group.group_id] === (previousGroup.note ?? '')) {
        noteDrafts[group.group_id] = group.note ?? '';
      }
      if (
        !previousGroup ||
        rejectionDrafts[group.group_id] === (previousGroup.rejection_reason ?? '')
      ) {
        rejectionDrafts[group.group_id] = group.rejection_reason ?? '';
      }
    }
  },
  { immediate: true },
);

function sleeveLabel(key: string): string {
  return frozenRunSleeveLabel(runDisplayContext.value, key);
}

function groupLegsFor(group: RecommendationGroupResponse): RecommendationLegResponse[] {
  if (!currentRun.value) return [];
  return groupLegs(currentRun.value, group).sort((left, right) => left.sequence - right.sequence);
}

function groupDetailLegs(group: RecommendationGroupResponse): RecommendationLegResponse[] {
  return groupLegsFor(group).filter(
    (leg) => leg.group_ids.length <= 1 && !invalidLegIds.value.has(leg.leg_id),
  );
}

function groupSellLotIdsFor(group: RecommendationGroupResponse): string[] {
  return currentRun.value ? groupSellLotIds(currentRun.value, group) : [];
}

function findLeg(legId: string): RecommendationLegResponse | undefined {
  return allCanonicalLegs.value.find((leg) => leg.leg_id === legId);
}

function isSharedLeg(legId: string): boolean {
  return visibleSharedLegs.value.some((leg) => leg.leg_id === legId);
}

function isUnlinkedLeg(legId: string): boolean {
  return visibleUnlinkedLegs.value.some((leg) => leg.leg_id === legId);
}

function groupLegReferences(group: RecommendationGroupResponse): TradeGroupLegReference[] {
  return group.leg_ids.map((legId) => {
    const leg = findLeg(legId);
    if (!leg) return { legId, label: 'Missing API leg', status: 'missing' };
    const status = isUnlinkedLeg(legId) ? 'unlinked' : isSharedLeg(legId) ? 'shared' : 'linked';
    return {
      legId,
      label: `Sequence ${leg.sequence} ${leg.side} ${leg.ticker ?? 'ticker unavailable'}`,
      status,
    };
  });
}

function legAnchor(legId: string): string {
  return `leg-${encodeURIComponent(legId)}`;
}

async function runOptimizer(): Promise<void> {
  if (!canRunOptimizer.value) return;
  try {
    await store.runOptimizer(
      proposedTradeDate.value ? { proposed_trade_date: proposedTradeDate.value } : {},
    );
  } catch {
    // The store retains a structured API error for this page.
  }
}

async function openSavedRun(): Promise<void> {
  const runId = savedRunId.value.trim();
  if (!runId) return;
  try {
    await store.openSavedRun(runId);
  } catch {
    // The store retains a structured API error for this page.
  }
}

async function recalculate(
  selection: Parameters<typeof store.recalculateSelection>[0],
): Promise<void> {
  if (!canChangeSelection.value) return;
  try {
    await store.recalculateSelection(selection);
  } catch {
    // Keep the last successful response and expose the API failure above.
  }
}

function changeGroupSelection({ groupId, selected }: GroupSelectionIntent): void {
  const run = currentRun.value;
  if (!run) return;
  void recalculate(requestGroupSelection(run, groupId, selected));
}

function changeLotSelection({ groupId, brokerLotId, selected }: LotSelectionIntent): void {
  const run = currentRun.value;
  if (!run) return;
  void recalculate(requestLotSelection(run, groupId, brokerLotId, selected));
}

function selectTopGroups(): void {
  const run = currentRun.value;
  if (!run) return;
  const count = Math.max(0, Math.floor(Number(topN.value) || 0));
  const selectedGroups = [...run.groups]
    .filter((group) => !group.rejected && groupSellLotIds(run, group).length > 0)
    .sort((left, right) => left.rank - right.rank)
    .slice(0, count);
  void recalculate({
    selected_group_ids: selectedGroups.map((group) => group.group_id),
    selected_sell_lots: Object.fromEntries(
      selectedGroups.map((group) => [group.group_id, groupSellLotIds(run, group)]),
    ),
  });
}

function clearSelection(): void {
  void recalculate({ selected_group_ids: [], selected_sell_lots: {} });
}

function changeNoteDraft({ groupId, value }: GroupTextIntent): void {
  noteDrafts[groupId] = value;
}

function changeRejectionDraft({ groupId, value }: GroupTextIntent): void {
  rejectionDrafts[groupId] = value;
}

async function saveNote({ groupId, note: submittedDraft }: GroupNoteIntent): Promise<void> {
  const run = currentRun.value;
  if (!run || !canChangeSelection.value || !run.groups.some((group) => group.group_id === groupId))
    return;
  const note = submittedDraft.trim() || null;
  try {
    await store.annotateGroup(run.run_id, groupId, { note });
    const current = currentRun.value;
    const publishedGroup = current?.groups.find((item) => item.group_id === groupId);
    if (
      current?.run_id === run.run_id &&
      publishedGroup?.note === note &&
      noteDrafts[groupId] === submittedDraft
    ) {
      noteDrafts[groupId] = publishedGroup.note ?? '';
    }
  } catch {
    // The store retains a structured API error for the page.
  }
}

async function rejectGroup({ groupId, reason: submittedDraft }: GroupRejectIntent): Promise<void> {
  const run = currentRun.value;
  if (!run || !canChangeSelection.value || !run.groups.some((group) => group.group_id === groupId))
    return;
  const reason = submittedDraft.trim();
  if (!reason || reason.length > 500) return;
  try {
    await store.annotateGroup(run.run_id, groupId, {
      rejected: true,
      rejection_reason: reason,
    });
    const current = currentRun.value;
    const publishedGroup = current?.groups.find((item) => item.group_id === groupId);
    if (
      current?.run_id === run.run_id &&
      publishedGroup?.rejected === true &&
      publishedGroup.rejection_reason === reason &&
      rejectionDrafts[groupId] === submittedDraft
    ) {
      rejectionDrafts[groupId] = publishedGroup.rejection_reason ?? '';
    }
  } catch {
    // Rejection failed; the last API-confirmed full basket remains in view.
  }
}

async function restoreGroup({ groupId }: GroupActionIntent): Promise<void> {
  const run = currentRun.value;
  if (!run || !canChangeSelection.value || !run.groups.some((group) => group.group_id === groupId))
    return;
  try {
    await store.annotateGroup(run.run_id, groupId, {
      rejected: false,
    });
  } catch {
    // The store retains a structured API error for the page.
  }
}
async function exportRun(format: ExportFormat): Promise<void> {
  if (!currentRun.value) return;
  try {
    const result = await store.exportRun(currentRun.value.run_id, format);
    const url = URL.createObjectURL(result.blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = result.filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  } catch {
    // The store retains a structured API error for this page.
  }
}

onMounted(() => {
  void store.ensureInitialWorkspace();
});
</script>

<style scoped>
/* Grid gaps use Quasar's spacing scale; negative-margin gutters distort grid tracks. */

.read-only-note,
.empty-inline,
.state-message {
  color: #526c7c;
  font-size: 0.78rem;
  line-height: 1.5;
}

.section-heading > span {
  color: #657d8b;
  font-size: 0.76rem;
}
.filter-panel label {
  flex: 1 1 9rem;
}
.selection-tools {
  border: 1px solid #dce6eb;
  border-radius: 0.65rem;
  min-width: 0;
}
.selection-tools legend {
  color: #29475a;
  font-weight: 800;
}
.top-n-control {
  max-width: 13rem;
}
.group-list {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  min-width: 0;
  gap: 8px;
}
.shared-legs {
  border-top: 1px solid #dce6eb;
}
.shared-legs > p {
  color: #526c7c;
  font-size: 0.78rem;
}

.export-panel > div {
  flex: 1 1 20rem;
}

@media (max-width: 760px) {
  .section-heading {
    flex-direction: column;
    align-items: stretch;
  }
  .saved-run-form {
    justify-content: flex-start;
  }
  .saved-run-form label {
    flex: 1 1 100%;
  }
}
</style>
