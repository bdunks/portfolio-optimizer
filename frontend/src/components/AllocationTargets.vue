<template>
  <section
    class="allocation-panel workspace-foundation tw:flex tw:flex-col tw:gap-4"
    aria-labelledby="allocation-title"
  >
    <header class="tw:flex tw:flex-col tw:gap-1">
      <h2 class="tw:m-0 tw:text-lg tw:font-semibold tw:tracking-tight" id="allocation-title">
        Portfolio Allocation
      </h2>
      <p class="tw:m-0 tw:text-sm tw:text-muted-foreground">
        API-reported sleeve weights as percentages of the whole portfolio.
      </p>
    </header>

    <Alert v-if="showNoCurrentBasket" role="status" class="workspace-foundation">
      <AlertDescription>
        No current proposed basket from a matching optimizer run. We show only allocation values
        reported by the portfolio API.
      </AlertDescription>
    </Alert>

    <WorkspaceEmptyState
      v-if="!allocation"
      title="Allocation data is unavailable from the portfolio API."
    />
    <template v-else-if="sleeveKeys.length">
      <AllocationWeightChart :allocation="allocation" :labels="labels" :sleeve-keys="sleeveKeys" />
      <WorkspaceTableFrame v-if="sleeveKeys.length" label="Portfolio allocation weights">
        <Table class="allocation-table">
          <TableCaption class="tw:sr-only">
            Current, proposed basket, and policy target allocation weights
          </TableCaption>
          <TableHeader>
            <TableRow v-for="headerGroup in table.getHeaderGroups()" :key="headerGroup.id">
              <TableHead v-for="header in headerGroup.headers" :key="header.id" scope="col">
                <FlexRender v-if="!header.isPlaceholder" :header="header" />
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="row in tableRows" :key="row.id">
              <template v-for="cell in row.getAllCells()" :key="cell.id">
                <TableHead
                  v-if="cell.column.id === 'sleeve'"
                  scope="row"
                  class="tw:text-left tw:font-medium"
                >
                  <FlexRender :cell="cell" />
                </TableHead>
                <TableCell v-else class="tw:tabular-nums">
                  <FlexRender :cell="cell" />
                </TableCell>
              </template>
            </TableRow>
          </TableBody>
        </Table>
      </WorkspaceTableFrame>
    </template>
    <WorkspaceEmptyState v-else title="No allocation weights were returned." />
  </section>
</template>

<script setup lang="ts">
import { computed, shallowRef, watch } from 'vue';
import { FlexRender, tableFeatures, useTable } from '@tanstack/vue-table';
import type { ColumnDef } from '@tanstack/vue-table';
import type { AllocationResponse } from '@/types/api';
import { formatPercent } from '@/utils/display-values';
import AllocationWeightChart from '@/components/charts/AllocationWeightChart.vue';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import WorkspaceEmptyState from '@/components/WorkspaceEmptyState.vue';
import WorkspaceTableFrame from '@/components/WorkspaceTableFrame.vue';

const props = withDefaults(
  defineProps<{
    allocation: AllocationResponse | null;
    labels?: Record<string, string>;
    showNoCurrentBasket?: boolean;
  }>(),
  { labels: () => ({}), showNoCurrentBasket: false },
);

type AllocationRow = {
  sleeveKey: string;
  current: string | undefined;
  proposed: string | undefined;
  target: string | undefined;
};

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

const allocationFeatures = tableFeatures({});
const columns: Array<ColumnDef<typeof allocationFeatures, AllocationRow>> = [
  {
    id: 'sleeve',
    accessorKey: 'sleeveKey',
    header: 'Sleeve',
    cell: ({ row }) => labels.value[row.original.sleeveKey] ?? row.original.sleeveKey,
  },
  {
    id: 'current',
    accessorKey: 'current',
    header: 'Current',
    cell: ({ row }) => formatPercent(row.original.current),
  },
  {
    id: 'proposed',
    accessorKey: 'proposed',
    header: 'Proposed basket',
    cell: ({ row }) => formatPercent(row.original.proposed),
  },
  {
    id: 'target',
    accessorKey: 'target',
    header: 'Policy target',
    cell: ({ row }) => formatPercent(row.original.target),
  },
];

const allocationRows = computed<AllocationRow[]>(() =>
  sleeveKeys.value.map((sleeveKey) => ({
    sleeveKey,
    current: props.allocation?.current?.sleeve_weights_pct[sleeveKey],
    proposed: props.allocation?.proposed?.sleeve_weights_pct[sleeveKey],
    target: props.allocation?.target?.sleeve_weights_pct[sleeveKey],
  })),
);

const tableData = shallowRef(allocationRows.value);
const table = useTable({ features: allocationFeatures, columns, data: tableData });
watch(
  allocationRows,
  (rows) => {
    tableData.value = rows;
    table.setOptions((previous) => ({ ...previous, data: rows }));
  },
  { flush: 'sync' },
);
const tableRows = computed(() => (tableData.value.length === 0 ? [] : table.getRowModel().rows));
</script>

<style scoped>
#allocation-title {
  font-size: var(--tw-text-lg);
  line-height: var(--tw-text-lg--line-height);
  font-weight: var(--tw-font-weight-semibold);
  letter-spacing: var(--tw-tracking-tight);
}
</style>
