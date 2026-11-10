<template>
  <section class="workspace-page q-my-none q-mx-auto q-pa-md" aria-labelledby="lots-title">
    <WorkspacePageHeader
      eyebrow="Portfolio inventory"
      title="Tax Lots"
      title-id="lots-title"
      subtitle="Account-wide lot search; complete-set intent for a current DEMO run only."
    >
      <template #actions>
        <q-btn
          unelevated
          no-caps
          type="button"
          class="primary-button"
          color="primary"
          size="sm"
          :disable="isLoading"
          @click="refreshLots"
        >
          {{ isLoading ? 'Loading…' : 'Refresh lots' }}
        </q-btn>
      </template>
    </WorkspacePageHeader>

    <WorkspaceCapabilityNotice label="DEMO ONLY.">
      No broker connection, OAuth, order preview, or trade submission is available.
    </WorkspaceCapabilityNotice>

    <ApiActionError
      :error="store.actionState.loadLots.error"
      title="Tax lots could not be loaded"
    />

    <ResourceFreshnessNotice :resources="['lots']" />

    <q-card
      tag="form"
      flat
      bordered
      aria-label="Tax lot filters"
      class="filter-panel row items-end q-gutter-sm q-pa-md text-caption text-weight-bold text-blue-grey-8"
      @submit.prevent="applyFilters"
    >
      <label class="column no-wrap q-gutter-y-xs">
        <span>Search all account lots</span>
        <q-input
          outlined
          dense
          hide-bottom-space
          v-model="search"
          type="search"
          placeholder="Ticker or broker lot ID"
        />
      </label>
      <label class="column no-wrap q-gutter-y-xs">
        <span>Holding term</span>
        <q-select
          v-model="termFilter"
          :options="[
            { label: 'All terms', value: '' },
            { label: 'Short term', value: 'ST' },
            { label: 'Long term', value: 'LT' },
          ]"
          emit-value
          map-options
          outlined
          dense
          hide-bottom-space
          aria-label="Holding term"
        />
      </label>
      <label class="column no-wrap q-gutter-y-xs">
        <span>Fractional cleanup</span>
        <q-select
          v-model="fractionalFilter"
          :options="[
            { label: 'All lots', value: '' },
            { label: 'Unsupported fractional cleanup', value: 'true' },
            { label: 'No unsupported fractional cleanup', value: 'false' },
          ]"
          emit-value
          map-options
          outlined
          dense
          hide-bottom-space
          aria-label="Fractional cleanup"
        />
      </label>
      <label class="column no-wrap q-gutter-y-xs">
        <span>Rows per API page</span>
        <q-select
          v-model="pageLimit"
          :options="[
            { label: '50', value: 50 },
            { label: '100', value: 100 },
            { label: '250', value: 250 },
            { label: '500', value: 500 },
          ]"
          emit-value
          map-options
          outlined
          dense
          hide-bottom-space
          aria-label="Rows per API page"
        />
      </label>
      <label class="column no-wrap q-gutter-y-xs">
        <span>Sort API results by</span>
        <q-select
          v-model="sortKey"
          :options="[
            { label: 'Security', value: 'ticker' },
            { label: 'Broker lot ID', value: 'broker_lot_id' },
            { label: 'Acquired date', value: 'acquired_date' },
            { label: 'Remaining shares', value: 'remaining_shares' },
            { label: 'Available shares', value: 'available_shares' },
            { label: 'Unit basis', value: 'adjusted_unit_basis_usd' },
            { label: 'Total basis', value: 'adjusted_total_basis_usd' },
            { label: 'Current price', value: 'current_price_usd' },
            { label: 'Unrealized P/L (USD)', value: 'unrealized_pl_usd' },
            { label: 'Unrealized P/L (%)', value: 'unrealized_pl_pct' },
            { label: 'Holding term', value: 'term' },
            { label: 'Sleeve', value: 'sleeve_key' },
            { label: 'Sub-sleeve', value: 'sub_sleeve_key' },
          ]"
          emit-value
          map-options
          outlined
          dense
          hide-bottom-space
          :disable="isLoading"
          aria-label="Sort API results by"
          @update:model-value="applyFilters"
        />
      </label>
      <q-btn
        no-caps
        type="button"
        class="icon-button"
        outline
        color="primary"
        size="sm"
        :disable="isLoading"
        :aria-label="sortDirection === 'asc' ? 'Sort ascending' : 'Sort descending'"
        @click="toggleSortDirection"
      >
        {{ sortDirection === 'asc' ? 'Ascending' : 'Descending' }}
      </q-btn>
      <q-btn
        no-caps
        type="submit"
        class="secondary-button"
        outline
        color="primary"
        size="sm"
        :disable="isLoading"
      >
        Apply API filters
      </q-btn>
    </q-card>

    <q-banner
      v-if="store.actionState.loadLots.pending && !store.lots"
      dense
      rounded
      class="q-mt-none bg-blue-grey-1 text-blue-grey-10"
      role="status"
    >
      Loading tax lots from the local API…
    </q-banner>
    <WorkspaceEmptyState v-else-if="!store.lots" title="No lot page loaded">
      Load the current API page to see broker-reported lots.
      <template #action>
        <q-btn
          no-caps
          type="button"
          class="secondary-button"
          outline
          color="primary"
          size="sm"
          :disable="isLoading"
          @click="refreshLots"
        >
          Retry loading lots
        </q-btn>
      </template>
    </WorkspaceEmptyState>
    <WorkspaceEmptyState v-else-if="store.lots.items.length === 0" title="No lots returned">
      The API returned an empty page for these filters.
    </WorkspaceEmptyState>
    <template v-else>
      <div
        class="results-heading row no-wrap items-center justify-between q-gutter-md text-caption text-blue-grey-7"
      >
        <p class="q-mr-none q-mb-none">
          API page {{ pageNumber }} · {{ store.lots.items.length }} rows returned ·
          {{ store.lots.total }} rows match the account-wide filters before pagination.
        </p>
      </div>

      <WorkspaceEmptyState v-if="filteredLots.length === 0" title="No matching lots">
        No lots on this API page match the account-wide filters.
      </WorkspaceEmptyState>
      <div v-else class="security-groups column no-wrap q-gutter-y-md">
        <q-card
          tag="section"
          flat
          bordered
          v-for="group in groupedLots"
          :key="group.ticker"
          class="security-card q-pa-none"
          :aria-labelledby="`security-${group.ticker}`"
        >
          <header
            class="security-heading row no-wrap items-center justify-between q-gutter-md q-pa-md"
          >
            <h2
              class="q-mr-none q-mb-none text-subtitle1 text-blue-grey-10"
              :id="`security-${group.ticker}`"
            >
              {{ group.ticker }}
            </h2>
            <span class="text-caption text-blue-grey-7"
              >{{ group.lots.length }} {{ group.lots.length === 1 ? 'lot' : 'lots' }}</span
            >
          </header>
          <WorkspaceTableFrame :label="`Tax lots for ${group.ticker}`">
            <q-markup-table class="tax-lot-table" wrap-cells>
              <caption class="sr-only">
                Tax lots for
                {{
                  group.ticker
                }}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Intent</th>
                  <th scope="col">Broker lot ID</th>
                  <th scope="col">Acquired</th>
                  <th scope="col">Remaining / available shares</th>
                  <th scope="col">Adjusted basis (unit / total)</th>
                  <th scope="col">Current price</th>
                  <th scope="col">Unrealized P/L (USD / %)</th>
                  <th scope="col">Term</th>
                  <th scope="col">Sleeve</th>
                  <th scope="col">Quality and cleanup flags</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="lot in group.lots" :key="lot.broker_lot_id">
                  <td>
                    <q-checkbox
                      dense
                      color="primary"
                      :model-value="requestedLotIds.has(lot.broker_lot_id)"
                      :disable="!canChangeLotIntent"
                      :aria-label="`Request ${lot.ticker} lot ${lot.broker_lot_id}`"
                      :label="requestedLotIds.has(lot.broker_lot_id) ? 'Requested' : 'Request'"
                      @update:model-value="changeLotIntent(lot, $event)"
                    />
                    <small
                      v-if="confirmedLotIds.has(lot.broker_lot_id)"
                      class="sub-value block q-mt-xs"
                    >
                      Backend-confirmed in loaded DEMO run
                    </small>
                  </td>
                  <th scope="row" class="lot-id">
                    <BrokerLotIdentity :broker-lot-id="lot.broker_lot_id" />
                  </th>
                  <td>{{ lot.acquired_date }}</td>
                  <td>
                    {{ lot.remaining_shares }} / {{ lot.available_shares }}
                    <small class="sub-value block q-mt-xs">
                      Whole shares available: {{ lot.whole_shares_available }}; fractional
                      remainder:
                      {{ lot.fractional_shares }}
                    </small>
                  </td>
                  <td>
                    {{ formatUsd(lot.adjusted_unit_basis_usd) }} /
                    {{ formatUsd(lot.adjusted_total_basis_usd) }}
                  </td>
                  <td>{{ formatUsd(lot.current_price_usd) }}</td>
                  <td>
                    {{ formatUsd(lot.unrealized_pl_usd) }} /
                    {{ formatPercent(lot.unrealized_pl_pct) }}
                  </td>
                  <td>{{ lot.term }}</td>
                  <td>
                    {{ lot.sleeve_key ?? 'Unassigned' }}
                    <small v-if="lot.sub_sleeve_key" class="sub-value block q-mt-xs">{{
                      lot.sub_sleeve_key
                    }}</small>
                  </td>
                  <td>
                    <ul
                      class="flag-list q-mr-none q-mb-none q-ml-none q-pl-md column no-wrap q-gutter-y-xs"
                    >
                      <li v-for="flag in lot.quality_flags" :key="flag">{{ flag }}</li>
                      <li v-if="lot.small_lot_cleanup_candidate">Small-lot cleanup candidate</li>
                      <li v-if="lot.position_cleanup_candidate">Only lot in position</li>
                      <li v-if="lot.fractional_cleanup_unsupported">
                        Fractional cleanup unsupported; not executable
                      </li>
                      <li v-if="lot.quality_flags.length === 0 && !hasCleanupFlag(lot)">
                        No quality or cleanup flags reported
                      </li>
                    </ul>
                    <small class="sub-value block q-mt-xs"
                      >{{ lot.source }} · as of {{ lot.as_of }}</small
                    >
                  </td>
                </tr>
              </tbody>
            </q-markup-table>
          </WorkspaceTableFrame>
        </q-card>
      </div>
    </template>
    <WorkspacePagination
      v-if="store.lots"
      :offset="store.lots.offset"
      :limit="store.lots.limit"
      :total="store.lots.total"
      :pending="isLoading || filterDraftChanged"
      label="Tax lot API pages"
      @page="loadLots"
    />

    <q-card
      tag="section"
      flat
      bordered
      class="review-summary q-pa-md text-body2 text-blue-grey-7"
      aria-labelledby="review-title"
    >
      <h2 class="q-mt-none q-mb-sm text-subtitle1 text-blue-grey-10" id="review-title">
        Requested lot intent · {{ store.lotReviewIntent.length }}
      </h2>
      <p class="q-mt-none q-mb-sm">
        This is a complete replacement set, not an additive change: apply submits every requested
        broker lot ID, and an explicitly empty set clears the DEMO recommendation basket. Requested
        intent is not backend-confirmed selection and neither one approves an order. Only a
        successful response updates the confirmed run; the endpoint re-solves saved DEMO candidates
        only and does not create candidates or a run.
      </p>
      <ApiActionError
        :error="store.actionState.applyLotReviewIntent.error"
        title="Requested lot set was not applied"
      />
      <q-banner
        v-if="
          store.lotReviewIntentGeneration !== null &&
          store.lotReviewIntentConfirmedRunId === store.currentRun?.run_id &&
          !store.lotReviewIntentDirty &&
          !store.actionState.applyLotReviewIntent.error
        "
        dense
        rounded
        class="q-mt-none q-mb-sm bg-blue-grey-1 text-blue-grey-10"
        role="status"
      >
        The loaded DEMO run currently selects exactly this requested set. This is recommendation
        state only, not order approval.
      </q-banner>
      <q-banner
        v-if="store.lotReviewIntentNotice"
        dense
        rounded
        class="q-mt-none q-mb-sm bg-blue-grey-1 text-blue-grey-10"
        role="status"
      >
        {{ store.lotReviewIntentNotice }}
      </q-banner>
      <q-banner
        v-if="store.lots?.source_generation === null"
        dense
        rounded
        class="q-mt-none q-mb-sm bg-blue-grey-1 text-blue-grey-10"
        role="status"
      >
        This lot page has no source generation. It is unvalidated; lot intent cannot be submitted.
      </q-banner>
      <q-banner
        v-else-if="store.lots && !lotPageGenerationMatches"
        dense
        rounded
        class="q-mt-none q-mb-sm bg-blue-grey-1 text-blue-grey-10"
        role="status"
      >
        This page is from source generation {{ store.lots.source_generation }}, but the workspace
        currently observes generation {{ store.observedSourceGeneration ?? 'unavailable' }}. Refresh
        lots before marking or submitting any set.
      </q-banner>
      <q-banner
        v-if="basketUnchanged"
        dense
        rounded
        class="q-mt-none q-mb-sm bg-blue-grey-1 text-blue-grey-10"
        role="status"
      >
        The API rejected the complete request atomically. Backend-confirmed selection is unchanged.
      </q-banner>
      <ul
        class="q-mr-none q-mb-none q-ml-none q-pl-md q-gutter-y-xs"
        v-if="rejectedLotReasons.length"
        aria-label="Requested lot rejection reasons"
      >
        <li v-for="entry in rejectedLotReasons" :key="entry.broker_lot_id">
          {{ entry.broker_lot_id }}: {{ rejectionReasonLabel(entry.reason) }} ({{ entry.reason }})
        </li>
      </ul>
      <q-banner
        v-if="store.currentRunView === 'stale'"
        dense
        rounded
        class="q-mt-none q-mb-sm bg-blue-grey-1 text-blue-grey-10"
        role="status"
      >
        The loaded DEMO run is stale. Create a current DEMO run before applying intent; this page
        will not silently create or merge one.
      </q-banner>
      <q-banner
        v-else-if="!currentRunIsUsable"
        dense
        rounded
        class="q-mt-none q-mb-sm bg-blue-grey-1 text-blue-grey-10"
        role="status"
      >
        No current DEMO run is available. Create a run in Overview or Recommendations, then return
        here. Saved runs remain read-only.
      </q-banner>
      <p v-else class="sub-value q-mt-xs q-mb-sm">
        Target run {{ store.currentRun?.run_id }} · source generation
        {{ store.currentRun?.source_generation }}
      </p>
      <ul class="q-ma-none q-pl-md" v-if="store.lotReviewIntent.length > 0">
        <li v-for="entry in store.lotReviewIntent" :key="entry.broker_lot_id">
          {{ entry.ticker }} · {{ entry.broker_lot_id }} · generation {{ entry.source_generation }}
          <q-btn
            no-caps
            type="button"
            class="text-button"
            flat
            color="primary"
            size="sm"
            :disable="store.reviewMutationPending"
            @click="removeRequestedLot(entry)"
          >
            Remove from requested set
          </q-btn>
        </li>
      </ul>
      <p v-else class="sub-value q-mt-xs q-mb-sm">
        Requested set is empty; clearing is explicit and must be applied.
      </p>
      <p class="sub-value q-mt-xs q-mb-sm">
        Backend-confirmed selected SELL lot IDs in the loaded run:
        {{ confirmedBrokerLotIds.join(', ') || 'none' }}
      </p>
      <div class="intent-actions">
        <q-btn
          no-caps
          type="button"
          class="secondary-button"
          outline
          color="primary"
          size="sm"
          :disable="!canChangeLotIntent"
          @click="clearRequestedLots"
        >
          Explicitly request an empty set
        </q-btn>
        <q-btn
          unelevated
          no-caps
          type="button"
          class="primary-button"
          color="primary"
          size="sm"
          :disable="!canApplyLotIntent"
          @click="applyRequestedLots"
        >
          {{
            store.actionState.applyLotReviewIntent.pending
              ? 'Applying complete set…'
              : store.lotReviewIntent.length === 0
                ? 'Apply empty set and clear confirmed basket'
                : 'Apply complete set to current DEMO run'
          }}
        </q-btn>
      </div>
    </q-card>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import ApiActionError from '@/components/ApiActionError.vue';
import BrokerLotIdentity from '@/components/BrokerLotIdentity.vue';
import WorkspacePageHeader from '@/components/WorkspacePageHeader.vue';
import WorkspaceCapabilityNotice from '@/components/WorkspaceCapabilityNotice.vue';
import WorkspaceEmptyState from '@/components/WorkspaceEmptyState.vue';
import WorkspacePagination from '@/components/WorkspacePagination.vue';
import WorkspaceTableFrame from '@/components/WorkspaceTableFrame.vue';
import { getPaginationMetadata } from '@/components/workspace-pagination-state';
import ResourceFreshnessNotice from '@/components/ResourceFreshnessNotice.vue';
import { useWorkspaceStore } from '@/stores/workspace-store';
import type { LotQuery } from '@/services/api';
import type { LotResponse } from '@/types/api';
import { formatPercent, formatUsd } from '@/utils/display-values';

const store = useWorkspaceStore();
const search = ref(store.lotFilters.search ?? '');
const termFilter = ref(store.lotFilters.term ?? '');
const fractionalFilter = ref(
  store.lotFilters.fractional === undefined || store.lotFilters.fractional === null
    ? ''
    : String(store.lotFilters.fractional),
);
const pageLimit = ref(store.lotFilters.limit ?? 100);
const sortKey = ref<NonNullable<LotQuery['sort_by']>>(store.lotFilters.sort_by ?? 'ticker');
const sortDirection = ref<NonNullable<LotQuery['sort_direction']>>(
  store.lotFilters.sort_direction ?? 'asc',
);
const isLoading = computed(() => store.actionState.loadLots.pending);
const pagination = computed(() => {
  const page = store.lots;
  return getPaginationMetadata(page?.offset ?? 0, page?.limit ?? 1, page?.total ?? 0);
});
const pageNumber = computed(() => pagination.value.pageNumber);
const filteredLots = computed(() => store.lots?.items ?? []);
const requestedLotIds = computed(
  () => new Set(store.lotReviewIntent.map((entry) => entry.broker_lot_id)),
);
const confirmedLotIds = computed(() => {
  const ids = new Set<string>();
  for (const leg of store.currentRun?.consolidated_legs ?? []) {
    if (leg.side !== 'SELL') continue;
    for (const lot of leg.selected_lots) {
      if (lot.selected) ids.add(lot.broker_lot_id);
    }
  }
  return ids;
});
const lotPageGenerationMatches = computed(
  () =>
    store.lots !== null &&
    store.lots.source_generation !== null &&
    store.lots.source_generation === store.observedSourceGeneration,
);
const currentRunIsUsable = computed(
  () =>
    store.currentRun !== null &&
    store.currentRunView === 'current' &&
    store.currentRun.source_generation === store.observedSourceGeneration &&
    store.currentRun.source_generation === store.lots?.source_generation,
);
const canChangeLotIntent = computed(
  () => lotPageGenerationMatches.value && !isLoading.value && !store.reviewMutationPending,
);
const canApplyLotIntent = computed(
  () =>
    canChangeLotIntent.value &&
    currentRunIsUsable.value &&
    store.lotReviewIntentDirty &&
    !store.reviewMutationPending,
);
const groupedLots = computed(() => {
  const groups = new Map<string, LotResponse[]>();
  for (const lot of filteredLots.value) {
    const rows = groups.get(lot.ticker) ?? [];
    rows.push(lot);
    groups.set(lot.ticker, rows);
  }
  return [...groups.entries()].map(([ticker, lots]) => ({ ticker, lots }));
});
const confirmedBrokerLotIds = computed(() => [...confirmedLotIds.value].sort());
const rejectedLotReasons = computed(() => {
  const details = store.actionState.applyLotReviewIntent.error?.details;
  if (details === null || typeof details !== 'object' || Array.isArray(details)) return [];
  const rejected = details['rejected_lots'];
  if (!Array.isArray(rejected)) return [];
  return rejected.flatMap((entry) => {
    if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) return [];
    const brokerLotId = entry['broker_lot_id'];
    const reason = entry['reason'];
    return typeof brokerLotId === 'string' && typeof reason === 'string'
      ? [{ broker_lot_id: brokerLotId, reason }]
      : [];
  });
});
const basketUnchanged = computed(() => {
  const details = store.actionState.applyLotReviewIntent.error?.details;
  return (
    details !== null &&
    typeof details === 'object' &&
    !Array.isArray(details) &&
    details['basket_unchanged'] === true
  );
});

function currentFilters(offset: number): LotQuery {
  return {
    ...(search.value.trim() ? { search: search.value.trim() } : {}),
    ...(termFilter.value ? { term: termFilter.value } : {}),
    ...(fractionalFilter.value === '' ? {} : { fractional: fractionalFilter.value === 'true' }),
    sort_by: sortKey.value,
    sort_direction: sortDirection.value,
    offset,
    limit: pageLimit.value,
  };
}

const filterDraftChanged = computed(() => {
  const draft = currentFilters(0);
  const applied = store.lotFilters;
  return (
    (draft.search ?? undefined) !== (applied.search ?? undefined) ||
    (draft.term ?? undefined) !== (applied.term ?? undefined) ||
    (draft.fractional ?? undefined) !== (applied.fractional ?? undefined) ||
    draft.sort_by !== applied.sort_by ||
    draft.sort_direction !== applied.sort_direction ||
    draft.limit !== applied.limit
  );
});

function hasCleanupFlag(lot: LotResponse): boolean {
  return (
    lot.small_lot_cleanup_candidate ||
    lot.position_cleanup_candidate ||
    lot.fractional_cleanup_unsupported
  );
}

async function loadLots(offset: number): Promise<void> {
  try {
    await store.loadLots({ ...store.lotFilters, offset });
  } catch {
    // The shared store retains the structured API error for the page.
  }
}

function applyFilters(): void {
  void loadWithFilters(0);
}

async function loadWithFilters(offset: number): Promise<void> {
  try {
    await store.loadLots(currentFilters(offset));
  } catch {
    // The shared store retains the structured API error for the page.
  }
}

function refreshLots(): void {
  void loadLots(store.lots?.offset ?? store.lotFilters.offset ?? 0);
}

function toggleSortDirection(): void {
  sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc';
  applyFilters();
}

function changeLotIntent(lot: LotResponse, requested: boolean): void {
  store.setLotReviewIntent(
    lot.broker_lot_id,
    lot.ticker,
    store.lots?.source_generation ?? null,
    requested,
  );
}

function removeRequestedLot(entry: {
  broker_lot_id: string;
  ticker: string;
  source_generation: number;
}): void {
  store.setLotReviewIntent(entry.broker_lot_id, entry.ticker, entry.source_generation, false);
}

function clearRequestedLots(): void {
  store.clearLotReviewIntent();
}

async function applyRequestedLots(): Promise<void> {
  try {
    await store.applyLotReviewIntent();
  } catch {
    // The shared store retains the structured API error and confirmed run on failure.
  }
}

function rejectionReasonLabel(reason: string): string {
  switch (reason) {
    case 'missing_current_lot':
      return 'This broker lot is not present in current inventory.';
    case 'outside_saved_demo_candidates':
      return 'This lot is not represented by a saved DEMO candidate; no candidate was generated.';
    case 'ambiguous_saved_demo_candidate':
      return 'This lot maps to multiple saved DEMO candidates and cannot be applied.';
    default:
      return reason;
  }
}

onMounted(() => {
  void loadWithFilters(store.lotFilters.offset ?? 0);
});
</script>

<style scoped>
.filter-panel {
  min-width: 0;
}

.security-card {
  min-width: 0;
  overflow: hidden;
}

.filter-panel label {
  min-width: min(13rem, 100%);
}

.security-heading {
  border-bottom: 1px solid #eaf0f3;
}
.tax-lot-table {
  min-width: 1150px;
}
.lot-id {
  overflow-wrap: anywhere;
}
.sub-value {
  color: #718792;
  font-size: 0.67rem;
  line-height: 1.4;
}
.flag-list {
  color: #725528;
}
/* Keep content available to assistive technology without occupying layout space. */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  clip-path: inset(50%);
}
@media (max-width: 760px) {
  .results-heading {
    align-items: stretch;
    flex-direction: column;
  }
  .filter-panel label {
    width: 100%;
  }
}
</style>
