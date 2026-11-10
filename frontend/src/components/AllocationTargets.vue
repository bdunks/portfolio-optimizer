<template>
  <section class="allocation-panel column no-wrap q-gutter-y-md" aria-labelledby="allocation-title">
    <header>
      <h2 class="q-ma-none text-h6" id="allocation-title">Portfolio Allocation</h2>
      <p class="q-mt-xs q-mb-none q-mx-none text-body2">
        API-reported sleeve weights as percentages of the whole portfolio.
      </p>
    </header>

    <q-banner
      v-if="showNoCurrentBasket"
      class="q-my-sm rounded bg-amber-1 text-brown-10"
      role="status"
    >
      No current proposed basket from a matching optimizer run. We show only allocation values
      reported by the portfolio API.
    </q-banner>

    <p v-if="!allocation" class="empty-state q-mr-none q-mb-none q-ml-none">
      Allocation data is unavailable from the portfolio API.
    </p>
    <WorkspaceTableFrame v-else-if="sleeveKeys.length" label="Portfolio allocation weights">
      <q-markup-table class="allocation-table" wrap-cells>
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
            <td>
              {{ formatPercent(allocation.current?.sleeve_weights_pct[sleeveKey]) }}
            </td>
            <td>
              {{ formatPercent(allocation.proposed?.sleeve_weights_pct[sleeveKey]) }}
            </td>
            <td>
              {{ formatPercent(allocation.target?.sleeve_weights_pct[sleeveKey]) }}
            </td>
          </tr>
        </tbody>
      </q-markup-table>
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
.allocation-table :deep(tbody td) {
  font-variant-numeric: tabular-nums;
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
