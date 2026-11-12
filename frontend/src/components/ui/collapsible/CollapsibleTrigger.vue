<script setup lang="ts">
import { computed } from 'vue';
import type { CollapsibleTriggerProps } from 'reka-ui';
import { CollapsibleTrigger } from 'reka-ui';

const props = defineProps<CollapsibleTriggerProps>();
const forwarded = computed(() => ({ ...props, as: props.as ?? 'button' }));
</script>

<template>
  <CollapsibleTrigger data-slot="collapsible-trigger" v-bind="forwarded">
    <slot />
  </CollapsibleTrigger>
</template>
