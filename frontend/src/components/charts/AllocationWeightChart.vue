<template>
  <div v-if="chartRows.length" class="allocation-comparison-chart">
    <Chart
      :definition="definition"
      aria-label="Current, proposed basket, and policy target allocation weights by sleeve"
      aria-description="The exact API-reported percentage strings are listed in the accessible allocation table."
      :height="chartHeight"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { barX, defineChart, group } from '@tanstack/charts';
import { Chart } from '@tanstack/charts/vue';
import { colorLegend } from '@tanstack/charts/legend';
import { scaleBand } from '@tanstack/charts/scales/band';
import { scaleLinear } from '@tanstack/charts/scales/linear';
import type { AllocationResponse } from '@/types/api';

type AllocationSeries = 'Current' | 'Proposed basket' | 'Policy target';
type AllocationChartRow = {
  sleeveKey: string;
  series: AllocationSeries;
  weightPct: number;
};

const props = defineProps<{
  allocation: AllocationResponse;
  labels: Record<string, string>;
  sleeveKeys: string[];
}>();

const series = computed(() => [
  { label: 'Current' as const, weights: props.allocation.current?.sleeve_weights_pct },
  { label: 'Proposed basket' as const, weights: props.allocation.proposed?.sleeve_weights_pct },
  { label: 'Policy target' as const, weights: props.allocation.target?.sleeve_weights_pct },
]);

const chartRows = computed<AllocationChartRow[]>(() => {
  const rows: AllocationChartRow[] = [];
  for (const sleeveKey of props.sleeveKeys) {
    for (const entry of series.value) {
      const rawWeight = entry.weights?.[sleeveKey];
      if (rawWeight == null || !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(rawWeight)) {
        continue;
      }
      const weightPct = Number(rawWeight);
      if (!Number.isFinite(weightPct)) continue;
      rows.push({ sleeveKey, series: entry.label, weightPct });
    }
  }
  return rows;
});

const chartHeight = computed(() => Math.max(220, props.sleeveKeys.length * 42 + 84));

const definition = computed(() =>
  defineChart({
    marks: [
      barX(chartRows.value, {
        x: 'weightPct',
        y: 'sleeveKey',
        z: 'series',
        color: 'series',
        layout: group(),
        inset: 2,
      }),
    ],
    scales: {
      x: {
        scale: scaleLinear,
        nice: true,
        grid: true,
        axis: { ticks: { format: (value) => `${value}%` } },
      },
      y: {
        scale: () => scaleBand<string>().padding(0.18),
        axis: { ticks: { format: (value) => props.labels[value] ?? value } },
      },
    },
    color: {
      domain: series.value.map((entry) => entry.label),
      legend: colorLegend({ placement: 'bottom' }),
    },
  }),
);
</script>

<style scoped>
.allocation-comparison-chart {
  --ts-chart-1: var(--chart-1);
  --ts-chart-2: var(--chart-2);
  --ts-chart-3: var(--chart-3);
}
</style>
