<script setup lang="ts">
import type { TooltipRootEmits, TooltipRootProps } from 'reka-ui';
import { TooltipRoot, useForwardPropsEmits } from 'reka-ui';
import { omitUndefinedProps } from '@/components/ui/props';

const props = defineProps<TooltipRootProps>();
const emits = defineEmits<TooltipRootEmits>();

const forwarded = useForwardPropsEmits(props, emits);
</script>

<template>
  <TooltipRoot #default="slotProps" data-slot="tooltip" v-bind="omitUndefinedProps(forwarded)">
    <slot v-bind="slotProps" />
  </TooltipRoot>
</template>
