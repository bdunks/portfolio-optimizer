<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{ class?: HTMLAttributes['class'] }>();
</script>

<template>
  <div data-slot="sheet-header" :class="cn('tw:gap-0.5 tw:p-4 tw:flex tw:flex-col', props.class)">
    <slot />
  </div>
</template>
