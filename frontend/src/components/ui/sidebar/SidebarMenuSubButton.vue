<script setup lang="ts">
import type { PrimitiveProps } from 'reka-ui';
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';
import { Primitive } from 'reka-ui';

const props = withDefaults(
  defineProps<
    PrimitiveProps & {
      size?: 'sm' | 'md';
      isActive?: boolean;
      class?: HTMLAttributes['class'];
    }
  >(),
  {
    as: 'a',
    size: 'md',
  },
);
</script>

<template>
  <Primitive
    data-slot="sidebar-menu-sub-button"
    data-sidebar="menu-sub-button"
    :as="as"
    :as-child="asChild"
    :data-size="size"
    :data-active="isActive || undefined"
    :class="
      cn(
        'tw:text-sidebar-foreground tw:ring-sidebar-ring tw:hover:bg-sidebar-accent tw:hover:text-sidebar-accent-foreground tw:active:bg-sidebar-accent tw:active:text-sidebar-accent-foreground tw:[&>svg]:text-sidebar-accent-foreground tw:data-active:bg-sidebar-accent tw:data-active:text-sidebar-accent-foreground tw:h-7 tw:gap-2 tw:rounded-md tw:px-2 tw:focus-visible:ring-2 tw:data-[size=md]:text-sm tw:data-[size=sm]:text-xs tw:[&>svg]:size-4 tw:flex tw:min-w-0 tw:-translate-x-px tw:items-center tw:overflow-hidden tw:outline-hidden tw:group-data-[collapsible=icon]:hidden tw:disabled:pointer-events-none tw:disabled:opacity-50 tw:aria-disabled:pointer-events-none tw:aria-disabled:opacity-50 tw:[&>span:last-child]:truncate tw:[&>svg]:shrink-0',
        props.class,
      )
    "
  >
    <slot />
  </Primitive>
</template>
