<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';
import { Label } from '@/components/ui/label';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <Label
    data-slot="field-label"
    :class="
      cn(
        'tw:has-data-checked:bg-primary/5 tw:has-data-checked:border-primary/30 tw:dark:has-data-checked:border-primary/20 tw:dark:has-data-checked:bg-primary/10 tw:gap-2 tw:group-data-[disabled=true]/field:opacity-50 tw:has-[>[data-slot=field]]:rounded-lg tw:has-[>[data-slot=field]]:border tw:*:data-[slot=field]:p-2.5 tw:group/field-label tw:peer/field-label tw:flex tw:w-fit tw:leading-snug',
        'tw:has-[>[data-slot=field]]:w-full tw:has-[>[data-slot=field]]:flex-col',
        props.class,
      )
    "
  >
    <slot />
  </Label>
</template>
