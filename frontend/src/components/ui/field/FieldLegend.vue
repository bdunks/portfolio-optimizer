<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = withDefaults(
  defineProps<{
    class?: HTMLAttributes['class'];
    variant?: 'legend' | 'label';
  }>(),
  {
    variant: 'legend',
  },
);
</script>

<template>
  <legend
    data-slot="field-legend"
    :data-variant="variant"
    :class="
      cn(
        'tw:mb-1.5 tw:font-medium tw:data-[variant=label]:text-sm tw:data-[variant=legend]:text-base',
        props.class,
      )
    "
  >
    <slot />
  </legend>
</template>
