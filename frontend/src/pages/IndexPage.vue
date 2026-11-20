<template>
  <section
    class="workspace-page overview-page tw:mx-auto tw:w-full tw:max-w-[1800px] tw:gap-4 tw:px-4 tw:py-4"
    aria-labelledby="overview-title"
  >
    <WorkspacePageHeader
      eyebrow="Workspace overview"
      title="Overview"
      title-id="overview-title"
      subtitle="Current account state and API-supplied allocation context for a single local workspace."
    >
      <template #actions>
        <Button
          type="button"
          variant="outline"
          class="overview-page-action tw:min-w-0 tw:whitespace-normal"
          :disabled="store.actionState.syncPortfolio.pending"
          :aria-busy="store.actionState.syncPortfolio.pending"
          @click="syncPortfolio"
        >
          <LoaderCircle
            v-if="store.actionState.syncPortfolio.pending"
            aria-hidden="true"
            data-icon="inline-start"
            class="tw:animate-spin"
          />
          <RefreshCw v-else aria-hidden="true" data-icon="inline-start" />
          {{ store.actionState.syncPortfolio.pending ? 'Syncing portfolio…' : 'Sync portfolio' }}
        </Button>
        <Button
          type="button"
          variant="default"
          class="overview-page-action tw:min-w-0 tw:whitespace-normal"
          :disabled="!canRunOptimizer"
          :aria-busy="store.actionState.runOptimizer.pending"
          @click="runOptimizer"
        >
          <LoaderCircle
            v-if="store.actionState.runOptimizer.pending"
            aria-hidden="true"
            data-icon="inline-start"
            class="tw:animate-spin"
          />
          <Play v-else aria-hidden="true" data-icon="inline-start" />
          {{
            store.actionState.runOptimizer.pending
              ? 'Running recommendations…'
              : 'Run DEMO recommendations'
          }}
        </Button>
      </template>
    </WorkspacePageHeader>

    <Alert v-if="!canRunOptimizer" role="status" aria-live="polite" class="tw:border-border">
      <AlertDescription>
        Recommendations require a ready portfolio snapshot and a valid active policy. Nothing runs
        automatically.
      </AlertDescription>
    </Alert>

    <div class="tw:grid tw:gap-2" aria-label="Workspace request errors">
      <ApiActionError
        :error="store.actionState.loadHealth.error"
        title="Application health could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.loadPortfolio.error"
        title="Portfolio data could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.loadPolicy.error"
        title="Allocation policy could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.syncPortfolio.error"
        title="Portfolio sync or refresh failed"
      />
      <ApiActionError
        :error="store.actionState.runOptimizer.error"
        title="Recommendation run failed"
      />
    </div>

    <ResourceFreshnessNotice />
    <Alert
      v-if="portfolioLabelContext.revisionMismatch"
      role="status"
      aria-live="polite"
      class="tw:border-border"
    >
      <AlertDescription>
        Portfolio effects use policy revision
        {{ portfolioLabelContext.portfolioRevisionId ?? 'unavailable' }}; the active policy is
        {{ portfolioLabelContext.policyRevisionId ?? 'unavailable' }}. Cached values remain visible
        with API sleeve keys until matching policy labels are confirmed.
      </AlertDescription>
    </Alert>
    <WorkspaceCapabilityNotice label="DEMO analysis only.">
      Recommendations are non-actionable; no broker calls, OAuth, live writes, or orders are
      available.
    </WorkspaceCapabilityNotice>

    <section
      class="summary-grid overview-summary-grid tw:grid tw:grid-cols-1 tw:gap-4 tw:sm:grid-cols-2 tw:xl:grid-cols-4"
      aria-label="Current optimization outcomes"
    >
      <Card class="summary-card tw:min-w-0">
        <CardHeader class="tw:gap-1 tw:pb-2">
          <CardTitle
            role="heading"
            aria-level="2"
            class="tw:text-sm tw:font-medium tw:text-muted-foreground"
          >
            Selected gross losses
          </CardTitle>
        </CardHeader>
        <CardContent class="tw:grid tw:gap-1">
          <p class="tw:m-0! tw:text-2xl tw:font-semibold tw:tracking-tight tw:tabular-nums">
            {{
              overviewHasSelectedBasket && overviewGrossLossUsd !== null
                ? formatUsd(overviewGrossLossUsd)
                : 'Unavailable'
            }}
          </p>
          <CardDescription>
            {{
              overviewHasSelectedBasket
                ? 'Gross losses from selected SELL lots only'
                : 'No selected current recommendation basket'
            }}
          </CardDescription>
        </CardContent>
      </Card>
      <Card class="summary-card tw:min-w-0">
        <CardHeader class="tw:gap-1 tw:pb-2">
          <CardTitle
            role="heading"
            aria-level="2"
            class="tw:text-sm tw:font-medium tw:text-muted-foreground"
          >
            Estimated tax benefit
          </CardTitle>
        </CardHeader>
        <CardContent class="tw:grid tw:gap-1">
          <p class="tw:m-0! tw:text-2xl tw:font-semibold tw:tracking-tight tw:tabular-nums">
            {{ overviewTaxBenefitLabel }}
          </p>
          <CardDescription>{{ overviewTaxBenefitExplanation }}</CardDescription>
        </CardContent>
      </Card>
      <Card class="summary-card tw:min-w-0">
        <CardHeader class="tw:gap-1 tw:pb-2">
          <CardTitle
            role="heading"
            aria-level="2"
            class="tw:text-sm tw:font-medium tw:text-muted-foreground"
          >
            Estimated realized P/L
          </CardTitle>
        </CardHeader>
        <CardContent class="tw:grid tw:gap-1">
          <dl class="tw:m-0! tw:grid tw:grid-cols-[auto_1fr] tw:gap-x-2 tw:text-sm tw:tabular-nums">
            <dt class="tw:text-muted-foreground">ST</dt>
            <dd class="tw:m-0! tw:text-right">{{ overviewRealizedStLabel }}</dd>
            <dt class="tw:text-muted-foreground">LT</dt>
            <dd class="tw:m-0! tw:text-right">{{ overviewRealizedLtLabel }}</dd>
            <dt class="tw:font-medium">Net</dt>
            <dd class="tw:m-0! tw:text-right tw:font-medium">{{ overviewRealizedNetLabel }}</dd>
          </dl>
          <CardDescription>Signed run estimates for the selected current basket</CardDescription>
        </CardContent>
      </Card>
      <Card class="summary-card tw:min-w-0">
        <CardHeader class="tw:gap-1 tw:pb-2">
          <CardTitle
            role="heading"
            aria-level="2"
            class="tw:text-sm tw:font-medium tw:text-muted-foreground"
          >
            Risk tracking
          </CardTitle>
        </CardHeader>
        <CardContent class="tw:grid tw:gap-1">
          <p class="tw:m-0! tw:text-2xl tw:font-semibold tw:tracking-tight">Unavailable</p>
          <CardDescription>No risk estimate is provided by this workflow</CardDescription>
        </CardContent>
      </Card>
    </section>

    <section class="content-grid tw:grid tw:items-start tw:gap-4 tw:lg:grid-cols-2">
      <Card class="workspace-card transition-card tw:min-w-0 tw:lg:col-span-full">
        <CardContent class="tw:pt-4">
          <USAllocationTransition
            :transition="usTransition"
            :labels="effectLabels"
            :snapshot-status="transitionSnapshotStatus"
            :basket-status="transitionBasketStatus"
            :role-identity="transitionRoleIdentity"
            :provenance="transitionProvenance"
          />
        </CardContent>
      </Card>

      <Card class="workspace-card allocation-card tw:min-w-0">
        <CardContent class="tw:pt-4">
          <div class="tw:mb-4 tw:flex tw:flex-wrap tw:items-start tw:justify-between tw:gap-3">
            <div class="tw:grid tw:gap-1">
              <h2 class="tw:m-0! tw:text-lg! tw:font-semibold!">ETF Look-Through</h2>
              <p class="tw:m-0! tw:text-sm tw:text-muted-foreground">
                Refresh cached fund holdings explicitly. A new recommendation run will use refreshed
                data; saved runs and targets are unchanged.
              </p>
              <p
                v-if="exposureLoadError"
                role="status"
                aria-live="polite"
                class="tw:m-0! tw:text-sm"
              >
                {{ exposureLoadError }}
              </p>
              <p
                v-if="exposureError"
                role="alert"
                aria-live="assertive"
                class="tw:m-0! tw:text-sm tw:text-destructive"
              >
                {{ exposureError }}
              </p>
              <ul
                v-if="exposureCache?.length"
                class="tw:m-0! tw:list-none tw:p-0 tw:text-sm"
                aria-label="ETF look-through cache status"
              >
                <li v-for="item in exposureCache" :key="item.ticker">
                  {{ item.ticker }}:
                  {{ item.freshness === 'configured_missing' ? 'not yet cached' : item.freshness }}
                  <template v-if="item.as_of_date">
                    · holdings as of {{ item.as_of_date }}</template
                  >
                  <template v-if="item.dimensions.length">
                    · observed coverage fractions
                    {{
                      item.dimensions
                        .map((dimension) => `${dimension.dimension} ${dimension.covered_weight}`)
                        .join(', ')
                    }}
                  </template>
                  <template v-if="item.last_attempt_status === 'failure'">
                    · latest refresh failed{{
                      item.last_error_summary ? `: ${item.last_error_summary}` : ''
                    }}
                  </template>
                </li>
              </ul>
              <p
                v-else-if="exposureCache && !exposureCache.length"
                role="status"
                class="tw:m-0! tw:text-sm"
              >
                No look-through source is configured.
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              :disabled="exposurePending"
              :aria-busy="exposurePending"
              @click="refreshExposure"
            >
              <LoaderCircle
                v-if="exposurePending"
                aria-hidden="true"
                data-icon="inline-start"
                class="tw:animate-spin"
              />
              <RefreshCw v-else aria-hidden="true" data-icon="inline-start" />
              {{ exposurePending ? 'Refreshing ETF Look-Through…' : 'Refresh ETF Look-Through' }}
            </Button>
          </div>
          <AllocationTargets
            :allocation="allocation"
            :labels="effectLabels"
            :show-no-current-basket="!currentRunAllocationAvailable"
          />
        </CardContent>
      </Card>
      <Card class="workspace-card run-card tw:min-w-0">
        <CardHeader
          class="tw:gap-3 tw:md:flex tw:md:flex-row tw:md:items-start tw:md:justify-between"
        >
          <div class="tw:grid tw:gap-2">
            <h2 class="tw:m-0! tw:text-lg! tw:font-semibold! tw:leading-tight!">
              Latest recommendations
            </h2>
            <CardDescription>
              Metrics are shown only for a run matching this current portfolio and active policy.
            </CardDescription>
          </div>
          <Badge v-if="currentRunMatches" as="span" variant="outline" class="tw:shrink-0">
            DEMO · non-actionable
          </Badge>
        </CardHeader>
        <CardContent class="tw:grid tw:gap-4">
          <Empty
            v-if="!overviewRun"
            role="status"
            aria-live="polite"
            class="tw:border-border tw:p-4"
          >
            <EmptyHeader class="tw:max-w-none">
              <EmptyTitle role="heading" aria-level="3">{{
                runPresentation.reviewMutationPending
                  ? 'Updating current selection'
                  : 'No current matching recommendation run'
              }}</EmptyTitle>
              <EmptyDescription>
                {{
                  runPresentation.reviewMutationPending
                    ? 'Current totals and previews are withheld until the API confirms the changed selection.'
                    : 'Saved or stale runs are not used as current portfolio comparisons.'
                }}
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
          <Empty
            v-else-if="!overviewHasSelectedBasket"
            role="status"
            aria-live="polite"
            class="tw:border-border tw:p-4"
          >
            <EmptyHeader class="tw:max-w-none">
              <EmptyTitle role="heading" aria-level="3"
                >No selected recommendation groups</EmptyTitle
              >
              <EmptyDescription>
                Select coherent groups in Recommendations to populate an overview preview; no
                proposed trades are assumed.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
          <section v-else class="tw:grid tw:gap-4" aria-labelledby="overview-preview-title">
            <div class="tw:grid tw:gap-1">
              <h3
                id="overview-preview-title"
                class="tw:m-0! tw:text-base! tw:font-semibold! tw:leading-tight"
              >
                Selected ranked trade groups
              </h3>
              <p class="tw:m-0! tw:text-sm tw:text-muted-foreground">
                Highest priorities first. Selection and filtering remain in Recommendations.
              </p>
            </div>
            <ol v-if="overviewPreviewGroups.length" class="tw:m-0! tw:grid tw:gap-3 tw:p-0!">
              <li
                v-for="preview in overviewPreviewGroups"
                :key="preview.group.group_id"
                class="tw:list-none tw:rounded-md tw:border tw:border-border tw:p-3"
              >
                <article class="tw:grid tw:gap-2">
                  <div class="tw:flex tw:flex-wrap tw:items-center tw:gap-2">
                    <Badge as="span" variant="secondary">Priority {{ preview.group.rank }}</Badge>
                    <strong
                      >SELL ·
                      {{
                        preview.group.sleeve_key !== null
                          ? (effectLabels[preview.group.sleeve_key] ?? preview.group.sleeve_key)
                          : 'Sleeve unavailable (not returned by API)'
                      }}</strong
                    >
                  </div>
                  <p class="tw:m-0! tw:text-sm">{{ preview.group.rationale }}</p>
                  <div v-if="preview.sells.length" class="tw:grid tw:gap-2">
                    <div
                      v-for="sell in preview.sells"
                      :key="sell.leg.leg_id"
                      class="tw:grid tw:gap-1 tw:border-l-2 tw:border-border tw:pl-3"
                    >
                      <strong class="tw:text-sm"
                        >SELL {{ sell.leg.ticker ?? 'Security unavailable' }}</strong
                      >
                      <ul v-if="sell.lots.length" class="tw:m-0! tw:grid tw:gap-1 tw:p-0!">
                        <li
                          v-for="lot in sell.lots"
                          :key="lot.broker_lot_id"
                          class="tw:list-none tw:break-words tw:text-sm tw:text-muted-foreground"
                        >
                          {{ lot.shares }} shares · lot {{ lot.broker_lot_id }} · {{ lot.st_lt }} ·
                          P/L {{ formatUsd(lot.realized_pl_usd) }}
                        </li>
                      </ul>
                      <p v-else class="tw:m-0! tw:text-sm tw:text-muted-foreground">
                        Selected SELL leg returned no selected lot details.
                      </p>
                    </div>
                  </div>
                  <p v-else class="tw:m-0! tw:text-sm tw:text-muted-foreground">
                    No selected SELL leg was returned for this group.
                  </p>
                  <p class="tw:m-0! tw:text-sm tw:text-muted-foreground">
                    Signed group P/L · ST
                    {{
                      formatUsd(
                        preview.group.impact?.realized_st_usd,
                        'Unavailable (not returned by API)',
                      )
                    }}
                    · LT
                    {{
                      formatUsd(
                        preview.group.impact?.realized_lt_usd,
                        'Unavailable (not returned by API)',
                      )
                    }}
                  </p>
                </article>
              </li>
            </ol>
            <p
              v-if="overviewSelectedGroupIds.length > overviewPreviewGroups.length"
              class="tw:m-0! tw:text-sm tw:text-muted-foreground"
            >
              Showing {{ overviewPreviewGroups.length }} of
              {{ overviewSelectedGroupIds.length }} selected groups; see the full ranked list in
              Recommendations.
            </p>
            <section class="tw:grid tw:gap-2" aria-labelledby="shared-buy-preview-title">
              <h4 id="shared-buy-preview-title" class="tw:m-0! tw:text-sm! tw:font-semibold!">
                Shared replacement BUY preview
              </h4>
              <p class="tw:m-0! tw:text-sm tw:text-muted-foreground">
                Canonical BUY legs are shown once, not repeated across trade groups.
              </p>
              <ul v-if="overviewSelectedBuyLegs.length" class="tw:m-0! tw:grid tw:gap-1 tw:p-0!">
                <li
                  v-for="leg in overviewSelectedBuyLegs"
                  :key="leg.leg_id"
                  class="tw:list-none tw:break-words tw:text-sm"
                >
                  BUY {{ leg.shares }} shares {{ leg.ticker ?? 'security unavailable' }} ·
                  {{ formatUsd(leg.estimated_notional_usd) }} notional
                </li>
              </ul>
              <p v-else class="tw:m-0! tw:text-sm tw:text-muted-foreground">
                No selected replacement BUY leg was returned.
              </p>
            </section>
            <div class="tw:flex tw:flex-wrap tw:gap-2">
              <Button as-child variant="outline" size="sm">
                <RouterLink to="/recommendations">Review ranked recommendations</RouterLink>
              </Button>
              <Button as-child variant="outline" size="sm">
                <RouterLink to="/review">Review selected basket</RouterLink>
              </Button>
            </div>
          </section>
          <RunSummary
            v-if="store.currentRun || store.currentRunSummary"
            mode="overview"
            :run="store.currentRun"
            :summary="store.currentRunSummary"
            :context="runDisplayContext"
            :pending="runPresentation.reviewMutationPending"
            :show-metrics="currentRunMatches"
            :view="store.currentRunView"
          />
          <section class="tw:grid tw:gap-2" aria-label="Supporting current portfolio context">
            <h3 class="tw:m-0! tw:text-sm! tw:font-semibold!">Current portfolio context</h3>
            <dl
              class="tw:m-0! tw:grid tw:grid-cols-1 tw:gap-x-4 tw:gap-y-1 tw:text-sm tw:sm:grid-cols-3"
            >
              <div class="tw:flex tw:justify-between tw:gap-2 tw:sm:block">
                <dt class="tw:text-muted-foreground">Portfolio value</dt>
                <dd class="tw:m-0! tw:font-medium">
                  {{ formatUsd(portfolio?.portfolio_total_usd) }}
                </dd>
              </div>
              <div class="tw:flex tw:justify-between tw:gap-2 tw:sm:block">
                <dt class="tw:text-muted-foreground">Cash</dt>
                <dd class="tw:m-0! tw:font-medium">{{ formatUsd(portfolio?.cash_usd) }}</dd>
              </div>
              <div class="tw:flex tw:justify-between tw:gap-2 tw:sm:block">
                <dt class="tw:text-muted-foreground">Positions</dt>
                <dd class="tw:m-0! tw:font-medium">{{ positionCount }}</dd>
              </div>
            </dl>
          </section>
        </CardContent>
      </Card>

      <Card class="workspace-card policy-card tw:min-w-0">
        <CardHeader
          class="tw:gap-3 tw:md:flex tw:md:flex-row tw:md:items-start tw:md:justify-between"
        >
          <div class="tw:grid tw:gap-2">
            <h2 class="tw:m-0! tw:text-lg! tw:font-semibold! tw:leading-tight!">
              Active allocation policy
            </h2>
            <CardDescription
              >Policy settings and allowed securities supplied by the API</CardDescription
            >
          </div>
          <Badge as="span" :variant="activePolicy ? 'secondary' : 'outline'" class="tw:shrink-0">
            {{ activePolicy ? `Revision ${activePolicy.revision_number}` : 'No active policy' }}
          </Badge>
        </CardHeader>
        <CardContent class="tw:grid tw:gap-4">
          <Empty
            v-if="!activePolicy"
            role="status"
            aria-live="polite"
            class="tw:border-border tw:p-4"
          >
            <EmptyHeader class="tw:max-w-none">
              <EmptyTitle role="heading" aria-level="3">No active policy returned</EmptyTitle>
              <EmptyDescription
                >Allocation targets are unavailable until a policy loads.</EmptyDescription
              >
            </EmptyHeader>
          </Empty>
          <template v-else>
            <div class="tw:grid tw:gap-4">
              <section class="tw:grid tw:gap-2" aria-labelledby="active-sleeves-title">
                <h3 id="active-sleeves-title" class="tw:m-0! tw:text-sm! tw:font-semibold!">
                  Active allocation targets
                </h3>
                <ul
                  v-if="enabledSleeves.length"
                  class="tw:m-0! tw:flex tw:flex-wrap tw:gap-2 tw:p-0!"
                >
                  <li
                    v-for="sleeve in enabledSleeves"
                    :key="sleeve.sleeve_key"
                    class="tw:list-none tw:rounded-md tw:border tw:border-border tw:px-2 tw:py-1 tw:text-sm"
                  >
                    {{ sleeve.display_name }} · {{ formatPercent(sleeve.target_pct) }}
                  </li>
                </ul>
                <p v-else class="tw:m-0! tw:text-sm tw:text-muted-foreground">
                  No enabled targets returned.
                </p>
              </section>
              <section class="tw:grid tw:gap-2" aria-labelledby="direct-index-context-title">
                <h3 id="direct-index-context-title" class="tw:m-0! tw:text-sm! tw:font-semibold!">
                  U.S. direct-index transition
                </h3>
                <p
                  v-if="
                    transitionRoleIdentity?.containerKey &&
                    transitionRoleIdentity.legacyKey &&
                    transitionRoleIdentity.destinationKey
                  "
                  class="tw:m-0! tw:text-sm"
                >
                  Individual equities, VB and VXF default to
                  {{
                    transitionRoleLabels[transitionRoleIdentity.containerKey] ??
                    transitionRoleIdentity.containerKey
                  }}, subject to explicit ticker overrides. Legacy sleeve:
                  {{
                    transitionRoleLabels[transitionRoleIdentity.legacyKey] ??
                    transitionRoleIdentity.legacyKey
                  }}. Configured U.S. new destination:
                  {{
                    transitionRoleLabels[transitionRoleIdentity.destinationKey] ??
                    transitionRoleIdentity.destinationKey
                  }}.
                </p>
                <p v-else class="tw:m-0! tw:text-sm tw:text-muted-foreground">
                  Direct-index roles are unavailable or unverified; no default destination or ETF is
                  inferred.
                </p>
              </section>
              <section class="tw:grid tw:gap-2" aria-labelledby="policy-rules-title">
                <h3 id="policy-rules-title" class="tw:m-0! tw:text-sm! tw:font-semibold!">
                  Configured rules
                </h3>
                <dl
                  v-if="activeSettings"
                  class="tw:m-0! tw:grid tw:grid-cols-[minmax(0,1fr)_auto] tw:gap-x-3 tw:gap-y-1 tw:text-sm"
                >
                  <dt>Prefer ETF buys</dt>
                  <dd class="tw:m-0!">
                    {{ activeSettings.prefer_etf_buys ? 'Enabled' : 'Disabled' }}
                  </dd>
                  <dt>Allow gain sales</dt>
                  <dd class="tw:m-0!">
                    {{ activeSettings.allow_gain_sales ? 'Enabled' : 'Disabled' }}
                  </dd>
                  <dt>Permit ETF harvest</dt>
                  <dd class="tw:m-0!">
                    {{ activeSettings.permit_etf_harvest ? 'Enabled' : 'Disabled' }}
                  </dd>
                  <dt>Permit muni exit</dt>
                  <dd class="tw:m-0!">
                    {{ activeSettings.permit_muni_exit ? 'Enabled' : 'Disabled' }}
                  </dd>
                  <dt>Gain budget</dt>
                  <dd class="tw:m-0! tw:text-right">{{ gainBudgetLabel }}</dd>
                  <dt>Sell batch limits</dt>
                  <dd class="tw:m-0! tw:text-right">
                    {{ activeSettings.max_sell_tickers_per_batch }} tickers ·
                    {{ activeSettings.max_sell_lots_per_batch }} lots ·
                    {{ activeSettings.max_total_orders_per_batch }} total orders
                  </dd>
                </dl>
                <p v-else class="tw:m-0! tw:text-sm tw:text-muted-foreground">
                  Policy settings unavailable.
                </p>
                <p class="tw:m-0! tw:text-sm tw:text-muted-foreground">
                  Small legacy and DRIP lots are not blocked by a minimum SELL notional; cleanup is
                  rewarded and multiple lots of one ticker are consolidated into a single SELL
                  order. This DEMO overview never approves orders; any future order remains
                  separately user-directed and individually reviewed.
                </p>
              </section>
              <section
                id="replacement-sets"
                class="tw:grid tw:gap-2"
                aria-labelledby="replacement-sets-title"
              >
                <div class="tw:flex tw:flex-wrap tw:items-center tw:justify-between tw:gap-2">
                  <h3 id="replacement-sets-title" class="tw:m-0! tw:text-sm! tw:font-semibold!">
                    Active replacement sets
                  </h3>
                  <Button as-child variant="outline" size="sm">
                    <RouterLink to="/policy#replacement-sets">View policy details</RouterLink>
                  </Button>
                </div>
                <p class="tw:m-0! tw:text-sm tw:text-muted-foreground">
                  Candidates below come from this active policy and remain grouped by assigned
                  sleeve, sub-sleeve and replacement-set ID.
                </p>
                <ul v-if="replacementSetGroups.length" class="tw:m-0! tw:grid tw:gap-2 tw:p-0!">
                  <li
                    v-for="set in replacementSetGroups"
                    :key="JSON.stringify([set.sleeveKey, set.subSleeveKey, set.replacementSetId])"
                    class="tw:list-none tw:rounded-md tw:border tw:border-border tw:p-3"
                  >
                    <h4 class="tw:m-0! tw:text-sm! tw:font-semibold!">
                      {{ policyLabels[set.sleeveKey] ?? set.sleeveKey }}
                      <span
                        v-if="
                          !activePolicy.sleeves.some(
                            (sleeve) => sleeve.sleeve_key === set.sleeveKey,
                          )
                        "
                        class="tw:font-normal tw:text-muted-foreground"
                        >(unconfigured destination)</span
                      >
                      · {{ set.subSleeveKey ?? 'No sub-sleeve' }} ·
                      {{ set.replacementSetId || 'Unassigned replacement set' }}
                    </h4>
                    <ul class="tw:m-0! tw:grid tw:gap-1 tw:pt-2 tw:pl-4">
                      <li
                        v-for="security in set.securities"
                        :key="security.ticker"
                        class="tw:text-sm"
                      >
                        <strong>{{ security.ticker }}</strong>
                        <span> · {{ security.enabled ? 'Enabled' : 'Disabled' }}</span>
                        <span v-if="security.exposure_suitability">
                          · Suitability: {{ security.exposure_suitability }}</span
                        >
                      </li>
                    </ul>
                  </li>
                </ul>
                <p v-else class="tw:m-0! tw:text-sm tw:text-muted-foreground">
                  No active-policy replacement candidates returned; no new destination is assumed.
                </p>
              </section>
            </div>
          </template>
        </CardContent>
      </Card>
      <Card class="workspace-card account-card tw:min-w-0">
        <CardHeader
          class="tw:gap-3 tw:md:flex tw:md:flex-row tw:md:items-start tw:md:justify-between"
        >
          <div class="tw:grid tw:gap-2">
            <h2 class="tw:m-0! tw:text-lg! tw:font-semibold! tw:leading-tight!">Portfolio data</h2>
            <CardDescription>Source status and coverage from the backend API</CardDescription>
          </div>
          <Badge as="span" variant="secondary" class="tw:shrink-0">
            {{ portfolioStatusLabel }}
          </Badge>
        </CardHeader>
        <CardContent class="tw:grid tw:gap-4">
          <dl class="data-list tw:m-0! tw:grid tw:gap-0">
            <div
              class="tw:grid tw:grid-cols-1 tw:gap-1 tw:border-b tw:border-border tw:py-3 tw:sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] tw:sm:gap-2"
            >
              <dt class="tw:text-sm tw:text-muted-foreground">Account</dt>
              <dd class="tw:m-0! tw:break-words tw:text-sm tw:font-medium">{{ accountLabel }}</dd>
            </div>
            <div
              class="tw:grid tw:grid-cols-1 tw:gap-1 tw:border-b tw:border-border tw:py-3 tw:sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] tw:sm:gap-2"
            >
              <dt class="tw:text-sm tw:text-muted-foreground">Application status</dt>
              <dd class="tw:m-0! tw:break-words tw:text-sm tw:font-medium">
                {{ store.health?.status ?? 'Unavailable' }}
              </dd>
            </div>
            <div
              class="tw:grid tw:grid-cols-1 tw:gap-1 tw:border-b tw:border-border tw:py-3 tw:sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] tw:sm:gap-2"
            >
              <dt class="tw:text-sm tw:text-muted-foreground">Database schema</dt>
              <dd class="tw:m-0! tw:break-words tw:text-sm tw:font-medium">
                {{
                  store.health ? (store.health.schema_ready ? 'Ready' : 'Not ready') : 'Unavailable'
                }}
              </dd>
            </div>
            <div
              class="tw:grid tw:grid-cols-1 tw:gap-1 tw:border-b tw:border-border tw:py-3 tw:sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] tw:sm:gap-2"
            >
              <dt class="tw:text-sm tw:text-muted-foreground">Source</dt>
              <dd class="tw:m-0! tw:break-words tw:text-sm tw:font-medium">
                {{ portfolio?.status === 'ready' ? portfolio.source : 'Unavailable' }}
              </dd>
            </div>
            <div
              class="tw:grid tw:grid-cols-1 tw:gap-1 tw:border-b tw:border-border tw:py-3 tw:sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] tw:sm:gap-2"
            >
              <dt class="tw:text-sm tw:text-muted-foreground">Data as of</dt>
              <dd class="tw:m-0! tw:break-words tw:text-sm tw:font-medium">
                {{ portfolio?.as_of ?? 'Unavailable' }}
              </dd>
            </div>
            <div
              class="tw:grid tw:grid-cols-1 tw:gap-1 tw:border-b tw:border-border tw:py-3 tw:sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] tw:sm:gap-2"
            >
              <dt class="tw:text-sm tw:text-muted-foreground">Sync generation</dt>
              <dd class="tw:m-0! tw:break-words tw:text-sm tw:font-medium">
                {{ portfolio ? String(portfolio.sync.generation) : 'Unavailable' }}
              </dd>
            </div>
            <div
              class="tw:grid tw:grid-cols-1 tw:gap-1 tw:border-b tw:border-border tw:py-3 tw:sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] tw:sm:gap-2"
            >
              <dt class="tw:text-sm tw:text-muted-foreground">Last completed sync</dt>
              <dd class="tw:m-0! tw:break-words tw:text-sm tw:font-medium">
                {{ portfolio?.sync.completed_at ?? 'Unavailable' }}
              </dd>
            </div>
            <div
              class="tw:grid tw:grid-cols-1 tw:gap-1 tw:border-b tw:border-border tw:py-3 tw:sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] tw:sm:gap-2"
            >
              <dt class="tw:text-sm tw:text-muted-foreground">Last sync error</dt>
              <dd class="tw:m-0! tw:break-words tw:text-sm tw:font-medium">
                <template v-if="portfolio?.sync.last_error_code">
                  {{ portfolio.sync.last_error_code }}:
                  {{ portfolio.sync.last_error_summary ?? 'No summary returned' }}
                </template>
                <template v-else>None reported</template>
              </dd>
            </div>
          </dl>

          <Alert v-if="portfolio?.status === 'not_synced'" role="status" aria-live="polite">
            <AlertDescription>
              The current portfolio snapshot has not been synchronized. Use Sync portfolio to
              request the configured local demo snapshot.
            </AlertDescription>
          </Alert>

          <section class="coverage-block tw:grid tw:gap-3" aria-labelledby="coverage-title">
            <h3
              id="coverage-title"
              class="tw:m-0! tw:text-sm! tw:font-semibold! tw:leading-tight! tw:uppercase tw:tracking-wide"
            >
              Data coverage
            </h3>
            <Empty
              v-if="coverageEntries.length === 0"
              role="status"
              aria-live="polite"
              class="tw:border-border tw:p-4"
            >
              <EmptyHeader class="tw:max-w-none">
                <EmptyTitle role="heading" aria-level="4">Coverage unavailable</EmptyTitle>
                <EmptyDescription
                  >Coverage is unavailable until portfolio data loads.</EmptyDescription
                >
              </EmptyHeader>
            </Empty>
            <ul v-else class="coverage-list tw:m-0! tw:grid tw:list-none tw:gap-0 tw:p-0!">
              <li
                v-for="[key, covered] in coverageEntries"
                :key="key"
                class="tw:flex tw:min-w-0 tw:flex-wrap tw:items-center tw:justify-between tw:gap-2 tw:border-b tw:border-border tw:py-3"
              >
                <span class="tw:min-w-0 tw:break-all tw:text-sm">{{ key }}</span>
                <Badge as="span" :variant="covered ? 'secondary' : 'outline'" class="tw:shrink-0">
                  {{ covered ? 'Available' : 'Unavailable' }}
                </Badge>
              </li>
            </ul>
          </section>
        </CardContent>
      </Card>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty';
import { LoaderCircle, Play, RefreshCw } from '@lucide/vue';
import { RouterLink, useRouter } from 'vue-router';
import AllocationTargets from '@/components/AllocationTargets.vue';
import ApiActionError from '@/components/ApiActionError.vue';
import RunSummary from '@/components/RunSummary.vue';
import WorkspacePageHeader from '@/components/WorkspacePageHeader.vue';
import WorkspaceCapabilityNotice from '@/components/WorkspaceCapabilityNotice.vue';
import { formatPercent, formatUsd } from '@/utils/display-values';
import USAllocationTransition from '@/components/USAllocationTransition.vue';
import { useWorkspace } from '@/composables/use-workspace';
import { displayCount } from './overview-state';
import {
  canonicalLegs,
  groupLegs,
  selectedSellGrossLossUsd,
  selectionFromRun,
} from './recommendations-state';
import { sumExactUsd } from '@/utils/exact-usd';
import type { AllowedSecurityResponse } from '@/types/api';

import { api } from '@/services/api';
import { completeFrozenRunSleeveLabels } from './run-context';
import {
  selectPortfolioLabelContext,
  selectRunPresentation,
  selectWorkspaceReadiness,
} from '@/stores/workspace-selectors';
import ResourceFreshnessNotice from '@/components/ResourceFreshnessNotice.vue';

const store = useWorkspace();
const exposureCache = ref<Awaited<ReturnType<typeof api.getExposureCache>> | null>(null);
const exposurePending = ref(false);
const exposureError = ref<string | null>(null);
const exposureLoadError = ref<string | null>(null);
let exposureReadRevision = 0;
async function loadExposureCache(): Promise<void> {
  const revision = exposureReadRevision;
  try {
    const result = await api.getExposureCache();
    if (revision !== exposureReadRevision) return;
    exposureCache.value = result;
    exposureLoadError.value = null;
  } catch (error) {
    if (revision !== exposureReadRevision) return;
    exposureLoadError.value =
      error instanceof Error ? error.message : 'Look-through cache status could not be loaded.';
  }
}

async function refreshExposure(): Promise<void> {
  if (exposurePending.value) return;
  exposurePending.value = true;
  exposureError.value = null;
  try {
    // Invalidate any mount-time status read so it cannot overwrite this newer refresh result.
    exposureReadRevision += 1;
    exposureCache.value = await api.refreshExposureCache();
    exposureLoadError.value = null;
  } catch (error) {
    exposureError.value =
      error instanceof Error ? error.message : 'ETF look-through refresh failed.';
    await loadExposureCache();
  } finally {
    exposurePending.value = false;
  }
}
const router = useRouter();
const portfolio = computed(() => store.portfolio);
const activePolicy = computed(() => store.policy?.active ?? null);
const runPresentation = computed(() =>
  selectRunPresentation({
    run: store.currentRun,
    summary: store.currentRunSummary,
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

const overviewRun = computed(() =>
  currentRunMatches.value && !runPresentation.value.reviewMutationPending ? store.currentRun : null,
);
const overviewSelection = computed(() => {
  const run = overviewRun.value;
  if (!run) return null;
  try {
    return selectionFromRun(run);
  } catch {
    return null;
  }
});
const overviewSelectedGroupIds = computed(() => overviewSelection.value?.selected_group_ids ?? []);
const overviewHasSelectedBasket = computed(() => overviewSelectedGroupIds.value.length > 0);
const overviewPreviewGroups = computed(() => {
  const run = overviewRun.value;
  if (!run) return [];
  const selectedIds = new Set(overviewSelectedGroupIds.value);
  return [...run.groups]
    .filter((group) => selectedIds.has(group.group_id) && !group.rejected)
    .sort((left, right) => left.rank - right.rank)
    .slice(0, 3)
    .map((group) => ({
      group,
      sells: groupLegs(run, group)
        .filter((leg) => leg.side === 'SELL' && leg.selected)
        .map((leg) => ({
          leg,
          lots: leg.selected_lots.filter((lot) => lot.selected),
        })),
    }));
});
const overviewSelectedBuyLegs = computed(() => {
  const run = overviewRun.value;
  if (!run) return [];
  const selectedIds = new Set(overviewSelectedGroupIds.value);
  try {
    return canonicalLegs(run).filter(
      (leg) =>
        leg.side === 'BUY' &&
        leg.selected &&
        leg.group_ids.some((groupId) => selectedIds.has(groupId)),
    );
  } catch {
    return [];
  }
});
const overviewGrossLossUsd = computed(() => {
  const run = overviewRun.value;
  if (!run || !overviewHasSelectedBasket.value) return null;
  try {
    return selectedSellGrossLossUsd(canonicalLegs(run));
  } catch {
    return null;
  }
});
const overviewTaxBenefitLabel = computed(() => {
  const run = overviewRun.value;
  if (!run || !overviewHasSelectedBasket.value || run.estimated_tax_benefit_usd === null) {
    return 'Unavailable';
  }
  return formatUsd(run.estimated_tax_benefit_usd);
});
const overviewTaxBenefitExplanation = computed(() => {
  const run = overviewRun.value;
  if (!run || !overviewHasSelectedBasket.value) return 'No selected current recommendation basket';
  if (run.estimated_tax_benefit_usd === null) {
    return `Estimate unavailable · ${run.estimated_tax_benefit_status.replaceAll('_', ' ')}`;
  }
  return 'API estimate for the selected current basket';
});
const overviewRealizedStLabel = computed(() =>
  overviewRun.value && overviewHasSelectedBasket.value
    ? formatUsd(overviewRun.value.estimated_realized_st_usd)
    : 'Unavailable',
);
const overviewRealizedLtLabel = computed(() =>
  overviewRun.value && overviewHasSelectedBasket.value
    ? formatUsd(overviewRun.value.estimated_realized_lt_usd)
    : 'Unavailable',
);
const overviewRealizedNetLabel = computed(() => {
  const run = overviewRun.value;
  if (!run || !overviewHasSelectedBasket.value) return 'Unavailable';
  const net = sumExactUsd([run.estimated_realized_st_usd, run.estimated_realized_lt_usd]);
  return net === null ? 'Unavailable' : formatUsd(net);
});
const currentRunAllocationAvailable = computed(
  () => currentRunMatches.value && store.currentRun?.portfolio_effects?.allocation != null,
);
const currentRunTransitionAvailable = computed(
  () => currentRunMatches.value && store.currentRun?.portfolio_effects?.us_transition != null,
);
const policyLabels = computed(() =>
  Object.fromEntries(
    (activePolicy.value?.sleeves ?? []).map((sleeve) => [sleeve.sleeve_key, sleeve.display_name]),
  ),
);
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
const runContextLabels = computed(() => {
  const run = store.currentRun;
  const allocation = run?.portfolio_effects?.allocation;
  const transition = run?.portfolio_effects?.us_transition;
  const sleeveKeys = [
    ...(run?.groups
      .map((group) => group.sleeve_key)
      .filter((sleeveKey): sleeveKey is string => sleeveKey !== null) ?? []),
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
  return completeFrozenRunSleeveLabels(runDisplayContext.value, sleeveKeys);
});
const effectLabels = computed(() =>
  currentRunMatches.value ? runContextLabels.value : portfolioLabelContext.value.labels,
);
const allocation = computed(() => {
  if (currentRunAllocationAvailable.value) {
    return store.currentRun?.portfolio_effects?.allocation ?? null;
  }
  return portfolio.value?.allocation ?? null;
});
const usTransition = computed(() => {
  if (currentRunTransitionAvailable.value) {
    return store.currentRun?.portfolio_effects?.us_transition ?? null;
  }
  return portfolio.value?.us_transition ?? null;
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
const transitionSnapshotStatus = computed(() =>
  currentRunTransitionAvailable.value ? 'confirmed' : currentPortfolioTransitionStatus.value,
);
const transitionBasketStatus = computed(() => {
  if (currentRunMatches.value) {
    const run = store.currentRun;
    if (!run) return 'unavailable';
    const hasSelectedTrades = hasSelectedTradeBasket(run);
    if (hasSelectedTrades === null) return 'unverified';
    if (!hasSelectedTrades) return 'no-selection';
    return currentRunTransitionAvailable.value ? 'confirmed' : 'unavailable';
  }
  if (runPresentation.value.state === 'pending') return 'pending';
  if (runPresentation.value.state === 'stale') return 'stale';
  if (runPresentation.value.state === 'unverified') return 'unverified';
  return 'no-selection';
});
const transitionProvenance = computed(() =>
  currentRunTransitionAvailable.value ? 'current_run' : 'current_portfolio',
);
const transitionRoleIdentity = computed(() => {
  const sleeves = currentRunTransitionAvailable.value
    ? (runDisplayContext.value?.sleeves ?? null)
    : currentPortfolioTransitionStatus.value === 'confirmed'
      ? (activePolicy.value?.sleeves ?? null)
      : null;
  if (!sleeves) return null;
  const enabledRoleSleeves = sleeves.filter((sleeve) => sleeve.enabled);
  const containers = enabledRoleSleeves.filter((sleeve) => sleeve.is_direct_index_container);
  if (containers.length !== 1) return null;
  const containerKey = containers[0]?.sleeve_key ?? null;
  if (!containerKey) return null;
  const children = enabledRoleSleeves.filter((sleeve) => sleeve.parent_sleeve_key === containerKey);
  const legacy = children.filter((sleeve) => sleeve.is_direct_index_sleeve);
  const destinations = children.filter((sleeve) => sleeve.is_transition_destination);
  return {
    containerKey,
    legacyKey: legacy.length === 1 ? (legacy[0]?.sleeve_key ?? null) : null,
    destinationKey: destinations.length === 1 ? (destinations[0]?.sleeve_key ?? null) : null,
  };
});
const transitionRoleLabels = computed(() => {
  if (currentRunTransitionAvailable.value) return runContextLabels.value;
  if (currentPortfolioTransitionStatus.value === 'confirmed') return policyLabels.value;
  return effectLabels.value;
});
const coverageEntries = computed(() => Object.entries(portfolio.value?.coverage ?? {}));
const positionCount = computed(() => {
  const value = portfolio.value;
  if (!value) return 'Unavailable';
  return displayCount(value.status === 'ready' ? value.position_count : value.positions.length);
});
const accountLabel = computed(() => {
  const value = portfolio.value;
  if (!value) return 'Unavailable';
  return value.status === 'ready' ? value.account.display_name : 'No synchronized account';
});
const portfolioStatusLabel = computed(() => {
  const value = portfolio.value;
  if (!value) return 'Loading';
  return value.status === 'ready' ? 'Snapshot ready' : 'Not synchronized';
});
const enabledSleeves = computed(() =>
  (activePolicy.value?.sleeves ?? []).filter((sleeve) => sleeve.enabled),
);
const activeSettings = computed(() => activePolicy.value?.settings ?? null);
const gainBudgetLabel = computed(() => {
  const budget = activeSettings.value?.gain_budget_usd;
  return budget == null || budget.trim() === '' ? 'Not configured' : formatUsd(budget);
});
const replacementSetGroups = computed(() => {
  const groups = new Map<
    string,
    {
      sleeveKey: string;
      subSleeveKey: string | null;
      replacementSetId: string;
      securities: AllowedSecurityResponse[];
    }
  >();
  for (const security of activePolicy.value?.allowed_securities ?? []) {
    const key = JSON.stringify([
      security.sleeve_key,
      security.sub_sleeve_key,
      security.replacement_set_id,
    ]);
    let group = groups.get(key);
    if (!group) {
      group = {
        sleeveKey: security.sleeve_key,
        subSleeveKey: security.sub_sleeve_key,
        replacementSetId: security.replacement_set_id,
        securities: [],
      };
      groups.set(key, group);
    }
    group.securities.push(security);
  }
  return [...groups.values()];
});
const workspaceReadiness = computed(() =>
  selectWorkspaceReadiness({
    health: store.health,
    portfolio: portfolio.value,
    activePolicy: activePolicy.value,
    resourceFreshness: store.resourceFreshness,

    resourceReadsPending: store.workspaceResourceLoadPending,
    syncPending: store.actionState.syncPortfolio.pending,
    runPending: store.actionState.runOptimizer.pending,
  }),
);
const canRunOptimizer = computed(() => workspaceReadiness.value.canRunOptimizer);

async function syncPortfolio(): Promise<void> {
  try {
    await store.syncPortfolio();
  } catch {
    // The store retains a structured ApiError for visible presentation in this page.
  }
}

async function runOptimizer(): Promise<void> {
  if (!canRunOptimizer.value) return;
  try {
    await store.runOptimizer({});
    await router.push('/recommendations');
  } catch {
    // The store retains a structured ApiError for visible presentation in this page.
  }
}

onMounted(() => {
  void loadExposureCache();
  void store.ensureInitialWorkspace();
});
</script>
