<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <p
    data-slot="field-description"
    :class="
      cn(
        'tw:text-muted-foreground tw:text-left tw:text-sm tw:[[data-variant=legend]+&]:-mt-1.5 tw:leading-normal tw:font-normal tw:group-has-data-horizontal/field:text-balance',
        'tw:last:mt-0 tw:nth-last-2:-mt-1',
        'tw:[&>a]:underline tw:[&>a]:underline-offset-4 tw:[&>a:hover]:text-primary',
        props.class,
      )
    "
  >
    <slot />
  </p>
</template>
