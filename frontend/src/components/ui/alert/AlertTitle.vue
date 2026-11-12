<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <div
    data-slot="alert-title"
    :class="
      cn(
        'tw:font-medium tw:group-has-[>svg]/alert:col-start-2 tw:cn-font-heading tw:[&_a]:underline tw:[&_a]:underline-offset-3 tw:[&_a]:hover:text-foreground',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>
