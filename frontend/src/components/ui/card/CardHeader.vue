<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <div
    data-slot="card-header"
    :class="
      cn(
        'tw:gap-1 tw:rounded-t-xl tw:px-4 tw:group-data-[size=sm]/card:px-3 tw:[.border-b]:pb-4 tw:group-data-[size=sm]/card:[.border-b]:pb-3 tw:group/card-header tw:@container/card-header tw:grid tw:auto-rows-min tw:items-start tw:has-data-[slot=card-action]:grid-cols-[1fr_auto] tw:has-data-[slot=card-description]:grid-rows-[auto_auto]',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>
