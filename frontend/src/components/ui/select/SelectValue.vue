<script setup lang="ts">
import type { SelectValueProps } from 'reka-ui';
import { SelectValue } from 'reka-ui';
import { omitUndefinedProps } from '@/components/ui/props';

const props = defineProps<SelectValueProps>();
</script>

<template>
  <SelectValue data-slot="select-value" v-bind="omitUndefinedProps(props)">
    <slot />
  </SelectValue>
</template>
