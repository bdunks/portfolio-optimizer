<script setup lang="ts">
import { useId } from 'vue';
import { Button } from '@/components/ui/button';
import { Field, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import type { EditableSectorBand } from '@/pages/policy-form';

const props = defineProps<{ sectorBands: EditableSectorBand[] }>();
const emit = defineEmits<{ 'update:sectorBands': [value: EditableSectorBand[]] }>();
const id = useId();

function update(index: number, key: keyof EditableSectorBand, value: string): void {
  emit(
    'update:sectorBands',
    props.sectorBands.map((row, rowIndex) => (rowIndex === index ? { ...row, [key]: value } : row)),
  );
}

function add(): void {
  emit('update:sectorBands', [
    ...props.sectorBands,
    { sector_key: '', target_weight_pct: '', band_pct: '' },
  ]);
}

function remove(index: number): void {
  emit(
    'update:sectorBands',
    props.sectorBands.filter((_, rowIndex) => rowIndex !== index),
  );
}
</script>

<template>
  <section
    class="tw:space-y-3 tw:rounded-lg tw:border tw:p-4"
    aria-labelledby="sector-band-heading"
  >
    <div>
      <h2 id="sector-band-heading" class="tw:text-base tw:font-semibold">Sector drift bands</h2>
      <p class="tw:text-sm tw:text-muted-foreground">
        Targets total exactly 100% of invested look-through security exposure. Cash is excluded;
        these are configurable policy values, not live sector measurements.
      </p>
    </div>
    <div
      v-for="(row, index) in sectorBands"
      :key="index"
      class="tw:grid tw:gap-2 tw:sm:grid-cols-4"
    >
      <Field>
        <FieldLabel :for="`${id}-${index}-sector`">Sector key</FieldLabel>
        <Input
          :id="`${id}-${index}-sector`"
          :model-value="row.sector_key"
          @update:model-value="update(index, 'sector_key', String($event))"
        />
      </Field>
      <Field>
        <FieldLabel :for="`${id}-${index}-target`">Target weight (%)</FieldLabel>
        <Input
          :id="`${id}-${index}-target`"
          :model-value="row.target_weight_pct"
          inputmode="decimal"
          @update:model-value="update(index, 'target_weight_pct', String($event))"
        />
      </Field>
      <Field>
        <FieldLabel :for="`${id}-${index}-band`">Band (percentage points)</FieldLabel>
        <Input
          :id="`${id}-${index}-band`"
          :model-value="row.band_pct"
          inputmode="decimal"
          @update:model-value="update(index, 'band_pct', String($event))"
        />
      </Field>
      <Button type="button" variant="outline" class="tw:self-end" @click="remove(index)">
        Remove sector band
      </Button>
    </div>
    <Button type="button" variant="outline" @click="add">Add sector band</Button>
  </section>
</template>
