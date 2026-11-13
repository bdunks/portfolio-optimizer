<template>
  <section
    ref="settingsRoot"
    class="tw:min-w-0"
    data-us-transition-settings-root
    :aria-labelledby="`${settingsId}-summary-title`"
  >
    <Card>
      <CardHeader
        class="tw:gap-3 tw:md:flex tw:md:flex-row tw:md:items-center tw:md:justify-between"
      >
        <div class="tw:space-y-1">
          <h2
            :id="`${settingsId}-summary-title`"
            class="tw:m-0! tw:text-lg tw:font-semibold tw:leading-tight"
          >
            US Equities Transition Policy
          </h2>
          <CardDescription>
            Explicitly choose the US allocation, existing Legacy holdings, and New holdings. No
            sleeve is inferred from its name, target, holdings, or ETF candidates.
          </CardDescription>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          data-transition-settings-trigger
          @click="openSettings"
        >
          {{
            unsupportedLegacyMapping
              ? 'View preserved mappings'
              : hasExplicitDestination
                ? 'Edit settings'
                : 'Set up US transition'
          }}
        </Button>
      </CardHeader>
    </Card>
    <div
      v-if="unsupportedLegacyMapping"
      role="status"
      class="tw:mt-3 tw:rounded-md tw:border tw:border-amber-600/40 tw:bg-amber-50 tw:p-3 tw:text-sm tw:text-amber-950"
    >
      <p class="tw:m-0!">{{ unsupportedLegacyMapping }}</p>
      <ul class="tw:mb-0 tw:mt-2 tw:list-disc tw:space-y-1 tw:pl-5">
        <li v-for="mapping in preservedRoleMappings" :key="`${mapping.role}-${mapping.key}`">
          {{ mapping.role }}: {{ mapping.name }} ({{ mapping.key }}), target {{ mapping.target }}%
          {{ mapping.parent ? 'within ' + mapping.parent : 'of portfolio' }}.
        </li>
      </ul>
    </div>

    <Sheet v-model:open="settingsOpen">
      <SheetContent
        side="right"
        class="tw:gap-6 tw:overflow-y-auto"
        @close-auto-focus="restoreSettingsFocus"
      >
        <SheetHeader>
          <SheetTitle>US Equities Transition Policy settings</SheetTitle>
          <SheetDescription v-if="unsupportedLegacyMapping">
            Guided editing is unavailable for this custom Legacy routing. Review the exact role
            mappings and targets on the policy card. Custom Legacy role mappings are preserved and
            read-only in guided settings; existing explicit nested targets remain editable in the
            allocation editor.
          </SheetDescription>
          <SheetDescription v-else>
            Choose all three roles explicitly. Legacy is the default direct-index routing branch for
            individual equities and VB/VXF; it must be a direct child of US. New is the explicit
            transition destination and may be any disjoint descendant of US. For an ordinary
            two-child US allocation, guided settings set the two child targets to exact complements.
          </SheetDescription>
        </SheetHeader>

        <div v-if="unsupportedLegacyMapping" class="tw:space-y-4">
          <p role="alert" class="tw:m-0! tw:text-sm tw:text-destructive">
            {{ unsupportedLegacyMapping }}
          </p>
          <ul class="tw:m-0 tw:list-disc tw:space-y-2 tw:pl-5 tw:text-sm">
            <li v-for="mapping in preservedRoleMappings" :key="`${mapping.role}-${mapping.key}`">
              {{ mapping.role }}: {{ mapping.name }} ({{ mapping.key }}), target
              {{ mapping.target }}%
              {{ mapping.parent ? 'within ' + mapping.parent : 'of portfolio' }}.
            </li>
          </ul>
          <div class="tw:flex tw:justify-end">
            <Button type="button" variant="outline" @click="settingsOpen = false">Close</Button>
          </div>
        </div>
        <FieldGroup v-else class="tw:gap-4">
          <Field>
            <FieldLabel :for="controlId('us')">US allocation</FieldLabel>
            <Select
              :model-value="selectedUsKey"
              @update:model-value="selectedUsKey = String($event ?? '')"
            >
              <SelectTrigger :id="controlId('us')" class="tw:w-full">
                <SelectValue placeholder="Choose US allocation" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem
                    v-for="option in usOptions"
                    :key="option.value"
                    :value="option.value"
                    :disabled="option.disabled ?? false"
                  >
                    {{ option.label }}
                  </SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </Field>

          <Field>
            <FieldLabel :for="controlId('legacy')">Legacy holdings</FieldLabel>
            <Select
              :model-value="selectedLegacyKey"
              @update:model-value="selectedLegacyKey = String($event ?? '')"
            >
              <SelectTrigger :id="controlId('legacy')" class="tw:w-full">
                <SelectValue placeholder="Choose Legacy holdings" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem
                    v-for="option in branchOptions('legacy')"
                    :key="option.value"
                    :value="option.value"
                    :disabled="option.disabled ?? false"
                  >
                    {{ option.label }}
                  </SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <p class="tw:m-0! tw:text-xs tw:text-muted-foreground">
              Existing individual equities and VB/VXF resolve here by default, subject to explicit
              holding overrides.
            </p>
          </Field>

          <Field>
            <FieldLabel :for="controlId('destination')">New holdings</FieldLabel>
            <Select
              :model-value="selectedDestinationKey"
              @update:model-value="selectDestination(String($event ?? ''))"
            >
              <SelectTrigger :id="controlId('destination')" class="tw:w-full">
                <SelectValue placeholder="Choose New holdings" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem
                    v-for="option in branchOptions('destination')"
                    :key="option.value"
                    :value="option.value"
                    :disabled="option.disabled ?? false"
                  >
                    {{ option.label }}
                  </SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <p class="tw:m-0! tw:text-xs tw:text-muted-foreground">
              Transition progress is measured only in this explicitly designated subtree.
            </p>
          </Field>

          <Field>
            <FieldLabel :for="controlId('target')">Target in New holdings</FieldLabel>
            <Input
              :id="controlId('target')"
              :model-value="destinationTarget"
              inputmode="decimal"
              :disabled="!ordinaryTwoChild"
              :aria-invalid="attempted && targetIssue ? 'true' : undefined"
              :aria-describedby="
                ordinaryTwoChild ? `${settingsId}-target-help` : `${settingsId}-nested-target-help`
              "
              @update:model-value="destinationTarget = String($event ?? '')"
            />
            <p
              v-if="ordinaryTwoChild"
              :id="`${settingsId}-target-help`"
              class="tw:m-0! tw:text-xs tw:text-muted-foreground"
            >
              Enter an exact percentage from 0 to 100. Apply sets Legacy to the exact 100%
              complement.
            </p>
            <p
              v-else
              :id="`${settingsId}-nested-target-help`"
              class="tw:m-0! tw:text-xs tw:text-muted-foreground"
            >
              This is a custom or nested allocation. Guided settings leave all explicit targets
              unchanged; edit nested targets in the allocation editor.
            </p>
            <p
              v-if="attempted && targetIssue"
              :id="`${settingsId}-target-error`"
              role="alert"
              class="tw:m-0! tw:text-sm tw:text-destructive"
            >
              New holdings target must be an exact decimal from 0 to 100.
            </p>
          </Field>

          <ul
            v-if="attempted && applyResult.issues.length"
            :id="`${settingsId}-mapping-errors`"
            role="alert"
            class="tw:m-0 tw:list-disc tw:space-y-1 tw:pl-5 tw:text-sm tw:text-destructive"
          >
            <li v-for="issue in applyResult.issues" :key="issue">{{ issue }}</li>
          </ul>

          <p class="tw:m-0! tw:text-xs tw:text-muted-foreground">
            These edits stay in the current unsaved policy draft. Save the policy revision
            separately when it is ready.
          </p>

          <div class="tw:flex tw:flex-wrap tw:justify-end tw:gap-2">
            <Button type="button" variant="outline" @click="settingsOpen = false">Cancel</Button>
            <Button type="button" @click="applySettings">Apply settings</Button>
          </div>
        </FieldGroup>
      </SheetContent>
    </Sheet>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, useId } from 'vue';
import {
  applyExplicitUSTransitionSettings,
  isStrictDescendantOf,
  unsupportedLegacyMappingIssue,
} from '@/pages/policy-form';
import type {
  EditablePolicyDraft,
  EditableSleeve,
  USTransitionSelection,
} from '@/pages/policy-form';
import { Button } from '@/components/ui/button';
import { Card, CardDescription, CardHeader } from '@/components/ui/card';
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
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';

type RoleOption = { value: string; label: string; disabled?: boolean };
type BranchRole = 'legacy' | 'destination';

const props = defineProps<{ draft: EditablePolicyDraft }>();
const emit = defineEmits<{ 'update:sleeves': [sleeves: EditableSleeve[]] }>();

const settingsId = useId();
const settingsRoot = ref<HTMLElement | null>(null);
const settingsOpen = ref(false);
const selectedUsKey = ref('');
const selectedLegacyKey = ref('');
const selectedDestinationKey = ref('');
const destinationTarget = ref('');
const attempted = ref(false);

const hasExplicitDestination = computed(() =>
  props.draft.sleeves.some((sleeve) => sleeve.is_transition_destination === true),
);

const unsupportedLegacyMapping = computed(() =>
  unsupportedLegacyMappingIssue(props.draft.sleeves, selectedUsKey.value || undefined),
);
const preservedRoleMappings = computed(() => {
  const roles = [
    { label: 'US allocation', field: 'is_direct_index_container' },
    { label: 'Legacy holdings', field: 'is_direct_index_sleeve' },
    { label: 'New holdings', field: 'is_transition_destination' },
  ] as const;
  return roles.flatMap(({ label, field }) =>
    props.draft.sleeves
      .filter((sleeve) => sleeve[field] === true)
      .map((sleeve) => ({
        role: label,
        name: sleeve.display_name.trim() || sleeve.sleeve_key,
        key: sleeve.sleeve_key,
        parent: sleeve.parent_sleeve_key,
        target: sleeve.target_pct,
      })),
  );
});

const applyResult = computed(() =>
  applyExplicitUSTransitionSettings(props.draft.sleeves, selection.value),
);
const ordinaryTwoChild = computed(() => applyResult.value.ordinaryTwoChild);
const targetIssue = computed(
  () =>
    ordinaryTwoChild.value && applyResult.value.issues.some((issue) => issue.includes('target')),
);
const selection = computed<USTransitionSelection>(() => ({
  usKey: selectedUsKey.value,
  legacyKey: selectedLegacyKey.value,
  destinationKey: selectedDestinationKey.value,
  destinationTarget: destinationTarget.value,
}));

const usOptions = computed<RoleOption[]>(() => {
  const options = props.draft.sleeves
    .filter((sleeve) => sleeve.enabled !== false)
    .map((sleeve) => ({ value: sleeve.sleeve_key, label: sleeveLabel(sleeve) }));
  return appendCurrentOption(options, selectedUsKey.value, 'US allocation');
});

function branchOptions(role: BranchRole): RoleOption[] {
  const selectedKey = role === 'legacy' ? selectedLegacyKey.value : selectedDestinationKey.value;
  const options = props.draft.sleeves
    .filter(
      (sleeve) =>
        sleeve.enabled !== false &&
        !!selectedUsKey.value &&
        (role === 'legacy'
          ? sleeve.parent_sleeve_key === selectedUsKey.value
          : isStrictDescendantOf(props.draft.sleeves, sleeve.sleeve_key, selectedUsKey.value)),
    )
    .map((sleeve) => ({ value: sleeve.sleeve_key, label: sleeveLabel(sleeve) }));
  return appendCurrentOption(options, selectedKey, 'holdings branch', role);
}

function appendCurrentOption(
  options: RoleOption[],
  selectedKey: string,
  roleName: string,
  role?: BranchRole,
): RoleOption[] {
  if (!selectedKey || options.some((option) => option.value === selectedKey)) return options;
  const current = props.draft.sleeves.find((sleeve) => sleeve.sleeve_key === selectedKey);
  if (!current) {
    return [
      ...options,
      {
        value: selectedKey,
        label: `Missing ${roleName} (${selectedKey})`,
        disabled: true,
      },
    ];
  }
  const enabled = current.enabled !== false;
  const isBranchRole = roleName === 'holdings branch';
  const outside =
    isBranchRole && selectedUsKey.value
      ? role === 'legacy'
        ? current.parent_sleeve_key !== selectedUsKey.value
        : !isStrictDescendantOf(props.draft.sleeves, selectedKey, selectedUsKey.value)
      : false;
  const unavailableReason =
    role === 'legacy' ? 'not a direct child of US allocation' : 'outside US allocation';
  const status = enabled ? (outside ? unavailableReason : 'not available') : 'disabled';
  return [
    ...options,
    {
      value: selectedKey,
      label: `${sleeveLabel(current)} (${status})`,
      disabled: !enabled || outside,
    },
  ];
}

function sleeveLabel(sleeve: EditableSleeve): string {
  const name = sleeve.display_name.trim() || sleeve.sleeve_key;
  return name === sleeve.sleeve_key ? name : `${name} · ${sleeve.sleeve_key}`;
}

function explicitRoleKey(
  sleeves: readonly EditableSleeve[],
  role: 'is_direct_index_container' | 'is_direct_index_sleeve' | 'is_transition_destination',
): string {
  const assigned = sleeves.filter((sleeve) => sleeve[role] === true);
  return assigned.length === 1 ? (assigned[0]?.sleeve_key ?? '') : '';
}

function openSettings(): void {
  selectedUsKey.value = explicitRoleKey(props.draft.sleeves, 'is_direct_index_container');
  selectedLegacyKey.value = explicitRoleKey(props.draft.sleeves, 'is_direct_index_sleeve');
  selectedDestinationKey.value = explicitRoleKey(props.draft.sleeves, 'is_transition_destination');
  const destination = props.draft.sleeves.find(
    (sleeve) => sleeve.sleeve_key === selectedDestinationKey.value,
  );
  destinationTarget.value = destination?.target_pct ?? '';
  attempted.value = false;
  settingsOpen.value = true;
}

function selectDestination(key: string): void {
  selectedDestinationKey.value = key;
  destinationTarget.value =
    props.draft.sleeves.find((sleeve) => sleeve.sleeve_key === key)?.target_pct ?? '';
  attempted.value = false;
}

function applySettings(): void {
  attempted.value = true;
  if (applyResult.value.issues.length || !applyResult.value.sleeves) return;
  emit('update:sleeves', applyResult.value.sleeves);
  settingsOpen.value = false;
}

function controlId(field: string): string {
  return `${settingsId}-${field}`;
}

function restoreSettingsFocus(event: Event): void {
  event.preventDefault();
  void nextTick(() => {
    settingsRoot.value
      ?.querySelector<HTMLButtonElement>('button[data-transition-settings-trigger]')
      ?.focus();
  });
}
</script>
