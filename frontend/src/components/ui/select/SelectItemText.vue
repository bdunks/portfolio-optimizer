<script setup lang="ts">
import type { SelectItemTextProps } from 'reka-ui';
import { SelectItemText } from 'reka-ui';
import { omitUndefinedProps } from '@/components/ui/props';

const props = defineProps<SelectItemTextProps>();
</script>

<template>
  <SelectItemText data-slot="select-item-text" v-bind="omitUndefinedProps(props)">
    <slot />
  </SelectItemText>
</template>
