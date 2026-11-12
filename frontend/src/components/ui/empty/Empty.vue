<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <div
    data-slot="empty"
    :class="
      cn(
        'tw:gap-4 tw:rounded-xl tw:border-dashed tw:p-6 tw:flex tw:w-full tw:min-w-0 tw:flex-1 tw:flex-col tw:items-center tw:justify-center tw:text-center tw:text-balance',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>
