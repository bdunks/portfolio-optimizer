<script setup lang="ts">
import type { EditableSectorBand } from '@/pages/policy-form';

const props = defineProps<{ sectorBands: EditableSectorBand[] }>();
const emit = defineEmits<{ 'update:sectorBands': [value: EditableSectorBand[]] }>();

function update(index: number, key: keyof EditableSectorBand, value: string): void {
  emit(
    'update:sectorBands',
    props.sectorBands.map((row, rowIndex) =>
      rowIndex === index ? { ...row, [key]: value } : row,
    ),
  );
}

function add(): void {
  emit('update:sectorBands', [
    ...props.sectorBands,
    { sector_key: '', target_weight_pct: '', band_pct: '' },
  ]);
}

function remove(index: number): void {
  emit('update:sectorBands', props.sectorBands.filter((_, rowIndex) => rowIndex !== index));
}
</script>

<template>
  <section class="space-y-3 rounded-lg border p-4" aria-labelledby="sector-band-heading">
    <div>
      <h2 id="sector-band-heading" class="text-base font-semibold">Sector drift bands</h2>
      <p class="text-sm text-muted-foreground">
        Targets total exactly 100% of invested look-through security exposure. Cash is excluded; these
        are configurable policy values, not live sector measurements.
      </p>
    </div>
    <div v-for="(row, index) in sectorBands" :key="index" class="grid gap-2 sm:grid-cols-4">
      <label class="space-y-1 text-sm">
        <span>Sector key</span>
        <input :value="row.sector_key" class="w-full rounded border px-2 py-1" @input="update(index, 'sector_key', ($event.target as HTMLInputElement).value)" />
      </label>
      <label class="space-y-1 text-sm">
        <span>Target weight (%)</span>
        <input :value="row.target_weight_pct" inputmode="decimal" class="w-full rounded border px-2 py-1" @input="update(index, 'target_weight_pct', ($event.target as HTMLInputElement).value)" />
      </label>
      <label class="space-y-1 text-sm">
        <span>Band (percentage points)</span>
        <input :value="row.band_pct" inputmode="decimal" class="w-full rounded border px-2 py-1" @input="update(index, 'band_pct', ($event.target as HTMLInputElement).value)" />
      </label>
      <button type="button" class="self-end rounded border px-3 py-1 text-sm" @click="remove(index)">Remove</button>
    </div>
    <button type="button" class="rounded border px-3 py-1 text-sm" @click="add">Add sector band</button>
  </section>
</template>
