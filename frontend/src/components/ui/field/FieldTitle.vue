<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <div
    data-slot="field-label"
    :class="
      cn(
        'tw:gap-2 tw:text-sm tw:font-medium tw:group-data-[disabled=true]/field:opacity-50 tw:flex tw:w-fit tw:items-center tw:leading-snug',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>
