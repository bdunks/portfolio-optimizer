<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <div
    data-slot="card-title"
    :class="
      cn(
        'tw:text-base tw:leading-snug tw:font-medium tw:group-data-[size=sm]/card:text-sm tw:cn-font-heading',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>
