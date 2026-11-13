<script setup lang="ts">
import { omitUndefinedProps } from '@/components/ui/props';
import type { DropdownMenuItemProps } from 'reka-ui';
import type { HTMLAttributes } from 'vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { DropdownMenuItem, useForwardProps } from 'reka-ui';

const props = withDefaults(
  defineProps<
    DropdownMenuItemProps & {
      class?: HTMLAttributes['class'];
      inset?: boolean;
      variant?: 'default' | 'destructive';
    }
  >(),
  {
    variant: 'default',
  },
);

const delegatedProps = reactiveOmit(props, 'inset', 'variant', 'class');

const forwardedProps = useForwardProps(delegatedProps);
</script>

<template>
  <DropdownMenuItem
    data-slot="dropdown-menu-item"
    :data-inset="inset ? '' : undefined"
    :data-variant="variant"
    v-bind="omitUndefinedProps(forwardedProps)"
    :class="
      cn(
        'tw:focus:bg-accent tw:focus:text-accent-foreground tw:data-[variant=destructive]:text-destructive tw:data-[variant=destructive]:focus:bg-destructive/10 tw:dark:data-[variant=destructive]:focus:bg-destructive/20 tw:data-[variant=destructive]:focus:text-destructive tw:data-[variant=destructive]:*:[svg]:text-destructive tw:not-data-[variant=destructive]:focus:**:text-accent-foreground tw:gap-1.5 tw:rounded-md tw:px-1.5 tw:py-1 tw:text-sm tw:data-inset:pl-7 tw:[&_svg:not([class*=size-])]:size-4 tw:group/dropdown-menu-item tw:relative tw:flex tw:cursor-default tw:items-center tw:outline-hidden tw:select-none tw:data-disabled:pointer-events-none tw:data-disabled:opacity-50 tw:[&_svg]:pointer-events-none tw:[&_svg]:shrink-0',
        props.class,
      )
    "
  >
    <slot />
  </DropdownMenuItem>
</template>
