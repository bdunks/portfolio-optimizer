<script setup lang="ts">
import type { DialogTriggerProps } from 'reka-ui';
import { DialogTrigger } from 'reka-ui';
import { omitUndefinedProps } from '@/components/ui/props';

const props = defineProps<DialogTriggerProps>();
</script>

<template>
  <DialogTrigger data-slot="sheet-trigger" v-bind="omitUndefinedProps(props)">
    <slot />
  </DialogTrigger>
</template>
