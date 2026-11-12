<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import { cn } from 'cn';

const props = defineProps<{
  class?: HTMLAttributes['class'];
}>();
</script>

<template>
  <fieldset
    data-slot="field-set"
    :class="
      cn(
        'tw:gap-4 tw:has-[>[data-slot=checkbox-group]]:gap-3 tw:has-[>[data-slot=radio-group]]:gap-3 tw:flex tw:flex-col',
        props.class,
      )
    "
  >
    <slot />
  </fieldset>
</template>
