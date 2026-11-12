<script setup lang="ts">
import { computed } from 'vue';
import type { CollapsibleContentProps } from 'reka-ui';
import { CollapsibleContent } from 'reka-ui';

const props = defineProps<CollapsibleContentProps>();
const forwarded = computed(() => ({ ...props, as: props.as ?? 'div' }));
</script>

<template>
  <CollapsibleContent data-slot="collapsible-content" v-bind="forwarded">
    <slot />
  </CollapsibleContent>
</template>
