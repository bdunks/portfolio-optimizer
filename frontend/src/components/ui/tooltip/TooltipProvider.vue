<script setup lang="ts">
import type { TooltipProviderProps } from 'reka-ui';
import { TooltipProvider } from 'reka-ui';
import { omitUndefinedProps } from '@/components/ui/props';

const props = withDefaults(defineProps<TooltipProviderProps>(), {
  delayDuration: 0,
});
</script>

<template>
  <TooltipProvider v-bind="omitUndefinedProps(props)">
    <slot />
  </TooltipProvider>
</template>
