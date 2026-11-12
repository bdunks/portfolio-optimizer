<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';
import { Separator } from '@/components/ui/separator';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <div
    data-slot="field-separator"
    :data-content="!!$slots.default"
    :class="
      cn(
        'tw:-my-2 tw:h-5 tw:text-sm tw:group-data-[variant=outline]/field-group:-mb-2 tw:relative',
        props.class,
      )
    "
  >
    <Separator class="tw:absolute tw:inset-0 tw:top-1/2" />
    <span
      v-if="$slots.default"
      class="tw:text-muted-foreground tw:px-2 tw:relative tw:mx-auto tw:block tw:w-fit tw:bg-background"
      data-slot="field-separator-content"
    >
      <slot />
    </span>
  </div>
</template>
