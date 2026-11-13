<script setup lang="ts">
import { omitUndefinedProps } from '@/components/ui/props';
import type { DropdownMenuGroupProps } from 'reka-ui';
import { DropdownMenuGroup } from 'reka-ui';

const props = defineProps<DropdownMenuGroupProps>();
</script>

<template>
  <DropdownMenuGroup data-slot="dropdown-menu-group" v-bind="omitUndefinedProps(props)">
    <slot />
  </DropdownMenuGroup>
</template>
