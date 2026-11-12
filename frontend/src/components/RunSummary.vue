<template>
  <section
    v-if="mode === 'overview'"
    class="overview-run-summary tw:flex tw:min-w-0 tw:flex-col tw:gap-2.5"
    aria-label="Run summary and frozen context"
  >
    <Alert v-if="pending" role="status" aria-live="polite">
      A review update is awaiting API confirmation. Prior run metrics and basket effects are
      withheld.
    </Alert>
    <template v-else>
      <dl
        v-if="record && showMetrics"
        class="overview-metrics tw:m-0 tw:grid tw:grid-cols-1 tw:gap-2 tw:sm:grid-cols-2 tw:xl:grid-cols-4"
      >
        <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
          <dt class="tw:text-xs tw:text-muted-foreground">Realized short-term P/L (estimated)</dt>
          <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold tw:tabular-nums">
            {{ formatUsd(record.estimated_realized_st_usd) }}
          </dd>
        </div>
        <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
          <dt class="tw:text-xs tw:text-muted-foreground">Realized long-term P/L (estimated)</dt>
          <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold tw:tabular-nums">
            {{ formatUsd(record.estimated_realized_lt_usd) }}
          </dd>
        </div>
        <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
          <dt class="tw:text-xs tw:text-muted-foreground">Estimated tax benefit</dt>
          <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold tw:tabular-nums">
            {{ formatUsd(record.estimated_tax_benefit_usd) }}
          </dd>
        </div>
        <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
          <dt class="tw:text-xs tw:text-muted-foreground">Lots sold / positions exited</dt>
          <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">
            {{ record.lots_sold_count }} / {{ record.positions_exited_count }}
          </dd>
        </div>
        <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
          <dt class="tw:text-xs tw:text-muted-foreground">Orders in recommendation</dt>
          <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">{{ record.orders_count }}</dd>
        </div>
        <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
          <dt class="tw:text-xs tw:text-muted-foreground">Cash before / after</dt>
          <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold tw:tabular-nums">
            {{ formatUsd(record.cash_before_usd) }} / {{ formatUsd(record.cash_after_usd) }}
          </dd>
        </div>
        <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
          <dt class="tw:text-xs tw:text-muted-foreground">Tax estimate status</dt>
          <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">
            {{ record.estimated_tax_benefit_status }}
          </dd>
        </div>
      </dl>
      <section
        v-if="record || context"
        class="frozen-context overview-context tw:min-w-0 tw:rounded-lg tw:border tw:border-border tw:p-3"
        aria-label="Overview frozen run context"
      >
        <h3 class="tw:m-0! tw:text-base tw:font-semibold">Frozen run policy context</h3>
        <template v-if="context?.available">
          <p class="tw:mb-0 tw:mt-2 tw:text-sm tw:text-muted-foreground">
            {{ view === 'saved' ? 'Historical saved run' : 'Run policy snapshot' }} · revision
            {{ context.policy_revision_id }} · {{ context.source ?? 'Unavailable source' }}
          </p>
          <p class="tw:mb-0 tw:mt-2 tw:text-sm" v-if="context.sleeves === null">
            Frozen sleeve labels and targets: Unavailable
          </p>
          <ul class="tw:mb-0 tw:mt-2 tw:list-disc tw:pl-5 tw:text-sm" v-else>
            <li v-for="sleeve in context.sleeves" :key="sleeve.sleeve_key">
              {{ sleeve.display_name }} · target {{ formatPercent(sleeve.target_pct) }}
            </li>
          </ul>
          <details class="tw:mt-2 tw:min-w-0 tw:rounded-md tw:border tw:border-border">
            <summary
              class="tw:cursor-pointer tw:px-3 tw:py-2 tw:font-medium tw:focus-visible:rounded-sm tw:focus-visible:outline-none tw:focus-visible:ring-2 tw:focus-visible:ring-ring"
            >
              Frozen policy assumptions and allowed securities
            </summary>
            <div class="tw:space-y-2 tw:border-t tw:border-border tw:p-3">
              <pre
                class="tw:m-0 tw:max-h-64 tw:overflow-auto tw:rounded-md tw:bg-muted tw:p-3 tw:text-xs tw:whitespace-pre-wrap tw:break-words"
                >{{ formatJson(context.settings) }}</pre>
              <p class="tw:m-0 tw:break-words tw:text-sm">
                Allowed securities: {{ formatJson(context.allowed_securities) }}
              </p>
              <p class="tw:m-0 tw:break-words tw:text-sm">
                Overrides: {{ formatJson(context.overrides) }}
              </p>
            </div>
          </details>
        </template>
        <p class="tw:mb-0 tw:mt-2 tw:text-sm" v-else>
          Unavailable ({{
            context?.unavailable_reason ?? 'the API returned no frozen run context'
          }}). Active policy data is not used to reconstruct run history.
        </p>
      </section>
    </template>
  </section>

  <Card
    v-else-if="record || pending"
    role="region"
    class="run-summary tw:min-w-0 tw:flex tw:flex-col tw:gap-4 tw:p-4 tw:sm:p-6"
    :aria-labelledby="headingId"
  >
    <h2 v-if="pending" :id="headingId" class="tw:sr-only">Run summary pending</h2>
    <Alert
      v-if="mode === 'review' && provenanceLabel"
      class="provenance-banner tw:min-w-0"
      :variant="view === 'stale' || view === 'unverified' ? 'destructive' : 'default'"
      :data-view="view ?? 'unknown'"
      role="status"
      aria-live="polite"
    >
      <AlertTitle class="tw:text-current">{{ provenanceLabel }}</AlertTitle>
      <AlertDescription class="tw:flex tw:flex-wrap tw:gap-x-4 tw:gap-y-1 tw:text-current">
        <span>Run {{ record?.run_id ?? 'Unavailable' }}</span>
        <span>Policy {{ record?.policy_revision_id ?? 'Unavailable' }}</span>
        <span>Source generation {{ record?.source_generation ?? 'Unavailable' }}</span>
        <span>As of {{ record?.as_of ?? 'Unavailable' }}</span>
        <span>Proposed trade date {{ record?.proposed_trade_date ?? 'Unavailable' }}</span>
      </AlertDescription>
    </Alert>

    <Alert v-if="pending" role="status" aria-live="polite">
      The requested selection or annotation is being saved or re-solved. Previous basket effects are
      withheld until the API responds; no unconfirmed selection is shown as active.
    </Alert>
    <template v-else-if="record">
      <div
        class="run-title-row tw:flex tw:min-w-0 tw:flex-wrap tw:items-center tw:justify-between tw:gap-4"
      >
        <div class="tw:min-w-0">
          <h2 class="tw:m-0! tw:text-lg tw:font-semibold tw:tracking-tight" :id="headingId">
            <template v-if="mode === 'saved'">Saved run summary and frozen settings</template>
            <template v-else
              >{{ record.solver_version }} recommendations · {{ record.status }}</template
            >
          </h2>
          <p class="tw:mb-0 tw:mt-2 tw:text-sm tw:text-muted-foreground" v-if="mode === 'review'">
            {{ record.demo ? 'DEMO hypothetical data' : 'API run' }} ·
            {{
              record.actionable
                ? 'API marks this run actionable'
                : 'API marks this run non-actionable'
            }}
          </p>
          <p
            v-if="mode === 'review'"
            class="review-capability-note tw:mb-0 tw:mt-2 tw:text-sm tw:text-muted-foreground"
          >
            No order preview, approval, or submission controls are available.
          </p>
          <p
            class="tw:mb-0 tw:mt-2 tw:text-sm tw:text-muted-foreground"
            v-else-if="mode === 'saved'"
          >
            Historical API summary only. Missing assumptions are not reconstructed from current
            policy.
          </p>
        </div>
        <Badge
          variant="secondary"
          class="tw:h-auto tw:whitespace-normal tw:px-2 tw:py-1"
          role="status"
        >
          {{
            record.demo
              ? 'DEMO · non-actionable'
              : record.actionable
                ? 'API-marked actionable · no order controls'
                : 'NON-ACTIONABLE'
          }}
        </Badge>
      </div>

      <Alert
        v-if="mode === 'review' && record.solver_version === 'DEMO'"
        variant="default"
        role="group"
        aria-label="DEMO solver output notice"
      >
        <AlertTitle class="tw:text-current">DEMO solver output notice</AlertTitle>
        <AlertDescription class="tw:text-current">
          DEMO solver output is not a real optimizer feasibility result. Treat every value as
          hypothetical and non-executable.
        </AlertDescription>
      </Alert>
      <Alert
        v-if="mode === 'review' && record.estimated_tax_benefit_status === 'optimizer_unavailable'"
        variant="destructive"
        role="group"
        aria-label="Tax estimate availability notice"
      >
        <AlertTitle class="tw:text-current">Tax estimate availability notice</AlertTitle>
        <AlertDescription class="tw:text-current">
          The real optimizer is unavailable. No production optimization or feasibility claim is
          made.
        </AlertDescription>
      </Alert>

      <dl
        class="run-metrics tw:m-0 tw:grid tw:grid-cols-1 tw:gap-2 tw:sm:grid-cols-2 tw:xl:grid-cols-3"
        :class="mode === 'saved' ? 'saved-metrics' : 'metric-grid'"
      >
        <template v-if="mode === 'saved'">
          <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
            <dt class="tw:text-xs tw:text-muted-foreground">Run ID</dt>
            <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">{{ record.run_id }}</dd>
          </div>
          <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
            <dt class="tw:text-xs tw:text-muted-foreground">Status / mode</dt>
            <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">
              {{ record.status }} · {{ record.mode }}
            </dd>
          </div>
          <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
            <dt class="tw:text-xs tw:text-muted-foreground">Policy revision</dt>
            <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">
              {{ record.policy_revision_id }}
            </dd>
          </div>
          <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
            <dt class="tw:text-xs tw:text-muted-foreground">Source generation</dt>
            <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">
              {{ record.source_generation }}
            </dd>
          </div>
          <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
            <dt class="tw:text-xs tw:text-muted-foreground">As of</dt>
            <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">{{ record.as_of }}</dd>
          </div>
          <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
            <dt class="tw:text-xs tw:text-muted-foreground">Proposed trade date</dt>
            <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">
              {{ record.proposed_trade_date ?? 'Unavailable' }}
            </dd>
          </div>
          <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
            <dt class="tw:text-xs tw:text-muted-foreground">Solver</dt>
            <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">
              {{ record.solver_version }}
            </dd>
          </div>
          <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
            <dt class="tw:text-xs tw:text-muted-foreground">Tax profile configured</dt>
            <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">
              {{ record.tax_profile_configured ? 'Yes' : 'No' }}
            </dd>
          </div>
          <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
            <dt class="tw:text-xs tw:text-muted-foreground">Tax estimate status</dt>
            <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">
              {{ record.estimated_tax_benefit_status }}
            </dd>
          </div>
        </template>
        <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
          <dt class="tw:text-xs tw:text-muted-foreground">Estimated realized ST</dt>
          <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold tw:tabular-nums">
            {{ money(record.estimated_realized_st_usd) }}
          </dd>
        </div>
        <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
          <dt class="tw:text-xs tw:text-muted-foreground">Estimated realized LT</dt>
          <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold tw:tabular-nums">
            {{ money(record.estimated_realized_lt_usd) }}
          </dd>
        </div>
        <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
          <dt class="tw:text-xs tw:text-muted-foreground">Estimated tax benefit</dt>
          <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold tw:tabular-nums">
            {{ money(record.estimated_tax_benefit_usd) }}
          </dd>
        </div>
        <div
          class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3"
          v-if="mode === 'review'"
        >
          <dt class="tw:text-xs tw:text-muted-foreground">Tax estimate status</dt>
          <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">
            {{ record.estimated_tax_benefit_status }}
          </dd>
        </div>
        <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
          <dt class="tw:text-xs tw:text-muted-foreground">Cash before / after</dt>
          <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold tw:tabular-nums">
            {{ money(record.cash_before_usd) }} / {{ money(record.cash_after_usd) }}
          </dd>
        </div>
        <template v-if="mode === 'review'">
          <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
            <dt class="tw:text-xs tw:text-muted-foreground">Risk tracking</dt>
            <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">
              Unavailable (not returned by API)
            </dd>
            <small class="tw:mt-1 tw:block tw:text-xs tw:text-muted-foreground">
              Not returned as a run-level risk score
            </small>
          </div>
          <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
            <dt class="tw:text-xs tw:text-muted-foreground">Hard constraints</dt>
            <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">
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
        <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
          <dt class="tw:text-xs tw:text-muted-foreground">
            API-reported sell lots / exited positions / orders
          </dt>
          <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">
            {{ record.lots_sold_count }} / {{ record.positions_exited_count }} /
            {{ record.orders_count }}
          </dd>
        </div>
        <div class="tw:min-w-0 tw:rounded-md tw:border tw:border-border tw:p-3">
          <dt class="tw:text-xs tw:text-muted-foreground">Tax profile</dt>
          <dd class="tw:m-0 tw:mt-1 tw:break-words tw:font-semibold">
            {{ record.tax_profile_configured ? 'Configured' : 'Incomplete' }}
          </dd>
        </div>
      </dl>

      <template v-if="mode === 'review'">
        <p
          v-if="record.no_trade_reason != null"
          class="no-trade-reason tw:m-0 tw:break-words tw:rounded-md tw:border tw:border-border tw:p-3 tw:text-sm"
        >
          <strong>No beneficial trades identified / API no-trade reason:</strong>
          {{ formatJson(record.no_trade_reason) }}
        </p>
        <p
          v-else-if="groupCount === 0"
          class="no-trade-reason tw:m-0 tw:rounded-md tw:border tw:border-border tw:p-3 tw:text-sm"
        >
          No beneficial trades identified. The API returned no recommendation groups.
        </p>
      </template>

      <h3 class="tw:m-0! tw:text-base tw:font-semibold" v-if="mode === 'saved'">
        Batch settings returned by the API
      </h3>
      <h3 class="tw:m-0! tw:text-base tw:font-semibold" v-else-if="mode === 'review'">
        Frozen API batch settings and provenance
      </h3>
      <pre
        class="tw:m-0 tw:max-h-64 tw:overflow-auto tw:rounded-md tw:bg-muted tw:p-3 tw:text-xs tw:whitespace-pre-wrap tw:break-words"
        >{{ formatJson(record.batch_settings) }}</pre>
      <section
        class="frozen-context tw:min-w-0 tw:rounded-lg tw:border tw:border-border tw:p-3"
        aria-label="Frozen run display context"
      >
        <h3 class="tw:m-0! tw:text-base tw:font-semibold">Frozen policy display context</h3>
        <template v-if="context?.available">
          <p class="tw:mb-0 tw:mt-2 tw:text-sm tw:text-muted-foreground">
            Policy revision {{ context.policy_revision_id }} ·
            {{ context.source ?? 'Unavailable source' }}
          </p>
          <p class="tw:mb-0 tw:mt-2 tw:text-sm" v-if="context.sleeves === null">
            Frozen sleeve labels and targets: Unavailable
          </p>
          <ul class="tw:mb-0 tw:mt-2 tw:list-disc tw:pl-5 tw:text-sm" v-else>
            <li v-for="sleeve in context.sleeves" :key="sleeve.sleeve_key">
              {{ sleeve.display_name }} · target {{ formatPercent(sleeve.target_pct) }}
            </li>
          </ul>
          <h4 class="tw:mb-0! tw:mt-3! tw:text-sm tw:font-semibold">Frozen policy assumptions</h4>
          <pre
            class="tw:mb-0 tw:mt-2 tw:max-h-64 tw:overflow-auto tw:rounded-md tw:bg-muted tw:p-3 tw:text-xs tw:whitespace-pre-wrap tw:break-words"
            >{{ formatJson(context.settings ?? 'Unavailable') }}</pre>
          <p class="tw:mb-0 tw:mt-2 tw:break-words tw:text-sm">
            Allowed securities: {{ formatJson(context.allowed_securities ?? 'Unavailable') }}
          </p>
          <p class="tw:mb-0 tw:mt-2 tw:break-words tw:text-sm">
            Overrides: {{ formatJson(context.overrides ?? 'Unavailable') }}
          </p>
        </template>
        <p class="tw:mb-0 tw:mt-2 tw:text-sm" v-else>
          Unavailable ({{
            context?.unavailable_reason ?? 'the API returned no frozen run context'
          }}). Active policy data is not used to reconstruct this historical run.
        </p>
      </section>

      <p class="provenance-note tw:m-0 tw:break-words tw:text-sm tw:text-muted-foreground">
        Provenance — input fingerprint: {{ record.input_fingerprint ?? 'Unavailable' }} · source
        checksum: {{ record.source_checksum ?? 'Unavailable' }}
      </p>
      <p v-if="mode === 'review' && summary" class="tw:m-0 tw:text-sm tw:text-muted-foreground">
        Saved summary status: {{ summary.status }} · {{ summary.mode }}
      </p>
      <ul
        v-if="record.warnings.length"
        class="warning-list tw:m-0 tw:list-disc tw:pl-5 tw:text-sm tw:text-destructive"
        aria-label="Run warnings"
      >
        <li v-for="warning in record.warnings" :key="warning">{{ warning }}</li>
      </ul>
    </template>
  </Card>
</template>

<script setup lang="ts">
import { computed, useId } from 'vue';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
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
.run-summary h2 {
  font-size: var(--tw-text-lg);
  line-height: var(--tw-text-lg--line-height);
  font-weight: var(--tw-font-weight-semibold);
  letter-spacing: var(--tw-tracking-tight);
}

.run-summary h3,
.overview-run-summary h3 {
  font-size: var(--tw-text-base);
  line-height: var(--tw-text-base--line-height);
  font-weight: var(--tw-font-weight-semibold);
}

.run-summary h4 {
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
  font-weight: var(--tw-font-weight-semibold);
}
</style>
