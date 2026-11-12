<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <div
    data-slot="field-content"
    :class="
      cn(
        'tw:gap-0.5 tw:group/field-content tw:flex tw:flex-1 tw:flex-col tw:leading-snug',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>
