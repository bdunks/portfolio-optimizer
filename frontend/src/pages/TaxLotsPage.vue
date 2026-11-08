<template>
  <section class="workspace-page" aria-labelledby="lots-title">
    <header class="page-header">
      <div>
        <p class="eyebrow">Portfolio inventory</p>
        <h1 id="lots-title">Tax Lots</h1>
        <p class="page-subtitle">
          API-reported lot details grouped by security. Review marking is local to this page and
          does not create or approve a trade.
        </p>
      </div>
      <button type="button" class="primary-button" :disabled="isLoading" @click="refreshLots">
        {{ isLoading ? 'Loading…' : 'Refresh lots' }}
      </button>
    </header>

    <p class="demo-notice" role="status">
      <strong>DEMO ONLY.</strong> No broker connection, OAuth, order preview, or trade submission is
      available.
    </p>

    <ApiActionError
      :error="store.actionState.loadLots.error"
      title="Tax lots could not be loaded"
    />

    <form class="filter-panel" @submit.prevent="applyFilters">
      <label>
        <span>Search this loaded page</span>
        <input v-model="search" type="search" placeholder="Ticker or broker lot ID" />
      </label>
      <label>
        <span>Holding term</span>
        <select v-model="termFilter">
          <option value="">All terms</option>
          <option value="ST">Short term</option>
          <option value="LT">Long term</option>
        </select>
      </label>
      <label>
        <span>Fractional cleanup</span>
        <select v-model="fractionalFilter">
          <option value="">All lots</option>
          <option value="true">Unsupported fractional cleanup</option>
          <option value="false">No unsupported fractional cleanup</option>
        </select>
      </label>
      <label>
        <span>Rows per API page</span>
        <select v-model.number="pageLimit">
          <option :value="50">50</option>
          <option :value="100">100</option>
          <option :value="250">250</option>
          <option :value="500">500</option>
        </select>
      </label>
      <button type="submit" class="secondary-button" :disabled="isLoading">
        Apply API filters
      </button>
    </form>

    <p v-if="store.actionState.loadLots.pending && !store.lots" class="state-message" role="status">
      Loading tax lots from the local API…
    </p>
    <section v-else-if="!store.lots" class="empty-state" aria-live="polite">
      <h2>No lot page loaded</h2>
      <p>Load the current API page to see broker-reported lots.</p>
      <button type="button" class="secondary-button" :disabled="isLoading" @click="refreshLots">
        Retry loading lots
      </button>
    </section>
    <section v-else-if="store.lots.items.length === 0" class="empty-state" aria-live="polite">
      <h2>No lots returned</h2>
      <p>The API returned an empty page for these filters.</p>
    </section>
    <template v-else>
      <div class="results-heading">
        <p>
          API page {{ pageNumber }} · {{ store.lots.items.length }} rows returned ·
          {{ store.lots.total }} rows match the API filters. Search applies to this loaded page
          only.
        </p>
        <label class="sort-control">
          <span>Sort loaded rows by</span>
          <select v-model="sortKey">
            <option value="ticker">Security</option>
            <option value="acquired_date">Acquired date</option>
            <option value="broker_lot_id">Broker lot ID</option>
          </select>
          <button
            type="button"
            class="icon-button"
            :aria-label="sortDirection === 'asc' ? 'Sort ascending' : 'Sort descending'"
            @click="toggleSortDirection"
          >
            {{ sortDirection === 'asc' ? 'Ascending' : 'Descending' }}
          </button>
        </label>
      </div>

      <p v-if="filteredLots.length === 0" class="empty-state" role="status">
        No lots on this API page match the search text.
      </p>
      <div v-else class="security-groups">
        <section
          v-for="group in groupedLots"
          :key="group.ticker"
          class="security-card"
          :aria-labelledby="`security-${group.ticker}`"
        >
          <header class="security-heading">
            <h2 :id="`security-${group.ticker}`">{{ group.ticker }}</h2>
            <span>{{ group.lots.length }} {{ group.lots.length === 1 ? 'lot' : 'lots' }}</span>
          </header>
          <div class="table-scroll">
            <table>
              <caption class="sr-only">
                Tax lots for
                {{
                  group.ticker
                }}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Review</th>
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
                <tr v-for="lot in group.lots" :key="lotReviewKey(lot)">
                  <td>
                    <label class="review-toggle">
                      <input
                        type="checkbox"
                        :checked="reviewSelection.has(lotReviewKey(lot))"
                        :aria-label="`Mark ${lot.ticker} lot ${lot.broker_lot_id} for review`"
                        @change="changeReviewSelection(lot, $event)"
                      />
                      <span>Mark</span>
                    </label>
                  </td>
                  <th scope="row" class="lot-id">{{ lot.broker_lot_id }}</th>
                  <td>{{ lot.acquired_date }}</td>
                  <td>
                    {{ lot.remaining_shares }} / {{ lot.available_shares }}
                    <small class="sub-value">
                      Whole shares available: {{ lot.whole_shares_available }}; fractional
                      remainder:
                      {{ lot.fractional_shares }}
                    </small>
                  </td>
                  <td>
                    {{ displayUsd(lot.adjusted_unit_basis_usd) }} /
                    {{ displayUsd(lot.adjusted_total_basis_usd) }}
                  </td>
                  <td>{{ displayUsd(lot.current_price_usd) }}</td>
                  <td>
                    {{ displayUsd(lot.unrealized_pl_usd) }} /
                    {{ displayPercent(lot.unrealized_pl_pct) }}
                  </td>
                  <td>{{ lot.term }}</td>
                  <td>
                    {{ lot.sleeve_key ?? 'Unassigned' }}
                    <small v-if="lot.sub_sleeve_key" class="sub-value">{{
                      lot.sub_sleeve_key
                    }}</small>
                  </td>
                  <td>
                    <ul class="flag-list">
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
                    <small class="sub-value">{{ lot.source }} · as of {{ lot.as_of }}</small>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </template>
    <nav v-if="store.lots" class="pagination" aria-label="Tax lot API pages">
      <button
        type="button"
        class="secondary-button"
        :disabled="isLoading || store.lots.offset === 0"
        @click="changePage(-1)"
      >
        Previous page
      </button>
      <span>Page {{ pageNumber }} of {{ pageCount }}</span>
      <button
        type="button"
        class="secondary-button"
        :disabled="isLoading || store.lots.offset + store.lots.limit >= store.lots.total"
        @click="changePage(1)"
      >
        Next page
      </button>
    </nav>

    <section class="review-summary" aria-labelledby="review-title">
      <h2 id="review-title">Marked for review · {{ reviewSelection.size }}</h2>
      <p>
        These local marks are a review aid only; they do not select, recommend, or execute a trade.
      </p>
      <ul v-if="reviewSelection.size > 0">
        <li v-for="[key, ticker, lotId] in reviewEntries" :key="key">
          {{ ticker }} · {{ lotId }}
          <button type="button" class="text-button" @click="removeReviewMark(key)">
            Remove mark
          </button>
        </li>
      </ul>
      <p v-else class="sub-value">No lots marked for review.</p>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import ApiActionError from '@/components/ApiActionError.vue';
import { useWorkspaceStore } from '@/stores/workspace-store';
import type { LotQuery } from '@/services/api';
import type { LotResponse } from '@/types/api';

const store = useWorkspaceStore();
const search = ref('');
const termFilter = ref(store.lotFilters.term ?? '');
const fractionalFilter = ref(
  store.lotFilters.fractional === undefined || store.lotFilters.fractional === null
    ? ''
    : String(store.lotFilters.fractional),
);
const pageLimit = ref(store.lotFilters.limit ?? 100);
const sortKey = ref<'ticker' | 'acquired_date' | 'broker_lot_id'>('ticker');
const sortDirection = ref<'asc' | 'desc'>('asc');
const reviewSelection = ref(new Map<string, { ticker: string; lotId: string }>());
const isLoading = computed(() => store.actionState.loadLots.pending);
const pageNumber = computed(() => {
  const page = store.lots;
  return page ? Math.floor(page.offset / page.limit) + 1 : 1;
});
const pageCount = computed(() => {
  const page = store.lots;
  return page ? Math.max(1, Math.ceil(page.total / page.limit)) : 1;
});
const filteredLots = computed(() => {
  const needle = search.value.trim().toLocaleLowerCase();
  const rows = store.lots?.items ?? [];
  const filtered = needle
    ? rows.filter((lot) =>
        `${lot.ticker} ${lot.broker_lot_id}`.toLocaleLowerCase().includes(needle),
      )
    : rows;
  const direction = sortDirection.value === 'asc' ? 1 : -1;
  return [...filtered].sort((left, right) => {
    const a = left[sortKey.value];
    const b = right[sortKey.value];
    return direction * a.localeCompare(b);
  });
});
const groupedLots = computed(() => {
  const groups = new Map<string, LotResponse[]>();
  for (const lot of filteredLots.value) {
    const rows = groups.get(lot.ticker) ?? [];
    rows.push(lot);
    groups.set(lot.ticker, rows);
  }
  return [...groups.entries()].map(([ticker, lots]) => ({ ticker, lots }));
});
const reviewEntries = computed(() =>
  [...reviewSelection.value.entries()].map(
    ([key, value]) => [key, value.ticker, value.lotId] as const,
  ),
);

function displayUsd(value: string | null): string {
  return value === null ? 'Unavailable' : `${value} USD`;
}

function displayPercent(value: string | null): string {
  return value === null ? 'Unavailable' : `${value}%`;
}

function hasCleanupFlag(lot: LotResponse): boolean {
  return (
    lot.small_lot_cleanup_candidate ||
    lot.position_cleanup_candidate ||
    lot.fractional_cleanup_unsupported
  );
}

function lotReviewKey(lot: LotResponse): string {
  return `${lot.ticker}:${lot.broker_lot_id}`;
}

function changeReviewSelection(lot: LotResponse, event: Event): void {
  if (!(event.target instanceof HTMLInputElement)) return;
  const next = new Map(reviewSelection.value);
  const key = lotReviewKey(lot);
  if (event.target.checked) next.set(key, { ticker: lot.ticker, lotId: lot.broker_lot_id });
  else next.delete(key);
  reviewSelection.value = next;
}

function removeReviewMark(key: string): void {
  const next = new Map(reviewSelection.value);
  next.delete(key);
  reviewSelection.value = next;
}

function currentFilters(offset: number): LotQuery {
  return {
    ...(termFilter.value ? { term: termFilter.value } : {}),
    ...(fractionalFilter.value === '' ? {} : { fractional: fractionalFilter.value === 'true' }),
    offset,
    limit: pageLimit.value,
  };
}

async function loadLots(offset: number): Promise<void> {
  try {
    await store.loadLots(currentFilters(offset));
  } catch {
    // The shared store retains the structured API error for the page.
  }
}

function applyFilters(): void {
  void loadLots(0);
}

function refreshLots(): void {
  void loadLots(store.lots?.offset ?? 0);
}

function changePage(direction: -1 | 1): void {
  const page = store.lots;
  if (!page) return;
  const nextOffset = Math.max(0, page.offset + direction * page.limit);
  void loadLots(nextOffset);
}

function toggleSortDirection(): void {
  sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc';
}

onMounted(() => {
  void loadLots(store.lotFilters.offset ?? 0);
});
</script>

<style scoped>
.workspace-page {
  display: grid;
  gap: 1rem;
  max-width: 1800px;
  margin: 0 auto;
  padding: clamp(1rem, 2.5vw, 2rem);
}
.page-header,
.security-heading,
.results-heading,
.sort-control,
.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.8rem;
}
.page-header {
  align-items: flex-start;
}
h1,
h2,
p {
  margin-top: 0;
}
.page-header h1 {
  margin-bottom: 0;
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
.page-subtitle {
  max-width: 52rem;
  margin: 0.4rem 0 0;
  color: #637b8a;
  font-size: 0.82rem;
  line-height: 1.5;
}
.demo-notice {
  margin: 0;
  padding: 0.8rem 1rem;
  border: 1px solid #f2dcad;
  border-radius: 0.65rem;
  background: #fff7e8;
  color: #765016;
  font-size: 0.82rem;
  line-height: 1.5;
}
.filter-panel,
.review-summary,
.security-card,
.empty-state {
  padding: 1rem;
  border: 1px solid #dce6eb;
  border-radius: 0.8rem;
  background: #fff;
  box-shadow: 0 4px 20px rgb(18 55 77 / 4.5%);
}
.filter-panel {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 0.75rem;
}
.filter-panel label,
.sort-control {
  display: grid;
  gap: 0.3rem;
  color: #466779;
  font-size: 0.75rem;
  font-weight: 700;
}
input,
select,
button {
  min-height: 2.4rem;
  border: 1px solid #b8c9d2;
  border-radius: 0.45rem;
  background: #fff;
  color: #203f52;
  font: inherit;
}
input,
select {
  padding: 0.4rem 0.55rem;
}
.filter-panel input[type='search'] {
  min-width: 15rem;
}
button {
  padding: 0.45rem 0.8rem;
  cursor: pointer;
  font-size: 0.76rem;
  font-weight: 750;
}
button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
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
  min-height: auto;
  margin-left: 0.5rem;
  padding: 0.15rem 0.35rem;
  border: 0;
  color: #087f7d;
  text-decoration: underline;
}
.results-heading {
  flex-wrap: wrap;
  color: #526c7c;
  font-size: 0.76rem;
}
.results-heading p {
  margin: 0;
}
.sort-control {
  display: flex;
  align-items: center;
}
.security-groups {
  display: grid;
  gap: 0.8rem;
}
.security-card {
  min-width: 0;
  padding: 0;
  overflow: hidden;
}
.security-heading {
  padding: 0.85rem 1rem;
  border-bottom: 1px solid #eaf0f3;
}
.security-heading h2 {
  margin: 0;
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
  padding: 0.65rem 0.7rem;
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
  gap: 0.25rem;
  white-space: nowrap;
}
.review-toggle input {
  min-height: auto;
}
.sub-value {
  display: block;
  margin-top: 0.25rem;
  color: #718792;
  font-size: 0.67rem;
  line-height: 1.4;
}
.flag-list {
  display: grid;
  gap: 0.2rem;
  margin: 0;
  padding-left: 1rem;
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
  margin-bottom: 0.4rem;
  color: #10263d;
  font-size: 1rem;
}
.empty-state p,
.review-summary p {
  margin-bottom: 0.7rem;
}
.pagination {
  justify-content: center;
  color: #526c7c;
  font-size: 0.78rem;
}
.review-summary ul {
  margin: 0;
  padding-left: 1.2rem;
  color: #29475a;
  font-size: 0.78rem;
}
.review-summary li + li {
  margin-top: 0.35rem;
}
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
  .page-header,
  .results-heading,
  .pagination {
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
  .pagination {
    text-align: center;
  }
}
</style>
