<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <div
    data-slot="card-footer"
    :class="
      cn(
        'tw:bg-muted/50 tw:rounded-b-xl tw:border-t tw:p-4 tw:group-data-[size=sm]/card:p-3 tw:flex tw:items-center',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>
