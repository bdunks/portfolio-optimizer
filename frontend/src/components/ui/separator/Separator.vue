<script setup lang="ts">
import type { SeparatorProps } from 'reka-ui';
import type { HTMLAttributes } from 'vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { omitUndefinedProps } from '@/components/ui/props';
import { Separator } from 'reka-ui';

const props = withDefaults(defineProps<SeparatorProps & { class?: HTMLAttributes['class'] }>(), {
  as: 'div',
  asChild: false,
  orientation: 'horizontal',
  decorative: true,
});

const delegatedProps = reactiveOmit(props, 'class');
</script>

<template>
  <Separator
    data-slot="separator"
    v-bind="omitUndefinedProps(delegatedProps)"
    :class="
      cn(
        'tw:shrink-0 tw:bg-border tw:data-[orientation=horizontal]:h-px tw:data-[orientation=horizontal]:w-full tw:data-[orientation=vertical]:w-px tw:data-[orientation=vertical]:self-stretch',
        props.class,
      )
    "
  />
</template>
