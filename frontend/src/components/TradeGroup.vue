<template>
  <Collapsible class="group-card tw:min-w-0">
    <Card class="tw:min-w-0 tw:gap-0 tw:overflow-hidden tw:p-0">
      <CardHeader class="tw:p-0">
        <CollapsibleTrigger as-child>
          <Button
            variant="ghost"
            type="button"
            class="group-header tw:flex tw:h-auto tw:w-full tw:flex-col tw:items-stretch tw:justify-start tw:gap-3 tw:rounded-none tw:px-4 tw:py-4 tw:text-left tw:sm:flex-row tw:sm:items-center tw:sm:justify-between tw:sm:px-6"
            :aria-labelledby="`${groupTitleId} ${groupIdentityId}`"
            :aria-describedby="`${groupIntentId} ${groupImpactId}`"
            :data-group-id="group.group_id"
          >
            <div class="tw:flex tw:min-w-0 tw:items-center tw:gap-3">
              <Badge variant="secondary" class="tw:shrink-0 tw:!text-xs tw:!font-semibold">
                Priority {{ group.rank }}
              </Badge>
              <div
                class="group-header-text tw:min-w-0 tw:flex-1 tw:!whitespace-normal tw:break-words"
              >
                <CardTitle
                  :id="groupTitleId"
                  class="group-title tw:!text-sm tw:!font-semibold tw:!text-foreground"
                >
                  {{ groupPurpose }}
                </CardTitle>
                <CardDescription
                  class="group-description tw:mt-1 tw:!text-xs tw:!font-normal tw:!text-muted-foreground"
                >
                  {{ group.group_type }} · {{ sleeveLabel }}
                </CardDescription>
                <p
                  :id="groupIntentId"
                  class="tw:m-0 tw:mt-1 tw:!text-xs tw:!leading-relaxed tw:!text-muted-foreground"
                >
                  {{ collapsedIntent }} · {{ group.rationale }}
                </p>
                <p
                  :id="groupImpactId"
                  class="tw:m-0 tw:mt-1 tw:!text-xs tw:!leading-relaxed tw:!text-muted-foreground"
                >
                  API realized ST / LT:
                  {{
                    formatUsd(group.impact?.realized_st_usd, 'Unavailable (not returned by API)')
                  }}
                  /
                  {{
                    formatUsd(group.impact?.realized_lt_usd, 'Unavailable (not returned by API)')
                  }}
                  ·
                  {{ group.selected ? 'Selected in returned run' : 'Not selected in returned run' }}
                  ·
                  {{
                    group.impact?.selected_sell_lots_count ?? 'Unavailable (not returned by API)'
                  }}
                  sell lots
                </p>
                <span :id="groupIdentityId" class="tw:sr-only">Group ID {{ group.group_id }}</span>
              </div>
            </div>
            <div class="tw:flex tw:flex-wrap tw:items-center tw:gap-2 tw:sm:justify-end">
              <Badge v-if="group.selected" variant="secondary" role="status">
                Selected in returned run
              </Badge>
              <Badge v-if="group.rejected" variant="destructive" role="status">
                Rejected by user
              </Badge>
              <ChevronDown
                aria-hidden="true"
                class="tw:size-4 tw:shrink-0 tw:text-muted-foreground tw:transition-transform"
              />
            </div>
          </Button>
        </CollapsibleTrigger>
      </CardHeader>

      <CollapsibleContent>
        <CardContent class="group-body tw:grid tw:min-w-0 tw:grid-cols-1 tw:gap-4 tw:p-4 tw:sm:p-6">
          <FieldGroup class="tw:gap-2">
            <Field orientation="horizontal" class="tw:items-start tw:gap-3">
              <Checkbox
                :id="selectionId"
                :model-value="group.selected"
                :disabled="pending || !canChangeSelection || group.rejected || !hasSellLots"
                :aria-label="`Select recommendation group ${group.group_id}`"
                @update:model-value="changeGroupSelection($event === true)"
              />
              <FieldLabel
                :for="selectionId"
                class="tw:!text-sm tw:!font-medium tw:!text-foreground"
              >
                {{ group.selected ? 'Selected in returned run' : 'Select this group and re-solve' }}
              </FieldLabel>
            </Field>
          </FieldGroup>

          <dl
            class="group-facts tw:grid tw:min-w-0 tw:grid-cols-1 tw:gap-2 tw:sm:grid-cols-2 tw:xl:grid-cols-3"
          >
            <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
              <dt class="tw:!text-xs tw:!font-medium tw:!text-muted-foreground">Group ID</dt>
              <dd
                class="tw:m-0 tw:mt-1 tw:break-words tw:!text-sm tw:!font-semibold tw:!text-foreground"
              >
                {{ group.group_id }}
              </dd>
            </div>
            <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
              <dt class="tw:!text-xs tw:!font-medium tw:!text-muted-foreground">Priority rank</dt>
              <dd
                class="tw:m-0 tw:mt-1 tw:break-words tw:!text-sm tw:!font-semibold tw:!text-foreground"
              >
                {{ group.rank }}
              </dd>
            </div>
            <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
              <dt class="tw:!text-xs tw:!font-medium tw:!text-muted-foreground">
                Expected benefit
              </dt>
              <dd
                class="tw:m-0 tw:mt-1 tw:break-words tw:!text-sm tw:!font-semibold tw:!text-foreground"
              >
                {{ formatUsd(group.estimated_benefit_usd, 'Unavailable (not returned by API)') }}
              </dd>
            </div>
            <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
              <dt class="tw:!text-xs tw:!font-medium tw:!text-muted-foreground">
                Selected sell-lot count
              </dt>
              <dd
                class="tw:m-0 tw:mt-1 tw:break-words tw:!text-sm tw:!font-semibold tw:!text-foreground"
              >
                {{ group.impact?.selected_sell_lots_count ?? 'Unavailable (not returned by API)' }}
              </dd>
            </div>
            <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
              <dt class="tw:!text-xs tw:!font-medium tw:!text-muted-foreground">
                API sell proceeds
              </dt>
              <dd
                class="tw:m-0 tw:mt-1 tw:break-words tw:!text-sm tw:!font-semibold tw:!text-foreground"
              >
                {{
                  formatUsd(group.impact?.sell_proceeds_usd, 'Unavailable (not returned by API)')
                }}
              </dd>
            </div>
            <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
              <dt class="tw:!text-xs tw:!font-medium tw:!text-muted-foreground">
                API realized ST / LT
              </dt>
              <dd
                class="tw:m-0 tw:mt-1 tw:break-words tw:!text-sm tw:!font-semibold tw:!text-foreground"
              >
                {{ formatUsd(group.impact?.realized_st_usd, 'Unavailable (not returned by API)') }}
                /
                {{ formatUsd(group.impact?.realized_lt_usd, 'Unavailable (not returned by API)') }}
              </dd>
            </div>
            <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
              <dt class="tw:!text-xs tw:!font-medium tw:!text-muted-foreground">
                API replacement BUY shares / cost
              </dt>
              <dd
                class="tw:m-0 tw:mt-1 tw:break-words tw:!text-sm tw:!font-semibold tw:!text-foreground"
              >
                {{ group.impact?.replacement_buy_shares ?? 'Unavailable (not returned by API)' }} /
                {{
                  formatUsd(
                    group.impact?.replacement_buy_cost_usd,
                    'Unavailable (not returned by API)',
                  )
                }}
              </dd>
            </div>
            <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
              <dt class="tw:!text-xs tw:!font-medium tw:!text-muted-foreground">API cash after</dt>
              <dd
                class="tw:m-0 tw:mt-1 tw:break-words tw:!text-sm tw:!font-semibold tw:!text-foreground"
              >
                {{ formatUsd(group.impact?.cash_after_usd, 'Unavailable (not returned by API)') }}
              </dd>
            </div>
            <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
              <dt class="tw:!text-xs tw:!font-medium tw:!text-muted-foreground">
                Risk / tracking score
              </dt>
              <dd
                class="tw:m-0 tw:mt-1 tw:break-words tw:!text-sm tw:!font-semibold tw:!text-foreground"
              >
                {{ group.impact?.risk_tracking_score ?? 'Unavailable (not returned by API)' }}
              </dd>
            </div>
            <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
              <dt class="tw:!text-xs tw:!font-medium tw:!text-muted-foreground">Wash status</dt>
              <dd
                class="tw:m-0 tw:mt-1 tw:break-words tw:!text-sm tw:!font-semibold tw:!text-foreground"
              >
                {{ group.impact?.wash_status ?? 'Unavailable (not returned by API)' }}
              </dd>
            </div>
          </dl>

          <p class="rationale tw:m-0 tw:!text-sm tw:!leading-relaxed tw:!text-muted-foreground">
            <strong class="tw:!font-semibold tw:!text-foreground">Rationale:</strong>
            {{ group.rationale }}
          </p>
          <p
            v-if="group.dependencies.length"
            class="dependency-note tw:m-0 tw:!text-sm tw:!leading-relaxed tw:!text-muted-foreground"
          >
            <strong class="tw:font-semibold">Group dependencies (API IDs):</strong>
            {{ group.dependencies.join(', ') }}. Follow only the API dependency sequence; this is
            not blanket approval.
          </p>
          <ul
            v-if="group.warnings.length"
            class="warning-list tw:m-0 tw:list-disc tw:pl-5 tw:!text-sm tw:!leading-relaxed tw:!text-destructive"
          >
            <li v-for="warning in group.warnings" :key="warning">{{ warning }}</li>
          </ul>

          <section class="tw:grid tw:gap-2" :aria-label="`Linked API legs for ${group.group_id}`">
            <h3 class="tw:m-0 tw:!text-base tw:!font-semibold tw:!text-foreground">
              Linked API legs
            </h3>
            <ul
              v-if="legReferences.length"
              class="leg-reference-list tw:m-0 tw:grid tw:list-disc tw:gap-2 tw:pl-5 tw:!text-sm tw:!text-foreground"
            >
              <li v-for="reference in legReferences" :key="reference.legId">
                <template v-if="reference.status !== 'missing'">
                  <a
                    :href="`#/recommendations#${encodeURIComponent(legAnchor(reference.legId))}`"
                    class="tw:font-medium tw:text-primary tw:underline tw:underline-offset-4"
                  >
                    {{ reference.label }} · {{ reference.legId }}
                  </a>
                  <p
                    v-if="reference.status === 'shared'"
                    class="shared-note tw:m-0 tw:mt-1 tw:!text-xs tw:!leading-relaxed tw:!text-muted-foreground"
                  >
                    Shared consolidated leg; canonical details appear once below the groups.
                  </p>
                  <p
                    v-else-if="reference.status === 'unlinked'"
                    class="warning-text tw:m-0 tw:mt-1 tw:!text-xs tw:!leading-relaxed tw:!text-destructive"
                  >
                    API group references are inconsistent; this leg is not executable.
                  </p>
                </template>
                <p
                  v-else
                  class="warning-text tw:m-0 tw:!text-xs tw:!leading-relaxed tw:!text-destructive"
                >
                  Missing API leg {{ reference.legId }}; this reference is not executable.
                </p>
              </li>
            </ul>
            <p v-else class="empty-inline tw:m-0 tw:!text-sm tw:!text-muted-foreground">
              No linked API legs were returned; this group is not executable.
            </p>
          </section>

          <div
            v-for="leg in legs"
            :key="leg.leg_id"
            class="group-leg-detail tw:grid tw:min-w-0 tw:grid-cols-1 tw:gap-3"
          >
            <RecommendationLegDetails :leg="leg" :id="legAnchor(leg.leg_id)" />
            <SellLotAttribution
              v-if="leg.side === 'SELL'"
              :leg="leg"
              :group-id="group.group_id"
              :can-change-selection="canChangeSelection"
              :pending="pending"
              :rejected="group.rejected"
              @lot-selection="emit('lotSelection', $event)"
            />
          </div>

          <p
            v-if="hasSharedLeg"
            class="shared-note tw:m-0 tw:!text-sm tw:!leading-relaxed tw:!text-muted-foreground"
          >
            Replacement BUYs are consolidated canonical legs and may fund multiple groups. They are
            not independently selectable; any subset or lot change must be re-solved by the API.
          </p>
        </CardContent>

        <CardFooter
          class="annotation-panel tw:flex tw:flex-col tw:items-stretch tw:gap-4 tw:border-t tw:border-border tw:p-4 tw:sm:p-6"
          :aria-label="`Notes and rejection for ${group.group_id}`"
        >
          <form.Field name="note" :validators="{ onChange: tradeGroupNoteSchema }">
            <template #default="{ field }">
              <FieldGroup class="tw:min-w-0 tw:gap-2">
                <Field
                  :data-invalid="
                    field.state.meta.isTouched && field.state.meta.errors.length
                      ? 'true'
                      : undefined
                  "
                  :data-disabled="pending || !canChangeSelection ? 'true' : undefined"
                >
                  <FieldLabel :for="noteId" class="tw:!text-sm tw:!font-medium tw:!text-foreground">
                    Group note (up to 2,000 characters; save an empty value to clear)
                  </FieldLabel>
                  <Textarea
                    :id="noteId"
                    :model-value="noteDraft"
                    rows="2"
                    maxlength="2000"
                    :disabled="pending || !canChangeSelection"
                    :aria-invalid="
                      field.state.meta.isTouched && field.state.meta.errors.length
                        ? 'true'
                        : undefined
                    "
                    :aria-describedby="
                      noteDescriptionIds(field.state.meta.isTouched, field.state.meta.errors.length)
                    "
                    @update:model-value="updateNote($event)"
                    @blur="field.handleBlur"
                  />
                  <FieldDescription :id="noteHintId" class="tw:!text-xs tw:!text-muted-foreground">
                    Notes are optional. Saving a blank note clears the saved value.
                  </FieldDescription>
                  <FieldError
                    v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                    :id="noteErrorId"
                    :errors="field.state.meta.errors"
                  />
                </Field>
              </FieldGroup>
            </template>
          </form.Field>
          <Button
            type="button"
            variant="outline"
            size="sm"
            class="tw:self-start"
            :disabled="pending || !canChangeSelection"
            @click="saveNote"
          >
            Save note
          </Button>

          <form.Field
            v-if="!group.rejected"
            name="rejectionReason"
            :validators="{ onChange: tradeGroupRejectionReasonSchema }"
          >
            <template #default="{ field }">
              <FieldGroup class="tw:min-w-0 tw:gap-2">
                <Field
                  :data-invalid="
                    field.state.meta.isTouched && field.state.meta.errors.length
                      ? 'true'
                      : undefined
                  "
                  :data-disabled="pending || !canChangeSelection ? 'true' : undefined"
                >
                  <FieldLabel
                    :for="rejectionId"
                    class="tw:!text-sm tw:!font-medium tw:!text-foreground"
                  >
                    Rejection reason (up to 500 characters)
                  </FieldLabel>
                  <Input
                    :id="rejectionId"
                    type="text"
                    :model-value="rejectionDraft"
                    maxlength="500"
                    :disabled="pending || !canChangeSelection"
                    :aria-invalid="
                      field.state.meta.isTouched && field.state.meta.errors.length
                        ? 'true'
                        : undefined
                    "
                    :aria-describedby="
                      rejectionDescriptionIds(
                        field.state.meta.isTouched,
                        field.state.meta.errors.length,
                      )
                    "
                    @update:model-value="updateRejection($event)"
                    @blur="field.handleBlur"
                  />
                  <FieldDescription
                    :id="rejectionHintId"
                    class="tw:!text-xs tw:!text-muted-foreground"
                  >
                    The reason must contain non-whitespace text; it is sent exactly as entered.
                  </FieldDescription>
                  <FieldError
                    v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                    :id="rejectionErrorId"
                    :errors="field.state.meta.errors"
                  />
                </Field>
              </FieldGroup>
            </template>
          </form.Field>
          <Button
            v-if="!group.rejected"
            type="button"
            variant="outline"
            size="sm"
            class="tw:self-start"
            :disabled="
              pending ||
              !canChangeSelection ||
              !rejectionDraft.trim() ||
              rejectionDraft.trim().length > 500
            "
            @click="rejectGroup"
          >
            Reject group (does not approve any order)
          </Button>
          <Button
            v-else
            type="button"
            variant="outline"
            size="sm"
            class="tw:self-start"
            :disabled="pending || !canChangeSelection"
            @click="emit('restoreGroup', { groupId: group.group_id })"
          >
            Restore rejected group (remains unselected)
          </Button>

          <p
            class="annotation-help tw:m-0 tw:!text-xs tw:!leading-relaxed tw:!text-muted-foreground"
          >
            Rejection is saved in one backend update; the API response preserves or updates the full
            basket atomically. Restoring leaves the group unselected and keeps its note.
          </p>
          <p
            v-if="group.rejection_reason"
            class="rejection-note tw:m-0 tw:!text-sm tw:!leading-relaxed tw:!text-muted-foreground"
          >
            Saved rejection reason: {{ group.rejection_reason }}
          </p>
        </CardFooter>
      </CollapsibleContent>
    </Card>
  </Collapsible>
</template>

<script setup lang="ts">
import { useForm } from '@tanstack/vue-form';
import { ChevronDown } from '@lucide/vue';
import { computed, useId, watch } from 'vue';
import RecommendationLegDetails from '@/components/RecommendationLegDetails.vue';
import SellLotAttribution from '@/components/SellLotAttribution.vue';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import type {
  GroupActionIntent,
  GroupNoteIntent,
  GroupRejectIntent,
  GroupSelectionIntent,
  GroupTextIntent,
  LotSelectionIntent,
  TradeGroupLegReference,
} from '@/components/trade-review-types';
import type { RecommendationGroupResponse, RecommendationLegResponse } from '@/types/api';
import { formatUsd } from '@/utils/display-values';
import {
  tradeGroupNoteSchema,
  tradeGroupRejectionReasonSchema,
} from '@/forms/trade-group-annotations';

const props = withDefaults(
  defineProps<{
    group: RecommendationGroupResponse;
    legs: RecommendationLegResponse[];
    legReferences: TradeGroupLegReference[];
    sleeveLabel: string;
    hasSellLots: boolean;
    hasSharedLeg: boolean;
    noteDraft: string;
    rejectionDraft: string;
    canChangeSelection: boolean;
    pending?: boolean;
  }>(),
  { pending: false },
);
const emit = defineEmits<{
  groupSelection: [intent: GroupSelectionIntent];
  lotSelection: [intent: LotSelectionIntent];
  noteDraftChange: [intent: GroupTextIntent];
  rejectionDraftChange: [intent: GroupTextIntent];
  saveNote: [intent: GroupNoteIntent];
  rejectGroup: [intent: GroupRejectIntent];
  restoreGroup: [intent: GroupActionIntent];
}>();

const idPrefix = `trade-group-${useId()}`;
const selectionId = `${idPrefix}-selection`;
const groupTitleId = `${idPrefix}-title`;
const groupIntentId = `${idPrefix}-intent`;
const groupImpactId = `${idPrefix}-impact`;
const groupIdentityId = `${idPrefix}-identity`;
const noteId = `${idPrefix}-note`;
const noteHintId = `${idPrefix}-note-hint`;
const noteErrorId = `${idPrefix}-note-error`;
const rejectionId = `${idPrefix}-rejection`;
const rejectionHintId = `${idPrefix}-rejection-hint`;
const rejectionErrorId = `${idPrefix}-rejection-error`;

const groupPurpose = computed(() =>
  props.group.group_type === 'demo_loss_harvest'
    ? 'Tax-loss harvest'
    : `Recommendation · ${String(props.group.group_type)}`,
);
const collapsedIntent = computed(
  () =>
    props.legReferences
      .map((reference) => reference.label.match(/\b(SELL|BUY)\s+([A-Z0-9.-]+)/)?.[0])
      .filter((label): label is string => Boolean(label))
      .join(' · ') || `${props.sleeveLabel} activity`,
);
const form = useForm({
  formId: `${idPrefix}-annotations`,
  defaultValues: {
    note: props.noteDraft,
    rejectionReason: props.rejectionDraft,
  },
});
const annotationValues = form.useSelector((state) => state.values);

watch(
  () => [props.group.group_id, props.noteDraft, props.rejectionDraft] as const,
  ([groupId, note, rejectionReason], [previousGroupId]) => {
    if (
      groupId !== previousGroupId ||
      annotationValues.value.note !== note ||
      annotationValues.value.rejectionReason !== rejectionReason
    ) {
      form.reset({ note, rejectionReason });
    }
  },
  { flush: 'sync' },
);

function changeGroupSelection(selected: boolean): void {
  emit('groupSelection', { groupId: props.group.group_id, selected });
}

function updateNote(value: string | number): void {
  const note = String(value ?? '');
  form.setFieldValue('note', note);
  emit('noteDraftChange', { groupId: props.group.group_id, value: note });
}

async function saveNote(): Promise<void> {
  const errors = await form.validateField('note', 'change');
  if (errors.length) return;
  emit('saveNote', { groupId: props.group.group_id, note: props.noteDraft });
}

function updateRejection(value: string | number): void {
  const reason = String(value ?? '');
  form.setFieldValue('rejectionReason', reason);
  emit('rejectionDraftChange', { groupId: props.group.group_id, value: reason });
}

async function rejectGroup(): Promise<void> {
  const errors = await form.validateField('rejectionReason', 'change');
  if (errors.length) return;
  emit('rejectGroup', { groupId: props.group.group_id, reason: props.rejectionDraft });
}

function noteDescriptionIds(isTouched: boolean, errorCount: number): string {
  return isTouched && errorCount ? `${noteHintId} ${noteErrorId}` : noteHintId;
}

function rejectionDescriptionIds(isTouched: boolean, errorCount: number): string {
  return isTouched && errorCount ? `${rejectionHintId} ${rejectionErrorId}` : rejectionHintId;
}

function legAnchor(legId: string): string {
  return `leg-${encodeURIComponent(legId)}`;
}
</script>
