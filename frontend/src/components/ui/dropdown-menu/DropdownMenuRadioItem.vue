<script setup lang="ts">
import { omitUndefinedProps } from '@/components/ui/props';
import type { DropdownMenuRadioItemEmits, DropdownMenuRadioItemProps } from 'reka-ui';

import type { HTMLAttributes } from 'vue';
import { CheckIcon } from '@lucide/vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { DropdownMenuItemIndicator, DropdownMenuRadioItem, useForwardPropsEmits } from 'reka-ui';

const props = defineProps<DropdownMenuRadioItemProps & { class?: HTMLAttributes['class'] }>();

const emits = defineEmits<DropdownMenuRadioItemEmits>();

const delegatedProps = reactiveOmit(props, 'class', 'value');

const forwarded = useForwardPropsEmits(delegatedProps, emits);
</script>

<template>
  <DropdownMenuRadioItem
    data-slot="dropdown-menu-radio-item"
    :value="props.value"
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
      data-slot="dropdown-menu-radio-item-indicator"
    >
      <DropdownMenuItemIndicator>
        <slot name="indicator-icon">
          <CheckIcon />
        </slot>
      </DropdownMenuItemIndicator>
    </span>
    <slot />
  </DropdownMenuRadioItem>
</template>
