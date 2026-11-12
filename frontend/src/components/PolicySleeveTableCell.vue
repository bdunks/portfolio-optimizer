<template>
  <div v-if="kind === 'order'" class="tw:flex tw:items-center tw:gap-1">
    <span class="tw:sr-only">Sleeve order {{ rowIndex + 1 }} controls</span>
    <Button
      type="button"
      variant="outline"
      size="icon-sm"
      :aria-label="`Move ${sleeve.display_name || sleeve.sleeve_key} up`"
      :disabled="!canMoveUp"
      @click="emit('move', sleeve.sleeve_key, -1)"
    >
      <ArrowUp aria-hidden="true" />
    </Button>
    <Button
      type="button"
      variant="outline"
      size="icon-sm"
      :aria-label="`Move ${sleeve.display_name || sleeve.sleeve_key} down`"
      :disabled="!canMoveDown"
      @click="emit('move', sleeve.sleeve_key, 1)"
    >
      <ArrowDown aria-hidden="true" />
    </Button>
    <span aria-hidden="true" class="tw:whitespace-nowrap tw:text-muted-foreground">
      {{ rowIndex + 1 }}
    </span>
    <code class="sleeve-key">{{ sleeve.sleeve_key || 'new sleeve' }}</code>
  </div>

  <FieldGroup v-else-if="kind === 'name'" class="tw:min-w-0 tw:gap-1">
    <Field>
      <FieldLabel :for="controlId('name')" class="tw:sr-only">{{
        `Sleeve display name for ${sleeve.display_name || sleeve.sleeve_key}`
      }}</FieldLabel>
      <Input
        :id="controlId('name')"
        :model-value="sleeve.display_name"
        :aria-label="`Sleeve display name for ${sleeve.display_name || sleeve.sleeve_key}`"
        placeholder="Display name"
        @update:model-value="
          emit('edit-text', sleeve.sleeve_key, 'display_name', String($event ?? ''))
        "
      />
    </Field>
  </FieldGroup>

  <FieldGroup v-else-if="kind === 'parent'" class="tw:min-w-0 tw:gap-1">
    <Field>
      <FieldLabel :id="controlId('parent-label')" :for="controlId('parent')" class="tw:sr-only">
        {{ `Parent sleeve for ${sleeve.display_name || sleeve.sleeve_key}` }}
      </FieldLabel>
      <Select
        :model-value="parentValue"
        @update:model-value="emit('edit-parent', sleeve.sleeve_key, String($event ?? ''))"
      >
        <SelectTrigger
          :id="controlId('parent')"
          :aria-labelledby="controlId('parent-label')"
          class="tw:w-full"
        >
          <SelectValue placeholder="Choose parent" />
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

  <FieldGroup v-else-if="kind === 'target'" class="tw:min-w-0 tw:gap-1">
    <Field>
      <FieldLabel :for="controlId('target')" class="tw:sr-only">{{
        `Target percent for ${sleeve.display_name || sleeve.sleeve_key}`
      }}</FieldLabel>
      <Input
        :id="controlId('target')"
        :model-value="sleeve.target_pct"
        :aria-label="`Target percent for ${sleeve.display_name || sleeve.sleeve_key}`"
        inputmode="decimal"
        placeholder="0"
        @update:model-value="
          emit('edit-text', sleeve.sleeve_key, 'target_pct', String($event ?? ''))
        "
      />
    </Field>
  </FieldGroup>

  <FieldGroup v-else-if="kind === 'drift'" class="tw:min-w-0 tw:gap-1">
    <Field>
      <FieldLabel :for="controlId('drift')" class="tw:sr-only">
        {{ `Drift band in percentage points for ${sleeve.display_name || sleeve.sleeve_key}` }}
      </FieldLabel>
      <Input
        :id="controlId('drift')"
        :model-value="sleeve.drift_band_pp"
        :aria-label="`Drift band in percentage points for ${sleeve.display_name || sleeve.sleeve_key}`"
        inputmode="decimal"
        placeholder="0"
        @update:model-value="
          emit('edit-text', sleeve.sleeve_key, 'drift_band_pp', String($event ?? ''))
        "
      />
    </Field>
  </FieldGroup>

  <FieldGroup v-else-if="kind === 'designations'" class="tw:min-w-[16rem] tw:gap-2">
    <Field orientation="horizontal" class="tw:items-center tw:gap-2">
      <Checkbox
        :id="controlId('direct-index-container')"
        :model-value="sleeve.is_direct_index_container ?? false"
        :aria-labelledby="controlId('direct-index-container-label')"
        @update:model-value="emit('edit-container', sleeve.sleeve_key, $event === true)"
      />
      <FieldLabel
        :id="controlId('direct-index-container-label')"
        :for="controlId('direct-index-container')"
      >
        {{ `Direct-index container for ${sleeve.display_name || sleeve.sleeve_key}` }}
      </FieldLabel>
    </Field>
    <Field orientation="horizontal" class="tw:items-center tw:gap-2">
      <Checkbox
        :id="controlId('direct-index-sleeve')"
        :model-value="sleeve.is_direct_index_sleeve ?? false"
        :aria-labelledby="controlId('direct-index-sleeve-label')"
        @update:model-value="
          emit('edit-role', sleeve.sleeve_key, 'is_direct_index_sleeve', $event === true)
        "
      />
      <FieldLabel
        :id="controlId('direct-index-sleeve-label')"
        :for="controlId('direct-index-sleeve')"
      >
        {{ `Direct-index sleeve for ${sleeve.display_name || sleeve.sleeve_key}` }}
      </FieldLabel>
    </Field>
    <Field orientation="horizontal" class="tw:items-center tw:gap-2">
      <Checkbox
        :id="controlId('transition-destination')"
        :model-value="sleeve.is_transition_destination ?? false"
        :aria-labelledby="controlId('transition-destination-label')"
        @update:model-value="emit('edit-transition', sleeve.sleeve_key, $event === true)"
      />
      <FieldLabel
        :id="controlId('transition-destination-label')"
        :for="controlId('transition-destination')"
      >
        {{ `Transition destination sub-sleeve for ${sleeve.display_name || sleeve.sleeve_key}` }}
      </FieldLabel>
    </Field>
    <Field orientation="horizontal" class="tw:items-center tw:gap-2">
      <Checkbox
        :id="controlId('cash-sleeve')"
        :model-value="sleeve.is_cash_sleeve ?? false"
        :aria-labelledby="controlId('cash-sleeve-label')"
        @update:model-value="
          emit('edit-role', sleeve.sleeve_key, 'is_cash_sleeve', $event === true)
        "
      />
      <FieldLabel :id="controlId('cash-sleeve-label')" :for="controlId('cash-sleeve')">
        {{ `Cash sleeve for ${sleeve.display_name || sleeve.sleeve_key}` }}
      </FieldLabel>
    </Field>
  </FieldGroup>

  <FieldGroup v-else-if="kind === 'enabled'" class="tw:min-w-[15rem] tw:gap-2">
    <Field orientation="horizontal" class="tw:items-center tw:gap-2">
      <Checkbox
        :id="controlId('enabled')"
        :model-value="sleeve.enabled !== false"
        :aria-labelledby="controlId('enabled-label')"
        @update:model-value="emit('edit-enabled', sleeve.sleeve_key, $event === true)"
      />
      <FieldLabel :id="controlId('enabled-label')" :for="controlId('enabled')">
        {{
          `${sleeve.enabled !== false ? 'Enabled' : 'Disabled'} ${sleeve.display_name || sleeve.sleeve_key}`
        }}
      </FieldLabel>
    </Field>
    <Field v-if="sleeve.enabled === false">
      <span>Reassign held assets to</span>
      <FieldLabel
        :id="controlId('reassignment-label')"
        :for="controlId('reassignment')"
        class="tw:sr-only"
      >
        {{ `Reassign holdings from ${sleeve.display_name || sleeve.sleeve_key}` }}
      </FieldLabel>
      <Select
        :model-value="reassignmentValue"
        @update:model-value="emit('edit-reassignment', sleeve.sleeve_key, String($event ?? ''))"
      >
        <SelectTrigger
          :id="controlId('reassignment')"
          :aria-labelledby="controlId('reassignment-label')"
          class="tw:w-full"
        >
          <SelectValue placeholder="Choose destination" />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem
              v-for="option in reassignmentOptions"
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

  <Button
    v-else
    type="button"
    variant="destructive"
    size="sm"
    :aria-label="`Delete ${sleeve.display_name || sleeve.sleeve_key}`"
    @click="emit('delete', sleeve.sleeve_key)"
  >
    <Trash2 aria-hidden="true" />
    Delete
  </Button>
</template>

<script setup lang="ts">
import { ArrowDown, ArrowUp, Trash2 } from '@lucide/vue';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { EditableSleeve } from '@/pages/policy-form';

export type PolicySleeveColumnKind =
  'order' | 'name' | 'parent' | 'target' | 'drift' | 'designations' | 'enabled' | 'actions';

export type PolicySleeveSelectOption = { value: string; label: string };

const props = defineProps<{
  kind: PolicySleeveColumnKind;
  sleeve: EditableSleeve;
  rowIndex: number;
  sectionId: string;
  parentOptions: readonly PolicySleeveSelectOption[];
  reassignmentOptions: readonly PolicySleeveSelectOption[];
  parentValue: string;
  reassignmentValue: string;
  canMoveUp: boolean;
  canMoveDown: boolean;
}>();

const emit = defineEmits<{
  'edit-text': [
    sleeveKey: string,
    field: 'display_name' | 'target_pct' | 'drift_band_pp',
    value: string,
  ];
  'edit-parent': [sleeveKey: string, optionValue: string];
  'edit-container': [sleeveKey: string, enabled: boolean];
  'edit-role': [
    sleeveKey: string,
    role: 'is_direct_index_sleeve' | 'is_cash_sleeve',
    enabled: boolean,
  ];
  'edit-transition': [sleeveKey: string, enabled: boolean];
  'edit-enabled': [sleeveKey: string, enabled: boolean];
  'edit-reassignment': [sleeveKey: string, optionValue: string];
  move: [sleeveKey: string, direction: -1 | 1];
  delete: [sleeveKey: string];
}>();

function controlId(field: string): string {
  return `${props.sectionId}-sleeve-${encodeURIComponent(props.sleeve.sleeve_key)}-${field}`;
}
</script>
