<script setup lang="ts">
import { omitUndefinedProps } from '@/components/ui/props';
import type { DropdownMenuSubEmits, DropdownMenuSubProps } from 'reka-ui';
import { DropdownMenuSub, useForwardPropsEmits } from 'reka-ui';

const props = defineProps<DropdownMenuSubProps>();
const emits = defineEmits<DropdownMenuSubEmits>();

const forwarded = useForwardPropsEmits(props, emits);
</script>

<template>
  <DropdownMenuSub
    #default="slotProps"
    data-slot="dropdown-menu-sub"
    v-bind="omitUndefinedProps(forwarded)"
  >
    <slot v-bind="slotProps" />
  </DropdownMenuSub>
</template>
