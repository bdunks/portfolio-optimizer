<script setup lang="ts">
import { omitUndefinedProps } from '@/components/ui/props';
import type { DropdownMenuRootEmits, DropdownMenuRootProps } from 'reka-ui';
import { DropdownMenuRoot, useForwardPropsEmits } from 'reka-ui';

const props = defineProps<DropdownMenuRootProps>();
const emits = defineEmits<DropdownMenuRootEmits>();

const forwarded = useForwardPropsEmits(props, emits);
</script>

<template>
  <DropdownMenuRoot
    #default="slotProps"
    data-slot="dropdown-menu"
    v-bind="omitUndefinedProps(forwarded)"
  >
    <slot v-bind="slotProps" />
  </DropdownMenuRoot>
</template>
