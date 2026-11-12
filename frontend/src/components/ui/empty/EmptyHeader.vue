<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <div
    data-slot="empty-header"
    :class="cn('tw:gap-2 tw:flex tw:max-w-sm tw:flex-col tw:items-center', props.class)"
  >
    <slot />
  </div>
</template>
