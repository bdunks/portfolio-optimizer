<template>
  <section class="allocation-panel" aria-labelledby="allocation-title">
    <header>
      <h2 id="allocation-title">Portfolio Allocation</h2>
      <p>API-reported sleeve weights as percentages of the whole portfolio.</p>
    </header>
    <p v-if="showNoCurrentBasket" class="comparison-note" role="status">
      No current proposed basket from a matching optimizer run. We show only allocation values
      reported by the portfolio API.
    </p>

    <p v-if="!allocation" class="empty-state">
      Allocation data is unavailable from the portfolio API.
    </p>
    <div v-else-if="sleeveKeys.length" class="table-wrap">
      <table>
        <caption class="visually-hidden">
          Current, proposed basket, and policy target allocation weights
        </caption>
        <thead>
          <tr>
            <th scope="col">Sleeve</th>
            <th scope="col">Current</th>
            <th scope="col">Proposed basket</th>
            <th scope="col">Policy target</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="sleeveKey in sleeveKeys" :key="sleeveKey">
            <th scope="row">{{ labels[sleeveKey] ?? sleeveKey }}</th>
            <td>{{ displayPercent(allocation.current?.sleeve_weights_pct[sleeveKey]) }}</td>
            <td>{{ displayPercent(allocation.proposed?.sleeve_weights_pct[sleeveKey]) }}</td>
            <td>{{ displayPercent(allocation.target?.sleeve_weights_pct[sleeveKey]) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="empty-state">No allocation weights were returned.</p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { AllocationResponse } from '@/types/api';

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

function displayPercent(value: string | null | undefined): string {
  return value == null || value === '' ? 'Unavailable' : `${value}%`;
}
</script>

<style scoped>
.allocation-panel {
  display: grid;
  gap: 0.8rem;
}

.allocation-panel h2 {
  margin: 0;
  color: #10263d;
  font-size: 1.1rem;
}

.allocation-panel header p {
  margin: 0.3rem 0 0;
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
  padding: 0.65rem 0.75rem;
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
  margin: 0;
  border-left: 3px solid #d19536;
  background: #fff7e9;
  color: #765016;
  padding: 0.75rem 0.9rem;
  line-height: 1.5;
  font-size: 0.78rem;
}

.empty-state {
  color: #718795;
  margin: 0;
  font-size: 0.82rem;
}

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
