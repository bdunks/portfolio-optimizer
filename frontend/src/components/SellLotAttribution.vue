<template>
  <section
    v-if="leg.side === 'SELL'"
    class="sell-lot-attribution"
    aria-label="SELL lot attribution"
  >
    <p class="quantity-note tw:mb-3! tw:text-sm tw:text-muted-foreground">
      These are API-proposed whole-share sale quantities for this run, not current remaining or
      available inventory. Inventory quantities are shown separately on Tax Lots.
    </p>
    <WorkspaceTableFrame :label="`SELL broker-lot attribution for leg ${leg.leg_id}`">
      <Table class="sell-lot-table tw:min-w-[64rem]">
        <TableCaption class="tw:m-0! tw:py-2 tw:text-left tw:text-foreground">
          SELL broker-lot attribution from the API · {{ leg.ticker ?? 'ticker unavailable' }}
        </TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead
              v-for="header in table.getHeaderGroups()[0]?.headers ?? []"
              :key="header.id"
              scope="col"
              class="tw:whitespace-normal"
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
              <TableCell
                v-if="cell.column.id === 'selection' && showSelectionControls"
                class="tw:whitespace-normal"
              >
                <Field orientation="horizontal" class="tw:items-center tw:gap-2">
                  <Checkbox
                    :id="`${selectionIdPrefix}-${row.original.broker_lot_id}`"
                    :model-value="row.getIsSelected()"
                    :disabled="selectionDisabled"
                    :aria-label="lotSelectionLabel(row.original.broker_lot_id)"
                    @update:model-value="requestSelectionFromUpdate(row, $event)"
                  />
                  <FieldLabel
                    :for="`${selectionIdPrefix}-${row.original.broker_lot_id}`"
                    class="tw:m-0! tw:text-sm tw:font-normal tw:text-foreground"
                  >
                    {{ row.getIsSelected() ? 'API selected' : 'Not selected' }}
                  </FieldLabel>
                </Field>
              </TableCell>
              <TableHead
                v-else-if="cell.column.id === 'broker_lot_id'"
                scope="row"
                class="tw:whitespace-normal tw:text-left"
              >
                <BrokerLotIdentity :broker-lot-id="row.original.broker_lot_id" />
              </TableHead>
              <TableCell v-else-if="cell.column.id === 'acquired_date'">
                {{ row.original.acquired_date }}
              </TableCell>
              <TableCell v-else-if="cell.column.id === 'shares'">
                {{ row.original.shares }}
              </TableCell>
              <TableCell v-else-if="cell.column.id === 'basis'">
                {{ formatUsd(row.original.adjusted_basis_usd) }}
              </TableCell>
              <TableCell v-else-if="cell.column.id === 'estimated_price'">
                {{ formatUsd(leg.estimated_unit_price_usd) }}
              </TableCell>
              <TableCell v-else-if="cell.column.id === 'term'">
                {{ row.original.st_lt }}
              </TableCell>
              <TableCell v-else-if="cell.column.id === 'realized_pl'">
                {{ formatUsd(row.original.realized_pl_usd) }}
              </TableCell>
            </template>
          </TableRow>
          <TableRow v-if="leg.selected_lots.length === 0">
            <TableCell :colspan="showSelectionControls ? 8 : 7" class="tw:whitespace-normal">
              No broker-lot rows were returned for this SELL leg.
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </WorkspaceTableFrame>
  </section>
</template>

<script setup lang="ts">
import type { ColumnDef, Row, RowSelectionState } from '@tanstack/vue-table';
import { FlexRender, rowSelectionFeature, tableFeatures, useTable } from '@tanstack/vue-table';
import { computed, useId } from 'vue';
import BrokerLotIdentity from '@/components/BrokerLotIdentity.vue';
import WorkspaceTableFrame from '@/components/WorkspaceTableFrame.vue';
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
import type { LotSelectionIntent } from '@/components/trade-review-types';
import type { RecommendationLegResponse } from '@/types/api';
import { formatUsd } from '@/utils/display-values';

const props = withDefaults(
  defineProps<{
    leg: RecommendationLegResponse;
    groupId?: string;
    canChangeSelection: boolean;
    pending?: boolean;
    rejected?: boolean;
    showSelectionControls?: boolean;
  }>(),
  { showSelectionControls: true },
);
const emit = defineEmits<{
  lotSelection: [intent: LotSelectionIntent];
}>();

const selectionIdPrefix = `sell-lot-${useId()}`;

type SelectedLot = RecommendationLegResponse['selected_lots'][number];
const features = tableFeatures({ rowSelectionFeature });
type SellLotTableFeatures = typeof features;

const allColumns: Array<ColumnDef<SellLotTableFeatures, SelectedLot>> = [
  { id: 'selection', header: 'Review selection', cell: () => '' },
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
  { id: 'shares', header: 'API proposed sale shares', cell: ({ row }) => row.original.shares },
  {
    id: 'basis',
    header: 'Adjusted basis (API value)',
    cell: ({ row }) => row.original.adjusted_basis_usd,
  },
  { id: 'estimated_price', header: 'Estimated price', cell: () => '' },
  { id: 'term', header: 'Term', cell: ({ row }) => row.original.st_lt },
  { id: 'realized_pl', header: 'Realized P/L', cell: ({ row }) => row.original.realized_pl_usd },
];
const columns = computed(() =>
  props.showSelectionControls
    ? allColumns
    : allColumns.filter((column) => column.id !== 'selection'),
);

const rowSelection = computed<RowSelectionState>(() =>
  Object.fromEntries(
    props.leg.selected_lots.filter((lot) => lot.selected).map((lot) => [lot.broker_lot_id, true]),
  ),
);
const selectionDisabled = computed(() =>
  Boolean(!props.groupId || props.pending || !props.canChangeSelection || props.rejected),
);
const table = useTable({
  features,
  columns,
  data: computed(() => props.leg.selected_lots),
  enableRowSelection: () =>
    Boolean(props.groupId && props.canChangeSelection && !props.pending && !props.rejected),
  getRowId: (lot: SelectedLot) => lot.broker_lot_id,
  state: computed(() => ({ rowSelection: rowSelection.value })),
  onRowSelectionChange: (updater) => {
    const current = rowSelection.value;
    const next = typeof updater === 'function' ? updater(current) : updater;
    for (const lot of props.leg.selected_lots) {
      const selected = Boolean(next[lot.broker_lot_id]);
      if (selected !== Boolean(current[lot.broker_lot_id])) {
        changeLotSelection(lot.broker_lot_id, selected);
      }
    }
  },
});

function lotSelectionLabel(brokerLotId: string): string {
  return props.groupId
    ? `Select SELL lot ${brokerLotId} in group ${props.groupId}`
    : `SELL lot ${brokerLotId} selection unavailable`;
}

function changeLotSelection(brokerLotId: string, selected: boolean): void {
  if (!props.groupId) return;
  emit('lotSelection', { groupId: props.groupId, brokerLotId, selected });
}

function requestSelectionFromUpdate(
  row: Row<SellLotTableFeatures, SelectedLot>,
  selected: boolean | 'indeterminate',
): void {
  if (selected === 'indeterminate') return;
  row.getToggleSelectedHandler()({
    target: { checked: selected },
    shiftKey: false,
  });
}
</script>
