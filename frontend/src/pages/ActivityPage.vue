<template>
  <section
    class="workspace-page activity-page tw:mx-auto tw:my-0 tw:min-w-0 tw:max-w-[1600px] tw:px-4 tw:py-4"
    data-activity-root
    aria-labelledby="activity-title"
  >
    <WorkspacePageHeader
      eyebrow="Workspace history"
      title="Activity"
      title-id="activity-title"
      subtitle="Timestamped API events, structured details, and saved optimizer-run reopening. Reopening a run does not approve any trade."
    >
      <template #actions>
        <Button type="button" variant="outline" size="sm" :disabled="isLoading" @click="refresh">
          {{ isLoading ? 'Loading…' : 'Refresh activity' }}
        </Button>
      </template>
    </WorkspacePageHeader>

    <WorkspaceCapabilityNotice label="DEMO ONLY.">
      This local activity view never connects to E*TRADE and contains no order preview or submission
      controls.
    </WorkspaceCapabilityNotice>

    <div
      v-if="store.actionState.loadActivity.error || store.actionState.openSavedRun.error"
      class="tw:grid tw:min-w-0 tw:gap-2"
      aria-label="Activity request errors"
    >
      <ApiActionError
        :error="store.actionState.loadActivity.error"
        title="Activity could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.openSavedRun.error"
        title="Saved optimizer run could not be reopened"
      />
    </div>

    <ResourceFreshnessNotice :resources="['activity']" />

    <RunSummary
      v-if="savedRunSummary || store.actionState.openSavedRun.pending"
      mode="saved"
      :summary="savedRunSummary"
      :context="savedRunSummary?.frozen_display_context ?? null"
      :pending="store.actionState.openSavedRun.pending"
    />

    <form aria-label="Activity filters" class="tw:min-w-0" @submit.prevent="applyFilters">
      <Card class="tw:min-w-0">
        <CardHeader class="tw:sr-only">
          <CardTitle id="activity-filter-title" role="heading" aria-level="2">
            Activity filters
          </CardTitle>
          <CardDescription>Filter API events and choose the returned page size.</CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup
            class="tw:grid tw:min-w-0 tw:grid-cols-1 tw:gap-4 tw:md:grid-cols-2 tw:lg:grid-cols-3"
            data-activity-filter-grid
          >
            <div class="tw:grid tw:gap-1">
              <span class="tw:text-sm tw:font-medium">Common event filters</span>
              <select
                id="activity-common-event-type"
                aria-label="Quick category selection"
                @change="selectCommonEventType"
              >
                <option value="">Choose an event type</option>
                <option
                  v-for="choice in COMMON_ACTIVITY_EVENT_TYPES"
                  :key="choice.code"
                  :value="choice.code"
                >
                  {{ choice.label }}
                </option>
              </select>
            </div>
            <filterForm.Field name="eventType">
              <template #default="{ field }">
                <UiField :data-invalid="field.state.meta.errors.length ? 'true' : undefined">
                  <FieldLabel for="activity-event-type">Event type</FieldLabel>
                  <Input
                    id="activity-event-type"
                    type="search"
                    :model-value="field.state.value"
                    placeholder="Exact API event type"
                    :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                    :aria-describedby="
                      field.state.meta.errors.length ? 'activity-event-type-error' : undefined
                    "
                    @update:model-value="(value) => setTextFilter('eventType', value)"
                    @blur="field.handleBlur"
                  />
                  <FieldError id="activity-event-type-error" :errors="field.state.meta.errors" />
                </UiField>
              </template>
            </filterForm.Field>

            <filterForm.Field name="status">
              <template #default="{ field }">
                <UiField :data-invalid="field.state.meta.errors.length ? 'true' : undefined">
                  <FieldLabel for="activity-status">Status</FieldLabel>
                  <Input
                    id="activity-status"
                    type="search"
                    :model-value="field.state.value"
                    placeholder="Exact API status"
                    :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                    :aria-describedby="
                      field.state.meta.errors.length ? 'activity-status-error' : undefined
                    "
                    @update:model-value="(value) => setTextFilter('status', value)"
                    @blur="field.handleBlur"
                  />
                  <FieldError id="activity-status-error" :errors="field.state.meta.errors" />
                </UiField>
              </template>
            </filterForm.Field>

            <filterForm.Field name="correlationId">
              <template #default="{ field }">
                <UiField :data-invalid="field.state.meta.errors.length ? 'true' : undefined">
                  <FieldLabel for="activity-correlation-id">Correlation ID</FieldLabel>
                  <Input
                    id="activity-correlation-id"
                    type="search"
                    :model-value="field.state.value"
                    placeholder="Correlation ID"
                    :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                    :aria-describedby="
                      field.state.meta.errors.length ? 'activity-correlation-id-error' : undefined
                    "
                    @update:model-value="(value) => setTextFilter('correlationId', value)"
                    @blur="field.handleBlur"
                  />
                  <FieldError
                    id="activity-correlation-id-error"
                    :errors="field.state.meta.errors"
                  />
                </UiField>
              </template>
            </filterForm.Field>

            <filterForm.Field name="since">
              <template #default="{ field }">
                <UiField :data-invalid="field.state.meta.errors.length ? 'true' : undefined">
                  <FieldLabel for="activity-since">Since (UTC)</FieldLabel>
                  <Input
                    id="activity-since"
                    type="datetime-local"
                    step="any"
                    :model-value="field.state.value"
                    :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                    :aria-describedby="
                      field.state.meta.errors.length ? 'activity-since-error' : undefined
                    "
                    @update:model-value="(value) => setDateFilter('since', value)"
                    @blur="field.handleBlur"
                  />
                  <FieldError id="activity-since-error" :errors="field.state.meta.errors" />
                </UiField>
              </template>
            </filterForm.Field>

            <filterForm.Field name="until">
              <template #default="{ field }">
                <UiField :data-invalid="field.state.meta.errors.length ? 'true' : undefined">
                  <FieldLabel for="activity-until">Until (UTC)</FieldLabel>
                  <Input
                    id="activity-until"
                    type="datetime-local"
                    step="any"
                    :model-value="field.state.value"
                    :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                    :aria-describedby="
                      field.state.meta.errors.length ? 'activity-until-error' : undefined
                    "
                    @update:model-value="(value) => setDateFilter('until', value)"
                    @blur="field.handleBlur"
                  />
                  <FieldError id="activity-until-error" :errors="field.state.meta.errors" />
                </UiField>
              </template>
            </filterForm.Field>

            <filterForm.Field name="limit">
              <template #default="{ field }">
                <UiField :data-invalid="field.state.meta.errors.length ? 'true' : undefined">
                  <FieldLabel for="activity-page-limit">Rows per page</FieldLabel>
                  <Select
                    :model-value="String(field.state.value)"
                    @update:model-value="updatePageLimit"
                  >
                    <SelectTrigger
                      id="activity-page-limit"
                      class="tw:w-full"
                      aria-label="Rows per page"
                      :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                      :aria-describedby="
                        field.state.meta.errors.length ? 'activity-page-limit-error' : undefined
                      "
                      @blur="field.handleBlur"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent class="activity-select-content">
                      <SelectGroup>
                        <SelectItem
                          v-for="limit in ACTIVITY_PAGE_LIMITS"
                          :key="limit"
                          :value="String(limit)"
                        >
                          {{ limit }}
                        </SelectItem>
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                  <FieldError id="activity-page-limit-error" :errors="field.state.meta.errors" />
                </UiField>
              </template>
            </filterForm.Field>
          </FieldGroup>

          <div class="tw:mt-4 tw:flex tw:flex-wrap tw:items-center tw:gap-2">
            <Button type="submit" size="sm" :disabled="isLoading">Apply filters</Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              :disabled="isLoading"
              @click="clearFilters"
            >
              Clear filters
            </Button>
          </div>
        </CardContent>
      </Card>
    </form>

    <Alert
      v-if="store.actionState.loadActivity.pending && !activity"
      role="status"
      aria-live="polite"
    >
      <AlertDescription>Loading activity from the local API…</AlertDescription>
    </Alert>

    <Empty
      v-else-if="!activity"
      class="tw:my-2 tw:border tw:border-border"
      role="status"
      aria-live="polite"
    >
      <EmptyHeader>
        <EmptyTitle role="heading" aria-level="2">No activity page loaded</EmptyTitle>
        <EmptyDescription class="tw:m-0">
          Retry to request current activity. No events are generated by this page.
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button type="button" variant="outline" size="sm" :disabled="isLoading" @click="refresh">
          Retry loading activity
        </Button>
      </EmptyContent>
    </Empty>

    <Empty
      v-else-if="activity.total === 0"
      class="tw:my-2 tw:border tw:border-border"
      role="status"
      aria-live="polite"
    >
      <EmptyHeader>
        <EmptyTitle role="heading" aria-level="2">No activity events returned</EmptyTitle>
        <EmptyDescription class="tw:m-0">
          The API returned no events for the selected filters.
        </EmptyDescription>
      </EmptyHeader>
    </Empty>

    <template v-else>
      <p class="tw:m-0 tw:text-sm tw:leading-relaxed tw:text-muted-foreground">
        {{ activity.items.length }} events on this page · {{ activity.total }} matching events ·
        page {{ pageNumber }} of {{ pageCount }}
      </p>
      <Empty
        v-if="activity.items.length === 0"
        class="tw:my-2 tw:border tw:border-border"
        role="status"
        aria-live="polite"
      >
        <EmptyHeader>
          <EmptyTitle role="heading" aria-level="2">No events on this page</EmptyTitle>
          <EmptyDescription class="tw:m-0">
            The API returned no events for this offset. Use the filters or return to a previous
            page.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
      <ol
        v-else
        class="tw:m-0 tw:grid tw:min-w-0 tw:list-none tw:gap-3 tw:p-0"
        aria-label="Activity events"
      >
        <li v-for="event in activity.items" :key="event.id" class="tw:min-w-0">
          <Card class="event-card tw:min-w-0">
            <CardHeader
              class="tw:flex tw:min-w-0 tw:flex-row tw:items-start tw:justify-between tw:gap-4"
            >
              <div class="tw:grid tw:min-w-0 tw:gap-1">
                <h2 class="tw:m-0! tw:break-words tw:text-base tw:font-semibold tw:leading-snug">
                  {{ eventCategoryLabel(event.event_type) }}
                </h2>
                <p class="tw:m-0 tw:break-all tw:text-xs tw:text-muted-foreground">
                  API event: {{ event.event_type }}
                </p>
                <p class="tw:m-0 tw:text-sm tw:leading-relaxed">{{ eventSummary(event) }}</p>
                <p class="tw:m-0 tw:break-all tw:text-sm tw:text-muted-foreground">
                  <time :datetime="event.created_at">{{ event.created_at }}</time>
                </p>
              </div>
              <Badge
                as="span"
                role="status"
                class="tw:shrink-0"
                :variant="statusBadgeVariant(event.status)"
              >
                {{ eventStatusLabel(event.status) }}
              </Badge>
            </CardHeader>
            <CardContent class="tw:grid tw:min-w-0 tw:gap-4">
              <dl class="tw:m-0 tw:grid tw:min-w-0 tw:grid-cols-1 tw:gap-2 tw:sm:grid-cols-2">
                <div
                  class="tw:grid tw:min-w-0 tw:gap-1 tw:rounded-lg tw:border tw:border-border tw:bg-muted/30 tw:p-3"
                >
                  <dt class="tw:text-xs tw:text-muted-foreground">Correlation ID</dt>
                  <dd class="tw:m-0 tw:break-all tw:text-sm tw:font-medium">
                    {{ event.correlation_id }}
                  </dd>
                </div>
                <div
                  class="tw:grid tw:min-w-0 tw:gap-1 tw:rounded-lg tw:border tw:border-border tw:bg-muted/30 tw:p-3"
                >
                  <dt class="tw:text-xs tw:text-muted-foreground">Event ID</dt>
                  <dd class="tw:m-0 tw:break-all tw:text-sm tw:font-medium">{{ event.id }}</dd>
                </div>
              </dl>
              <details class="tw:min-w-0">
                <summary class="tw:cursor-pointer tw:font-medium">
                  Event details, including any returned error information
                </summary>
                <pre
                  class="tw:mt-2 tw:max-h-80 tw:min-w-0 tw:overflow-auto tw:rounded-md tw:bg-muted/50 tw:p-3 tw:text-xs tw:text-foreground tw:whitespace-pre-wrap tw:break-all"
                  >{{ formatJson(event.details) }}</pre>
              </details>
            </CardContent>
            <CardFooter v-if="savedRunId(event)" class="tw:flex tw:flex-wrap tw:gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                class="reopen-button"
                :disabled="store.actionState.openSavedRun.pending"
                @click="reopenRun(savedRunId(event)!)"
              >
                {{
                  store.actionState.openSavedRun.pending
                    ? 'Opening saved run…'
                    : 'Reopen saved optimizer run'
                }}
              </Button>
            </CardFooter>
          </Card>
        </li>
      </ol>
    </template>

    <WorkspacePagination
      v-if="activity"
      :offset="activity.offset"
      :limit="activity.limit"
      :total="activity.total"
      :pending="isLoading"
      label="Activity pages"
      @page="loadActivity"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useForm } from '@tanstack/vue-form';
import ApiActionError from '@/components/ApiActionError.vue';
import RunSummary from '@/components/RunSummary.vue';
import WorkspacePageHeader from '@/components/WorkspacePageHeader.vue';
import WorkspaceCapabilityNotice from '@/components/WorkspaceCapabilityNotice.vue';
import WorkspacePagination from '@/components/WorkspacePagination.vue';
import ResourceFreshnessNotice from '@/components/ResourceFreshnessNotice.vue';
import { getPaginationMetadata } from '@/components/workspace-pagination-state';
import { Alert, AlertDescription } from '@/components/ui/alert';
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
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from '@/components/ui/empty';
import { FieldError, FieldGroup, FieldLabel, Field as UiField } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useWorkspace } from '@/composables/use-workspace';
import {
  ACTIVITY_PAGE_LIMITS,
  activityFilterDefaults,
  activityFilterSchema,
  isActivityPageLimit,
  selectedDateTimeFilter,
  type ActivityFilterValues,
} from '@/forms/activity-filters';
import type { ActivityQuery } from '@/services/api';
import type { ActivityEventResponse } from '@/types/api';

const store = useWorkspace();
const router = useRouter();
const activity = computed(() => store.activity);
const savedRunSummary = computed(() => store.currentRunSummary);
const savedSinceBound = store.activityFilters.since ?? null;
const savedUntilBound = store.activityFilters.until ?? null;
const sinceEdited = ref(false);
const untilEdited = ref(false);
const filterForm = useForm({
  defaultValues: activityFilterDefaults(store.activityFilters),
  validators: { onChange: activityFilterSchema },
  onSubmit: async ({ value }) => {
    await loadActivity(0, value);
  },
});
const filters = filterForm.useSelector((state) => state.values);
const isLoading = computed(() => store.actionState.loadActivity.pending);
const pagination = computed(() => {
  const page = activity.value;
  return getPaginationMetadata(page?.offset ?? 0, page?.limit ?? 1, page?.total ?? 0);
});
const pageNumber = computed(() => pagination.value.pageNumber);
const pageCount = computed(() => pagination.value.pageCount);

type ActivityTextFilterField = 'eventType' | 'status' | 'correlationId';

const COMMON_ACTIVITY_EVENT_TYPES = [
  { code: 'policy_activation', label: 'Policy revision activated' },
  { code: 'sync', label: 'Portfolio sync' },
  { code: 'optimizer_run', label: 'Optimizer run' },
  { code: 'recommendation_selection', label: 'Recommendation selection' },
  { code: 'recommendation_lot_review_intent', label: 'Tax-lot review selection' },
  { code: 'recommendation_annotation', label: 'Recommendation annotation' },
] as const;

const EVENT_CATEGORY_LABELS = new Map<string, string>(
  COMMON_ACTIVITY_EVENT_TYPES.map(({ code, label }): [string, string] => [code, label]),
);

function eventCategoryLabel(code: string): string {
  return EVENT_CATEGORY_LABELS.get(code) ?? 'Other activity event';
}

function eventSummary(event: ActivityEventResponse): string {
  const details = event.details;
  if (typeof details !== 'object' || details === null || Array.isArray(details)) {
    return 'Activity recorded; additional details were not returned.';
  }
  const value = details as Record<string, unknown>;
  const textValue = (key: string): string | null =>
    typeof value[key] === 'string' && value[key].trim() ? value[key].trim() : null;
  const numberValue = (key: string): string | null =>
    typeof value[key] === 'number' && Number.isFinite(value[key]) ? String(value[key]) : null;
  if (event.status.toLowerCase() === 'failed' || event.status.toLowerCase() === 'error') {
    const code = textValue('code') ?? textValue('error_code');
    const message = textValue('message') ?? textValue('error_summary');
    return (
      [message, code ? `Code: ${code}` : null].filter(Boolean).join(' · ') ||
      'The operation failed; no readable error details were returned.'
    );
  }
  if (event.event_type === 'policy_activation' && event.status.toLowerCase() === 'complete') {
    const revision = numberValue('revision_number');
    return revision
      ? `Policy revision ${revision} was activated.`
      : 'A policy revision was activated; revision number was not returned.';
  }
  if (event.event_type === 'sync' && event.status.toLowerCase() === 'complete') {
    const generation = numberValue('generation');
    const source = textValue('source');
    return `Portfolio sync completed${generation ? ` for generation ${generation}` : ''}${source ? ` from ${source}` : ''}. This records the sync outcome, not a current-state confirmation.`;
  }
  if (event.event_type === 'optimizer_run') {
    return 'An optimizer run was recorded. Recommendations are not orders or evidence of execution.';
  }
  if (
    event.event_type === 'recommendation_selection' &&
    event.status.toLowerCase() === 'complete'
  ) {
    const ids = Array.isArray(value.selected_group_ids) ? value.selected_group_ids : null;
    return `Recommendation selection updated${ids ? ` (${ids.length} groups selected)` : ''}; no trade was authorized or executed.`;
  }
  if (event.event_type === 'recommendation_lot_review_intent') {
    const lots = Array.isArray(value.broker_lot_ids) ? value.broker_lot_ids.length : null;
    return `Tax-lot review selection recorded${lots === null ? '' : ` (${lots} lots)`}; this is not an order or execution.`;
  }
  if (event.event_type === 'recommendation_annotation') {
    return 'A recommendation annotation was recorded; no trade was authorized or executed.';
  }
  return 'Activity recorded; see the returned details for information.';
}
function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? 'Unavailable';
}

function savedRunId(event: ActivityEventResponse): string | null {
  if (event.event_type !== 'optimizer_run') return null;
  const details = event.details;
  if (typeof details !== 'object' || details === null || Array.isArray(details)) return null;
  const runId = details.run_id;
  return typeof runId === 'string' && runId.length > 0 ? runId : null;
}

function statusBadgeVariant(value: string): 'destructive' | 'secondary' {
  return value.toLocaleLowerCase() === 'error' || value.toLocaleLowerCase() === 'failed'
    ? 'destructive'
    : 'secondary';
}

function setTextFilter(field: ActivityTextFilterField, value: string | number): void {
  filterForm.setFieldValue(field, String(value));
}

function selectCommonEventType(event: Event): void {
  const target = event.target;
  if (!(target instanceof HTMLSelectElement)) return;
  if (target.value) filterForm.setFieldValue('eventType', target.value);
}

function eventStatusLabel(status: string): string {
  const labels = new Map([
    ['complete', 'Completed'],
    ['failed', 'Failed'],
    ['error', 'Error'],
  ]);
  return labels.get(status.toLowerCase()) ?? status;
}

function setDateFilter(field: 'since' | 'until', value: string | number): void {
  if (typeof value !== 'string') return;
  filterForm.setFieldValue(field, value);
  if (field === 'since') sinceEdited.value = true;
  else untilEdited.value = true;
}

function updatePageLimit(value: unknown): void {
  if (typeof value !== 'string') return;
  const limit = Number(value);
  if (isActivityPageLimit(limit)) filterForm.setFieldValue('limit', limit);
}

function currentFilters(values: ActivityFilterValues, offset: number): ActivityQuery {
  const sinceFilter = selectedDateTimeFilter(values.since, sinceEdited.value, savedSinceBound);
  const untilFilter = selectedDateTimeFilter(values.until, untilEdited.value, savedUntilBound);
  return {
    ...(values.eventType.trim() ? { event_type: values.eventType.trim() } : {}),
    ...(values.status.trim() ? { status: values.status.trim() } : {}),
    ...(values.correlationId.trim() ? { correlation_id: values.correlationId.trim() } : {}),
    ...(sinceFilter ? { since: sinceFilter } : {}),
    ...(untilFilter ? { until: untilFilter } : {}),
    offset,
    limit: values.limit,
  };
}

async function loadActivity(
  offset: number,
  values: ActivityFilterValues = filters.value,
): Promise<void> {
  try {
    await store.loadActivity(currentFilters(values, offset));
  } catch {
    // The shared store retains the structured API error for the page.
  }
}

function applyFilters(): void {
  void filterForm.handleSubmit();
}

function clearFilters(): void {
  const clearedFilters: ActivityFilterValues = {
    eventType: '',
    status: '',
    correlationId: '',
    since: '',
    until: '',
    limit: 25,
  };
  filterForm.reset(clearedFilters);
  sinceEdited.value = true;
  untilEdited.value = true;
  void loadActivity(0, clearedFilters);
}

function refresh(): void {
  void loadActivity(activity.value?.offset ?? 0);
}

async function reopenRun(runId: string): Promise<void> {
  try {
    await store.openSavedRun(runId);
    await router.push('/recommendations');
  } catch {
    // A structured saved-run error is shown above; no order action is initiated.
  }
}

onMounted(() => {
  void loadActivity(store.activityFilters.offset ?? 0, filters.value);
});
</script>

<style scoped>
:global([data-activity-root]) {
  color: var(--foreground);
}

:global([data-activity-root] .event-card h2) {
  color: var(--foreground);
  font-size: var(--tw-text-base);
  font-weight: 600;
  line-height: 1.375;
}

:global([data-activity-root] input[data-slot='input']) {
  appearance: none;
  border: 1px solid var(--input);
  border-radius: var(--radius-md);
  background-color: transparent;
  color: var(--foreground);
  font-family: inherit;
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
}

:global([data-activity-root] button[data-slot='button']),
:global([data-activity-root] button[data-slot='select-trigger']) {
  appearance: none;
  font-family: inherit;
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
  text-transform: none;
}

:global([data-activity-root] button[data-slot='select-trigger']) {
  border: 1px solid var(--input);
  background-color: transparent;
  color: var(--foreground);
}

:global([data-activity-root] pre) {
  overflow-wrap: anywhere;
}
:global(.activity-select-content) {
  color: var(--popover-foreground);
  font-family: inherit;
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
}
</style>
