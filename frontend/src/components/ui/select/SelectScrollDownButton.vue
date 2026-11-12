<script setup lang="ts">
import type { SelectScrollDownButtonProps } from 'reka-ui';

import type { HTMLAttributes } from 'vue';
import { ChevronDownIcon } from '@lucide/vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { omitUndefinedProps } from '@/components/ui/props';
import { SelectScrollDownButton, useForwardProps } from 'reka-ui';

const props = defineProps<SelectScrollDownButtonProps & { class?: HTMLAttributes['class'] }>();

const delegatedProps = reactiveOmit(props, 'class');

const forwardedProps = useForwardProps(delegatedProps);
</script>

<template>
  <SelectScrollDownButton
    data-slot="select-scroll-down-button"
    v-bind="omitUndefinedProps(forwardedProps)"
    :class="
      cn(
        'tw:bg-popover tw:z-10 tw:flex tw:cursor-default tw:items-center tw:justify-center tw:py-1 tw:[&_svg:not([class*=size-])]:size-4',
        props.class,
      )
    "
  >
    <slot>
      <ChevronDownIcon />
    </slot>
  </SelectScrollDownButton>
</template>
