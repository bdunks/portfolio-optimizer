<script setup lang="ts">
import type { SelectItemProps } from 'reka-ui';

import type { HTMLAttributes } from 'vue';
import { CheckIcon } from '@lucide/vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { omitUndefinedProps } from '@/components/ui/props';
import { SelectItem, SelectItemIndicator, SelectItemText, useForwardProps } from 'reka-ui';

const props = defineProps<SelectItemProps & { class?: HTMLAttributes['class'] }>();

const delegatedProps = reactiveOmit(props, 'class');

const forwardedProps = useForwardProps(delegatedProps);
</script>

<template>
  <SelectItem
    data-slot="select-item"
    v-bind="omitUndefinedProps(forwardedProps)"
    :value="props.value"
    :class="
      cn(
        'tw:focus:bg-accent tw:focus:text-accent-foreground tw:not-data-[variant=destructive]:focus:**:text-accent-foreground tw:gap-1.5 tw:rounded-md tw:py-1 tw:pr-8 tw:pl-1.5 tw:text-sm tw:[&_svg:not([class*=size-])]:size-4 tw:*:[span]:last:flex tw:*:[span]:last:items-center tw:*:[span]:last:gap-2 tw:relative tw:flex tw:w-full tw:cursor-default tw:items-center tw:outline-hidden tw:select-none tw:data-[disabled]:pointer-events-none tw:data-[disabled]:opacity-50 tw:[&_svg]:pointer-events-none tw:[&_svg]:shrink-0',
        props.class,
      )
    "
  >
    <span
      class="tw:pointer-events-none tw:absolute tw:right-2 tw:flex tw:size-4 tw:items-center tw:justify-center"
    >
      <SelectItemIndicator>
        <slot name="indicator-icon">
          <CheckIcon class="tw:pointer-events-none" />
        </slot>
      </SelectItemIndicator>
    </span>

    <SelectItemText>
      <slot />
    </SelectItemText>
  </SelectItem>
</template>
