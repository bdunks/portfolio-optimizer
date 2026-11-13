<script setup lang="ts">
import { omitUndefinedProps } from '@/components/ui/props';
import type { DropdownMenuSubContentEmits, DropdownMenuSubContentProps } from 'reka-ui';
import type { HTMLAttributes } from 'vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { DropdownMenuSubContent, useForwardPropsEmits } from 'reka-ui';

const props = defineProps<DropdownMenuSubContentProps & { class?: HTMLAttributes['class'] }>();
const emits = defineEmits<DropdownMenuSubContentEmits>();

const delegatedProps = reactiveOmit(props, 'class');

const forwarded = useForwardPropsEmits(delegatedProps, emits);
</script>

<template>
  <DropdownMenuSubContent
    data-slot="dropdown-menu-sub-content"
    v-bind="omitUndefinedProps(forwarded)"
    :class="
      cn(
        'tw:data-open:animate-in tw:data-closed:animate-out tw:data-closed:fade-out-0 tw:data-open:fade-in-0 tw:data-closed:zoom-out-95 tw:data-open:zoom-in-95 tw:data-[side=bottom]:slide-in-from-top-2 tw:data-[side=left]:slide-in-from-right-2 tw:data-[side=right]:slide-in-from-left-2 tw:data-[side=top]:slide-in-from-bottom-2 tw:ring-foreground/10 tw:bg-popover tw:text-popover-foreground tw:min-w-[96px] tw:rounded-lg tw:p-1 tw:shadow-lg tw:ring-1 tw:duration-100 tw: tw:cn-menu-translucent tw:z-50 tw:max-w-(--reka-dropdown-menu-content-available-width) tw:origin-(--reka-dropdown-menu-content-transform-origin) tw:overflow-hidden',
        props.class,
      )
    "
  >
    <slot />
  </DropdownMenuSubContent>
</template>
