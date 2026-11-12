<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <div
    data-slot="field-group"
    :class="
      cn(
        'tw:gap-5 tw:data-[slot=checkbox-group]:gap-3 tw:*:data-[slot=field-group]:gap-4 tw:group/field-group tw:@container/field-group tw:flex tw:w-full tw:flex-col',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>
