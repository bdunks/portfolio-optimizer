<template>
  <section
    class="holding-overrides-root workspace-foundation tw:min-w-0"
    data-workspace-foundation
    data-policy-holding-overrides-root
    :aria-labelledby="`${sectionId}-title`"
  >
    <Card class="tw:min-w-0">
      <CardHeader>
        <CardTitle
          :id="`${sectionId}-title`"
          class="holding-overrides-title"
          role="heading"
          aria-level="2"
        >
          Explicit holding overrides
        </CardTitle>
        <CardDescription class="holding-overrides-description">
          “Use default resolution” removes an override. The API resolves approved ETFs by configured
          assignment and individual equities plus VB/VXF by the direct-index container unless
          explicitly overridden; this page does not infer new assignments.
        </CardDescription>
      </CardHeader>
      <CardContent class="tw:min-w-0">
        <Alert
          v-if="portfolioLoading && !portfolioAvailable"
          role="status"
          aria-live="polite"
          class="tw:mb-4"
        >
          <AlertDescription>Loading the current single-account holding list…</AlertDescription>
        </Alert>
        <Alert v-else-if="!portfolioAvailable" role="status" aria-live="polite" class="tw:mb-4">
          <AlertDescription>
            Current holdings are unavailable. Existing saved overrides remain editable below; no
            holdings are guessed.
          </AlertDescription>
        </Alert>
        <WorkspaceTableFrame label="Holding sleeve overrides">
          <Table class="tw:min-w-[48rem]">
            <TableCaption class="tw:sr-only">
              Current API sleeve resolutions and explicit overrides by ticker
            </TableCaption>
            <TableHeader>
              <TableRow v-for="headerGroup in table.getHeaderGroups()" :key="headerGroup.id">
                <TableHead v-for="header in headerGroup.headers" :key="header.id" scope="col">
                  <FlexRender v-if="!header.isPlaceholder" :header="header" />
                </TableHead>
              </TableRow>
            </TableHeader>
            <selectionForm.Field name="selectedTargets">
              <template #default="{ field }">
                <TableBody>
                  <TableRow v-for="row in tableRows" :key="row.id">
                    <template v-for="cell in row.getAllCells()" :key="cell.id">
                      <TableHead
                        v-if="cell.column.id === 'ticker'"
                        scope="row"
                        class="tw:text-left tw:font-medium"
                      >
                        <FlexRender :cell="cell" />
                      </TableHead>
                      <TableCell v-else-if="cell.column.id === 'currentResolution'">
                        <FlexRender :cell="cell" />
                      </TableCell>
                      <TableCell v-else>
                        <FieldGroup class="tw:min-w-0 tw:gap-1">
                          <Field>
                            <FieldLabel
                              :id="`${sectionId}-override-${row.id}-label`"
                              :for="`${sectionId}-override-${row.id}`"
                              class="tw:sr-only"
                            >
                              Explicit override for {{ row.original.ticker }}
                            </FieldLabel>
                            <Select
                              :model-value="
                                field.state.value[row.original.ticker] ??
                                currentSelectionValue(row.original.ticker)
                              "
                              @update:model-value="
                                (value) =>
                                  updateOverrideSelection(field, row.original.ticker, value)
                              "
                            >
                              <SelectTrigger
                                :id="`${sectionId}-override-${row.id}`"
                                :aria-labelledby="`${sectionId}-override-${row.id}-label`"
                                class="tw:w-full"
                              >
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectGroup>
                                  <SelectItem :value="defaultTargetValue">
                                    Use default resolution
                                  </SelectItem>
                                  <SelectItem
                                    v-if="currentOverrideNeedsRepair(row.original.ticker)"
                                    :value="invalidTargetValue"
                                    disabled
                                  >
                                    {{ currentAssignmentUnavailableLabel(row.original.ticker) }}
                                  </SelectItem>
                                  <SelectItem
                                    v-for="target in overrideOptions"
                                    :key="target.sleeve_key"
                                    :value="target.sleeve_key"
                                  >
                                    {{ target.display_name || target.sleeve_key }}
                                  </SelectItem>
                                </SelectGroup>
                              </SelectContent>
                            </Select>
                          </Field>
                        </FieldGroup>
                      </TableCell>
                    </template>
                  </TableRow>
                  <TableEmpty
                    v-if="tableRows.length === 0"
                    :colspan="3"
                    class="tw:whitespace-normal"
                  >
                    <Empty class="tw:gap-2 tw:border-0 tw:p-2">
                      <EmptyHeader>
                        <EmptyTitle>No current holdings or explicit overrides</EmptyTitle>
                        <EmptyDescription>
                          No current holdings or explicit overrides have been returned.
                        </EmptyDescription>
                      </EmptyHeader>
                    </Empty>
                  </TableEmpty>
                </TableBody>
              </template>
            </selectionForm.Field>
          </Table>
        </WorkspaceTableFrame>
      </CardContent>
    </Card>
  </section>
</template>

<script setup lang="ts">
import { useForm } from '@tanstack/vue-form';
import { FlexRender, tableFeatures, useTable } from '@tanstack/vue-table';
import type { ColumnDef } from '@tanstack/vue-table';
import { computed, shallowRef, useId, watch } from 'vue';
import { z } from 'zod';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty';
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field';
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
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import WorkspaceTableFrame from '@/components/WorkspaceTableFrame.vue';
import type { OverrideInput, PositionResponse } from '@/types/api';
import type { EditablePolicyDraft } from '@/pages/policy-form';

const props = defineProps<{
  draft: EditablePolicyDraft;
  positions: readonly PositionResponse[] | null;
  portfolioAvailable: boolean;
  portfolioLoading: boolean;
}>();
const emit = defineEmits<{
  'update:overrides': [overrides: OverrideInput[]];
}>();

const sectionId = useId();
const overrides = computed(() => props.draft.overrides);
const sleeves = computed(() => props.draft.sleeves);
const enabledSleeves = computed(() => {
  const seen = new Set<string>();
  return sleeves.value.filter((sleeve) => {
    if (sleeve.enabled === false || seen.has(sleeve.sleeve_key)) return false;
    seen.add(sleeve.sleeve_key);
    return true;
  });
});
const overrideOptions = computed(() => enabledSleeves.value);
const defaultTargetValue = computed(() =>
  uniqueSentinel(
    'default',
    sleeves.value.map((sleeve) => sleeve.sleeve_key),
  ),
);
const invalidTargetValue = computed(() =>
  uniqueSentinel('unavailable', [
    ...sleeves.value.map((sleeve) => sleeve.sleeve_key),
    defaultTargetValue.value,
  ]),
);

type OverrideHolding = { ticker: string; currentLabel: string };
const overrideHoldings = computed<OverrideHolding[]>(() => {
  const holdings = new Map<string, OverrideHolding>();
  for (const position of props.positions ?? []) {
    if (holdings.has(position.ticker)) continue;
    holdings.set(position.ticker, {
      ticker: position.ticker,
      currentLabel: position.sub_sleeve_key
        ? `${position.sleeve_key} → ${position.sub_sleeve_key}`
        : (position.sleeve_key ?? 'No API sleeve resolution'),
    });
  }
  for (const override of overrides.value) {
    if (!holdings.has(override.ticker)) {
      holdings.set(override.ticker, {
        ticker: override.ticker,
        currentLabel: 'Override returned by policy API; holding not in current portfolio response',
      });
    }
  }
  return [...holdings.values()];
});

function uniqueSentinel(purpose: string, reservedValues: readonly string[]): string {
  const base = `__portfolio_optimizer_policy_holding_override_${purpose}__`;
  const reserved = new Set(reservedValues);
  let candidate = base;
  let suffix = 0;
  while (reserved.has(candidate)) candidate = `${base}${++suffix}`;
  return candidate;
}

function currentOverride(ticker: string): OverrideInput | undefined {
  return overrides.value.find((override) => override.ticker === ticker);
}

function currentTargetKey(ticker: string): string | null {
  const override = currentOverride(ticker);
  return override ? (override.sub_sleeve_key ?? override.sleeve_key) : null;
}

function currentSelectionValue(ticker: string): string {
  const override = currentOverride(ticker);
  if (!override) return defaultTargetValue.value;
  const targetKey = currentTargetKey(ticker);
  return enabledSleeves.value.some((sleeve) => sleeve.sleeve_key === targetKey)
    ? (targetKey ?? invalidTargetValue.value)
    : invalidTargetValue.value;
}

function currentOverrideNeedsRepair(ticker: string): boolean {
  const override = currentOverride(ticker);
  return (
    !!override &&
    !enabledSleeves.value.some((sleeve) => sleeve.sleeve_key === currentTargetKey(ticker))
  );
}

function currentAssignmentUnavailableLabel(ticker: string): string {
  const override = currentOverride(ticker);
  if (!override) return 'Current assignment unavailable; choose a valid target or remove';
  const targetKey = currentTargetKey(ticker);
  const targetExists = sleeves.value.some((sleeve) => sleeve.sleeve_key === targetKey);
  const assignment = override.sub_sleeve_key
    ? `${override.sleeve_key} → ${override.sub_sleeve_key}`
    : override.sleeve_key;
  return `Current assignment — ${targetExists ? 'disabled' : 'missing target'} (${assignment}); choose a valid target or remove`;
}

const overrideSelectionSchema = z.object({
  selectedTargets: z.record(z.string(), z.string()),
});
type OverrideSelectionValues = z.infer<typeof overrideSelectionSchema>;
function selectionValuesFromDraft(): OverrideSelectionValues {
  return {
    selectedTargets: Object.fromEntries(
      overrideHoldings.value.map((holding) => [
        holding.ticker,
        currentSelectionValue(holding.ticker),
      ]),
    ),
  };
}
const selectionForm = useForm({
  defaultValues: selectionValuesFromDraft(),
  validators: { onChange: overrideSelectionSchema },
});
watch(
  [() => props.draft.sleeves, () => props.draft.overrides, () => props.positions],
  () => selectionForm.reset(selectionValuesFromDraft()),
  { deep: true, flush: 'sync' },
);

type SelectionField = {
  state: { value: Record<string, string> };
  handleChange: (value: Record<string, string>) => void;
};
function updateOverrideSelection(field: SelectionField, ticker: string, value: unknown): void {
  if (typeof value !== 'string') return;
  field.handleChange({ ...field.state.value, [ticker]: value });
  setOverrideTarget(ticker, value);
}

function setOverrideTarget(ticker: string, targetKey: string): void {
  if (targetKey === defaultTargetValue.value) {
    const next = overrides.value.filter((override) => override.ticker !== ticker);
    if (next.length !== overrides.value.length)
      emit(
        'update:overrides',
        next.map((item) => ({ ...item })),
      );
    return;
  }
  if (targetKey === invalidTargetValue.value) return;
  const target = enabledSleeves.value.find((sleeve) => sleeve.sleeve_key === targetKey);
  if (!target) return;
  const nextOverride: OverrideInput = target.parent_sleeve_key
    ? { ticker, sleeve_key: target.parent_sleeve_key, sub_sleeve_key: target.sleeve_key }
    : { ticker, sleeve_key: target.sleeve_key, sub_sleeve_key: null };
  const next: OverrideInput[] = [];
  let replaced = false;
  for (const existing of overrides.value) {
    if (existing.ticker !== ticker) {
      next.push({ ...existing });
    } else if (!replaced) {
      next.push(nextOverride);
      replaced = true;
    }
  }
  if (!replaced) next.push(nextOverride);
  emit('update:overrides', next);
}

const overrideTableFeatures = tableFeatures({});
const columns: Array<ColumnDef<typeof overrideTableFeatures, OverrideHolding>> = [
  {
    id: 'ticker',
    accessorKey: 'ticker',
    header: 'Ticker',
  },
  {
    id: 'currentResolution',
    accessorKey: 'currentLabel',
    header: 'Current API resolution',
  },
  {
    id: 'explicitOverride',
    accessorFn: () => '',
    header: 'Explicit override',
  },
];
const tableData = shallowRef(overrideHoldings.value);
const table = useTable({ features: overrideTableFeatures, columns, data: tableData });
watch(
  overrideHoldings,
  (rows) => {
    tableData.value = rows;
    table.setOptions((previous) => ({ ...previous, data: rows }));
  },
  { flush: 'sync' },
);
const tableRows = computed(() => (tableData.value.length === 0 ? [] : table.getRowModel().rows));
</script>

<style scoped>
.holding-overrides-root {
  color: var(--foreground);
}

.holding-overrides-root :deep(p) {
  all: initial;
  display: block;
  color: inherit;
  font-family: inherit;
  font-size: inherit;
  font-weight: inherit;
  line-height: inherit;
}

.holding-overrides-root :deep(.holding-overrides-title) {
  all: initial;
  display: block;
  color: var(--foreground);
  font-family: inherit;
  font-size: var(--tw-text-lg);
  font-weight: var(--tw-font-weight-semibold);
  letter-spacing: var(--tw-tracking-tight);
  line-height: var(--tw-text-lg--line-height);
}

.holding-overrides-root :deep(.holding-overrides-description) {
  all: initial;
  display: block;
  color: var(--muted-foreground);
  font-family: inherit;
  font-size: var(--tw-text-sm);
  font-weight: var(--tw-font-weight-normal);
  line-height: var(--tw-text-sm--line-height);
}

.holding-overrides-root :deep(button[data-slot='select-trigger']) {
  appearance: none;
  border: 1px solid var(--input);
  background-color: transparent;
  color: var(--foreground);
  font-family: inherit;
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
  text-transform: none;
}

.holding-overrides-root :deep([data-slot='table-container']) {
  width: max-content;
  min-width: 100%;
  overflow: visible;
}
</style>
