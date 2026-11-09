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
    <WorkspaceTableFrame
      class="lot-table-wrap"
      :label="`SELL broker-lot attribution for leg ${leg.leg_id}`"
    >
      <table>
        <caption class="q-py-sm">
          SELL broker-lot attribution from the API ·
          {{
            leg.ticker ?? 'ticker unavailable'
          }}
        </caption>
        <thead>
          <tr>
            <th class="q-pa-sm" scope="col">Review selection</th>
            <th class="q-pa-sm" scope="col">Broker lot ID</th>
            <th class="q-pa-sm" scope="col">Acquired</th>
            <th class="q-pa-sm" scope="col">API proposed sale shares</th>
            <th class="q-pa-sm" scope="col">Adjusted basis (API value)</th>
            <th class="q-pa-sm" scope="col">Estimated price</th>
            <th class="q-pa-sm" scope="col">Term</th>
            <th class="q-pa-sm" scope="col">Realized P/L</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="lot in leg.selected_lots" :key="lot.broker_lot_id">
            <td class="q-pa-sm">
              <q-checkbox
                class="lot-selection"
                dense
                color="primary"
                :model-value="lot.selected"
                :disable="pending || !canChangeSelection || rejected"
                :aria-label="`Select SELL lot ${lot.broker_lot_id} in group ${groupId}`"
                :label="lot.selected ? 'API selected' : 'Not selected'"
                @update:model-value="changeLotSelection(lot.broker_lot_id, $event)"
              />
            </td>
            <th class="q-pa-sm" scope="row">
              <BrokerLotIdentity :broker-lot-id="lot.broker_lot_id" />
            </th>
            <td class="q-pa-sm">{{ lot.acquired_date }}</td>
            <td class="q-pa-sm">{{ lot.shares }}</td>
            <td class="q-pa-sm">{{ formatUsd(lot.adjusted_basis_usd) }}</td>
            <td class="q-pa-sm">{{ formatUsd(leg.estimated_unit_price_usd) }}</td>
            <td class="q-pa-sm">{{ lot.st_lt }}</td>
            <td class="q-pa-sm">{{ formatUsd(lot.realized_pl_usd) }}</td>
          </tr>
          <tr v-if="leg.selected_lots.length === 0">
            <td class="q-pa-sm" colspan="8">No broker-lot rows were returned for this SELL leg.</td>
          </tr>
        </tbody>
      </table>
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

.lot-table-wrap {
  max-width: 100%;
  min-width: 0;
  overflow-x: auto;
}

:deep(table) {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}

:deep(caption) {
  color: #526c7c;
  font-size: 0.74rem;
  font-weight: 700;
  text-align: left;
}

:deep(th),
:deep(td) {
  border-bottom: 1px solid #eaf0f3;
  color: #35586c;
  font-size: 0.73rem;
  white-space: nowrap;
}

:deep(thead th) {
  background: #f3f8fa;
  color: #627b8b;
  font-size: 0.68rem;
  text-transform: uppercase;
}

.lot-selection {
  color: #526c7c;
  font-size: 0.76rem;
  font-weight: 650;
}
</style>
