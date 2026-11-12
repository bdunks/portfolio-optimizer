<template>
  <div v-if="kind === 'order'" class="tw:flex tw:items-center tw:gap-1">
    <span class="tw:sr-only">Candidate order {{ rowIndex + 1 }} controls</span>
    <Button
      :id="controlId('move-up')"
      type="button"
      variant="outline"
      size="icon-sm"
      :aria-label="`Move ${security.ticker || 'candidate'} up`"
      :disabled="!canMoveUp"
      @click="emit('move', rowId, -1)"
    >
      <ArrowUp aria-hidden="true" />
    </Button>
    <Button
      :id="controlId('move-down')"
      type="button"
      variant="outline"
      size="icon-sm"
      :aria-label="`Move ${security.ticker || 'candidate'} down`"
      :disabled="!canMoveDown"
      @click="emit('move', rowId, 1)"
    >
      <ArrowDown aria-hidden="true" />
    </Button>
    <span aria-hidden="true" class="tw:whitespace-nowrap tw:text-muted-foreground">
      {{ rowIndex + 1 }}
    </span>
  </div>

  <FieldGroup v-else-if="kind === 'ticker'" class="tw:min-w-0 tw:gap-1">
    <Field>
      <FieldLabel :for="controlId('ticker')" class="tw:sr-only">ETF ticker</FieldLabel>
      <Input
        :id="controlId('ticker')"
        :model-value="security.ticker"
        placeholder="Ticker"
        @update:model-value="emit('edit-text', rowId, 'ticker', String($event ?? ''))"
      />
    </Field>
  </FieldGroup>

  <FieldGroup v-else-if="kind === 'replacementSetId'" class="tw:min-w-0 tw:gap-1">
    <Field>
      <FieldLabel :for="controlId('replacement-set-id')" class="tw:sr-only">
        Replacement set ID
      </FieldLabel>
      <Input
        :id="controlId('replacement-set-id')"
        :model-value="security.replacement_set_id ?? ''"
        placeholder="Set ID"
        @update:model-value="emit('edit-text', rowId, 'replacement_set_id', String($event ?? ''))"
      />
    </Field>
  </FieldGroup>

  <FieldGroup v-else-if="kind === 'priority'" class="tw:min-w-0 tw:gap-1">
    <Field :data-invalid="priorityError ? 'true' : undefined">
      <FieldLabel :for="controlId('priority')" class="tw:sr-only">Candidate priority</FieldLabel>
      <Input
        :id="controlId('priority')"
        type="number"
        step="1"
        :model-value="security.priority ?? ''"
        :aria-invalid="priorityError ? 'true' : undefined"
        :aria-describedby="priorityError ? controlId('priority-error') : undefined"
        @update:model-value="emit('edit-priority', rowId, String($event ?? ''))"
      />
      <FieldError
        v-if="priorityError"
        :id="controlId('priority-error')"
        :errors="[priorityError]"
      />
    </Field>
  </FieldGroup>

  <FieldGroup v-else-if="kind === 'parentSleeve'" class="tw:min-w-0 tw:gap-1">
    <Field>
      <FieldLabel
        :id="controlId('parent-sleeve-label')"
        :for="controlId('parent-sleeve')"
        class="tw:sr-only"
      >
        Candidate parent sleeve
      </FieldLabel>
      <Select
        :model-value="selectedParentValue"
        @update:model-value="emit('edit-parent', rowId, String($event ?? ''))"
      >
        <SelectTrigger
          :id="controlId('parent-sleeve')"
          :aria-labelledby="controlId('parent-sleeve-label')"
          class="tw:w-full"
        >
          <SelectValue placeholder="Choose sleeve" />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem v-for="option in parentOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
    </Field>
  </FieldGroup>

  <FieldGroup v-else-if="kind === 'subSleeve'" class="tw:min-w-0 tw:gap-1">
    <Field>
      <FieldLabel
        :id="controlId('sub-sleeve-label')"
        :for="controlId('sub-sleeve')"
        class="tw:sr-only"
      >
        Candidate sub-sleeve
      </FieldLabel>
      <Select
        :model-value="selectedSubSleeveValue"
        @update:model-value="emit('edit-sub-sleeve', rowId, String($event ?? ''))"
      >
        <SelectTrigger
          :id="controlId('sub-sleeve')"
          :aria-labelledby="controlId('sub-sleeve-label')"
          class="tw:w-full"
        >
          <SelectValue placeholder="None" />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem
              v-for="option in subSleeveOptions"
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

  <FieldGroup v-else-if="kind === 'exposureSuitability'" class="tw:min-w-0 tw:gap-1">
    <Field>
      <FieldLabel :for="controlId('exposure-suitability')" class="tw:sr-only">
        Exposure suitability note
      </FieldLabel>
      <Input
        :id="controlId('exposure-suitability')"
        :model-value="security.exposure_suitability ?? ''"
        placeholder="Optional API text"
        @update:model-value="emit('edit-text', rowId, 'exposure_suitability', String($event ?? ''))"
      />
    </Field>
  </FieldGroup>

  <FieldGroup v-else-if="kind === 'enabled'" class="tw:min-w-0 tw:gap-1">
    <Field orientation="horizontal" class="tw:items-center tw:gap-2">
      <Checkbox
        :id="controlId('enabled')"
        :model-value="security.enabled ?? false"
        :aria-labelledby="controlId('enabled-label')"
        @update:model-value="emit('edit-enabled', rowId, $event === true)"
      />
      <FieldLabel :id="controlId('enabled-label')" :for="controlId('enabled')">
        {{ security.enabled ? 'Enabled' : 'Disabled' }}
      </FieldLabel>
    </Field>
  </FieldGroup>

  <Button
    v-else
    :id="controlId('remove')"
    type="button"
    variant="destructive"
    size="sm"
    :aria-label="`Remove ${security.ticker || 'ETF candidate'}`"
    @click="emit('remove', rowId)"
  >
    <Trash2 aria-hidden="true" />
    Remove
  </Button>
</template>

<script setup lang="ts">
import { ArrowDown, ArrowUp, Trash2 } from '@lucide/vue';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { AllowedSecurityInput } from '@/types/api';

export type ReplacementSecurityCellKind =
  | 'order'
  | 'ticker'
  | 'replacementSetId'
  | 'priority'
  | 'parentSleeve'
  | 'subSleeve'
  | 'exposureSuitability'
  | 'enabled'
  | 'actions';

export type ReplacementSecuritySelectOption = { value: string; label: string };

const props = defineProps<{
  kind: ReplacementSecurityCellKind;
  rowId: string;
  rowIndex: number;
  sectionId: string;
  security: AllowedSecurityInput;
  parentOptions: readonly ReplacementSecuritySelectOption[];
  subSleeveOptions: readonly ReplacementSecuritySelectOption[];
  selectedParentValue: string;
  selectedSubSleeveValue: string;
  priorityError?: string;
  canMoveUp: boolean;
  canMoveDown: boolean;
}>();

const emit = defineEmits<{
  'edit-text': [
    rowId: string,
    key: 'ticker' | 'replacement_set_id' | 'exposure_suitability',
    value: string,
  ];
  'edit-priority': [rowId: string, value: string];
  'edit-parent': [rowId: string, optionValue: string];
  'edit-sub-sleeve': [rowId: string, optionValue: string];
  'edit-enabled': [rowId: string, value: boolean];
  move: [rowId: string, direction: -1 | 1];
  remove: [rowId: string];
}>();

function controlId(field: string): string {
  return `${props.sectionId}-${props.rowId}-${field}`;
}
</script>
