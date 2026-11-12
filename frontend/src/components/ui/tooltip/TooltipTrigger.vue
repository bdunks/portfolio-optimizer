<script setup lang="ts">
import type { TooltipTriggerProps } from 'reka-ui';
import { TooltipTrigger } from 'reka-ui';
import { omitUndefinedProps } from '@/components/ui/props';

const props = defineProps<TooltipTriggerProps>();
</script>

<template>
  <TooltipTrigger data-slot="tooltip-trigger" v-bind="omitUndefinedProps(props)">
    <slot />
  </TooltipTrigger>
</template>
