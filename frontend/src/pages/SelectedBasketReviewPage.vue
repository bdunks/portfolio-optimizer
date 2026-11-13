<template>
  <main
    class="workspace-page tw:mx-auto tw:grid tw:min-w-0 tw:max-w-6xl tw:gap-5 tw:px-4 tw:py-6 tw:sm:px-6"
  >
    <WorkspacePageHeader
      eyebrow="Informational review"
      title="Selected trades"
      title-id="selected-basket-review-title"
      subtitle="Review only the API-confirmed selected basket and its exact proposed SELL lot attribution. This page does not authorize orders."
    >
      <template #actions>
        <Button as-child variant="outline" size="sm">
          <RouterLink to="/recommendations">Back to Recommendations</RouterLink>
        </Button>
      </template>
    </WorkspacePageHeader>

    <WorkspaceCapabilityNotice label="INFORMATIONAL REVIEW · NOT ORDER APPROVAL">
      This read-only view cannot preview, approve, or submit orders. API-proposed shares and sale
      lots are not current available inventory. DEMO data remains hypothetical and non-actionable.
    </WorkspaceCapabilityNotice>

    <Alert role="status" aria-live="polite" :data-review-state="presentation.state">
      <AlertDescription>{{ stateMessage }}</AlertDescription>
    </Alert>

    <section
      class="tw:min-w-0 tw:rounded-lg tw:border tw:border-border tw:p-4"
      aria-labelledby="review-context-title"
    >
      <h2 id="review-context-title" class="tw:m-0! tw:text-base tw:font-semibold">
        Run and policy provenance
      </h2>
      <dl
        class="tw:mt-3 tw:grid tw:min-w-0 tw:grid-cols-1 tw:gap-3 tw:sm:grid-cols-2 tw:xl:grid-cols-3"
      >
        <div>
          <dt>Run ID</dt>
          <dd>{{ displayRecord?.run_id ?? 'Unavailable' }}</dd>
        </div>
        <div>
          <dt>Run policy revision</dt>
          <dd>{{ displayRecord?.policy_revision_id ?? 'Unavailable' }}</dd>
        </div>
        <div>
          <dt>Run source generation</dt>
          <dd>{{ displayRecord?.source_generation ?? 'Unavailable' }}</dd>
        </div>
        <div>
          <dt>Run as of</dt>
          <dd>{{ displayRecord?.as_of ?? 'Unavailable' }}</dd>
        </div>
        <div>
          <dt>Current portfolio generation</dt>
          <dd>{{ portfolioGenerationLabel }}</dd>
        </div>
        <div>
          <dt>Frozen policy provenance</dt>
          <dd v-if="frozenContext?.available">
            Revision {{ frozenContext.policy_revision_id }} ·
            {{ frozenContext.source ?? 'Unavailable source' }}
          </dd>
          <dd v-else>
            Unavailable ({{ frozenContext?.unavailable_reason ?? 'not returned by the API' }}).
            Current policy is not used to reconstruct run history.
          </dd>
        </div>
      </dl>
    </section>

    <template v-if="canShowSelectedBasket && selectedCanonicalLegs.length > 0">
      <section
        class="tw:min-w-0 tw:rounded-lg tw:border tw:border-border tw:p-4"
        aria-labelledby="selected-basket-financials-title"
      >
        <h2 id="selected-basket-financials-title" class="tw:m-0! tw:text-base tw:font-semibold">
          Selected basket financial summary
        </h2>
        <p class="tw:mb-0 tw:mt-2 tw:text-sm tw:text-muted-foreground">
          Gross losses count only negative realized P/L on selected SELL lots. Signed ST/LT and net
          P/L are the API run estimates; estimated tax benefit is a separate API field.
        </p>
        <dl
          class="tw:mt-3 tw:grid tw:min-w-0 tw:grid-cols-1 tw:gap-3 tw:sm:grid-cols-2 tw:xl:grid-cols-3"
        >
          <div>
            <dt>Selected canonical orders</dt>
            <dd>{{ selectedCanonicalLegs.length }}</dd>
          </div>
          <div>
            <dt>Selected SELL broker lots</dt>
            <dd>{{ selectedSellLotCount }}</dd>
          </div>
          <div>
            <dt>Gross losses (selected SELL lots only)</dt>
            <dd>
              {{
                formatUsd(
                  grossLossUsd,
                  'Unavailable (selected-lot realized P/L is missing or malformed)',
                )
              }}
            </dd>
          </div>
          <div>
            <dt>Signed realized ST P/L (API estimate)</dt>
            <dd>
              {{ formatUsd(realizedStUsd, 'Unavailable (not returned as a valid API decimal)') }}
            </dd>
          </div>
          <div>
            <dt>Signed realized LT P/L (API estimate)</dt>
            <dd>
              {{ formatUsd(realizedLtUsd, 'Unavailable (not returned as a valid API decimal)') }}
            </dd>
          </div>
          <div>
            <dt>Signed net realized P/L (ST + LT)</dt>
            <dd>
              {{
                formatUsd(
                  netRealizedUsd,
                  'Unavailable (ST/LT API estimates are missing or malformed)',
                )
              }}
            </dd>
          </div>
          <div>
            <dt>Estimated tax benefit (distinct from gross losses)</dt>
            <dd>
              {{
                formatUsd(
                  run?.estimated_tax_benefit_usd,
                  `Unavailable (${run?.estimated_tax_benefit_status ?? 'not returned by API'})`,
                )
              }}
            </dd>
          </div>
        </dl>
      </section>

      <section
        class="tw:grid tw:min-w-0 tw:gap-3"
        aria-labelledby="selected-canonical-orders-title"
      >
        <div>
          <h2 id="selected-canonical-orders-title" class="tw:m-0! tw:text-base tw:font-semibold">
            Selected canonical orders
          </h2>
          <p class="tw:mb-0 tw:mt-1 tw:text-sm tw:text-muted-foreground">
            Shared BUY legs appear once. Sequence and dependencies are API supplied; only selected
            SELL lots are listed.
          </p>
        </div>
        <div
          v-for="leg in selectedCanonicalLegs"
          :key="leg.leg_id"
          class="tw:grid tw:min-w-0 tw:gap-3"
        >
          <RecommendationLegDetails :leg="leg" />
          <SellLotAttribution
            v-if="leg.side === 'SELL'"
            :leg="selectedSellLegForDisplay(leg)"
            :can-change-selection="false"
            :show-selection-controls="false"
          />
        </div>
      </section>
    </template>

    <WorkspaceEmptyState v-else-if="canShowSelectedBasket" title="No trades selected">
      The API confirms that this {{ presentation.state === 'saved' ? 'historical ' : '' }}run has no
      selected canonical legs. No basket totals or order details are shown.
    </WorkspaceEmptyState>

    <WorkspaceEmptyState v-else-if="!run" title="No recommendation details available">
      {{
        displayRecord
          ? 'A run summary is available, but its recommendation details are not loaded.'
          : 'No recommendation run is loaded.'
      }}
      This page does not automatically analyze a portfolio. Use Recommendations to run a DEMO
      analysis or reopen a saved run.
    </WorkspaceEmptyState>

    <RouterLink
      class="tw:justify-self-start tw:text-sm tw:font-medium tw:text-primary tw:underline-offset-4 hover:tw:underline"
      to="/recommendations"
    >
      Back to Recommendations to edit the selection
    </RouterLink>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { RouterLink } from 'vue-router';
import SellLotAttribution from '@/components/SellLotAttribution.vue';
import RecommendationLegDetails from '@/components/RecommendationLegDetails.vue';
import WorkspaceCapabilityNotice from '@/components/WorkspaceCapabilityNotice.vue';
import WorkspaceEmptyState from '@/components/WorkspaceEmptyState.vue';
import WorkspacePageHeader from '@/components/WorkspacePageHeader.vue';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { useWorkspace } from '@/composables/use-workspace';
import type { RecommendationLegResponse } from '@/types/api';
import { canonicalLegs } from '@/pages/recommendations-state';
import { selectRunPresentation } from '@/stores/workspace-selectors';
import { formatUsd } from '@/utils/display-values';
import { isNegativeExactUsd, sumExactUsd } from '@/utils/exact-usd';

const store = useWorkspace();

const run = computed(() => store.currentRun);
const summary = computed(() => store.currentRunSummary);
const displayRecord = computed(() => run.value ?? summary.value);
const presentation = computed(() =>
  selectRunPresentation({
    run: run.value,
    summary: summary.value,
    view: store.currentRunView,
    proposedRunIsStale: store.proposedRunIsStale,
    health: store.health,
    portfolio: store.portfolio,
    activePolicy: store.policy?.active ?? null,
    resourceFreshness: store.resourceFreshness,
    resourceReadsPending: store.workspaceResourceLoadPending,
    reviewMutationPending: store.reviewMutationPending,
  }),
);
const frozenContext = computed(() => presentation.value.displayContext);
const basketPayloadAvailable = computed(
  () => Array.isArray(run.value?.groups) && Array.isArray(run.value?.consolidated_legs),
);
const canShowSelectedBasket = computed(
  () =>
    basketPayloadAvailable.value &&
    (presentation.value.currentRunMatches || presentation.value.state === 'saved'),
);
// canonicalLegs deduplicates by leg_id and sorts by API sequence before this selected-only filter.
const selectedCanonicalLegs = computed(() =>
  canShowSelectedBasket.value && run.value
    ? canonicalLegs(run.value).filter((leg) => leg.selected)
    : [],
);
const selectedSellLegs = computed(() =>
  selectedCanonicalLegs.value.filter((leg) => leg.side === 'SELL'),
);
const selectedSellLots = computed(() =>
  selectedSellLegs.value.flatMap((leg) =>
    Array.isArray(leg.selected_lots) ? leg.selected_lots.filter((lot) => lot.selected) : [],
  ),
);
const selectedSellLotCount = computed(
  () => new Set(selectedSellLots.value.map((lot) => lot.broker_lot_id)).size,
);
const grossLossUsd = computed(() => {
  if (!canShowSelectedBasket.value) return null;
  if (selectedSellLegs.value.length === 0) return '0.00';
  const negativeLotValues: string[] = [];
  for (const leg of selectedSellLegs.value) {
    if (!Array.isArray(leg.selected_lots)) return null;
    const selectedLots = leg.selected_lots.filter((lot) => lot.selected);
    if (selectedLots.length === 0) return null;
    for (const lot of selectedLots) {
      const isNegative = isNegativeExactUsd(lot.realized_pl_usd);
      if (isNegative === null) return null;
      if (isNegative) negativeLotValues.push(lot.realized_pl_usd);
    }
  }
  if (negativeLotValues.length === 0) return '0.00';
  const negativeTotal = sumExactUsd(negativeLotValues);
  return negativeTotal?.startsWith('-') ? negativeTotal.slice(1) : negativeTotal;
});
const realizedStUsd = computed(() => validApiUsd(run.value?.estimated_realized_st_usd));
const realizedLtUsd = computed(() => validApiUsd(run.value?.estimated_realized_lt_usd));
const netRealizedUsd = computed(() => sumExactUsd([realizedStUsd.value, realizedLtUsd.value]));
const portfolioGenerationLabel = computed(() => {
  if (presentation.value.currentRunMatches)
    return store.portfolio?.sync.generation ?? 'Unavailable';
  if (presentation.value.state === 'saved') return 'Not overlaid on historical run';
  return 'Unavailable until current run provenance is verified';
});
const stateMessage = computed(() => {
  switch (presentation.value.state) {
    case 'pending':
      return 'A selection update is pending API confirmation. The previous basket, legs, and financial totals are withheld.';
    case 'stale':
      return 'This run is stale. Current basket details and totals are withheld until Recommendations verifies a current run.';
    case 'unverified':
      return 'This run cannot be verified against fresh portfolio and policy provenance. Current basket details and totals are withheld.';
    case 'saved':
      return 'Historical saved run · frozen API context · read-only. This is not the current portfolio basket.';
    case 'current':
      return canShowSelectedBasket.value
        ? 'Current run and selection are confirmed by the API. This informational review is not order approval.'
        : 'Current run provenance is confirmed, but recommendation details are unavailable; no basket is shown.';
    default:
      return displayRecord.value
        ? 'Run context is available but not verified as a current or frozen saved recommendation; basket details are withheld.'
        : 'No run is loaded. Use Recommendations to run a DEMO analysis or reopen a saved run; this page does not analyze automatically.';
  }
});

function validApiUsd(value: string | null | undefined): string | null {
  return isNegativeExactUsd(value) === null ? null : (value ?? null);
}

function selectedSellLegForDisplay(leg: RecommendationLegResponse): RecommendationLegResponse {
  return {
    ...leg,
    selected_lots: Array.isArray(leg.selected_lots)
      ? leg.selected_lots.filter((lot) => lot.selected)
      : [],
  };
}

onMounted(() => {
  const title = document.getElementById('selected-basket-review-title');
  title?.setAttribute('tabindex', '-1');
  title?.focus();
  void store.ensureInitialWorkspace();
});
</script>
