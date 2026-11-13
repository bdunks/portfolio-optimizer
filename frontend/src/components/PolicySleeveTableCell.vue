<template>
  <div v-if="kind === 'order'" class="tw:flex tw:min-w-max tw:items-center tw:gap-1">
    <div
      class="tw:flex tw:items-center tw:gap-1"
      :style="{ paddingInlineStart: `${hierarchyDepth * 1.25}rem` }"
    >
      <Button
        v-if="hasChildren"
        type="button"
        variant="ghost"
        size="icon-sm"
        :aria-label="`${isExpanded ? 'Collapse' : 'Expand'} children of ${sleeve.display_name || sleeve.sleeve_key}`"
        :aria-expanded="isExpanded"
        @click="emit('toggle-expand', sleeve.sleeve_key)"
      >
        <ChevronRight
          aria-hidden="true"
          class="tw:transition-transform"
          :class="isExpanded ? 'tw:rotate-90' : ''"
        />
      </Button>
      <span v-else aria-hidden="true" class="tw:size-8 tw:shrink-0" />
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
      <div class="tw:flex tw:min-w-0 tw:flex-col tw:gap-0.5">
        <code class="sleeve-key">{{ sleeve.sleeve_key || 'new sleeve' }}</code>
        <span v-if="hierarchyDepth > 0" class="tw:text-xs tw:text-muted-foreground">
          Sub-sleeve
        </span>
      </div>
    </div>
  </div>

  <FieldGroup v-else-if="kind === 'name'" class="tw:min-w-[12rem] tw:gap-1">
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

  <FieldGroup v-else-if="kind === 'target'" class="tw:min-w-0 tw:gap-1">
    <Field>
      <FieldLabel :for="controlId('target')" class="tw:sr-only">{{
        `Target percent ${targetBasis} for ${sleeve.display_name || sleeve.sleeve_key}`
      }}</FieldLabel>
      <Input
        :id="controlId('target')"
        :model-value="sleeve.target_pct"
        :aria-label="`Target percent ${targetBasis} for ${sleeve.display_name || sleeve.sleeve_key}`"
        inputmode="decimal"
        placeholder="0"
        @update:model-value="
          emit('edit-text', sleeve.sleeve_key, 'target_pct', String($event ?? ''))
        "
      />
      <span class="tw:text-xs tw:text-muted-foreground">Percent {{ targetBasis }}</span>
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

  <DropdownMenu v-else>
    <DropdownMenuTrigger as-child>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        :aria-label="`Actions for ${sleeve.display_name || sleeve.sleeve_key}`"
      >
        <MoreHorizontal aria-hidden="true" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end">
      <DropdownMenuItem @select="emit('add-child', sleeve.sleeve_key)">
        <Plus aria-hidden="true" />
        Add sub-sleeve
      </DropdownMenuItem>
      <DropdownMenuItem @select="emit('open-settings', sleeve.sleeve_key)">
        <Settings2 aria-hidden="true" />
        Allocation settings
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem class="tw:text-destructive" @select="emit('delete', sleeve.sleeve_key)">
        <Trash2 aria-hidden="true" />
        Delete allocation
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>

<script setup lang="ts">
import {
  ArrowDown,
  ArrowUp,
  ChevronRight,
  MoreHorizontal,
  Plus,
  Settings2,
  Trash2,
} from '@lucide/vue';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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

export type PolicySleeveColumnKind = 'order' | 'name' | 'target' | 'drift' | 'enabled' | 'actions';

export type PolicySleeveSelectOption = { value: string; label: string };

const props = defineProps<{
  kind: PolicySleeveColumnKind;
  sleeve: EditableSleeve;
  rowIndex: number;
  sectionId: string;
  targetBasis: string;
  hierarchyDepth: number;
  hasChildren: boolean;
  isExpanded: boolean;
  reassignmentOptions: readonly PolicySleeveSelectOption[];
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
  'edit-enabled': [sleeveKey: string, enabled: boolean];
  'edit-reassignment': [sleeveKey: string, optionValue: string];
  move: [sleeveKey: string, direction: -1 | 1];
  delete: [sleeveKey: string];
  'add-child': [parentKey: string];
  'open-settings': [sleeveKey: string];
  'toggle-expand': [sleeveKey: string];
}>();

function controlId(field: string): string {
  return `${props.sectionId}-sleeve-${encodeURIComponent(props.sleeve.sleeve_key)}-${field}`;
}
</script>
