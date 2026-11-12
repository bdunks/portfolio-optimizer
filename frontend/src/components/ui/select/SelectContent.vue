<script setup lang="ts">
import type { SelectContentEmits, SelectContentProps } from 'reka-ui';
import type { HTMLAttributes } from 'vue';
import { reactiveOmit } from '@vueuse/core';
import { omitUndefinedProps } from '@/components/ui/props';
import { cn } from 'cn';
import { SelectContent, SelectPortal, SelectViewport, useForwardPropsEmits } from 'reka-ui';
import { SelectScrollDownButton, SelectScrollUpButton } from '.';

defineOptions({
  inheritAttrs: false,
});

const props = withDefaults(
  defineProps<SelectContentProps & { class?: HTMLAttributes['class'] }>(),
  {
    position: 'item-aligned',
    align: 'center',
  },
);
const emits = defineEmits<SelectContentEmits>();

const delegatedProps = reactiveOmit(props, 'class');

const forwarded = useForwardPropsEmits(delegatedProps, emits);
</script>

<template>
  <SelectPortal>
    <SelectContent
      data-slot="select-content"
      :data-align-trigger="position === 'item-aligned'"
      v-bind="omitUndefinedProps({ ...$attrs, ...forwarded })"
      :class="
        cn(
          'tw:bg-popover tw:text-popover-foreground tw:data-open:animate-in tw:data-closed:animate-out tw:data-closed:fade-out-0 tw:data-open:fade-in-0 tw:data-closed:zoom-out-95 tw:data-open:zoom-in-95 tw:data-[side=bottom]:slide-in-from-top-2 tw:data-[side=left]:slide-in-from-right-2 tw:data-[side=right]:slide-in-from-left-2 tw:data-[side=top]:slide-in-from-bottom-2 tw:ring-foreground/10 tw:min-w-36 tw:rounded-lg tw:shadow-md tw:ring-1 tw:duration-100 tw:data-[side=inline-start]:slide-in-from-right-2 tw:data-[side=inline-end]:slide-in-from-left-2 tw: tw:cn-menu-translucent tw:relative tw:z-50 tw:max-h-(--reka-select-content-available-height) tw:origin-(--reka-select-content-transform-origin) tw:overflow-x-hidden tw:overflow-y-auto tw:data-[align-trigger=true]:animate-none',
          position === 'popper' &&
            'tw:data-[side=bottom]:translate-y-1 tw:data-[side=left]:-translate-x-1 tw:data-[side=right]:translate-x-1 tw:data-[side=top]:-translate-y-1',
          props.class,
        )
      "
    >
      <SelectScrollUpButton />
      <SelectViewport
        :data-position="position"
        :class="
          cn(
            'tw:data-[position=popper]:h-(--reka-select-trigger-height) tw:data-[position=popper]:w-full tw:data-[position=popper]:min-w-(--reka-select-trigger-width)',
          )
        "
      >
        <slot />
      </SelectViewport>
      <SelectScrollDownButton />
    </SelectContent>
  </SelectPortal>
</template>
