<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <div data-slot="alert-action" :class="cn('tw:absolute tw:top-2 tw:right-2', props.class)">
    <slot />
  </div>
</template>
