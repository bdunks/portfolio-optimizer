<template>
  <section
    ref="sectionRoot"
    class="replacement-editor-root workspace-foundation tw:min-w-0"
    data-workspace-foundation
    data-policy-replacement-sets-root
    :aria-labelledby="`${sectionId}-title`"
  >
    <Card class="tw:min-w-0">
      <CardHeader class="tw:gap-3">
        <div
          class="tw:flex tw:flex-col tw:gap-4 tw:md:flex-row tw:md:items-start tw:md:justify-between"
        >
          <div class="tw:min-w-0 tw:flex-1">
            <h2 :id="`${sectionId}-title`" class="replacement-editor-title">
              {{
                props.context
                  ? `Replacement sets for ${props.context.label}`
                  : 'All configured replacement sets'
              }}
            </h2>
            <CardDescription class="replacement-editor-description">
              Replacement-set IDs group securities; priority, suitability, enabled status, and
              allocation assignments are explicit policy data. Distinct investments are a
              user-entered wash-sale assumption, not a guarantee or automated exposure-equivalence
              check.
            </CardDescription>
          </div>
          <Button :id="addButtonId" type="button" variant="outline" size="sm" @click="addSecurity">
            <Plus aria-hidden="true" />
            Add security
          </Button>
        </div>
      </CardHeader>

      <CardContent class="tw:min-w-0">
        <div>
          <Table
            role="region"
            aria-label="Replacement security candidates"
            tabindex="0"
            class="tw:min-w-[76rem]"
          >
            <TableCaption class="tw:sr-only">
              Configured replacement-set securities and policy settings
            </TableCaption>
            <TableHeader>
              <TableRow v-for="headerGroup in table.getHeaderGroups()" :key="headerGroup.id">
                <TableHead v-for="header in headerGroup.headers" :key="header.id" scope="col">
                  <FlexRender v-if="!header.isPlaceholder" :header="header" />
                </TableHead>
              </TableRow>
            </TableHeader>
            <securityForm.Field name="rows">
              <template #default>
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
                      <TableCell v-else>
                        <FlexRender :cell="cell" />
                      </TableCell>
                    </template>
                  </TableRow>
                  <TableEmpty v-if="tableRows.length === 0" :colspan="9">
                    <Empty class="tw:border-0 tw:bg-transparent">
                      <EmptyHeader>
                        <EmptyTitle>{{
                          props.context
                            ? `No replacement securities for ${props.context.label}`
                            : 'No replacement candidates'
                        }}</EmptyTitle>
                        <EmptyDescription>
                          Nothing is inferred or added automatically. Add a security to configure a
                          replacement set.
                        </EmptyDescription>
                      </EmptyHeader>
                    </Empty>
                  </TableEmpty>
                </TableBody>
              </template>
            </securityForm.Field>
          </Table>
        </div>
      </CardContent>
    </Card>
  </section>
</template>

<script setup lang="ts">
import { useForm } from '@tanstack/vue-form';
import { FlexRender, tableFeatures, useTable } from '@tanstack/vue-table';
import type { ColumnDef } from '@tanstack/vue-table';
import { Plus } from '@lucide/vue';
import type { Component } from 'vue';
import { h, computed, nextTick, shallowRef, useId, watch } from 'vue';
import PolicyReplacementSecurityCell from '@/components/PolicyReplacementSecurityCell.vue';
import type { ReplacementSecurityCellKind } from '@/components/PolicyReplacementSecurityCell.vue';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty';

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
import type { AllowedSecurityInput } from '@/types/api';
import type { EditablePolicyDraft, EditableSleeve } from '@/pages/policy-form';
import { policyReplacementSetsSchema } from '@/forms/policy-replacement-sets';

type ReplacementSetsContext = {
  sleeveKey: string;
  label: string;
  requireSubSleeve?: boolean;
  newSubSleeveKey?: string;
};

const props = defineProps<{
  draft: EditablePolicyDraft;
  context?: ReplacementSetsContext | null;
}>();
const emit = defineEmits<{
  'update:allowed-securities': [securities: AllowedSecurityInput[]];
}>();

const sectionId = useId();
const sectionRoot = shallowRef<HTMLElement | null>(null);
const addButtonId = `${sectionId}-add-candidate`;
let nextRowId = 0;

const pendingAddedRows = shallowRef(new Map<string, string>());
type ReplacementFormSecurity = {
  ticker: string;
  sleeve_key: string;
  sub_sleeve_key?: string | null | undefined;
  replacement_set_id?: string | undefined;
  priority?: number | undefined;
  enabled?: boolean | undefined;
  exposure_suitability?: string | null | undefined;
};
type ReplacementFormRow = { rowId: string; security: ReplacementFormSecurity };
type SelectChoice = { value: string; label: string; domainValue: string | null };

function createRowId(): string {
  nextRowId += 1;
  return `${sectionId}-candidate-${nextRowId}`;
}

function rowsFromSecurities(securities: readonly AllowedSecurityInput[]): ReplacementFormRow[] {
  return securities.map((security) => ({ rowId: createRowId(), security: { ...security } }));
}

const securityForm = useForm({
  defaultValues: { rows: rowsFromSecurities(props.draft.allowedSecurities) },
  validators: { onChange: policyReplacementSetsSchema },
});
const formValues = securityForm.useSelector((state) => state.values);
const rows = computed(() => formValues.value.rows);
const sleeves = computed(() => props.draft.sleeves);
const enabledSleeves = computed(() => sleeves.value.filter((sleeve) => sleeve.enabled !== false));
const enabledTopLevelSleeves = computed(() =>
  enabledSleeves.value.filter((sleeve) => !sleeve.parent_sleeve_key),
);

function enabledChildren(parentKey: string): EditableSleeve[] {
  return enabledSleeves.value.filter((sleeve) => sleeve.parent_sleeve_key === parentKey);
}

function optionToken(kind: 'parent' | 'sub', value: string): string {
  return `${sectionId}-${kind}-${encodeURIComponent(value)}`;
}

function choice(kind: 'parent' | 'sub', domainValue: string | null, label: string): SelectChoice {
  const tokenValue = domainValue === null ? 'none' : `value:${domainValue}`;
  return { value: optionToken(kind, tokenValue), domainValue, label };
}

function parentChoices(security: AllowedSecurityInput): SelectChoice[] {
  const options = [choice('parent', '', 'Choose sleeve')];
  for (const sleeve of enabledTopLevelSleeves.value) {
    if (sleeve.sleeve_key && !options.some((option) => option.domainValue === sleeve.sleeve_key)) {
      options.push(choice('parent', sleeve.sleeve_key, sleeve.display_name || sleeve.sleeve_key));
    }
  }

  if (!options.some((option) => option.domainValue === security.sleeve_key)) {
    const saved = sleeves.value.find((sleeve) => sleeve.sleeve_key === security.sleeve_key);
    const status = !saved
      ? 'missing'
      : saved.enabled === false
        ? 'disabled'
        : saved.parent_sleeve_key
          ? 'not a parent sleeve'
          : 'unavailable';
    const name = saved?.display_name || security.sleeve_key;
    options.push(
      choice('parent', security.sleeve_key, `Current parent sleeve — ${status} (${name})`),
    );
  }
  return options;
}

function subSleeveChoices(security: AllowedSecurityInput): SelectChoice[] {
  const options = [choice('sub', null, 'None')];
  for (const sleeve of enabledChildren(security.sleeve_key)) {
    if (!options.some((option) => option.domainValue === sleeve.sleeve_key)) {
      options.push(choice('sub', sleeve.sleeve_key, sleeve.display_name || sleeve.sleeve_key));
    }
  }

  const currentSubSleeve = security.sub_sleeve_key;
  if (
    currentSubSleeve != null &&
    !options.some((option) => option.domainValue === currentSubSleeve)
  ) {
    const saved = sleeves.value.find((sleeve) => sleeve.sleeve_key === currentSubSleeve);
    const status = !currentSubSleeve
      ? 'empty value'
      : !saved
        ? 'missing'
        : saved.enabled === false
          ? 'disabled'
          : saved.parent_sleeve_key !== security.sleeve_key
            ? 'not under the current parent'
            : 'unavailable';
    const name = saved?.display_name || currentSubSleeve || 'blank';
    options.push(choice('sub', currentSubSleeve, `Current sub-sleeve — ${status} (${name})`));
  }
  return options;
}

function selectedOptionValue(options: readonly SelectChoice[], domainValue: string | null): string {
  return (
    options.find((option) => option.domainValue === domainValue)?.value ?? options[0]?.value ?? ''
  );
}

const validationResult = computed(() => policyReplacementSetsSchema.safeParse(formValues.value));
const priorityErrors = computed<Record<string, string>>(() => {
  if (validationResult.value.success) return {};
  const errors: Record<string, string> = {};
  for (const issue of validationResult.value.error.issues) {
    const [root, rowIndex, objectKey, fieldKey] = issue.path;
    if (
      root !== 'rows' ||
      typeof rowIndex !== 'number' ||
      objectKey !== 'security' ||
      fieldKey !== 'priority'
    ) {
      continue;
    }
    const row = formValues.value.rows[rowIndex];
    if (row) errors[row.rowId] = issue.message;
  }
  return errors;
});

function securityInput(security: ReplacementFormSecurity): AllowedSecurityInput {
  const input: AllowedSecurityInput = {
    ticker: security.ticker,
    sleeve_key: security.sleeve_key,
  };
  if (security.sub_sleeve_key !== undefined) input.sub_sleeve_key = security.sub_sleeve_key;
  if (security.replacement_set_id !== undefined) {
    input.replacement_set_id = security.replacement_set_id;
  }
  if (security.priority !== undefined) input.priority = security.priority;
  if (security.enabled !== undefined) input.enabled = security.enabled;
  if (security.exposure_suitability !== undefined)
    input.exposure_suitability = security.exposure_suitability;
  return input;
}

function securitiesFromRows(formRows: readonly ReplacementFormRow[]): AllowedSecurityInput[] {
  return formRows.map(({ security }) => securityInput(security));
}

function sameSecurity(left: AllowedSecurityInput, right: AllowedSecurityInput): boolean {
  const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
  for (const rawKey of keys) {
    const key = rawKey as keyof AllowedSecurityInput;
    if (
      Object.prototype.hasOwnProperty.call(left, key) !==
        Object.prototype.hasOwnProperty.call(right, key) ||
      !Object.is(left[key], right[key])
    ) {
      return false;
    }
  }
  return true;
}

function sameSecurities(
  left: readonly AllowedSecurityInput[],
  right: readonly AllowedSecurityInput[],
): boolean {
  return (
    left.length === right.length &&
    left.every((security, index) => {
      const other = right[index];
      return other !== undefined && sameSecurity(security, other);
    })
  );
}

watch(
  formValues,
  (values) => {
    const securities = securitiesFromRows(values.rows);
    if (!sameSecurities(securities, props.draft.allowedSecurities)) {
      emit('update:allowed-securities', securities);
    }
  },
  { deep: true, flush: 'sync' },
);

watch(
  () => props.draft.allowedSecurities,
  (securities) => {
    if (!sameSecurities(securitiesFromRows(formValues.value.rows), securities)) {
      securityForm.reset({ rows: rowsFromSecurities(securities) });
    }
  },
  { deep: true, flush: 'sync' },
);

function setRows(nextRows: ReplacementFormRow[]): void {
  securityForm.setFieldValue('rows', nextRows);
}

function updateSecurity(rowId: string, patch: Partial<AllowedSecurityInput>): void {
  const focusTarget =
    Object.hasOwn(patch, 'sleeve_key') || Object.hasOwn(patch, 'sub_sleeve_key')
      ? visibleRowFocusTarget(rowId)
      : null;
  setRows(
    rows.value.map((row) => ({
      rowId: row.rowId,
      security: row.rowId === rowId ? { ...row.security, ...patch } : { ...row.security },
    })),
  );
  if (focusTarget) {
    void nextTick(() => {
      if (!tableRows.value.some((row) => row.original.rowId === rowId)) focusControl(focusTarget);
    });
  }
}

function setSecurityText(
  rowId: string,
  key: 'ticker' | 'replacement_set_id' | 'exposure_suitability',
  value: string,
): void {
  if (key === 'ticker') updateSecurity(rowId, { ticker: value });
  else if (key === 'replacement_set_id') updateSecurity(rowId, { replacement_set_id: value });
  else updateSecurity(rowId, { exposure_suitability: value });
}

function setSecurityPriority(rowId: string, value: string): void {
  updateSecurity(rowId, { priority: value.trim() ? Number(value) : Number.NaN });
}

function setSecurityParent(rowId: string, optionValue: string): void {
  const row = rows.value.find((candidate) => candidate.rowId === rowId);
  if (!row) return;
  const selected = parentChoices(securityInput(row.security)).find(
    (option) => option.value === optionValue,
  );
  if (selected && selected.domainValue !== null) {
    updateSecurity(rowId, { sleeve_key: selected.domainValue });
  }
}

function setSecuritySubSleeve(rowId: string, optionValue: string): void {
  const row = rows.value.find((candidate) => candidate.rowId === rowId);
  if (!row) return;
  const selected = subSleeveChoices(securityInput(row.security)).find(
    (option) => option.value === optionValue,
  );
  if (selected) updateSecurity(rowId, { sub_sleeve_key: selected.domainValue });
}

function setSecurityEnabled(rowId: string, enabled: boolean): void {
  updateSecurity(rowId, { enabled });
}

function focusControl(id: string): void {
  const target = [...(sectionRoot.value?.querySelectorAll<HTMLElement>('[id]') ?? [])].find(
    (element) => element.id === id,
  );
  target?.focus();
}

function visibleRowFocusTarget(rowId: string): string | null {
  const visibleIds = tableRows.value.map((row) => row.original.rowId);
  const index = visibleIds.indexOf(rowId);
  if (index < 0) return null;
  const focusRowId = visibleIds[index + 1] ?? visibleIds[index - 1];
  return focusRowId ? `${sectionId}-${focusRowId}-remove` : addButtonId;
}

function newSecurityAssignment(): Pick<ReplacementFormSecurity, 'sleeve_key' | 'sub_sleeve_key'> {
  const context = props.context;
  if (!context) return { sleeve_key: '', sub_sleeve_key: null };

  const contextSleeve = sleeves.value.find((sleeve) => sleeve.sleeve_key === context.sleeveKey);
  if (contextSleeve?.parent_sleeve_key) {
    const parent = sleeves.value.find(
      (sleeve) => sleeve.sleeve_key === contextSleeve.parent_sleeve_key,
    );
    if (parent && !parent.parent_sleeve_key)
      return { sleeve_key: parent.sleeve_key, sub_sleeve_key: contextSleeve.sleeve_key };
    return { sleeve_key: '', sub_sleeve_key: null };
  }

  const destination = context.newSubSleeveKey
    ? sleeves.value.find((sleeve) => sleeve.sleeve_key === context.newSubSleeveKey)
    : undefined;
  if (destination?.parent_sleeve_key === context.sleeveKey) {
    return { sleeve_key: context.sleeveKey, sub_sleeve_key: destination.sleeve_key };
  }
  if (context.requireSubSleeve) return { sleeve_key: '', sub_sleeve_key: null };
  return { sleeve_key: context.sleeveKey, sub_sleeve_key: null };
}

async function addSecurity(): Promise<void> {
  const currentSecurities = securitiesFromRows(rows.value);
  const rowId = createRowId();
  const assignment = newSecurityAssignment();
  setRows([
    ...rows.value,
    {
      rowId,
      security: {
        ticker: '',
        ...assignment,
        replacement_set_id: '',
        priority: currentSecurities.length,
        enabled: true,
        exposure_suitability: null,
      },
    },
  ]);
  if (props.context) {
    const pending = new Map(pendingAddedRows.value);
    pending.set(rowId, props.context.sleeveKey);
    pendingAddedRows.value = pending;
  }
  await nextTick();
  focusControl(`${sectionId}-${rowId}-ticker`);
}

function removeSecurity(rowId: string): void {
  const focusTarget = visibleRowFocusTarget(rowId);
  if (!focusTarget) return;
  const pending = new Map(pendingAddedRows.value);
  pending.delete(rowId);
  pendingAddedRows.value = pending;
  setRows(rows.value.filter((row) => row.rowId !== rowId));
  void nextTick(() => focusControl(focusTarget));
}

function siblingTargetIndex(rowId: string, direction: -1 | 1): number | null {
  const index = rows.value.findIndex((row) => row.rowId === rowId);
  const row = rows.value[index];
  if (!row) return null;
  const siblings = rows.value
    .map((candidate, candidateIndex) => ({ candidate, candidateIndex }))
    .filter(
      ({ candidate }) =>
        candidate.security.sleeve_key === row.security.sleeve_key &&
        candidate.security.replacement_set_id === row.security.replacement_set_id &&
        candidate.security.sub_sleeve_key === row.security.sub_sleeve_key,
    );
  const siblingPosition = siblings.findIndex(({ candidate }) => candidate.rowId === rowId);
  return siblings[siblingPosition + direction]?.candidateIndex ?? null;
}

function canMoveSecurity(rowId: string, direction: -1 | 1): boolean {
  return siblingTargetIndex(rowId, direction) !== null;
}

async function moveSecurity(rowId: string, direction: -1 | 1): Promise<void> {
  const targetIndex = siblingTargetIndex(rowId, direction);
  const currentIndex = rows.value.findIndex((row) => row.rowId === rowId);
  if (targetIndex === null || currentIndex < 0) return;
  const nextRows = rows.value.map((row) => ({ rowId: row.rowId, security: { ...row.security } }));
  const current = nextRows[currentIndex];
  const next = nextRows[targetIndex];
  if (!current || !next) return;
  [nextRows[currentIndex], nextRows[targetIndex]] = [next, current];
  const oldPriority = current.security.priority ?? 0;
  current.security.priority = next.security.priority ?? 0;
  next.security.priority = oldPriority;
  setRows(nextRows);
  await nextTick();
  const action = direction < 0 ? 'move-up' : 'move-down';
  const actionId = `${sectionId}-${rowId}-${action}`;
  const actionElement = [...(sectionRoot.value?.querySelectorAll<HTMLElement>('[id]') ?? [])].find(
    (element) => element.id === actionId,
  );
  if (actionElement?.hasAttribute('disabled')) focusControl(`${sectionId}-${rowId}-remove`);
  else actionElement?.focus();
}

function replacementCellProps(
  kind: ReplacementSecurityCellKind,
  row: ReplacementFormRow,
  rowIndex: number,
) {
  const security = securityInput(row.security);
  const parent = kind === 'parentSleeve' ? parentChoices(security) : [];
  const subSleeve = kind === 'subSleeve' ? subSleeveChoices(security) : [];
  const priorityError = priorityErrors.value[row.rowId];
  return {
    kind,
    rowId: row.rowId,
    rowIndex,
    sectionId,
    security,
    parentOptions: parent,
    subSleeveOptions: subSleeve,
    selectedParentValue: selectedOptionValue(parent, security.sleeve_key),
    selectedSubSleeveValue: selectedOptionValue(subSleeve, security.sub_sleeve_key ?? null),
    ...(priorityError ? { priorityError } : {}),
    canMoveUp: kind === 'order' && canMoveSecurity(row.rowId, -1),
    canMoveDown: kind === 'order' && canMoveSecurity(row.rowId, 1),
  };
}

function renderReplacementCell(
  kind: ReplacementSecurityCellKind,
  row: ReplacementFormRow,
  rowIndex: number,
) {
  return h(PolicyReplacementSecurityCell as Component, {
    ...replacementCellProps(kind, row, rowIndex),
    onEditText: setSecurityText,
    onEditPriority: setSecurityPriority,
    onEditParent: setSecurityParent,
    onEditSubSleeve: setSecuritySubSleeve,
    onEditEnabled: setSecurityEnabled,
    onMove: moveSecurity,
    onRemove: removeSecurity,
  });
}

const replacementTableFeatures = tableFeatures({});
const makeColumn = (
  kind: ReplacementSecurityCellKind,
  header: string,
  accessor: (row: ReplacementFormRow) => unknown,
): ColumnDef<typeof replacementTableFeatures, ReplacementFormRow> => ({
  id: kind,
  header,
  accessorFn: accessor,
  cell: ({ row }) => renderReplacementCell(kind, row.original, row.index),
});
const columns: Array<ColumnDef<typeof replacementTableFeatures, ReplacementFormRow>> = [
  makeColumn('order', 'Order', (row) => row.rowId),
  makeColumn('ticker', 'Ticker', (row) => row.security.ticker),
  makeColumn('replacementSetId', 'Replacement set ID', (row) => row.security.replacement_set_id),
  makeColumn('priority', 'Priority', (row) => row.security.priority),
  makeColumn('parentSleeve', 'Parent sleeve', (row) => row.security.sleeve_key),
  makeColumn('subSleeve', 'Sub-sleeve', (row) => row.security.sub_sleeve_key),
  makeColumn(
    'exposureSuitability',
    'Exposure suitability (API note)',
    (row) => row.security.exposure_suitability,
  ),
  makeColumn('enabled', 'Enabled', (row) => row.security.enabled),
  makeColumn('actions', 'Actions', (row) => row.rowId),
];
const tableData = shallowRef(rows.value);
const table = useTable({
  features: replacementTableFeatures,
  columns,
  data: tableData,
  getRowId: (row: ReplacementFormRow) => row.rowId,
});
watch(
  rows,
  (nextRows) => {
    tableData.value = nextRows;
    table.setOptions((previous) => ({ ...previous, data: nextRows }));
  },
  { deep: true, flush: 'sync' },
);
const tableRows = computed(() => {
  if (tableData.value.length === 0) return [];
  return table.getRowModel().rows.filter((row) => {
    const context = props.context;
    if (!context) return true;
    const security = row.original.security;
    return (
      security.sleeve_key === context.sleeveKey ||
      security.sub_sleeve_key === context.sleeveKey ||
      (pendingAddedRows.value.get(row.original.rowId) === context.sleeveKey &&
        !security.sleeve_key &&
        !security.sub_sleeve_key)
    );
  });
});
</script>

<style scoped>
.replacement-editor-root {
  color: var(--foreground);
}

.replacement-editor-root :deep(h2) {
  all: initial;
  display: block;
  color: var(--foreground);
  font-family: inherit;
  font-size: var(--tw-text-lg);
  font-weight: var(--tw-font-weight-semibold);
  letter-spacing: var(--tw-tracking-tight);
  line-height: var(--tw-text-lg--line-height);
}

.replacement-editor-root :deep(p),
.replacement-editor-root :deep(.replacement-editor-description) {
  all: initial;
  display: block;
  color: var(--muted-foreground);
  font-family: inherit;
  font-size: var(--tw-text-sm);
  font-weight: var(--tw-font-weight-normal);
  line-height: var(--tw-text-sm--line-height);
}

.replacement-editor-root :deep(button[data-slot='button']) {
  font-family: inherit;
  text-transform: none;
}

.replacement-editor-root :deep(button[data-slot='select-trigger']) {
  appearance: none;
  border: 1px solid var(--input);
  background-color: transparent;
  color: var(--foreground);
  font-family: inherit;
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
  text-transform: none;
}
</style>
