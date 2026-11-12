<script setup lang="ts">
import type { DialogTitleProps } from 'reka-ui';
import type { HTMLAttributes } from 'vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { omitUndefinedProps } from '@/components/ui/props';
import { DialogTitle } from 'reka-ui';

const props = defineProps<DialogTitleProps & { class?: HTMLAttributes['class'] }>();

const delegatedProps = reactiveOmit(props, 'class');
</script>

<template>
  <DialogTitle
    data-slot="sheet-title"
    :class="cn('tw:text-foreground tw:text-base tw:font-medium tw:cn-font-heading', props.class)"
    v-bind="omitUndefinedProps(delegatedProps)"
  >
    <slot />
  </DialogTitle>
</template>
