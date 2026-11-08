<template>
  <section class="workspace-page activity-page" aria-labelledby="activity-title">
    <header class="page-header">
      <div>
        <p class="eyebrow">Workspace history</p>
        <h1 id="activity-title">Activity</h1>
        <p class="page-subtitle">
          Timestamped API events, structured details, and saved optimizer-run reopening. Reopening a
          run does not approve any trade.
        </p>
      </div>
      <button type="button" class="primary-button" :disabled="isLoading" @click="refresh">
        {{ isLoading ? 'Loading…' : 'Refresh activity' }}
      </button>
    </header>

    <p class="demo-notice" role="status">
      <strong>DEMO ONLY.</strong> This local activity view never connects to E*TRADE and contains no
      order preview or submission controls.
    </p>

    <div class="error-stack">
      <ApiActionError
        :error="store.actionState.loadActivity.error"
        title="Activity could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.openSavedRun.error"
        title="Saved optimizer run could not be reopened"
      />
    </div>

    <section v-if="savedRunSummary" class="summary-card" aria-labelledby="saved-run-title">
      <div class="section-heading">
        <div>
          <h2 id="saved-run-title">Saved run summary and frozen settings</h2>
          <p class="section-subtitle">
            Values below are from the API run summary. Only the fields returned by the summary DTO
            are shown; no missing assumptions are reconstructed.
          </p>
        </div>
        <span class="demo-badge">DEMO · non-actionable</span>
      </div>
      <dl class="run-summary-grid">
        <div>
          <dt>Run ID</dt>
          <dd>{{ savedRunSummary.run_id }}</dd>
        </div>
        <div>
          <dt>Status / mode</dt>
          <dd>{{ savedRunSummary.status }} · {{ savedRunSummary.mode }}</dd>
        </div>
        <div>
          <dt>Policy revision</dt>
          <dd>{{ savedRunSummary.policy_revision_id }}</dd>
        </div>
        <div>
          <dt>Source generation</dt>
          <dd>{{ savedRunSummary.source_generation }}</dd>
        </div>
        <div>
          <dt>As of</dt>
          <dd>{{ savedRunSummary.as_of }}</dd>
        </div>
        <div>
          <dt>Proposed trade date</dt>
          <dd>{{ savedRunSummary.proposed_trade_date ?? 'Unavailable' }}</dd>
        </div>
        <div>
          <dt>Solver</dt>
          <dd>{{ savedRunSummary.solver_version }}</dd>
        </div>
        <div>
          <dt>Tax profile configured</dt>
          <dd>{{ savedRunSummary.tax_profile_configured ? 'Yes' : 'No' }}</dd>
        </div>
        <div>
          <dt>Tax estimate status</dt>
          <dd>{{ savedRunSummary.estimated_tax_benefit_status }}</dd>
        </div>
        <div>
          <dt>Estimated realized ST</dt>
          <dd>{{ displayUsd(savedRunSummary.estimated_realized_st_usd) }}</dd>
        </div>
        <div>
          <dt>Estimated realized LT</dt>
          <dd>{{ displayUsd(savedRunSummary.estimated_realized_lt_usd) }}</dd>
        </div>
        <div>
          <dt>Estimated tax benefit</dt>
          <dd>{{ displayUsd(savedRunSummary.estimated_tax_benefit_usd) }}</dd>
        </div>
        <div>
          <dt>Cash before / after</dt>
          <dd>
            {{ displayUsd(savedRunSummary.cash_before_usd) }} /
            {{ displayUsd(savedRunSummary.cash_after_usd) }}
          </dd>
        </div>
      </dl>
      <h3>Batch settings returned by the API</h3>
      <pre>{{ formatJson(savedRunSummary.batch_settings) }}</pre>
      <p
        v-if="savedRunSummary.input_fingerprint || savedRunSummary.source_checksum"
        class="provenance-note"
      >
        Provenance — input fingerprint: {{ savedRunSummary.input_fingerprint ?? 'Unavailable' }} ·
        source checksum: {{ savedRunSummary.source_checksum ?? 'Unavailable' }}
      </p>
      <ul v-if="savedRunSummary.warnings.length" class="warning-list">
        <li v-for="warning in savedRunSummary.warnings" :key="warning">{{ warning }}</li>
      </ul>
    </section>

    <form class="filter-panel" @submit.prevent="applyFilters">
      <label>
        <span>Event type</span>
        <input v-model="eventType" type="search" placeholder="Exact API event type" />
      </label>
      <label>
        <span>Status</span>
        <input v-model="status" type="search" placeholder="Exact API status" />
      </label>
      <label>
        <span>Correlation ID</span>
        <input v-model="correlationId" type="search" placeholder="Correlation ID" />
      </label>
      <label>
        <span>Since (UTC)</span>
        <input
          v-model="since"
          type="datetime-local"
          step="any"
          @input="markDateTimeEdited('since')"
        />
      </label>
      <label>
        <span>Until (UTC)</span>
        <input
          v-model="until"
          type="datetime-local"
          step="any"
          @input="markDateTimeEdited('until')"
        />
      </label>
      <label>
        <span>Rows per page</span>
        <select v-model.number="pageLimit">
          <option :value="25">25</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
          <option :value="250">250</option>
        </select>
      </label>
      <button type="submit" class="secondary-button" :disabled="isLoading">Apply filters</button>
      <button type="button" class="text-button" :disabled="isLoading" @click="clearFilters">
        Clear filters
      </button>
    </form>

    <p
      v-if="store.actionState.loadActivity.pending && !activity"
      class="state-message"
      role="status"
    >
      Loading activity from the local API…
    </p>
    <section v-else-if="!activity" class="empty-state" aria-live="polite">
      <h2>No activity page loaded</h2>
      <p>Retry to request current activity. No events are generated by this page.</p>
      <button type="button" class="secondary-button" :disabled="isLoading" @click="refresh">
        Retry loading activity
      </button>
    </section>
    <section v-else-if="activity.total === 0" class="empty-state" aria-live="polite">
      <h2>No activity events returned</h2>
      <p>The API returned no events for the selected filters.</p>
    </section>
    <template v-else>
      <p class="results-summary">
        {{ activity.items.length }} events on this page · {{ activity.total }} matching events ·
        page {{ pageNumber }} of {{ pageCount }}
      </p>
      <section v-if="activity.items.length === 0" class="empty-state" aria-live="polite">
        <h2>No events on this page</h2>
        <p>
          The API returned no events for this offset. Use the filters or return to a previous page.
        </p>
      </section>
      <ol v-else class="event-list" aria-label="Activity events">
        <li v-for="event in activity.items" :key="event.id" class="event-card">
          <header class="event-heading">
            <div>
              <h2>{{ event.event_type }}</h2>
              <p>{{ event.created_at }}</p>
            </div>
            <span class="status-badge" :class="statusClass(event.status)">{{ event.status }}</span>
          </header>
          <dl class="event-meta">
            <div>
              <dt>Correlation ID</dt>
              <dd>{{ event.correlation_id }}</dd>
            </div>
            <div>
              <dt>Event ID</dt>
              <dd>{{ event.id }}</dd>
            </div>
          </dl>
          <details>
            <summary>Event details, including any returned error information</summary>
            <pre>{{ formatJson(event.details) }}</pre>
          </details>
          <button
            v-if="savedRunId(event)"
            type="button"
            class="secondary-button reopen-button"
            :disabled="store.actionState.openSavedRun.pending"
            @click="reopenRun(savedRunId(event)!)"
          >
            {{
              store.actionState.openSavedRun.pending
                ? 'Opening saved run…'
                : 'Reopen saved optimizer run'
            }}
          </button>
        </li>
      </ol>
      <nav class="pagination" aria-label="Activity pages">
        <button
          type="button"
          class="secondary-button"
          :disabled="isLoading || activity.offset === 0"
          @click="changePage(-1)"
        >
          Previous page
        </button>
        <span>Page {{ pageNumber }} of {{ pageCount }}</span>
        <button
          type="button"
          class="secondary-button"
          :disabled="isLoading || activity.offset + activity.limit >= activity.total"
          @click="changePage(1)"
        >
          Next page
        </button>
      </nav>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import ApiActionError from '@/components/ApiActionError.vue';
import { useWorkspaceStore } from '@/stores/workspace-store';
import type { ActivityQuery } from '@/services/api';
import type { ActivityEventResponse, JSONValue } from '@/types/api';

const store = useWorkspaceStore();
const router = useRouter();
const activity = computed(() => store.activity);
const savedRunSummary = computed(() => store.currentRunSummary);
const eventType = ref(store.activityFilters.event_type ?? '');
const status = ref(store.activityFilters.status ?? '');
const correlationId = ref(store.activityFilters.correlation_id ?? '');
const since = ref(utcFilterToDateTimeLocal(store.activityFilters.since));
const until = ref(utcFilterToDateTimeLocal(store.activityFilters.until));
const savedSinceBound = store.activityFilters.since ?? null;
const savedUntilBound = store.activityFilters.until ?? null;
const sinceEdited = ref(false);
const untilEdited = ref(false);
const pageLimit = ref(store.activityFilters.limit ?? 25);
const isLoading = computed(() => store.actionState.loadActivity.pending);
const pageNumber = computed(() => {
  const page = activity.value;
  return page ? Math.floor(page.offset / page.limit) + 1 : 1;
});
const pageCount = computed(() => {
  const page = activity.value;
  return page ? Math.max(1, Math.ceil(page.total / page.limit)) : 1;
});

function displayUsd(value: string | null): string {
  return value === null ? 'Unavailable' : `${value} USD`;
}

function formatJson(value: JSONValue): string {
  return JSON.stringify(value, null, 2);
}

function savedRunId(event: ActivityEventResponse): string | null {
  if (event.event_type !== 'optimizer_run') return null;
  const details = event.details;
  if (typeof details !== 'object' || details === null || Array.isArray(details)) return null;
  const runId = details.run_id;
  return typeof runId === 'string' && runId.length > 0 ? runId : null;
}

function statusClass(value: string): string {
  return value.toLocaleLowerCase() === 'error' || value.toLocaleLowerCase() === 'failed'
    ? 'status-error'
    : 'status-neutral';
}

function markDateTimeEdited(bound: 'since' | 'until'): void {
  if (bound === 'since') sinceEdited.value = true;
  else untilEdited.value = true;
}

function utcFilterToDateTimeLocal(value: string | null | undefined): string {
  if (!value) return '';
  const timestamp = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
  return Number.isNaN(timestamp.getTime())
    ? ''
    : timestamp
        .toISOString()
        .replace(/\.000Z$/, '')
        .replace(/Z$/, '');
}

function dateTimeLocalToUtcFilter(value: string): string {
  return `${value.length === 16 ? `${value}:00` : value}Z`;
}

function selectedDateTimeFilter(
  value: string,
  edited: boolean,
  savedBound: string | null,
): string | undefined {
  if (!edited && savedBound) return savedBound;
  return value ? dateTimeLocalToUtcFilter(value) : undefined;
}

function currentFilters(offset: number): ActivityQuery {
  const sinceFilter = selectedDateTimeFilter(since.value, sinceEdited.value, savedSinceBound);
  const untilFilter = selectedDateTimeFilter(until.value, untilEdited.value, savedUntilBound);
  return {
    ...(eventType.value.trim() ? { event_type: eventType.value.trim() } : {}),
    ...(status.value.trim() ? { status: status.value.trim() } : {}),
    ...(correlationId.value.trim() ? { correlation_id: correlationId.value.trim() } : {}),
    ...(sinceFilter ? { since: sinceFilter } : {}),
    ...(untilFilter ? { until: untilFilter } : {}),
    offset,
    limit: pageLimit.value,
  };
}

async function loadActivity(offset: number): Promise<void> {
  try {
    await store.loadActivity(currentFilters(offset));
  } catch {
    // The shared store retains the structured API error for the page.
  }
}

function applyFilters(): void {
  void loadActivity(0);
}

function clearFilters(): void {
  eventType.value = '';
  status.value = '';
  correlationId.value = '';
  since.value = '';
  until.value = '';
  sinceEdited.value = true;
  untilEdited.value = true;
  pageLimit.value = 25;
  void loadActivity(0);
}

function refresh(): void {
  void loadActivity(activity.value?.offset ?? 0);
}

function changePage(direction: -1 | 1): void {
  const page = activity.value;
  if (!page) return;
  const nextOffset = Math.max(0, page.offset + direction * page.limit);
  void loadActivity(nextOffset);
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
  void loadActivity(store.activityFilters.offset ?? 0);
});
</script>

<style scoped>
.activity-page {
  max-width: 1600px;
}

.event-heading,
.pagination {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.demo-notice {
  margin: 0;
  padding: 0.8rem 1rem;
  border: 1px solid #f2dcad;
  border-radius: 0.65rem;
  background: #fff7e8;
  color: #765016;
  font-size: 0.82rem;
  line-height: 1.5;
}
.error-stack {
  display: grid;
  gap: 0.6rem;
}
.filter-panel,
.summary-card,
.empty-state,
.event-card {
  min-width: 0;
  padding: 1rem;
  border: 1px solid #dce6eb;
  border-radius: 0.8rem;
  background: #fff;
  box-shadow: 0 4px 20px rgb(18 55 77 / 4.5%);
}
.filter-panel {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 0.75rem;
}
.filter-panel label {
  display: grid;
  min-width: min(13rem, 100%);
  gap: 0.3rem;
  color: #466779;
  font-size: 0.75rem;
  font-weight: 700;
}
input,
select,
button {
  min-height: 2.4rem;
  border: 1px solid #b8c9d2;
  border-radius: 0.45rem;
  background: #fff;
  color: #203f52;
  font: inherit;
}
input,
select {
  padding: 0.4rem 0.55rem;
}
button {
  padding: 0.45rem 0.8rem;
  cursor: pointer;
  font-size: 0.76rem;
  font-weight: 750;
}
button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.primary-button {
  border-color: #067777;
  background: #087f7d;
  color: white;
}
.secondary-button {
  border-color: #bfd0d8;
  background: #f7fafb;
}
.text-button {
  border: 0;
  color: #087f7d;
  text-decoration: underline;
}
.section-heading {
  align-items: center;
  margin-bottom: 0.8rem;
}
.section-heading h2,
.event-heading h2,
.empty-state h2 {
  margin: 0;
  color: #10263d;
  font-size: 1.05rem;
}
.demo-badge {
  flex: 0 0 auto;
  padding: 0.25rem 0.55rem;
  border-radius: 2rem;
  background: #fff1d2;
  color: #77520d;
  font-size: 0.68rem;
  font-weight: 800;
}
.run-summary-grid,
.event-meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.65rem;
  margin: 0;
}
.run-summary-grid > div,
.event-meta > div {
  min-width: 0;
  padding: 0.6rem;
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
  font-size: 0.76rem;
  font-weight: 700;
  overflow-wrap: anywhere;
}
.summary-card h3 {
  margin: 0.9rem 0 0.4rem;
  color: #526c7c;
  font-size: 0.75rem;
  text-transform: uppercase;
}
pre {
  max-height: 20rem;
  margin: 0;
  padding: 0.75rem;
  overflow: auto;
  border-radius: 0.5rem;
  background: #f5f8fa;
  color: #29475a;
  font-size: 0.7rem;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.provenance-note,
.warning-list,
.state-message,
.empty-state p,
.results-summary {
  color: #657d8b;
  font-size: 0.78rem;
  line-height: 1.5;
}
.provenance-note {
  margin: 0.6rem 0 0;
  overflow-wrap: anywhere;
}
.warning-list {
  margin: 0.6rem 0 0;
  padding-left: 1.2rem;
  color: #765016;
}
.results-summary {
  margin: 0;
}
.event-list {
  display: grid;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.event-heading {
  align-items: center;
  margin-bottom: 0.7rem;
}
.event-heading h2 {
  font-size: 0.95rem;
  text-transform: capitalize;
}
.event-heading p {
  margin: 0.25rem 0 0;
  color: #657d8b;
  font-size: 0.72rem;
}
.status-badge {
  flex: 0 0 auto;
  padding: 0.25rem 0.55rem;
  border-radius: 2rem;
  font-size: 0.68rem;
  font-weight: 800;
}
.status-neutral {
  background: #eaf3f5;
  color: #315c6b;
}
.status-error {
  background: #fff0f0;
  color: #812f36;
}
.event-meta {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-bottom: 0.7rem;
}
details {
  color: #405f71;
  font-size: 0.76rem;
}
summary {
  cursor: pointer;
  font-weight: 700;
}
details pre {
  margin-top: 0.5rem;
}
.reopen-button {
  margin-top: 0.7rem;
}
.pagination {
  align-items: center;
  justify-content: center;
  color: #526c7c;
  font-size: 0.78rem;
}
.empty-state p {
  margin: 0.6rem 0 0.8rem;
}
@media (max-width: 900px) {
  .run-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 650px) {
  .page-header,
  .event-heading,
  .pagination {
    align-items: stretch;
    flex-direction: column;
  }
  .filter-panel label {
    width: 100%;
  }
  .run-summary-grid,
  .event-meta {
    grid-template-columns: 1fr;
  }
}
</style>
