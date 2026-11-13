<script setup lang="ts">
import { omitUndefinedProps } from '@/components/ui/props';
import type { DropdownMenuTriggerProps } from 'reka-ui';
import { DropdownMenuTrigger, useForwardProps } from 'reka-ui';

const props = defineProps<DropdownMenuTriggerProps>();

const forwardedProps = useForwardProps(props);
</script>

<template>
  <DropdownMenuTrigger
    data-slot="dropdown-menu-trigger"
    v-bind="omitUndefinedProps(forwardedProps)"
  >
    <slot />
  </DropdownMenuTrigger>
</template>
