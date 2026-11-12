<template>
  <article :id="id" class="leg-card" tabindex="-1" :aria-labelledby="headingId">
    <Card class="leg-shell">
      <CardHeader>
        <CardTitle>
          <h3 :id="headingId" class="leg-heading tw:m-0!">
            Sequence {{ leg.sequence }} · {{ leg.side }} {{ leg.ticker ?? 'ticker unavailable' }}
          </h3>
        </CardTitle>
      </CardHeader>
      <CardContent class="leg-content">
        <dl class="leg-facts tw:m-0! tw:gap-2">
          <div class="tw:p-3">
            <dt>Leg ID</dt>
            <dd class="fact-value tw:m-0!">{{ leg.leg_id }}</dd>
          </div>
          <div class="tw:p-3">
            <dt>API-proposed whole shares</dt>
            <dd class="fact-value tw:m-0!">{{ leg.shares }}</dd>
          </div>
          <div class="tw:p-3">
            <dt>Estimated unit price</dt>
            <dd class="fact-value tw:m-0!">{{ formatUsd(leg.estimated_unit_price_usd) }}</dd>
          </div>
          <div class="tw:p-3">
            <dt>Estimated notional</dt>
            <dd class="fact-value tw:m-0!">{{ formatUsd(leg.estimated_notional_usd) }}</dd>
          </div>
          <div class="tw:p-3">
            <dt>Net realized ST / LT</dt>
            <dd class="fact-value tw:m-0!">
              {{ formatUsd(leg.net_st_realized_usd) }} / {{ formatUsd(leg.net_lt_realized_usd) }}
            </dd>
          </div>
        </dl>
        <div class="leg-notes tw:mt-4 tw:gap-2">
          <p class="dependency-note tw:m-0!">
            {{
              leg.dependencies.length
                ? `Requires API leg(s): ${leg.dependencies.join(', ')}`
                : 'No leg dependency was returned by the API.'
            }}
          </p>
          <p class="leg-status tw:m-0!">
            {{ leg.selected ? 'Selected in this API basket' : 'Not selected in this API basket' }}
          </p>
        </div>
      </CardContent>
    </Card>
  </article>
</template>

<script setup lang="ts">
import { useId } from 'vue';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatUsd } from '@/utils/display-values';
import type { RecommendationLegResponse } from '@/types/api';

defineProps<{
  leg: RecommendationLegResponse;
  id?: string;
}>();

const headingId = `recommendation-leg-${useId()}`;
</script>

<style scoped>
.leg-card {
  min-width: 0;
  scroll-margin-top: 1rem;
}

.leg-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 11.25rem), 1fr));
}

.leg-facts > div {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.leg-facts dt {
  color: var(--muted-foreground);
  font-size: var(--tw-text-xs);
  line-height: var(--tw-text-xs--line-height);
  font-weight: var(--tw-font-weight-medium);
}

.leg-facts dd {
  color: var(--foreground);
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}

:global(.leg-card h3) {
  display: block;
  color: var(--foreground);
  font-family: inherit;
  font-size: var(--tw-text-base) !important;
  font-weight: var(--tw-font-weight-semibold) !important;
  line-height: var(--tw-text-base--line-height) !important;
}

:global(.leg-card p) {
  font-size: var(--tw-text-sm) !important;
  line-height: var(--tw-text-sm--line-height) !important;
}

.leg-notes {
  display: grid;
}

.dependency-note,
.leg-status {
  color: var(--muted-foreground);
}

.leg-status {
  font-size: var(--tw-text-xs) !important;
  line-height: var(--tw-text-xs--line-height) !important;
}
</style>
