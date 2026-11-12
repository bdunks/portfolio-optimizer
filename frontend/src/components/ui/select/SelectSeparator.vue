<script setup lang="ts">
import type { SelectSeparatorProps } from 'reka-ui';
import type { HTMLAttributes } from 'vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { omitUndefinedProps } from '@/components/ui/props';
import { SelectSeparator } from 'reka-ui';

const props = defineProps<SelectSeparatorProps & { class?: HTMLAttributes['class'] }>();

const delegatedProps = reactiveOmit(props, 'class');
</script>

<template>
  <SelectSeparator
    data-slot="select-separator"
    v-bind="omitUndefinedProps(delegatedProps)"
    :class="cn('tw:bg-border tw:-mx-1 tw:my-1 tw:h-px tw:pointer-events-none', props.class)"
  />
</template>
