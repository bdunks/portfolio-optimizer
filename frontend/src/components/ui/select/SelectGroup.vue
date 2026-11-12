<script setup lang="ts">
import type { SelectGroupProps } from 'reka-ui';
import type { HTMLAttributes } from 'vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { SelectGroup } from 'reka-ui';
import { omitUndefinedProps } from '@/components/ui/props';

const props = defineProps<SelectGroupProps & { class?: HTMLAttributes['class'] }>();

const delegatedProps = reactiveOmit(props, 'class');
</script>

<template>
  <SelectGroup
    data-slot="select-group"
    v-bind="omitUndefinedProps(delegatedProps)"
    :class="cn('tw:scroll-my-1 tw:p-1', props.class)"
  >
    <slot />
  </SelectGroup>
</template>
