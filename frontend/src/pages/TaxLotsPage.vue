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

    <WorkspaceFilterPanel
      label="Tax lot filters"
      class="filter-panel row items-end q-gutter-sm q-pa-md"
      @submit="applyFilters"
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
        unelevated
        no-caps
        type="button"
        class="icon-button"
        :disable="isLoading"
        :aria-label="sortDirection === 'asc' ? 'Sort ascending' : 'Sort descending'"
        @click="toggleSortDirection"
      >
        {{ sortDirection === 'asc' ? 'Ascending' : 'Descending' }}
      </q-btn>
      <q-btn unelevated no-caps type="submit" class="secondary-button" :disable="isLoading">
        Apply API filters
      </q-btn>
    </WorkspaceFilterPanel>

    <p
      v-if="store.actionState.loadLots.pending && !store.lots"
      class="state-message q-mt-none"
      role="status"
    >
      Loading tax lots from the local API…
    </p>
    <WorkspaceEmptyState v-else-if="!store.lots" title="No lot page loaded">
      Load the current API page to see broker-reported lots.
      <template #action>
        <q-btn
          unelevated
          no-caps
          type="button"
          class="secondary-button"
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
      <div class="results-heading row no-wrap items-center justify-between q-gutter-md">
        <p class="q-mr-none q-mb-none">
          API page {{ pageNumber }} · {{ store.lots.items.length }} rows returned ·
          {{ store.lots.total }} rows match the account-wide filters before pagination.
        </p>
      </div>

      <WorkspaceEmptyState v-if="filteredLots.length === 0" title="No matching lots">
        No lots on this API page match the account-wide filters.
      </WorkspaceEmptyState>
      <div v-else class="security-groups column no-wrap q-gutter-y-md">
        <section
          v-for="group in groupedLots"
          :key="group.ticker"
          class="security-card q-pa-none"
          :aria-labelledby="`security-${group.ticker}`"
        >
          <header
            class="security-heading row no-wrap items-center justify-between q-gutter-md q-pa-md"
          >
            <h2 class="q-mr-none q-mb-none" :id="`security-${group.ticker}`">{{ group.ticker }}</h2>
            <span>{{ group.lots.length }} {{ group.lots.length === 1 ? 'lot' : 'lots' }}</span>
          </header>
          <WorkspaceTableFrame :label="`Tax lots for ${group.ticker}`" class="table-scroll">
            <table>
              <caption class="sr-only">
                Tax lots for
                {{
                  group.ticker
                }}
              </caption>
              <thead>
                <tr>
                  <th class="q-pa-sm" scope="col">Intent</th>
                  <th class="q-pa-sm" scope="col">Broker lot ID</th>
                  <th class="q-pa-sm" scope="col">Acquired</th>
                  <th class="q-pa-sm" scope="col">Remaining / available shares</th>
                  <th class="q-pa-sm" scope="col">Adjusted basis (unit / total)</th>
                  <th class="q-pa-sm" scope="col">Current price</th>
                  <th class="q-pa-sm" scope="col">Unrealized P/L (USD / %)</th>
                  <th class="q-pa-sm" scope="col">Term</th>
                  <th class="q-pa-sm" scope="col">Sleeve</th>
                  <th class="q-pa-sm" scope="col">Quality and cleanup flags</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="lot in group.lots" :key="lot.broker_lot_id">
                  <td class="q-pa-sm">
                    <q-checkbox
                      class="review-toggle"
                      dense
                      color="primary"
                      :model-value="requestedLotIds.has(lot.broker_lot_id)"
                      :disable="!canChangeLotIntent"
                      :aria-label="`Request ${lot.ticker} lot ${lot.broker_lot_id}`"
                      :label="requestedLotIds.has(lot.broker_lot_id) ? 'Requested' : 'Request'"
                      @update:model-value="changeLotIntent(lot, $event)"
                    />
                    <small v-if="confirmedLotIds.has(lot.broker_lot_id)" class="sub-value q-mt-xs">
                      Backend-confirmed in loaded DEMO run
                    </small>
                  </td>
                  <th scope="row" class="lot-id q-pa-sm">
                    <BrokerLotIdentity :broker-lot-id="lot.broker_lot_id" />
                  </th>
                  <td class="q-pa-sm">{{ lot.acquired_date }}</td>
                  <td class="q-pa-sm">
                    {{ lot.remaining_shares }} / {{ lot.available_shares }}
                    <small class="sub-value q-mt-xs">
                      Whole shares available: {{ lot.whole_shares_available }}; fractional
                      remainder:
                      {{ lot.fractional_shares }}
                    </small>
                  </td>
                  <td class="q-pa-sm">
                    {{ formatUsd(lot.adjusted_unit_basis_usd) }} /
                    {{ formatUsd(lot.adjusted_total_basis_usd) }}
                  </td>
                  <td class="q-pa-sm">{{ formatUsd(lot.current_price_usd) }}</td>
                  <td class="q-pa-sm">
                    {{ formatUsd(lot.unrealized_pl_usd) }} /
                    {{ formatPercent(lot.unrealized_pl_pct) }}
                  </td>
                  <td class="q-pa-sm">{{ lot.term }}</td>
                  <td class="q-pa-sm">
                    {{ lot.sleeve_key ?? 'Unassigned' }}
                    <small v-if="lot.sub_sleeve_key" class="sub-value q-mt-xs">{{
                      lot.sub_sleeve_key
                    }}</small>
                  </td>
                  <td class="q-pa-sm">
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
                    <small class="sub-value q-mt-xs"
                      >{{ lot.source }} · as of {{ lot.as_of }}</small
                    >
                  </td>
                </tr>
              </tbody>
            </table>
          </WorkspaceTableFrame>
        </section>
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

    <section class="review-summary q-pa-md" aria-labelledby="review-title">
      <h2 class="q-mt-none q-mb-sm" id="review-title">
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
      <p
        v-if="
          store.lotReviewIntentGeneration !== null &&
          store.lotReviewIntentConfirmedRunId === store.currentRun?.run_id &&
          !store.lotReviewIntentDirty &&
          !store.actionState.applyLotReviewIntent.error
        "
        class="state-message q-mt-none q-mb-sm"
        role="status"
      >
        The loaded DEMO run currently selects exactly this requested set. This is recommendation
        state only, not order approval.
      </p>
      <p v-if="store.lotReviewIntentNotice" class="state-message q-mt-none q-mb-sm" role="status">
        {{ store.lotReviewIntentNotice }}
      </p>
      <p
        v-if="store.lots?.source_generation === null"
        class="state-message q-mt-none q-mb-sm"
        role="status"
      >
        This lot page has no source generation. It is unvalidated; lot intent cannot be submitted.
      </p>
      <p
        v-else-if="store.lots && !lotPageGenerationMatches"
        class="state-message q-mt-none q-mb-sm"
        role="status"
      >
        This page is from source generation {{ store.lots.source_generation }}, but the workspace
        currently observes generation {{ store.observedSourceGeneration ?? 'unavailable' }}. Refresh
        lots before marking or submitting any set.
      </p>
      <p v-if="basketUnchanged" class="state-message q-mt-none q-mb-sm" role="status">
        The API rejected the complete request atomically. Backend-confirmed selection is unchanged.
      </p>
      <ul
        class="q-mr-none q-mb-none q-ml-none q-pl-md q-gutter-y-xs"
        v-if="rejectedLotReasons.length"
        aria-label="Requested lot rejection reasons"
      >
        <li v-for="entry in rejectedLotReasons" :key="entry.broker_lot_id">
          {{ entry.broker_lot_id }}: {{ rejectionReasonLabel(entry.reason) }} ({{ entry.reason }})
        </li>
      </ul>
      <p
        v-if="store.currentRunView === 'stale'"
        class="state-message q-mt-none q-mb-sm"
        role="status"
      >
        The loaded DEMO run is stale. Create a current DEMO run before applying intent; this page
        will not silently create or merge one.
      </p>
      <p v-else-if="!currentRunIsUsable" class="state-message q-mt-none q-mb-sm" role="status">
        No current DEMO run is available. Create a run in Overview or Recommendations, then return
        here. Saved runs remain read-only.
      </p>
      <p v-else class="sub-value q-mt-xs q-mb-sm">
        Target run {{ store.currentRun?.run_id }} · source generation
        {{ store.currentRun?.source_generation }}
      </p>
      <ul class="q-ma-none q-pl-md" v-if="store.lotReviewIntent.length > 0">
        <li v-for="entry in store.lotReviewIntent" :key="entry.broker_lot_id">
          {{ entry.ticker }} · {{ entry.broker_lot_id }} · generation {{ entry.source_generation }}
          <q-btn
            unelevated
            no-caps
            type="button"
            class="text-button"
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
          unelevated
          no-caps
          type="button"
          class="secondary-button"
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
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import ApiActionError from '@/components/ApiActionError.vue';
import BrokerLotIdentity from '@/components/BrokerLotIdentity.vue';
import WorkspacePageHeader from '@/components/WorkspacePageHeader.vue';
import WorkspaceCapabilityNotice from '@/components/WorkspaceCapabilityNotice.vue';
import WorkspaceEmptyState from '@/components/WorkspaceEmptyState.vue';
import WorkspaceFilterPanel from '@/components/WorkspaceFilterPanel.vue';
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
.filter-panel,
.review-summary,
.security-card,
.empty-state {
  border: 1px solid #dce6eb;
  border-radius: 0.8rem;
  background: #fff;
  box-shadow: 0 4px 20px rgb(18 55 77 / 4.5%);
}

.filter-panel label,
.sort-control {
  color: #466779;
  font-size: 0.75rem;
  font-weight: 700;
}
.primary-button {
  border-color: #067777;
  background: #087f7d;
  color: white;
}
.secondary-button,
.icon-button {
  border-color: #bfd0d8;
  background: #f7fafb;
}
.text-button {
  border: 0;
  color: #087f7d;
  text-decoration: underline;
}
.results-heading {
  color: #526c7c;
  font-size: 0.76rem;
}

.sort-control {
  display: flex;
  align-items: center;
}

.security-card {
  min-width: 0;
  overflow: hidden;
}
.security-heading {
  border-bottom: 1px solid #eaf0f3;
}
.security-heading h2 {
  color: #10263d;
  font-size: 1rem;
}
.security-heading span {
  color: #647c8b;
  font-size: 0.75rem;
}
.table-scroll {
  overflow-x: auto;
}
table {
  width: 100%;
  min-width: 1150px;
  border-collapse: collapse;
  font-size: 0.73rem;
}
th,
td {
  border-bottom: 1px solid #edf2f4;
  text-align: left;
  vertical-align: top;
}
thead th {
  background: #f7fafb;
  color: #526c7c;
  font-size: 0.67rem;
}
tbody th {
  color: #29475a;
  font-weight: 750;
}
.lot-id {
  overflow-wrap: anywhere;
}
.review-toggle {
  display: inline-flex;
  align-items: center;
  white-space: nowrap;
}
.sub-value {
  display: block;
  color: #718792;
  font-size: 0.67rem;
  line-height: 1.4;
}
.flag-list {
  color: #725528;
}
.state-message,
.empty-state,
.review-summary p {
  color: #657d8b;
  font-size: 0.8rem;
  line-height: 1.5;
}
.empty-state h2,
.review-summary h2 {
  color: #10263d;
  font-size: 1rem;
}

.review-summary ul {
  color: #29475a;
  font-size: 0.78rem;
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
  .filter-panel label,
  .filter-panel input[type='search'] {
    width: 100%;
  }
  .sort-control {
    flex-wrap: wrap;
  }
}
</style>
