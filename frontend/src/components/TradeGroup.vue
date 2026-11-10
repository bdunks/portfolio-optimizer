<template>
  <q-card class="group-card">
    <q-expansion-item
      header-class="group-header q-gutter-sm text-primary text-weight-bold"
      :aria-label="`Recommendation group ${group.group_id}`"
    >
      <template #header>
        <q-chip dense :clickable="false" color="teal-1" text-color="teal-10" class="q-ma-none">
          Priority {{ group.rank }}
        </q-chip>
        <span>{{ group.group_type }} · {{ sleeveLabel }}</span>
        <q-badge v-if="group.selected" rounded color="teal-1" text-color="teal-10">
          Selected by API
        </q-badge>
        <q-badge v-if="group.rejected" rounded color="red-1" text-color="red-10">
          Rejected by user
        </q-badge>
      </template>

      <div class="group-body q-pt-none q-pb-md q-px-md">
        <q-checkbox
          class="text-caption text-weight-bold text-blue-grey-8"
          dense
          color="primary"
          :model-value="group.selected"
          :disable="pending || !canChangeSelection || group.rejected || !hasSellLots"
          :aria-label="`Select recommendation group ${group.group_id}`"
          :label="
            group.selected ? 'API-confirmed selected group' : 'Select this group and re-solve'
          "
          @update:model-value="changeGroupSelection"
        />

        <dl
          class="group-facts q-mt-md q-mb-none q-mx-none text-caption text-blue-grey-10 text-weight-bold"
        >
          <div class="q-pa-sm">
            <dt>Group ID</dt>
            <dd class="q-mt-xs q-mb-none q-mx-none">{{ group.group_id }}</dd>
          </div>
          <div class="q-pa-sm">
            <dt>Priority rank</dt>
            <dd class="q-mt-xs q-mb-none q-mx-none">{{ group.rank }}</dd>
          </div>
          <div class="q-pa-sm">
            <dt>Expected benefit</dt>
            <dd class="q-mt-xs q-mb-none q-mx-none">
              {{ formatUsd(group.estimated_benefit_usd, 'Unavailable (not returned by API)') }}
            </dd>
          </div>
          <div class="q-pa-sm">
            <dt>Selected sell-lot count</dt>
            <dd class="q-mt-xs q-mb-none q-mx-none">{{ group.impact.selected_sell_lots_count }}</dd>
          </div>
          <div class="q-pa-sm">
            <dt>API sell proceeds</dt>
            <dd class="q-mt-xs q-mb-none q-mx-none">
              {{ formatUsd(group.impact.sell_proceeds_usd) }}
            </dd>
          </div>
          <div class="q-pa-sm">
            <dt>API realized ST / LT</dt>
            <dd class="q-mt-xs q-mb-none q-mx-none">
              {{ formatUsd(group.impact.realized_st_usd) }} /
              {{ formatUsd(group.impact.realized_lt_usd) }}
            </dd>
          </div>
          <div class="q-pa-sm">
            <dt>API replacement BUY shares / cost</dt>
            <dd class="q-mt-xs q-mb-none q-mx-none">
              {{ group.impact.replacement_buy_shares }} /
              {{ formatUsd(group.impact.replacement_buy_cost_usd) }}
            </dd>
          </div>
          <div class="q-pa-sm">
            <dt>API cash after</dt>
            <dd class="q-mt-xs q-mb-none q-mx-none">
              {{ formatUsd(group.impact.cash_after_usd) }}
            </dd>
          </div>
          <div class="q-pa-sm">
            <dt>Risk / tracking score</dt>
            <dd class="q-mt-xs q-mb-none q-mx-none">
              {{ group.impact.risk_tracking_score ?? 'Unavailable (not returned by API)' }}
            </dd>
          </div>
          <div class="q-pa-sm">
            <dt>Wash status</dt>
            <dd class="q-mt-xs q-mb-none q-mx-none">{{ group.impact.wash_status }}</dd>
          </div>
        </dl>

        <p class="rationale q-ma-none"><strong>Rationale:</strong> {{ group.rationale }}</p>
        <p v-if="group.dependencies.length" class="dependency-note q-ma-none">
          <strong>Group dependencies (API IDs):</strong> {{ group.dependencies.join(', ') }}. Follow
          only the API dependency sequence; this is not blanket approval.
        </p>
        <ul v-if="group.warnings.length" class="warning-list q-ma-none q-pl-md">
          <li v-for="warning in group.warnings" :key="warning">{{ warning }}</li>
        </ul>

        <h3 class="q-mt-xs q-mb-none q-mx-none">Linked API legs</h3>
        <ul
          v-if="legReferences.length"
          class="leg-reference-list q-mr-none q-mb-none q-ml-none q-pl-md column no-wrap q-gutter-y-sm"
        >
          <li v-for="reference in legReferences" :key="reference.legId">
            <template v-if="reference.status !== 'missing'">
              <a :href="`#${legAnchor(reference.legId)}`"
                >{{ reference.label }} · {{ reference.legId }}</a
              >
              <span v-if="reference.status === 'shared'" class="shared-note q-ma-none block">
                Shared consolidated leg; canonical details appear once below the groups.
              </span>
              <span v-else-if="reference.status === 'unlinked'" class="warning-text">
                API group references are inconsistent; this leg is not executable.
              </span>
            </template>
            <span v-else class="warning-text">
              Missing API leg {{ reference.legId }}; this reference is not executable.
            </span>
          </li>
        </ul>
        <p v-else class="empty-inline q-ma-none">
          No linked API legs were returned; this group is not executable.
        </p>

        <div
          v-for="leg in legs"
          :key="leg.leg_id"
          class="group-leg-detail column no-wrap q-gutter-y-sm"
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

        <p v-if="hasSharedLeg" class="shared-note q-ma-none">
          Replacement BUYs are consolidated canonical legs and may fund multiple groups. They are
          not independently selectable; any subset or lot change must be re-solved by the API.
        </p>

        <section
          class="annotation-panel row items-end q-gutter-sm q-pt-sm"
          :aria-label="`Notes and rejection for ${group.group_id}`"
        >
          <label
            class="column no-wrap q-gutter-y-xs text-caption text-weight-bold text-blue-grey-8"
          >
            <span>Group note (up to 2,000 characters; save an empty value to clear)</span>
            <q-input
              type="textarea"
              :model-value="noteDraft"
              rows="2"
              maxlength="2000"
              :disable="pending || !canChangeSelection"
              outlined
              dense
              hide-bottom-space
              aria-label="Group note (up to 2,000 characters; save an empty value to clear)"
              @update:model-value="emitText('noteDraftChange', $event)"
            />
          </label>
          <q-btn
            no-caps
            type="button"
            class="text-button"
            flat
            color="primary"
            size="sm"
            :disable="pending || !canChangeSelection"
            @click="emit('saveNote', { groupId: group.group_id, note: noteDraft })"
          >
            Save note
          </q-btn>

          <label
            class="column no-wrap q-gutter-y-xs text-caption text-weight-bold text-blue-grey-8"
            v-if="!group.rejected"
          >
            <span>Rejection reason (up to 500 characters)</span>
            <q-input
              outlined
              dense
              hide-bottom-space
              :model-value="rejectionDraft"
              type="text"
              maxlength="500"
              :disable="pending || !canChangeSelection"
              @update:model-value="emitText('rejectionDraftChange', $event)"
            />
          </label>
          <q-btn
            no-caps
            v-if="!group.rejected"
            type="button"
            class="secondary-button"
            outline
            color="primary"
            size="sm"
            :disable="
              pending ||
              !canChangeSelection ||
              !rejectionDraft.trim() ||
              rejectionDraft.trim().length > 500
            "
            @click="emit('rejectGroup', { groupId: group.group_id, reason: rejectionDraft })"
          >
            Reject group (does not approve any order)
          </q-btn>
          <q-btn
            no-caps
            v-else
            type="button"
            class="secondary-button"
            outline
            color="primary"
            size="sm"
            :disable="pending || !canChangeSelection"
            @click="emit('restoreGroup', { groupId: group.group_id })"
          >
            Restore rejected group (remains unselected)
          </q-btn>
          <p class="annotation-help q-mr-none q-mb-none">
            Rejection is saved in one backend update; the API response preserves or updates the full
            basket atomically. Restoring leaves the group unselected and keeps its note.
          </p>
          <p v-if="group.rejection_reason" class="rejection-note q-mr-none q-mb-none">
            Saved rejection reason: {{ group.rejection_reason }}
          </p>
        </section>
      </div>
    </q-expansion-item>
  </q-card>
</template>

<script setup lang="ts">
import RecommendationLegDetails from '@/components/RecommendationLegDetails.vue';
import SellLotAttribution from '@/components/SellLotAttribution.vue';
import type {
  GroupActionIntent,
  GroupNoteIntent,
  GroupRejectIntent,
  GroupSelectionIntent,
  GroupTextIntent,
  LotSelectionIntent,
} from '@/components/trade-review-types';
import type { RecommendationGroupResponse, RecommendationLegResponse } from '@/types/api';
import { formatUsd } from '@/utils/display-values';
import type { TradeGroupLegReference } from './trade-review-types';

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

function changeGroupSelection(selected: boolean): void {
  emit('groupSelection', { groupId: props.group.group_id, selected });
}

function emitText(
  eventName: 'noteDraftChange' | 'rejectionDraftChange',
  value: Event | string | number | null,
): void {
  const text =
    value instanceof Event
      ? (value.currentTarget as HTMLInputElement | HTMLTextAreaElement).value
      : String(value ?? '');
  const intent: GroupTextIntent = { groupId: props.group.group_id, value: text };
  if (eventName === 'noteDraftChange') emit('noteDraftChange', intent);
  else emit('rejectionDraftChange', intent);
}

function legAnchor(legId: string): string {
  return `leg-${encodeURIComponent(legId)}`;
}

const hasSharedLeg = props.hasSharedLeg;
</script>

<style scoped>
/* Grid gaps use Quasar's spacing scale; negative-margin gutters distort grid tracks. */
.group-card {
  min-width: 0;
}

.group-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  min-width: 0;
  gap: 8px;
}

.group-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px;
}

.group-facts > div {
  min-width: 0;
  border: 1px solid #eaf0f3;
  border-radius: 0.55rem;
}

.group-facts dt {
  color: #647c8b;
  font-size: 0.7rem;
}

.group-facts dd {
  overflow-wrap: anywhere;
}

.rationale,
.dependency-note,
.rejection-note,
.empty-inline,
.shared-note {
  color: #526c7c;
  font-size: 0.78rem;
  line-height: 1.5;
}

.warning-list {
  color: #765016;
  font-size: 0.78rem;
}

.group-body h3 {
  color: #29475a;
  font-size: 0.9rem;
}

.leg-reference-list {
  color: #405f71;
  font-size: 0.78rem;
}

.leg-reference-list a {
  color: #087f7d;
  font-weight: 650;
}

.warning-text {
  color: #812f36;
}

.group-leg-detail {
  min-width: 0;
}

.annotation-panel {
  border-top: 1px solid #eaf0f3;
}

.annotation-panel label:first-child {
  flex: 1 1 18rem;
}

.annotation-panel label:nth-of-type(2) {
  flex: 1 1 14rem;
}

.annotation-help {
  flex: 1 0 100%;
  color: #61798a;
  font-size: 0.72rem;
  line-height: 1.45;
}

@media (max-width: 760px) {
  .group-facts {
    grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
  }
}
</style>
