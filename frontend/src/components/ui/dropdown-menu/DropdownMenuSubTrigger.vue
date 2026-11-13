<script setup lang="ts">
import { omitUndefinedProps } from '@/components/ui/props';
import type { DropdownMenuSubTriggerProps } from 'reka-ui';

import type { HTMLAttributes } from 'vue';
import { ChevronRightIcon } from '@lucide/vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { DropdownMenuSubTrigger, useForwardProps } from 'reka-ui';

const props = defineProps<
  DropdownMenuSubTriggerProps & { class?: HTMLAttributes['class']; inset?: boolean }
>();

const delegatedProps = reactiveOmit(props, 'class', 'inset');
const forwardedProps = useForwardProps(delegatedProps);
</script>

<template>
  <DropdownMenuSubTrigger
    data-slot="dropdown-menu-sub-trigger"
    :data-inset="inset ? '' : undefined"
    v-bind="omitUndefinedProps(forwardedProps)"
    :class="
      cn(
        'tw:focus:bg-accent tw:focus:text-accent-foreground tw:data-open:bg-accent tw:data-open:text-accent-foreground tw:not-data-[variant=destructive]:focus:**:text-accent-foreground tw:gap-1.5 tw:rounded-md tw:px-1.5 tw:py-1 tw:text-sm tw:data-inset:pl-7 tw:[&_svg:not([class*=size-])]:size-4 tw:flex tw:cursor-default tw:items-center tw:outline-hidden tw:select-none tw:[&_svg]:pointer-events-none tw:[&_svg]:shrink-0',
        props.class,
      )
    "
  >
    <slot />
    <ChevronRightIcon class="tw:cn-rtl-flip tw:ml-auto" />
  </DropdownMenuSubTrigger>
</template>
