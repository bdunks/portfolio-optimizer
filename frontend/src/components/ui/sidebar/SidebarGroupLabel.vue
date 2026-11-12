<script setup lang="ts">
import type { PrimitiveProps } from 'reka-ui';
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';
import { omitUndefinedProps } from '@/components/ui/props';
import { Primitive } from 'reka-ui';

const props = defineProps<
  PrimitiveProps & {
    class?: HTMLAttributes['class'];
  }
>();
</script>

<template>
  <Primitive
    data-slot="sidebar-group-label"
    data-sidebar="group-label"
    v-bind="omitUndefinedProps({ as, asChild })"
    :class="
      cn(
        'tw:text-sidebar-foreground/70 tw:ring-sidebar-ring tw:h-8 tw:rounded-md tw:px-2 tw:text-xs tw:font-medium tw:transition-[margin,opacity] tw:duration-200 tw:ease-linear tw:group-data-[collapsible=icon]:pointer-events-none tw:group-data-[collapsible=icon]:-mt-8 tw:group-data-[collapsible=icon]:select-none tw:group-data-[collapsible=icon]:opacity-0 tw:focus-visible:ring-2 tw:[&>svg]:size-4 tw:flex tw:shrink-0 tw:items-center tw:outline-hidden tw:[&>svg]:shrink-0',
        props.class,
      )
    "
  >
    <slot />
  </Primitive>
</template>
