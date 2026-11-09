<template>
  <section
    v-if="mode === 'overview'"
    class="overview-run-summary"
    aria-label="Run summary and frozen context"
  >
    <p v-if="pending" class="pending-message" role="status">
      A review update is awaiting API confirmation. Prior run metrics and basket effects are
      withheld.
    </p>
    <template v-else>
      <dl v-if="record && showMetrics" class="overview-metrics">
        <div>
          <dt>Realized short-term P/L (estimated)</dt>
          <dd>{{ formatUsd(record.estimated_realized_st_usd) }}</dd>
        </div>
        <div>
          <dt>Realized long-term P/L (estimated)</dt>
          <dd>{{ formatUsd(record.estimated_realized_lt_usd) }}</dd>
        </div>
        <div>
          <dt>Estimated tax benefit</dt>
          <dd>{{ formatUsd(record.estimated_tax_benefit_usd) }}</dd>
        </div>
        <div>
          <dt>Lots sold / positions exited</dt>
          <dd>{{ record.lots_sold_count }} / {{ record.positions_exited_count }}</dd>
        </div>
        <div>
          <dt>Orders in recommendation</dt>
          <dd>{{ record.orders_count }}</dd>
        </div>
        <div>
          <dt>Cash before / after</dt>
          <dd>{{ formatUsd(record.cash_before_usd) }} / {{ formatUsd(record.cash_after_usd) }}</dd>
        </div>
        <div>
          <dt>Tax estimate status</dt>
          <dd>{{ record.estimated_tax_benefit_status }}</dd>
        </div>
      </dl>
      <section
        v-if="record || context"
        class="frozen-context overview-context"
        aria-label="Overview frozen run context"
      >
        <h3>Frozen run policy context</h3>
        <template v-if="context?.available">
          <p>
            {{ view === 'saved' ? 'Historical saved run' : 'Run policy snapshot' }} · revision
            {{ context.policy_revision_id }} · {{ context.source ?? 'Unavailable source' }}
          </p>
          <p v-if="context.sleeves === null">Frozen sleeve labels and targets: Unavailable</p>
          <ul v-else>
            <li v-for="sleeve in context.sleeves" :key="sleeve.sleeve_key">
              {{ sleeve.display_name }} · target {{ formatPercent(sleeve.target_pct) }}
            </li>
          </ul>
          <details>
            <summary>Frozen policy assumptions and allowed securities</summary>
            <pre>{{ formatJson(context.settings) }}</pre>
            <p>Allowed securities: {{ formatJson(context.allowed_securities) }}</p>
            <p>Overrides: {{ formatJson(context.overrides) }}</p>
          </details>
        </template>
        <p v-else>
          Unavailable ({{
            context?.unavailable_reason ?? 'the API returned no frozen run context'
          }}). Active policy data is not used to reconstruct run history.
        </p>
      </section>
    </template>
  </section>

  <section v-else-if="record || pending" class="run-summary" :aria-labelledby="headingId">
    <h2 v-if="pending" :id="headingId" class="sr-only">Run summary pending</h2>
    <p
      v-if="mode === 'review' && provenanceLabel"
      class="provenance-banner"
      :data-view="view ?? 'unknown'"
      role="status"
    >
      <strong>{{ provenanceLabel }}</strong>
      <span>Run {{ record?.run_id ?? 'Unavailable' }}</span>
      <span>Policy {{ record?.policy_revision_id ?? 'Unavailable' }}</span>
      <span>Source generation {{ record?.source_generation ?? 'Unavailable' }}</span>
      <span>As of {{ record?.as_of ?? 'Unavailable' }}</span>
      <span>Proposed trade date {{ record?.proposed_trade_date ?? 'Unavailable' }}</span>
    </p>

    <p v-if="pending" class="pending-message" role="status">
      The requested selection or annotation is being saved or re-solved. Previous basket effects are
      withheld until the API responds; no unconfirmed selection is shown as active.
    </p>
    <template v-else-if="record">
      <div class="run-title-row">
        <div>
          <h2 :id="headingId">
            <template v-if="mode === 'saved'">Saved run summary and frozen settings</template>
            <template v-else
              >{{ record.solver_version }} recommendations · {{ record.status }}</template
            >
          </h2>
          <p v-if="mode === 'review'">
            {{ record.demo ? 'DEMO hypothetical data' : 'API run' }} ·
            {{
              record.actionable
                ? 'API marks this run actionable'
                : 'API marks this run non-actionable'
            }}
          </p>
          <p v-if="mode === 'review'" class="review-capability-note">
            No order preview, approval, or submission controls are available.
          </p>
          <p v-else-if="mode === 'saved'">
            Historical API summary only. Missing assumptions are not reconstructed from current
            policy.
          </p>
        </div>
        <span class="demo-badge">
          {{
            record.demo
              ? 'DEMO · non-actionable'
              : record.actionable
                ? 'API-marked actionable · no order controls'
                : 'NON-ACTIONABLE'
          }}
        </span>
      </div>

      <p v-if="mode === 'review' && record.solver_version === 'DEMO'" class="warning-banner">
        DEMO solver output is not a real optimizer feasibility result. Treat every value as
        hypothetical and non-executable.
      </p>
      <p
        v-if="mode === 'review' && record.estimated_tax_benefit_status === 'optimizer_unavailable'"
        class="warning-banner"
      >
        The real optimizer is unavailable. No production optimization or feasibility claim is made.
      </p>

      <dl :class="mode === 'saved' ? 'saved-metrics' : 'metric-grid'">
        <template v-if="mode === 'saved'">
          <div>
            <dt>Run ID</dt>
            <dd>{{ record.run_id }}</dd>
          </div>
          <div>
            <dt>Status / mode</dt>
            <dd>{{ record.status }} · {{ record.mode }}</dd>
          </div>
          <div>
            <dt>Policy revision</dt>
            <dd>{{ record.policy_revision_id }}</dd>
          </div>
          <div>
            <dt>Source generation</dt>
            <dd>{{ record.source_generation }}</dd>
          </div>
          <div>
            <dt>As of</dt>
            <dd>{{ record.as_of }}</dd>
          </div>
          <div>
            <dt>Proposed trade date</dt>
            <dd>{{ record.proposed_trade_date ?? 'Unavailable' }}</dd>
          </div>
          <div>
            <dt>Solver</dt>
            <dd>{{ record.solver_version }}</dd>
          </div>
          <div>
            <dt>Tax profile configured</dt>
            <dd>{{ record.tax_profile_configured ? 'Yes' : 'No' }}</dd>
          </div>
          <div>
            <dt>Tax estimate status</dt>
            <dd>{{ record.estimated_tax_benefit_status }}</dd>
          </div>
        </template>
        <div>
          <dt>Estimated realized ST</dt>
          <dd>{{ money(record.estimated_realized_st_usd) }}</dd>
        </div>
        <div>
          <dt>Estimated realized LT</dt>
          <dd>{{ money(record.estimated_realized_lt_usd) }}</dd>
        </div>
        <div>
          <dt>Estimated tax benefit</dt>
          <dd>{{ money(record.estimated_tax_benefit_usd) }}</dd>
        </div>
        <div v-if="mode === 'review'">
          <dt>Tax estimate status</dt>
          <dd>{{ record.estimated_tax_benefit_status }}</dd>
        </div>
        <div>
          <dt>Cash before / after</dt>
          <dd>{{ money(record.cash_before_usd) }} / {{ money(record.cash_after_usd) }}</dd>
        </div>
        <template v-if="mode === 'review'">
          <div>
            <dt>Risk tracking</dt>
            <dd>Unavailable (not returned by API)</dd>
            <small>Not returned as a run-level risk score</small>
          </div>
          <div>
            <dt>Hard constraints</dt>
            <dd>
              {{
                record.constraints_satisfied == null
                  ? 'Unavailable (not evaluated)'
                  : record.constraints_satisfied
                    ? 'Satisfied'
                    : 'Not satisfied'
              }}
            </dd>
          </div>
        </template>
        <div>
          <dt>API-reported sell lots / exited positions / orders</dt>
          <dd>
            {{ record.lots_sold_count }} / {{ record.positions_exited_count }} /
            {{ record.orders_count }}
          </dd>
        </div>
        <div>
          <dt>Tax profile</dt>
          <dd>{{ record.tax_profile_configured ? 'Configured' : 'Incomplete' }}</dd>
        </div>
      </dl>

      <template v-if="mode === 'review'">
        <p v-if="record.no_trade_reason != null" class="no-trade-reason">
          <strong>No beneficial trades identified / API no-trade reason:</strong>
          {{ formatJson(record.no_trade_reason) }}
        </p>
        <p v-else-if="groupCount === 0" class="no-trade-reason">
          No beneficial trades identified. The API returned no recommendation groups.
        </p>
      </template>

      <h3 v-if="mode === 'saved'">Batch settings returned by the API</h3>
      <h3 v-else-if="mode === 'review'">Frozen API batch settings and provenance</h3>
      <pre>{{ formatJson(record.batch_settings) }}</pre>

      <section class="frozen-context" aria-label="Frozen run display context">
        <h3>Frozen policy display context</h3>
        <template v-if="context?.available">
          <p>
            Policy revision {{ context.policy_revision_id }} ·
            {{ context.source ?? 'Unavailable source' }}
          </p>
          <p v-if="context.sleeves === null">Frozen sleeve labels and targets: Unavailable</p>
          <ul v-else>
            <li v-for="sleeve in context.sleeves" :key="sleeve.sleeve_key">
              {{ sleeve.display_name }} · target {{ formatPercent(sleeve.target_pct) }}
            </li>
          </ul>
          <h4>Frozen policy assumptions</h4>
          <pre>{{ formatJson(context.settings ?? 'Unavailable') }}</pre>
          <p>Allowed securities: {{ formatJson(context.allowed_securities ?? 'Unavailable') }}</p>
          <p>Overrides: {{ formatJson(context.overrides ?? 'Unavailable') }}</p>
        </template>
        <p v-else>
          Unavailable ({{
            context?.unavailable_reason ?? 'the API returned no frozen run context'
          }}). Active policy data is not used to reconstruct this historical run.
        </p>
      </section>

      <p class="provenance-note">
        Provenance — input fingerprint: {{ record.input_fingerprint ?? 'Unavailable' }} · source
        checksum: {{ record.source_checksum ?? 'Unavailable' }}
      </p>
      <p v-if="mode === 'review' && summary">
        Saved summary status: {{ summary.status }} · {{ summary.mode }}
      </p>
      <ul v-if="record.warnings.length" class="warning-list" aria-label="Run warnings">
        <li v-for="warning in record.warnings" :key="warning">{{ warning }}</li>
      </ul>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, useId } from 'vue';
import type {
  FrozenRunDisplayContextResponse,
  OptimizerRecommendationsResponse,
  OptimizerRunResponse,
} from '@/types/api';
import { formatPercent, formatUsd } from '@/utils/display-values';

const props = withDefaults(
  defineProps<{
    mode: 'review' | 'overview' | 'saved';
    run?: OptimizerRecommendationsResponse | null;
    summary?: OptimizerRunResponse | null;
    context?: FrozenRunDisplayContextResponse | null;
    pending?: boolean;
    showMetrics?: boolean;
    view?: string | null;
    provenanceLabel?: string;
  }>(),
  {
    run: null,
    summary: null,
    context: null,
    pending: false,
    showMetrics: true,
    view: null,
    provenanceLabel: '',
  },
);

const record = computed(() => props.run ?? props.summary);
const context = computed(() => props.context ?? record.value?.frozen_display_context ?? null);
const groupCount = computed(() => (props.run ? props.run.groups.length : null));
const headingId = `run-summary-${useId()}`;

function money(value: string | null | undefined): string {
  return formatUsd(
    value,
    props.mode === 'review' ? 'Unavailable (not returned by API)' : 'Unavailable',
  );
}

function formatJson(value: unknown): string {
  if (value == null) return 'Unavailable';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2) ?? 'Unavailable';
  } catch {
    return 'Unavailable';
  }
}
</script>

<style scoped>
.run-summary {
  display: grid;
  gap: 0.8rem;
  min-width: 0;
  padding: 1rem;
  border: 1px solid #dce6eb;
  border-radius: 0.8rem;
  background: #fff;
  box-shadow: 0 4px 20px rgb(18 55 77 / 4.5%);
}

.provenance-banner,
.pending-message,
.warning-banner {
  margin: 0;
  padding: 0.8rem 1rem;
  border-radius: 0.65rem;
  line-height: 1.5;
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

.provenance-banner[data-view='stale'],
.provenance-banner[data-view='unverified'] {
  border-color: #e8d39a;
  background: #fff8e7;
}

.pending-message {
  border: 1px solid #9dcbd0;
  background: #eef9fa;
  color: #245a62;
  font-size: 0.8rem;
}

.warning-banner {
  border: 1px solid #e8d39a;
  background: #fff8e7;
  color: #70501b;
  font-size: 0.78rem;
}

.run-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.run-title-row h2 {
  margin: 0;
  color: #10263d;
  font-size: 1.1rem;
}

.run-title-row p {
  margin: 0.35rem 0 0;
  color: #61798a;
  line-height: 1.5;
}

.demo-badge {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  padding: 0.25rem 0.55rem;
  border-radius: 999px;
  background: #fff1d2;
  color: #77520d;
  font-size: 0.68rem;
  font-weight: 800;
  white-space: nowrap;
}

.metric-grid,
.saved-metrics,
.overview-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.6rem;
  margin: 0;
}

.metric-grid > div,
.saved-metrics > div,
.overview-metrics > div {
  min-width: 0;
  padding: 0.65rem;
  border: 1px solid #eaf0f3;
  border-radius: 0.55rem;
}

.metric-grid dt,
.saved-metrics dt,
.overview-metrics dt {
  color: #647c8b;
  font-size: 0.7rem;
}

.metric-grid dd,
.saved-metrics dd,
.overview-metrics dd {
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
.provenance-note {
  margin: 0;
  color: #526c7c;
  font-size: 0.78rem;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.run-summary h3,
.run-summary h4,
.overview-context h3 {
  margin: 0.2rem 0 0;
  color: #29475a;
  font-size: 0.9rem;
}

.run-summary pre,
.overview-context pre {
  max-height: 16rem;
  margin: 0;
  padding: 0.7rem;
  overflow: auto;
  border-radius: 0.5rem;
  background: #f5f8fa;
  color: #29475a;
  font-size: 0.76rem;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.frozen-context {
  display: grid;
  gap: 0.35rem;
  margin-top: 0.15rem;
  padding: 0.75rem;
  border: 1px solid #e0e9ed;
  border-radius: 0.55rem;
  color: #405f71;
  font-size: 0.76rem;
}

.frozen-context p,
.frozen-context ul {
  margin: 0.2rem 0;
}

.frozen-context ul {
  padding-left: 1.2rem;
}

.frozen-context details summary {
  cursor: pointer;
  font-weight: 700;
}

.frozen-context details pre {
  margin-top: 0.5rem;
}

.warning-list {
  margin: 0;
  padding-left: 1.2rem;
  color: #765016;
  font-size: 0.78rem;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.overview-run-summary {
  display: grid;
  gap: 0.7rem;
  min-width: 0;
}

.overview-context {
  margin-top: 0.2rem;
}

@media (max-width: 760px) {
  .run-title-row {
    flex-direction: column;
    align-items: stretch;
  }

  .provenance-banner {
    display: grid;
  }

  .metric-grid,
  .saved-metrics,
  .overview-metrics {
    grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
  }
}
</style>
