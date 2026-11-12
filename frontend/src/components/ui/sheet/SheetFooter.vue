<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{ class?: HTMLAttributes['class'] }>();
</script>

<template>
  <div
    data-slot="sheet-footer"
    :class="cn('tw:gap-2 tw:p-4 tw:mt-auto tw:flex tw:flex-col', props.class)"
  >
    <slot />
  </div>
</template>
