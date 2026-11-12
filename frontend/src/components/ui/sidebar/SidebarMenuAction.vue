<script setup lang="ts">
import type { PrimitiveProps } from 'reka-ui';
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';
import { Primitive } from 'reka-ui';

const props = withDefaults(
  defineProps<
    PrimitiveProps & {
      showOnHover?: boolean;
      class?: HTMLAttributes['class'];
    }
  >(),
  {
    as: 'button',
  },
);
</script>

<template>
  <Primitive
    data-slot="sidebar-menu-action"
    data-sidebar="menu-action"
    :class="
      cn(
        'tw:text-sidebar-foreground tw:ring-sidebar-ring tw:hover:bg-sidebar-accent tw:hover:text-sidebar-accent-foreground tw:peer-hover/menu-button:text-sidebar-accent-foreground tw:absolute tw:top-1.5 tw:right-1 tw:aspect-square tw:w-5 tw:rounded-md tw:p-0 tw:peer-data-[size=default]/menu-button:top-1.5 tw:peer-data-[size=lg]/menu-button:top-2.5 tw:peer-data-[size=sm]/menu-button:top-1 tw:focus-visible:ring-2 tw:[&>svg]:size-4 tw:flex tw:items-center tw:justify-center tw:outline-hidden tw:transition-transform tw:group-data-[collapsible=icon]:hidden tw:after:absolute tw:after:-inset-2 tw:md:after:hidden tw:[&>svg]:shrink-0',
        showOnHover &&
          'tw:group-focus-within/menu-item:opacity-100 tw:group-hover/menu-item:opacity-100 tw:peer-data-active/menu-button:text-sidebar-accent-foreground tw:aria-expanded:opacity-100 tw:md:opacity-0',
        props.class,
      )
    "
    :as="as"
    :as-child="asChild"
  >
    <slot />
  </Primitive>
</template>
