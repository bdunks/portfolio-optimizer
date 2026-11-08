<template>
  <section class="workspace-page" aria-labelledby="wash-title">
    <header class="page-header">
      <div>
        <p class="eyebrow">Managed-account restrictions</p>
        <h1 id="wash-title">Wash Sales</h1>
        <p class="page-subtitle">
          Transaction history and purchase restrictions returned by the local wash-sales API. This
          page does not perform or imply wash-sale validation.
        </p>
      </div>
      <button type="button" class="primary-button" :disabled="isLoading" @click="refresh">
        {{ isLoading ? 'Loading…' : 'Refresh wash data' }}
      </button>
    </header>

    <p class="demo-notice" role="status">
      <strong>DEMO ONLY.</strong> Returned records are not live E*TRADE validation; no broker
      connection, OAuth, preview, or trade submission is available.
    </p>

    <ApiActionError
      :error="store.actionState.loadWashSales.error"
      title="Wash-sale data could not be loaded"
    />

    <form class="filter-panel" @submit.prevent>
      <label>
        <span>Filter records</span>
        <input v-model="search" type="search" placeholder="Ticker, source, trigger, or ID" />
      </label>
      <label>
        <span>Transaction kind</span>
        <select v-model="transactionKind">
          <option value="">All transaction kinds</option>
          <option value="BUY">BUY</option>
          <option value="SELL">SELL</option>
          <option value="DIVIDEND">DIVIDEND</option>
          <option value="OTHER">OTHER</option>
        </select>
      </label>
    </form>

    <p
      v-if="store.actionState.loadWashSales.pending && !washSales"
      class="state-message"
      role="status"
    >
      Loading wash-sale history and restrictions from the local API…
    </p>
    <section v-else-if="!washSales" class="empty-state" aria-live="polite">
      <h2>No wash-sale data loaded</h2>
      <p>
        Retry to request the current API response. No history or restrictions have been inferred.
      </p>
      <button type="button" class="secondary-button" :disabled="isLoading" @click="refresh">
        Retry loading wash data
      </button>
    </section>
    <template v-else>
      <section class="coverage-card" aria-labelledby="coverage-title">
        <div class="section-heading">
          <div>
            <h2 id="coverage-title">API coverage</h2>
            <p class="section-subtitle">Source: {{ washSales.source }}</p>
          </div>
          <span class="demo-badge">{{ washSales.demo ? 'DEMO' : 'API' }}</span>
        </div>
        <dl class="coverage-grid">
          <div>
            <dt>Transaction history rows</dt>
            <dd>{{ washSales.history.length }}</dd>
          </div>
          <div>
            <dt>Acquisition rows</dt>
            <dd>{{ washSales.acquisitions.length }}</dd>
          </div>
          <div>
            <dt>Current restrictions</dt>
            <dd>{{ washSales.current_restrictions.length }}</dd>
          </div>
          <div>
            <dt>Proposed restrictions</dt>
            <dd>{{ washSales.proposed_restrictions.length }}</dd>
          </div>
        </dl>
        <p class="coverage-note">
          Conflicting-transaction links and affected tax-lot IDs are not included in this API
          response; they are not inferred here. Counts are returned-record counts; the endpoint
          provides no pagination or total-coverage indicator.
        </p>
        <ul
          v-if="washSales.warnings.length"
          class="warning-list"
          aria-label="API coverage warnings"
        >
          <li v-for="warning in washSales.warnings" :key="warning">{{ warning }}</li>
        </ul>
        <p v-else class="coverage-note">The API returned no coverage warnings.</p>
      </section>

      <section class="data-card" aria-labelledby="history-title">
        <div class="section-heading">
          <div>
            <h2 id="history-title">Acquisition and transaction history</h2>
            <p class="section-subtitle">
              Acquisition rows include the API-provided lookback-window end date; transaction keys
              and quantities are shown as returned.
            </p>
          </div>
        </div>
        <div v-if="filteredAcquisitions.length" class="table-scroll">
          <table>
            <caption class="sr-only">
              Acquisition history with API-provided lookback dates
            </caption>
            <thead>
              <tr>
                <th scope="col">Ticker</th>
                <th scope="col">Kind</th>
                <th scope="col">Trade date / time</th>
                <th scope="col">Shares</th>
                <th scope="col">Lookback window ends</th>
                <th scope="col">Transaction key</th>
                <th scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in filteredAcquisitions" :key="row.broker_transaction_key">
                <th scope="row">{{ row.ticker ?? 'Ticker unavailable' }}</th>
                <td>{{ row.transaction_kind }}</td>
                <td>{{ row.trade_date }} · {{ row.transaction_time }}</td>
                <td>{{ row.shares }}</td>
                <td>{{ row.lookback_window_end_date }}</td>
                <td class="wrap-cell">{{ row.broker_transaction_key }}</td>
                <td>{{ row.source }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="empty-note">
          {{
            washSales.acquisitions.length
              ? 'No acquisition rows match these filters.'
              : 'The API returned no acquisition rows.'
          }}
        </p>

        <h3 class="subsection-title">All transaction history</h3>
        <div v-if="filteredHistory.length" class="table-scroll">
          <table>
            <caption class="sr-only">
              Managed-account transaction history returned by the API
            </caption>
            <thead>
              <tr>
                <th scope="col">Ticker</th>
                <th scope="col">Kind</th>
                <th scope="col">Acquisition?</th>
                <th scope="col">Trade date / time</th>
                <th scope="col">Shares</th>
                <th scope="col">Transaction key</th>
                <th scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in filteredHistory" :key="row.broker_transaction_key">
                <th scope="row">{{ row.ticker ?? 'Ticker unavailable' }}</th>
                <td>{{ row.transaction_kind }}</td>
                <td>{{ row.is_acquisition ? 'Yes' : 'No' }}</td>
                <td>{{ row.trade_date }} · {{ row.transaction_time }}</td>
                <td>{{ row.shares }}</td>
                <td class="wrap-cell">{{ row.broker_transaction_key }}</td>
                <td>{{ row.source }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="empty-note">
          {{
            washSales.history.length
              ? 'No transaction rows match these filters.'
              : 'The API returned no transaction-history rows.'
          }}
        </p>
      </section>

      <section class="data-card" aria-labelledby="restrictions-title">
        <div class="section-heading">
          <div>
            <h2 id="restrictions-title">Purchase restrictions</h2>
            <p class="section-subtitle">
              Current and proposed restrictions are separate API lists. Proposed records are not
              represented as executed sales.
            </p>
          </div>
        </div>
        <div v-if="filteredRestrictions.length" class="table-scroll">
          <table>
            <caption class="sr-only">
              Current and proposed purchase restrictions
            </caption>
            <thead>
              <tr>
                <th scope="col">Status</th>
                <th scope="col">Ticker</th>
                <th scope="col">Trigger</th>
                <th scope="col">Loss-sale date</th>
                <th scope="col">Next eligible purchase</th>
                <th scope="col">Validation</th>
                <th scope="col">Run / source</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in filteredRestrictions" :key="restrictionKey(row)">
                <th scope="row">{{ row.statusLabel }}</th>
                <td>{{ row.ticker }}</td>
                <td>{{ row.trigger }}</td>
                <td>{{ row.loss_sale_date }}</td>
                <td>{{ row.next_eligible_purchase_date }}</td>
                <td>{{ row.validation }}</td>
                <td class="wrap-cell">
                  {{ row.run_id ?? 'No run ID returned' }}<br />{{ row.source }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="empty-note">
          {{
            allRestrictions.length
              ? 'No restrictions match these filters.'
              : 'The API returned no current or proposed restrictions.'
          }}
        </p>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import ApiActionError from '@/components/ApiActionError.vue';
import { useWorkspaceStore } from '@/stores/workspace-store';
import type { WashRestrictionResponse, WashTransactionResponse } from '@/types/api';

const store = useWorkspaceStore();
const search = ref('');
const transactionKind = ref('');
const washSales = computed(() => store.washSales);
const isLoading = computed(() => store.actionState.loadWashSales.pending);
const needle = computed(() => search.value.trim().toLocaleLowerCase());
const filteredHistory = computed(() =>
  (washSales.value?.history ?? []).filter(
    (row) => kindMatches(row) && matchesText([row.ticker, row.broker_transaction_key, row.source]),
  ),
);
const filteredAcquisitions = computed(() =>
  (washSales.value?.acquisitions ?? []).filter(
    (row) => kindMatches(row) && matchesText([row.ticker, row.broker_transaction_key, row.source]),
  ),
);
const allRestrictions = computed(() => [
  ...(washSales.value?.current_restrictions ?? []).map((row) => ({
    ...row,
    statusLabel: 'Current',
  })),
  ...(washSales.value?.proposed_restrictions ?? []).map((row) => ({
    ...row,
    statusLabel: 'Proposed',
  })),
]);
const filteredRestrictions = computed(() =>
  allRestrictions.value.filter((row) =>
    matchesText([row.ticker, row.trigger, row.source, row.validation, row.run_id]),
  ),
);

function kindMatches(row: WashTransactionResponse): boolean {
  return transactionKind.value === '' || row.transaction_kind === transactionKind.value;
}

function matchesText(values: Array<string | null | undefined>): boolean {
  if (!needle.value) return true;
  return values.some((value) => value?.toLocaleLowerCase().includes(needle.value));
}

function restrictionKey(row: WashRestrictionResponse): string {
  return `${row.run_id ?? 'current'}:${row.ticker}:${row.loss_sale_date}:${row.trigger}`;
}

async function refresh(): Promise<void> {
  try {
    await store.loadWashSales();
  } catch {
    // The shared store retains the structured API error for the page.
  }
}

onMounted(() => {
  void refresh();
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
.section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
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
  max-width: 52rem;
  margin: 0.4rem 0 0;
  color: #637b8a;
  font-size: 0.82rem;
  line-height: 1.5;
}
.section-subtitle {
  font-size: 0.76rem;
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
.coverage-card,
.data-card,
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
.filter-panel label {
  display: grid;
  min-width: min(19rem, 100%);
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
.secondary-button {
  border-color: #bfd0d8;
  background: #f7fafb;
}
.coverage-card,
.data-card {
  min-width: 0;
}
.section-heading {
  align-items: center;
  margin-bottom: 0.8rem;
}
.section-heading h2,
.empty-state h2 {
  margin: 0;
  color: #10263d;
  font-size: 1.05rem;
}
.demo-badge {
  padding: 0.25rem 0.55rem;
  border-radius: 2rem;
  background: #fff1d2;
  color: #77520d;
  font-size: 0.68rem;
  font-weight: 800;
}
.coverage-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.7rem;
  margin: 0;
}
.coverage-grid > div {
  padding: 0.65rem;
  border: 1px solid #eaf0f3;
  border-radius: 0.55rem;
}
.coverage-grid dt {
  color: #647c8b;
  font-size: 0.7rem;
}
.coverage-grid dd {
  margin: 0.3rem 0 0;
  color: #087f7d;
  font-size: 1rem;
  font-weight: 800;
}
.coverage-note,
.warning-list,
.empty-note,
.state-message {
  color: #657d8b;
  font-size: 0.78rem;
  line-height: 1.5;
}
.coverage-note {
  margin: 0.7rem 0 0;
}
.warning-list {
  margin: 0.7rem 0 0;
  padding-left: 1.2rem;
  color: #765016;
}
.table-scroll {
  overflow-x: auto;
}
table {
  width: 100%;
  min-width: 940px;
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
.wrap-cell {
  max-width: 14rem;
  overflow-wrap: anywhere;
}
.subsection-title {
  margin: 1rem 0 0.5rem;
  color: #526c7c;
  font-size: 0.8rem;
  text-transform: uppercase;
}
.empty-note {
  margin: 0.7rem 0 0;
}
.empty-state p {
  margin: 0.6rem 0 0.8rem;
  color: #657d8b;
  font-size: 0.8rem;
  line-height: 1.5;
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
@media (max-width: 850px) {
  .page-header,
  .section-heading {
    align-items: stretch;
    flex-direction: column;
  }
  .coverage-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .filter-panel label {
    width: 100%;
  }
}
</style>
