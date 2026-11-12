<script setup lang="ts">
import type {
  ColumnDef,
  ColumnFiltersState,
  PaginationState,
  Row,
  RowSelectionState,
  SortingState,
} from '@tanstack/vue-table';
import {
  columnFilteringFeature,
  FlexRender,
  globalFilteringFeature,
  rowPaginationFeature,
  rowSelectionFeature,
  rowSortingFeature,
  tableFeatures,
  useTable,
} from '@tanstack/vue-table';
import { computed } from 'vue';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Field, FieldLabel } from '@/components/ui/field';
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import BrokerLotIdentity from '@/components/BrokerLotIdentity.vue';
import type { LotResponse } from '@/types/api';
import type { LotQuery } from '@/services/api';
import { formatPercent, formatUsd } from '@/utils/display-values';

const props = defineProps<{
  ticker: string;
  lots: LotResponse[];
  requestedLotIds: ReadonlySet<string>;
  confirmedSellLotIds: ReadonlySet<string>;
  canChangeIntent: boolean;
  sourceGeneration: number | null;
  sortBy: NonNullable<LotQuery['sort_by']>;
  sortDirection: NonNullable<LotQuery['sort_direction']>;
  search: string;
  term: LotQuery['term'];
  fractional: LotQuery['fractional'];
  offset: number;
  limit: number;
  total: number;
}>();

const emit = defineEmits<{
  intentChange: [
    change: {
      brokerLotId: string;
      ticker: string;
      sourceGeneration: number | null;
      requested: boolean;
    },
  ];
}>();

const features = tableFeatures({
  columnFilteringFeature,
  globalFilteringFeature,
  rowPaginationFeature,
  rowSelectionFeature,
  rowSortingFeature,
});
type LotTableFeatures = typeof features;

const columns: Array<ColumnDef<LotTableFeatures, LotResponse>> = [
  { id: 'intent', header: 'Intent', cell: () => '' },
  {
    accessorKey: 'broker_lot_id',
    header: 'Broker lot ID',
    cell: ({ row }) => row.original.broker_lot_id,
  },
  {
    accessorKey: 'acquired_date',
    header: 'Acquired',
    cell: ({ row }) => row.original.acquired_date,
  },
  {
    id: 'shares',
    header: 'Remaining / available shares',
    cell: ({ row }) => row.original.remaining_shares,
  },
  {
    id: 'basis',
    header: 'Adjusted basis (unit / total)',
    cell: ({ row }) =>
      `${formatUsd(row.original.adjusted_unit_basis_usd)} / ${formatUsd(row.original.adjusted_total_basis_usd)}`,
  },
  {
    accessorKey: 'current_price_usd',
    header: 'Current price',
    cell: ({ row }) => formatUsd(row.original.current_price_usd),
  },
  {
    id: 'unrealized_pl',
    header: 'Unrealized P/L (USD / %)',
    cell: ({ row }) =>
      `${formatUsd(row.original.unrealized_pl_usd)} / ${formatPercent(row.original.unrealized_pl_pct)}`,
  },
  { accessorKey: 'term', header: 'Term', cell: ({ row }) => row.original.term },
  { id: 'sleeve', header: 'Sleeve', cell: ({ row }) => row.original.sleeve_key ?? 'Unassigned' },
  { id: 'flags', header: 'Quality and cleanup flags', cell: ({ row }) => row.original.source },
];

const rowSelection = computed<RowSelectionState>(() =>
  Object.fromEntries(
    props.lots
      .filter((lot) => props.requestedLotIds.has(lot.broker_lot_id))
      .map((lot) => [lot.broker_lot_id, true]),
  ),
);
const sorting = computed<SortingState>(() => [
  { id: props.sortBy, desc: props.sortDirection === 'desc' },
]);
const columnFilters = computed<ColumnFiltersState>(() => {
  const filters: ColumnFiltersState = [];
  if (props.term) filters.push({ id: 'term', value: props.term });
  if (props.fractional !== undefined && props.fractional !== null) {
    filters.push({ id: 'fractional_cleanup_unsupported', value: props.fractional });
  }
  return filters;
});
const pagination = computed<PaginationState>(() => ({
  pageIndex: Math.floor(props.offset / props.limit),
  pageSize: props.limit,
}));
const state = computed(() => ({
  columnFilters: columnFilters.value,
  globalFilter: props.search,
  pagination: pagination.value,
  rowSelection: rowSelection.value,
  sorting: sorting.value,
}));

const table = useTable({
  features,
  columns,
  data: computed(() => props.lots),
  enableRowSelection: () => props.canChangeIntent,
  getRowId: (lot: LotResponse) => lot.broker_lot_id,
  manualFiltering: true,
  manualPagination: true,
  manualSorting: true,
  rowCount: computed(() => props.total),
  state,
  onRowSelectionChange: (updater) => {
    const current = rowSelection.value;
    const next = typeof updater === 'function' ? updater(current) : updater;
    for (const lot of props.lots) {
      const requested = Boolean(next[lot.broker_lot_id]);
      if (requested !== Boolean(current[lot.broker_lot_id])) {
        emit('intentChange', {
          brokerLotId: lot.broker_lot_id,
          ticker: lot.ticker,
          sourceGeneration: props.sourceGeneration,
          requested,
        });
      }
    }
  },
});

function requestSelectionFromClick(
  row: Row<LotTableFeatures, LotResponse>,
  event: MouseEvent,
): void {
  row.getToggleSelectedHandler()({
    target: { checked: !row.getIsSelected() },
    shiftKey: event.shiftKey,
  });
}
</script>

<template>
  <Table class="tax-lot-table">
    <TableCaption class="tw:m-0! tw:sr-only">Tax lots for {{ ticker }}</TableCaption>
    <TableHeader>
      <TableRow>
        <TableHead
          v-for="header in table.getHeaderGroups()[0]?.headers ?? []"
          :key="header.id"
          scope="col"
        >
          <FlexRender
            v-if="!header.isPlaceholder"
            :render="header.column.columnDef.header"
            :props="header.getContext()"
          />
        </TableHead>
      </TableRow>
    </TableHeader>
    <TableBody>
      <TableRow v-for="row in table.getRowModel().rows" :key="row.id">
        <template v-for="cell in row.getAllCells()" :key="cell.id">
          <TableCell v-if="cell.column.id === 'intent'" class="tw:whitespace-normal">
            <Field orientation="horizontal" class="tw:items-center tw:gap-2">
              <Checkbox
                :id="`request-${row.original.broker_lot_id}`"
                :model-value="row.getIsSelected()"
                :disabled="!canChangeIntent"
                :aria-label="`Request ${row.original.ticker} lot ${row.original.broker_lot_id}`"
                @click="requestSelectionFromClick(row, $event)"
              />
              <FieldLabel :for="`request-${row.original.broker_lot_id}`" class="tw:m-0! tw:text-sm">
                {{ row.getIsSelected() ? 'Requested' : 'Request' }}
              </FieldLabel>
            </Field>
            <p
              v-if="confirmedSellLotIds.has(row.original.broker_lot_id)"
              class="tw:mb-0! tw:mt-2! tw:text-xs tw:text-muted-foreground"
            >
              Backend-confirmed selected SELL lot in loaded DEMO run
            </p>
          </TableCell>
          <TableHead v-else-if="cell.column.id === 'broker_lot_id'" scope="row">
            <BrokerLotIdentity :broker-lot-id="row.original.broker_lot_id" />
          </TableHead>
          <TableCell v-else-if="cell.column.id === 'shares'" class="tw:whitespace-normal">
            <span class="tw:block"
              >{{ row.original.remaining_shares }} / {{ row.original.available_shares }}</span
            >
            <span class="tw:mt-1! tw:block tw:text-xs tw:text-muted-foreground">
              Whole available {{ row.original.whole_shares_available }} · fractional
              {{ row.original.fractional_shares }}
            </span>
          </TableCell>
          <TableCell v-else-if="cell.column.id === 'basis'" class="tw:whitespace-normal">
            <span class="tw:block"
              >{{ formatUsd(row.original.adjusted_unit_basis_usd) }} /
              {{ formatUsd(row.original.adjusted_total_basis_usd) }}</span
            >
          </TableCell>
          <TableCell v-else-if="cell.column.id === 'unrealized_pl'" class="tw:whitespace-normal">
            <span class="tw:block"
              >{{ formatUsd(row.original.unrealized_pl_usd) }} /
              {{ formatPercent(row.original.unrealized_pl_pct) }}</span
            >
          </TableCell>
          <TableCell v-else-if="cell.column.id === 'sleeve'" class="tw:whitespace-normal">
            <span class="tw:block">{{ row.original.sleeve_key ?? 'Unassigned' }}</span>
            <span class="tw:mt-1! tw:block tw:text-xs tw:text-muted-foreground">
              Sub-sleeve {{ row.original.sub_sleeve_key ?? 'Unassigned' }}
            </span>
          </TableCell>
          <TableCell v-else-if="cell.column.id === 'flags'" class="tw:whitespace-normal">
            <div v-if="row.original.quality_flags.length" class="tw:flex tw:flex-wrap tw:gap-1">
              <Badge
                v-for="(flag, index) in row.original.quality_flags"
                :key="`${flag}-${index}`"
                variant="secondary"
                >{{ flag }}</Badge
              >
            </div>
            <ul
              v-if="
                row.original.small_lot_cleanup_candidate ||
                row.original.position_cleanup_candidate ||
                row.original.fractional_cleanup_unsupported
              "
              class="tw:mb-0! tw:mt-2! tw:list-disc tw:pl-4 tw:text-sm"
            >
              <li v-if="row.original.small_lot_cleanup_candidate">Small-lot cleanup candidate</li>
              <li v-if="row.original.position_cleanup_candidate">Only lot in position</li>
              <li v-if="row.original.fractional_cleanup_unsupported">
                Fractional cleanup unsupported; not executable
              </li>
            </ul>
            <p
              v-if="
                !row.original.quality_flags.length &&
                !row.original.small_lot_cleanup_candidate &&
                !row.original.position_cleanup_candidate &&
                !row.original.fractional_cleanup_unsupported
              "
              class="tw:mb-0! tw:text-sm"
            >
              No quality or cleanup flags reported
            </p>
            <p class="tw:mb-0! tw:mt-2! tw:text-xs tw:text-muted-foreground">
              {{ row.original.source }} · as of {{ row.original.as_of }}
            </p>
          </TableCell>
          <TableCell v-else>
            <FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" />
          </TableCell>
        </template>
      </TableRow>
    </TableBody>
  </Table>
</template>
