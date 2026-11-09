<template>
  <section class="allocation-panel column no-wrap q-gutter-y-md" aria-labelledby="allocation-title">
    <header>
      <h2 class="q-ma-none" id="allocation-title">Portfolio Allocation</h2>
      <p class="q-mt-xs q-mb-none q-mx-none">
        API-reported sleeve weights as percentages of the whole portfolio.
      </p>
    </header>
    <p
      v-if="showNoCurrentBasket"
      class="comparison-note q-mr-none q-mb-none q-ml-none q-py-sm q-px-md"
      role="status"
    >
      No current proposed basket from a matching optimizer run. We show only allocation values
      reported by the portfolio API.
    </p>

    <p v-if="!allocation" class="empty-state q-mr-none q-mb-none q-ml-none">
      Allocation data is unavailable from the portfolio API.
    </p>
    <WorkspaceTableFrame
      v-else-if="sleeveKeys.length"
      class="table-wrap"
      label="Portfolio allocation weights"
    >
      <table>
        <caption class="visually-hidden">
          Current, proposed basket, and policy target allocation weights
        </caption>
        <thead>
          <tr>
            <th class="q-pa-sm" scope="col">Sleeve</th>
            <th class="q-pa-sm" scope="col">Current</th>
            <th class="q-pa-sm" scope="col">Proposed basket</th>
            <th class="q-pa-sm" scope="col">Policy target</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="sleeveKey in sleeveKeys" :key="sleeveKey">
            <th class="q-pa-sm" scope="row">{{ labels[sleeveKey] ?? sleeveKey }}</th>
            <td class="q-pa-sm">
              {{ formatPercent(allocation.current?.sleeve_weights_pct[sleeveKey]) }}
            </td>
            <td class="q-pa-sm">
              {{ formatPercent(allocation.proposed?.sleeve_weights_pct[sleeveKey]) }}
            </td>
            <td class="q-pa-sm">
              {{ formatPercent(allocation.target?.sleeve_weights_pct[sleeveKey]) }}
            </td>
          </tr>
        </tbody>
      </table>
    </WorkspaceTableFrame>
    <p v-else class="empty-state q-mr-none q-mb-none q-ml-none">
      No allocation weights were returned.
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { AllocationResponse } from '@/types/api';
import { formatPercent } from '@/utils/display-values';
import WorkspaceTableFrame from '@/components/WorkspaceTableFrame.vue';

const props = withDefaults(
  defineProps<{
    allocation: AllocationResponse | null;
    labels?: Record<string, string>;
    showNoCurrentBasket?: boolean;
  }>(),
  { labels: () => ({}), showNoCurrentBasket: false },
);

const allocation = computed(() => props.allocation);
const labels = computed(() => props.labels);
const sleeveKeys = computed(() => {
  if (!props.allocation) return [];
  return [
    ...new Set([
      ...Object.keys(props.allocation.current?.sleeve_weights_pct ?? {}),
      ...Object.keys(props.allocation.proposed?.sleeve_weights_pct ?? {}),
      ...Object.keys(props.allocation.target?.sleeve_weights_pct ?? {}),
    ]),
  ];
});
</script>

<style scoped>
.allocation-panel h2 {
  color: #10263d;
  font-size: 1.1rem;
}

.allocation-panel header p {
  color: #61798a;
  font-size: 0.82rem;
}

.table-wrap {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}

th,
td {
  border-bottom: 1px solid #eaf0f3;
  font-size: 0.8rem;
}

thead th {
  background: #f3f8fa;
  color: #627b8b;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

tbody th {
  color: #29475a;
  font-weight: 650;
}

tbody td {
  color: #35586c;
  font-variant-numeric: tabular-nums;
}

.comparison-note {
  border-left: 3px solid #d19536;
  background: #fff7e9;
  color: #765016;
  line-height: 1.5;
  font-size: 0.78rem;
}

.empty-state {
  color: #718795;
  font-size: 0.82rem;
}

/* Keep content available to assistive technology without occupying layout space. */
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
