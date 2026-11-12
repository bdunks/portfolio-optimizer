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
    data-slot="sidebar-group-action"
    data-sidebar="group-action"
    v-bind="omitUndefinedProps({ as, asChild })"
    :class="
      cn(
        'tw:text-sidebar-foreground tw:ring-sidebar-ring tw:hover:bg-sidebar-accent tw:hover:text-sidebar-accent-foreground tw:absolute tw:top-3.5 tw:right-3 tw:w-5 tw:rounded-md tw:p-0 tw:focus-visible:ring-2 tw:[&>svg]:size-4 tw:flex tw:aspect-square tw:items-center tw:justify-center tw:outline-hidden tw:transition-transform tw:group-data-[collapsible=icon]:hidden tw:after:absolute tw:after:-inset-2 tw:md:after:hidden tw:[&>svg]:shrink-0',
        props.class,
      )
    "
  >
    <slot />
  </Primitive>
</template>
