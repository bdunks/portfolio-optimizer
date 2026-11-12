<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <ul
    data-slot="sidebar-menu-sub"
    data-sidebar="menu-sub"
    :class="
      cn(
        'tw:border-sidebar-border tw:mx-3.5 tw:translate-x-px tw:gap-1 tw:border-l tw:px-2.5 tw:py-0.5 tw:group-data-[collapsible=icon]:hidden tw:flex tw:min-w-0 tw:flex-col',
        props.class,
      )
    "
  >
    <slot />
  </ul>
</template>
