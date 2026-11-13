<template>
  <section
    class="workspace-page recommendations-page tw:mx-auto tw:my-0! tw:min-w-0 tw:max-w-[1600px] tw:px-4 tw:py-4"
    data-recommendations-root
    aria-labelledby="recommendations-title"
  >
    <WorkspacePageHeader
      eyebrow="Small-batch review"
      title="Recommendations"
      title-id="recommendations-title"
      subtitle="Review ranked groups and API-proposed legs. Group or sell-lot selection requests a backend re-solve; selection is never an order approval."
    >
      <template #actions>
        <Button
          type="button"
          variant="default"
          size="sm"
          class="primary-button tw:whitespace-normal"
          :disabled="!canRunOptimizer"
          @click="runOptimizer"
        >
          {{
            store.actionState.runOptimizer.pending ? 'Running DEMO…' : 'Run DEMO recommendations'
          }}
        </Button>
      </template>
    </WorkspacePageHeader>

    <WorkspaceCapabilityNotice label="DEMO ONLY · non-actionable.">
      API demo values are hypothetical. No E*TRADE connection, OAuth, order preview, approval, or
      submission controls exist on this screen.
    </WorkspaceCapabilityNotice>

    <section class="run-controls tw:min-w-0" aria-label="Recommendation run controls">
      <Card class="tw:min-w-0">
        <CardHeader class="tw:gap-1">
          <h2 class="tw:m-0! tw:text-base! tw:font-semibold!">Run recommendations</h2>
          <p class="tw:m-0! tw:text-sm! tw:text-muted-foreground">
            Choose an optional calendar date, or reopen a frozen run by its API run ID.
          </p>
        </CardHeader>
        <CardContent class="tw:grid tw:min-w-0 tw:grid-cols-1 tw:gap-4 tw:md:grid-cols-2">
          <runForm.Field name="proposedTradeDate">
            <template #default="{ field }">
              <UiField :data-invalid="field.state.meta.errors.length ? 'true' : undefined">
                <FieldLabel for="recommendation-proposed-trade-date">
                  Proposed trade date (optional)
                </FieldLabel>
                <Input
                  id="recommendation-proposed-trade-date"
                  type="date"
                  :model-value="field.state.value"
                  :disabled="!canRunOptimizer"
                  :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                  :aria-describedby="
                    field.state.meta.errors.length
                      ? 'recommendation-proposed-trade-date-error recommendation-date-help'
                      : 'recommendation-date-help'
                  "
                  @update:model-value="setProposedTradeDate"
                  @blur="field.handleBlur"
                />
                <FieldDescription id="recommendation-date-help">
                  Blank uses the deterministic DEMO date 2026-11-05. This is a calendar date; no
                  weekend or holiday adjustment is applied.
                </FieldDescription>
                <FieldError
                  id="recommendation-proposed-trade-date-error"
                  :errors="field.state.meta.errors"
                />
              </UiField>
            </template>
          </runForm.Field>
          <p
            v-if="!canRunOptimizer"
            class="state-message tw:m-0! tw:self-center tw:text-sm! tw:text-muted-foreground"
          >
            A new run requires a ready synchronized portfolio, healthy local API, and valid active
            policy. Nothing runs automatically.
          </p>
        </CardContent>
      </Card>
    </section>

    <form
      class="saved-run-form tw:min-w-0"
      aria-label="Open saved recommendation run"
      @submit.prevent="openSavedRun"
    >
      <Card class="tw:min-w-0">
        <CardHeader class="tw:gap-1">
          <h2 class="tw:m-0! tw:text-base! tw:font-semibold!">Open a saved run</h2>
          <p class="tw:m-0! tw:text-sm! tw:text-muted-foreground">
            Saved runs retain their frozen historical display context and are read-only.
          </p>
        </CardHeader>
        <CardContent
          class="tw:grid tw:min-w-0 tw:grid-cols-1 tw:items-start tw:gap-4 tw:sm:grid-cols-[minmax(0,1fr)_auto]"
        >
          <savedRunForm.Field name="savedRunId">
            <template #default="{ field }">
              <UiField :data-invalid="field.state.meta.errors.length ? 'true' : undefined">
                <FieldLabel for="recommendation-saved-run-id">Open saved run ID</FieldLabel>
                <Input
                  id="recommendation-saved-run-id"
                  type="text"
                  autocomplete="off"
                  placeholder="Run ID from Activity"
                  :model-value="field.state.value"
                  :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                  :aria-describedby="
                    field.state.meta.errors.length ? 'recommendation-saved-run-id-error' : undefined
                  "
                  @update:model-value="setSavedRunId"
                  @blur="field.handleBlur"
                />
                <FieldError
                  id="recommendation-saved-run-id-error"
                  :errors="field.state.meta.errors"
                />
              </UiField>
            </template>
          </savedRunForm.Field>
          <Button
            type="submit"
            variant="outline"
            size="sm"
            class="secondary-button tw:whitespace-normal"
            :disabled="
              !savedRunId.trim() ||
              store.actionState.openSavedRun.pending ||
              runPresentation.reviewMutationPending
            "
          >
            {{ store.actionState.openSavedRun.pending ? 'Opening saved run…' : 'Open frozen run' }}
          </Button>
        </CardContent>
      </Card>
    </form>

    <div class="error-stack tw:grid tw:min-w-0 tw:gap-2" aria-label="Recommendation request errors">
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

    <ResourceFreshnessNotice />
    <div
      v-if="portfolioLabelContext.revisionMismatch && !currentRunEffectsAreUsable"
      role="status"
      class="tw:my-2! tw:w-full tw:rounded-lg tw:border tw:border-border tw:bg-card tw:px-2.5 tw:py-2 tw:text-left tw:text-sm! tw:text-card-foreground"
    >
      <AlertDescription>
        Portfolio effects use policy revision
        {{ portfolioLabelContext.portfolioRevisionId ?? 'unavailable' }}; the active policy is
        {{ portfolioLabelContext.policyRevisionId ?? 'unavailable' }}. Cached values remain visible
        with API sleeve keys until matching policy labels are confirmed.
      </AlertDescription>
    </div>

    <WorkspaceEmptyState
      v-if="!currentRun"
      :title="
        store.actionState.runOptimizer.pending || store.actionState.openSavedRun.pending
          ? 'Loading recommendations'
          : 'No recommendation run loaded'
      "
    >
      <template
        v-if="store.actionState.runOptimizer.pending || store.actionState.openSavedRun.pending"
      >
        The local API is preparing or reopening a run.
      </template>
      <template v-else>
        Run a DEMO analysis from Overview or this page, or reopen a saved run by its API run ID.
      </template>
      <template #details>
        <p
          v-if="store.actionState.runOptimizer.error || store.actionState.openSavedRun.error"
          class="tw:m-0!"
        >
          The request failed. Retry only after reviewing the API error above.
        </p>
      </template>
    </WorkspaceEmptyState>

    <template v-else>
      <RunSummary
        mode="review"
        :run="currentRun"
        :summary="savedRunSummary"
        :context="runDisplayContext"
        :pending="runPresentation.reviewMutationPending"
        :current-selection-confirmed="runPresentation.currentRunMatches"
        :view="store.currentRunView"
        :provenance-label="provenanceLabel"
      />

      <section
        v-if="!runPresentation.reviewMutationPending"
        class="effects-panel tw:min-w-0"
        aria-labelledby="effects-title"
      >
        <Card class="tw:min-w-0">
          <CardHeader class="tw:gap-1">
            <h2 class="tw:m-0! tw:text-base! tw:font-semibold!" id="effects-title">
              API allocation effects
            </h2>
            <p class="tw:m-0! tw:text-sm! tw:text-muted-foreground">{{ effectsDescription }}</p>
          </CardHeader>
          <CardContent class="tw:grid tw:min-w-0 tw:gap-4">
            <AllocationTargets
              :allocation="effectDisplay.allocation"
              :labels="effectDisplay.labels"
              :show-no-current-basket="showNoCurrentBasket"
            />
            <USAllocationTransition
              :transition="effectDisplay.transition"
              :labels="effectDisplay.labels"
              :snapshot-status="transitionSnapshotStatus"
              :basket-status="transitionBasketStatus"
              :role-identity="transitionRoleIdentity"
              :provenance="effectDisplay.source"
            />
          </CardContent>
        </Card>
      </section>

      <section
        v-if="currentRunGroupCount && !runPresentation.reviewMutationPending"
        class="review-panel tw:min-w-0"
        aria-labelledby="groups-title"
      >
        <Card class="tw:min-w-0">
          <CardHeader class="tw:gap-2">
            <div class="tw:grid tw:min-w-0 tw:gap-1">
              <h2 class="tw:m-0! tw:text-base! tw:font-semibold!" id="groups-title">
                Ranked trade groups
              </h2>
              <p class="tw:m-0! tw:text-sm! tw:text-muted-foreground">
                Priority rank is the API rank, not a precision score. Execution sequence and
                dependencies are shown separately.
              </p>
            </div>
            <span class="tw:text-sm! tw:text-muted-foreground">
              {{ filteredGroups.length }} shown / {{ currentRunGroupCount }} returned
            </span>
          </CardHeader>
          <CardContent class="tw:grid tw:min-w-0 tw:gap-4">
            <form class="tw:min-w-0" aria-label="Recommendation filters" @submit.prevent>
              <Card class="filter-panel tw:min-w-0" size="sm">
                <CardHeader class="tw:sr-only">
                  <h3 class="tw:m-0! tw:text-sm! tw:font-semibold!">Recommendation filters</h3>
                </CardHeader>
                <CardContent>
                  <FieldGroup
                    class="tw:grid tw:min-w-0 tw:grid-cols-1 tw:gap-4 tw:sm:grid-cols-2 tw:lg:grid-cols-3"
                  >
                    <filterForm.Field name="sleeve">
                      <template #default="{ field }">
                        <UiField>
                          <FieldLabel for="recommendation-filter-sleeve">Sleeve</FieldLabel>
                          <Select
                            :model-value="filters.sleeve ? `key:${filters.sleeve}` : 'all-sleeves'"
                            @update:model-value="setSleeveFilter"
                          >
                            <SelectTrigger id="recommendation-filter-sleeve" aria-label="Sleeve">
                              <SelectValue placeholder="All sleeves" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectGroup>
                                <SelectItem value="all-sleeves">All sleeves</SelectItem>
                                <SelectItem
                                  v-for="sleeve in sleeveOptions"
                                  :key="sleeve"
                                  :value="`key:${sleeve}`"
                                >
                                  {{ sleeveLabel(sleeve) }}
                                </SelectItem>
                              </SelectGroup>
                            </SelectContent>
                          </Select>
                          <FieldError :errors="field.state.meta.errors" />
                        </UiField>
                      </template>
                    </filterForm.Field>

                    <filterForm.Field name="action">
                      <template #default="{ field }">
                        <UiField>
                          <FieldLabel for="recommendation-filter-action">Action</FieldLabel>
                          <Select
                            :model-value="filters.action || 'all-actions'"
                            @update:model-value="setActionFilter"
                          >
                            <SelectTrigger id="recommendation-filter-action" aria-label="Action">
                              <SelectValue placeholder="Any action" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectGroup>
                                <SelectItem value="all-actions">Any action</SelectItem>
                                <SelectItem value="SELL">SELL</SelectItem>
                                <SelectItem value="BUY">BUY</SelectItem>
                              </SelectGroup>
                            </SelectContent>
                          </Select>
                          <FieldError :errors="field.state.meta.errors" />
                        </UiField>
                      </template>
                    </filterForm.Field>

                    <filterForm.Field name="term">
                      <template #default="{ field }">
                        <UiField>
                          <FieldLabel for="recommendation-filter-term">Tax term</FieldLabel>
                          <Select
                            :model-value="filters.term || 'all-terms'"
                            @update:model-value="setTermFilter"
                          >
                            <SelectTrigger id="recommendation-filter-term" aria-label="Tax term">
                              <SelectValue placeholder="Any term" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectGroup>
                                <SelectItem value="all-terms">Any term</SelectItem>
                                <SelectItem value="ST">Short term</SelectItem>
                                <SelectItem value="LT">Long term</SelectItem>
                              </SelectGroup>
                            </SelectContent>
                          </Select>
                          <FieldError :errors="field.state.meta.errors" />
                        </UiField>
                      </template>
                    </filterForm.Field>

                    <filterForm.Field name="benefit">
                      <template #default="{ field }">
                        <UiField>
                          <FieldLabel for="recommendation-filter-benefit"
                            >Expected benefit</FieldLabel
                          >
                          <Select
                            :model-value="filters.benefit || 'any-benefit'"
                            @update:model-value="setBenefitFilter"
                          >
                            <SelectTrigger
                              id="recommendation-filter-benefit"
                              aria-label="Expected benefit"
                            >
                              <SelectValue placeholder="Any" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectGroup>
                                <SelectItem value="any-benefit">Any</SelectItem>
                                <SelectItem value="unavailable">Unavailable in API</SelectItem>
                              </SelectGroup>
                            </SelectContent>
                          </Select>
                          <FieldError :errors="field.state.meta.errors" />
                        </UiField>
                      </template>
                    </filterForm.Field>

                    <filterForm.Field name="warning">
                      <template #default="{ field }">
                        <UiField>
                          <FieldLabel for="recommendation-filter-warning">Warnings</FieldLabel>
                          <Select
                            :model-value="filters.warning || 'any-warning-state'"
                            @update:model-value="setWarningFilter"
                          >
                            <SelectTrigger id="recommendation-filter-warning" aria-label="Warnings">
                              <SelectValue placeholder="Any" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectGroup>
                                <SelectItem value="any-warning-state">Any</SelectItem>
                                <SelectItem value="with">With warnings</SelectItem>
                                <SelectItem value="without">No warnings returned</SelectItem>
                              </SelectGroup>
                            </SelectContent>
                          </Select>
                          <FieldError :errors="field.state.meta.errors" />
                        </UiField>
                      </template>
                    </filterForm.Field>

                    <filterForm.Field name="groupType">
                      <template #default="{ field }">
                        <UiField>
                          <FieldLabel for="recommendation-filter-group-type">Group type</FieldLabel>
                          <Select
                            :model-value="
                              filters.groupType ? `key:${filters.groupType}` : 'all-group-types'
                            "
                            @update:model-value="setGroupTypeFilter"
                          >
                            <SelectTrigger
                              id="recommendation-filter-group-type"
                              aria-label="Group type"
                            >
                              <SelectValue placeholder="Any type" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectGroup>
                                <SelectItem value="all-group-types">Any type</SelectItem>
                                <SelectItem
                                  v-for="type in groupTypeOptions"
                                  :key="type"
                                  :value="`key:${type}`"
                                >
                                  {{ type }}
                                </SelectItem>
                              </SelectGroup>
                            </SelectContent>
                          </Select>
                          <FieldError :errors="field.state.meta.errors" />
                        </UiField>
                      </template>
                    </filterForm.Field>

                    <filterForm.Field name="sortOrder">
                      <template #default="{ field }">
                        <UiField>
                          <FieldLabel for="recommendation-sort-order"
                            >Sort by API priority rank</FieldLabel
                          >
                          <Select
                            :model-value="filters.sortOrder"
                            @update:model-value="setSortOrder"
                          >
                            <SelectTrigger
                              id="recommendation-sort-order"
                              aria-label="Sort by API priority rank"
                            >
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectGroup>
                                <SelectItem value="rank-ascending"
                                  >Highest priority first (ascending rank)</SelectItem
                                >
                                <SelectItem value="rank-descending"
                                  >Lowest priority first (descending rank)</SelectItem
                                >
                              </SelectGroup>
                            </SelectContent>
                          </Select>
                          <FieldError :errors="field.state.meta.errors" />
                        </UiField>
                      </template>
                    </filterForm.Field>
                  </FieldGroup>
                </CardContent>
              </Card>
            </form>

            <fieldset
              class="selection-tools tw:grid tw:min-w-0 tw:grid-cols-1 tw:items-end tw:gap-3 tw:rounded-lg tw:border tw:border-border tw:p-4 tw:sm:grid-cols-[minmax(10rem,13rem)_auto_auto]"
              :disabled="!canChangeSelection"
            >
              <legend class="tw:px-1 tw:text-sm! tw:font-semibold!">
                Re-solve selected basket
              </legend>
              <topNForm.Field name="topN">
                <template #default="{ field }">
                  <UiField class="top-n-control">
                    <FieldLabel for="recommendation-top-n">Top N groups by API rank</FieldLabel>
                    <Input
                      id="recommendation-top-n"
                      type="number"
                      min="1"
                      :model-value="String(field.state.value)"
                      :disabled="!canChangeSelection"
                      :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                      :aria-describedby="
                        field.state.meta.errors.length ? 'recommendation-top-n-error' : undefined
                      "
                      @update:model-value="setTopN"
                      @blur="field.handleBlur"
                    />
                    <FieldError id="recommendation-top-n-error" :errors="field.state.meta.errors" />
                  </UiField>
                </template>
              </topNForm.Field>
              <Button
                type="button"
                variant="outline"
                size="sm"
                class="secondary-button tw:whitespace-normal"
                :disabled="!canChangeSelection"
                @click="selectTopGroups"
              >
                Select top N and re-solve
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                class="secondary-button tw:whitespace-normal"
                :disabled="!canChangeSelection"
                @click="clearSelection"
              >
                Clear selected groups and re-solve
              </Button>
              <p
                v-if="!canChangeSelection"
                class="read-only-note tw:m-0! tw:text-sm! tw:text-muted-foreground tw:sm:col-span-3"
              >
                Saved, stale, or unverified run context is read-only. Open/run a current matching
                run to change selection.
              </p>
              <p
                v-else
                class="read-only-note tw:m-0! tw:text-sm! tw:text-muted-foreground tw:sm:col-span-3"
              >
                Group selection and individual SELL-lot selection re-solve through the API. Shared
                BUY legs cannot be toggled independently.
              </p>
            </fieldset>

            <p
              v-if="filteredGroups.length === 0"
              class="empty-inline tw:m-0! tw:text-sm! tw:text-muted-foreground"
            >
              No returned groups match these filters.
            </p>
            <div v-else class="group-list tw:grid tw:min-w-0 tw:gap-2">
              <TradeGroup
                v-for="group in filteredGroups"
                :key="group.group_id"
                :group="group"
                :legs="groupDetailLegs(group)"
                :leg-references="groupLegReferences(group)"
                :sleeve-label="sleeveLabel(group.sleeve_key)"
                :has-sell-lots="groupSellLotIdsFor(group).length > 0"
                :has-shared-leg="group.leg_ids.some(isSharedLeg)"
                :note-draft="noteDrafts[group.group_id] ?? ''"
                :rejection-draft="rejectionDrafts[group.group_id] ?? ''"
                :can-change-selection="canChangeSelection"
                :pending="runPresentation.reviewMutationPending"
                @group-selection="changeGroupSelection"
                @lot-selection="changeLotSelection"
                @note-draft-change="changeNoteDraft"
                @rejection-draft-change="changeRejectionDraft"
                @save-note="saveNote"
                @reject-group="rejectGroup"
                @restore-group="restoreGroup"
              />
            </div>

            <section
              v-if="visibleSharedLegs.length"
              class="shared-legs tw:grid tw:min-w-0 tw:gap-2 tw:border-t tw:border-border tw:pt-4"
              aria-labelledby="shared-legs-title"
            >
              <h3 class="tw:m-0! tw:text-sm! tw:font-semibold!" id="shared-legs-title">
                Shared consolidated legs · each canonical leg shown once
              </h3>
              <p class="tw:m-0! tw:text-sm! tw:text-muted-foreground">
                These API legs are referenced by multiple groups. A shared BUY cannot be toggled
                independently.
              </p>
              <article
                v-for="leg in visibleSharedLegs"
                :key="leg.leg_id"
                class="shared-leg-card tw:min-w-0"
              >
                <RecommendationLegDetails :leg="leg" :id="legAnchor(leg.leg_id)" />
                <p class="tw:mt-2! tw:mb-0! tw:break-words tw:text-sm!">
                  <strong>Linked groups:</strong> {{ leg.group_ids.join(', ') }}
                </p>
                <p
                  v-if="leg.dependencies.length"
                  class="tw:mt-1! tw:mb-0! tw:break-words tw:text-sm!"
                >
                  <strong>Leg dependencies:</strong> {{ leg.dependencies.join(', ') }}
                </p>
              </article>
            </section>

            <Alert
              v-if="visibleUnlinkedLegs.length"
              role="region"
              aria-label="Unlinked API legs"
              class="tw:gap-2"
            >
              <div class="tw:grid tw:min-w-0 tw:gap-2">
                <h3 class="tw:m-0! tw:text-sm! tw:font-semibold!">
                  Unlinked API legs — not executable
                </h3>
                <article
                  v-for="leg in visibleUnlinkedLegs"
                  :key="leg.leg_id"
                  class="unlinked-leg-card tw:min-w-0"
                >
                  <RecommendationLegDetails :leg="leg" :id="legAnchor(leg.leg_id)" />
                  <p class="tw:mt-2! tw:mb-0! tw:text-sm! tw:text-muted-foreground">
                    API group references are missing or inconsistent. Do not treat this leg as an
                    executable recommendation.
                  </p>
                </article>
              </div>
            </Alert>
          </CardContent>
        </Card>
      </section>

      <section
        v-if="!runPresentation.reviewMutationPending"
        class="export-panel tw:min-w-0"
        aria-label="Recommendation export"
      >
        <Card class="tw:min-w-0">
          <CardHeader class="tw:gap-1">
            <h2 class="tw:m-0! tw:text-base! tw:font-semibold!">Export this API run</h2>
            <p class="tw:m-0! tw:text-sm! tw:text-muted-foreground">
              Exports retain the API run, policy, source generation, as-of time, warnings, and
              demo/actionability metadata.
            </p>
          </CardHeader>
          <CardContent class="tw:flex tw:min-w-0 tw:flex-wrap tw:gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              class="secondary-button tw:whitespace-normal"
              :disabled="store.actionState.exportRun.pending"
              @click="exportRun('csv')"
            >
              Export CSV
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              class="secondary-button tw:whitespace-normal"
              :disabled="store.actionState.exportRun.pending"
              @click="exportRun('json')"
            >
              Export JSON
            </Button>
          </CardContent>
        </Card>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, watch } from 'vue';
import { useForm } from '@tanstack/vue-form';
import type { AcceptableValue } from 'reka-ui';
import ApiActionError from '@/components/ApiActionError.vue';
import WorkspaceCapabilityNotice from '@/components/WorkspaceCapabilityNotice.vue';
import WorkspaceEmptyState from '@/components/WorkspaceEmptyState.vue';
import WorkspacePageHeader from '@/components/WorkspacePageHeader.vue';
import RecommendationLegDetails from '@/components/RecommendationLegDetails.vue';
import RunSummary from '@/components/RunSummary.vue';
import TradeGroup from '@/components/TradeGroup.vue';

import ResourceFreshnessNotice from '@/components/ResourceFreshnessNotice.vue';
import AllocationTargets from '@/components/AllocationTargets.vue';
import USAllocationTransition from '@/components/USAllocationTransition.vue';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import {
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  Field as UiField,
} from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { ExportFormat } from '@/services/api';
import {
  recommendationRunFormSchema,
  recommendationFilterDefaults,
  recommendationFilterFormSchema,
  recommendationTopNDefaults,
  recommendationTopNFormSchema,
  savedRunFormSchema,
} from '@/forms/recommendations-page';
import { useWorkspace } from '@/composables/use-workspace';
import type { RecommendationGroupResponse, RecommendationLegResponse } from '@/types/api';
import type {
  GroupActionIntent,
  GroupNoteIntent,
  GroupRejectIntent,
  GroupSelectionIntent,
  GroupTextIntent,
  LotSelectionIntent,
  TradeGroupLegReference,
} from '@/components/trade-review-types';
import {
  canonicalLegs,
  filterGroups,
  groupLegs,
  groupSellLotIds,
  requestGroupSelection,
  requestLotSelection,
  selectionFromRun,
  sharedLegs,
  unlinkedLegs,
} from './recommendations-state';

import { completeFrozenRunSleeveLabels, frozenRunSleeveLabel } from './run-context';
import {
  selectPortfolioLabelContext,
  selectRunPresentation,
  selectWorkspaceReadiness,
} from '@/stores/workspace-selectors';

const store = useWorkspace();
const runForm = useForm({
  defaultValues: { proposedTradeDate: '' },
  validators: { onChange: recommendationRunFormSchema },
  onSubmit: async ({ value }) => {
    if (!canRunOptimizer.value) return;
    try {
      await store.runOptimizer(
        value.proposedTradeDate ? { proposed_trade_date: value.proposedTradeDate } : {},
      );
    } catch {
      // The store retains a structured API error for this page.
    }
  },
});
const savedRunForm = useForm({
  defaultValues: { savedRunId: '' },
  validators: { onChange: savedRunFormSchema },
  onSubmit: async ({ value }) => {
    const runId = value.savedRunId.trim();
    if (!runId) return;
    try {
      await store.openSavedRun(runId);
    } catch {
      // The store retains a structured saved-run error for this page.
    }
  },
});
const savedRunId = savedRunForm.useSelector((state) => state.values.savedRunId);
const filterForm = useForm({
  defaultValues: recommendationFilterDefaults,
  validators: { onChange: recommendationFilterFormSchema },
});
const filters = filterForm.useSelector((state) => state.values);
const topNForm = useForm({
  defaultValues: recommendationTopNDefaults,
  validators: { onChange: recommendationTopNFormSchema },
  onSubmit: async ({ value }) => {
    const run = currentRun.value;
    if (!run) return;
    const count = Math.max(0, Math.floor(Number(value.topN) || 0));
    const selectedGroups = [...run.groups]
      .filter((group) => !group.rejected && groupSellLotIds(run, group).length > 0)
      .sort((left, right) => left.rank - right.rank)
      .slice(0, count);
    await recalculate({
      selected_group_ids: selectedGroups.map((group) => group.group_id),
      selected_sell_lots: Object.fromEntries(
        selectedGroups.map((group) => [group.group_id, groupSellLotIds(run, group)]),
      ),
    });
  },
});
const noteDrafts = reactive<Record<string, string>>({});
const rejectionDrafts = reactive<Record<string, string>>({});

const currentRun = computed(() => store.currentRun);
const savedRunSummary = computed(() => store.currentRunSummary);
const currentRunGroupCount = computed(() => currentRun.value?.groups.length ?? 0);

const portfolio = computed(() => store.portfolio);
const activePolicy = computed(() => store.policy?.active ?? null);
const runPresentation = computed(() =>
  selectRunPresentation({
    run: currentRun.value,
    summary: savedRunSummary.value,
    view: store.currentRunView,
    proposedRunIsStale: store.proposedRunIsStale,
    health: store.health,
    portfolio: portfolio.value,
    activePolicy: activePolicy.value,
    resourceFreshness: store.resourceFreshness,

    resourceReadsPending: store.workspaceResourceLoadPending,
    reviewMutationPending: store.reviewMutationPending,
  }),
);
const runDisplayContext = computed(() => runPresentation.value.displayContext);

const currentRunMatches = computed(() => runPresentation.value.currentRunMatches);
const provenanceLabel = computed(() => runPresentation.value.provenanceLabel);
const currentRunEffectsAreUsable = computed(() => runPresentation.value.effectsAvailable);
const showNoCurrentBasket = computed(
  () => !currentRunMatches.value && store.currentRunView !== 'saved',
);
const workspaceReadiness = computed(() =>
  selectWorkspaceReadiness({
    health: store.health,
    portfolio: portfolio.value,
    activePolicy: activePolicy.value,
    resourceFreshness: store.resourceFreshness,

    resourceReadsPending: store.workspaceResourceLoadPending,
    syncPending: store.actionState.syncPortfolio.pending,
    runPending: store.actionState.runOptimizer.pending,
    openSavedRunPending: store.actionState.openSavedRun.pending,
  }),
);
const canRunOptimizer = computed(() => workspaceReadiness.value.canRunOptimizer);
const canChangeSelection = computed(
  () =>
    currentRunMatches.value &&
    store.currentRunView === 'current' &&
    !store.actionState.syncPortfolio.pending,
);
const runSleeveLabels = computed(() => {
  const run = currentRun.value;
  const allocation = run?.portfolio_effects?.allocation;
  const transition = run?.portfolio_effects?.us_transition;
  return completeFrozenRunSleeveLabels(runDisplayContext.value, [
    ...(run?.groups.map((group) => group.sleeve_key) ?? []),
    ...Object.keys(allocation?.current?.sleeve_weights_pct ?? {}),
    ...Object.keys(allocation?.proposed?.sleeve_weights_pct ?? {}),
    ...Object.keys(allocation?.target?.sleeve_weights_pct ?? {}),
    ...(transition
      ? [
          transition.sleeve_key,
          ...(transition.transition_destination_sleeve_key
            ? [transition.transition_destination_sleeve_key]
            : []),
          ...Object.keys(transition.current.children),
          ...Object.keys(transition.proposed_basket.children),
          ...Object.keys(transition.target.children),
        ]
      : []),
  ]);
});
const portfolioLabelContext = computed(() => {
  const allocation = portfolio.value?.allocation;
  const transition = portfolio.value?.us_transition;
  const sleeveKeys = [
    ...Object.keys(allocation?.current?.sleeve_weights_pct ?? {}),
    ...Object.keys(allocation?.proposed?.sleeve_weights_pct ?? {}),
    ...Object.keys(allocation?.target?.sleeve_weights_pct ?? {}),
    ...(transition
      ? [
          transition.sleeve_key,
          ...(transition.transition_destination_sleeve_key
            ? [transition.transition_destination_sleeve_key]
            : []),
          ...Object.keys(transition.current.children),
          ...Object.keys(transition.proposed_basket.children),
          ...Object.keys(transition.target.children),
        ]
      : []),
  ];
  return selectPortfolioLabelContext({
    portfolio: portfolio.value,
    activePolicy: activePolicy.value,
    sleeveKeys,
  });
});
const effectDisplay = computed(() => {
  if (currentRunEffectsAreUsable.value) {
    return {
      allocation: currentRun.value?.portfolio_effects?.allocation ?? null,
      transition: currentRun.value?.portfolio_effects?.us_transition ?? null,
      labels: runSleeveLabels.value,
      source: store.currentRunView === 'saved' ? ('saved_run' as const) : ('current_run' as const),
    };
  }
  return {
    allocation: portfolio.value?.allocation ?? null,
    transition: portfolio.value?.us_transition ?? null,
    labels: portfolioLabelContext.value.labels,
    source: 'current_portfolio' as const,
  };
});
function hasSelectedTradeBasket(run: NonNullable<typeof store.currentRun>): boolean | null {
  if (!Array.isArray(run.groups) || !Array.isArray(run.consolidated_legs)) return null;
  try {
    return (selectionFromRun(run).selected_group_ids?.length ?? 0) > 0;
  } catch {
    return null;
  }
}
const currentPortfolioTransitionStatus = computed(() => {
  if (store.workspaceResourceLoadPending) return 'pending';
  const freshness = store.resourceFreshness;
  if (
    freshness.health.status === 'stale' ||
    freshness.portfolio.status === 'stale' ||
    freshness.policy.status === 'stale'
  ) {
    return 'stale';
  }
  if (!portfolio.value || portfolio.value.status !== 'ready') return 'unavailable';
  if (
    !portfolio.value.sync.complete ||
    store.health?.status !== 'ok' ||
    !store.health.schema_ready ||
    freshness.health.status !== 'fresh' ||
    freshness.portfolio.status !== 'fresh' ||
    freshness.policy.status !== 'fresh' ||
    !activePolicy.value ||
    !portfolioLabelContext.value.revisionsMatch
  ) {
    return 'unverified';
  }
  return 'confirmed';
});
const transitionSnapshotStatus = computed(() => {
  if (effectDisplay.value.source === 'saved_run') return 'saved';
  if (effectDisplay.value.source === 'current_run') return 'confirmed';
  return currentPortfolioTransitionStatus.value;
});
const transitionBasketStatus = computed(() => {
  if (effectDisplay.value.source === 'current_run' || effectDisplay.value.source === 'saved_run') {
    const run = currentRun.value;
    if (!run) return 'unavailable';
    const hasSelectedTrades = hasSelectedTradeBasket(run);
    if (hasSelectedTrades === null) return 'unverified';
    if (!hasSelectedTrades) return 'no-selection';
    if (!effectDisplay.value.transition) return 'unavailable';
    return effectDisplay.value.source === 'saved_run' ? 'saved' : 'confirmed';
  }
  if (runPresentation.value.state === 'pending') return 'pending';
  if (runPresentation.value.state === 'stale') return 'stale';
  if (runPresentation.value.state === 'unverified') return 'unverified';
  return 'no-selection';
});
const transitionRoleIdentity = computed(() => {
  const sleeves =
    effectDisplay.value.source === 'current_run' || effectDisplay.value.source === 'saved_run'
      ? (runDisplayContext.value?.sleeves ?? null)
      : currentPortfolioTransitionStatus.value === 'confirmed'
        ? (activePolicy.value?.sleeves ?? null)
        : null;
  if (!sleeves) return null;
  const containers = sleeves.filter((sleeve) => sleeve.is_direct_index_container);
  if (containers.length !== 1) return null;
  const containerKey = containers[0]?.sleeve_key ?? null;
  if (!containerKey) return null;
  const children = sleeves.filter((sleeve) => sleeve.parent_sleeve_key === containerKey);
  const legacy = children.filter((sleeve) => sleeve.is_direct_index_sleeve);
  const destinations = children.filter((sleeve) => sleeve.is_transition_destination);
  return {
    containerKey,
    legacyKey: legacy.length === 1 ? (legacy[0]?.sleeve_key ?? null) : null,
    destinationKey: destinations.length === 1 ? (destinations[0]?.sleeve_key ?? null) : null,
  };
});
const effectsDescription = computed(() => runPresentation.value.effectsDescription);
const sleeveOptions = computed(() => {
  const keys = new Set<string>(currentRun.value?.groups.map((group) => group.sleeve_key) ?? []);
  if (filters.value.sleeve) keys.add(filters.value.sleeve);
  return [...keys].sort();
});
const groupTypeOptions = computed(() => {
  const types = new Set<string>(currentRun.value?.groups.map((group) => group.group_type) ?? []);
  if (filters.value.groupType) types.add(filters.value.groupType);
  return [...types].sort();
});
const filteredGroups = computed(() =>
  currentRun.value ? filterGroups(currentRun.value, filters.value, filters.value.sortOrder) : [],
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
  return frozenRunSleeveLabel(runDisplayContext.value, key);
}

function setProposedTradeDate(value: string | number): void {
  runForm.setFieldValue('proposedTradeDate', String(value));
}

function setSavedRunId(value: string | number): void {
  savedRunForm.setFieldValue('savedRunId', String(value));
}

function setTopN(value: string | number): void {
  topNForm.setFieldValue('topN', value);
}

function setSleeveFilter(value: AcceptableValue): void {
  if (value === 'all-sleeves') filterForm.setFieldValue('sleeve', '');
  else if (typeof value === 'string' && value.startsWith('key:')) {
    filterForm.setFieldValue('sleeve', value.slice('key:'.length));
  }
}

function setActionFilter(value: AcceptableValue): void {
  if (value === 'all-actions') filterForm.setFieldValue('action', '');
  else if (value === 'BUY' || value === 'SELL') filterForm.setFieldValue('action', value);
}

function setTermFilter(value: AcceptableValue): void {
  if (value === 'all-terms') filterForm.setFieldValue('term', '');
  else if (value === 'ST' || value === 'LT') filterForm.setFieldValue('term', value);
}

function setBenefitFilter(value: AcceptableValue): void {
  if (value === 'any-benefit') filterForm.setFieldValue('benefit', '');
  else if (value === 'unavailable') filterForm.setFieldValue('benefit', value);
}

function setWarningFilter(value: AcceptableValue): void {
  if (value === 'any-warning-state') filterForm.setFieldValue('warning', '');
  else if (value === 'with' || value === 'without') filterForm.setFieldValue('warning', value);
}

function setGroupTypeFilter(value: AcceptableValue): void {
  if (value === 'all-group-types') filterForm.setFieldValue('groupType', '');
  else if (typeof value === 'string' && value.startsWith('key:')) {
    filterForm.setFieldValue('groupType', value.slice('key:'.length));
  }
}

function setSortOrder(value: AcceptableValue): void {
  if (value === 'rank-ascending' || value === 'rank-descending') {
    filterForm.setFieldValue('sortOrder', value);
  }
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

function groupLegReferences(group: RecommendationGroupResponse): TradeGroupLegReference[] {
  return group.leg_ids.map((legId) => {
    const leg = findLeg(legId);
    if (!leg) return { legId, label: 'Missing API leg', status: 'missing' };
    const status = isUnlinkedLeg(legId) ? 'unlinked' : isSharedLeg(legId) ? 'shared' : 'linked';
    return {
      legId,
      label: `Sequence ${leg.sequence} ${leg.side} ${leg.ticker ?? 'ticker unavailable'}`,
      status,
    };
  });
}

function legAnchor(legId: string): string {
  return `leg-${encodeURIComponent(legId)}`;
}

function runOptimizer(): void {
  void runForm.handleSubmit();
}

function openSavedRun(): void {
  void savedRunForm.handleSubmit();
}

async function recalculate(
  selection: Parameters<typeof store.recalculateSelection>[0],
): Promise<void> {
  if (!canChangeSelection.value) return;
  try {
    await store.recalculateSelection(selection);
  } catch {
    // Keep the last successful response and expose the API failure above.
  }
}

function changeGroupSelection({ groupId, selected }: GroupSelectionIntent): void {
  const run = currentRun.value;
  if (!run) return;
  void recalculate(requestGroupSelection(run, groupId, selected));
}

function changeLotSelection({ groupId, brokerLotId, selected }: LotSelectionIntent): void {
  const run = currentRun.value;
  if (!run) return;
  void recalculate(requestLotSelection(run, groupId, brokerLotId, selected));
}
function selectTopGroups(): void {
  void topNForm.handleSubmit();
}

function clearSelection(): void {
  void recalculate({ selected_group_ids: [], selected_sell_lots: {} });
}

function changeNoteDraft({ groupId, value }: GroupTextIntent): void {
  noteDrafts[groupId] = value;
}

function changeRejectionDraft({ groupId, value }: GroupTextIntent): void {
  rejectionDrafts[groupId] = value;
}

async function saveNote({ groupId, note: submittedDraft }: GroupNoteIntent): Promise<void> {
  const run = currentRun.value;
  if (!run || !canChangeSelection.value || !run.groups.some((group) => group.group_id === groupId))
    return;
  const note = submittedDraft.trim() || null;
  try {
    await store.annotateGroup(run.run_id, groupId, { note });
    const current = currentRun.value;
    const publishedGroup = current?.groups.find((item) => item.group_id === groupId);
    if (
      current?.run_id === run.run_id &&
      publishedGroup?.note === note &&
      noteDrafts[groupId] === submittedDraft
    ) {
      noteDrafts[groupId] = publishedGroup.note ?? '';
    }
  } catch {
    // The store retains a structured API error for the page.
  }
}

async function rejectGroup({ groupId, reason: submittedDraft }: GroupRejectIntent): Promise<void> {
  const run = currentRun.value;
  if (!run || !canChangeSelection.value || !run.groups.some((group) => group.group_id === groupId))
    return;
  const reason = submittedDraft.trim();
  if (!reason || reason.length > 500) return;
  try {
    await store.annotateGroup(run.run_id, groupId, {
      rejected: true,
      rejection_reason: reason,
    });
    const current = currentRun.value;
    const publishedGroup = current?.groups.find((item) => item.group_id === groupId);
    if (
      current?.run_id === run.run_id &&
      publishedGroup?.rejected === true &&
      publishedGroup.rejection_reason === reason &&
      rejectionDrafts[groupId] === submittedDraft
    ) {
      rejectionDrafts[groupId] = publishedGroup.rejection_reason ?? '';
    }
  } catch {
    // Rejection failed; the last API-confirmed full basket remains in view.
  }
}

async function restoreGroup({ groupId }: GroupActionIntent): Promise<void> {
  const run = currentRun.value;
  if (!run || !canChangeSelection.value || !run.groups.some((group) => group.group_id === groupId))
    return;
  try {
    await store.annotateGroup(run.run_id, groupId, {
      rejected: false,
    });
  } catch {
    // The store retains a structured API error for the page.
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

onMounted(() => {
  void store.ensureInitialWorkspace();
});
</script>
