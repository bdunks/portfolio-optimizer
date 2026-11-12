<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <div
    data-slot="sidebar-group"
    data-sidebar="group"
    :class="cn('tw:p-2 tw:relative tw:flex tw:w-full tw:min-w-0 tw:flex-col', props.class)"
  >
    <slot />
  </div>
</template>
