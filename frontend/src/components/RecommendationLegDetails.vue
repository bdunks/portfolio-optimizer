<template>
  <q-card tag="article" :id="id" class="leg-card q-pa-md" :aria-labelledby="headingId">
    <h3 class="q-ma-none text-subtitle1" :id="headingId">
      Sequence {{ leg.sequence }} · {{ leg.side }} {{ leg.ticker ?? 'ticker unavailable' }}
    </h3>
    <dl class="leg-facts q-mt-md q-mb-sm q-mx-none text-caption text-blue-grey-10 text-weight-bold">
      <div class="q-pa-sm">
        <dt>Leg ID</dt>
        <dd class="q-mt-xs q-mb-none q-mx-none">{{ leg.leg_id }}</dd>
      </div>
      <div class="q-pa-sm">
        <dt>API-proposed whole shares</dt>
        <dd class="q-mt-xs q-mb-none q-mx-none">{{ leg.shares }}</dd>
      </div>
      <div class="q-pa-sm">
        <dt>Estimated unit price</dt>
        <dd class="q-mt-xs q-mb-none q-mx-none">{{ formatUsd(leg.estimated_unit_price_usd) }}</dd>
      </div>
      <div class="q-pa-sm">
        <dt>Estimated notional</dt>
        <dd class="q-mt-xs q-mb-none q-mx-none">{{ formatUsd(leg.estimated_notional_usd) }}</dd>
      </div>
      <div class="q-pa-sm">
        <dt>Net realized ST / LT</dt>
        <dd class="q-mt-xs q-mb-none q-mx-none">
          {{ formatUsd(leg.net_st_realized_usd) }} / {{ formatUsd(leg.net_lt_realized_usd) }}
        </dd>
      </div>
    </dl>
    <p class="dependency-note q-mt-sm q-mb-none q-mx-none">
      {{
        leg.dependencies.length
          ? `Requires API leg(s): ${leg.dependencies.join(', ')}`
          : 'No leg dependency was returned by the API.'
      }}
    </p>
    <p class="leg-status q-mt-sm q-mb-none q-mx-none">
      {{ leg.selected ? 'Selected in this API basket' : 'Not selected in this API basket' }}
    </p>
  </q-card>
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
/* Grid gaps use Quasar's spacing scale; negative-margin gutters distort grid tracks. */
.leg-card {
  min-width: 0;
  /* Anchor navigation needs scroll clearance; Quasar margin utilities do not affect scrolling. */
  scroll-margin-top: 16px;
}

.leg-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px;
}

.leg-facts > div {
  min-width: 0;
  border: 1px solid #eaf0f3;
  border-radius: 0.55rem;
}

.leg-facts dt {
  color: #647c8b;
  font-size: 0.7rem;
}

.leg-facts dd {
  overflow-wrap: anywhere;
}

.dependency-note,
.leg-status {
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
