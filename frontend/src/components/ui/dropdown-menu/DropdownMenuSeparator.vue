<script setup lang="ts">
import { omitUndefinedProps } from '@/components/ui/props';
import type { DropdownMenuSeparatorProps } from 'reka-ui';
import type { HTMLAttributes } from 'vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { DropdownMenuSeparator } from 'reka-ui';

const props = defineProps<
  DropdownMenuSeparatorProps & {
    class?: HTMLAttributes['class'];
  }
>();

const delegatedProps = reactiveOmit(props, 'class');
</script>

<template>
  <DropdownMenuSeparator
    data-slot="dropdown-menu-separator"
    v-bind="omitUndefinedProps(delegatedProps)"
    :class="cn('tw:bg-border tw:-mx-1 tw:my-1 tw:h-px', props.class)"
  />
</template>
