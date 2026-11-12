<script setup lang="ts">
import type { DialogContentEmits, DialogContentProps } from 'reka-ui';

import type { HTMLAttributes } from 'vue';
import { XIcon } from '@lucide/vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { omitUndefinedProps } from '@/components/ui/props';
import { DialogClose, DialogContent, DialogPortal, useForwardPropsEmits } from 'reka-ui';
import { Button } from '@/components/ui/button';
import SheetOverlay from './SheetOverlay.vue';

interface SheetContentProps extends DialogContentProps {
  class?: HTMLAttributes['class'];
  side?: 'top' | 'right' | 'bottom' | 'left';
  showCloseButton?: boolean;
}

defineOptions({
  inheritAttrs: false,
});

const props = withDefaults(defineProps<SheetContentProps>(), {
  side: 'right',
  showCloseButton: true,
});
const emits = defineEmits<DialogContentEmits>();

const delegatedProps = reactiveOmit(props, 'class', 'side', 'showCloseButton');

const forwarded = useForwardPropsEmits(delegatedProps, emits);
</script>

<template>
  <DialogPortal>
    <SheetOverlay />
    <DialogContent
      data-slot="sheet-content"
      :data-side="side"
      :class="
        cn(
          'tw:bg-popover tw:text-popover-foreground tw:fixed tw:z-50 tw:flex tw:flex-col tw:gap-4 tw:bg-clip-padding tw:text-sm tw:shadow-lg tw:transition tw:duration-200 tw:ease-in-out tw:data-[side=bottom]:inset-x-0 tw:data-[side=bottom]:bottom-0 tw:data-[side=bottom]:h-auto tw:data-[side=bottom]:border-t tw:data-[side=left]:inset-y-0 tw:data-[side=left]:left-0 tw:data-[side=left]:h-full tw:data-[side=left]:w-3/4 tw:data-[side=left]:border-r tw:data-[side=right]:inset-y-0 tw:data-[side=right]:right-0 tw:data-[side=right]:h-full tw:data-[side=right]:w-3/4 tw:data-[side=right]:border-l tw:data-[side=top]:inset-x-0 tw:data-[side=top]:top-0 tw:data-[side=top]:h-auto tw:data-[side=top]:border-b tw:data-[side=left]:sm:max-w-sm tw:data-[side=right]:sm:max-w-sm tw:data-open:animate-in tw:data-open:fade-in-0 tw:data-[side=bottom]:data-open:slide-in-from-bottom-10 tw:data-[side=left]:data-open:slide-in-from-left-10 tw:data-[side=right]:data-open:slide-in-from-right-10 tw:data-[side=top]:data-open:slide-in-from-top-10 tw:data-closed:animate-out tw:data-closed:fade-out-0 tw:data-[side=bottom]:data-closed:slide-out-to-bottom-10 tw:data-[side=left]:data-closed:slide-out-to-left-10 tw:data-[side=right]:data-closed:slide-out-to-right-10 tw:data-[side=top]:data-closed:slide-out-to-top-10',
          props.class,
        )
      "
      v-bind="omitUndefinedProps({ ...$attrs, ...forwarded })"
    >
      <slot />

      <DialogClose v-if="showCloseButton" data-slot="sheet-close" as-child>
        <Button variant="ghost" class="tw:absolute tw:top-3 tw:right-3" size="icon-sm">
          <XIcon />
          <span class="tw:sr-only">Close</span>
        </Button>
      </DialogClose>
    </DialogContent>
  </DialogPortal>
</template>
