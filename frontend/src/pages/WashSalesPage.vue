<template>
  <section class="workspace-page q-my-none q-mx-auto q-pa-md" aria-labelledby="wash-title">
    <WorkspacePageHeader
      eyebrow="Managed-account restrictions"
      title="Wash Sales"
      title-id="wash-title"
      subtitle="Transaction history and purchase restrictions returned by the local wash-sales API. This page does not perform or imply wash-sale validation."
    >
      <template #actions>
        <q-btn
          unelevated
          no-caps
          type="button"
          class="primary-button"
          :disable="isLoading"
          @click="refresh"
        >
          {{ isLoading ? 'Loading…' : 'Refresh wash data' }}
        </q-btn>
      </template>
    </WorkspacePageHeader>

    <WorkspaceCapabilityNotice label="DEMO ONLY.">
      Returned records are not live E*TRADE validation; no broker connection, OAuth, preview, or
      trade submission is available.
    </WorkspaceCapabilityNotice>

    <ApiActionError
      :error="store.actionState.loadWashSales.error"
      title="Wash-sale data could not be loaded"
    />

    <ResourceFreshnessNotice :resources="['washSales']" />

    <WorkspaceFilterPanel
      label="Wash-sale filters"
      class="filter-panel row items-end q-gutter-sm q-pa-md"
    >
      <label class="column no-wrap q-gutter-y-xs">
        <span>Filter records</span>
        <q-input
          outlined
          dense
          hide-bottom-space
          v-model="search"
          type="search"
          placeholder="Ticker, source, trigger, or ID"
        />
      </label>
      <label class="column no-wrap q-gutter-y-xs">
        <span>Transaction kind</span>
        <q-select
          v-model="transactionKind"
          :options="[
            { label: 'All transaction kinds', value: '' },
            { label: 'BUY', value: 'BUY' },
            { label: 'SELL', value: 'SELL' },
            { label: 'DIVIDEND', value: 'DIVIDEND' },
            { label: 'OTHER', value: 'OTHER' },
          ]"
          emit-value
          map-options
          outlined
          dense
          hide-bottom-space
          aria-label="Transaction kind"
        />
      </label>
    </WorkspaceFilterPanel>

    <p
      v-if="store.actionState.loadWashSales.pending && !washSales"
      class="state-message"
      role="status"
    >
      Loading wash-sale history and restrictions from the local API…
    </p>
    <WorkspaceEmptyState v-else-if="!washSales" title="No wash-sale data loaded">
      Retry to request the current API response. No history or restrictions have been inferred.
      <template #action>
        <q-btn
          unelevated
          no-caps
          type="button"
          class="secondary-button"
          :disable="isLoading"
          @click="refresh"
        >
          Retry loading wash data
        </q-btn>
      </template>
    </WorkspaceEmptyState>
    <template v-else>
      <section class="coverage-card q-pa-md" aria-labelledby="coverage-title">
        <div class="section-heading row justify-between q-gutter-md items-center q-mb-md">
          <div>
            <h2 class="q-ma-none" id="coverage-title">API coverage</h2>
            <p class="section-subtitle q-mt-sm q-mb-none q-mx-none">
              Source: {{ washSales.source }}
            </p>
          </div>
          <span class="demo-badge q-py-xs q-px-sm">{{ washSales.demo ? 'DEMO' : 'API' }}</span>
        </div>
        <dl class="coverage-grid q-ma-none">
          <div class="q-pa-sm">
            <dt>Transaction history rows</dt>
            <dd class="q-mt-xs q-mb-none q-mx-none">{{ washSales.history.length }}</dd>
          </div>
          <div class="q-pa-sm">
            <dt>Acquisition rows</dt>
            <dd class="q-mt-xs q-mb-none q-mx-none">{{ washSales.acquisitions.length }}</dd>
          </div>
          <div class="q-pa-sm">
            <dt>Current restrictions</dt>
            <dd class="q-mt-xs q-mb-none q-mx-none">{{ washSales.current_restrictions.length }}</dd>
          </div>
          <div class="q-pa-sm">
            <dt>Proposed restrictions</dt>
            <dd class="q-mt-xs q-mb-none q-mx-none">
              {{ washSales.proposed_restrictions.length }}
            </dd>
          </div>
        </dl>
        <p class="coverage-note q-mt-sm q-mb-none q-mx-none">
          Conflicting-transaction links and affected tax-lot IDs are not included in this API
          response; they are not inferred here. Counts are returned-record counts; the endpoint
          provides no pagination or total-coverage indicator.
        </p>
        <ul
          v-if="washSales.warnings.length"
          class="warning-list q-mt-sm q-mb-none q-mx-none q-pl-md"
          aria-label="API coverage warnings"
        >
          <li v-for="warning in washSales.warnings" :key="warning">{{ warning }}</li>
        </ul>
        <p v-else class="coverage-note q-mt-sm q-mb-none q-mx-none">
          The API returned no coverage warnings.
        </p>
      </section>

      <section class="data-card q-pa-md" aria-labelledby="history-title">
        <div class="section-heading row justify-between q-gutter-md items-center q-mb-md">
          <div>
            <h2 class="q-ma-none" id="history-title">Acquisition and transaction history</h2>
            <p class="section-subtitle q-mt-sm q-mb-none q-mx-none">
              Acquisition rows include the API-provided lookback-window end date; transaction keys
              and quantities are shown as returned.
            </p>
          </div>
        </div>
        <WorkspaceTableFrame
          v-if="filteredAcquisitions.length"
          class="table-scroll"
          label="Wash-sale acquisition rows"
        >
          <table>
            <caption class="sr-only">
              Acquisition history with API-provided lookback dates
            </caption>
            <thead>
              <tr>
                <th class="q-pa-sm" scope="col">Ticker</th>
                <th class="q-pa-sm" scope="col">Kind</th>
                <th class="q-pa-sm" scope="col">Trade date / time</th>
                <th class="q-pa-sm" scope="col">Shares</th>
                <th class="q-pa-sm" scope="col">Lookback window ends</th>
                <th class="q-pa-sm" scope="col">Transaction key</th>
                <th class="q-pa-sm" scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in filteredAcquisitions" :key="row.broker_transaction_key">
                <th class="q-pa-sm" scope="row">{{ row.ticker ?? 'Ticker unavailable' }}</th>
                <td class="q-pa-sm">{{ row.transaction_kind }}</td>
                <td class="q-pa-sm">{{ row.trade_date }} · {{ row.transaction_time }}</td>
                <td class="q-pa-sm">{{ row.shares }}</td>
                <td class="q-pa-sm">{{ row.lookback_window_end_date }}</td>
                <td class="wrap-cell q-pa-sm">{{ row.broker_transaction_key }}</td>
                <td class="q-pa-sm">{{ row.source }}</td>
              </tr>
            </tbody>
          </table>
        </WorkspaceTableFrame>
        <p v-else class="empty-note q-mt-sm q-mb-none q-mx-none">
          {{
            washSales.acquisitions.length
              ? 'No acquisition rows match these filters.'
              : 'The API returned no acquisition rows.'
          }}
        </p>

        <h3 class="subsection-title q-mt-md q-mb-sm q-mx-none">All transaction history</h3>
        <WorkspaceTableFrame
          v-if="filteredHistory.length"
          class="table-scroll"
          label="Wash-sale transaction history"
        >
          <table>
            <caption class="sr-only">
              Managed-account transaction history returned by the API
            </caption>
            <thead>
              <tr>
                <th class="q-pa-sm" scope="col">Ticker</th>
                <th class="q-pa-sm" scope="col">Kind</th>
                <th class="q-pa-sm" scope="col">Acquisition?</th>
                <th class="q-pa-sm" scope="col">Trade date / time</th>
                <th class="q-pa-sm" scope="col">Shares</th>
                <th class="q-pa-sm" scope="col">Transaction key</th>
                <th class="q-pa-sm" scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in filteredHistory" :key="row.broker_transaction_key">
                <th class="q-pa-sm" scope="row">{{ row.ticker ?? 'Ticker unavailable' }}</th>
                <td class="q-pa-sm">{{ row.transaction_kind }}</td>
                <td class="q-pa-sm">{{ row.is_acquisition ? 'Yes' : 'No' }}</td>
                <td class="q-pa-sm">{{ row.trade_date }} · {{ row.transaction_time }}</td>
                <td class="q-pa-sm">{{ row.shares }}</td>
                <td class="wrap-cell q-pa-sm">{{ row.broker_transaction_key }}</td>
                <td class="q-pa-sm">{{ row.source }}</td>
              </tr>
            </tbody>
          </table>
        </WorkspaceTableFrame>
        <p v-else class="empty-note q-mt-sm q-mb-none q-mx-none">
          {{
            washSales.history.length
              ? 'No transaction rows match these filters.'
              : 'The API returned no transaction-history rows.'
          }}
        </p>
      </section>

      <section class="data-card q-pa-md" aria-labelledby="restrictions-title">
        <div class="section-heading row justify-between q-gutter-md items-center q-mb-md">
          <div>
            <h2 class="q-ma-none" id="restrictions-title">Purchase restrictions</h2>
            <p class="section-subtitle q-mt-sm q-mb-none q-mx-none">
              Current and proposed restrictions are separate API lists. Proposed records are not
              represented as executed sales.
            </p>
          </div>
        </div>
        <WorkspaceTableFrame
          v-if="filteredRestrictions.length"
          class="table-scroll"
          label="Wash-sale purchase restrictions"
        >
          <table>
            <caption class="sr-only">
              Current and proposed purchase restrictions
            </caption>
            <thead>
              <tr>
                <th class="q-pa-sm" scope="col">Status</th>
                <th class="q-pa-sm" scope="col">Ticker</th>
                <th class="q-pa-sm" scope="col">Trigger</th>
                <th class="q-pa-sm" scope="col">Loss-sale date</th>
                <th class="q-pa-sm" scope="col">Next eligible purchase</th>
                <th class="q-pa-sm" scope="col">Validation</th>
                <th class="q-pa-sm" scope="col">Run / source</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in filteredRestrictions" :key="restrictionKey(row)">
                <th class="q-pa-sm" scope="row">{{ row.statusLabel }}</th>
                <td class="q-pa-sm">{{ row.ticker }}</td>
                <td class="q-pa-sm">{{ row.trigger }}</td>
                <td class="q-pa-sm">{{ row.loss_sale_date }}</td>
                <td class="q-pa-sm">{{ row.next_eligible_purchase_date }}</td>
                <td class="q-pa-sm">{{ row.validation }}</td>
                <td class="wrap-cell q-pa-sm">
                  {{ row.run_id ?? 'No run ID returned' }}<br />{{ row.source }}
                </td>
              </tr>
            </tbody>
          </table>
        </WorkspaceTableFrame>
        <p v-else class="empty-note q-mt-sm q-mb-none q-mx-none">
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
import WorkspacePageHeader from '@/components/WorkspacePageHeader.vue';
import WorkspaceCapabilityNotice from '@/components/WorkspaceCapabilityNotice.vue';
import WorkspaceEmptyState from '@/components/WorkspaceEmptyState.vue';
import WorkspaceFilterPanel from '@/components/WorkspaceFilterPanel.vue';
import WorkspaceTableFrame from '@/components/WorkspaceTableFrame.vue';

import ResourceFreshnessNotice from '@/components/ResourceFreshnessNotice.vue';
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
/* Grid gaps use Quasar's spacing scale; negative-margin gutters distort grid tracks. */
.filter-panel,
.coverage-card,
.data-card,
.empty-state {
  border: 1px solid #dce6eb;
  border-radius: 0.8rem;
  background: #fff;
  box-shadow: 0 4px 20px rgb(18 55 77 / 4.5%);
}

.filter-panel label {
  min-width: min(19rem, 100%);
  color: #466779;
  font-size: 0.75rem;
  font-weight: 700;
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

.section-heading h2,
.empty-state h2 {
  color: #10263d;
  font-size: 1.05rem;
}
.demo-badge {
  border-radius: 2rem;
  background: #fff1d2;
  color: #77520d;
  font-size: 0.68rem;
  font-weight: 800;
}
.coverage-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}
.coverage-grid > div {
  border: 1px solid #eaf0f3;
  border-radius: 0.55rem;
}
.coverage-grid dt {
  color: #647c8b;
  font-size: 0.7rem;
}
.coverage-grid dd {
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

.warning-list {
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
  color: #526c7c;
  font-size: 0.8rem;
  text-transform: uppercase;
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
@media (max-width: 850px) {
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
