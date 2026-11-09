<template>
  <article :id="id" class="leg-card" :aria-labelledby="headingId">
    <h3 :id="headingId">
      Sequence {{ leg.sequence }} · {{ leg.side }} {{ leg.ticker ?? 'ticker unavailable' }}
    </h3>
    <dl class="leg-facts">
      <div>
        <dt>Leg ID</dt>
        <dd>{{ leg.leg_id }}</dd>
      </div>
      <div>
        <dt>API-proposed whole shares</dt>
        <dd>{{ leg.shares }}</dd>
      </div>
      <div>
        <dt>Estimated unit price</dt>
        <dd>{{ formatUsd(leg.estimated_unit_price_usd) }}</dd>
      </div>
      <div>
        <dt>Estimated notional</dt>
        <dd>{{ formatUsd(leg.estimated_notional_usd) }}</dd>
      </div>
      <div>
        <dt>Net realized ST / LT</dt>
        <dd>{{ formatUsd(leg.net_st_realized_usd) }} / {{ formatUsd(leg.net_lt_realized_usd) }}</dd>
      </div>
    </dl>
    <p class="dependency-note">
      {{
        leg.dependencies.length
          ? `Requires API leg(s): ${leg.dependencies.join(', ')}`
          : 'No leg dependency was returned by the API.'
      }}
    </p>
    <p class="leg-status">
      {{ leg.selected ? 'Selected in this API basket' : 'Not selected in this API basket' }}
    </p>
  </article>
</template>

<script setup lang="ts">
import { useId } from 'vue';
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
  padding: 0.8rem;
  border: 1px solid #eaf0f3;
  border-radius: 0.6rem;
  background: #fbfdfe;
  scroll-margin-top: 1rem;
}

.leg-card h3 {
  margin: 0;
  color: #29475a;
  font-size: 0.9rem;
}

.leg-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.6rem;
  margin: 0.8rem 0 0.5rem;
}

.leg-facts > div {
  min-width: 0;
  padding: 0.65rem;
  border: 1px solid #eaf0f3;
  border-radius: 0.55rem;
}

.leg-facts dt {
  color: #647c8b;
  font-size: 0.7rem;
}

.leg-facts dd {
  margin: 0.25rem 0 0;
  color: #29475a;
  font-size: 0.78rem;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.dependency-note,
.leg-status {
  margin: 0.4rem 0 0;
  color: #526c7c;
  font-size: 0.78rem;
  line-height: 1.5;
}

.leg-status {
  color: #657d8b;
  font-size: 0.73rem;
}

@media (max-width: 760px) {
  .leg-facts {
    grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
  }
}
</style>
