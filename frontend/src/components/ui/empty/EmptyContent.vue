<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <div
    data-slot="empty-content"
    :class="
      cn(
        'tw:gap-2.5 tw:text-sm tw:flex tw:w-full tw:max-w-sm tw:min-w-0 tw:flex-col tw:items-center tw:text-balance',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>
