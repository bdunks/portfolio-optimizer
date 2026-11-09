<template>
  <details class="group-card" :aria-label="`Recommendation group ${group.group_id}`">
    <summary>
      <span class="priority-badge">Priority {{ group.rank }}</span>
      <span>{{ group.group_type }} · {{ sleeveLabel }}</span>
      <span v-if="group.selected" class="selected-badge">Selected by API</span>
      <span v-if="group.rejected" class="rejected-badge">Rejected by user</span>
    </summary>

    <div class="group-body">
      <label class="group-selection">
        <input
          type="checkbox"
          :checked="group.selected"
          :disabled="pending || !canChangeSelection || group.rejected || !hasSellLots"
          :aria-label="`Select recommendation group ${group.group_id}`"
          @change="changeGroupSelection"
        />
        <span>{{
          group.selected ? 'API-confirmed selected group' : 'Select this group and re-solve'
        }}</span>
      </label>

      <dl class="group-facts">
        <div>
          <dt>Group ID</dt>
          <dd>{{ group.group_id }}</dd>
        </div>
        <div>
          <dt>Priority rank</dt>
          <dd>{{ group.rank }}</dd>
        </div>
        <div>
          <dt>Expected benefit</dt>
          <dd>{{ formatUsd(group.estimated_benefit_usd, 'Unavailable (not returned by API)') }}</dd>
        </div>
        <div>
          <dt>Selected sell-lot count</dt>
          <dd>{{ group.impact.selected_sell_lots_count }}</dd>
        </div>
        <div>
          <dt>API sell proceeds</dt>
          <dd>{{ formatUsd(group.impact.sell_proceeds_usd) }}</dd>
        </div>
        <div>
          <dt>API realized ST / LT</dt>
          <dd>
            {{ formatUsd(group.impact.realized_st_usd) }} /
            {{ formatUsd(group.impact.realized_lt_usd) }}
          </dd>
        </div>
        <div>
          <dt>API replacement BUY shares / cost</dt>
          <dd>
            {{ group.impact.replacement_buy_shares }} /
            {{ formatUsd(group.impact.replacement_buy_cost_usd) }}
          </dd>
        </div>
        <div>
          <dt>API cash after</dt>
          <dd>{{ formatUsd(group.impact.cash_after_usd) }}</dd>
        </div>
        <div>
          <dt>Risk / tracking score</dt>
          <dd>{{ group.impact.risk_tracking_score ?? 'Unavailable (not returned by API)' }}</dd>
        </div>
        <div>
          <dt>Wash status</dt>
          <dd>{{ group.impact.wash_status }}</dd>
        </div>
      </dl>

      <p class="rationale"><strong>Rationale:</strong> {{ group.rationale }}</p>
      <p v-if="group.dependencies.length" class="dependency-note">
        <strong>Group dependencies (API IDs):</strong> {{ group.dependencies.join(', ') }}. Follow
        only the API dependency sequence; this is not blanket approval.
      </p>
      <ul v-if="group.warnings.length" class="warning-list">
        <li v-for="warning in group.warnings" :key="warning">{{ warning }}</li>
      </ul>

      <h3>Linked API legs</h3>
      <ul v-if="legReferences.length" class="leg-reference-list">
        <li v-for="reference in legReferences" :key="reference.legId">
          <template v-if="reference.status !== 'missing'">
            <a :href="`#${legAnchor(reference.legId)}`"
              >{{ reference.label }} · {{ reference.legId }}</a
            >
            <span v-if="reference.status === 'shared'" class="shared-note">
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
      <p v-else class="empty-inline">
        No linked API legs were returned; this group is not executable.
      </p>

      <div v-for="leg in legs" :key="leg.leg_id" class="group-leg-detail">
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

      <p v-if="hasSharedLeg" class="shared-note">
        Replacement BUYs are consolidated canonical legs and may fund multiple groups. They are not
        independently selectable; any subset or lot change must be re-solved by the API.
      </p>

      <section class="annotation-panel" :aria-label="`Notes and rejection for ${group.group_id}`">
        <label>
          <span>Group note (up to 2,000 characters; save an empty value to clear)</span>
          <textarea
            :value="noteDraft"
            rows="2"
            maxlength="2000"
            :disabled="pending || !canChangeSelection"
            @input="emitText('noteDraftChange', $event)"
          />
        </label>
        <button
          type="button"
          class="text-button"
          :disabled="pending || !canChangeSelection"
          @click="emit('saveNote', { groupId: group.group_id, note: noteDraft })"
        >
          Save note
        </button>

        <label v-if="!group.rejected">
          <span>Rejection reason (up to 500 characters)</span>
          <input
            :value="rejectionDraft"
            type="text"
            maxlength="500"
            :disabled="pending || !canChangeSelection"
            @input="emitText('rejectionDraftChange', $event)"
          />
        </label>
        <button
          v-if="!group.rejected"
          type="button"
          class="secondary-button"
          :disabled="
            pending ||
            !canChangeSelection ||
            !rejectionDraft.trim() ||
            rejectionDraft.trim().length > 500
          "
          @click="emit('rejectGroup', { groupId: group.group_id, reason: rejectionDraft })"
        >
          Reject group (does not approve any order)
        </button>
        <button
          v-else
          type="button"
          class="secondary-button"
          :disabled="pending || !canChangeSelection"
          @click="emit('restoreGroup', { groupId: group.group_id })"
        >
          Restore rejected group (remains unselected)
        </button>
        <p class="annotation-help">
          Rejection is saved in one backend update; the API response preserves or updates the full
          basket atomically. Restoring leaves the group unselected and keeps its note.
        </p>
        <p v-if="group.rejection_reason" class="rejection-note">
          Saved rejection reason: {{ group.rejection_reason }}
        </p>
      </section>
    </div>
  </details>
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

function changeGroupSelection(event: Event): void {
  const input = event.currentTarget as HTMLInputElement;
  const selected = input.checked;
  input.checked = props.group.selected;
  emit('groupSelection', { groupId: props.group.group_id, selected });
}

function emitText(eventName: 'noteDraftChange' | 'rejectionDraftChange', event: Event): void {
  const value = (event.currentTarget as HTMLInputElement | HTMLTextAreaElement).value;
  const intent: GroupTextIntent = { groupId: props.group.group_id, value };
  if (eventName === 'noteDraftChange') emit('noteDraftChange', intent);
  else emit('rejectionDraftChange', intent);
}

function legAnchor(legId: string): string {
  return `leg-${encodeURIComponent(legId)}`;
}

const hasSharedLeg = props.hasSharedLeg;
</script>

<style scoped>
.group-card {
  min-width: 0;
  border: 1px solid #dce6eb;
  border-radius: 0.7rem;
  background: #fff;
}

.group-card > summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.55rem;
  padding: 0.85rem;
  color: #29475a;
  cursor: pointer;
  font-weight: 700;
}

.priority-badge,
.selected-badge,
.rejected-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.25rem 0.55rem;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 800;
  white-space: nowrap;
}

.priority-badge,
.selected-badge {
  background: #e4f5f2;
  color: #086f6e;
}

.rejected-badge {
  background: #fff0f0;
  color: #812f36;
}

.group-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  min-width: 0;
  gap: 0.75rem;
  padding: 0 0.85rem 0.9rem;
}

.group-selection {
  display: inline-flex;
  align-items: center;
  justify-content: start;
  gap: 0.45rem;
}

.group-selection input {
  min-width: auto;
}

.group-selection {
  color: #526c7c;
  font-size: 0.76rem;
  font-weight: 650;
}

.group-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.6rem;
  margin: 0.8rem 0 0;
}

.group-facts > div {
  min-width: 0;
  padding: 0.65rem;
  border: 1px solid #eaf0f3;
  border-radius: 0.55rem;
}

.group-facts dt {
  color: #647c8b;
  font-size: 0.7rem;
}

.group-facts dd {
  margin: 0.25rem 0 0;
  color: #29475a;
  font-size: 0.78rem;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.rationale,
.dependency-note,
.rejection-note,
.empty-inline,
.shared-note {
  margin: 0;
  color: #526c7c;
  font-size: 0.78rem;
  line-height: 1.5;
}

.warning-list {
  margin: 0;
  padding-left: 1.2rem;
  color: #765016;
  font-size: 0.78rem;
}

.group-body h3 {
  margin: 0.2rem 0 0;
  color: #29475a;
  font-size: 0.9rem;
}

.leg-reference-list {
  display: grid;
  gap: 0.4rem;
  margin: 0;
  padding-left: 1.2rem;
  color: #405f71;
  font-size: 0.78rem;
}

.leg-reference-list a {
  color: #087f7d;
  font-weight: 650;
}

.shared-note {
  display: block;
}

.warning-text {
  color: #812f36;
}

.group-leg-detail {
  display: grid;
  gap: 0.5rem;
  min-width: 0;
}

.annotation-panel {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 0.75rem;
  padding-top: 0.7rem;
  border-top: 1px solid #eaf0f3;
}

.annotation-panel label {
  display: grid;
  gap: 0.3rem;
  color: #526c7c;
  font-size: 0.76rem;
  font-weight: 650;
}

.annotation-panel label:first-child {
  flex: 1 1 18rem;
}

.annotation-panel label:nth-of-type(2) {
  flex: 1 1 14rem;
}

.annotation-panel input,
.annotation-panel textarea {
  min-width: 0;
  padding: 0.55rem 0.65rem;
  border: 1px solid #bfd0d8;
  border-radius: 0.45rem;
  background: #fff;
  color: #29475a;
  font: inherit;
}

.annotation-panel textarea {
  resize: vertical;
}

.annotation-panel button {
  padding: 0.58rem 0.82rem;
  border: 1px solid #bfd0d8;
  border-radius: 0.5rem;
  background: #f7fafb;
  color: #24475a;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.annotation-panel button.text-button {
  border: 0;
  background: transparent;
  color: #087f7d;
  text-decoration: underline;
}

.annotation-panel button:disabled,
.annotation-panel input:disabled,
.annotation-panel textarea:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.annotation-help {
  flex: 1 0 100%;
  margin: 0;
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
