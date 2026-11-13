<script setup lang="ts">
import { omitUndefinedProps } from '@/components/ui/props';
import type { DropdownMenuLabelProps } from 'reka-ui';
import type { HTMLAttributes } from 'vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { DropdownMenuLabel, useForwardProps } from 'reka-ui';

const props = defineProps<
  DropdownMenuLabelProps & { class?: HTMLAttributes['class']; inset?: boolean }
>();

const delegatedProps = reactiveOmit(props, 'class', 'inset');
const forwardedProps = useForwardProps(delegatedProps);
</script>

<template>
  <DropdownMenuLabel
    data-slot="dropdown-menu-label"
    :data-inset="inset ? '' : undefined"
    v-bind="omitUndefinedProps(forwardedProps)"
    :class="
      cn(
        'tw:text-muted-foreground tw:px-1.5 tw:py-1 tw:text-xs tw:font-medium tw:data-inset:pl-7',
        props.class,
      )
    "
  >
    <slot />
  </DropdownMenuLabel>
</template>
