<template>
  <section
    class="policy-sleeves-editor-root workspace-foundation tw:min-w-0"
    data-workspace-foundation
    data-policy-sleeves-root
    :aria-labelledby="`${sectionId}-title`"
  >
    <Card class="tw:min-w-0">
      <CardHeader>
        <div
          class="tw:flex tw:flex-col tw:gap-4 tw:md:flex-row tw:md:items-start tw:md:justify-between"
        >
          <div class="tw:min-w-0 tw:flex-1">
            <h2 :id="`${sectionId}-title`" class="policy-sleeves-title">
              Sleeves and allocation targets
            </h2>
            <CardDescription class="policy-sleeves-description">
              Top-level targets and every populated nested allocation must total exactly 100%. Drift
              bands use percentage points. No tolerance, implicit cash sleeve, or normalization is
              applied. Transition progress uses an explicitly designated destination sub-sleeve and
              all descendants regardless of security type; it remains unavailable when no
              destination is configured.
            </CardDescription>
          </div>
          <Button type="button" variant="outline" size="sm" @click="addSleeve">
            <Plus aria-hidden="true" />
            Add sleeve
          </Button>
        </div>
      </CardHeader>

      <CardContent class="tw:min-w-0">
        <Alert
          v-if="targetIssues.length"
          role="status"
          aria-live="polite"
          class="tw:mb-4 tw:border-muted-foreground/20 tw:bg-muted/30"
        >
          <AlertTitle>Target check — activation is not valid yet</AlertTitle>
          <AlertDescription>
            <ul class="tw:list-disc tw:pl-5">
              <li v-for="issue in targetIssues" :key="issue">{{ issue }}</li>
            </ul>
            <p class="tw:mt-2">
              These client-side checks are guidance only; the backend response is authoritative.
            </p>
          </AlertDescription>
        </Alert>
        <Alert v-else role="status" class="tw:mb-4 tw:border-primary/30 tw:bg-primary/5">
          <AlertDescription>
            Enabled top-level and nested target sums are exactly 100%.
          </AlertDescription>
        </Alert>

        <Alert
          v-if="deleteError && !pendingDeleteSleeve"
          variant="destructive"
          role="alert"
          class="tw:mb-4"
        >
          <AlertDescription>{{ deleteError }}</AlertDescription>
        </Alert>

        <Table
          role="region"
          aria-label="Sleeve allocation policy settings"
          tabindex="0"
          class="tw:min-w-[88rem]"
        >
          <TableCaption class="tw:sr-only">
            Configured sleeves and their allocation policy settings
          </TableCaption>
          <TableHeader>
            <TableRow v-for="headerGroup in table.getHeaderGroups()" :key="headerGroup.id">
              <TableHead v-for="header in headerGroup.headers" :key="header.id" scope="col">
                <FlexRender v-if="!header.isPlaceholder" :header="header" />
              </TableHead>
            </TableRow>
          </TableHeader>
          <sleeveForm.Field name="sleeves">
            <template #default>
              <TableBody>
                <TableRow v-for="row in tableRows" :key="row.id">
                  <template v-for="cell in row.getAllCells()" :key="cell.id">
                    <TableHead
                      v-if="cell.column.id === 'order'"
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
                <TableEmpty v-if="tableRows.length === 0" :colspan="8">
                  <Empty class="tw:border-0 tw:bg-transparent">
                    <EmptyHeader>
                      <EmptyTitle>No sleeves configured</EmptyTitle>
                      <EmptyDescription>
                        No sleeves configured. Add a sleeve and enter its policy values.
                      </EmptyDescription>
                    </EmptyHeader>
                  </Empty>
                </TableEmpty>
              </TableBody>
            </template>
          </sleeveForm.Field>
        </Table>

        <sleeveForm.Field name="deletion">
          <template #default="{ field }">
            <Card
              v-if="pendingDeleteSleeve"
              role="group"
              class="tw:mt-4 tw:min-w-0"
              :aria-labelledby="`${sectionId}-delete-title`"
            >
              <CardHeader>
                <h3 :id="`${sectionId}-delete-title`" class="policy-sleeves-delete-title">
                  Delete {{ pendingDeleteSleeve.display_name || pendingDeleteSleeve.sleeve_key }}
                </h3>
                <CardDescription>
                  Choose an enabled destination for any holdings currently assigned here.
                  Reassignments are explicit; no holdings are silently orphaned.
                </CardDescription>
              </CardHeader>
              <CardContent class="tw:min-w-0 tw:gap-3">
                <FieldGroup class="tw:gap-3">
                  <Field v-if="heldInSleeve(pendingDeleteSleeve.sleeve_key).length">
                    <FieldLabel
                      :id="`${sectionId}-delete-holdings-label`"
                      :for="`${sectionId}-delete-holdings`"
                    >
                      Holding reassignment destination
                    </FieldLabel>
                    <Select
                      :model-value="
                        selectedOptionValue(
                          deletionTargetOptions,
                          'delete-holdings',
                          field.state.value.targetKey,
                        )
                      "
                      @update:model-value="
                        setDeletionTarget(field.state.value, String($event ?? ''))
                      "
                    >
                      <SelectTrigger
                        :id="`${sectionId}-delete-holdings`"
                        :aria-labelledby="`${sectionId}-delete-holdings-label`"
                        class="tw:w-full"
                      >
                        <SelectValue placeholder="Choose destination" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          <SelectItem
                            v-for="option in deletionTargetOptions"
                            :key="option.value"
                            :value="option.value"
                          >
                            {{ option.label }}
                          </SelectItem>
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                  </Field>

                  <FieldGroup
                    v-for="child in childrenOf(pendingDeleteSleeve.sleeve_key)"
                    :key="child.sleeve_key"
                    class="tw:min-w-0"
                  >
                    <Field>
                      <FieldLabel
                        :id="`${sectionId}-delete-parent-${encodeURIComponent(child.sleeve_key)}-label`"
                        :for="`${sectionId}-delete-parent-${encodeURIComponent(child.sleeve_key)}`"
                      >
                        Move child “{{ child.display_name || child.sleeve_key }}” under
                      </FieldLabel>
                      <Select
                        :model-value="
                          selectedOptionValue(
                            deletionParentOptions(pendingDeleteSleeve.sleeve_key, child.sleeve_key),
                            `delete-parent-${child.sleeve_key}`,
                            field.state.value.childReparents[child.sleeve_key],
                          )
                        "
                        @update:model-value="
                          setDeletionParent(
                            field.state.value,
                            child.sleeve_key,

                            String($event ?? ''),
                          )
                        "
                      >
                        <SelectTrigger
                          :id="`${sectionId}-delete-parent-${encodeURIComponent(child.sleeve_key)}`"
                          :aria-labelledby="`${sectionId}-delete-parent-${encodeURIComponent(child.sleeve_key)}-label`"
                          class="tw:w-full"
                        >
                          <SelectValue placeholder="Choose new parent" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectGroup>
                            <SelectItem
                              v-for="option in deletionParentOptions(
                                pendingDeleteSleeve.sleeve_key,
                                child.sleeve_key,
                              )"
                              :key="option.value"
                              :value="option.value"
                            >
                              {{ option.label }}
                            </SelectItem>
                          </SelectGroup>
                        </SelectContent>
                      </Select>
                    </Field>
                  </FieldGroup>
                </FieldGroup>

                <Alert v-if="deleteError" variant="destructive" role="alert">
                  <AlertDescription>{{ deleteError }}</AlertDescription>
                </Alert>
                <div class="tw:flex tw:flex-wrap tw:items-center tw:gap-2">
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    @click="confirmDeleteSleeve"
                  >
                    <Trash2 aria-hidden="true" />
                    Confirm delete
                  </Button>
                  <Button type="button" variant="ghost" size="sm" @click="cancelDeleteSleeve">
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          </template>
        </sleeveForm.Field>
      </CardContent>
    </Card>
  </section>
</template>

<script setup lang="ts">
import { useForm } from '@tanstack/vue-form';
import { FlexRender, tableFeatures as createTableFeatures, useTable } from '@tanstack/vue-table';
import type { ColumnDef } from '@tanstack/vue-table';
import { Plus, Trash2 } from '@lucide/vue';
import type { Component } from 'vue';
import { computed, h, shallowRef, useId, watch } from 'vue';
import PolicySleeveTableCell from '@/components/PolicySleeveTableCell.vue';
import type { PolicySleeveColumnKind } from '@/components/PolicySleeveTableCell.vue';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
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
import { policySleevesFormSchema } from '@/forms/policy-sleeves';
import type { PolicySleeveFormRow, PolicySleevesFormValues } from '@/forms/policy-sleeves';
import type { EditablePolicyDraft, EditableSleeve } from '@/pages/policy-form';
import type { PositionResponse } from '@/types/api';

const props = defineProps<{
  draft: EditablePolicyDraft;
  positions: readonly PositionResponse[] | null;
  targetIssues: readonly string[];
  sourceRevisionId: string | null;
}>();
const emit = defineEmits<{
  'update:sleeves': [sleeves: EditableSleeve[]];
  'update:reassignments': [
    reassignments: Record<string, string>,
    reassignmentHoldings: Record<string, string[]>,
  ];
}>();

const sectionId = useId();
let nextSleeveNumber = 1;

function copySleeves(sleeves: readonly PolicySleeveFormRow[]): PolicySleeveFormRow[] {
  return sleeves.map((sleeve) => ({ ...sleeve }));
}

function toFormSleeve(sleeve: EditableSleeve, index: number): PolicySleeveFormRow {
  return {
    sleeve_key: sleeve.sleeve_key,
    display_name: sleeve.display_name,
    sort_order: sleeve.sort_order ?? index,
    parent_sleeve_key: sleeve.parent_sleeve_key ?? null,
    target_pct: sleeve.target_pct,
    drift_band_pp: sleeve.drift_band_pp,
    is_direct_index_container: sleeve.is_direct_index_container ?? false,
    is_direct_index_sleeve: sleeve.is_direct_index_sleeve ?? false,
    is_transition_destination: sleeve.is_transition_destination ?? false,
    is_cash_sleeve: sleeve.is_cash_sleeve ?? false,
    enabled: sleeve.enabled ?? true,
  };
}

function toEditableSleeve(sleeve: PolicySleeveFormRow): EditableSleeve {
  return { ...sleeve };
}

function sameSleeves(left: readonly EditableSleeve[], right: readonly EditableSleeve[]): boolean {
  return (
    left.length === right.length &&
    left.every((sleeve, index) => {
      const other = right[index];
      if (!other) return false;
      const keys = new Set([...Object.keys(sleeve), ...Object.keys(other)]);
      return Array.from(keys).every(
        (key) =>
          Object.prototype.hasOwnProperty.call(sleeve, key) ===
            Object.prototype.hasOwnProperty.call(other, key) &&
          Object.is(sleeve[key as keyof EditableSleeve], other[key as keyof EditableSleeve]),
      );
    })
  );
}

const initialFormValues: PolicySleevesFormValues = {
  sleeves: props.draft.sleeves.map(toFormSleeve),
  deletion: { sleeveKey: '', targetKey: '', childReparents: {} },
};
const sleeveForm = useForm({
  defaultValues: initialFormValues,
  validators: { onChange: policySleevesFormSchema },
});
const formValues = sleeveForm.useSelector((state) => state.values);
const sleeves = computed(() => formValues.value.sleeves);
const deletion = computed(() => formValues.value.deletion);
const targetIssues = computed(() => props.targetIssues);
const reassignments = computed(() => props.draft.reassignments);
const enabledSleeves = computed(() => sleeves.value.filter((sleeve) => sleeve.enabled !== false));
const enabledTopLevelSleeves = computed(() =>
  enabledSleeves.value.filter((sleeve) => !sleeve.parent_sleeve_key),
);
const pendingDeleteSleeve = computed(
  () => sleeves.value.find((sleeve) => sleeve.sleeve_key === deletion.value.sleeveKey) ?? null,
);

watch(
  formValues,
  (values) => {
    const nextSleeves = values.sleeves.map(toEditableSleeve);
    if (!sameSleeves(nextSleeves, props.draft.sleeves)) {
      emit('update:sleeves', nextSleeves);
    }
  },
  { deep: true, flush: 'sync' },
);

watch(
  () => props.draft.sleeves,
  (nextSleeves) => {
    if (!sameSleeves(sleeves.value.map(toEditableSleeve), nextSleeves)) {
      sleeveForm.setFieldValue('sleeves', nextSleeves.map(toFormSleeve));
    }
  },
  { deep: true, flush: 'sync' },
);

watch(
  () =>
    `${props.sourceRevisionId ?? ''}:${JSON.stringify(props.draft.sleeves.map((sleeve) => sleeve.sleeve_key))}`,
  cancelDeleteSleeve,
);

function setSleeves(next: PolicySleeveFormRow[]): void {
  sleeveForm.setFieldValue('sleeves', copySleeves(next));
}

function updateSleeve(key: string, patch: Partial<PolicySleeveFormRow>): void {
  if (!sleeves.value.some((sleeve) => sleeve.sleeve_key === key)) return;
  setSleeves(
    sleeves.value.map((sleeve) => (sleeve.sleeve_key === key ? { ...sleeve, ...patch } : sleeve)),
  );
}

function setSleeveText(
  key: string,
  field: 'display_name' | 'target_pct' | 'drift_band_pp',
  value: string,
): void {
  if (field === 'display_name') updateSleeve(key, { display_name: value });
  else if (field === 'target_pct') updateSleeve(key, { target_pct: value });
  else updateSleeve(key, { drift_band_pp: value });
}

type PolicySleeveSelectOption = { value: string; label: string };

function optionToken(kind: string, domainValue: string | null): string {
  return `${sectionId}-${kind}-${domainValue === null ? 'none' : `value-${encodeURIComponent(domainValue)}`}`;
}

function choice(
  kind: string,
  domainValue: string | null,
  label: string,
): PolicySleeveSelectOption & { domainValue: string | null } {
  return { value: optionToken(kind, domainValue), label, domainValue };
}

function selectedOptionValue(
  options: readonly (PolicySleeveSelectOption & { domainValue: string | null })[],
  kind: string,
  domainValue: string | null | undefined,
): string {
  return (
    options.find((option) => option.domainValue === domainValue)?.value ?? optionToken(kind, '')
  );
}

function selectedDomainValue(
  options: readonly (PolicySleeveSelectOption & { domainValue: string | null })[],
  value: string,
): string | null | undefined {
  return options.find((option) => option.value === value)?.domainValue;
}

function parentOptions(sleeve: PolicySleeveFormRow) {
  return [
    choice('parent', null, 'Top level'),
    ...enabledSleeves.value
      .filter(
        (candidate) =>
          candidate.sleeve_key !== sleeve.sleeve_key &&
          !isDescendant(candidate.sleeve_key, sleeve.sleeve_key),
      )
      .map((parent) =>
        choice('parent', parent.sleeve_key, parent.display_name || parent.sleeve_key),
      ),
  ];
}

function reassignmentOptions(excludedKey: string) {
  return [
    choice('reassignment', '', 'Choose destination'),
    ...enabledSleeves.value
      .filter((sleeve) => sleeve.sleeve_key !== excludedKey)
      .map((sleeve) =>
        choice('reassignment', sleeve.sleeve_key, sleeve.display_name || sleeve.sleeve_key),
      ),
  ];
}

function deletionTargetOptionsFor(key: string) {
  return reassignmentOptions(key);
}

const deletionTargetOptions = computed(() =>
  pendingDeleteSleeve.value ? deletionTargetOptionsFor(pendingDeleteSleeve.value.sleeve_key) : [],
);

function deletionParentOptions(deletingKey: string, childKey: string) {
  return [
    choice(`delete-parent-${childKey}`, '', 'Choose new parent'),
    choice(`delete-parent-${childKey}`, null, 'Top level'),
    ...enabledTopLevelSleeves.value
      .filter(
        (sleeve) =>
          sleeve.sleeve_key !== deletingKey &&
          sleeve.sleeve_key !== childKey &&
          !isDescendant(sleeve.sleeve_key, childKey),
      )
      .map((parent) =>
        choice(
          `delete-parent-${childKey}`,
          parent.sleeve_key,
          parent.display_name || parent.sleeve_key,
        ),
      ),
  ];
}

function setSleeveParent(key: string, value: string): void {
  const sleeve = sleeves.value.find((candidate) => candidate.sleeve_key === key);
  if (!sleeve) return;
  const nextParent = selectedDomainValue(parentOptions(sleeve), value);
  if (nextParent !== undefined) updateSleeve(key, { parent_sleeve_key: nextParent });
}

function addSleeve(): void {
  let key: string;
  do {
    key = `sleeve-new-${nextSleeveNumber++}`;
  } while (sleeves.value.some((sleeve) => sleeve.sleeve_key === key));

  setSleeves([
    ...sleeves.value,
    {
      sleeve_key: key,
      display_name: '',
      sort_order: sleeves.value.length,
      parent_sleeve_key: null,
      target_pct: '',
      drift_band_pp: '',
      is_direct_index_container: false,
      is_direct_index_sleeve: false,
      is_transition_destination: false,
      is_cash_sleeve: false,
      enabled: true,
    },
  ]);
}

function hasEnabledChild(key: string): boolean {
  return sleeves.value.some(
    (sleeve) => sleeve.enabled !== false && sleeve.parent_sleeve_key === key,
  );
}

function heldInSleeve(key: string): Array<{ ticker: string }> {
  return (
    props.positions?.filter(
      (position) => position.sleeve_key === key || position.sub_sleeve_key === key,
    ) ?? []
  );
}

function emitReassignments(next: Record<string, string>, holdings: Record<string, string[]>): void {
  emit('update:reassignments', next, holdings);
}

function updateReassignment(sourceKey: string, targetKey: string | null): void {
  const next = { ...reassignments.value };
  const holdings = { ...props.draft.reassignmentHoldings };
  if (targetKey) {
    next[sourceKey] = targetKey;
    holdings[sourceKey] = heldInSleeve(sourceKey).map((position) => position.ticker);
  } else {
    delete next[sourceKey];
    delete holdings[sourceKey];
  }
  emitReassignments(next, holdings);
}

function setReassignment(sourceKey: string, value: string): void {
  const domainValue = selectedDomainValue(reassignmentOptions(sourceKey), value);
  updateReassignment(sourceKey, domainValue || null);
}

const deleteError = shallowRef('');

function setSleeveEnabled(key: string, enabled: boolean): void {
  if (!enabled && hasEnabledChild(key)) {
    deleteError.value = 'Disable or reparent enabled child sleeves before disabling this parent.';
    return;
  }
  updateSleeve(key, { enabled });
  if (enabled) updateReassignment(key, null);
  deleteError.value = '';
}

function setDirectIndexContainer(key: string, enabled: boolean): void {
  setSleeves(
    sleeves.value.map((sleeve) => ({
      ...sleeve,
      is_direct_index_container: sleeve.sleeve_key === key && enabled,
    })),
  );
}

function setSleeveRole(
  key: string,
  role: 'is_direct_index_sleeve' | 'is_cash_sleeve',
  enabled: boolean,
): void {
  updateSleeve(
    key,
    role === 'is_direct_index_sleeve'
      ? { is_direct_index_sleeve: enabled }
      : { is_cash_sleeve: enabled },
  );
}

function setTransitionDestination(key: string, enabled: boolean): void {
  setSleeves(
    sleeves.value.map((sleeve) => ({
      ...sleeve,
      is_transition_destination: sleeve.sleeve_key === key && enabled,
    })),
  );
}

function childrenOf(key: string): PolicySleeveFormRow[] {
  return sleeves.value.filter((sleeve) => sleeve.parent_sleeve_key === key);
}

function isDescendant(candidateKey: string, ancestorKey: string): boolean {
  let current = sleeves.value.find((sleeve) => sleeve.sleeve_key === candidateKey);
  while (current?.parent_sleeve_key) {
    if (current.parent_sleeve_key === ancestorKey) return true;
    current = sleeves.value.find((sleeve) => sleeve.sleeve_key === current?.parent_sleeve_key);
  }
  return false;
}

function sleeveSiblingTargetIndex(index: number, direction: -1 | 1): number | null {
  const sleeve = sleeves.value[index];
  if (!sleeve) return null;
  const siblings = sleeves.value
    .map((candidate, candidateIndex) => ({ candidate, candidateIndex }))
    .filter(({ candidate }) => candidate.parent_sleeve_key === sleeve.parent_sleeve_key);
  const siblingPosition = siblings.findIndex(({ candidateIndex }) => candidateIndex === index);
  return siblings[siblingPosition + direction]?.candidateIndex ?? null;
}

function canMoveSleeve(index: number, direction: -1 | 1): boolean {
  return sleeveSiblingTargetIndex(index, direction) !== null;
}

function moveSleeve(key: string, direction: -1 | 1): void {
  const index = sleeves.value.findIndex((sleeve) => sleeve.sleeve_key === key);
  if (index < 0) return;
  const targetIndex = sleeveSiblingTargetIndex(index, direction);
  if (targetIndex === null) return;
  const next = copySleeves(sleeves.value);
  [next[index], next[targetIndex]] = [next[targetIndex]!, next[index]!];
  setSleeves(next);
}

function beginDeleteSleeve(key: string): void {
  const childReparents: Record<string, string | null> = {};
  for (const child of childrenOf(key)) childReparents[child.sleeve_key] = '';
  sleeveForm.setFieldValue('deletion', { sleeveKey: key, targetKey: '', childReparents });
  deleteError.value = '';
}

function setDeletionTarget(current: PolicySleevesFormValues['deletion'], value: string): void {
  const domainValue = selectedDomainValue(deletionTargetOptions.value, value);
  if (typeof domainValue === 'string') {
    sleeveForm.setFieldValue('deletion', { ...current, targetKey: domainValue });
  }
}

function setDeletionParent(
  current: PolicySleevesFormValues['deletion'],
  childKey: string,
  value: string,
): void {
  const options = pendingDeleteSleeve.value
    ? deletionParentOptions(pendingDeleteSleeve.value.sleeve_key, childKey)
    : [];
  const domainValue = selectedDomainValue(options, value);
  if (domainValue !== undefined) {
    sleeveForm.setFieldValue('deletion', {
      ...current,
      childReparents: { ...current.childReparents, [childKey]: domainValue },
    });
  }
}

function confirmDeleteSleeve(): void {
  const key = deletion.value.sleeveKey;
  if (!key) return;
  const children = childrenOf(key);
  if (children.some((child) => deletion.value.childReparents[child.sleeve_key] === '')) {
    deleteError.value = 'Choose a new parent or top-level placement for every child sleeve.';
    return;
  }
  const holdings = heldInSleeve(key);
  if (holdings.length && !deletion.value.targetKey) {
    deleteError.value =
      'Choose an enabled holding reassignment destination before deleting this sleeve.';
    return;
  }
  updateReassignment(key, holdings.length ? deletion.value.targetKey : null);
  const next = sleeves.value
    .filter((sleeve) => sleeve.sleeve_key !== key)
    .map((sleeve) =>
      sleeve.parent_sleeve_key === key
        ? { ...sleeve, parent_sleeve_key: deletion.value.childReparents[sleeve.sleeve_key] || null }
        : sleeve,
    );
  setSleeves(next);
  sleeveForm.setFieldValue('deletion', { sleeveKey: '', targetKey: '', childReparents: {} });
  deleteError.value = '';
}

function cancelDeleteSleeve(): void {
  sleeveForm.setFieldValue('deletion', { sleeveKey: '', targetKey: '', childReparents: {} });
  deleteError.value = '';
}

function cellProps(kind: PolicySleeveColumnKind, sleeve: PolicySleeveFormRow, rowIndex: number) {
  const parents = kind === 'parent' ? parentOptions(sleeve) : [];
  const reassignments = kind === 'enabled' ? reassignmentOptions(sleeve.sleeve_key) : [];
  return {
    kind,
    sleeve,
    rowIndex,
    sectionId,
    parentOptions: parents,
    reassignmentOptions: reassignments,
    parentValue: selectedOptionValue(parents, 'parent', sleeve.parent_sleeve_key ?? null),
    reassignmentValue: selectedOptionValue(
      reassignments,
      'reassignment',
      props.draft.reassignments[sleeve.sleeve_key] ?? '',
    ),
    canMoveUp: kind === 'order' && canMoveSleeve(rowIndex, -1),
    canMoveDown: kind === 'order' && canMoveSleeve(rowIndex, 1),
  };
}

function renderSleeveCell(
  kind: PolicySleeveColumnKind,
  sleeve: PolicySleeveFormRow,
  rowIndex: number,
) {
  return h(PolicySleeveTableCell as Component, {
    ...cellProps(kind, sleeve, rowIndex),
    onEditText: setSleeveText,
    onEditParent: setSleeveParent,
    onEditContainer: setDirectIndexContainer,
    onEditRole: setSleeveRole,
    onEditTransition: setTransitionDestination,
    onEditEnabled: setSleeveEnabled,
    onEditReassignment: setReassignment,
    onMove: moveSleeve,
    onDelete: beginDeleteSleeve,
  });
}

const sleeveTableFeatures = createTableFeatures({});
const makeColumn = (
  kind: PolicySleeveColumnKind,
  header: string,
  accessor: (sleeve: PolicySleeveFormRow) => unknown,
): ColumnDef<typeof sleeveTableFeatures, PolicySleeveFormRow> => ({
  id: kind,
  header,
  accessorFn: accessor,
  cell: ({ row }) => renderSleeveCell(kind, row.original, row.index),
});
const columns: Array<ColumnDef<typeof sleeveTableFeatures, PolicySleeveFormRow>> = [
  makeColumn('order', 'Order / sleeve key', (sleeve) => sleeve.sleeve_key),
  makeColumn('name', 'Name', (sleeve) => sleeve.display_name),
  makeColumn('parent', 'Parent', (sleeve) => sleeve.parent_sleeve_key),
  makeColumn('target', 'Target (%)', (sleeve) => sleeve.target_pct),
  makeColumn('drift', 'Drift band (pp)', (sleeve) => sleeve.drift_band_pp),
  makeColumn('designations', 'Designations', (sleeve) => sleeve.is_direct_index_container),
  makeColumn('enabled', 'Enabled', (sleeve) => sleeve.enabled),
  makeColumn('actions', 'Actions', (sleeve) => sleeve.sleeve_key),
];
const tableData = shallowRef(sleeves.value);
const table = useTable({
  features: sleeveTableFeatures,
  columns,
  data: tableData,
  getRowId: (sleeve: PolicySleeveFormRow) => sleeve.sleeve_key,
});
watch(
  sleeves,
  (nextSleeves) => {
    tableData.value = nextSleeves;
    table.setOptions((previous) => ({ ...previous, data: nextSleeves }));
  },
  { deep: true, flush: 'sync' },
);
const tableRows = computed(() => (tableData.value.length === 0 ? [] : table.getRowModel().rows));
</script>

<style scoped>
.policy-sleeves-editor-root {
  color: var(--foreground);
}

.policy-sleeves-editor-root :deep(h2),
.policy-sleeves-editor-root :deep(h3) {
  all: initial;
  display: block;
  color: var(--foreground);
  font-family: inherit;
  font-size: var(--tw-text-lg);
  font-weight: var(--tw-font-weight-semibold);
  letter-spacing: var(--tw-tracking-tight);
  line-height: var(--tw-text-lg--line-height);
}

.policy-sleeves-editor-root :deep(p) {
  all: initial;
  display: block;
  color: var(--muted-foreground);
  font-family: inherit;
  font-size: var(--tw-text-sm);
  font-weight: var(--tw-font-weight-normal);
  line-height: var(--tw-text-sm--line-height);
}

.policy-sleeves-editor-root :deep(button[data-slot='button']),
.policy-sleeves-editor-root :deep(button[data-slot='checkbox']) {
  font-family: inherit;
  text-transform: none;
}

.policy-sleeves-editor-root :deep(button[data-slot='select-trigger']) {
  appearance: none;
  border: 1px solid var(--input);
  background-color: transparent;
  color: var(--foreground);
  font-family: inherit;
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
  text-transform: none;
}

.policy-sleeves-editor-root :deep([data-slot='table-container']:focus-visible) {
  outline: 2px solid var(--ring);
  outline-offset: 2px;
}
</style>
