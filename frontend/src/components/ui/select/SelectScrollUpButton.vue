<script setup lang="ts">
import type { SelectScrollUpButtonProps } from 'reka-ui';

import type { HTMLAttributes } from 'vue';
import { ChevronUpIcon } from '@lucide/vue';
import { reactiveOmit } from '@vueuse/core';
import { omitUndefinedProps } from '@/components/ui/props';
import { cn } from 'cn';
import { SelectScrollUpButton, useForwardProps } from 'reka-ui';

const props = defineProps<SelectScrollUpButtonProps & { class?: HTMLAttributes['class'] }>();

const delegatedProps = reactiveOmit(props, 'class');

const forwardedProps = useForwardProps(delegatedProps);
</script>

<template>
  <SelectScrollUpButton
    data-slot="select-scroll-up-button"
    v-bind="omitUndefinedProps(forwardedProps)"
    :class="
      cn(
        'tw:bg-popover tw:z-10 tw:flex tw:cursor-default tw:items-center tw:justify-center tw:py-1 tw:[&_svg:not([class*=size-])]:size-4',
        props.class,
      )
    "
  >
    <slot>
      <ChevronUpIcon />
    </slot>
  </SelectScrollUpButton>
</template>
