<script setup lang="ts">
import type { DialogDescriptionProps } from 'reka-ui';
import type { HTMLAttributes } from 'vue';
import { reactiveOmit } from '@vueuse/core';
import { cn } from 'cn';
import { omitUndefinedProps } from '@/components/ui/props';
import { DialogDescription } from 'reka-ui';

const props = defineProps<DialogDescriptionProps & { class?: HTMLAttributes['class'] }>();

const delegatedProps = reactiveOmit(props, 'class');
</script>

<template>
  <DialogDescription
    data-slot="sheet-description"
    :class="cn('tw:text-muted-foreground tw:text-sm', props.class)"
    v-bind="omitUndefinedProps(delegatedProps)"
  >
    <slot />
  </DialogDescription>
</template>
