<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <div
    data-slot="empty-title"
    :class="cn('tw:text-sm tw:font-medium tw:tracking-tight tw:cn-font-heading', props.class)"
  >
    <slot />
  </div>
</template>
