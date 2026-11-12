<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <div
    data-slot="alert-description"
    :class="
      cn(
        'tw:text-muted-foreground tw:text-sm tw:text-balance tw:md:text-pretty tw:[&_p:not(:last-child)]:mb-4 tw:[&_a]:underline tw:[&_a]:underline-offset-3 tw:[&_a]:hover:text-foreground',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>
