<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <ul
    data-slot="sidebar-menu"
    data-sidebar="menu"
    :class="
      cn(
        'tw:m-0 tw:list-none tw:p-0 tw:gap-0 tw:flex tw:w-full tw:min-w-0 tw:flex-col',
        props.class,
      )
    "
  >
    <slot />
  </ul>
</template>
