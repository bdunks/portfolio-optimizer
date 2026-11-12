<script setup lang="ts">
import type { SelectTriggerProps } from 'reka-ui';

import type { HTMLAttributes } from 'vue';
import { ChevronDownIcon } from '@lucide/vue';
import { reactiveOmit } from '@vueuse/core';
import { omitUndefinedProps } from '@/components/ui/props';
import { cn } from 'cn';
import { SelectIcon, SelectTrigger, useForwardProps } from 'reka-ui';

const props = withDefaults(
  defineProps<SelectTriggerProps & { class?: HTMLAttributes['class']; size?: 'sm' | 'default' }>(),
  { size: 'default' },
);

const delegatedProps = reactiveOmit(props, 'class', 'size');
const forwardedProps = useForwardProps(delegatedProps);
</script>

<template>
  <SelectTrigger
    data-slot="select-trigger"
    :data-size="size"
    v-bind="omitUndefinedProps(forwardedProps)"
    :class="
      cn(
        'tw:border-input tw:data-placeholder:text-muted-foreground tw:dark:bg-input/30 tw:dark:hover:bg-input/50 tw:focus-visible:border-ring tw:focus-visible:ring-ring/50 tw:aria-invalid:ring-destructive/20 tw:dark:aria-invalid:ring-destructive/40 tw:aria-invalid:border-destructive tw:dark:aria-invalid:border-destructive/50 tw:gap-1.5 tw:rounded-lg tw:border tw:bg-transparent tw:py-2 tw:pr-2 tw:pl-2.5 tw:text-sm tw:transition-colors tw:select-none tw:focus-visible:ring-3 tw:aria-invalid:ring-3 tw:data-[size=default]:h-8 tw:data-[size=sm]:h-7 tw:data-[size=sm]:rounded-[min(var(--radius-md),10px)] tw:*:data-[slot=select-value]:gap-1.5 tw:[&_svg:not([class*=size-])]:size-4 tw:flex tw:w-fit tw:items-center tw:justify-between tw:whitespace-nowrap tw:outline-none tw:disabled:cursor-not-allowed tw:disabled:opacity-50 tw:*:data-[slot=select-value]:line-clamp-1 tw:*:data-[slot=select-value]:flex tw:*:data-[slot=select-value]:items-center tw:[&_svg]:pointer-events-none tw:[&_svg]:shrink-0',
        props.class,
      )
    "
  >
    <slot />
    <SelectIcon as-child>
      <ChevronDownIcon class="tw:text-muted-foreground tw:size-4 tw:pointer-events-none" />
    </SelectIcon>
  </SelectTrigger>
</template>
