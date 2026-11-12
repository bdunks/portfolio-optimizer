<script setup lang="ts">
import type { SelectRootEmits, SelectRootProps } from 'reka-ui';
import { SelectRoot, useForwardPropsEmits } from 'reka-ui';
import { omitUndefinedProps } from '@/components/ui/props';

const props = defineProps<SelectRootProps>();
const emits = defineEmits<SelectRootEmits>();

const forwarded = useForwardPropsEmits(props, emits);
</script>

<template>
  <SelectRoot #default="slotProps" data-slot="select" v-bind="omitUndefinedProps(forwarded)">
    <slot v-bind="slotProps" />
  </SelectRoot>
</template>
