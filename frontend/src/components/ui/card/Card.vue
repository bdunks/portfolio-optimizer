<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = withDefaults(
  defineProps<{
    class?: HTMLAttributes['class'];
    size?: 'default' | 'sm';
  }>(),
  {
    size: 'default',
  },
);
</script>

<template>
  <div
    data-slot="card"
    :data-size="size"
    :class="
      cn(
        'tw:ring-foreground/10 tw:bg-card tw:text-card-foreground tw:gap-4 tw:overflow-hidden tw:rounded-xl tw:py-4 tw:text-sm tw:ring-1 tw:has-data-[slot=card-footer]:pb-0 tw:has-[>img:first-child]:pt-0 tw:data-[size=sm]:gap-3 tw:data-[size=sm]:py-3 tw:data-[size=sm]:has-data-[slot=card-footer]:pb-0 tw:*:[img:first-child]:rounded-t-xl tw:*:[img:last-child]:rounded-b-xl tw:group/card tw:flex tw:flex-col',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>
