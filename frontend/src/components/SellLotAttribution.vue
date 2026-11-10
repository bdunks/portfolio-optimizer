<template>
  <section
    v-if="leg.side === 'SELL'"
    class="sell-lot-attribution"
    aria-label="SELL lot attribution"
  >
    <p class="quantity-note q-mt-none q-mb-sm q-mx-none">
      These are API-proposed whole-share sale quantities for this run, not current remaining or
      available inventory. Inventory quantities are shown separately on Tax Lots.
    </p>
    <WorkspaceTableFrame :label="`SELL broker-lot attribution for leg ${leg.leg_id}`">
      <q-markup-table>
        <caption class="q-py-sm">
          SELL broker-lot attribution from the API ·
          {{
            leg.ticker ?? 'ticker unavailable'
          }}
        </caption>
        <thead>
          <tr>
            <th scope="col">Review selection</th>
            <th scope="col">Broker lot ID</th>
            <th scope="col">Acquired</th>
            <th scope="col">API proposed sale shares</th>
            <th scope="col">Adjusted basis (API value)</th>
            <th scope="col">Estimated price</th>
            <th scope="col">Term</th>
            <th scope="col">Realized P/L</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="lot in leg.selected_lots" :key="lot.broker_lot_id">
            <td>
              <q-checkbox
                class="text-caption text-weight-bold text-blue-grey-8"
                dense
                color="primary"
                :model-value="lot.selected"
                :disable="pending || !canChangeSelection || rejected"
                :aria-label="`Select SELL lot ${lot.broker_lot_id} in group ${groupId}`"
                :label="lot.selected ? 'API selected' : 'Not selected'"
                @update:model-value="changeLotSelection(lot.broker_lot_id, $event)"
              />
            </td>
            <th scope="row">
              <BrokerLotIdentity :broker-lot-id="lot.broker_lot_id" />
            </th>
            <td>{{ lot.acquired_date }}</td>
            <td>{{ lot.shares }}</td>
            <td>{{ formatUsd(lot.adjusted_basis_usd) }}</td>
            <td>{{ formatUsd(leg.estimated_unit_price_usd) }}</td>
            <td>{{ lot.st_lt }}</td>
            <td>{{ formatUsd(lot.realized_pl_usd) }}</td>
          </tr>
          <tr v-if="leg.selected_lots.length === 0">
            <td colspan="8">No broker-lot rows were returned for this SELL leg.</td>
          </tr>
        </tbody>
      </q-markup-table>
    </WorkspaceTableFrame>
  </section>
</template>

<script setup lang="ts">
import WorkspaceTableFrame from '@/components/WorkspaceTableFrame.vue';
import BrokerLotIdentity from '@/components/BrokerLotIdentity.vue';
import type { LotSelectionIntent } from '@/components/trade-review-types';
import type { RecommendationLegResponse } from '@/types/api';
import { formatUsd } from '@/utils/display-values';

const props = defineProps<{
  leg: RecommendationLegResponse;
  groupId: string;
  canChangeSelection: boolean;
  pending?: boolean;
  rejected?: boolean;
}>();
const emit = defineEmits<{
  lotSelection: [intent: LotSelectionIntent];
}>();

function changeLotSelection(brokerLotId: string, selected: boolean): void {
  emit('lotSelection', { groupId: props.groupId, brokerLotId, selected });
}
</script>

<style scoped>
.quantity-note {
  color: #526c7c;
  font-size: 0.74rem;
  line-height: 1.5;
}

:deep(caption) {
  color: #526c7c;
  font-size: 0.74rem;
  font-weight: 700;
  text-align: left;
}
</style>
