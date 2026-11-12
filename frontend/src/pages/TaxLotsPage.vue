<template>
  <section
    class="workspace-page tax-lots-page tw:mx-auto tw:my-0! tw:min-w-0 tw:max-w-[1600px] tw:px-4 tw:py-4"
    data-tax-lots-root
    aria-labelledby="lots-title"
  >
    <WorkspacePageHeader
      eyebrow="Portfolio inventory"
      title="Tax Lots"
      title-id="lots-title"
      subtitle="Account-wide lot search; complete-set intent for a current DEMO run only."
    >
      <template #actions>
        <Button
          type="button"
          variant="outline"
          size="sm"
          :disabled="isLoading"
          @click="refreshLots"
        >
          {{ isLoading ? 'Loading…' : 'Refresh lots' }}
        </Button>
      </template>
    </WorkspacePageHeader>

    <WorkspaceCapabilityNotice label="DEMO ONLY.">
      No broker connection, OAuth, order preview, or trade submission is available.
    </WorkspaceCapabilityNotice>

    <ApiActionError
      :error="store.actionState.loadLots.error"
      title="Tax lots could not be loaded"
    />
    <ResourceFreshnessNotice :resources="['lots']" />

    <form aria-label="Tax lot filters" class="tw:min-w-0" @submit.prevent="applyFilters">
      <Card class="tw:min-w-0">
        <CardHeader class="tw:sr-only">
          <CardTitle id="tax-lot-filter-title" role="heading" aria-level="2"
            >Tax lot filters</CardTitle
          >
          <CardDescription
            >Filter account-wide tax lots and choose the API page size and sort
            order.</CardDescription
          >
        </CardHeader>
        <CardContent>
          <FieldGroup
            class="tw:grid tw:min-w-0 tw:grid-cols-1 tw:gap-4 tw:md:grid-cols-2 tw:xl:grid-cols-4"
          >
            <filterForm.Field name="search">
              <template #default="{ field }">
                <Field :data-invalid="field.state.meta.errors.length ? 'true' : undefined">
                  <FieldLabel for="tax-lot-search">Search all account lots</FieldLabel>
                  <Input
                    id="tax-lot-search"
                    type="search"
                    :model-value="field.state.value"
                    placeholder="Ticker or broker lot ID"
                    :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                    aria-describedby="tax-lot-search-hint"
                    @update:model-value="(value) => setSearch(value)"
                    @blur="field.handleBlur"
                  />
                  <FieldDescription id="tax-lot-search-hint"
                    >Search is trimmed only when the API request is applied.</FieldDescription
                  >
                  <FieldError id="tax-lot-search-error" :errors="field.state.meta.errors" />
                </Field>
              </template>
            </filterForm.Field>

            <filterForm.Field name="term">
              <template #default="{ field }">
                <Field :data-invalid="field.state.meta.errors.length ? 'true' : undefined">
                  <FieldLabel for="tax-lot-term">Holding term</FieldLabel>
                  <Select
                    :model-value="field.state.value || 'all'"
                    @update:model-value="setTermFilter"
                  >
                    <SelectTrigger
                      id="tax-lot-term"
                      aria-label="Holding term"
                      :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                      :aria-describedby="
                        field.state.meta.errors.length ? 'tax-lot-term-error' : undefined
                      "
                    >
                      <SelectValue placeholder="All terms" />
                    </SelectTrigger>
                    <SelectContent class="tax-lots-select-content">
                      <SelectItem value="all">All terms</SelectItem>
                      <SelectItem value="ST">Short term</SelectItem>
                      <SelectItem value="LT">Long term</SelectItem>
                    </SelectContent>
                  </Select>
                  <FieldError id="tax-lot-term-error" :errors="field.state.meta.errors" />
                </Field>
              </template>
            </filterForm.Field>

            <filterForm.Field name="fractional">
              <template #default="{ field }">
                <Field :data-invalid="field.state.meta.errors.length ? 'true' : undefined">
                  <FieldLabel for="tax-lot-fractional">Fractional cleanup</FieldLabel>
                  <Select
                    :model-value="field.state.value || 'all'"
                    @update:model-value="setFractionalFilter"
                  >
                    <SelectTrigger
                      id="tax-lot-fractional"
                      aria-label="Fractional cleanup"
                      :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                      :aria-describedby="
                        field.state.meta.errors.length ? 'tax-lot-fractional-error' : undefined
                      "
                    >
                      <SelectValue placeholder="All lots" />
                    </SelectTrigger>
                    <SelectContent class="tax-lots-select-content">
                      <SelectItem value="all">All lots</SelectItem>
                      <SelectItem value="true">Unsupported fractional cleanup</SelectItem>
                      <SelectItem value="false">No unsupported fractional cleanup</SelectItem>
                    </SelectContent>
                  </Select>
                  <FieldError id="tax-lot-fractional-error" :errors="field.state.meta.errors" />
                </Field>
              </template>
            </filterForm.Field>

            <filterForm.Field name="limit">
              <template #default="{ field }">
                <Field :data-invalid="field.state.meta.errors.length ? 'true' : undefined">
                  <FieldLabel for="tax-lot-limit">Rows per API page</FieldLabel>
                  <Select
                    :model-value="String(field.state.value)"
                    @update:model-value="setPageLimit"
                  >
                    <SelectTrigger
                      id="tax-lot-limit"
                      aria-label="Rows per API page"
                      :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                      :aria-describedby="
                        field.state.meta.errors.length ? 'tax-lot-limit-error' : undefined
                      "
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent class="tax-lots-select-content">
                      <SelectItem
                        v-for="limit in TAX_LOT_PAGE_LIMITS"
                        :key="limit"
                        :value="String(limit)"
                      >
                        {{ limit }}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                  <FieldError id="tax-lot-limit-error" :errors="field.state.meta.errors" />
                </Field>
              </template>
            </filterForm.Field>

            <filterForm.Field name="sortBy">
              <template #default="{ field }">
                <Field :data-invalid="field.state.meta.errors.length ? 'true' : undefined">
                  <FieldLabel for="tax-lot-sort">Sort API results by</FieldLabel>
                  <Select
                    :model-value="field.state.value"
                    :disabled="isLoading"
                    @update:model-value="setSortField"
                  >
                    <SelectTrigger
                      id="tax-lot-sort"
                      aria-label="Sort API results by"
                      :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                      :aria-describedby="
                        field.state.meta.errors.length ? 'tax-lot-sort-error' : undefined
                      "
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent class="tax-lots-select-content">
                      <SelectItem value="ticker">Security</SelectItem>
                      <SelectItem value="broker_lot_id">Broker lot ID</SelectItem>
                      <SelectItem value="acquired_date">Acquired date</SelectItem>
                      <SelectItem value="remaining_shares">Remaining shares</SelectItem>
                      <SelectItem value="available_shares">Available shares</SelectItem>
                      <SelectItem value="adjusted_unit_basis_usd">Unit basis</SelectItem>
                      <SelectItem value="adjusted_total_basis_usd">Total basis</SelectItem>
                      <SelectItem value="current_price_usd">Current price</SelectItem>
                      <SelectItem value="unrealized_pl_usd">Unrealized P/L (USD)</SelectItem>
                      <SelectItem value="unrealized_pl_pct">Unrealized P/L (%)</SelectItem>
                      <SelectItem value="term">Holding term</SelectItem>
                      <SelectItem value="sleeve_key">Sleeve</SelectItem>
                      <SelectItem value="sub_sleeve_key">Sub-sleeve</SelectItem>
                    </SelectContent>
                  </Select>
                  <FieldError id="tax-lot-sort-error" :errors="field.state.meta.errors" />
                </Field>
              </template>
            </filterForm.Field>

            <Field orientation="horizontal" class="tw:items-end tw:gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                class="tw:mb-0!"
                :disabled="isLoading"
                :aria-label="filters.sortDirection === 'asc' ? 'Sort ascending' : 'Sort descending'"
                @click="toggleSortDirection"
              >
                {{ filters.sortDirection === 'asc' ? 'Ascending' : 'Descending' }}
              </Button>
              <Button type="submit" size="sm" class="tw:mb-0!" :disabled="isLoading">
                Apply API filters
              </Button>
            </Field>
          </FieldGroup>
        </CardContent>
      </Card>
    </form>

    <Alert
      v-if="store.actionState.loadLots.pending && !store.lots"
      variant="default"
      role="status"
      class="tw:mt-4!"
    >
      <AlertDescription>Loading tax lots from the local API…</AlertDescription>
    </Alert>
    <Empty v-else-if="!store.lots" class="tw:mt-4! tw:min-h-40">
      <EmptyHeader>
        <EmptyTitle>No lot page loaded</EmptyTitle>
        <EmptyDescription>Load the current API page to see broker-reported lots.</EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button
          type="button"
          variant="outline"
          size="sm"
          :disabled="isLoading"
          @click="refreshLots"
        >
          Retry loading lots
        </Button>
      </EmptyContent>
    </Empty>
    <Empty v-else-if="store.lots.items.length === 0" class="tw:mt-4! tw:min-h-40">
      <EmptyHeader>
        <EmptyTitle role="heading" aria-level="2">No lots returned</EmptyTitle>
        <EmptyDescription>The API returned an empty page for these filters.</EmptyDescription>
      </EmptyHeader>
    </Empty>
    <template v-else>
      <div
        class="results-heading tw:mt-4! tw:flex tw:min-w-0 tw:flex-wrap tw:items-center tw:justify-between tw:gap-3 tw:text-sm tw:text-muted-foreground"
      >
        <p class="tw:m-0!">
          API page {{ pageNumber }} · {{ store.lots.items.length }} rows returned ·
          {{ store.lots.total }} rows match the account-wide filters before pagination.
        </p>
      </div>

      <div class="security-groups tw:mt-4! tw:grid tw:min-w-0 tw:gap-4">
        <section
          v-for="group in groupedLots"
          :key="group.ticker"
          class="security-card tw:min-w-0 tw:overflow-hidden tw:rounded-xl tw:border tw:bg-card tw:text-card-foreground"
          :aria-labelledby="`security-${group.ticker}`"
        >
          <header
            class="security-heading tw:flex tw:min-w-0 tw:flex-wrap tw:items-center tw:justify-between tw:gap-3 tw:p-4"
          >
            <h2 :id="`security-${group.ticker}`" class="tw:m-0!">{{ group.ticker }}</h2>
            <span class="tw:text-sm tw:text-muted-foreground"
              >{{ group.lots.length }} {{ group.lots.length === 1 ? 'lot' : 'lots' }}</span
            >
          </header>
          <WorkspaceTableFrame :label="`Tax lots for ${group.ticker}`">
            <TaxLotGroupTable
              :ticker="group.ticker"
              :lots="group.lots"
              :requested-lot-ids="requestedLotIds"
              :confirmed-sell-lot-ids="confirmedLotIds"
              :can-change-intent="canChangeLotIntent"
              :source-generation="store.lots.source_generation"
              :sort-by="appliedSortBy"
              :sort-direction="appliedSortDirection"
              :search="store.lotFilters.search ?? ''"
              :term="store.lotFilters.term"
              :fractional="store.lotFilters.fractional"
              :offset="store.lots.offset"
              :limit="store.lots.limit"
              :total="store.lots.total"
              @intent-change="changeLotIntent"
            />
          </WorkspaceTableFrame>
        </section>
      </div>
    </template>

    <WorkspacePagination
      v-if="store.lots"
      :offset="store.lots.offset"
      :limit="store.lots.limit"
      :total="store.lots.total"
      :pending="isLoading || filterDraftChanged"
      label="Tax lot API pages"
      @page="loadLots"
    />

    <section class="review-summary tw:mt-4! tw:min-w-0" aria-labelledby="review-title">
      <Card class="tw:min-w-0">
        <CardHeader>
          <CardTitle id="review-title" role="heading" aria-level="2"
            >Requested lot intent · {{ store.lotReviewIntent.length }}</CardTitle
          >
          <CardDescription>
            This is a complete replacement set, not an additive change: apply submits every
            requested broker lot ID, and an explicitly empty set clears the DEMO recommendation
            basket. Requested intent is not backend-confirmed selection and neither one approves an
            order. Only a successful response updates the confirmed run; the endpoint re-solves
            saved DEMO candidates only and does not create candidates or a run.
          </CardDescription>
        </CardHeader>
        <CardContent class="tw:grid tw:min-w-0 tw:gap-3">
          <ApiActionError
            :error="store.actionState.applyLotReviewIntent.error"
            title="Requested lot set was not applied"
          />

          <Alert
            v-if="
              store.lotReviewIntentGeneration !== null &&
              store.lotReviewIntentConfirmedRunId === store.currentRun?.run_id &&
              !store.lotReviewIntentDirty &&
              !store.actionState.applyLotReviewIntent.error
            "
            variant="default"
            role="status"
          >
            <AlertDescription
              >The loaded DEMO run currently selects exactly this requested set. This is
              recommendation state only, not order approval.</AlertDescription
            >
          </Alert>
          <Alert v-if="store.lotReviewIntentNotice" variant="default" role="status">
            <AlertDescription>{{ store.lotReviewIntentNotice }}</AlertDescription>
          </Alert>
          <Alert v-if="store.lots?.source_generation === null" variant="default" role="status">
            <AlertDescription
              >This lot page has no source generation. It is unvalidated; lot intent cannot be
              submitted.</AlertDescription
            >
          </Alert>
          <Alert
            v-else-if="store.lots && !lotPageGenerationMatches"
            variant="default"
            role="status"
          >
            <AlertDescription>
              This page is from source generation {{ store.lots.source_generation }}, but the
              workspace currently observes generation
              {{ store.observedSourceGeneration ?? 'unavailable' }}. Refresh lots before marking or
              submitting any set.
            </AlertDescription>
          </Alert>
          <Alert v-if="basketUnchanged" variant="default" role="status">
            <AlertDescription
              >The API rejected the complete request atomically. Backend-confirmed selection is
              unchanged.</AlertDescription
            >
          </Alert>
          <ul
            v-if="rejectedLotReasons.length"
            aria-label="Requested lot rejection reasons"
            class="tw:m-0! tw:grid tw:gap-2 tw:pl-5"
          >
            <li v-for="entry in rejectedLotReasons" :key="entry.broker_lot_id">
              {{ entry.broker_lot_id }}: {{ rejectionReasonLabel(entry.reason) }} ({{
                entry.reason
              }})
            </li>
          </ul>
          <Alert v-if="store.currentRunView === 'stale'" variant="default" role="status">
            <AlertDescription>
              The loaded DEMO run is stale. Create a current DEMO run before applying intent; this
              page will not silently create or merge one.
            </AlertDescription>
          </Alert>
          <Alert v-else-if="!currentRunIsUsable" variant="default" role="status">
            <AlertDescription>
              No current DEMO run is available. Create a run in Overview or Recommendations, then
              return here. Saved runs remain read-only.
            </AlertDescription>
          </Alert>
          <p v-else class="tw:m-0! tw:text-sm tw:text-muted-foreground">
            Target run {{ store.currentRun?.run_id }} · source generation
            {{ store.currentRun?.source_generation }}
          </p>

          <ul v-if="store.lotReviewIntent.length > 0" class="tw:m-0! tw:grid tw:gap-2 tw:pl-5">
            <li v-for="entry in store.lotReviewIntent" :key="entry.broker_lot_id">
              {{ entry.ticker }} · {{ entry.broker_lot_id }} · generation
              {{ entry.source_generation }}
              <Button
                type="button"
                variant="outline"
                size="sm"
                class="tw:ml-2!"
                :disabled="store.reviewMutationPending"
                @click="removeRequestedLot(entry)"
              >
                Remove from requested set
              </Button>
            </li>
          </ul>
          <p v-else class="tw:m-0! tw:text-sm tw:text-muted-foreground">
            Requested set is empty; clearing is explicit and must be applied.
          </p>
          <p class="tw:m-0! tw:text-sm tw:text-muted-foreground">
            Backend-confirmed selected SELL lot IDs in the loaded run:
            {{ confirmedBrokerLotIds.join(', ') || 'none' }}
          </p>
          <Field orientation="horizontal" class="tw:flex-wrap tw:items-center tw:gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              :disabled="!canChangeLotIntent"
              @click="clearRequestedLots"
            >
              Explicitly request an empty set
            </Button>
            <Button
              type="button"
              size="sm"
              :disabled="!canApplyLotIntent"
              @click="applyRequestedLots"
            >
              {{
                store.actionState.applyLotReviewIntent.pending
                  ? 'Applying complete set…'
                  : store.lotReviewIntent.length === 0
                    ? 'Apply empty set and clear confirmed basket'
                    : 'Apply complete set to current DEMO run'
              }}
            </Button>
          </Field>
        </CardContent>
      </Card>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useForm } from '@tanstack/vue-form';
import ApiActionError from '@/components/ApiActionError.vue';
import ResourceFreshnessNotice from '@/components/ResourceFreshnessNotice.vue';
import WorkspaceCapabilityNotice from '@/components/WorkspaceCapabilityNotice.vue';
import WorkspacePageHeader from '@/components/WorkspacePageHeader.vue';
import WorkspacePagination from '@/components/WorkspacePagination.vue';
import WorkspaceTableFrame from '@/components/WorkspaceTableFrame.vue';
import { Alert, AlertDescription } from '@/components/ui/alert';

import { Button } from '@/components/ui/button';
import type { AcceptableValue } from 'reka-ui';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from '@/components/ui/empty';
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { getPaginationMetadata } from '@/components/workspace-pagination-state';
import { useWorkspace } from '@/composables/use-workspace';
import {
  TAX_LOT_PAGE_LIMITS,
  isTaxLotPageLimit,
  isTaxLotSortField,
  taxLotFilterDefaults,
  taxLotFilterSchema,
  type TaxLotFilterValues,
} from '@/forms/tax-lot-filters';
import type { LotQuery } from '@/services/api';
import type { LotResponse } from '@/types/api';
import TaxLotGroupTable from './TaxLotGroupTable.vue';

const store = useWorkspace();
const filterForm = useForm({
  defaultValues: taxLotFilterDefaults(store.lotFilters),
  validators: { onChange: taxLotFilterSchema },
  onSubmit: async ({ value }) => {
    await loadWithFilters(0, value);
  },
});
const filters = filterForm.useSelector((state) => state.values);
const isLoading = computed(() => store.actionState.loadLots.pending);
const pagination = computed(() => {
  const page = store.lots;
  return getPaginationMetadata(page?.offset ?? 0, page?.limit ?? 1, page?.total ?? 0);
});
const pageNumber = computed(() => pagination.value.pageNumber);
const appliedSortBy = computed<NonNullable<LotQuery['sort_by']>>(
  () => store.lotFilters.sort_by ?? 'ticker',
);
const appliedSortDirection = computed<NonNullable<LotQuery['sort_direction']>>(
  () => store.lotFilters.sort_direction ?? 'asc',
);
const requestedLotIds = computed(
  () => new Set(store.lotReviewIntent.map((entry) => entry.broker_lot_id)),
);
const confirmedLotIds = computed(() => {
  const ids = new Set<string>();
  for (const leg of store.currentRun?.consolidated_legs ?? []) {
    if (leg.side !== 'SELL') continue;
    for (const lot of leg.selected_lots) {
      if (lot.selected) ids.add(lot.broker_lot_id);
    }
  }
  return ids;
});
const lotPageGenerationMatches = computed(
  () =>
    store.lots !== null &&
    store.lots.source_generation !== null &&
    store.lots.source_generation === store.observedSourceGeneration,
);
const currentRunIsUsable = computed(
  () =>
    store.currentRun !== null &&
    store.currentRunView === 'current' &&
    store.currentRun.source_generation === store.observedSourceGeneration &&
    store.currentRun.source_generation === store.lots?.source_generation,
);
const canChangeLotIntent = computed(
  () => lotPageGenerationMatches.value && !isLoading.value && !store.reviewMutationPending,
);
const canApplyLotIntent = computed(
  () =>
    canChangeLotIntent.value &&
    currentRunIsUsable.value &&
    store.lotReviewIntentDirty &&
    !store.reviewMutationPending,
);
const groupedLots = computed(() => {
  const groups = new Map<string, LotResponse[]>();
  for (const lot of store.lots?.items ?? []) {
    const rows = groups.get(lot.ticker) ?? [];
    rows.push(lot);
    groups.set(lot.ticker, rows);
  }
  return [...groups.entries()].map(([ticker, lots]) => ({ ticker, lots }));
});
const confirmedBrokerLotIds = computed(() => [...confirmedLotIds.value].sort());
const filterDraftChanged = computed(() => {
  const draft = currentFilters(0);
  const applied = currentFilters(0, taxLotFilterDefaults(store.lotFilters));
  return (
    (draft.search ?? undefined) !== (applied.search ?? undefined) ||
    (draft.term ?? undefined) !== (applied.term ?? undefined) ||
    (draft.fractional ?? undefined) !== (applied.fractional ?? undefined) ||
    draft.sort_by !== applied.sort_by ||
    draft.sort_direction !== applied.sort_direction ||
    draft.limit !== applied.limit
  );
});
const rejectedLotReasons = computed(() => {
  const details = store.actionState.applyLotReviewIntent.error?.details;
  if (details === null || typeof details !== 'object' || Array.isArray(details)) return [];
  const rejected = details['rejected_lots'];
  if (!Array.isArray(rejected)) return [];
  return rejected.flatMap((entry) => {
    if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) return [];
    const brokerLotId = entry['broker_lot_id'];
    const reason = entry['reason'];
    return typeof brokerLotId === 'string' && typeof reason === 'string'
      ? [{ broker_lot_id: brokerLotId, reason }]
      : [];
  });
});
const basketUnchanged = computed(() => {
  const details = store.actionState.applyLotReviewIntent.error?.details;
  return (
    details !== null &&
    typeof details === 'object' &&
    !Array.isArray(details) &&
    details['basket_unchanged'] === true
  );
});

function currentFilters(offset: number, values: TaxLotFilterValues = filters.value): LotQuery {
  const search = values.search.trim();
  return {
    ...(search ? { search } : {}),
    ...(values.term ? { term: values.term } : {}),
    ...(values.fractional === '' ? {} : { fractional: values.fractional === 'true' }),
    sort_by: values.sortBy,
    sort_direction: values.sortDirection,
    offset,
    limit: values.limit,
  };
}

async function loadLots(offset: number): Promise<void> {
  try {
    await store.loadLots({ ...store.lotFilters, offset });
  } catch {
    // The shared store retains the structured API error for the page.
  }
}

async function loadWithFilters(
  offset: number,
  values: TaxLotFilterValues = filters.value,
): Promise<void> {
  try {
    await store.loadLots(currentFilters(offset, values));
  } catch {
    // The shared store retains the structured API error for the page.
  }
}

function applyFilters(): void {
  void filterForm.handleSubmit();
}

function setSearch(value: string | number): void {
  filterForm.setFieldValue('search', String(value));
}

function setTermFilter(value: AcceptableValue): void {
  const term = value === 'ST' || value === 'LT' ? value : '';
  filterForm.setFieldValue('term', term);
}

function setFractionalFilter(value: AcceptableValue): void {
  const fractional = value === 'true' || value === 'false' ? value : '';
  filterForm.setFieldValue('fractional', fractional);
}

function setPageLimit(value: AcceptableValue): void {
  const limit = Number(value);
  if (isTaxLotPageLimit(limit)) filterForm.setFieldValue('limit', limit);
}

function setSortField(value: AcceptableValue): void {
  if (typeof value !== 'string' || !isTaxLotSortField(value)) return;
  filterForm.setFieldValue('sortBy', value);
  void loadWithFilters(0, { ...filters.value, sortBy: value });
}

function toggleSortDirection(): void {
  const sortDirection = filters.value.sortDirection === 'asc' ? 'desc' : 'asc';
  filterForm.setFieldValue('sortDirection', sortDirection);
  void loadWithFilters(0, { ...filters.value, sortDirection });
}

function refreshLots(): void {
  void loadLots(store.lots?.offset ?? store.lotFilters.offset ?? 0);
}

function changeLotIntent(change: {
  brokerLotId: string;
  ticker: string;
  sourceGeneration: number | null;
  requested: boolean;
}): void {
  store.setLotReviewIntent(
    change.brokerLotId,
    change.ticker,
    change.sourceGeneration,
    change.requested,
  );
}

function removeRequestedLot(entry: {
  broker_lot_id: string;
  ticker: string;
  source_generation: number;
}): void {
  store.setLotReviewIntent(entry.broker_lot_id, entry.ticker, entry.source_generation, false);
}

function clearRequestedLots(): void {
  store.clearLotReviewIntent();
}

async function applyRequestedLots(): Promise<void> {
  try {
    await store.applyLotReviewIntent();
  } catch {
    // The shared store retains the structured API error and confirmed run on failure.
  }
}

function rejectionReasonLabel(reason: string): string {
  switch (reason) {
    case 'missing_current_lot':
      return 'This broker lot is not present in current inventory.';
    case 'outside_saved_demo_candidates':
      return 'This lot is not represented by a saved DEMO candidate; no candidate was generated.';
    case 'ambiguous_saved_demo_candidate':
      return 'This lot maps to multiple saved DEMO candidates and cannot be applied.';
    default:
      return reason;
  }
}

onMounted(() => {
  void loadLots(store.lotFilters.offset ?? 0);
});
</script>

<style scoped>
:global([data-tax-lots-root]) {
  color: var(--foreground);
}

:global([data-tax-lots-root] .security-heading h2),
:global([data-tax-lots-root] .review-summary h2) {
  color: var(--foreground);
  font-size: var(--tw-text-base);
  font-weight: 600;
  line-height: 1.375;
}

:global([data-tax-lots-root] input[data-slot='input']) {
  appearance: none;
  border: 1px solid var(--input);
  border-radius: var(--radius-md);
  background-color: transparent;
  color: var(--foreground);
  font-family: inherit;
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
}

:global([data-tax-lots-root] button[data-slot='button']),
:global([data-tax-lots-root] button[data-slot='select-trigger']) {
  appearance: none;
  font-family: inherit;
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
  text-transform: none;
}

:global([data-tax-lots-root] button[data-slot='select-trigger']) {
  border: 1px solid var(--input);
  background-color: transparent;
  color: var(--foreground);
}

:global([data-tax-lots-root] [data-slot='table-container']) {
  overflow: visible;
}

:global([data-tax-lots-root] table[data-slot='table']) {
  min-width: 1150px;
  border-collapse: collapse;
}

:global([data-tax-lots-root] .lot-id) {
  overflow-wrap: anywhere;
}

:global(.tax-lots-select-content) {
  color: var(--popover-foreground);
  font-family: inherit;
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
}
</style>
