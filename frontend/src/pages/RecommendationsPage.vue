<template>
  <section class="workspace-page recommendations-page" aria-labelledby="recommendations-title">
    <header class="page-header">
      <div>
        <p class="eyebrow">Small-batch review</p>
        <h1 id="recommendations-title">Recommendations</h1>
        <p class="page-subtitle">
          Review ranked groups and API-proposed legs. Group or sell-lot selection requests a backend
          re-solve; selection is never an order approval.
        </p>
      </div>
      <button
        type="button"
        class="primary-button"
        :disabled="!canRunOptimizer"
        @click="runOptimizer"
      >
        {{ store.actionState.runOptimizer.pending ? 'Running DEMO…' : 'Run DEMO recommendations' }}
      </button>
    </header>

    <p class="demo-notice" role="status">
      <strong>DEMO ONLY · non-actionable.</strong> API demo values are hypothetical. No E*TRADE
      connection, OAuth, order preview, approval, or submission controls exist on this screen.
    </p>

    <section class="run-controls" aria-label="Recommendation run controls">
      <p v-if="!canRunOptimizer" class="state-message">
        A new run requires a ready synchronized portfolio, healthy local API, and valid active
        policy. Nothing runs automatically.
      </p>
      <form class="saved-run-form" @submit.prevent="openSavedRun">
        <label>
          <span>Open saved run ID</span>
          <input
            v-model.trim="savedRunId"
            type="text"
            autocomplete="off"
            placeholder="Run ID from Activity"
          />
        </label>
        <button
          type="submit"
          class="secondary-button"
          :disabled="!savedRunId || store.actionState.openSavedRun.pending || mutationBusy"
        >
          {{ store.actionState.openSavedRun.pending ? 'Opening saved run…' : 'Open frozen run' }}
        </button>
      </form>
    </section>

    <div class="error-stack" aria-label="Recommendation request errors">
      <ApiActionError
        :error="store.actionState.loadHealth.error"
        title="Local API health could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.loadPortfolio.error"
        title="Portfolio snapshot could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.loadPolicy.error"
        title="Active policy could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.runOptimizer.error"
        title="Recommendation run failed"
      />
      <ApiActionError
        :error="store.actionState.openSavedRun.error"
        title="Saved run could not be opened"
      />
      <ApiActionError
        :error="store.actionState.recalculateSelection.error"
        title="Selection re-solve failed; the last successful API selection remains in view"
      />
      <ApiActionError
        :error="store.actionState.annotateGroup.error"
        title="Group note or rejection was not saved"
      />
      <ApiActionError
        :error="store.actionState.exportRun.error"
        title="Recommendation export failed"
      />
    </div>

    <p
      v-if="store.currentRunView"
      class="provenance-banner"
      :data-view="store.currentRunView"
      role="status"
    >
      <strong>{{ provenanceLabel }}</strong>
      <span>Run {{ currentRun?.run_id ?? 'Unavailable' }}</span>
      <span>Policy {{ currentRun?.policy_revision_id ?? 'Unavailable' }}</span>
      <span>Source generation {{ currentRun?.source_generation ?? 'Unavailable' }}</span>
      <span>As of {{ currentRun?.as_of ?? 'Unavailable' }}</span>
    </p>

    <p v-if="mutationBusy" class="pending-banner" role="status">
      The requested selection or annotation is being saved/re-solved. Previous basket effects are
      withheld until the API responds; no unconfirmed selection is shown as active.
    </p>

    <section v-if="!currentRun" class="empty-state" aria-live="polite">
      <template
        v-if="store.actionState.runOptimizer.pending || store.actionState.openSavedRun.pending"
      >
        <h2>Loading recommendations</h2>
        <p>The local API is preparing or reopening a run.</p>
      </template>
      <template v-else>
        <h2>No recommendation run loaded</h2>
        <p>
          Run a DEMO analysis from Overview or this page, or reopen a saved run by its API run ID.
        </p>
        <p v-if="store.actionState.runOptimizer.error || store.actionState.openSavedRun.error">
          The request failed. Retry only after reviewing the API error above.
        </p>
      </template>
    </section>

    <template v-else>
      <section v-if="!mutationBusy" class="run-summary" aria-label="Run status and provenance">
        <div class="run-title-row">
          <div>
            <h2>{{ currentRun.solver_version }} recommendations · {{ currentRun.status }}</h2>
            <p>
              {{ currentRun.demo ? 'DEMO hypothetical data' : 'API run' }} ·
              {{
                currentRun.actionable
                  ? 'API marks this run actionable'
                  : 'API marks this run non-actionable'
              }}
            </p>
          </div>
          <span class="demo-badge">{{
            currentRun.actionable ? 'No order controls' : 'NON-ACTIONABLE'
          }}</span>
        </div>
        <p v-if="currentRun.solver_version === 'DEMO'" class="warning-banner">
          DEMO solver output is not a real optimizer feasibility result. Treat every value as
          hypothetical and non-executable.
        </p>
        <p
          v-if="currentRun.estimated_tax_benefit_status === 'optimizer_unavailable'"
          class="warning-banner"
        >
          The real optimizer is unavailable. No production optimization or feasibility claim is
          made.
        </p>
        <dl class="metric-grid">
          <div>
            <dt>Estimated tax benefit</dt>
            <dd>{{ displayUsd(currentRun.estimated_tax_benefit_usd) }}</dd>
            <small>{{ currentRun.estimated_tax_benefit_status }}</small>
          </div>
          <div>
            <dt>Estimated realized ST</dt>
            <dd>{{ displayUsd(currentRun.estimated_realized_st_usd) }}</dd>
          </div>
          <div>
            <dt>Estimated realized LT</dt>
            <dd>{{ displayUsd(currentRun.estimated_realized_lt_usd) }}</dd>
          </div>
          <div>
            <dt>Cash before / after</dt>
            <dd>
              {{ displayUsd(currentRun.cash_before_usd) }} /
              {{ displayUsd(currentRun.cash_after_usd) }}
            </dd>
          </div>
          <div>
            <dt>Risk tracking</dt>
            <dd>Unavailable (not returned by API)</dd>
            <small>Not returned as a run-level risk score</small>
          </div>
          <div>
            <dt>Hard constraints</dt>
            <dd>
              {{
                currentRun.constraints_satisfied == null
                  ? 'Unavailable (not evaluated)'
                  : currentRun.constraints_satisfied
                    ? 'Satisfied'
                    : 'Not satisfied'
              }}
            </dd>
          </div>
          <div>
            <dt>API-reported sell lots / exited positions / orders</dt>
            <dd>
              {{ currentRun.lots_sold_count }} / {{ currentRun.positions_exited_count }} /
              {{ currentRun.orders_count }}
            </dd>
          </div>
          <div>
            <dt>Tax profile</dt>
            <dd>{{ currentRun.tax_profile_configured ? 'Configured' : 'Incomplete' }}</dd>
          </div>
        </dl>
        <p v-if="currentRun.no_trade_reason != null" class="no-trade-reason">
          <strong>No beneficial trades identified / API no-trade reason:</strong>
          {{ displayJson(currentRun.no_trade_reason) }}
        </p>
        <p v-else-if="currentRun.groups.length === 0" class="no-trade-reason">
          No beneficial trades identified. The API returned no recommendation groups.
        </p>
        <ul v-if="currentRun.warnings.length" class="warning-list" aria-label="Run warnings">
          <li v-for="warning in currentRun.warnings" :key="warning">{{ warning }}</li>
        </ul>
        <details class="provenance-details">
          <summary>Frozen API batch settings and provenance</summary>
          <pre>{{ displayJson(currentRun.batch_settings) }}</pre>
          <p>Input fingerprint: {{ currentRun.input_fingerprint ?? 'Unavailable' }}</p>
          <p>Source checksum: {{ currentRun.source_checksum ?? 'Unavailable' }}</p>
          <p v-if="savedRunSummary">
            Saved summary status: {{ savedRunSummary.status }} · {{ savedRunSummary.mode }}
          </p>
        </details>
      </section>

      <section v-if="!mutationBusy" class="effects-panel" aria-labelledby="effects-title">
        <header class="section-heading">
          <div>
            <h2 id="effects-title">API allocation effects</h2>
            <p>{{ effectsDescription }}</p>
          </div>
        </header>
        <AllocationTargets
          :allocation="effectAllocation"
          :labels="sleeveLabels"
          :show-no-current-basket="showNoCurrentBasket"
        />
        <USAllocationTransition
          :transition="effectTransition"
          :labels="sleeveLabels"
          :show-no-current-basket="showNoCurrentBasket"
        />
      </section>

      <section
        v-if="currentRun.groups.length && !mutationBusy"
        class="review-panel"
        aria-labelledby="groups-title"
      >
        <header class="section-heading">
          <div>
            <h2 id="groups-title">Ranked trade groups</h2>
            <p>
              Priority rank is the API rank, not a precision score. Execution sequence and
              dependencies are shown separately.
            </p>
          </div>
          <span>{{ filteredGroups.length }} shown / {{ currentRun.groups.length }} returned</span>
        </header>

        <form class="filter-panel" @submit.prevent>
          <label>
            <span>Sleeve</span>
            <select v-model="filters.sleeve">
              <option value="">All sleeves</option>
              <option v-for="sleeve in sleeveOptions" :key="sleeve" :value="sleeve">
                {{ sleeveLabel(sleeve) }}
              </option>
            </select>
          </label>
          <label>
            <span>Action</span>
            <select v-model="filters.action">
              <option value="">Any action</option>
              <option value="SELL">SELL</option>
              <option value="BUY">BUY</option>
            </select>
          </label>
          <label>
            <span>Tax term</span>
            <select v-model="filters.term">
              <option value="">Any term</option>
              <option value="ST">Short term</option>
              <option value="LT">Long term</option>
            </select>
          </label>
          <label>
            <span>Expected benefit</span>
            <select v-model="filters.benefit">
              <option value="">Any</option>
              <option value="unavailable">Unavailable in API</option>
            </select>
          </label>
          <label>
            <span>Warnings</span>
            <select v-model="filters.warning">
              <option value="">Any</option>
              <option value="with">With warnings</option>
              <option value="without">No warnings returned</option>
            </select>
          </label>
          <label>
            <span>Group type</span>
            <select v-model="filters.groupType">
              <option value="">Any type</option>
              <option v-for="type in groupTypeOptions" :key="type" :value="type">{{ type }}</option>
            </select>
          </label>
          <label>
            <span>Sort by API priority rank</span>
            <select v-model="sortOrder">
              <option value="rank-ascending">Highest priority first (ascending rank)</option>
              <option value="rank-descending">Lowest priority first (descending rank)</option>
            </select>
          </label>
        </form>

        <fieldset class="selection-tools" :disabled="!canChangeSelection">
          <legend>Re-solve selected basket</legend>
          <label class="top-n-control">
            <span>Top N groups by API rank</span>
            <input v-model.number="topN" type="number" min="1" :max="currentRun.groups.length" />
          </label>
          <button type="button" class="secondary-button" @click="selectTopGroups">
            Select top N and re-solve
          </button>
          <button type="button" class="secondary-button" @click="clearSelection">
            Clear selected groups and re-solve
          </button>
          <span v-if="!canChangeSelection" class="read-only-note">
            Saved, stale, or unverified run context is read-only. Open/run a current matching run to
            change selection.
          </span>
          <span v-else class="read-only-note">
            Group selection and individual SELL-lot selection re-solve through the API. Shared BUY
            legs cannot be toggled independently.
          </span>
        </fieldset>

        <p v-if="filteredGroups.length === 0" class="empty-inline">
          No returned groups match these filters.
        </p>
        <div v-else class="group-list">
          <details v-for="group in filteredGroups" :key="group.group_id" class="group-card">
            <summary>
              <span class="priority-badge">Priority {{ group.rank }}</span>
              <span>{{ group.group_type }} · {{ sleeveLabel(group.sleeve_key) }}</span>
              <span v-if="group.selected" class="selected-badge">Selected by API</span>
              <span v-if="group.rejected" class="rejected-badge">Rejected by user</span>
            </summary>
            <div class="group-body">
              <label class="group-selection">
                <input
                  type="checkbox"
                  :checked="group.selected"
                  :disabled="
                    !canChangeSelection || group.rejected || groupSellLotIdsFor(group).length === 0
                  "
                  :aria-label="`Select recommendation group ${group.group_id}`"
                  @change="changeGroupSelection(group, $event)"
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
                  <dd>{{ displayUsd(group.estimated_benefit_usd) }}</dd>
                </div>
                <div>
                  <dt>Selected sell-lot count</dt>
                  <dd>{{ group.impact.selected_sell_lots_count }}</dd>
                </div>
                <div>
                  <dt>API sell proceeds</dt>
                  <dd>{{ displayUsd(group.impact.sell_proceeds_usd) }}</dd>
                </div>
                <div>
                  <dt>API realized ST / LT</dt>
                  <dd>
                    {{ displayUsd(group.impact.realized_st_usd) }} /
                    {{ displayUsd(group.impact.realized_lt_usd) }}
                  </dd>
                </div>
                <div>
                  <dt>API replacement BUY shares / cost</dt>
                  <dd>
                    {{ group.impact.replacement_buy_shares }} /
                    {{ displayUsd(group.impact.replacement_buy_cost_usd) }}
                  </dd>
                </div>
                <div>
                  <dt>API cash after</dt>
                  <dd>{{ displayUsd(group.impact.cash_after_usd) }}</dd>
                </div>
                <div>
                  <dt>Risk / tracking score</dt>
                  <dd>
                    {{
                      group.impact.risk_tracking_score == null
                        ? 'Unavailable (not returned by API)'
                        : group.impact.risk_tracking_score
                    }}
                  </dd>
                </div>
                <div>
                  <dt>Wash status</dt>
                  <dd>{{ group.impact.wash_status }}</dd>
                </div>
              </dl>
              <p class="rationale"><strong>Rationale:</strong> {{ group.rationale }}</p>
              <p v-if="group.dependencies.length" class="dependency-note">
                <strong>Group dependencies (API IDs):</strong> {{ group.dependencies.join(', ') }}.
                Follow only the API dependency sequence; this is not blanket approval.
              </p>
              <ul v-if="group.warnings.length" class="warning-list">
                <li v-for="warning in group.warnings" :key="warning">{{ warning }}</li>
              </ul>

              <h3>Linked API legs</h3>
              <ul v-if="group.leg_ids.length" class="leg-reference-list">
                <li v-for="legId in group.leg_ids" :key="legId">
                  <template v-if="findLeg(legId)">
                    <a :href="`#${legAnchor(legId)}`">{{ legLabel(group, legId) }} · {{ legId }}</a>
                    <span v-if="isSharedLeg(legId)" class="shared-note">
                      Shared consolidated leg; details appear once below.
                    </span>
                    <span v-else-if="isUnlinkedLeg(legId)" class="warning-text">
                      API group references are inconsistent; this leg is not executable.
                    </span>
                  </template>
                  <span v-else class="warning-text">
                    Missing API leg {{ legId }}; this reference is not executable.
                  </span>
                </li>
              </ul>
              <p v-else class="empty-inline">
                No linked API legs were returned; this group is not executable.
              </p>

              <div
                v-for="leg in groupDetailLegs(group)"
                :id="legAnchor(leg.leg_id)"
                :key="leg.leg_id"
                class="leg-card"
              >
                <LegDetails :leg="leg" />
                <div v-if="leg.side === 'SELL'" class="lot-table-wrap">
                  <table>
                    <caption>
                      SELL broker-lot attribution from the API ·
                      {{
                        leg.ticker ?? 'ticker unavailable'
                      }}
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Review selection</th>
                        <th scope="col">Broker lot ID</th>
                        <th scope="col">Acquired</th>
                        <th scope="col">API shares</th>
                        <th scope="col">Adjusted basis (API value)</th>
                        <th scope="col">Estimated price</th>
                        <th scope="col">Term</th>
                        <th scope="col">Realized P/L</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="lot in leg.selected_lots" :key="lot.broker_lot_id">
                        <td>
                          <label class="lot-selection">
                            <input
                              type="checkbox"
                              :checked="lot.selected"
                              :disabled="!canChangeSelection || group.rejected"
                              :aria-label="`Select SELL lot ${lot.broker_lot_id} in group ${group.group_id}`"
                              @change="changeLotSelection(group, lot.broker_lot_id, $event)"
                            />
                            {{ lot.selected ? 'API selected' : 'Not selected' }}
                          </label>
                        </td>
                        <th scope="row">{{ lot.broker_lot_id }}</th>
                        <td>{{ lot.acquired_date }}</td>
                        <td>{{ lot.shares }}</td>
                        <td>{{ displayUsd(lot.adjusted_basis_usd) }}</td>
                        <td>{{ displayUsd(leg.estimated_unit_price_usd) }}</td>
                        <td>{{ lot.st_lt }}</td>
                        <td>{{ displayUsd(lot.realized_pl_usd) }}</td>
                      </tr>
                      <tr v-if="leg.selected_lots.length === 0">
                        <td colspan="8">No broker-lot rows were returned for this SELL leg.</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <p v-if="group.leg_ids.some(isSharedLeg)" class="shared-note">
                Replacement BUYs are consolidated canonical legs and may fund multiple groups. They
                are not independently selectable; any subset/lot change must be re-solved by the
                API.
              </p>
              <section
                class="annotation-panel"
                :aria-label="`Notes and rejection for ${group.group_id}`"
              >
                <label>
                  <span>Group note (saved through API)</span>
                  <textarea
                    v-model="noteDrafts[group.group_id]"
                    rows="2"
                    :disabled="!canChangeSelection"
                  />
                </label>
                <button
                  type="button"
                  class="text-button"
                  :disabled="!canChangeSelection"
                  @click="saveNote(group)"
                >
                  Save note
                </button>
                <label v-if="!group.rejected">
                  <span>Rejection reason</span>
                  <input
                    v-model="rejectionDrafts[group.group_id]"
                    type="text"
                    :disabled="!canChangeSelection"
                  />
                </label>
                <button
                  v-if="!group.rejected"
                  type="button"
                  class="secondary-button"
                  :disabled="!canChangeSelection || !rejectionDrafts[group.group_id]?.trim()"
                  @click="rejectGroup(group)"
                >
                  Reject group (does not approve any order)
                </button>
                <button
                  v-else
                  type="button"
                  class="secondary-button"
                  :disabled="!canChangeSelection"
                  @click="restoreGroup(group)"
                >
                  Restore rejected group (remains unselected)
                </button>
                <p v-if="group.rejection_reason" class="rejection-note">
                  Saved rejection reason: {{ group.rejection_reason }}
                </p>
              </section>
            </div>
          </details>
        </div>

        <section
          v-if="visibleSharedLegs.length"
          class="shared-legs"
          aria-labelledby="shared-legs-title"
        >
          <h3 id="shared-legs-title">Shared consolidated legs · each canonical leg shown once</h3>
          <p>
            These API legs are referenced by multiple groups. A shared BUY cannot be toggled
            independently.
          </p>
          <article
            v-for="leg in visibleSharedLegs"
            :id="legAnchor(leg.leg_id)"
            :key="leg.leg_id"
            class="leg-card"
          >
            <LegDetails :leg="leg" />
            <p><strong>Linked groups:</strong> {{ leg.group_ids.join(', ') }}</p>
            <p v-if="leg.dependencies.length">
              <strong>Leg dependencies:</strong> {{ leg.dependencies.join(', ') }}
            </p>
          </article>
        </section>

        <section
          v-if="visibleUnlinkedLegs.length"
          class="warning-banner"
          aria-label="Unlinked API legs"
        >
          <h3>Unlinked API legs — not executable</h3>
          <article
            v-for="leg in visibleUnlinkedLegs"
            :id="legAnchor(leg.leg_id)"
            :key="leg.leg_id"
            class="leg-card"
          >
            <LegDetails :leg="leg" />
            <p>
              API group references are missing or inconsistent. Do not treat this leg as an
              executable recommendation.
            </p>
          </article>
        </section>
      </section>

      <section v-if="!mutationBusy" class="export-panel" aria-label="Recommendation export">
        <div>
          <h2>Export this API run</h2>
          <p>
            Exports retain the API run, policy, source generation, as-of time, warnings, and
            demo/actionability metadata.
          </p>
        </div>
        <button
          type="button"
          class="secondary-button"
          :disabled="store.actionState.exportRun.pending"
          @click="exportRun('csv')"
        >
          Export CSV
        </button>
        <button
          type="button"
          class="secondary-button"
          :disabled="store.actionState.exportRun.pending"
          @click="exportRun('json')"
        >
          Export JSON
        </button>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, reactive, ref, toRaw, watch } from 'vue';
import type { PropType } from 'vue';
import ApiActionError from '@/components/ApiActionError.vue';
import AllocationTargets from '@/components/AllocationTargets.vue';
import USAllocationTransition from '@/components/USAllocationTransition.vue';
import type { ExportFormat } from '@/services/api';
import { useWorkspaceStore } from '@/stores/workspace-store';
import type { RecommendationGroupResponse, RecommendationLegResponse } from '@/types/api';
import {
  canonicalLegs,
  displayJson,
  displayUsd,
  filterGroups,
  groupLegs,
  groupSellLotIds,
  requestGroupSelection,
  requestLotSelection,
  sharedLegs,
  unlinkedLegs,
  type RecommendationFilters,
} from './recommendations-state';
import { isMatchingCurrentRun } from './overview-state';

const store = useWorkspaceStore();
const savedRunId = ref('');
const topN = ref(3);
const sortOrder = ref<'rank-ascending' | 'rank-descending'>('rank-ascending');
const mutationBusy = ref(false);
const noteDrafts = reactive<Record<string, string>>({});
const rejectionDrafts = reactive<Record<string, string>>({});
const filters = reactive<RecommendationFilters>({
  sleeve: '',
  action: '',
  term: '',
  benefit: '',
  warning: '',
  groupType: '',
});

const currentRun = computed(() => store.currentRun);
const savedRunSummary = computed(() => store.currentRunSummary);
const portfolio = computed(() => store.portfolio);
const activePolicy = computed(() => store.policy?.active ?? null);
const currentRunMatches = computed(() =>
  isMatchingCurrentRun(
    portfolio.value?.status === 'ready' ? portfolio.value : null,
    currentRun.value,
    store.currentRunView,
    store.proposedRunIsStale,
  ),
);
const staleOrUnverified = computed(() => {
  if (!currentRun.value || store.currentRunView !== 'current') return false;
  if (portfolio.value?.status !== 'ready') return true;
  return !currentRunMatches.value;
});
const provenanceLabel = computed(() => {
  if (store.currentRunView === 'saved') return 'Saved run · frozen API context · read-only';
  if (store.currentRunView === 'stale' || staleOrUnverified.value)
    return 'Stale/unverified run · read-only';
  return 'Current run · API context';
});
const currentRunEffectsAreUsable = computed(
  () =>
    currentRun.value !== null &&
    !mutationBusy.value &&
    (currentRunMatches.value || store.currentRunView === 'saved'),
);
const effectAllocation = computed(() => {
  if (currentRunEffectsAreUsable.value)
    return currentRun.value?.portfolio_effects?.allocation ?? null;
  return portfolio.value?.allocation ?? null;
});
const effectTransition = computed(() => {
  if (currentRunEffectsAreUsable.value)
    return currentRun.value?.portfolio_effects?.us_transition ?? null;
  return portfolio.value?.us_transition ?? null;
});
const showNoCurrentBasket = computed(
  () => !currentRunMatches.value && store.currentRunView !== 'saved',
);
const effectsDescription = computed(() => {
  if (store.currentRunView === 'saved' && currentRunEffectsAreUsable.value)
    return 'Frozen effects returned with this saved run; no current portfolio values are overlaid.';
  if (currentRunMatches.value)
    return 'Effects returned by the current selected-basket API response. Missing values remain unavailable.';
  return 'Only the current portfolio API values are shown. Stale or unverified run effects are not overlaid.';
});
const canRunOptimizer = computed(
  () =>
    portfolio.value?.status === 'ready' &&
    portfolio.value.sync.complete &&
    store.health?.status === 'ok' &&
    store.health.schema_ready &&
    activePolicy.value !== null &&
    portfolio.value.active_policy_revision_id === activePolicy.value.id &&
    (activePolicy.value.activation_errors?.length ?? 0) === 0 &&
    !store.actionState.syncPortfolio.pending &&
    !store.actionState.runOptimizer.pending &&
    !store.actionState.openSavedRun.pending,
);
const canChangeSelection = computed(
  () =>
    currentRunMatches.value &&
    store.currentRunView === 'current' &&
    !store.actionState.recalculateSelection.pending &&
    !store.actionState.syncPortfolio.pending &&
    !mutationBusy.value,
);
const sleeveLabels = computed(() =>
  Object.fromEntries(
    (activePolicy.value?.sleeves ?? []).map((sleeve) => [sleeve.sleeve_key, sleeve.display_name]),
  ),
);
const sleeveOptions = computed(() =>
  [...new Set(currentRun.value?.groups.map((group) => group.sleeve_key) ?? [])].sort(),
);
const groupTypeOptions = computed(() =>
  [...new Set(currentRun.value?.groups.map((group) => group.group_type) ?? [])].sort(),
);
const filteredGroups = computed(() =>
  currentRun.value ? filterGroups(currentRun.value, filters, sortOrder.value) : [],
);
const allCanonicalLegs = computed(() => (currentRun.value ? canonicalLegs(currentRun.value) : []));
const allSharedLegs = computed(() => (currentRun.value ? sharedLegs(currentRun.value) : []));
const invalidLegIds = computed(() => new Set(visibleUnlinkedLegs.value.map((leg) => leg.leg_id)));
const visibleSharedLegs = computed(() =>
  allSharedLegs.value.filter((leg) => !invalidLegIds.value.has(leg.leg_id)),
);
const visibleUnlinkedLegs = computed(() =>
  currentRun.value ? unlinkedLegs(currentRun.value) : [],
);

watch(
  currentRun,
  (run, previousRun) => {
    const sameRun = run !== null && previousRun?.run_id === run.run_id;
    if (!sameRun) {
      for (const key of Object.keys(noteDrafts)) delete noteDrafts[key];
      for (const key of Object.keys(rejectionDrafts)) delete rejectionDrafts[key];
    } else {
      const groupIds = new Set(run.groups.map((group) => group.group_id));
      for (const key of Object.keys(noteDrafts)) {
        if (!groupIds.has(key)) delete noteDrafts[key];
      }
      for (const key of Object.keys(rejectionDrafts)) {
        if (!groupIds.has(key)) delete rejectionDrafts[key];
      }
    }

    for (const group of run?.groups ?? []) {
      const previousGroup = sameRun
        ? previousRun?.groups.find((item) => item.group_id === group.group_id)
        : undefined;
      if (!previousGroup || noteDrafts[group.group_id] === (previousGroup.note ?? '')) {
        noteDrafts[group.group_id] = group.note ?? '';
      }
      if (
        !previousGroup ||
        rejectionDrafts[group.group_id] === (previousGroup.rejection_reason ?? '')
      ) {
        rejectionDrafts[group.group_id] = group.rejection_reason ?? '';
      }
    }
  },
  { immediate: true },
);

function sleeveLabel(key: string): string {
  return sleeveLabels.value[key] ?? key;
}

function groupLegsFor(group: RecommendationGroupResponse): RecommendationLegResponse[] {
  if (!currentRun.value) return [];
  return groupLegs(currentRun.value, group).sort((left, right) => left.sequence - right.sequence);
}

function groupDetailLegs(group: RecommendationGroupResponse): RecommendationLegResponse[] {
  return groupLegsFor(group).filter(
    (leg) => leg.group_ids.length <= 1 && !invalidLegIds.value.has(leg.leg_id),
  );
}

function groupSellLotIdsFor(group: RecommendationGroupResponse): string[] {
  return currentRun.value ? groupSellLotIds(currentRun.value, group) : [];
}

function findLeg(legId: string): RecommendationLegResponse | undefined {
  return allCanonicalLegs.value.find((leg) => leg.leg_id === legId);
}

function isSharedLeg(legId: string): boolean {
  return visibleSharedLegs.value.some((leg) => leg.leg_id === legId);
}

function isUnlinkedLeg(legId: string): boolean {
  return visibleUnlinkedLegs.value.some((leg) => leg.leg_id === legId);
}

function legLabel(group: RecommendationGroupResponse, legId: string): string {
  const leg = findLeg(legId);
  if (!leg) return 'Missing API leg';
  return `Sequence ${leg.sequence} ${leg.side} ${leg.ticker ?? 'ticker unavailable'}`;
}

function legAnchor(legId: string): string {
  return `leg-${encodeURIComponent(legId)}`;
}

function loadInitialWorkspace(): void {
  const requests: Promise<unknown>[] = [];
  if (!store.health) requests.push(store.loadHealth());
  if (!store.portfolio) requests.push(store.loadPortfolio());
  if (!store.policy) requests.push(store.loadPolicy());
  void Promise.allSettled(requests);
}

async function runOptimizer(): Promise<void> {
  if (!canRunOptimizer.value) return;
  try {
    await store.runOptimizer({});
  } catch {
    // The store retains a structured API error for this page.
  }
}

async function openSavedRun(): Promise<void> {
  const runId = savedRunId.value.trim();
  if (!runId) return;
  try {
    await store.openSavedRun(runId);
  } catch {
    // The store retains a structured API error for this page.
  }
}

async function recalculate(
  selection: Parameters<typeof store.recalculateSelection>[0],
): Promise<void> {
  if (!canChangeSelection.value) return;
  mutationBusy.value = true;
  try {
    await store.recalculateSelection(selection);
  } catch {
    // Keep the last successful response and expose the API failure above.
  } finally {
    mutationBusy.value = false;
  }
}

function changeGroupSelection(group: RecommendationGroupResponse, event: Event): void {
  if (!currentRun.value) return;
  const input = event.currentTarget as HTMLInputElement;
  const requestedSelection = input.checked;
  // Keep the visible state at the last API-confirmed value until re-solving succeeds.
  input.checked = group.selected;
  void recalculate(requestGroupSelection(currentRun.value, group.group_id, requestedSelection));
}

function changeLotSelection(
  group: RecommendationGroupResponse,
  brokerLotId: string,
  event: Event,
): void {
  if (!currentRun.value) return;
  const input = event.currentTarget as HTMLInputElement;
  const requestedSelection = input.checked;
  const confirmedSelection =
    groupLegsFor(group)
      .filter((leg) => leg.side === 'SELL')
      .flatMap((leg) => leg.selected_lots)
      .find((lot) => lot.broker_lot_id === brokerLotId)?.selected ?? false;
  // Do not display the attempted checkbox state as selected before the API accepts it.
  input.checked = confirmedSelection;
  void recalculate(
    requestLotSelection(currentRun.value, group.group_id, brokerLotId, requestedSelection),
  );
}

function selectTopGroups(): void {
  const run = currentRun.value;
  if (!run) return;
  const count = Math.max(0, Math.floor(Number(topN.value) || 0));
  const selectedGroups = [...run.groups]
    .filter((group) => !group.rejected && groupSellLotIds(run, group).length > 0)
    .sort((left, right) => left.rank - right.rank)
    .slice(0, count);
  void recalculate({
    selected_group_ids: selectedGroups.map((group) => group.group_id),
    selected_sell_lots: Object.fromEntries(
      selectedGroups.map((group) => [group.group_id, groupSellLotIds(run, group)]),
    ),
  });
}

function clearSelection(): void {
  void recalculate({ selected_group_ids: [], selected_sell_lots: {} });
}

async function saveNote(group: RecommendationGroupResponse): Promise<void> {
  const run = currentRun.value;
  if (!run || !canChangeSelection.value || mutationBusy.value) return;
  const groupId = group.group_id;
  const submittedDraft = noteDrafts[groupId] ?? '';
  const note = submittedDraft.trim() || null;
  mutationBusy.value = true;
  try {
    const result = await store.annotateGroup(run.run_id, groupId, { note });
    const current = currentRun.value;
    const publishedGroup = current?.groups.find((item) => item.group_id === groupId);
    if (
      current?.run_id === run.run_id &&
      publishedGroup !== undefined &&
      toRaw(publishedGroup) === toRaw(result) &&
      noteDrafts[groupId] === submittedDraft
    ) {
      noteDrafts[groupId] = result.note ?? '';
    }
  } catch {
    // The store retains a structured API error for this page.
  } finally {
    mutationBusy.value = false;
  }
}

async function rejectGroup(group: RecommendationGroupResponse): Promise<void> {
  const run = currentRun.value;
  if (!run || !canChangeSelection.value || mutationBusy.value) return;
  const groupId = group.group_id;
  const submittedDraft = rejectionDrafts[groupId] ?? '';
  const reason = submittedDraft.trim();
  if (!reason) return;
  mutationBusy.value = true;
  try {
    // Deselect first so the full re-solved basket is stored in the workspace before annotation.
    if (group.selected) {
      const deselected = requestGroupSelection(run, groupId, false);
      await store.recalculateSelection(deselected);
    }
    const result = await store.annotateGroup(run.run_id, groupId, {
      rejected: true,
      rejection_reason: reason,
    });
    const current = currentRun.value;
    const publishedGroup = current?.groups.find((item) => item.group_id === groupId);
    if (
      current?.run_id === run.run_id &&
      publishedGroup !== undefined &&
      toRaw(publishedGroup) === toRaw(result) &&
      rejectionDrafts[groupId] === submittedDraft
    ) {
      rejectionDrafts[groupId] = result.rejection_reason ?? '';
    }
  } catch {
    // Do not apply the rejection if deselection/re-solve failed; retain the API error.
  } finally {
    mutationBusy.value = false;
  }
}

async function restoreGroup(group: RecommendationGroupResponse): Promise<void> {
  if (!currentRun.value || !canChangeSelection.value || mutationBusy.value) return;
  mutationBusy.value = true;
  try {
    await store.annotateGroup(currentRun.value.run_id, group.group_id, {
      rejected: false,
      rejection_reason: null,
    });
  } catch {
    // The store retains a structured API error for this page.
  } finally {
    mutationBusy.value = false;
  }
}

async function exportRun(format: ExportFormat): Promise<void> {
  if (!currentRun.value) return;
  try {
    const result = await store.exportRun(currentRun.value.run_id, format);
    const url = URL.createObjectURL(result.blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = result.filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  } catch {
    // The store retains a structured API error for this page.
  }
}

onMounted(loadInitialWorkspace);

const LegDetails = defineComponent({
  name: 'RecommendationLegDetails',
  props: { leg: { type: Object as PropType<RecommendationLegResponse>, required: true } },
  setup(props) {
    return () =>
      h('div', { class: 'leg-details' }, [
        h(
          'h3',
          `Sequence ${props.leg.sequence} · ${props.leg.side} ${props.leg.ticker ?? 'ticker unavailable'}`,
        ),
        h('dl', { class: 'leg-facts' }, [
          h('div', [h('dt', 'Leg ID'), h('dd', props.leg.leg_id)]),
          h('div', [h('dt', 'API-proposed whole shares'), h('dd', props.leg.shares)]),
          h('div', [
            h('dt', 'Estimated unit price'),
            h('dd', displayUsd(props.leg.estimated_unit_price_usd)),
          ]),
          h('div', [
            h('dt', 'Estimated notional'),
            h('dd', displayUsd(props.leg.estimated_notional_usd)),
          ]),
          h('div', [
            h('dt', 'Net realized ST / LT'),
            h(
              'dd',
              `${displayUsd(props.leg.net_st_realized_usd)} / ${displayUsd(props.leg.net_lt_realized_usd)}`,
            ),
          ]),
        ]),
        props.leg.dependencies.length
          ? h(
              'p',
              { class: 'dependency-note' },
              `Requires API leg(s): ${props.leg.dependencies.join(', ')}`,
            )
          : h('p', { class: 'dependency-note' }, 'No leg dependency was returned by the API.'),
        h(
          'p',
          { class: 'leg-status' },
          props.leg.selected ? 'Selected in this API basket' : 'Not selected in this API basket',
        ),
      ]);
  },
});
</script>

<style scoped>
.run-title-row,
.export-panel {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.section-heading h2,
.run-title-row h2,
.export-panel h2 {
  margin: 0;
  color: #10263d;
}

.section-heading p,
.run-title-row p,
.export-panel p {
  margin: 0.35rem 0 0;
  color: #61798a;
  line-height: 1.5;
}
.demo-notice,
.warning-banner,
.pending-banner,
.provenance-banner {
  margin: 0;
  padding: 0.8rem 1rem;
  border-radius: 0.65rem;
  line-height: 1.5;
}
.demo-notice {
  border: 1px solid #e8d39a;
  background: #fff8e7;
  color: #70501b;
}
.warning-banner {
  border: 1px solid #e8d39a;
  background: #fff8e7;
  color: #70501b;
}
.pending-banner {
  border: 1px solid #9dcbd0;
  background: #eef9fa;
  color: #245a62;
}
.provenance-banner {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem 1rem;
  border: 1px solid #dce6eb;
  background: #f7fafb;
  color: #35586c;
  font-size: 0.78rem;
}
.provenance-banner[data-view='stale'] {
  border-color: #e8d39a;
  background: #fff8e7;
}
.run-controls,
.run-summary,
.effects-panel,
.review-panel,
.export-panel {
  padding: 1rem;
  border: 1px solid #dce6eb;
  border-radius: 0.8rem;
  background: #fff;
  box-shadow: 0 4px 20px rgb(18 55 77 / 4.5%);
}
.saved-run-form,
.filter-panel,
.selection-tools,
.annotation-panel {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 0.75rem;
}
.saved-run-form {
  justify-content: flex-end;
}
label {
  display: grid;
  gap: 0.3rem;
  color: #526c7c;
  font-size: 0.76rem;
  font-weight: 650;
}
input,
select,
textarea {
  min-width: 9rem;
  padding: 0.55rem 0.65rem;
  border: 1px solid #bfd0d8;
  border-radius: 0.45rem;
  background: #fff;
  color: #29475a;
  font: inherit;
}
textarea {
  min-width: min(28rem, 100%);
  resize: vertical;
}
button {
  padding: 0.58rem 0.82rem;
  border: 1px solid #bfd0d8;
  border-radius: 0.5rem;
  background: #f7fafb;
  color: #24475a;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}
button.primary-button {
  border-color: #087f7d;
  background: #087f7d;
  color: #fff;
}
button.text-button {
  border: 0;
  background: transparent;
  color: #087f7d;
  text-decoration: underline;
}
button:disabled,
input:disabled,
select:disabled,
textarea:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}
.error-stack {
  display: grid;
  gap: 0.5rem;
}
.run-title-row {
  align-items: center;
}
.run-title-row h2 {
  font-size: 1.1rem;
}
.demo-badge,
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
.demo-badge {
  background: #fff1d2;
  color: #77520d;
}
.priority-badge {
  background: #e4f5f2;
  color: #086f6e;
}
.selected-badge {
  background: #e4f5f2;
  color: #086f6e;
}
.rejected-badge {
  background: #fff0f0;
  color: #812f36;
}
.warning-banner {
  margin-top: 0.7rem;
}
.metric-grid,
.group-facts,
.leg-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.6rem;
  margin: 0.8rem 0 0;
}
.metric-grid > div,
.group-facts > div,
.leg-facts > div {
  min-width: 0;
  padding: 0.65rem;
  border: 1px solid #eaf0f3;
  border-radius: 0.55rem;
}
dl dt {
  color: #647c8b;
  font-size: 0.7rem;
}
dl dd {
  margin: 0.25rem 0 0;
  color: #29475a;
  font-size: 0.78rem;
  font-weight: 700;
  overflow-wrap: anywhere;
}
.metric-grid small {
  color: #657d8b;
}
.no-trade-reason,
.rationale,
.dependency-note,
.read-only-note,
.rejection-note,
.empty-inline,
.shared-note,
.state-message {
  color: #526c7c;
  font-size: 0.78rem;
  line-height: 1.5;
}
.no-trade-reason {
  margin: 0.8rem 0 0;
}
.warning-list {
  margin: 0.6rem 0 0;
  padding-left: 1.2rem;
  color: #765016;
  font-size: 0.78rem;
}
.provenance-details {
  margin-top: 0.8rem;
  color: #405f71;
  font-size: 0.76rem;
}
.provenance-details summary {
  cursor: pointer;
  font-weight: 700;
}
pre {
  max-height: 16rem;
  overflow: auto;
  padding: 0.7rem;
  border-radius: 0.5rem;
  background: #f5f8fa;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.effects-panel {
  display: grid;
  gap: 1rem;
}
.section-heading h2 {
  font-size: 1.05rem;
}
.section-heading > span {
  color: #657d8b;
  font-size: 0.76rem;
}
.filter-panel {
  padding: 0.75rem;
  border: 1px solid #eaf0f3;
  border-radius: 0.65rem;
}
.filter-panel label {
  flex: 1 1 9rem;
}
.filter-panel select {
  min-width: 0;
  width: 100%;
}
.selection-tools {
  margin: 0.8rem 0;
  padding: 0.8rem;
  border: 1px solid #dce6eb;
  border-radius: 0.65rem;
  min-width: 0;
}
.selection-tools legend {
  padding: 0 0.3rem;
  color: #29475a;
  font-weight: 800;
}
.top-n-control {
  max-width: 13rem;
}
.top-n-control input {
  min-width: 5rem;
}
.selection-tools:disabled {
  opacity: 0.7;
}
.group-list {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  min-width: 0;
  gap: 0.65rem;
}
.group-card {
  border: 1px solid #dce6eb;
  border-radius: 0.7rem;
  background: #fff;
  min-width: 0;
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
.group-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  min-width: 0;
  gap: 0.75rem;
  padding: 0 0.85rem 0.9rem;
}
.group-selection,
.lot-selection {
  display: inline-flex;
  grid-auto-flow: column;
  align-items: center;
  justify-content: start;
  gap: 0.45rem;
}
.group-selection input,
.lot-selection input {
  min-width: auto;
}
.group-facts {
  margin-top: 0;
}
.rationale {
  margin: 0;
}
.group-body h3,
.shared-legs h3,
.warning-banner h3 {
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
a {
  color: #087f7d;
  font-weight: 650;
}
.shared-note {
  display: block;
}
.warning-text {
  color: #812f36;
}
.leg-card {
  padding: 0.8rem;
  border: 1px solid #eaf0f3;
  border-radius: 0.6rem;
  background: #fbfdfe;
  scroll-margin-top: 1rem;
  min-width: 0;
}
.leg-card h3 {
  margin: 0;
  color: #29475a;
  font-size: 0.9rem;
}
.leg-facts {
  margin-bottom: 0.5rem;
}
.leg-status {
  margin: 0.4rem 0 0;
  color: #657d8b;
  font-size: 0.73rem;
}
.lot-table-wrap {
  max-width: 100%;
  overflow-x: auto;
  min-width: 0;
}
table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}
caption {
  padding: 0.6rem 0;
  color: #526c7c;
  font-size: 0.74rem;
  font-weight: 700;
  text-align: left;
}
th,
td {
  padding: 0.55rem;
  border-bottom: 1px solid #eaf0f3;
  color: #35586c;
  font-size: 0.73rem;
  white-space: nowrap;
}
thead th {
  background: #f3f8fa;
  color: #627b8b;
  font-size: 0.68rem;
  text-transform: uppercase;
}
.annotation-panel {
  align-items: end;
  padding-top: 0.7rem;
  border-top: 1px solid #eaf0f3;
}
.annotation-panel label:first-child {
  flex: 1 1 18rem;
}
.annotation-panel label:nth-of-type(2) {
  flex: 1 1 14rem;
}
.annotation-panel input {
  min-width: 0;
}
.shared-legs {
  display: grid;
  gap: 0.65rem;
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #dce6eb;
}
.shared-legs > p {
  margin: 0;
  color: #526c7c;
  font-size: 0.78rem;
}
.export-panel {
  align-items: center;
  flex-wrap: wrap;
}
.export-panel > div {
  flex: 1 1 20rem;
}
.export-panel h2 {
  font-size: 1rem;
}
.empty-state {
  padding: 1.2rem;
  border: 1px dashed #bfd0d8;
  border-radius: 0.75rem;
  color: #526c7c;
}
.empty-state h2 {
  margin: 0;
  color: #29475a;
  font-size: 1rem;
}
.empty-state p {
  margin: 0.55rem 0 0;
  font-size: 0.8rem;
  line-height: 1.5;
}
.empty-inline {
  margin: 0.3rem 0;
}
@media (max-width: 760px) {
  .page-header,
  .section-heading,
  .run-title-row {
    flex-direction: column;
    align-items: stretch;
  }
  .saved-run-form {
    justify-content: flex-start;
  }
  .saved-run-form label {
    flex: 1 1 100%;
  }
  .saved-run-form input {
    width: 100%;
  }
  .provenance-banner {
    display: grid;
  }
  .metric-grid,
  .group-facts,
  .leg-facts {
    grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
  }
}
</style>
