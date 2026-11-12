<template>
  <section
    class="workspace-page tw:mx-auto tw:my-0 tw:min-w-0 tw:px-4 tw:py-4"
    data-workspace-foundation
    data-wash-sales-root
    aria-labelledby="wash-title"
  >
    <WorkspacePageHeader
      eyebrow="Managed-account restrictions"
      title="Wash Sales"
      title-id="wash-title"
      subtitle="Transaction history and restrictions from the local API; no wash-sale validation is implied."
    >
      <template #actions>
        <Button type="button" :disabled="isLoading" @click="refresh">
          {{ isLoading ? 'Loading…' : 'Refresh wash data' }}
        </Button>
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

    <form aria-label="Wash-sale filters" class="tw:min-w-0" @submit.prevent>
      <Card class="tw:min-w-0">
        <CardHeader class="tw:sr-only">
          <CardTitle id="wash-filter-title" role="heading" aria-level="2">
            Wash-sale filters
          </CardTitle>
          <CardDescription>Filter returned wash-sale records.</CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup class="tw:grid tw:grid-cols-1 tw:gap-4 tw:md:grid-cols-2">
            <filterForm.Field name="search">
              <template #default="{ field }">
                <UiField :data-invalid="field.state.meta.errors.length ? 'true' : undefined">
                  <FieldLabel for="wash-search">Filter records</FieldLabel>
                  <Input
                    id="wash-search"
                    type="search"
                    :model-value="field.state.value"
                    placeholder="Ticker, source, trigger, or ID"
                    :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                    :aria-describedby="
                      field.state.meta.errors.length ? 'wash-search-error' : undefined
                    "
                    @update:model-value="setSearch"
                    @blur="field.handleBlur"
                  />
                  <FieldError id="wash-search-error" :errors="field.state.meta.errors" />
                </UiField>
              </template>
            </filterForm.Field>

            <filterForm.Field name="transactionKind">
              <template #default="{ field }">
                <UiField :data-invalid="field.state.meta.errors.length ? 'true' : undefined">
                  <FieldLabel for="wash-transaction-kind">Transaction kind</FieldLabel>
                  <Select
                    :model-value="selectedTransactionKind"
                    @update:model-value="updateTransactionKind"
                  >
                    <SelectTrigger
                      id="wash-transaction-kind"
                      class="tw:w-full"
                      aria-label="Transaction kind"
                      :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                      :aria-describedby="
                        field.state.meta.errors.length ? 'wash-kind-error' : undefined
                      "
                      @blur="field.handleBlur"
                    >
                      <SelectValue placeholder="All transaction kinds" />
                    </SelectTrigger>
                    <SelectContent class="wash-sales-select-content">
                      <SelectGroup>
                        <SelectItem value="all">All transaction kinds</SelectItem>
                        <SelectItem
                          v-for="kind in WASH_SALES_TRANSACTION_KINDS"
                          :key="kind"
                          :value="kind"
                        >
                          {{ kind }}
                        </SelectItem>
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                  <FieldError id="wash-kind-error" :errors="field.state.meta.errors" />
                </UiField>
              </template>
            </filterForm.Field>
          </FieldGroup>
        </CardContent>
      </Card>
    </form>

    <Alert
      v-if="store.actionState.loadWashSales.pending && !washSales"
      role="status"
      aria-live="polite"
    >
      <AlertDescription>
        Loading wash-sale history and restrictions from the local API…
      </AlertDescription>
    </Alert>

    <Empty
      v-else-if="!washSales"
      class="tw:my-2 tw:border tw:border-border"
      role="status"
      aria-live="polite"
    >
      <EmptyHeader>
        <EmptyTitle id="wash-data-empty-title" role="heading" aria-level="2">
          No wash-sale data loaded
        </EmptyTitle>
        <EmptyDescription class="tw:m-0">
          Retry to request the current API response. No history or restrictions have been inferred.
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button variant="outline" type="button" :disabled="isLoading" @click="refresh">
          Retry loading wash data
        </Button>
      </EmptyContent>
    </Empty>

    <template v-else>
      <section aria-labelledby="coverage-title" class="tw:min-w-0">
        <Card class="tw:min-w-0">
          <CardHeader class="tw:flex tw:flex-row tw:items-start tw:justify-between tw:gap-4">
            <div class="tw:min-w-0">
              <CardTitle id="coverage-title" role="heading" aria-level="2">
                API coverage
              </CardTitle>
              <CardDescription>Source: {{ washSales.source }}</CardDescription>
            </div>
            <CardAction class="tw:ml-auto">
              <Badge role="status" variant="secondary">
                {{ washSales.demo ? 'DEMO' : 'API' }}
              </Badge>
            </CardAction>
          </CardHeader>
          <CardContent class="tw:flex tw:min-w-0 tw:flex-col tw:gap-4">
            <dl class="tw:m-0 tw:grid tw:grid-cols-1 tw:gap-2 tw:sm:grid-cols-2 tw:lg:grid-cols-4">
              <div
                class="tw:flex tw:min-w-0 tw:flex-col tw:gap-1 tw:rounded-lg tw:border tw:border-border tw:bg-muted/30 tw:p-3"
              >
                <dt class="tw:text-sm tw:text-muted-foreground">Transaction history rows</dt>
                <dd class="tw:m-0 tw:text-lg tw:font-semibold tw:tabular-nums">
                  {{ washSales.history.length }}
                </dd>
              </div>
              <div
                class="tw:flex tw:min-w-0 tw:flex-col tw:gap-1 tw:rounded-lg tw:border tw:border-border tw:bg-muted/30 tw:p-3"
              >
                <dt class="tw:text-sm tw:text-muted-foreground">Acquisition rows</dt>
                <dd class="tw:m-0 tw:text-lg tw:font-semibold tw:tabular-nums">
                  {{ washSales.acquisitions.length }}
                </dd>
              </div>
              <div
                class="tw:flex tw:min-w-0 tw:flex-col tw:gap-1 tw:rounded-lg tw:border tw:border-border tw:bg-muted/30 tw:p-3"
              >
                <dt class="tw:text-sm tw:text-muted-foreground">Current restrictions</dt>
                <dd class="tw:m-0 tw:text-lg tw:font-semibold tw:tabular-nums">
                  {{ washSales.current_restrictions.length }}
                </dd>
              </div>
              <div
                class="tw:flex tw:min-w-0 tw:flex-col tw:gap-1 tw:rounded-lg tw:border tw:border-border tw:bg-muted/30 tw:p-3"
              >
                <dt class="tw:text-sm tw:text-muted-foreground">Proposed restrictions</dt>
                <dd class="tw:m-0 tw:text-lg tw:font-semibold tw:tabular-nums">
                  {{ washSales.proposed_restrictions.length }}
                </dd>
              </div>
            </dl>

            <p class="tw:m-0 tw:text-sm tw:leading-relaxed tw:text-muted-foreground">
              Overall API coverage is unknown beyond returned rows. Conflicting-transaction links
              and affected tax-lot IDs are not included in this API response; they are not inferred
              here. Counts are returned-record counts; the endpoint provides no pagination or
              total-coverage indicator.
            </p>

            <Alert
              v-if="washSales.warnings.length"
              role="status"
              aria-live="polite"
              aria-label="API coverage warnings"
            >
              <AlertTitle>API coverage warnings</AlertTitle>
              <AlertDescription>
                <ul aria-label="API coverage warnings" class="tw:m-0 tw:list-disc tw:pl-4">
                  <li v-for="warning in washSales.warnings" :key="warning">{{ warning }}</li>
                </ul>
              </AlertDescription>
            </Alert>
            <p v-else class="tw:m-0 tw:text-sm tw:text-muted-foreground">
              The API returned no coverage warnings.
            </p>
          </CardContent>
        </Card>
      </section>

      <section aria-labelledby="history-title" class="tw:min-w-0">
        <Card class="tw:min-w-0">
          <CardHeader>
            <CardTitle id="history-title" role="heading" aria-level="2">
              Acquisition and transaction history
            </CardTitle>
            <CardDescription>
              Acquisition rows include the API-provided lookback-window end date; transaction keys
              and quantities are shown as returned.
            </CardDescription>
          </CardHeader>
          <CardContent class="tw:flex tw:min-w-0 tw:flex-col tw:gap-4">
            <WorkspaceTableFrame
              v-if="filteredAcquisitions.length"
              label="Wash-sale acquisition rows"
            >
              <Table class="tw:min-w-[940px]">
                <TableCaption class="tw:sr-only">
                  Acquisition history with API-provided lookback dates
                </TableCaption>
                <TableHeader>
                  <TableRow
                    v-for="headerGroup in acquisitionTable.getHeaderGroups()"
                    :key="headerGroup.id"
                  >
                    <TableHead v-for="header in headerGroup.headers" :key="header.id" scope="col">
                      <FlexRender v-if="!header.isPlaceholder" :header="header" />
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow v-for="row in acquisitionTable.getRowModel().rows" :key="row.id">
                    <template v-for="cell in row.getAllCells()" :key="cell.id">
                      <TableHead
                        v-if="cell.column.id === 'ticker'"
                        scope="row"
                        class="tw:text-left tw:font-medium"
                      >
                        <FlexRender :cell="cell" />
                      </TableHead>
                      <TableCell
                        v-else
                        :class="
                          cell.column.id === 'transactionKey' ? 'wash-sales-wrap-cell' : undefined
                        "
                      >
                        <FlexRender :cell="cell" />
                      </TableCell>
                    </template>
                  </TableRow>
                </TableBody>
              </Table>
            </WorkspaceTableFrame>
            <Empty v-else class="tw:border tw:border-border" role="status" aria-live="polite">
              <EmptyHeader>
                <EmptyTitle>
                  {{
                    washSales.acquisitions.length
                      ? 'No acquisition rows match these filters.'
                      : 'The API returned no acquisition rows.'
                  }}
                </EmptyTitle>
              </EmptyHeader>
            </Empty>

            <CardTitle class="tw:pt-2" role="heading" aria-level="3">
              All transaction history
            </CardTitle>
            <WorkspaceTableFrame
              v-if="filteredHistory.length"
              label="Wash-sale transaction history"
            >
              <Table class="tw:min-w-[940px]">
                <TableCaption class="tw:sr-only">
                  Managed-account transaction history returned by the API
                </TableCaption>
                <TableHeader>
                  <TableRow
                    v-for="headerGroup in historyTable.getHeaderGroups()"
                    :key="headerGroup.id"
                  >
                    <TableHead v-for="header in headerGroup.headers" :key="header.id" scope="col">
                      <FlexRender v-if="!header.isPlaceholder" :header="header" />
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow v-for="row in historyTable.getRowModel().rows" :key="row.id">
                    <template v-for="cell in row.getAllCells()" :key="cell.id">
                      <TableHead
                        v-if="cell.column.id === 'ticker'"
                        scope="row"
                        class="tw:text-left tw:font-medium"
                      >
                        <FlexRender :cell="cell" />
                      </TableHead>
                      <TableCell
                        v-else
                        :class="
                          cell.column.id === 'transactionKey' ? 'wash-sales-wrap-cell' : undefined
                        "
                      >
                        <FlexRender :cell="cell" />
                      </TableCell>
                    </template>
                  </TableRow>
                </TableBody>
              </Table>
            </WorkspaceTableFrame>
            <Empty v-else class="tw:border tw:border-border" role="status" aria-live="polite">
              <EmptyHeader>
                <EmptyTitle>
                  {{
                    washSales.history.length
                      ? 'No transaction rows match these filters.'
                      : 'The API returned no transaction-history rows.'
                  }}
                </EmptyTitle>
              </EmptyHeader>
            </Empty>
          </CardContent>
        </Card>
      </section>

      <section aria-labelledby="restrictions-title" class="tw:min-w-0">
        <Card class="tw:min-w-0">
          <CardHeader>
            <CardTitle id="restrictions-title" role="heading" aria-level="2">
              Purchase restrictions
            </CardTitle>
            <CardDescription>
              Current and proposed restrictions are separate API lists. Proposed records are not
              represented as executed sales.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <WorkspaceTableFrame
              v-if="filteredRestrictions.length"
              label="Wash-sale purchase restrictions"
            >
              <Table class="tw:min-w-[940px]">
                <TableCaption class="tw:sr-only">
                  Current and proposed purchase restrictions
                </TableCaption>
                <TableHeader>
                  <TableRow
                    v-for="headerGroup in restrictionTable.getHeaderGroups()"
                    :key="headerGroup.id"
                  >
                    <TableHead v-for="header in headerGroup.headers" :key="header.id" scope="col">
                      <FlexRender v-if="!header.isPlaceholder" :header="header" />
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow v-for="row in restrictionTable.getRowModel().rows" :key="row.id">
                    <template v-for="cell in row.getAllCells()" :key="cell.id">
                      <TableHead
                        v-if="cell.column.id === 'statusLabel'"
                        scope="row"
                        class="tw:text-left tw:font-medium"
                      >
                        <FlexRender :cell="cell" />
                      </TableHead>
                      <TableCell
                        v-else
                        :class="cell.column.id === 'runSource' ? 'wash-sales-wrap-cell' : undefined"
                      >
                        <FlexRender :cell="cell" />
                      </TableCell>
                    </template>
                  </TableRow>
                </TableBody>
              </Table>
            </WorkspaceTableFrame>
            <Empty v-else class="tw:border tw:border-border" role="status" aria-live="polite">
              <EmptyHeader>
                <EmptyTitle>
                  {{
                    allRestrictions.length
                      ? 'No restrictions match these filters.'
                      : 'The API returned no current or proposed restrictions.'
                  }}
                </EmptyTitle>
              </EmptyHeader>
            </Empty>
          </CardContent>
        </Card>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { FlexRender, tableFeatures, useTable } from '@tanstack/vue-table';
import type { ColumnDef } from '@tanstack/vue-table';
import { useForm } from '@tanstack/vue-form';
import type {
  WashAcquisitionResponse,
  WashRestrictionResponse,
  WashTransactionResponse,
} from '@/types/api';
import ApiActionError from '@/components/ApiActionError.vue';
import WorkspacePageHeader from '@/components/WorkspacePageHeader.vue';
import WorkspaceCapabilityNotice from '@/components/WorkspaceCapabilityNotice.vue';
import WorkspaceTableFrame from '@/components/WorkspaceTableFrame.vue';
import ResourceFreshnessNotice from '@/components/ResourceFreshnessNotice.vue';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from '@/components/ui/empty';
import { FieldError, FieldGroup, FieldLabel, Field as UiField } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  isWashSalesTransactionKind,
  WASH_SALES_TRANSACTION_KINDS,
  washSalesFilterSchema,
} from '@/forms/wash-sales-filters';
import type { WashSalesFilterValues } from '@/forms/wash-sales-filters';
import { useWorkspace } from '@/composables/use-workspace';

const store = useWorkspace();
const defaultFilterValues: WashSalesFilterValues = { search: '', transactionKind: '' };
const filterForm = useForm({
  defaultValues: defaultFilterValues,
  validators: { onChange: washSalesFilterSchema },
});
const filters = filterForm.useSelector((state) => state.values);
const washSales = computed(() => store.washSales);
const isLoading = computed(() => store.actionState.loadWashSales.pending);
const searchNeedle = computed(() => filters.value.search.trim().toLocaleLowerCase());
const allKindValue = 'all';
const selectedTransactionKind = computed(() => filters.value.transactionKind || allKindValue);

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
type WashRestrictionTableRow = WashRestrictionResponse & { statusLabel: 'Current' | 'Proposed' };
const allRestrictions = computed<WashRestrictionTableRow[]>(() => [
  ...(washSales.value?.current_restrictions ?? []).map((row) => ({
    ...row,
    statusLabel: 'Current' as const,
  })),
  ...(washSales.value?.proposed_restrictions ?? []).map((row) => ({
    ...row,
    statusLabel: 'Proposed' as const,
  })),
]);
const filteredRestrictions = computed(() =>
  allRestrictions.value.filter((row) =>
    matchesText([row.ticker, row.trigger, row.source, row.validation, row.run_id]),
  ),
);

function kindMatches(row: WashTransactionResponse | WashAcquisitionResponse): boolean {
  return (
    filters.value.transactionKind === '' || row.transaction_kind === filters.value.transactionKind
  );
}

function matchesText(values: Array<string | null | undefined>): boolean {
  if (!searchNeedle.value) return true;
  return values.some((value) => value?.toLocaleLowerCase().includes(searchNeedle.value));
}

function setSearch(value: string | number): void {
  filterForm.setFieldValue('search', String(value));
}

function updateTransactionKind(value: unknown): void {
  if (typeof value !== 'string') return;
  if (value === allKindValue) {
    filterForm.setFieldValue('transactionKind', '');
  } else if (isWashSalesTransactionKind(value)) {
    filterForm.setFieldValue('transactionKind', value);
  }
}

const washSalesTableFeatures = tableFeatures({});
const acquisitionColumns: Array<ColumnDef<typeof washSalesTableFeatures, WashAcquisitionResponse>> =
  [
    {
      id: 'ticker',
      accessorKey: 'ticker',
      header: 'Ticker',
      cell: ({ row }) => row.original.ticker ?? 'Ticker unavailable',
    },
    { accessorKey: 'transaction_kind', header: 'Kind' },
    {
      id: 'tradeDateTime',
      header: 'Trade date / time',
      cell: ({ row }) => `${row.original.trade_date} · ${row.original.transaction_time}`,
    },
    { accessorKey: 'shares', header: 'Shares' },
    { accessorKey: 'lookback_window_end_date', header: 'Lookback window ends' },
    { id: 'transactionKey', accessorKey: 'broker_transaction_key', header: 'Transaction key' },
    { accessorKey: 'source', header: 'Source' },
  ];
const historyColumns: Array<ColumnDef<typeof washSalesTableFeatures, WashTransactionResponse>> = [
  {
    id: 'ticker',
    accessorKey: 'ticker',
    header: 'Ticker',
    cell: ({ row }) => row.original.ticker ?? 'Ticker unavailable',
  },
  { accessorKey: 'transaction_kind', header: 'Kind' },
  {
    id: 'isAcquisition',
    header: 'Acquisition?',
    cell: ({ row }) => (row.original.is_acquisition ? 'Yes' : 'No'),
  },
  {
    id: 'tradeDateTime',
    header: 'Trade date / time',
    cell: ({ row }) => `${row.original.trade_date} · ${row.original.transaction_time}`,
  },
  { accessorKey: 'shares', header: 'Shares' },
  { id: 'transactionKey', accessorKey: 'broker_transaction_key', header: 'Transaction key' },
  { accessorKey: 'source', header: 'Source' },
];
const restrictionColumns: Array<ColumnDef<typeof washSalesTableFeatures, WashRestrictionTableRow>> =
  [
    { accessorKey: 'statusLabel', header: 'Status' },
    { accessorKey: 'ticker', header: 'Ticker' },
    { accessorKey: 'trigger', header: 'Trigger' },
    { accessorKey: 'loss_sale_date', header: 'Loss-sale date' },
    { accessorKey: 'next_eligible_purchase_date', header: 'Next eligible purchase' },
    { accessorKey: 'validation', header: 'Validation' },
    {
      id: 'runSource',
      header: 'Run / source',
      cell: ({ row }) => `${row.original.run_id ?? 'No run ID returned'} · ${row.original.source}`,
    },
  ];
const acquisitionTable = useTable({
  features: washSalesTableFeatures,
  columns: acquisitionColumns,
  data: filteredAcquisitions,
});
const historyTable = useTable({
  features: washSalesTableFeatures,
  columns: historyColumns,
  data: filteredHistory,
});
const restrictionTable = useTable({
  features: washSalesTableFeatures,
  columns: restrictionColumns,
  data: filteredRestrictions,
});

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
:global([data-wash-sales-root]) {
  color: var(--foreground);
}

:global([data-wash-sales-root] input[data-slot='input']) {
  appearance: none;
  border: 1px solid var(--input);
  border-radius: var(--radius-md);
  background-color: transparent;
  color: var(--foreground);
  font-family: inherit;
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
}

:global([data-wash-sales-root] button[data-slot='button']),
:global([data-wash-sales-root] button[data-slot='select-trigger']) {
  appearance: none;
  font-family: inherit;
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
  text-transform: none;
}

:global([data-wash-sales-root] button[data-slot='select-trigger']) {
  border: 1px solid var(--input);
  background-color: transparent;
  color: var(--foreground);
}

:global([data-wash-sales-root] [data-slot='table-container']) {
  overflow: visible;
}

:global([data-wash-sales-root] table[data-slot='table']) {
  border-collapse: collapse;
}

:global([data-wash-sales-root] .wash-sales-wrap-cell) {
  max-width: 14rem;
  overflow-wrap: anywhere;
  white-space: normal;
}

:global(.wash-sales-select-content) {
  color: var(--popover-foreground);
  font-family: inherit;
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
}
</style>
