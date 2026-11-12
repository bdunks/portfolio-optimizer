<script setup lang="ts">
import type { DialogCloseProps } from 'reka-ui';
import { omitUndefinedProps } from '@/components/ui/props';
import { DialogClose } from 'reka-ui';

const props = defineProps<DialogCloseProps>();
</script>

<template>
  <DialogClose data-slot="sheet-close" v-bind="omitUndefinedProps(props)">
    <slot />
  </DialogClose>
</template>
