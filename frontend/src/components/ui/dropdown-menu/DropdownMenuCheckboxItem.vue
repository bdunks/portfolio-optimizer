<script setup lang="ts">
import { omitUndefinedProps } from '@/components/ui/props';
import type { DropdownMenuCheckboxItemEmits, DropdownMenuCheckboxItemProps } from 'reka-ui';

import type { HTMLAttributes } from 'vue';
import { CheckIcon } from '@lucide/vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { DropdownMenuCheckboxItem, DropdownMenuItemIndicator, useForwardPropsEmits } from 'reka-ui';

const props = defineProps<DropdownMenuCheckboxItemProps & { class?: HTMLAttributes['class'] }>();
const emits = defineEmits<DropdownMenuCheckboxItemEmits>();

const delegatedProps = reactiveOmit(props, 'class');

const forwarded = useForwardPropsEmits(delegatedProps, emits);
</script>

<template>
  <DropdownMenuCheckboxItem
    data-slot="dropdown-menu-checkbox-item"
    v-bind="omitUndefinedProps(forwarded)"
    :class="
      cn(
        'tw:focus:bg-accent tw:focus:text-accent-foreground tw:focus:**:text-accent-foreground tw:gap-1.5 tw:rounded-md tw:py-1 tw:pr-8 tw:pl-1.5 tw:text-sm tw:data-inset:pl-7 tw:[&_svg:not([class*=size-])]:size-4 tw:relative tw:flex tw:cursor-default tw:items-center tw:outline-hidden tw:select-none tw:data-disabled:pointer-events-none tw:data-disabled:opacity-50 tw:[&_svg]:pointer-events-none tw:[&_svg]:shrink-0',
        props.class,
      )
    "
  >
    <span
      class="tw:absolute tw:right-2 tw:flex tw:items-center tw:justify-center tw:pointer-events-none"
      data-slot="dropdown-menu-checkbox-item-indicator"
    >
      <DropdownMenuItemIndicator>
        <slot name="indicator-icon">
          <CheckIcon />
        </slot>
      </DropdownMenuItemIndicator>
    </span>
    <slot />
  </DropdownMenuCheckboxItem>
</template>
