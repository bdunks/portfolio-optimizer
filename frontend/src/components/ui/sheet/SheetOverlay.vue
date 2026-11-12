<script setup lang="ts">
import type { DialogOverlayProps } from 'reka-ui';
import type { HTMLAttributes } from 'vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { omitUndefinedProps } from '@/components/ui/props';
import { DialogOverlay } from 'reka-ui';

const props = defineProps<DialogOverlayProps & { class?: HTMLAttributes['class'] }>();

const delegatedProps = reactiveOmit(props, 'class');
</script>

<template>
  <DialogOverlay
    data-slot="sheet-overlay"
    :class="
      cn(
        'tw:bg-black/10 tw:supports-backdrop-filter:backdrop-blur-xs tw:fixed tw:inset-0 tw:z-50 tw:duration-100 tw:data-open:animate-in tw:data-open:fade-in-0 tw:data-closed:animate-out tw:data-closed:fade-out-0',
        props.class,
      )
    "
    v-bind="omitUndefinedProps(delegatedProps)"
  >
    <slot />
  </DialogOverlay>
</template>
